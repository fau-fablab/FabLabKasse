#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Timo Voigt <timo@fablab.fau.de>
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

from qtpy import QtGui, QtWidgets
from .uic_generated.PayupManualDialog import Ui_PayupManualDialog
import re
from decimal import Decimal


class PayupManualDialog(QtWidgets.QDialog, Ui_PayupManualDialog):
    def __init__(self, parent, amount_total):
        QtWidgets.QDialog.__init__(self, parent)
        self.setupUi(self)
        self.amount_total = amount_total

        self.lineEdit.textEdited.connect(self.lineEditUpdated)
        self.lineEdit.cursorPositionChanged.connect(self.lineEditResetCursor)

        # Numpad
        self.pushButton_0.clicked.connect(lambda x: self.insertIntoLineEdit("0"))
        self.pushButton_comma.clicked.connect(lambda x: self.insertIntoLineEdit(","))
        self.pushButton_9.clicked.connect(lambda x: self.insertIntoLineEdit("9"))
        self.pushButton_8.clicked.connect(lambda x: self.insertIntoLineEdit("8"))
        self.pushButton_7.clicked.connect(lambda x: self.insertIntoLineEdit("7"))
        self.pushButton_6.clicked.connect(lambda x: self.insertIntoLineEdit("6"))
        self.pushButton_5.clicked.connect(lambda x: self.insertIntoLineEdit("5"))
        self.pushButton_4.clicked.connect(lambda x: self.insertIntoLineEdit("4"))
        self.pushButton_3.clicked.connect(lambda x: self.insertIntoLineEdit("3"))
        self.pushButton_2.clicked.connect(lambda x: self.insertIntoLineEdit("2"))
        self.pushButton_1.clicked.connect(lambda x: self.insertIntoLineEdit("1"))

        # Function keys
        self.pushButton_backspace.clicked.connect(self.backspaceLineEdit)
        self.pushButton_back.clicked.connect(self.reject)
        self.pushButton_done.clicked.connect(self.accept)

        # Display amount to be payed to user
        self.label_amount.setText(f"{self.amount_total:.2f} €".replace(".", ","))

        self.lineEdit.setText("0")
        self.lineEditUpdated()

    def insertIntoLineEdit(self, char):
        self.lineEdit.setFocus()
        text = self.lineEdit.text()[:-2]
        self.lineEdit.setText(text + char + " €")
        self.lineEditUpdated()

    def backspaceLineEdit(self):
        oldtext = self.lineEdit.text()
        if oldtext:
            self.lineEdit.setText(oldtext[:-3])
            self.lineEditUpdated()

    def lineEditUpdated(self):
        input = self.lineEdit.text()
        self.pushButton_comma.setEnabled(not ("," in input))

        # do not allow more than one comma
        while sum([int(x == ",") for x in input]) > 1:
            input = input[:-1]

        # Getting rid of all special characters (everything but numbers)
        newString = re.sub(r"[^0-9,]", "", str(input))

        if (not re.match("[0-9]", newString)) and (
            "," in newString
        ):  # convert ,24 -> 0,24
            newString = "0" + newString

        # only one leading zero
        while re.match(r"0[0-9]", newString):
            newString = newString[1:]

        # maximum two decimal places, remove the rest
        while re.match(r".*,[0-9][0-9][0-9]", newString):
            newString = newString[:-1]

        # re-add euro sign
        newString += " €"

        # Set correctly formated text, if anything changed (preserves cursor position)
        if newString != input:
            self.lineEdit.setText(newString)

    def lineEditResetCursor(self):
        self.lineEdit.setCursorPosition(len(self.lineEdit.text()) - 2)

    def getPaidAmount(self):
        t = self.lineEdit.text()[:-2]
        return Decimal(str(t).replace(",", "."))

    def reject(self):
        self.lineEdit.setText(
            "0,00 €"
        )  # make sure that getPaidAmount() returns 0 on abort
        QtWidgets.QDialog.reject(self)

    def accept(self):
        if self.getPaidAmount() == 0:
            QtWidgets.QMessageBox.critical(
                self,
                "Fehler",
                "Bitte gib ein, wieviel du bezahlt hast, oder breche die Bezahlung ab.",
                QtWidgets.QMessageBox.Ok,
                QtWidgets.QMessageBox.Ok,
            )
            return
        diff = self.getPaidAmount() - self.amount_total

        if diff < -0.009:
            reply = QtWidgets.QMessageBox.warning(
                self,
                "Message",
                "Bitte zahle mindestens den geforderten Betrag.",
                QtWidgets.QMessageBox.Ok,
            )
            return
        elif diff > min(5, self.amount_total * 2):
            reply = QtWidgets.QMessageBox.question(
                self,
                "Message",
                f'<html>Willst du wirklich <span style="color:#006600; font-weight:bold;">{float(diff):.02f} € spenden</span>?</html>',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )

            if reply == QtWidgets.QMessageBox.No:
                return

        QtWidgets.QDialog.accept(self)
