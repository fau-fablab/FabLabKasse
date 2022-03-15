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

from PyQt4 import QtGui, QtCore
from .uic_generated.SelectClientDialog import Ui_SelectClientDialog
import re
from KeyboardDialogCode import KeyboardDialog
from .. import scriptHelper
import random
from ConfigParser import Error as ConfigParserError
import datetime


class SelectClientDialog(QtGui.QDialog, Ui_SelectClientDialog):

    """GUI code for the dialog for selecting clients"""

    def __init__(self, parent, shopping_backend):
        """constructor for the ClientDialog

        :param parent: parent GUI dialog
        :type parent: QtGui.QDialog
        :param shopping_backend: current instance of ShoppingBackend
        :type shopping_backend: shopping.backend.abstract.AbstractShoppingBackend
        """
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)

        self.shopping_backend = shopping_backend

        self.lineEdit_client.textEdited.connect(self.lineEditClientUpdate)
        self.lineEdit_pin.textEdited.connect(self.lineEditPINUpdate)
        self.comboBox_client.currentIndexChanged.connect(self.comboBoxClientUpdate)

        # Numpad
        self.pushButton_0.clicked.connect(lambda x: self.insertIntoLineEdit("0"))
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
        self.pushButton_register.clicked.connect(self.register)
        self.comboBox_client.setVisible(False)
        self.pushButton_showList.clicked.connect(self.showHideList)
        self._reload_clients()

    def _reload_clients(self):
        # Load clients and populate comboBox_client
        self._clients = self.shopping_backend.list_clients()
        self.comboBox_client.clear()
        self.comboBox_client.addItem(u"")
        clientNames_sorted = sorted(
            [c.name for c in self._clients.itervalues()], key=lambda x: x.lower()
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
        newString = re.sub(r"[^0-9]", "", unicode(input))

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

        if unicode(self.comboBox_client.currentText()) == client.name:
            # client is already selected in combo box
            return

        idx = self.comboBox_client.findText(QtCore.QString(client.name))
        if idx != -1:
            self.comboBox_client.setCurrentIndex(idx)
        else:
            self.comboBox_client.setCurrentIndex(0)

    def comboBoxClientUpdate(self):
        name = unicode(self.comboBox_client.currentText())

        # TODO is there a nicer solution than get-by-name, e.g. storing indices somewhere?
        client = filter(lambda c: c.name == name, self._clients.itervalues())

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
        newString = re.sub(r"[^0-9]", "", unicode(input))

        # Set correctly formated text, if anything changed (preserves cursor position)
        if newString != input:
            self.lineEdit_pin.setText(newString)

        # Enable / Disable pushButton_done depending on pin length:
        if len(newString) == 4:
            self.pushButton_done.setEnabled(True)
        else:
            self.pushButton_done.setEnabled(False)

    def getClient(self):
        try:
            return self._clients[int(self.lineEdit_client.text())]
        except (KeyError, ValueError):
            return None

    def getPIN(self):
        return str(self.lineEdit_pin.text())

    def check_client_and_pin(self, require_admin=False):
        """Check client number and PIN"""
        # Check client number
        kunde = self.getClient()
        if kunde is None:
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(
                u"Unter der Kundennummer konnte leider nichts gefunden werden."
            )
            msgBox.exec_()
            return False

        # Check PIN
        if not kunde.test_pin(str(self.lineEdit_pin.text())):
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"Falscher PIN oder Kundennummer.")
            msgBox.exec_()
            return False

        if require_admin and not kunde.is_admin():
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(
                u"Das angegebene Konto hat keine Administratorrechte.\n (Kommentar muss mit #admin# beginnen)"
            )
            msgBox.exec_()
            return False
        return kunde

    def accept(self):
        kunde = self.check_client_and_pin()
        if not kunde:
            return
        msgBox = QtGui.QMessageBox(self)
        msgBox.setText(u"Willst du auf das Konto " + kunde.name + " bezahlen?")
        msgBox.addButton(QtGui.QMessageBox.Cancel)
        msgBox.addButton(QtGui.QMessageBox.Ok)
        msgBox.setDefaultButton(QtGui.QMessageBox.Ok)
        msgBox.setEscapeButton(QtGui.QMessageBox.Cancel)
        if msgBox.exec_() != QtGui.QMessageBox.Ok:
            return
        QtGui.QDialog.accept(self)

    def reject(self):
        msgBox = QtGui.QMessageBox(self)
        msgBox.setText(u"Bezahlung abgebrochen.")
        msgBox.exec_()
        QtGui.QDialog.reject(self)

    def ask_admin_pin(self):
        return self.check_client_and_pin(require_admin=True)

    def register(self):
        admin = self.ask_admin_pin()
        if not admin:
            return
        username = (
            KeyboardDialog.askText(
                u"Kundenkennung (nur a-z 0-9 -) (mind. 5 Zeichen): vorname-nachname oder firma",
                parent=self,
            )
            or ""
        )
        username = username.replace("-", "_")
        username = username.replace(" ", "_")
        username = username.lower()
        if not re.match(r"^[a-z0-9_]{5,}$", username):
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"Nicht gültig. Abbruch.")
            msgBox.exec_()
            return
        email1 = KeyboardDialog.askText(u"Email Kunde - Teil VOR dem @", parent=self)
        if email1 is None:
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"abgebrochen.")
            msgBox.exec_()
            return
        email2 = KeyboardDialog.askText(u"Email Kunde - Teil NACH dem @", parent=self)
        if email2 is None or len(email2) < 3 or ("." not in email2):
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"ungültige Mail. Abbruch.")
            msgBox.exec_()
            return
        email = email1 + "@" + email2
        address = [""] * 4
        addressLabel = [
            u"Name/Firma",
            u"ggf Addresszusatz/Mitarbeiter",
            u"Strasse Hausnr",
            u"PLZ Ort",
        ]
        for i in [0, 1, 2, 3]:
            address[i] = KeyboardDialog.askText(
                u"Anschrift Zeile " + str(i + 1) + "/4   " + addressLabel[i],
                parent=self,
            )
            if address[i] is None:
                msgBox = QtGui.QMessageBox(self)
                msgBox.setText(u"abgebrochen.")
                msgBox.exec_()
                return
            if (
                i in [0, 2] and len(address[i]) < 2
            ):  # name and street are mandatory. Other lines may be empty depending on how the user arranges the input.
                msgBox = QtGui.QMessageBox(self)
                msgBox.setText(u"keine Anschrift angegeben. Abbruch.")
                msgBox.exec_()
                return
        address_joined = "; ".join(address)
        comment = KeyboardDialog.askText(u"Kommentar", parent=self)
        if comment is None:
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"abgebrochen.")
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

        msgBox = QtGui.QMessageBox(self)
        msgBox.setText(
            u"Bitte prüfe die Daten: \nKunde: "
            + username
            + u"\n Email: "
            + email
            + u"\nAnschrift:\n"
            + u"\n".join(address)
            + u"\n\nKommentar: "
            + comment
        )
        msgBox.addButton(QtGui.QMessageBox.Cancel)
        msgBox.addButton(QtGui.QMessageBox.Ok)
        msgBox.setDefaultButton(QtGui.QMessageBox.Ok)
        msgBox.setEscapeButton(QtGui.QMessageBox.Cancel)
        if msgBox.exec_() != QtGui.QMessageBox.Ok:
            return

        pin = random.randint(1, 9999)
        pin = "{0:04}".format(pin)
        DEFAULT_DEBT_LIMIT = 300

        try:
            client_id = self.shopping_backend.add_client(
                username, email, address_joined, pin, comment, DEFAULT_DEBT_LIMIT
            )
        except Exception as e:
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"Fehler: " + str(e))
            msgBox.exec_()
            return
        msgBox = QtGui.QMessageBox(self)
        msgBox.setText(
            u"Konto wurde angelegt. Bitte Kundenkarte ausfüllen und an Kunde geben:\n Konto "
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
