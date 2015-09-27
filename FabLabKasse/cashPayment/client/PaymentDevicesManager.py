#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# combine multiple physical payment devices (coin/banknote pay-in and pay-out)
# into one logical device

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
import unittest
from PaymentDeviceClient import PaymentDeviceClient
import logging
import time
from ConfigParser import NoOptionError

# for unittest
from ConfigParser import ConfigParser
import codecs

class PaymentDevicesManager(object):

    def __init__(self, cfg):
        self.devices = []
        self._reset()
        if cfg.get("payup_methods", "cash") == "on":
            for n in range(1, 999):
                prefix = "device" + str(n) + "_"
                try:
                    cmd = cfg.get("cash_payment", "device" + str(n))
                except NoOptionError:
                    break
                options = {}
                for (key, value) in cfg.items("cash_payment"):
                    if not key.startswith(prefix):
                        continue
                    # remove prefix
                    key = key[len(prefix):]
                    options[key] = value
                self.devices.append(PaymentDeviceClient(cmd, options))
        logging.info("cashPayment started with {} devices".format(len(self.devices)))
        self.mode = "start"

    def _reset(self):
        self.requestedPayin = None
        self.maximumPayin = None
        self.requestedPayout = None
        self.payoutDeviceNumber = None
        self.payoutDeviceDispensing = False
        self.finishedAmount = 0

    def poll(self):
        """
        call repeatedly to update status

        :rtype: None
        """
        for d in self.devices:
            try:
                d.poll()
            except Exception:
                logging.error("device {} failed - see cash-{}.log. If it crashed before writing the logfile, try launching the server yourself with the commandline from gui.log ".format(d, d.options['name']))
                raise
        if self.mode == "idle":
            pass
        elif self.mode == "start":
            # query if device can accept
            if None in [d.canAccept() for d in self.devices]:
                pass  # still busy waiting for answer
            else:
                self.mode = "idle"
        elif self.mode == "canPayout":
            for i in range(len(self.devices)):
                if self.canPayoutAmounts[i] == None:
                    # no valid reply received yet
                    self.canPayoutAmounts[i] = self.devices[i].possibleDispense()
        elif self.mode == "payin":
            if self.getCurrentAmount() >= self.requestedPayin:
                self.abortPayin()
            else:
                self._updatePayinAmounts()
        elif self.mode == "payinStop":
            if False in [d.hasStopped() for d in self.devices]:
                pass  # waiting for devices to finish
            else:
                for d in self.devices:
                    final = d.getFinalAmountAndReset()
                    assert final >= 0
                    self.finishedAmount += final
                logging.info("cash accept finished: total {}".format(self.finishedAmount))
                self.mode = "stopped"
        elif self.mode == "payout":
            # sequential:
            # per client: dispense, wait until finished, get final amount
            d = self.devices[self.payoutDeviceNumber]
            if not self.payoutDeviceDispensing:
                # self.finishedAmount is negative!
                dispenseAmount = self.requestedPayout + self.finishedAmount
                logging.info("trying to pay out {} on device {}".format(dispenseAmount, self.payoutDeviceNumber))
                d.dispense(dispenseAmount)
                self.payoutDeviceDispensing = True
            else:
                if d.hasStopped():
                    final = d.getFinalAmountAndReset()
                    assert final <= 0
                    self.finishedAmount += final
                    # go on to next device
                    self.payoutDeviceNumber += 1
                    self.payoutDeviceDispensing = False
                    if self.payoutDeviceNumber == len(self.devices):
                        # all devices are finished
                        logging.info("cash payout finished: total {}".format(self.finishedAmount))
                        self.mode = "stopped"
        elif self.mode == "empty":
            pass  # just poll and wait for stop command
        elif self.mode == "emptyingStop":
            if False in [d.hasStopped() for d in self.devices]:
                pass  # waiting for devices to finish
            else:
                for d in self.devices:
                    final = d.getFinalAmountAndReset()
                    assert final <= 0
                    self.finishedAmount += final
                self.mode = "stopped"
        elif self.mode == "stopped":
            pass  # do nothing
        else:
            raise Exception("unknown mode")

    def canPayout(self):
        """
        returns values [totalMaximumRequest, totalRemaining]:

        every requested amount <= totalMaximumRequest can be paid out, with an unpaid rest <= totalRemaining
        (the return value is only a conservative estimate, not the theoretical optimum)

        Please warn the user if totalMaximumRequest is too low for the possible change

        if this function returns None, the value is still being fetched.
        In this case, sleep some time, then call poll() and then call the function again.
        """
        if self.mode == "idle":
            # fill canPayoutAmounts with "None" values
            self.canPayoutAmounts = [None for _ in self.devices]
            self.mode = "canPayout"
            return None
        if self.mode == "canPayout":
            # commands already sent
            if not None in self.canPayoutAmounts:
                # all devices sent replies
                canPayoutAmounts = self.canPayoutAmounts
                self.canPayoutAmounts = None  # invalidate cache
                self.mode = "idle"
                return self._canPayout_total(canPayoutAmounts)
            else:
                # still waiting for some replies
                return None
        else:
            raise Exception("canPayout() is not possible when busy")

    def _canPayout_total(self, canPayoutAmounts):
        """
        find values totalMaximumRequest (as high as possible) and totalRemaining (as low as possible) so that:
        every requested amount <= totalMaximumRequest can be paid out, with an unpaid rest <= totalRemaining

        canPayoutAmounts=[[maximumRequest, remaining], ...] values for the individual payment devices

        the return value is only a conservative estimate, not the theoretical optimum

        :return: [totalMaximumRequest, totalRemaining]
        """

        if len(canPayoutAmounts) == 0:
            return [0, 0]
        [totalMaximumRequest, totalRemaining] = canPayoutAmounts[0]
        for [maximumRequest, remainingAmount] in canPayoutAmounts[1:]:
            if remainingAmount >= maximumRequest:
                # cannot dispense (empty)
                continue
            if remainingAmount <= totalRemaining:
                # this device has a finer resolution, i.e. smaller coins
                if maximumRequest >= totalRemaining:
                    # and we may request the whole remaining amount

                    # example: previous device: max 200€ with 9,99€ rest
                    #              this device: max  n € with 0,50€ rest
                    #   n=10: okay,   n=2: not okay

                    # if the device has more than the previously remaining amount, we can payout even more than the previous maximum
                    totalMaximumRequest += maximumRequest - totalRemaining
                    totalRemaining = remainingAmount

                    # example: we now can pay >= (200 + n - 9,99)  with 0,50 rest

                    assert remainingAmount <= maximumRequest

            else:
                # APPROXIMATION: assume zero payout
                pass
        return [totalMaximumRequest, totalRemaining]

    def payin(self, requested, maximum):
        assert self.mode == "idle"
        self.requestedPayin = requested
        self.maximumPayin = maximum
        for d in self.devices:
            d.accept(self.maximumPayin)
            d.poll()

        self.mode = "payin"

    def _updatePayinAmounts(self):
        """
        while accept is running:

        if cash is inserted into one device, lower the allowed maximum of all other devices

        (use case: there is a banknote accepting device and a separate coin
        accepting device. If the user may pay in 100€ maximum and has already
        inserted lots of coins, he may no longer use a 100€ banknote.)
        """
        for d in self.devices:
            maximum = self.maximumPayin - self.getCurrentAmount()
            if d.getCurrentAmount() != None:
                maximum += d.getCurrentAmount()
            d.updateAcceptValue(maximum)

    def getCurrentAmount(self):
        """
        get intermediate amount, how much was paid in or out
        """
        totalSum = self.finishedAmount
        for d in self.devices:
            if d.getCurrentAmount() != None:
                totalSum += d.getCurrentAmount()
        return totalSum

    def empty(self):
        """
        start service-empty mode

        see PaymentDeviceClient.empty

        :rtype: None
        """
        assert self.mode == "idle"
        self.mode = "empty"
        for d in self.devices:
            d.empty()
            d.poll()

    def stopEmptying(self):
        """
        exit service-empty mode

        use getFinalAmount() afterwards

        :rtype: None
        """
        assert self.mode == "empty"
        self.mode = "emptyingStop"
        for d in self.devices:
            d.stopEmptying()

    def statusText(self):
        def formatCent(x):
            return u"{:.2f}\u2009€".format(float(x) / 100).replace(".", ",")
        totalSum = self.getCurrentAmount()
        if self.mode.startswith("payout"):
            totalSum = -totalSum
        modes = {"payin": "Bitte bezahlen",
                 "payinStop": "Bezahlung wird abgeschlossen...",
                 "stopped": "Bitte warten, Daten werden gespeichert",
                 "idle": "Bereit",
                 "payout": u"Zahle Rückgeld...",
                 "start": "Bitte warten, initialisiere...",
                 "canPayout": u"Bitte warten, prüfe Wechselgeldvorrat...",
                 "empty": u"Service Ausleeren aktiv: Geldscheinspeicher->Cashbox (automatisch), Münzauswurf (manuell: Knopf drücken),\n zum Beenden Abbrechen drücken",
                 "emptyingStop": u"Service: beende automatisches/manuelles Ausleeren..."}
        text = u""
        if self.mode in modes.keys():
            text += modes[self.mode]
        else:
            text += "bitte warten (Modus {})".format(self.mode)
        requested = None
        if self.mode.startswith("payin"):
            requested = self.requestedPayin
        elif self.mode.startswith("payout"):
            requested = self.requestedPayout
        if requested != None:
            text += u":\n{} von {} ".format(formatCent(totalSum), formatCent(requested))
        if self.mode.startswith("payin"):
            text += "bezahlt (maximal " + formatCent(self.maximumPayin) + ")"
        elif self.mode.startswith("payout"):
            text += "ausgezahlt"
        elif self.mode.startswith("empty"):
            text += "\n" + formatCent(totalSum)
        return text

    def startingUp(self):
        """
        return True if devices are still being started

        No action methods may be called until this returns False
        """
        return self.mode == "start"

    def payout(self, value):
        assert self.mode == "idle"
        assert value >= 0
        self.mode = "payout"
        self.requestedPayout = value
        self.payoutDeviceNumber = 0

    def abortPayin(self):
        if self.mode == "payin":
            for d in self.devices:
                d.stopAccepting()
            self.mode = "payinStop"
        elif self.mode == "payinStop":
            pass
        else:
            raise Exception("abortPayin in wrong mode")

    def getFinalAmount(self):
        """
        if stopped, return the final amount and reset to idle state

        else, return None
        """
        if self.mode != "stopped":
            return None
        ret = self.finishedAmount
        self._reset()
        self.mode = "idle"
        return ret

