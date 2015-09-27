#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# connection to MDB interface hardware, which is connected to a MDB cash changer

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


import random
import time
import serial
import logging
import re


class BusError(Exception):
    pass


class InterfaceHardwareError(Exception):
    pass


class MissingResetEventError(Exception):
    pass


class MdbCashDevice:
    # changer commands - subtracting 8 from the (wrong) values in the specification
    CMD_RESET = 0x08 - 8
    CMD_TUBE_STATUS = 0x0A - 8
    CMD_POLL = 0x0B - 8
    CMD_SETUP = 0x09 - 8
    CMD_COIN_TYPE = 0x0C - 8
    CMD_DISPENSE = 0x0D - 8
    CMD_EXPANSION = 0x0F - 8

    NAK = 0xFF
    ACK = 0x00
    RET = 0xAA

    IGNORE = "ignore"
    WARNING = "warning"
    BUSY = "busy"
    ERROR = "error"
    JUST_RESET = "just reset"
    statusEvents = {
        0b0001: ["Escrow request", IGNORE],
                0b0010: ["Payout Busy", BUSY],
                0b0011: ["valid coin did not get to the place where credit is given", WARNING],
                0b0100: ["Defective Tube Sensor", WARNING],
                0b0101: ["Double Arrival", IGNORE],
                0b0110: ["Acceptor unplugged", ERROR],
                0b0111: ["Tube jam", WARNING],
                0b1000: ["ROM checksum error", ERROR],
                0b1001: ["coin routing error", ERROR],
                0b1010: ["Busy", BUSY],
                0b1011: ["Was just reset", JUST_RESET],
                0b1100: ["Coin jam", WARNING],
                0b1101: ["Possible credited coin removal", WARNING]
    }

    def __init__(self, port, addr=0b00001, extensionConfig=None):
        """
        :param extensionConfig: settings for extension commands (by the interface hardware, not on the MDB bus). dictionary.
        :param extensionConfig["hopper"]: Set to False to only use MDB. Set to a coin value to enable an external non-MDB hopper (like Compact Hopper SBB) with the given coin value (e.g. 200 for 2.00€). Currently this hopper is always used first for payout, so it should be filled with the highest possible coin value.
        :param extensionConfig["leds"]: True to enable RGB-LEDs for payin/payout via extension command
        """
        if not extensionConfig:
            extensionConfig = {"hopper": False,  "leds": False}
        self.ser = serial.serial_for_url(port, 38400, timeout=0.2)
        assert 0 <= addr < 2 ** 5
        self.addr = addr
        self.buffer = ""
        self.extensionConfig = extensionConfig

        assert self.extensionConfig.get("hopper", False) in [False] + range(1, 9999),  "invalid extensionConfig for hopper"

        self.reset()

    # =======================
    # debug functions
    # =======================
    def __repr__(self):
        return "<MDB>"

    def printDebug(self, s, debugLevel):
        logLevels = {-1: logging.ERROR,  0: logging.WARNING,  1: logging.INFO, 2: logging.DEBUG,  3: logging.DEBUG - 1}
        logging.getLogger(self.__repr__()).log(logLevels[debugLevel], s)

    def error(self, s):
        self.printDebug(s, -1)

    def log(self, s):
        self.printDebug(s, 1)

    def warn(self, s):
        self.printDebug(s, 0)

    # =======================
    # Low-Level Send/Receive
    # =======================

    # clear all read buffers
    def flushRead(self):
        while self.ser.inWaiting() > 0:
            self.warn("flushing serial read buffer")
            self.ser.read(self.ser.inWaiting())
        if len(self.buffer) > 0:
            self.warn("flushing input buffer")
            self.buffer = ""

    def serialCmd(self, text):
        logging.debug("serial send: '{}'".format(text))
        self.ser.write(text + "\n")

    # get data from serial port
    # return values:
    #   None: No answer from interface hardware received.

    # raises:
    #   BusError: the bus device failed to respond, it is guaranteed that no ACK has been sent. Please resend.
    #   InterfaceHardwareError: the interface hardware did not respond properly, a packet might have been lost between interface and PC!
    #                            Do not attempt to resend, because the lost reply could have been ACKed by the interface!
    def read(self):
        bytesToRead = self.ser.inWaiting()
        # logging.debug(bytesToRead)
        if bytesToRead > 0:
            self.buffer += self.ser.read(bytesToRead)
        else:
            pass
            # logging.debug("not read:" + self.ser.read())
        if len(self.buffer) > 0:
            logging.debug("buffer: {}".format(self.buffer.__repr__()))
        if not ("\n" in self.buffer):
            # we have not yet received a full response
            return None
        if not self.buffer.endswith("\n"):
            self.warn("received more than one response - flushing buffer. ignore next warnings. buffer:" + self.buffer.__repr__())
            self.buffer = ""
            raise InterfaceHardwareError("received more than one response")
        if self.buffer == "RT\n":
            self.log("bus timeout")
            self.buffer = ""
            raise BusError("bus timeout")
        if self.buffer == "RN\n":
            self.log("bus NAK")
            self.buffer = ""
            raise BusError("bus NAK")
        if self.buffer == "RE\n":
            self.log("bus error")
            self.buffer = ""
            raise BusError("bus error")
        if not self.buffer.startswith("R:"):
            self.warn("response has wrong start,  skipping data. ignore next warnings. buffer:" + self.buffer.__repr__())
            self.buffer = ""
            raise InterfaceHardwareError("response has wrong start")
        # everything is okay, return data
        ret = self.buffer[2:]
        self.buffer = ""
        return ret

    # =======================
    # High-Level Send/Receive
    # =======================

    def checksum(self, data):
        sum = 0
        for byte in data:
            sum += byte
        return sum % 256

    # raises BusError or InterfaceHardwareError, see send()
    # returns valid data
    def cmd(self, command, data=None):
        if data == None:
            data = []
        assert 0 <= command < 8
        bytes = [self.addr << 3 | command] + data
        bytes.append(self.checksum(bytes))
        send = ""
        resp = None
        for b in bytes:
            send += "{:02X}".format(b)
        for _ in range(3):
            try:
                self.serialCmd(send)
                for _ in range(30):
                    # timeout for interface board: 1sec
                    time.sleep(0.1)
                    resp = self.read()  # possibly raises BusError (will be caught below) or InterfaceHardwareError (will not be caught)
                    if resp != None:
                        resp = resp.strip()
                        logging.debug("resp: " + resp.__repr__())
                        break
                if resp == None:
                    raise InterfaceHardwareError("interface timeout")
                else:
                    break
            except (BusError):
                # BusError is not dramatic, just resend
                logging.debug("bus error,  resending")
                time.sleep(1)
                continue
        if resp == None:
            raise BusError("no successful response after 3 retries")
        responseData = []
        # convert response (hex-string) to a byte array
        for i in range(len(resp) / 2):
            try:
                responseData.append(int(resp[2 * i:2 * i + 2], 16))
            except ValueError:
                raise InterfaceHardwareError("cannot parse hex response")
        if len(responseData) > 1:
            if sum(responseData[:-1]) % 256 != responseData[-1]:
                raise InterfaceHardwareError("checksum mismatch")  # interface checks the checksum itself, so we are in big trouble!
            del responseData[-1]  # discard checksum
        logging.debug("respData: " + responseData.__repr__())
        assert responseData != [MdbCashDevice.NAK]  # NAK will already be caught in read()
        return responseData

    def extensionCmd(self, data):
        """in addition to the MDB commands, the interface hardware provides extension commands for other
        features (LEDs, hopper, ...). Failure on these commands is not tolerated.
        """
        self.serialCmd("X" + data)
        for _ in range(30):
            # timeout for interface board: 1sec
            time.sleep(0.1)
            resp = self.read()  # possibly raises BusError or InterfaceHardwareError (both will not be caught)
            if resp != None:
                resp = resp.strip()
                logging.debug("resp: " + resp.__repr__())
                return resp
        raise InterfaceHardwareError("interface timeout")

    # =======================
    # High-Level Commands
    # =======================

    def reset(self):
        for i in range(20):
            time.sleep(1)
            self.flushRead()
            try:
                if self.cmd(MdbCashDevice.CMD_RESET) == [MdbCashDevice.ACK]:
                    # device responded to reset: discard first poll
                    time.sleep(0.5)
                    self.poll(wasJustReset=True)
                    self.getSetup()
                    self.getTubeStatus()
                    self.setAcceptCoins(False, manualDispenseEnabled=False)
                    return
            except (InterfaceHardwareError, BusError, MissingResetEventError),  e:
                logging.debug("reset failed with exception: " + e.__repr__())
                continue
        raise Exception("Device did not respond to reset attempts for 10 seconds")

    def getSetup(self):
        d = self.cmd(MdbCashDevice.CMD_SETUP)
        assert 8 <= len(d) <= 23
        assert d[0] in [2, 3]
        # d[1,2] country code
        coinScalingFactor = d[3]
        # decimal places d[4]
        # coin routing d[5,6]
        self.coinValues = []
        # unsent value-bytes are zero
        while len(d) < 23:
            d.append(0)
        for byte in d[7:23]:
            if byte == 0xFF:
                value = 0  # vending token, ignored
            else:
                value = byte * coinScalingFactor
            self.coinValues.append(value)
        logging.debug("coin values: {}".format(self.coinValues))

    def getValue(self, type):
        return self.coinValues[type]

    def poll(self, wasJustReset=False):
        """ get events from device.
        :param wasJustReset: set this to True at the first poll after the RESET command
        """
        receivedResetEvent = False

        def getBits(byte, lowest, highest):  # cut out bits lowest...highest (including highest) from byte
            # example: getBits(0b0110,2,3)=0b11
            mask = 0
            for bit in range(lowest, highest + 1):
                mask |= (1 << bit)
            return (byte & mask) >> lowest

        data = self.cmd(MdbCashDevice.CMD_POLL)
        if data == []:
            return False
        assert len(data) <= 16
        status = {"manuallyDispensed": [], "accepted": [], "busy": False}
        if data == [MdbCashDevice.ACK]:
            return status
        while len(data) > 0:
            # parse status response
            if data[0] & 1 << 7:
                # coin dispensed because of MANUAL! REQUEST (by pressing the button at the changer device itself)
                assert len(data) >= 2
                dispensedType = getBits(data[0], 0, 3)
                dispensedNumber = getBits(data[0], 4, 6)
                status["manuallyDispensed"] += [{"count": dispensedNumber,  "denomination": self.getValue(dispensedType), "storage": "tube{}".format(dispensedType)}]
                del data[0:2]
                # remaining in tube: data[1]
            else:
                if data[0] & 1 << 6:
                    assert len(data) >= 2
                    acceptedType = getBits(data[0], 0, 3)
                    # unused:
                    acceptedRouting = getBits(data[0], 4, 5)
                    assert acceptedRouting != 2  # this value isnt allowed
                    # coins now in tube: data[1]
                    if acceptedRouting != 3:  # 3 == Reject, not accepted!
                        if acceptedRouting == 0:
                            storage = "cashbox"
                        else:
                            storage = "tube{}".format(acceptedType)
                        status["accepted"] += [{"count": 1,  "denomination": self.getValue(acceptedType), "storage": storage}]
                    del data[0:2]
                else:
                    if data[0] & 1 << 5:
                        # "slug" = counterfeit coin - ignore
                        del data[0]
                    else:
                        # status events
                        assert data[0] in MdbCashDevice.statusEvents
                        [description, severity] = MdbCashDevice.statusEvents[data[0]]
                        if severity == MdbCashDevice.JUST_RESET:
                            receivedResetEvent = True
                            if wasJustReset:
                                logging.debug("received JUST RESET event after reset.")
                            else:
                                raise Exception("received unexpected JUST RESET event")
                        elif severity == MdbCashDevice.WARNING:
                            logging.warning(description)
                        elif severity == MdbCashDevice.ERROR:
                            raise Exception(description)
                        elif severity == MdbCashDevice.BUSY:
                            status["busy"] = True
                            # BUG: if the payout-stack is removed and reattached, the device may send BUSY even while we are not doing payout/payin.
                            # by design, we shouldn't just ignore it because this would remove protections against accidental state mismatches between device and this code
                            logging.debug("received event: {}. If this happens shortly before an error, read the following explanation: If at this moment a service operator was doing something with the device (the payout unit was removed or the device menu was used), then it is a known bug which can be ignored. Otherwise it probably has happened because of a state mismatch between this driver and the device, then it is a severe problem. To be safe, CashServer will halt with an exception.".format(description))
                        elif severity == MdbCashDevice.IGNORE:
                            pass
                        else:
                            raise Exception("unknown severity. ups.")
                        del data[0]
        if wasJustReset and not receivedResetEvent:
            raise MissingResetEventError("did not receive JUST_RESET response at first poll")
        return status

    def setAcceptCoins(self, acceptCoins, manualDispenseEnabled=False):
        # simplified: always accept either all values or no value
        map = {True: [0xFF, 0xFF],  False: [0x00, 0x00]}
        d = []
        d += map[acceptCoins]
        d += map[manualDispenseEnabled]
        # logging.warning("debug")
