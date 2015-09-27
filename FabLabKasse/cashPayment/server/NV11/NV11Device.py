#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# Interface client for Innovative Technology NV11 banknote validator/changer with eSSP Protocol
# based on the official specification (Innovative Technology GA138 SSP Protocol Manual) and a lot of own practical tests

# (C) 2013 Max Gaukler <development@maxgaukler.de>

#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  The text of the license conditions can be read at
#  <http://www.gnu.org/licenses/>.

import serial
import copy
import time
import traceback
from crc_algorithms import Crc
import Crypto.Cipher.AES
import Crypto.Random.random
import logging
from ..hex import hex


class ESSPDevice(object):

    """low layer eSSP protocol - implements the network layer and all communication-related commands"""

    def __init__(self, port, presharedKey=0x0123456701234567, slaveID=0):

        ESSPDevice.Helper.unitTest()
        ESSPDevice.ByteStreamReader.unitTest()
        self.ser = serial.serial_for_url(port, 9600, timeout=0.2)
        self.seq = 0
        self.slaveID = slaveID
        self.rawBuffer = []
        self.buffer = []
        self.lastPacket = None
        self.crypt = None
        self.encryptionCounter = None

        self.unencryptedCommand([0x11])  # sync: start communications

        self.initCrypto(presharedKey)

    # debug functions
    def __repr__(self):
        return "<ESSP>"

    def printDebug(self, s, debugLevel):
        logLevels = {-1: logging.ERROR,  0: logging.WARNING,  1: logging.INFO, 2: logging.DEBUG,  3: logging.DEBUG - 1}
        logging.getLogger(self.__repr__()).log(logLevels[debugLevel], s)

    def error(self, s):
        self.printDebug(s, -1)

    def log(self, s):
        self.printDebug(s, 1)

    def warn(self, s):
        self.printDebug(s, 0)

    def debug(self, s):
        self.printDebug(s, 2)

    def debug2(self, s):
        self.printDebug(s, 3)

    class Helper(object):
        CRC = Crc(width=16,  poly=0x8005, reflect_in=False, xor_in=0xFFFF, reflect_out=False, xor_out=0x0000)  # specification is slightly unclear, figured out by trial-and-error

        @staticmethod
        def unitTest():
            assert ESSPDevice.Helper.crc([0x80, 0x01, 0x01]) == [0x06,  0x02]
            assert ESSPDevice.Helper.crc([0x80, 0x01, 0xF0]) == [0x23,  0x80]

        @classmethod
        def splitBytes(cls,  uint16):
            # uint16 -> [lowByte, highByte]
            return [uint16 & 0xFF,  uint16 >> 8]

        @classmethod
        def crc(cls, data):
            c = cls.CRC.bit_by_bit(data)
            return cls.splitBytes(c)

        @classmethod
        def Unsigned32ToBytes(cls, x):
            # return little-endian representation
            return ESSPDevice.Helper.UnsignedToBytes(x, n=4)

        @staticmethod
        def Unsigned64ToBytes(x):
            # return little-endian representation
            return ESSPDevice.Helper.UnsignedToBytes(x, n=8)

        @staticmethod
        def UnsignedToBytes(x, n):
            r = []
            for i in range(n):
                r.append(x & 0xFF)
                x = x >> 8
            return r

        @classmethod
        def AsciiToBytes(cls, x):
            return [ord(c) for c in x]

        @staticmethod
        def byteArrayToString(data):
            return b''.join([chr(x) for x in data])

        @staticmethod
        def stringToByteArray(string):
            return ([ord(x) for x in string])

    class ByteStreamReader:  # read data values from a list of bytes

        def __init__(self, bytesList):
            self.buffer = copy.deepcopy(bytesList)

        @staticmethod
        def unitTest():
            test = ESSPDevice.ByteStreamReader([0x00, 0x1C, 0x96, 0x2C])
            assert test.readUnsigned32BigEndian() == 0x1c962c
            test.assertFinished()

        def readData(self, n):
            assert len(self.buffer) >= n
            data = copy.deepcopy(self.buffer[0:n])
            del self.buffer[0:n]
            return data

        def hasData(self):
            return len(self.buffer) > 0

        def readByte(self):
            # unsigned int8
            return self.readData(1)[0]

        # read a n-bytes unsigned integer, little or big endian
        def readUnsigned(self, numBytes, littleEndian):
            data = self.readData(numBytes)
            if littleEndian:
                data.reverse()
            result = 0
            for byte in data:
                result *= 256
                result += byte
            return result

        def readUnsigned32(self, CheckOverrun=True):
            d = self.readUnsigned(numBytes=4, littleEndian=True)
            # values should be far far away from the integer maximum.
            # if the most significant byte is very large, a decoding error is very likely
            # even the value counters won't be that large for heavy use:
            # 10k€/month * 100 ct/euro * 12 months/year * 10 years < 2**31 !
            if CheckOverrun:
                assert d <= 2 ** 31
            return d

        def readUnsigned32BigEndian(self):
            # big-endian version of previous function
            d = self.readUnsigned(numBytes=4, littleEndian=False)
            assert d <= 2 ** 31
            return d

        def readUnsigned24(self):
            # unsigned int24 little-endian
            return self.readUnsigned(numBytes=3, littleEndian=True)

        def readUnsigned24BigEndian(self):
            return self.readUnsigned(numBytes=3, littleEndian=False)

        def readAscii(self, n):
            d = self.readData(n)
            for byte in d:
                # only printable ASCII characters allowed
                assert byte >= 32
                assert byte <= 126
            # ASCII byte-array to string
            return "".join(map(chr, d))

        def assertFinished(self):  # assert that there is no data left - use this at the end of parsing fixed-length replies
            assert not self.hasData()

    #
    # Low-Level Send/Receive
    #
    def send(self, data):
        self.debug2("encoding packet: " + hex(data))
        # alternate sequence bit
        self.seq = int(not self.seq)
        content = [self.seq * 128 + self.slaveID, len(data)] + data
        content = content + ESSPDevice.Helper.crc(content)

        def bytestuff(bytesList):
            output = []
            for b in bytesList:
                output.append(b)
                if b == 0x7F:
                    # 0x7F is repeated once ("byte stuffing")
                    output.append(b)
            return output

        content = bytestuff(content)

        packet = [0x7F] + content

        self.debug2("sending raw packet: " + hex(packet))
        packetString = ""
        for byte in packet:
            packetString = packetString + chr(byte)
        self.ser.write(packetString)
        self.lastPacket = packetString

    def resendLast(self):
        self.debug("resending last packet")
        self.ser.write(self.lastPacket)

    # clear all read buffers
    def flushRead(self):
        while self.ser.inWaiting() > 0:
            self.warn("flushing serial read buffer")
            self.ser.read(self.ser.inWaiting())
        if len(self.rawBuffer) > 0:
            self.warn("flushing raw input buffer")
            self.rawBuffer = []
        if len(self.buffer) > 0:
            self.warn("flushing input buffer")
            self.buffer = []

    # get data from serial port - call this repeatedly until it returns False, then again after some waiting time
    # if data was received for the right slaveID, it returns a Response object containing data and status
    def read(self):
        bytesToRead = self.ser.inWaiting()
        if bytesToRead > 0:
            self.debug2("received " + str(bytesToRead) + " bytes")
            rxString = self.ser.read(bytesToRead)
            self.debug2("raw buffer at start of read()  (old data): " + hex(self.rawBuffer))
            for char in rxString:
                self.rawBuffer.append(ord(char))
            self.debug2("raw buffer before byte-destuffing: " + hex(self.rawBuffer))

        # read bytes for de-stuffing

        while len(self.rawBuffer) > 0:
            if self.rawBuffer[0] == 0x7F:
                # the STX byte needs special care (byte-stuffing needs to be reversed)
                if len(self.rawBuffer) == 1:
                    # a 0x7F byte at the end of the buffer cannot be processed yet (unclear if it will be followed by another by 0x7F)
                    break
                if self.rawBuffer[1] == 0x7F:
                    # we got a byte-stuffed 0x7F databyte
                    self.buffer.append(0x7F)
                    del self.rawBuffer[0:2]  # delete first two elements (indices 0 and 1)
                else:
                    # we received a real STX byte
                    # store it as -1 (special value)
                    del self.rawBuffer[0]
                    self.buffer.append(-1)
            else:
                # accept other bytes unmodified
                self.buffer.append(self.rawBuffer.pop(0))

        # parse data
        # data format AFTER bytestuffing:
        # 0: STX byte (originally 0x7F, now -1)
        # 1: sequence bit + slave ID
        # 2: length
        # 3 ... 3+length-1: data
        # 4+length-1 ... 5+length-1: CRC

        # attention, python subranging is a bit strange: array[a:b] returns array[a] ... array[b-1]   (not including b!)

        while len(self.buffer) > 0:
            self.debug2("buffer: " + hex(self.buffer))

            # check validity of packet
            while len(self.buffer) > 0 and self.buffer[0] != -1:
                self.warn("wrong sync-start of packet - discarding one byte")
                self.error("halting because of wrong sync-start. buffer: " + hex(self.buffer))
                raise Exception("comms error or device firmware bug. halting.")
                # del self.buffer[0]

            if len(self.buffer) < 3:
                # not enough data received
                return False

            length = self.buffer[2]

            if -1 in self.buffer[1:length + 5]:  # note: python does not throw exceptions if the buffer is not long enough for the range 1 ... length+5, but just returns the longest possible part
                self.warn("packet data contains a sync-start, skipping the start of this malformed (too short?) packet and waiting for next sync")
                del self.buffer[0]
                continue

            if len(self.buffer) < length + 5:
                # not enough data received to parse the whole packet
                return False

            crc = self.buffer[length + 3:length + 4 + 1]
            if ESSPDevice.Helper.crc(self.buffer[1:3 + length - 1 + 1]) != crc:
                self.warn("CRC error - discarding this packet start and waiting for next sync-start")
                # do not delete whole packet from buffer (the length might have been corrupted), but only the first byte (sync-start), wait until the next start
                del self.buffer[0]
                continue

            # valid packet - return the data
            if self.buffer[1] & 0x7F == self.slaveID:
                if bool(self.buffer[1] & 128) != bool(self.seq):
                    self.warn("response has wrong sequence number, discarding it.")
                    data = False
                else:
                    data = ESSPDevice.Response(self.buffer[3:length + 3])
                    self.debug("response: {}".format(data))
            else:
                # the packet was not for us, but for another slave
                data = False
            del self.buffer[0:length + 5]
            return data
        return False

    #
    # High-Level Send/Receive: Command/Response
    #
    class Response:  # status + data
        statusStrings = {
            -1:   "decoded response contains no data",
                        0xF0: "OK",
                        0xF2: "Command not known",
                        0xF3: "Wrong number of parameters",
                        0xF4: "Param out of range",
                        0xF5: "Command cannot be processed at this time, possibly busy or not correctly configured",
                        0xF6: "Software error",
                        0xF8: "Command failure",
                        0xFA: "Encryption key not set",
                        0x7E: "Encrypted Data"
        }

        def __init__(self, data):
            if len(data) == 0:
                # empty response AFTER decoding
                self.status = -1
                self.data = []
            self.status = data[0]
            self.data = copy.copy(data[1:])

        def isOkay(self):
            return self.status == 0xF0

        def isSoftFail(self):
            return self.status == 0xF5

        def isHardFail(self):
            return not(self.isOkay() or self.isSoftFail())

        def isEncrypted(self):
            return self.status == 0x7E

        def statusString(self):
            try:
                return self.statusStrings[self.status]
            except KeyError:
                return "unknown statuscode " + str(self.status)

        def __repr__(self):
            return "<Response: status=" + hex(self.status) + " (" + self.statusString() + "), data=" + hex(self.data) + ">"

        def getData(self):
            return copy.copy(self.data)

        def getDataStream(self):
            return ESSPDevice.ByteStreamReader(self.getData())

        def getStatus(self):
            return self.status()

    def unencryptedCommand(self, data, allowSoftFail=False):
        return self.command(data, allowSoftFail, encrypted=False)

    def command(self, data, allowSoftFail=False, encrypted=True):
        if encrypted:
            self.debug2("encrypting command, original data:" + hex(data))
            data = self.encryptData(data)
            self.debug2("encrypted data:" + hex(data))
        time.sleep(0.25)
        self.flushRead()
        self.send(data)
        for retry_count in [0, 1, 2]:  # 3 tries
            for i in range(20):
                time.sleep(0.01)
                r = self.read()
                if r is not False:
                    break
            if encrypted:
                if r is not False and r.isEncrypted():
                    r = self.decryptResponse(r)
                else:
                    if r is False:
                        self.log("response timeout")
                    else:
                        self.log("unsuccessful response: " + str(r))
            if r is False:
                self.warn("Timeout or CRC/Crypto error -- resend necessary (not fatal, this may happen rarely)")
                self.resendLast()
                continue
            if not r.isOkay():
                self.warn("got response with error status:" + str(r))
                if not (r.isSoftFail() and allowSoftFail):
                    self.error(("Command failed: Cmd " + hex(data) + ", Resp " + str(r)))
                    raise Exception("Command failed: Cmd " + hex(data) + ", Resp " + str(r))
            else:
                self.debug2("got response:" + str(r))
            return r
        self.error("No valid response after 3 retries")
        raise Exception("No reply received")

    #
    # Crypto
    #
    def initCrypto(self, presharedKey):
        # todo use real random primes here ????????? whatever, the whole crypto stuff is rather a marketing gag than a useful security measure, it has no MITM protection
        # and AFAIK SSL also uses fixed generator and modulus
        generator = 0x5a7ccab
        modulus = 0x4c564cf
        assert modulus < generator
        self.unencryptedCommand([0x4A] + ESSPDevice.Helper.Unsigned64ToBytes(generator))  # set generator
        self.unencryptedCommand([0x4B] + ESSPDevice.Helper.Unsigned64ToBytes(modulus))  # set modulus
        # hostRandomNumber=1 # random number
        hostRandomNumber = 0x4e9efc7
        hostTempKey = pow(generator, hostRandomNumber, modulus)  # generator ** hostRandomNumber % modulus
        # assert hostTempKey==0x1d9ecb1
        s = self.unencryptedCommand([0x4C] + ESSPDevice.Helper.Unsigned64ToBytes(hostTempKey)).getDataStream()
        slaveTempKey = s.readUnsigned(numBytes=8, littleEndian=True)
        # SlaveInter=0x10ada5d
        # slaveTempKey=SlaveInter
        s.assertFinished()
        negotiatedKey = pow(slaveTempKey, hostRandomNumber, modulus)  # (slaveTempKey ** hostRandomNumber) % modulus

        key = negotiatedKey * (2 ** 64) + presharedKey
        # convert to byte array
        keyBytearray = ESSPDevice.Helper.UnsignedToBytes(key, n=16)
        # convert to string
        keyString = ESSPDevice.Helper.byteArrayToString(keyBytearray)
        self.crypt = Crypto.Cipher.AES.new(keyString)
        self.encryptionCounter = 0

    def encryptData(self, data):
        d = [len(data)] + ESSPDevice.Helper.Unsigned32ToBytes(self.encryptionCounter) + data
        self.encryptionCounter += 1

        # padding: make the final data length a multiple of 16 bytes
        while not (len(d) + 2) % 16 == 0:
            d.append(Crypto.Random.random.randint(0, 255))

        d += ESSPDevice.Helper.crc(d)

        stream = ESSPDevice.ByteStreamReader(d)

        encryptedData = [0x7E]  # start byte of encrypted transmission
        while stream.hasData():
            dataStr = ESSPDevice.Helper.byteArrayToString(stream.readData(16))
            cryptedStr = self.crypt.encrypt(dataStr)
            encryptedData += ESSPDevice.Helper.stringToByteArray(cryptedStr)

        return encryptedData

    def decryptResponse(self, r):
        try:
            assert r.isEncrypted()  # check start byte 0x7E, it is the response status byte
            assert len(r.data) % 16 == 0, "padding length"
            encryptedStream = r.getDataStream()
            decryptedData = []
            while encryptedStream.hasData():
                dataStr = ESSPDevice.Helper.byteArrayToString(encryptedStream.readData(16))
                decryptedStr = self.crypt.decrypt(dataStr)
                decryptedData += ESSPDevice.Helper.stringToByteArray(decryptedStr)
            self.debug2("parsing decrypted data: " + hex(decryptedData))
            stream = ESSPDevice.ByteStreamReader(decryptedData)
            length = stream.readByte()
            assert length > 0, "nonzero length"
            receivedEncryptionCounter = stream.readUnsigned32(CheckOverrun=False)
            assert self.encryptionCounter == receivedEncryptionCounter, "encryption counter: expected {}, received {}".format(self.encryptionCounter, receivedEncryptionCounter)
            data = stream.readData(length)

            # discard padding
            #
            # len,counter,data,padding,CRC have a total length of n*16
            # 1  +  4    + len +  x   + 2   = n*16
            #
            # => (7 + len) + x - n*16 = 0
            # => x = n*16 - (7*length) so that x >= 0
            stream.readData((- (7 + length)) % 16)

            # CRC on all bytes except the start byte and the CRC itself
            assert stream.readData(2) == ESSPDevice.Helper.crc(decryptedData[0:-2]), "decrypted CRC mismatch"

            stream.assertFinished()

            return ESSPDevice.Response(data)
        except AssertionError:
            self.warn("failed to decrypt response, discarding it. " + traceback.format_exc())
            # self.encryptionCounter-=1
            return False

    #
    # Basic Commands
    #
        # resets the device - ATTENTION, the usb device also detaches after reset, so you need to reopen the port!
    def reset(self):
        r = self.unencryptedCommand([0x01])
        if r != 0x01:
            raise Exception("Reset failed")

    def setEnabled(self, enabled):
        if enabled:
            self.command([0x0A])
        else:
            self.command([0x09])


