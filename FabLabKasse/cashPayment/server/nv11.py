#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

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

import time
import logging
import NV11.NV11Device as NV11
from helpers.banknote_stack_helper import BanknoteStackHelper

# Device driver (CashServer) for NV11 banknote acceptor-and-dispenser device.
# config options:
# deviceN_name
# deviceN_port

from cashServer import CashServer


class NV11CashServer(CashServer):

    def initializeDevice(self):
        self.acceptedRest = 999   # how much money may be not paid out at payout? (default: try hard to get 10€ bills, but if a 5€ bill is too far down the stack, just stop paying out)
        self.banknoteStackHelper = BanknoteStackHelper(accepted_rest=self.acceptedRest)
        self.payoutActive = False
        self.stackingFromPayoutActive = False
        self.emptyingActive = False
        port = "/dev/ttyACM0"
        if "port" in self.options:
            port = self.options["port"]
        self.dev = NV11.NV11Device(port=port)
        self.dev.setRouteToPayout([500, 1000, 2000, 5000])
        # WARNING: the NV11 firmware is probably buggy. Because of this this code is very careful and will rather get stuck waiting for an event than wrongly accept or dismiss a banknote.
        #
        # Memory corruption bug when sending payout command while another payout is still active,
        # the device then doesn't send "payout completed 10€", but "payout completed 0€"!
        # this can be reproduced by:
            # Fill the device with 20-30 notes and then send this command
            # print self.dev.getPayoutValues()
            # while True:
            #    self.dev.command([0x42], allowSoftFail=True)
            #    self.dev.poll()

            # example trouble data:
            # preData=[0x01,  0xE8,  0x03,  00,  00]
            # d=[0x7F , 0x80 , 0x15 , 0xF0 , 0xD2 , 0x01 , 0x00 , 0x00 , 0x00 , 0x00 , 0x45 , 0x55 , 0x52 , 0xDA , 0x01 , 0x00 , 0x00 , 0x00 , 0x00 , 0x45 , 0x55 , 0x52 , 0xB5 , 0xE8 , 0xB2 , 0xB8]
            # print ESSPDevice.Response(d[3:-2])
            # print hex(ESSPDevice.Helper.crc(d[1:-2]))
            # import sys
            # sys.exit(0)

        self.dev.setEnabledChannels()
        self.dev.log("startup,  checking if idle")
        startupCounter = 10
        while startupCounter > 0:
            startupCounter -= 1
            val = self.dev.poll()
            if val != {'payoutActive': False, 'received': [], 'smartEmptyFinished': False, 'stackedFromPayout': False, 'dispensed': [], 'finished': True, 'acceptActive': False}:
                self.dev.warn("not idle at startup poll: " + str(val))
                startupCounter = 10
            time.sleep(0.3)
        self.dev.log("startup finished")

    def getCanPayout(self):
        return [self.banknoteStackHelper.can_payout(self.dev.getPayoutValues()), self.acceptedRest]

    def getCanAccept(self):
        return True

    def doEmpty(self):
        self.dev.empty()
        self.emptyingActive = True

    def pollAndUpdateStatus(self):
        if self.moneyReceiveAllowed > 0:
            assert not self.payoutActive
            assert not self.stackingFromPayoutActive
            assert not self.emptyingActive

        if self.emptyingActive:
            assert not self.moneyDispenseAllowed > 0
            assert not self.moneyReceiveAllowed > 0

        self.dev.setEnabledChannels(upTo=self.moneyReceiveAllowed - self.moneyReceivedTotal)

        # poll device and react to response
        val = self.dev.poll()

        for receivedNote in val['received']:
            self.event_receivedMoney(1, receivedNote, "main", "received")
        for dispensedNote in val['dispensed']:
            self.event_dispensedMoney(1, dispensedNote, "main", "dispense")

        # do various safety checks, update self.*Active variables that mirror the device's state
        # the code is extremely careful because we can't trust the device firmware 100%
        if val['payoutActive']:
            assert self.currentMode == "dispense"
            assert self.payoutActive
        if val['received'] != []:
            assert self.currentMode == "accept" or self.currentMode.startswith("stopping")
        if val['dispensed'] != []:
            assert self.currentMode == "dispense"
            assert self.payoutActive
            self.payoutActive = False
        if val['stackedFromPayout']:
            assert self.currentMode == "dispense"
            assert self.stackingFromPayoutActive
            self.stackingFromPayoutActive = False
        if val['smartEmptyFinished']:
            assert self.emptyingActive
            assert self.currentMode == "empty" or self.currentMode.startswith("stopping")
            self.emptyingActive = False

        payInOutBusy = (not val['finished']) or self.payoutActive or self.stackingFromPayoutActive or val['received'] != [] or val['dispensed'] != []
        self.busy = payInOutBusy or self.emptyingActive
        assert not (payInOutBusy and self.emptyingActive), "it is impossible to be emptying while payin/out is active"

        # pay out the next banknote, if ...
        if (self.currentMode == "dispense"  # we are currently paying out,
                and not self.payoutActive and val['dispensed'] == []  # previous payout operations have finished
                and not self.stackingFromPayoutActive):  # and the device isn't busy stacking away a banknote

            action = self.banknoteStackHelper.get_next_payout_action(self.dev.getPayoutValues(),  self.moneyDispenseAllowed - self.moneyDispensedTotal)
            if action == "payout":
                assert self.dev.tryPayout(self.moneyDispenseAllowed - self.moneyDispensedTotal) is True
                self.payoutActive = True
            elif action == "stack":
                self.dev.stackFromPayout()
                self.stackingFromPayoutActive = True
            elif action == "stop":
                logging.info("cannot payout any more. paid out: {}, requested: {}\n".format(self.moneyDispensedTotal, self.moneyDispenseAllowed))
                self.currentMode = "stopping"
            else:
                raise AssertionError("impossible return value")
        logging.debug(str([self.currentMode, val, self.payoutActive, self.stackingFromPayoutActive, self.moneyReceiveAllowed, self.moneyReceivedTotal, self.moneyDispenseAllowed, self.moneyDispensedTotal]) + "\n")

    def getSleepTime(self):
        return 0.5  # don't make this lower.
                    # polling too fast is bad, it causes strange responses!

if __name__ == "__main__":
    e = NV11CashServer()
    e.run()
