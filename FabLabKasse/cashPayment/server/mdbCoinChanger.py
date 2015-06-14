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

import logging
from .mdbCash.mdb import MdbCashDevice
from .cashServer import CashServer

class MDBCoinChangerServer(CashServer):
    ''' setup device
    supported options:
    
    port = /dev/ttyACM0
    
    enable RGB LED outputs:
    leds = True
    disable:
    leds = False
    
    external "dumb" hopper (not on the MDB bus, but via hopper interface):
    disable (default):
    hopper = False
    1,00 € coins:
    hopper = 100
    2,00 € coins:
    hopper = 200
    
    '''
    def initializeDevice(self):
        logging.info(str(self.options))
        port=self.options.get("port", "/dev/ttyACM0")
        extensionConfig = {}
        extensionConfig["leds"] = (self.options.get("leds","").strip().lower() == "true")
        extensionConfig["hopper"] = self.options.get("hopper","").strip()
        if extensionConfig["hopper"].isdigit():
            extensionConfig["hopper"] = int(extensionConfig["hopper"])
        else:
            extensionConfig["hopper"] = False
        self.dev=MdbCashDevice(port, extensionConfig=extensionConfig)

    ''' return [a, b] so that for every payout request up to a the resulting payout is at least (request-b) '''
    def getCanPayout(self):
        return self.dev.getPossiblePayout()
    
    ''' return True if device is an acceptor device '''
    def getCanAccept(self):
        return True
    
    ''' empty the payout store.  '''
    def doEmpty(self):
        pass # empty == enable manual dispense buttons
        # do nothing, will be enabled at every poll
    
    ''' poll the device, update self.busy, self.moneyReceivedTotal and self.moneyDispensedTotal. '''
    ''' set self.busy=False only if the device has completely stopped, i.e. no spontaneous dispense/accept/empty can happen '''
    ''' when dispensing/emptying has completed, change self.currentMode to "stopping" '''
    def pollAndUpdateStatus(self):
        status=self.dev.poll()
        for d in status["accepted"]:
            self.event_receivedMoney(d["count"], d["denomination"], d["storage"], "received")
        
        for d in status["manuallyDispensed"]:
            self.event_internallyMovedMoney(d["count"], d["denomination"], d["storage"], "manual", "dispensed after manual request (service button)")
        if not self.currentMode in ["empty", "stopping"]:
            assert status["manuallyDispensed"]==[]
        
        # ATTENTION, overwritten later near the end of this function
        self.busy = (status["busy"] or self.currentMode=="empty")
        
        # accept/deny coins and manual dispense
        # stop if nothing to do
        acceptCoins=False
        allowManualDispense=False
        if self.currentMode == "accept":
            smallestCoinValue=self.dev.getSortedCoinValues()[-1][1]
            if self.moneyReceiveAllowed - self.moneyReceivedTotal > smallestCoinValue:
                self.dev.setLEDs(["00FF00B", "000000N"]) # payin blink green, payout off
                acceptCoins=True
            else:
                self.dev.setLEDs(["FF0000T", "000000N"]) # payin red, payout off
                # remaining allowed amount is smaller than the smallest coin  - stop accepting
                self.currentMode="stopping"
        elif self.currentMode == "dispense":
            if self.moneyDispensedTotal <= self.moneyDispenseAllowed:
                if not self.busy:
                    dispensedNow=self.dev.dispenseValue(self.moneyDispenseAllowed-self.moneyDispensedTotal)
                    if dispensedNow==False: # cannot dispense anymore
                        self.currentMode = "stopping"
                    else:
                        self.event_dispensedMoney(dispensedNow["count"], dispensedNow["denomination"], dispensedNow["storage"], "dispensed")
                        self.dev.setLEDs(["000000N", "FF7700B"]) # payin off, payout blink orange
            else:
                self.currentMode="stopping"
                
            if self.currentMode == "stopping": # mode just now changed to 'stopping'
                self.dev.setLEDs(["000000N", "FFFFFFT"]) # payin off, payout white (for a certain time, then off)
        elif self.currentMode == "empty":
            self.dev.setLEDs(["000000N", "0000FFT"]) # payin off, payout blue
            allowManualDispense=True
            
        self.dev.setAcceptCoins(acceptCoins, allowManualDispense)
        
        # WORKAROUND: the device sometimes also reports "busy" in the idle
        # state. This does not (necessarily) mean that an unintended
        # payout/payin operation is in progress, but also happens when the 
        # cassette is removed for service purposes.
        # Therefore we filter this event in the "idle" state.
        if self.busy and self.currentMode == "idle":
            logging.info("ignoring BUSY flag in idle mode, most probably" \
                "caused by service action")
            self.busy = False
        
    ''' sleep time in seconds between polls - do not make this larger than 1sec or command handling will be slowed down '''
    def getSleepTime(self):
        return 0.5


    
if __name__=="__main__":
    e=MDBCoinChangerServer()
    e.run()