class NV11Device(ESSPDevice):

    """Interface client for Innovative Technology NV11 banknote validator/changer with eSSP Protocol"""

    def __init__(self, port, presharedKey=0x0123456701234567, slaveID=0):
        ESSPDevice.__init__(self, port, presharedKey, slaveID)

        self.command([0x06, 0x07])  # Host protocol version 7
        self.unitData = self._getUnitData()

        # set Value reporting: Value - if this is changed, a lot of the event decoding will break!
        self.command([0x45, 0x00])  # report by value, not by channel ID

        self.command([0x5C, 0x01])  # enable payout device

        self.setEnabled(False)
        self.setEnabledChannels()

    def __repr__(self):
        return "<NV11>"
    #
    # Commands
    #

    def setEnabledChannels(self, enabledChannels=None, upTo=0):
        # channel numbers are counted from 1 on
        bitmask = 0
        enabledChannels = set(enabledChannels or [])
        for i in range(self.unitData["numChannels"]):
            if self.unitData["real channel value"][i] <= upTo:
                enabledChannels.add(i + 1)
        for c in list(enabledChannels):
            assert c > 0
            assert c <= 16
            bitmask = bitmask | (1 << (c - 1))
        bytesList = ESSPDevice.Helper.splitBytes(bitmask)
        self.command([0x02] + bytesList)
        self.setEnabled(bitmask != 0)

    def getChannelValue(self, channelId, reportedValue=False):
        assert channelId > 0
        assert channelId <= 16
        if reportedValue:
            return self.unitData["reported channel value"][channelId - 1]
        else:
            return self.unitData["real channel value"][channelId - 1]

    def _getUnitData(self):
        """get device setup data -- see ESSP specification"""
        unitData = {}

        # Serial number
        s = self.command([0xC]).getDataStream()
        unitData["serial number"] = s.readUnsigned32BigEndian()  # serial number is big-endian - WTF
        s.assertFinished()

        # Unit data
        s = self.command([0xD]).getDataStream()
        unitData["unit type"] = s.readByte()
        unitData["firmware version"] = s.readAscii(4)
        unitData["country"] = s.readAscii(3)
        unitData["internal value multiplier"] = s.readUnsigned24BigEndian()  # the official documentation example looks like this should be little-endian, but it isn't
        unitData["protocol version"] = s.readByte()
        s.assertFinished()

        # Setup Request
        s = self.command([0x5]).getDataStream()
        assert s.readByte() == 7  # BNV with NoteFloat
        assert s.readAscii(4) == unitData["firmware version"]
        assert s.readAscii(3) == unitData["country"]
        assert unitData["internal value multiplier"] == s.readUnsigned24BigEndian()
        assert unitData["internal value multiplier"] != 0  # assuming old-style dataset - if this fails, see official docs and rewrite

        unitData["numChannels"] = s.readByte()
        assert unitData["numChannels"] in range(1, 17)
        unmultipliedChannelValue = [s.readByte() for n in range(unitData["numChannels"])]
        unitData["channel security (obsolete)"] = [s.readByte() for n in range(unitData["numChannels"])]
        unitData["real value multiplier"] = s.readUnsigned24BigEndian()  # second value multiplier
        assert unitData["internal value multiplier"] != 0

        unitData["reported channel value"] = [x * unitData["internal value multiplier"] for x in unmultipliedChannelValue]
        unitData["real channel value"] = [x * unitData["internal value multiplier"] * unitData["real value multiplier"] for x in unmultipliedChannelValue]

        assert s.readByte() == 7  # current protocol version

        # multi currency datasets are not implemented. assume all country codes are equal
        for i in range(unitData["numChannels"]):
            assert s.readAscii(3) == unitData["country"]
        # full channel value
        for i in range(unitData["numChannels"]):
            assert s.readUnsigned32() == unitData["reported channel value"][i]

        s.assertFinished()
        self.log("Unit data: {0}".format(unitData))
        return unitData

    def setRouteToPayout(self, values):
        """route all notes in the given list of values to the payout-store.
        others will be directly put to the cashbox and are not availble for return.
        """
        for v in values:
            assert v % self.unitData["real value multiplier"] == 0
            assert v / self.unitData["real value multiplier"] in self.unitData["reported channel value"]
        for v in self.unitData["reported channel value"]:
            # set denomination route
            route = 0x01  # default: to cashbox
            if v * self.unitData["real value multiplier"] in values:
                route = 0x00  # route to payout-store
            # docs are unclear: here the real and not the reported value is used!!!!
            self.command([0x3B, route] + ESSPDevice.Helper.Unsigned32ToBytes(v * self.unitData["real value multiplier"]) + ESSPDevice.Helper.AsciiToBytes(self.unitData["country"]))

    def getPayoutValues(self):
        """get values of notes on payout stack.
        The last one of these is on top of the stack and will be paid out by the payout-command.
        """
        s = self.command([0x41]).getDataStream()  # get note positions
        num = s.readByte()
        values = [s.readUnsigned32() for i in range(num)]
        s.assertFinished()
        self.debug("payout values:" + str(values))
        return values

    def tryPayout(self, value):
        l = self.getPayoutValues()
        if len(l) == 0 or l[-1] > value:
            return False
        # payout seems possible
        self.log("trying payout")
        r = self.command([0x42], allowSoftFail=True)  # payout last stored note
        if not r.isOkay():
            self.log("could not payout (busy if data==3, otherwise error):" + str(r))
        return r.isOkay()  # False = could not payout, True = starting payout / waiting for start

    def stackFromPayout(self):
        """
        move the current note from payout store to the cashbox, so that a smaller note that isn't on top of the stack
        can be paid out.
        does not check if this is useful, these checks need to be done at a higher level!
        """
        l = self.getPayoutValues()
        assert len(l) > 0
        self.log("moving note {} from payout-store to cashbox. payout store contents before:{} ".format(l[-1], l))
        self.command([0x43])

    def empty(self):
        self.log("counters:")
        s = self.command([0x58]).getDataStream()
        msg = "Counters: "
        assert s.readByte() == 5  # 5x4bytes
        msg += "{} stacked, ".format(s.readUnsigned32())
        msg += "{} stored, ".format(s.readUnsigned32())
        msg += "{} dispensed, ".format(s.readUnsigned32())
        msg += "{} transferred from store to stacker, ".format(s.readUnsigned32())
        msg += "{} rejected.".format(s.readUnsigned32())
        s.assertFinished()
        self.log(msg)
        self.log("emptying (smart-empty)")
        self.command([0x52])

    def poll(self):
        # TODO properly document return type
        # should we use the POLL_WITH_ACK command?
        # from the docs, it looks better than POLL, but in practice it caused some strange trouble
        USE_POLL_WITH_ACK = False
        if USE_POLL_WITH_ACK:
            resp = self.command([0x56])  # Poll with ACK
        else:
            resp = self.command([0x07])  # Poll (normal, does not need extra ACK)
        fullData = resp.getData()  # copy for logging
        self.debug("event response:" + hex(fullData))
        eventData = resp.getDataStream()  # stream for parsing

        # event importance (log level)
        # error=-1 is not used as long as the communication is okay
        warning = 0  # something bad happened - email the operator!
        log = 1  # interesting, but usual
        debug = 2  # uninteresting noise, only for debugging

        # non-ACK events with no data:
        simpleEvents = {
            # 0xB5: ["all input channels disabled", debug],
                      0xB6: ["booting,  please wait", log],
                      0xC2: ["emptying,  please wait", debug],
                      0xC3: ["emptied", log],
                      0xC6: ["payout device went out of service - (TODO: implement re-enabling by ENABLE PAYOUT DEVICE)", warning],
                      0xC7: ["payout device removed", warning],
                      0xC8: ["payout device attached", log],
                      0xCF: ["payout device full", log],  # TODO official documentation says that this event is 0xC9,  which already has a meaning. WTF
                      0xCC: ["note stacking", debug],
                      0xE3: ["cashbox removed", log],
                      0xE4: ["cashbox reinserted", log],
                      0xE7: ["stacker full", warning],
                      0xE9: ["note jammed, possibly removable by user", warning],
                      0xEA: ["note jammed, safe (not retrievable by user)", warning],
                      0xEB: ["note stacked", debug],
                      0xEC: ["note rejected", debug],
                      0xED: ["rejecting note", debug],
                      0xF1: ["power reset", log],
        }

        # TODO filter out repetitions????
        # TODO email for errors

        # events with 1 byte data (channel or 0=in progress)
        # only for NV9/NV11 validators - needs many changes for other device types!
        eventsWithChannelInfo = {0xE6: ["Fraud attemtpted", True, warning],
                                 0xE1: ["Note rejected to user at powerup", True, warning],
                                 0xE2: ["Note cleared to cashbox at powerup", True, warning],
                                 0xEE: ["Credit note ", True, log]
                                 }

        # events with and without ACK that have a data response like:
        # numItems, [Countrycode, Value], [Countrycode, Value], ...
        eventsWithValueReporting = {  # Code: [name, needsACK, logLevel, meaning], ...
            # meaning: see code below - how should the code handle this event
                                  0xB3: ["emptying (smart-empty), current value ", False, debug, "ignore"],
                                  0xB4: ["emptied (smart-empty)", True, log, "ignore"],
                                  0xCA: ["note cleared to stacker at powerup", True, warning, "LogSingleItem"],
                                  0xCB: ["note cleared to payout-store at powerup", True, warning, "LogSingleItem"],
                                  0xCD: ["note cleared to user (dispensed!) at powerup", True, warning, "LogSingleItem"],
                                  0xCE: ["dispensed note held in bezel", False, log, "LogSingleItem"],
                                  0xD2: ["payout completed", True, log, "EndOfPayout"],
                                  0xD5: ["jammed - needs manual intervention,  currently paid out value:", False, warning, "EndOfPayout"],  # TODO should this really be EndOfPayout ?????
                                  # TODO 0xD5 really EndOfPayout ?????
                                  0xD6: ["payout halted (requested by host),  currently paid out value", False, log, "Unsupported"],
                                  0xD9: ["Timeout: unable to complete payout request. paid out value:", True, warning, "EndOfPayout"],  # TODO should this really be EndOfPayout ?????
                                  0xDA: ["payout is active, currently paid out:", False, debug, "ignore"],
                                  0xDB: ["note stored in payout", False, log, "LogSingleItem"],  # official documentation unclear!
                                  0xDC: ["Payout request before powerup was interrupted. floated value / requested value:", True, warning, "LogTwoValues"],
                                  0xDD: ["Float request before powerup was interrupted. floated value / requested value: ", True, warning, "LogTwoValues"],
                                  0xC9: ["note moved from payout to stacker", True, log, "LogSingleItem"],

        }
        eventNeedsACK = False
        r = {}  # return
        r["acceptActive"] = True
        r["received"] = []
        r["dispensed"] = []
        r["payoutActive"] = False
        r["finished"] = False
        r["stackedFromPayout"] = False
        r["smartEmptyFinished"] = False
        while eventData.hasData():
            ev = eventData.readByte()
            self.debug("event  " + hex(ev))
            if ev in simpleEvents:
                self.printDebug("event " + hex(ev) + ": " + simpleEvents[ev][0], simpleEvents[ev][1])
            elif ev == 0xEF:
                channel = eventData.readByte()
                if channel == 0:
                    self.debug("reading note...")
                else:
                    self.log("note in escrow, channel " + str(channel))
                    # we could also reject the note here, but then we must send Hold/Reject command before ANY  ack is sent out, even if other ACK events are pending!!!
            elif ev == 0xE8:
                self.debug("shutdown")
                r["finished"] = True
            elif ev == 0xB5:
                self.debug("accept-shutdown (all inputs disabled)")
                r["acceptActive"] = False
            elif ev in eventsWithChannelInfo.keys():
                message = eventsWithChannelInfo[ev][0]
                if eventsWithChannelInfo[ev][1]:
                    eventNeedsACK = True
                logSeverity = eventsWithChannelInfo[ev][2]
                channel = eventData.readByte()
                self.printDebug(message + " - channel " + str(channel), logSeverity)
                if ev == 0xEE:  # credit note
                    r["received"] += [self.getChannelValue(channel)]  # TODO we can't easily tell if the note was stacked or put into the cashbox
                    self.setEnabledChannels()  # do not allow further notes before explicit reactivation
                    # self.setEnabled(False)
            elif ev in eventsWithValueReporting.keys():
                message = eventsWithValueReporting[ev][0]
                if eventsWithValueReporting[ev][1]:  # needs ACK
                    eventNeedsACK = True
                logSeverity = eventsWithValueReporting[ev][2]
                meaning = eventsWithValueReporting[ev][3]

                assert meaning in ["EndOfPayout", "Unsupported", "ignore", "LogTwoValues", "LogSingleItem"]
                assert meaning != "Unsupported"

                if ev == 0xDA:
                    # payout in progress
                    r["payoutActive"] = True
                if ev == 0xC9:
                    r["stackedFromPayout"] = True
                if ev == 0xB4:
                    r["smartEmptyFinished"] = True
                if True:  # meaning != "LogSingleItem": TODO
                    # array of (country, value) pairs, first byte is the number of array-items
                    # we don't implement multi-country, so assert there is only one
                    assert eventData.readByte() == 1
                    # for "LogSingleItems" the array length is not transmitted and fixed to 1

                value = eventData.readUnsigned32()  # assuming reporting by value (this is set in init)
                if meaning == "LogTwoValues":
                    # this event has an answer with two values: (value1 value2 country)
                    value = [value,  eventData.readUnsigned32()]
                country = eventData.readAscii(3)
                message += " {0} {1}. ".format(value, country)

                if meaning == "EndOfPayout":
                    self.log(hex(ev) + "end of payout,  dispensed: " + str(value))
                    assert r["dispensed"] == []  # prevent duplicate counting of one pay-out in single poll response - TODO is this okay?
                    assert value > 0  # empty completed payouts are usually reported after communication errors - TODO may this happen?
                    r["dispensed"] += [value]

                self.printDebug(message, logSeverity)
            else:
                remainingData = []
                while eventData.hasData():
                    remainingData.append(eventData.readByte())
                self.error("event decode error: " + hex(fullData) + ", trouble at " + hex(ev) + ", remaining unparsed data:" + hex(remainingData))
                raise Exception("unknown event - probably decode error")
        if eventNeedsACK and USE_POLL_WITH_ACK:
            # when using poll-with-ACK, certain events need to be confirmed via ACK, otherwise they will reappear in the next poll response.
            # because of strange bugs, we have a extra safety delay added here.
            time.sleep(1)
            self.command([0x57])  # event ACK
            time.sleep(1)

        return r
