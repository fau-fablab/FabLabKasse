#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# dummy cash-acceptor server
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

from .cashServer import CashServer
import random


class ExampleServer(CashServer):

    def initializeDevice(self):
        pass

    def getCanPayout(self):
        return [2999, 999]

    def getCanAccept(self):
        return True

    def doEmpty(self):
        pass
        # emptyingActive=True

    def pollAndUpdateStatus(self):
        self.busy = False
        if self.currentMode == "accept":
            self.busy = True
            if self.moneyReceivedTotal + 1000 <= self.moneyReceiveAllowed:
                if random.random() > 0.9:
                    self.event_receivedMoney(1, 1000, "storage", "yay, example server received some virtual money!")
        elif self.currentMode == "dispense":
            self.busy = True
            if self.moneyDispensedTotal + 1000 <= 3000 and self.moneyDispensedTotal + 1000 <= self.moneyDispenseAllowed:
                if random.random() > 0.9:
                    self.event_dispensedMoney(1, 1000, "storage", "yay, example server dispensed some virtual money!")
            else:
                self.currentMode = "stopping"
        elif self.currentMode == "empty":
            self.busy = True
            if random.random() > 0.95:
                self.currentMode = "stopping"

    def getSleepTime(self):
        return random.random() * 2

    def checkAssertionsBeforePoll(self):
        return


if __name__ == "__main__":
    e = ExampleServer()
    e.run()
