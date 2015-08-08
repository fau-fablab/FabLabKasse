#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2013-2015 Julian Hammer <julian.hammer@fablab.fau.de>
#                         Maximilian Gaukler <max@fablab.fau.de>
#                         Timo Voigt <timo@fablab.fau.de>
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program. If not,
# see <http://www.gnu.org/licenses/>.

from PyQt4 import QtGui, QtCore
from .uic_generated.PayupCashDialog import Ui_PayupCashDialog
import functools
import logging
from decimal import Decimal


class PayupCashDialog(QtGui.QDialog, Ui_PayupCashDialog):

    def __init__(self, parent, amount_total):
        """payment method dialog for automatic cash payin and payout"""
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        # maximize window - WORKAROUND because showMaximized() doesn't work
        # when a default geometry is set in the Qt designer file
        QtCore.QTimer.singleShot(0, lambda: self.setWindowState(QtCore.Qt.WindowMaximized))
        self.pushButton_return.clicked.connect(self.payoutReturnCompletely)
        self.pushButton_donate.clicked.connect(self.donateReturn)
        self.pushButton_acceptLowPayout.clicked.connect(self.acceptLowPayoutWarning)
        self.pushButton_return.setVisible(False)
        self.pushButton_donate.setVisible(False)
        self.pushButton_donate1.setVisible(False)
        self.pushButton_donate2.setVisible(False)
        self.pushButton_donate3.setVisible(False)
        self.pushButton_cancel.setVisible(False)
        self.pushButton_finish.setVisible(False)
        self.pushButton_acceptLowPayout.setVisible(False)
        self.pushButton_receipt.setVisible(False)
        self.pushButton_receipt.clicked.connect(self.accept_and_print_receipt)
        assert amount_total % Decimal("0.01") == 0
        self.centsToPay = int(100 * amount_total)
        self.centsToPayOut = None
        self.centsReceived = None
        self.centsPaidOut = None
        self.returnDonated = False
        # The finish button doesn't print a receipt, only the "print receipt and finish" one.
        # Sometimes the later logic still forces receipt printing  (e.g. payment aborted, not everything paid back)
        self.receipt_wanted = False
        assert self.centsToPay >= 0
        self.state = "init"

        if not parent.cashPayment.devices:
            QtGui.QMessageBox.warning(self, "Error", "No cash payment devices are configured. For testing please add an example (simulated) device.")

        self.update()
        # call update() regularly via QTimer
        self.timer = QtCore.QTimer()
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.update)
        self.timer.start()
        # timer will be cleaned up in self.accept()

    @staticmethod
    def getSuggestedDonations(toPay, payout):
        """ heuristically determine a list of up to three recommended donation values.
        :param toPay: how much was paid for articles
        :param payout: how much was paid too much and would be paid back to the user
        """
        # step 1: collect a list of useful donation values, where no small coins are paid out
        donationCandidates = set()

        # hardcoded payout options: round up to nearest 50c + donate 50c, etc.
        donationCandidates.add(payout % 50 + 50)
        donationCandidates.add(payout % 100 + 100)
        donationCandidates.add(payout % 100 + 200)

        for denomination in [50, 100, 200, 500, 10000]:
            # suggest return possible only with coins of denomination X (i.e., no small coins)
            donationCandidates.add(payout % denomination)
        for usefulPayouts in [50] + range(100, 1000, 100) + range(1000, 20000, 1000):
            # suggest a donation where exactly X is paid out
            donationCandidates.add(payout - denomination)

        # do not suggest:
        # - donate nothing/everything [there are already buttons for that]
        #  - any donation greater than "donate everything" (makes no sense)
        # also convert to sorted list
        donationCandidates = filter(lambda donation: 0 < donation < payout,  donationCandidates)
        donationCandidates.sort()

        # step 2: from the previous list, fetch up to three values based on the amount paid
        suggestedDonation = []
        donationCandidates.reverse()
        for donationPart in [0.01, .05, .10]:
            try:
                while True:
                    value = donationCandidates.pop()
                    if value < donationPart * toPay:
                        continue
                    else:
                        suggestedDonation.append(value)
                        break
            except IndexError:
                # no suggestions left
                break
        return suggestedDonation

    def showSuggestedDonations(self):
        """update text of donate[123] buttons"""
        self.pushButton_donate.setText(u"{} (gesamtes Rückgeld) spenden ".format(PayupCashDialog.formatCent(self.centsReceived - self.centsToPay)))
        suggestedDonations = PayupCashDialog.getSuggestedDonations(toPay=self.centsToPay, payout=self.centsReceived - self.centsToPay)
        suggestedDonations.reverse()
        for i in [1, 2, 3]:
            button = getattr(self, "pushButton_donate" + str(i))
            try:
                button.clicked.disconnect()
            except TypeError:
                pass
                # .disconnect() returns TypeError if currently nothing is connected to the signal
                # http://stackoverflow.com/questions/21586643/pyqt-widget-connect-and-disconnect/21587045#21587045
            if len(suggestedDonations) > 0:
                donationValue = suggestedDonations.pop()
                # functools.partial is used here instead of lambda because "donationValue" needs to be evaluated here.
                #   when using a lambda, it would be wrongly used by-reference and get the value of the last iteration of this loop
                #  see http://stackoverflow.com/a/3252364

                button.clicked.connect(functools.partial(self.payoutReturn, self.centsReceived - self.centsToPay - donationValue))
                button.setText(self.formatCent(donationValue) + " spenden")
                button.setVisible(True)
            else:
                # no suggestions left, hide button
                button.setVisible(False)

    @staticmethod
    # TODO deduplicate
    def formatCent(x):
            return u"{:.2f}\u2009€".format(float(x) / 100).replace(".", ",")

    def update(self):
        p = self.parent().cashPayment
        p.poll()

        self.label_toPay.setText(PayupCashDialog.formatCent(self.centsToPay))

        if self.centsReceived == None:
            # still receiving money
            received = p.getCurrentAmount()
            paidOut = 0
        else:
            received = self.centsReceived
            if self.centsPaidOut == None:
                paidOut = -p.getCurrentAmount()
            else:
                paidOut = self.centsPaidOut
        self.label_received.setText(PayupCashDialog.formatCent(received))
        missing = self.centsToPay - received
        if missing < 0:
            self.label_missing_text.setText(u"Rückgeld")
            missing = -missing
        self.label_missing.setText(PayupCashDialog.formatCent(missing))

        self.label_return_donation_text.setEnabled(self.returnDonated)
        self.label_return_donation.setEnabled(self.returnDonated)

        if self.returnDonated:
            self.label_return_donation.setText(PayupCashDialog.formatCent(self.centsReceived - self.centsToPay - self.centsToPayOut))
        if self.centsToPayOut != None:
            self.label_missing.setText(PayupCashDialog.formatCent(self.centsToPayOut))
        self.label_payout_current.setText(PayupCashDialog.formatCent(paidOut))
        self.label_status.setText(p.statusText())

        if self.state == "init":
            if not p.startingUp():
                self.state = "initCanPayout"
        elif self.state == "initCanPayout":
            pay = p.canPayout()
            if pay != None:
                [self.payoutMaximumAmount, self.payoutRemainingAmount] = pay

                # all amounts under 50€ may be paid with <= n+50€
                self.allowedOverpay = 50 * 100
                if self.centsToPay < 50 * 100:
                    # above 50€ may pay n+100€
                    if self.payoutMaximumAmount > 50 * 100:
                        self.allowedOverpay = min(self.payoutMaximumAmount, 100 * 100)

                if self.allowedOverpay > self.payoutMaximumAmount:
                    # cannot pay out all overpayment
                    pass  # do not limit payin, just warn the user, it's his problem

                self.state = "askLowPayout"
                logging.info("canPayout: {} with max. rest {} / to pay: {} / allowed overpay: {}".format(self.payoutMaximumAmount, self.payoutRemainingAmount, self.centsToPay, self.allowedOverpay))
        elif self.state == "askLowPayout":
            warningText = u""
            if self.payoutMaximumAmount < self.allowedOverpay or self.payoutRemainingAmount > 10 * 100:
                warningText = u"Der Automat hat gerade nur wenig Wechselgeld.\nBitte zahle passend oder spende dein Rückgeld!\n\n"
            elif self.payoutRemainingAmount > 20:
                warningText = u"Der Automat hat gerade nur wenig Kleingeld.\nBitte zahle passend oder spende dein Rückgeld!\n\n"

            if self.centsToPay + self.allowedOverpay > 200 * 100:
                warningText += u"Der bezahlte Betrag ist recht hoch.\nSolltest du später die Bezahlung abbrechen,\nwird dir womöglich nur ein Teil zurückgezahlt!"
            elif self.centsToPay + self.allowedOverpay > self.payoutMaximumAmount or self.payoutRemainingAmount > 50:
                warningText += u"Wenn du später die Bezahlung abbrichst,\nwird dir womöglich nur ein Teil zurückgezahlt!"

            if warningText == u"":
                self.label_status.setText(u"bitte warten....")
                self.state = "startAccepting"
            else:
                self.label_status.setText(warningText)
                self.pushButton_acceptLowPayout.setVisible(True)
                self.pushButton_cancel.setVisible(False)
        elif self.state == "startAccepting":
            self.label_status.setText(u"bitte warten.....")
            p.payin(self.centsToPay, self.centsToPay + self.allowedOverpay)
            self.state = "accept"
        elif self.state == "accept":
            self.pushButton_cancel.setVisible(True)
            if p.mode == "payinStop":
                # already hide "cancel" button when payin is stopping.
                # the user has already paid enough, so aborting is nonsense here.
                self.pushButton_cancel.setVisible(False)
            received = p.getFinalAmount()
            if received != None:
                self.centsReceived = received
                self.pushButton_cancel.setVisible(False)
                if received > self.centsToPay:
                    self.state = "askPayout"
                else:
                    self.centsPaidOut = 0
                    self.state = "finish"
        elif self.state == "askPayout":
            if self.centsToPay == 0:  # payment was aborted, payout return
                self.payoutReturn(self.centsReceived)
            else:
                self.label_status.setText(u'<html><p style="margin-bottom:20px;">Du würdest {} Rückgeld bekommen.<br>Möchtest du etwas davon spenden?</br><p style="font-size:14px;">Alle Spenden und Einnahmen werden ausschließlich für das FabLab verwendet.</p></html>'.format(PayupCashDialog.formatCent(self.centsReceived - self.centsToPay)))
                self.pushButton_return.setVisible(True)
                self.pushButton_donate.setVisible(True)
                self.showSuggestedDonations()
        elif self.state == "startPayout":  # this state is reached by payoutReturn()
            self.label_status.setText(u"starte Auszahlung...")
            self.label_payout_current_text.setEnabled(True)
            self.label_payout_current.setEnabled(True)
            assert self.centsReceived >= self.centsToPay
            p.payout(min(self.centsToPayOut, 200 * 100))  # HARDCODED: limit payouts to 200€ - here and in PaymentDeviceServer
            self.state = "payout"
        elif self.state == "payout":
            # poll until payout is finished
            paidOut = p.getFinalAmount()
            if paidOut != None:
                # payout finished
                paidOut = -paidOut
                assert paidOut >= 0
                self.centsPaidOut = paidOut
                self.state = "finish"
        elif self.state == "finish":
            totalPaid = self.centsReceived - self.centsPaidOut
            assert totalPaid >= self.centsToPay
            self.state = "finished"
        elif self.state == "finished":
            text = "<html><p>"
            if self.centsToPay == 0:  # payment aborted
                text += u"Die Bezahlung wurde abgebrochen."
            elif self.returnDonated:  # donated something
                text += u"Vielen Dank für deine Spende."
            else:  # did not donate
                text += u"Vielen Dank."
            text += "</p>"
            rest = self.centsReceived - self.centsPaidOut - self.centsToPay
            assert rest >= 0
            if self.centsPaidOut < self.centsToPayOut:
                text = text + u" <p>Ein Rest von {} konnte leider nicht zurückgezahlt werden.</p>".format(PayupCashDialog.formatCent(self.centsToPayOut - self.centsPaidOut))
            if self.centsToPay > 0:  # payment not aborted
                text += u"<p>Bitte das Aufräumen nicht vergessen!</p>"
            text = text + u'<p style="font-size:14px"> Sollte etwas nicht stimmen, benachrichtige bitte sofort einen Betreuer und melde dich bei kasse@fablab.fau.de.</p></html>'
            self.label_status.setText(text)
            self.pushButton_finish.setVisible(True)
            # only ask for receipt if something was paid
            # and we are not in the special case where receipt printing is enforced by the backend
            if self.centsReceived > self.centsPaidOut and self.centsToPay > 0:
                self.pushButton_receipt.setVisible(True)
                self.pushButton_finish.setText(u"Ich brauche keine Rechnung")
        else:
            raise Exception("Unknown state")

    def acceptLowPayoutWarning(self):
        if self.state != "askLowPayout":
            return
        self.pushButton_acceptLowPayout.setVisible(False)
        self.state = "startAccepting"

    def donateReturn(self):
        """user does not want money back, but donates it all"""
        self.payoutReturn(0)

    def payoutReturn(self, requestedPayback):
        """user requests amount X to be paid back"""
        if self.state != "askPayout":
            return
        assert requestedPayback <= self.centsReceived - self.centsToPay
        self.returnDonated = (requestedPayback < (self.centsReceived - self.centsToPay))
        self.pushButton_return.setVisible(False)
        self.pushButton_donate.setVisible(False)
        self.pushButton_donate1.setVisible(False)
        self.pushButton_donate2.setVisible(False)
        self.pushButton_donate3.setVisible(False)
        self.centsToPayOut = requestedPayback
        self.centsPaidOut = 0

        if requestedPayback > 0:
            self.state = "startPayout"
        else:
            self.state = "finish"

    def payoutReturnCompletely(self):
        """user wants all return money paid out, no donation"""
        self.payoutReturn(self.centsReceived - self.centsToPay)

    def getPaidAmount(self):
        return Decimal("0.01") * (self.centsReceived - self.centsPaidOut)

    def get_receipt_wanted(self):
        """
        did the user want to print a receipt?
        :rtype: boolean
        """
        return self.receipt_wanted

    def reject(self):
        p = self.parent().cashPayment
        if self.state != "accept":
            return
        p.abortPayin()
        self.centsToPay = 0

    def accept_and_print_receipt(self):
        self.receipt_wanted = True
        self.accept()

    def accept(self):
        """Button Finish: Exit the dialog if possible
        This is the only function from which PayupCashDialog can be closed (by the user).
        """
        if self.state != "finished":
            return
        if self.centsToPay == 0:  # payout aborted
            QtGui.QDialog.reject(self)
        else:
            QtGui.QDialog.accept(self)
        # cleanup the timer so that the python GC will clear this dialog when it is no longer needed.
        # otherwise for every dialog creation, a stale timer will be lying around and calling .update() (at least under
        # particular circumstances, probably depending on timing)
        # TODO is there a better approach for cleanup?
        self.timer.deleteLater()
