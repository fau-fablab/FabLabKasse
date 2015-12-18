#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# base class for cash-acceptor server
# protocol see protocol.txt

# (C) 2013 Max Gaukler <development@maxgaukler.de>

# This program is free software: you can redistribute it and/or modify
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
import sys
import re
import logging
from abc import ABCMeta, abstractmethod  # abstract base class support
import threading
import Queue
from ... import scriptHelper
from ..cashState import CashStorage, CashState
import pickle
import base64


class CashServer:
    __metaclass__ = ABCMeta
    MAXIMUM_DISPENSE = 200 * 100

    def reply(self, s):
        s = "COMMAND ANSWER:" + str(s)
        print s
        sys.stdout.flush()  # necessary if not run from console
        logging.info(s)

    def __init__(self):
        # load options, PaymentDevicesManager encoded these
        self.options = pickle.loads(base64.b64decode(sys.argv[1]))
        deviceName = self.options['name']
        self.lock = scriptHelper.FileLock("cash-" + deviceName)
        db = scriptHelper.getDB()
        self.cash = CashStorage(db, deviceName, readonly=False)

        self.moneyDispenseAllowed = 0
        self.moneyReceiveAllowed = 0
        self.__moneyDispensedTotal = 0
        self.__moneyReceivedTotal = 0
        self.currentMode = "idle"
        self.busy = None

        def readStdinThread():
            global stdinQueue
            while True:
                stdinQueue.put(sys.stdin.readline())

        global stdinQueue
        stdinQueue = Queue.Queue()
        thread = threading.Thread(target=readStdinThread, name="stdinReader")
        thread.daemon = True
        thread.start()
        scriptHelper.setupSigInt()
        logfile = "cash-" + deviceName + ".log"
        scriptHelper.setupLogging(logfile)

    def readlineStdinNonblocking(self):
        global stdinQueue
        try:
            return stdinQueue.get(block=False)
        except Queue.Empty:
            return None

    def run(self):
        logging.info("starting up")

        try:
            self._run()
        except Exception:
            logging.exception("Stopping because of exception")

    def _run(self):
        idleCounter = 9999

        self.initializeDevice()

        while True:
            # TODO this statemachine is too complicated.
            # rewrite it using two separate variables:
            #   mode = accept / dispense / empty / idle
            #  status = running / stopping / stopped / idle
            # (stopCountdown = 0 ... N      if a minimum number of idle iterations is required e.g. for accept)
            #  mode transitions: idle -> accept/dispense/empty (on ACCEPT/DISPENSE/EMPTY command)
            #                     accept/dispense/empty  -> idle (on successful STOP command)
            # status transitions: idle -> running (on ACCEPT/DISPENSE/EMPTY command)
            #                   running -> stopping (if STOP command received)
            #                   stopping -> stopped (if not busy)
            #                   stopped -> idle (successful STOP command)
            command = self.readlineStdinNonblocking()
            if command is not None:
                command = command.strip()
                logging.info("cmd: " + command + "\n")
                acceptCommandMatch = re.match("^ACCEPT ([0-9]+)$", command)
                updateAcceptCommandMatch = re.match("^UPDATE-ACCEPT ([0-9]+)$", command)
                dispenseCommandMatch = re.match("^DISPENSE ([0-9]+)$", command)
                if acceptCommandMatch:
                    assert self.currentMode == "idle"
                    self.currentMode = "accept"
                    self.moneyReceiveAllowed = int(acceptCommandMatch.groups()[0])
                    self.reply("OK")
                    self.cash.log("started accepting, max. {0}".format(self.moneyReceiveAllowed))
                elif updateAcceptCommandMatch:
                    newMoneyReceiveAllowed = int(updateAcceptCommandMatch.groups()[0])
                    if self.moneyReceiveAllowed > newMoneyReceiveAllowed:
                        self.moneyReceiveAllowed = newMoneyReceiveAllowed
                    self.reply("OK")
                elif dispenseCommandMatch:
                    assert self.currentMode == "idle"
                    self.currentMode = "dispense"
                    self.moneyDispenseAllowed = int(dispenseCommandMatch.groups()[0])
                    assert self.moneyDispenseAllowed <= self.MAXIMUM_DISPENSE
                    assert self.moneyDispenseAllowed >= 0
                    self.reply("OK")
                    self.cash.log("started dispensing, requested {0}".format(self.moneyDispenseAllowed))
                elif command == "POLL":
                    self.reply("{0} {1} (not the final value!)".format(self.moneyReceivedTotal - self.moneyDispensedTotal,
                                                                     self.currentMode))
                elif command == "CANPAYOUT":
                    p = self.getCanPayout()
                    self.reply("{0} {1}".format(p[0], p[1]))
                elif command == "CANACCEPT":
                    self.reply(str(self.getCanAccept()))
                elif command == "EMPTY":
                    assert self.currentMode == "idle"
                    self.currentMode = "empty"
                    self.doEmpty()
                    self.reply("OK")
                    self.cash.log("started emptying.")
                elif command == "STOP":
                    assert self.currentMode != "idle"  # cannot stop twice
                    if self.currentMode == "stopped":
                        self.reply(self.moneyReceivedTotal - self.moneyDispensedTotal)
                        self.cash.log("stopped. received {0}".format(self.moneyReceivedTotal - self.moneyDispensedTotal))
                        self.__moneyReceivedTotal = 0
                        self.__moneyDispensedTotal = 0
                        self.currentMode = "idle"
                        idleCounter = 999
                    else:
                        # wait until the action finishes (e.g. all money dispensed), then the mode will change to "stopping"
                        # "stopping" waits for shutdown (empty poll response) and then switches to "stopped"
                        # self.moneyDispenseAllowed=0
                        self.moneyReceiveAllowed = 0
                        if self.currentMode == "empty":
                            self.currentMode = "stopping"
                        self.reply("wait")
                elif command == "":
                    # if readline() returns an empty string, the input was closed or EOF was received
                    logging.info("Exiting (stdin closed)")
                    sys.exit(0)
                else:
                    raise Exception("unknown network command {0}".format(repr(command)))

            assert not (self.moneyDispenseAllowed > 0 and self.moneyReceiveAllowed > 0)

            if self.currentMode == "idle":
                assert self.moneyReceivedTotal == self.moneyDispensedTotal == 0
                if idleCounter < self.getIdleTime():
                    idleCounter += 1
                    # time.sleep(1.0)
                    continue
                else:
                    idleCounter = 0
                    # poll once every self.getIdleTime(), usually 60s, don't spam the log

            self.pollAndUpdateStatus()

            if self.currentMode.startswith("stopping"):
                self.moneyDispenseAllowed = 0
                self.moneyReceiveAllowed = 0
                if not self.currentMode.startswith("stopping..."):
                    # use the mode name as counter
                    if self.busy:
                        self.currentMode = "stopping"
                    else:
                        self.currentMode += "."
                else:
                    self.currentMode = "stopped"
            elif self.currentMode == "dispense":
                pass
            elif self.currentMode == "accept":
                if self.__moneyReceivedTotal >= self.moneyReceiveAllowed:
                    self.currentMode = "stopping"
            elif self.currentMode == "idle":
                assert not self.busy
            elif self.currentMode == "empty":
                if not self.busy:
                    self.currentMode = "stopping"
            elif self.currentMode == "stopped":
                pass  # do nothing and wait for STOP command
            else:
                raise Exception("unknown self.currentMode")
            # prevVal=val

            time.sleep(self.getSleepTime())

    def event_receivedMoney(self, count, denomination, storage="main", comment="accept"):
        logging.info("event_receivedMoney {0}*{1}".format(count, denomination))
        assert count > 0
        assert denomination > 0
        self.cash.addToState(storage, CashState({denomination: count}), comment=comment)
        # TODO improve currentMode so that "stopping..." is not the same mode for dispense and accept
        # would like something like:  assert self.currentMode.contains("accept")
        assert self.moneyDispenseAllowed == 0, "error: money received while in dispensing-mode!"
        assert self.currentMode not in ["dispense", "stopped",
                                        "idle"], "error: money received while in dispensing-mode!"
        self.__moneyReceivedTotal += count * denomination

    def event_dispensedMoney(self, count, denomination, storage="main", comment="dispense"):
        logging.info("event_dispensedMoney {0}*{1}".format(count, denomination))
        assert count > 0
        assert denomination > 0
        self.cash.addToState(storage, CashState({denomination: -count}), comment=comment)
        # TODO improve currentMode so that "stopping..." is not the same mode for dispense and accept
        # would like something like:
        # assert self.currentMode.contains("dispense")
        assert self.moneyReceiveAllowed == 0, "error: money dispensed while in accepting-mode!"
        assert self.currentMode not in ["accept", "stopped", "idle"], "error: money dispensed while in accepting-mode!"
        self.__moneyDispensedTotal += count * denomination

    # internal move (between different subindices of the cash device)
    # not for giving money to the customer
    def event_internallyMovedMoney(self, count, denomination, fromStorage, toStorage, comment="move"):
        assert count > 0
        assert denomination > 0
        self.cash.moveToOtherSubindex(fromStorage, toStorage, denomination, count, comment)

    @abstractmethod
    def initializeDevice(self):
        """ setup device"""
        pass

    @abstractmethod
    def getCanPayout(self):
        """
        Get a two-element list of [maximumAmount, remainingAmount]:
          - maximumAmount (int): the device has enough money to pay out any amount up to maximumAmount
          - remainingAmount (int): How much money could be remaining at worst for any request <= maximumAmount? This is usually a per-device constant.

              Examples for remainingAmount:
               - 0 for a small-coins dispenser that includes 1ct.
               - 99 for a coin dispenser that only has 1€ coins and larger.
               - 499 for a banknote dispenser that has 5€ notes

        :return: [x, y] so that for every payout request <= x the resulting payout is >= (request-y)
        :rtype: list[int]
        """
        pass

    @abstractmethod
    def getCanAccept(self):
        """ return True if device is an acceptor device """
        pass

    @abstractmethod
    def doEmpty(self):
        """ empty the payout store.  """
        pass

    @abstractmethod
    def pollAndUpdateStatus(self):
        """ poll the device, update self.busy, and call :meth:`event_receivedMoney` and :meth:`event_dispensedMoney`

        set self.busy=False only if the device has completely stopped, i.e. no spontaneous dispense/accept/empty can happen
        when dispensing/emptying has completed, change self.currentMode to "stopping" """
        pass

    def getSleepTime(self):
        """ sleep time in seconds between polls - do not make this larger than 1sec or
        command handling will be slowed down
        """
        return 0.5

    def getIdleTime(self):
        """ slow down polling after specified time -- change to float("inf") to disable this feature """
        return 60

    @property
    def moneyDispensedTotal(self):
        """ an implementation may read moneyDispensedTotal and moneyReceivedTotal, but writing must take place
        through event_dispensedMoney and event_receivedMoney.
        """
        return self.__moneyDispensedTotal

    @property
    def moneyReceivedTotal(self):
        """ an implementation may read moneyDispensedTotal and moneyReceivedTotal, but writing must take place
        through event_dispensedMoney and event_receivedMoney.
        """
        return self.__moneyReceivedTotal