#        d=[0xFF, 0xFF, 0xFF, 0xFF]
        assert self.cmd(MdbCashDevice.CMD_COIN_TYPE,  d) == [MdbCashDevice.ACK]

    def getTubeStatus(self):
        d = self.cmd(MdbCashDevice.CMD_TUBE_STATUS)
        assert 2 <= len(d) <= 18
        tubeStatus = d[0] << 8 + d[1]
        status = [{} for i in range(16)]
        for i in range(16):
            status[i]["okay"] = True
            status[i]["full"] = (tubeStatus & i) > 0
            if len(d) > 2 + i:
                status[i]["count"] = d[2 + i]
            else:
                # 0 count bytes at the end of the packet are not sent
                status[i]["count"] = 0
            status[i]["okay"] = not (status[i]["count"] == 0 and status[i]["full"])  # count 0 and full means "defective"
            if not status[i]["okay"]:
                self.warn("tube {} defective".format(i))
        return status

    # dispense coin - may only be called if poll() returns busy==False
    # may only be called if enough coins are availavle!
    def dispenseCoin(self, type, amount):
        assert 0 <= type <= 15
        assert 0 < amount <= 15
        self.log("dispensing {}x value {} (coin type {})".format(amount, self.coinValues[type], type))
        assert self.cmd(MdbCashDevice.CMD_DISPENSE, [type | amount << 4]) == [MdbCashDevice.ACK]

    def tryDispenseCoinFromExternalHopper(self):
        """dispense a coin from an external non-MDB hopper connected directly to the interface board.
        :returns: False if it failed (or no external hopper is enabled), True if one coin was dispensed
        """
        if not self.extensionConfig.get("hopper", False):
            logging.debug("skipping external hopper,  disabled")
            return False
        #==============================================================================
        # hopper protocol, copied from kassenautomat.mdb-interface/main.c:
        #
        # Hopper Protocol:
        #
        # command: H
        #
        # response:
        # A  = ACK: command received, starting a dispense operation, please resend to poll for the result
        #  B = busy, please resend command until you receive something else than busy (must not take more than 3 seconds)
        # E01  = out of service because of a serious error #01.
        #         01 is the hexadecimal error number from hopperErrorEnum in task_hopper.h
        #         Please reset board to exit this state, otherwise all hopper requests will be ignored and answered with this error.
        #  RD = okay, dispensed a coin
        #  RE = okay, hopper is empty, could not dispense a coin
        #==============================================================================
        self.log("trying to dispense from hopper")
        response = self.extensionCmd("H")
        assert response == "A", "Did not receive ACK on first dispense request, but {}. Lost reply from a previous command?".format(response)
        poll_tries = 20
        for _ in range(poll_tries):
            response = self.extensionCmd("H")
            if response == "B":
                # received BUSY answer
                logging.debug("hopper busy, polling again...")
                time.sleep(0.3)
                continue
            else:
                break
        logging.info("response: {}".format(response))
        if response == "B":
            raise Exception("Hopper still busy after 6 seconds")
        elif response == "RD":
            logging.info("dispensed coin from hopper")
            return True
        elif response == "RE":
            logging.info("hopper empty")
            return False
        elif response.startswith("E"):
            errors = {"E00": "HOPPER_OKAY",
                      "E01": "HOPPER_ERR_SENSOR1",
                      "E02": "HOPPER_ERR_SENSOR2",
                      "E03": "HOPPER_ERR_SHORT_COIN_IMPULSE",
                      "E04": "HOPPER_ERR_UNEXPECTED_COIN",
                      "E05": "HOPPER_ERR_EARLY_COIN",
                      "E06": "HOPPER_ERR_UNEXPECTED_COIN_AT_COOLDOWN"}
            errorText = errors.get(response, "unknown error")
            logging.warn("hopper is disabled because of hardware error {} - {}. poweroff interface board to re-enable.".format(response, errorText))
            return False
        else:
            raise BusError("received unknown response {}.".format(response))

    def setLEDs(self, leds):
        """ set RGB-LED color via extension command, if it is enabled in the extensionConfig.
        :param leds: list of two LED color values.
        color value: RR GG BB in hex plus a mode of N (normal) or special modes B (blink) or T (timeout: switch off after 20 sec)
        e.g. "00FF00N" = green normal, "FF0000B" = red blink, "0000FFT" = blue with timeout (will switch off after 20sec or the next command)
        """
        if not self.extensionConfig.get("leds", False):
            return
        assert isinstance(leds, list)
        assert len(leds) == 2
        for led in leds:
            assert re.match(r"^[0-9A-F]{6}[BTN]$", led), "invalid LED value"
        assert self.extensionCmd("L{}{}".format(leds[0], leds[1])) == "OK",  "LED command failed"

    # =======================
    # higher level functions
    # =======================

    # return a list of [coinType, value] sorted by descending value, ignoring 0-value coins
    def getSortedCoinValues(self):
        v = []
        for i in range(16):
            if self.coinValues[i] == 0:
                continue
            v.append([i, self.coinValues[i]])

        def cmpItem(x, y):
            return cmp(x[1], y[1])
        v.sort(cmp=cmpItem, reverse=True)
        return v

    def getPossiblePayout(self):
        v = self.getSortedCoinValues()
        t = self.getTubeStatus()
        logging.debug("coinValues: {}".format(v))
        logging.debug("tubeStatus: {}".format(t))
        return self._getPossiblePayout(v, t)

    @staticmethod
    def _getPossiblePayout(v, t):
        totalAmount = 0
        previousCoinValue = None
        # go through the coins from large to small
        for [index, value] in v:
            n = t[index]["count"]
            if previousCoinValue != None and n * value < previousCoinValue:
                # we dont have enough of this coin to "split" one previous coin
                continue
            if previousCoinValue == None:
                previousCoinValue = 0
            totalAmount += n * value - previousCoinValue
            previousCoinValue = value

        if previousCoinValue == None:
            return [0, 0]

        return [totalAmount, previousCoinValue]

    @staticmethod
    def _unittest_getPossiblePayout():
        def randFactor():  # 0 or 1 or something inbetween
            r = random.random() * 1.2 - 0.1
            if r < 0:
                r = 0
            if r > 1:
                r = 1
            return r

        def myRandInt(n):  # 0 ... n, with a finite >0 probability for both endpoints
            return int(randFactor() * n)

        n = myRandInt(5)
        v = []
        t = []
        values = [1, 2, 5, 10, 20, 50, 100, 200]
        for i in range(n):
            v.append([i, values[myRandInt(len(values) - 1)]])
            t.append({"count": myRandInt(20) + 1})

        def cmpItem(x, y):
            return cmp(x[1], y[1])
        v.sort(cmp=cmpItem, reverse=True)

        [canPay, remainingAllowed] = MdbCashDevice._getPossiblePayout(v, t)

        pay = 0
        shouldPay = myRandInt(canPay)
        coinsRemaining = [x["count"] + myRandInt(2) for x in t]

        def hasCoins(c):
            for x in c:
                if x > 0:
                    return True
            return False
        while hasCoins(coinsRemaining):
            couldPay = False
            for [id, value] in v:
                if coinsRemaining[id] > 0 and value <= (shouldPay - pay):
                    coinsRemaining[id] -= 1
                    pay += value
                    couldPay = True
                    break
            if not couldPay:
                break
        assert shouldPay - remainingAllowed <= pay <= shouldPay

    # dispense one coin type for the given value - may only be called if poll() returns busy==False
    # returns: dictionary with count, denomination, storage (tubeXX)
    # or: False if nothing could be dispensed
    # if not False, call again with the remaining value as soon as the device is not busy anymore

    def dispenseValue(self, maximumDispense):
        assert isinstance(maximumDispense, int)

        # first try to dispense from external hopper
        hopperCoinValue = self.extensionConfig.get("hopper", False)
        if hopperCoinValue is not False and 0 < hopperCoinValue <= maximumDispense:
            if self.tryDispenseCoinFromExternalHopper():
                return {"count": 1, "denomination": hopperCoinValue, "storage": "hopper"}

        # it did not work, now use MDB bus
        tubeStatus = self.getTubeStatus()
        sortedCoinValues = self.getSortedCoinValues()

        # get number of avail. coins by value
        coinsAvailable = {}
        for [coinType, coinValue] in sortedCoinValues:
            if not coinsAvailable.has_key(coinValue):
                coinsAvailable[coinValue] = 0
            coinsAvailable[coinValue] += tubeStatus[coinType]["count"]

        def shouldSplit(coinValue):
            """determine if the payout of 1* coin X should be split into 2 pieces of (X/2)
            so that the coin storage does not run short of often paid out coins (like 1€)
            this will only happen if more than enough of the smaller coins (like 50c) are present
            """
            if not coinsAvailable.has_key(coinValue / 2):
                # there is no "half" coin of the currently used value
                # TODO implement something for splitting 50c -> 20c+10c
                return False
            if coinsAvailable[coinValue / 2] < 20:
                # too few of the smaller coins
                return False
            # only split if there are more smaller coins available
            return coinsAvailable[coinValue / 2] > coinsAvailable[coinValue] + 5

        for [coinType, coinValue] in sortedCoinValues:
            # how many coins should be dispensed? maximum 15 at once
            assert isinstance(coinValue, int)
            number = maximumDispense / coinValue  # integer division, implies truncation
            numberAvailable = tubeStatus[coinType]["count"]
            if number > numberAvailable:
                number = numberAvailable
            if number == 0:
                continue
            if number == 1 and shouldSplit(coinValue):
                logging.debug("splitting payout of 1x {} into 2x smaller coin".format(coinValue))
                continue
            if number > 15:
                number = 15
            self.dispenseCoin(coinType, number)
            dispensed = coinValue * number
            assert dispensed <= maximumDispense
            return {"count": number, "denomination": coinValue, "storage": "tube{}".format(coinType)}
        return False

if __name__ == "__main__":
    print "running unittest,  should take some minutes"
    for _ in xrange(300000):
        MdbCashDevice._unittest_getPossiblePayout()
    print "ok"
