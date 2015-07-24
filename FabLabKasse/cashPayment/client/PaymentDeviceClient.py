#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# generic cash-acceptor client
# protocol see ../protocol.txt
# example server implementation see ../server/exampleServer.py

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


"""
Client for accessing a cash device driver.
"""

import sys
import logging
from FabLabKasse.libs.process_helper.nonblockingProcess import nonblockingProcess
import pickle
import base64
import monotonic as monotonic_time


class PaymentDeviceClient(object):

    """
    Client for accessing a cash device driver. It starts a new python process
    ("server") for the specified device driver. It uses non-blocking
    communication and talks to the server process using stdin/stdout.
    """

    def __init__(self, cmd, options):
        """
        :param cmd: class name of the device driver
        :param options: dictionary of options (name (required), device, ...) that were set in config.ini as deviceN_foo=value
        :type options: dict(unicode, unicode)
        """
        self.stopped = False
        self.canAccept_cachedResponse = None
        self._reset()
        self.waitingForResponse = False
        if (sys.version_info.major, sys.version_info.minor) != (2, 7):
            raise Exception("not running in python2.7 - please update PaymentDeviceClient to use the right python version for the payment servers")
        args = ["/usr/bin/env", "python2.7", "-m", "FabLabKasse.cashPayment.server." + cmd, base64.b64encode(pickle.dumps(options))]
        logging.info("starting cashPayment server: PYTHONPATH=.. " + " ".join(args))
        self.process = nonblockingProcess(args, {"PYTHONPATH": ".."})
        self.commandline = cmd
        self.options = options
        self.lastCommand = ""

    def __repr__(self):
        return "<PaymentDeviceClient(type=" + self.commandline + ", name=" + self.options["name"] + ")>"

    def _reset(self):
        """
        Initialise/Reset internal state to default values

        does not check for any condition!

        Called at the end of an operation to go back to idle state
        """
        self.lastResponseTime = None
        self.finalAmount = None
        self.pollAmount = None
        self.requestedAccept = None
        self.lastSentAccept = None
        self.requestedDispense = None
        self.testDispenseAnswer = None
        self.status = "idle"
        self.stopped = False

    def poll(self):
        """
        update internal status

        call this regularly

        :raise: Exception if the device crashed - do not try to recover from this exception, or the result of any following calls will be undefined
        """
        if not self.process.isAlive():
            raise Exception("device {} server crashed -- check cash-{}.log. If it crashed before writing the logfile, try launching the server yourself with the commandline from gui.log ".format(self, self.options["name"]))
        if not self.waitingForResponse:
            if self.status == "stop":
                if self.stopped:
                    cmd = None
                    # wait until getFinalAmountAndReset() is called
                else:
                    cmd = "STOP"
            elif self.status == "dispense":
                cmd = "DISPENSE {}".format(self.requestedDispense)
            elif self.status == "accept":
                cmd = "ACCEPT {}".format(self.requestedAccept)
                self.lastSentAccept = self.requestedAccept
            elif self.status == "acceptWait":
                # alternate between polling and (if necessary) updating the maximum accepted value
                if self.lastSentAccept != self.requestedAccept and self.lastCommand.startswith("POLL"):
                    cmd = "UPDATE-ACCEPT {}".format(self.requestedAccept)
                    self.lastSentAccept = self.requestedAccept
                else:
                    cmd = "POLL"
            elif self.status == "dispenseWait":
                # alternate between polling (to get intermediate value) and stopping (to see if finished)
                if self.lastCommand == "POLL":
                    cmd = "STOP"
                else:
                    cmd = "POLL"
            elif self.status == "testDispense":
                cmd = "CANPAYOUT"
            elif self.status == "canAccept":
                cmd = "CANACCEPT"
            elif self.status == "empty":
                cmd = "EMPTY"
            elif self.status == "emptyWait":
                cmd = "POLL"
            elif self.status == "idle":
                cmd = None
            else:
                raise Exception("unknown status")
            if cmd == None:
                return
            print "SEND CMD: " + cmd  # +"\n"
            self.process.write(cmd + "\n")
            self.lastCommand = cmd
            self.waitingForResponse = True
            self.lastResponseTime = monotonic_time.monotonic()  # get monotonic time. until python 3.3 we have to use this extra module because time.monotonic() is not available in older versions.

        response = self.process.readline()
        if response == None and self.waitingForResponse \
                and monotonic_time.monotonic() - self.lastResponseTime > 50:
            raise Exception("device {} server timeout (>50sec)".format(self))
        if response != None:
            print "got response: '" + response + "'"
            assert self.waitingForResponse
            self.waitingForResponse = False

            # strip prefix
            prefix = "COMMAND ANSWER:"
            assert response.startswith(prefix), "response with wrong prefix: " + response
            response = response[len(prefix):]
            cmd = self.lastCommand
            # parse response
            if cmd.startswith("DISPENSE"):
                assert response == "OK"
                assert self.status == "dispense"
                self.status = "dispenseWait"  # wait for dispense to finish
            elif cmd.startswith("ACCEPT"):
                assert response == "OK"
                assert self.status in ["accept", "stop"]
                if self.status == "accept":
                    self.status = "acceptWait"  # wait for accept to finish
                elif self.status == "stop":
                    pass  # "quickstop": the status was changed to "stop" even before the accept mode was fully started. slowly stop accepting
            elif cmd.startswith("UPDATE-ACCEPT"):
                assert response == "OK"
                assert self.status in ["accept", "stop"]
            elif cmd == "POLL":
                l = response.split(" ")
                assert len(l) > 1
                self.pollAmount = int(l[0])
            elif cmd == "CANPAYOUT":
                l = response.split(" ")
                assert len(l) == 2
                self.testDispenseAnswer = [int(l[0]), int(l[1])]
                self.status = "idle"
            elif cmd == "CANACCEPT":
                assert self.status == "canAccept"
                if response == "True":
                    self.canAccept_cachedResponse = True
                elif response == "False":
                    self.canAccept_cachedResponse = False
                else:
                    raise Exception("response is neither False nor True:" + response)
                self.status = "idle"
            elif cmd == "STOP":
                assert not self.stopped
                assert self.status in ["stop", "dispenseWait"]
                if response == "wait":
                    pass  # do nothing, resend STOP next time
                else:
                    self.finalAmount = int(response)
                    self.stopped = True
            elif cmd == "EMPTY":
                assert response == "OK"
                self.status = "emptyWait"
            else:
                raise Exception("unknown command at parsing answer")

    def accept(self, maximumPayin):
        """
        accept up to maximumPayin money, until stopAccepting() is called

        poll() must be called before other actions are taken
        """
        assert self.status == "idle"
        self.status = "accept"
        self.requestedAccept = maximumPayin

    def updateAcceptValue(self, maximumPayin):
        """
        lower the amount of money that is accepted at maximum

        this can be called while accept is active

        example use case: Two payment devices should accept 50€ in total. 10€ were inserted into the first device -> update the second device to a maximum of 40€.
        """
        if self.requestedAccept > 0 and self.status == "accept":
            self.requestedAccept = maximumPayin

    def stopAccepting(self):
        """
        stop accepting (does not work immediately - some payins may be possible!)

        :rtype: None
        """
        if self.status == "accept":
            # if the last sent command is not ACCEPT, we have not sent the ACCEPT command yet. this means that poll wasn't called yet.
            assert self.lastCommand.startswith("ACCEPT"), "you must call poll() after accept() first before calling stopAccepting() !"

            # the answer to ACCEPT was not yet received
            # instead of messing up everything, just wait for the answer and then send stop commands
            self.status = "stop"
            return
        assert self.status == "acceptWait"
        assert not self.stopped
        self.status = "stop"

    def dispense(self, amount):
        """
        Dispense up to the requested amount of money (as much as possible)

        - Wait until hasStopped() is true, then retrieve the paid out value with getFinalAmountAndReset()
        - An intermediate value (as a progess report) can be retrieved with getCurrentAmount, but the operation cannot be aborted.
        - If you want to make sure that enough is available, see possibleDispense()
        """
        assert self.status == "idle"
        self.requestedDispense = amount
        self.status = "dispense"

    def possibleDispense(self):
        """
        how much can be paid out?

         (function may only be called while no operation is in progress, will raise Exception otherwise)

         return value:

         - ``None``: request in progress, please call the function again until it does not return None.
           No other actions (dispense/accept/canPayout) may be called until a non-None value was returned!
           Call poll() repeatedly until possibleDispense()!=None.

         - [maximumAmount, remainingAmount]: This one non-None response is not cached, another call will send return None again and send a new query to the device
            - maximumAmount (int): the device has enough money to pay out any amount up to maximumAmount
            - remainingAmount (int): How much money could be remaining at worst, if canBePaid==True? This is usually a per-device constant.
              remainingAmount will be == 0 for a small-coins dispenser that includes 1ct.


         .. IMPORTANT::
            it can be still possible to payout more, but not any value above maximumAmount!

            For example a banknote dispenser filled with 2*10€ and 5*100€ bills will return:

            ``possibleDispense() == [2999, 999]`` which means "can payout any value in 0...29,99€ with an unpaid rest of <= 9,99€"

            But it can still fulfill a request of exactly 500€!


        :rtype: None | [int, int]
        """
        if self.testDispenseAnswer != None:
            # we have a cached answer
            a = self.testDispenseAnswer
            self.testDispenseAnswer = None
            return a

        if self.status == "testDispense":
            # request is already sent, but answer not yet received
            return None
        if self.status != "idle":
            raise Exception("possibleDispense cannot be used while dispensing or accepting")
        self.testDispenseAnswer = None
        self.status = "testDispense"
        return None

    def canAccept(self):
        """
        does the device support accept commands?

        (If this function has not returned True/False once before, it may only
        be called while no operation is in progress and will raise an Exception
        otherwise. )

        return values and usage:

        - None:  please call the function again later. The answer has not yet
          been received from the device.
          No other actions (dispense/accept/possibleDispense) may be called until
          a non-None value was returned!
          call poll() repeatedly until ``canAccept() != None``
        - True/False: Does (not) support accepting. (Now the answer is cached and may the function may be called again always)

        :rtype: boolean | None
        """
        if self.canAccept_cachedResponse != None:
            return self.canAccept_cachedResponse
        if self.status == "canAccept":
            return None
        if self.status != "idle":
            raise Exception("canAccept cannot be used for the first time while dispensing or accepting")
        self.status = "canAccept"

    def empty(self):
        """
        start service-mode emptying

        The implementation of this modes is device specific:

        - If the device has
          an inaccessible storage, it should move the contents to the cashbox
          so that it can be taken out for counting.
        - If available, manual payout buttons are enabled.

        usage:

        - call empty()
        - sleep, do something else, whatever you want...
        - call poll() at least once before the next step:
        - as soon as you want to stop, call stopEmptying()
        - call hasStopped() until it returns True
        - then call getFinalAmountAndReset()
        """
        assert self.status == "idle"
        self.status = "empty"

    def stopEmptying(self):
        """
        end the mode that was started by empty()

        usage: see empty()
        """
        assert self.status != "empty", "stopEmptying() called before first poll()"
        assert self.status == "emptyWait"
        assert not self.stopped
        self.status = "stop"

    def getCurrentAmount(self):
        "how much has currently been paid in? (value is not always up-to-date, but will not be higher than the actual value)"
        return self.pollAmount

    def hasStopped(self):
        "returns True as soon as the operation (accept/dispense) has finished"
        return self.stopped

    def getFinalAmountAndReset(self):
        "call this as soon as hasStopped() is true. this returns the final amount paid in/out (negative for payout)"
        assert self.hasStopped()
        r = self.finalAmount
        self._reset()
        return r

