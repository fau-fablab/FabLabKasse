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

from __future__ import absolute_import
from qtpy import QtGui, QtWidgets
from .uic_generated.SelectClientDialog import Ui_SelectClientDialog
from .GUIHelper import connect_button_to_lineedit
import string
import re
from .KeyboardDialogCode import KeyboardDialog
from .. import scriptHelper
import random
from configparser import Error as ConfigParserError
import datetime


class InvalidClientException(Exception):
    """Client not found, wrong PIN or insufficient rights"""

    pass


class SelectClientDialog(QtWidgets.QDialog, Ui_SelectClientDialog):

    """GUI code for the dialog for selecting clients"""

    def __init__(self, parent, shopping_backend):
        """constructor for the ClientDialog

        :param parent: parent GUI dialog
        :type parent: QtWidgets.QDialog
        :param shopping_backend: current instance of ShoppingBackend
        :type shopping_backend: shopping.backend.abstract.AbstractShoppingBackend
        """
        QtWidgets.QDialog.__init__(self, parent)
        self.setupUi(self)

        self.shopping_backend = shopping_backend

        self.lineEdit_client.textEdited.connect(self.lineEditClientUpdate)
        self.lineEdit_pin.textEdited.connect(self.lineEditPINUpdate)
        self.comboBox_client.currentIndexChanged.connect(self.comboBoxClientUpdate)

        # Numpad
        # Connect buttons 0-9 with for loop
        for i in list(range(10)):
            connect_button_to_lineedit(self, i)

        # Function keys
        self.pushButton_backspace.clicked.connect(self.backspaceLineEdit)
        self.pushButton_back.clicked.connect(self.reject)
        self.pushButton_done.clicked.connect(self.accept)
        self.pushButton_register.clicked.connect(self.register)
        self.comboBox_client.setVisible(False)
        self.pushButton_showList.clicked.connect(self.showHideList)
        self._reload_clients()
        self.lineEditPINUpdate()

    def _reload_clients(self):
        # Load clients and populate comboBox_client
        self._clients = self.shopping_backend.list_clients()
        self.comboBox_client.clear()
        self.comboBox_client.addItem("")
        clientNames_sorted = sorted(
            [c.name for c in self._clients.values()], key=lambda x: x.lower()
        )
        for name in clientNames_sorted:
            self.comboBox_client.addItem(name)

        self.lineEdit_client.setFocus()

    def insertIntoLineEdit(self, char):
        if self.lineEdit_pin.hasFocus():
            self.lineEdit_pin.setText(self.lineEdit_pin.text() + char)
            self.lineEditPINUpdate()
        else:
            self.lineEdit_client.setText(self.lineEdit_client.text() + char)
            self.lineEditClientUpdate()

    def backspaceLineEdit(self):
        if self.lineEdit_pin.hasFocus():
            oldtext = self.lineEdit_pin.text()
            if oldtext:
                self.lineEdit_pin.setText(oldtext[:-1])
                self.lineEditPINUpdate()
        else:
            oldtext = self.lineEdit_client.text()
            if oldtext:
                self.lineEdit_client.setText(oldtext[:-1])
                self.lineEditClientUpdate()

    def lineEditClientUpdate(self):
        input = self.lineEdit_client.text()
        # Getting rid of all special characters (everything but numbers)
        newString = re.sub(r"[^0-9]", "", str(input))

        # remove leading zeros:
        newString = newString.lstrip("0")

        # Set correctly formated text, if anything changed (preserves cursor position)
        if newString != input:
            self.lineEdit_client.setText(newString)

        # Check if client number existst and switch to client in comboBox_client
        client = self.getClient()
        if client is None:
            self.comboBox_client.setCurrentIndex(0)
            return

        if str(self.comboBox_client.currentText()) == client.name:
            # client is already selected in combo box
            return

        idx = self.comboBox_client.findText(str(client.name))
        if idx != -1:
            self.comboBox_client.setCurrentIndex(idx)
        else:
            self.comboBox_client.setCurrentIndex(0)

    def comboBoxClientUpdate(self):
        name = str(self.comboBox_client.currentText())

        # TODO is there a nicer solution than get-by-name, e.g. storing indices somewhere?
        client = list(filter(lambda c: c.name == name, self._clients.values()))

        if client:
            # set lineEdit_client to client id
            self.lineEdit_client.setText(str(client[0].client_id))
        else:
            pass
            # do not clear the client textbox because otherwise you can not enter client number 123 if client 12 is disabled / nonexistent.
            # self.lineEdit_client.setText(u'')

    def lineEditPINUpdate(self):
        input = self.lineEdit_pin.text()
        # Getting rid of all special characters (everything but numbers)
        newString = re.sub(r"[^0-9]", "", str(input))

        # Set correctly formated text, if anything changed (preserves cursor position)
        if newString != input:
            self.lineEdit_pin.setText(newString)

        # Enable / Disable pushButton_done depending on pin length:
        if len(newString) == 4:
            self.pushButton_done.setEnabled(True)
        else:
            self.pushButton_done.setEnabled(False)

        # Show client info if entry is correct
        try:
            client = self.check_client_and_pin()
            self.label_clientName.setText(client.name)
            debt = client.get_debt()
            self.label_clientBalance.setText(self.shopping_backend.format_money(-debt))
            color = "#176b00" if debt <= 0 else "#6b0000"
            self.label_clientBalance.setStyleSheet("color:" + color + ";")
            self.label_for_balance.setText("Kontostand:")
        except InvalidClientException:
            self.label_clientName.setText("")
            self.label_clientBalance.setText("")
            self.label_for_balance.setText("")

    def getClient(self):
        try:
            return self._clients[int(self.lineEdit_client.text())]
        except (KeyError, ValueError):
            return None

    def getPIN(self):
        return str(self.lineEdit_pin.text())

    def check_client_and_pin(self, require_admin=False):
        """Check client number and PIN.
        Return client object if valid customer and PIN, else raise an InvalidClientException."""
        # Check client number
        kunde = self.getClient()
        if kunde is None:
            raise InvalidClientException("Diese Kundennummer gibt es nicht.")

        # Check PIN
        if not kunde.test_pin(str(self.lineEdit_pin.text())):
            raise InvalidClientException("Falsche PIN.")

        if require_admin and not kunde.is_admin():
            raise InvalidClientException(
                "Das angegebene Konto hat keine Administratorrechte.\n (Kommentar muss mit #admin# beginnen)"
            )
        return kunde

    def check_client_and_pin_with_gui_error(self, require_admin=False):
        """Check client number and PIN.
        If customer and PIN are valid, return the client object.
        Else, return False and show a GUI error message box.
        """
        try:
            return self.check_client_and_pin(require_admin)
        except InvalidClientException as e:
            msgBox = QtWidgets.QMessageBox(self)
            msgBox.setText(str(e))
            msgBox.exec_()
            return False

    def accept(self):
        kunde = self.check_client_and_pin_with_gui_error()
        if not kunde:
            return
        msgBox = QtWidgets.QMessageBox(self)
        msgBox.setText("Willst du auf das Konto " + kunde.name + " bezahlen?")
        msgBox.addButton(QtWidgets.QMessageBox.Cancel)
        msgBox.addButton(QtWidgets.QMessageBox.Ok)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Ok)
        msgBox.setEscapeButton(QtWidgets.QMessageBox.Cancel)
        if msgBox.exec_() != QtWidgets.QMessageBox.Ok:
            return
        QtWidgets.QDialog.accept(self)

    def reject(self):
        msgBox = QtWidgets.QMessageBox(self)
        msgBox.setText("Bezahlung abgebrochen.")
        msgBox.exec_()
        QtWidgets.QDialog.reject(self)

    def ask_admin_pin(self):
        return self.check_client_and_pin_with_gui_error(require_admin=True)

    def register(self):
        admin = self.ask_admin_pin()
        if not admin:
            return
        username = (
            KeyboardDialog.askText(
                "Kundenkennung (nur a-z 0-9 -) (mind. 5 Zeichen): vorname-nachname oder firma",
                parent=self,
            )
            or ""
        )
        username = username.replace("-", "_")
        username = username.replace(" ", "_")
        username = username.lower()
        if not re.match(r"^[a-z0-9_]{5,}$", username):
            msgBox = QtWidgets.QMessageBox(self)
            msgBox.setText("Nicht gültig. Abbruch.")
            msgBox.exec_()
            return
        email1 = KeyboardDialog.askText("Email Kunde - Teil VOR dem @", parent=self)
        if email1 is None:
            msgBox = QtWidgets.QMessageBox(self)
            msgBox.setText("abgebrochen.")
            msgBox.exec_()
            return
        email2 = KeyboardDialog.askText("Email Kunde - Teil NACH dem @", parent=self)
        if email2 is None or len(email2) < 3 or ("." not in email2):
            msgBox = QtWidgets.QMessageBox(self)
            msgBox.setText("ungültige Mail. Abbruch.")
            msgBox.exec_()
            return
        email = email1 + "@" + email2
        address = [""] * 4
        addressLabel = [
            "Name/Firma",
            "ggf Addresszusatz/Mitarbeiter",
            "Strasse Hausnr",
            "PLZ Ort",
        ]
        for i in [0, 1, 2, 3]:
            address[i] = KeyboardDialog.askText(
                "Anschrift Zeile " + str(i + 1) + "/4   " + addressLabel[i],
                parent=self,
            )
            if address[i] is None:
                msgBox = QtWidgets.QMessageBox(self)
                msgBox.setText("abgebrochen.")
                msgBox.exec_()
                return
            if (
                i in [0, 2] and len(address[i]) < 2
            ):  # name and street are mandatory. Other lines may be empty depending on how the user arranges the input.
                msgBox = QtWidgets.QMessageBox(self)
                msgBox.setText("keine Anschrift angegeben. Abbruch.")
                msgBox.exec_()
                return
        address_joined = "; ".join(address)
        comment = KeyboardDialog.askText("Kommentar", parent=self)
        if comment is None:
            msgBox = QtWidgets.QMessageBox(self)
            msgBox.setText("abgebrochen.")
            msgBox.exec_()
            return
        comment.replace(
            "#", ""
        )  # remove special characters used for admin-check in legacy_offline_kassenbuch.py
        comment = (
            comment
            + ";  registered by "
            + admin.name
            + " at "
            + str(datetime.datetime.now())
        )

        msgBox = QtWidgets.QMessageBox(self)
        msgBox.setText(
            "Bitte prüfe die Daten: \nKunde: "
            + username
            + "\n Email: "
            + email
            + "\nAnschrift:\n"
            + "\n".join(address)
            + "\n\nKommentar: "
            + comment
        )
        msgBox.addButton(QtWidgets.QMessageBox.Cancel)
        msgBox.addButton(QtWidgets.QMessageBox.Ok)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Ok)
        msgBox.setEscapeButton(QtWidgets.QMessageBox.Cancel)
        if msgBox.exec_() != QtWidgets.QMessageBox.Ok:
            return

        pin = random.randint(1, 9999)
        pin = f"{pin:04}"
        DEFAULT_DEBT_LIMIT = 300

        try:
            client_id = self.shopping_backend.add_client(
                username, email, address_joined, pin, comment, DEFAULT_DEBT_LIMIT
            )
        except Exception as e:
            msgBox = QtWidgets.QMessageBox(self)
            msgBox.setText("Fehler: " + str(e))
            msgBox.exec_()
            return
        msgBox = QtWidgets.QMessageBox(self)
        msgBox.setText(
            "Konto wurde angelegt. Bitte Kundenkarte ausfüllen und an Kunde geben:\n Konto "
            + str(username)
            + ", Kundennr "
            + str(client_id)
            + ", PIN "
            + str(pin)
            + "."
        )
        msgBox.exec_()
        self._reload_clients()
        self.lineEdit_client.setText(str(client_id))
        self.lineEdit_pin.setText(str(pin))
        self.accept()

    def showHideList(self):
        if not self.comboBox_client.isVisible():
            if not self.ask_admin_pin():
                return
        self.comboBox_client.setVisible(not self.comboBox_client.isVisible())