class PaymentDevicesManagerTest(unittest.TestCase):
    """ Test PaymentDevicesManager
    """
    def test_canPayout_with_one_random_datapoint_on_example_server(self):
        """
        test the _canPayout_total() function with 10 random datapoints and the exampleserver (from example config)
        """
        # probably hacky, should be improved
        cfg = ConfigParser()
        cfg.readfp(codecs.open('./FabLabKasse/config.ini.example', 'r', 'utf8'))

        for _ in range(0, 9):
            history = []

            p = PaymentDevicesManager(cfg=cfg)

            p.poll()

            def randFactor():  # 0 or 1 or something inbetween
                r = random.random() * 1.2 - 0.1
                if r < 0:
                    r = 0
                if r > 1:
                    r = 1
                return r

            def myRandInt(n):  # 0 ... n, with a finite >0 probability for both endpoints
                return int(randFactor() * n)
            canPayoutAmounts = []
            n = random.randint(2, 5)
            # fill canPayoutAmounts with random foo
            for _ in range(n):
                canPayoutAmounts.append([int(randFactor() * randFactor() * 70000), myRandInt(1023)])

            [canMaximumRequest, canRemain] = p._canPayout_total(canPayoutAmounts)
            requested = myRandInt(canMaximumRequest)
            paidOut = 0
            for [maximumRequest, maximumRemaining] in canPayoutAmounts:
                nowRequested = requested - paidOut
                nowRequested_limited = nowRequested
                if nowRequested > maximumRequest:
                    # requested more than the guaranteed amount
                    nowRequested_limited = maximumRequest + myRandInt(nowRequested - maximumRequest)
                nowPaidOut = nowRequested_limited - myRandInt(maximumRemaining)
                if nowPaidOut < 0:
                    nowPaidOut = 0

                if nowRequested <= maximumRequest:
                    # request is in the accepted range, will be satisfied
                    self.assertTrue(maximumRequest >= nowRequested >= nowPaidOut >= nowRequested - maximumRemaining)
                else:
                    # requested more than guaranteed, may not be satisfied
                    self.assertTrue(nowRequested >= nowPaidOut >= maximumRequest - maximumRemaining)
                history.append([requested, paidOut, nowPaidOut, nowRequested])
                paidOut += nowPaidOut
            msg = "Failed: {} {} {} {} {}\n".format(requested, paidOut, canMaximumRequest, canRemain, history)
            msg += str(canPayoutAmounts)
            self.assertTrue(requested - canRemain <= paidOut <= requested, msg=msg)
            self.assertTrue(paidOut >= 0, msg=msg)

def demo():
    """Simple demonstration using two exampleServer devices"""
    # TODO this code seems to be broken, maybe adapt code from unittest or discard
    p = PaymentDevicesManager(["exampleServer", "exampleServer"])

    def wait():
        p.poll()
        print p.statusText()
        time.sleep(0.3)
    while p.startingUp():
        wait()
    pay = None
    while pay == None:
        wait()
        pay = p.canPayout()
    print pay
    print "Es dürfen maximal {} Cent gezahlt werden. Ein Rest-Rückgeld von unter {} Cent wird nicht zurückgegeben!".format(pay[0], pay[1])
    shouldPay = 4213
    p.payin(shouldPay, shouldPay + pay[0])
    received = None
    while received == None:
        received = p.getFinalAmount()
        wait()
    print "Geld erhalten: {}".format(received)
    p.poll()
    if received > shouldPay:
        p.payout(received - shouldPay)
    paidOut = None
    while paidOut == None:
        paidOut = p.getFinalAmount()
        wait()
    paidOut = -paidOut
    print "Rückgeld gezahlt: {}".format(paidOut)
    print "nicht ausgezahltes Rückgeld: {}".format(received - shouldPay - paidOut)


if __name__ == "__main__":
    demo()