#==============================================================================
# old demo code that is currently not working because
# if __name__ == "__main__":
#     if "--nv11-demo" in sys.argv:
#         nv11_demo()
#     else:
#         dummy_demo()
#
#
# def nv11_demo():
#     a = PaymentDeviceClient("../server/banknotenleser.py")
#     a.poll()
#     while a.canAccept() == None:
#         print "waiting for canAccept"
#         a.poll()
#         time.sleep(1)
#     print a.canAccept()
#     a.accept(2341)
#     for i in range(42):
#         a.poll()
#         print a.getCurrentAmount()
#         time.sleep(1)
#     a.stopAccepting()
#     while not a.hasStopped():
#         a.poll()
#         time.sleep(1)
#     print a.getFinalAmountAndReset()
#
#     print "can dispense: ..."
#     canDispense = None
#     while canDispense == None:
#         canDispense = a.possibleDispense()
#         a.poll()
#         time.sleep(1)
#     print "can dispense:", canDispense
#
#     a.dispense(2341)
#
#     while not a.hasStopped():
#         a.poll()
#         print "waiting for dispense to stop, currently dispensed", a.getCurrentAmount()
#         time.sleep(1)
#     print "final dispensed:", a.getFinalAmountAndReset()
#
#
# def dummy_demo():
#     a = PaymentDeviceClient("../server/exampleServer.py")
#     a.poll()
#     while a.canAccept() == None:
#         print "waiting for canAccept"
#         a.poll()
#         time.sleep(1)
#     print a.canAccept()
#     a.accept(2341)
#     for i in range(4):
#         a.poll()
#         print a.getCurrentAmount()
#         time.sleep(1)
#     a.stopAccepting()
#     while not a.hasStopped():
#         a.poll()
#         time.sleep(1)
#     print a.getFinalAmountAndReset()
#
#     print "can dispense: ..."
#     canDispense = None
#     while canDispense == None:
#         canDispense = a.possibleDispense()
#         a.poll()
#         time.sleep(1)
#     print "can dispense:", canDispense
#
#     a.dispense(2341)
#
#     while not a.hasStopped():
#         a.poll()
#         print "waiting for dispense to stop, currently dispensed", a.getCurrentAmount()
#         time.sleep(1)
#     print "final dispensed:", a.getFinalAmountAndReset()
