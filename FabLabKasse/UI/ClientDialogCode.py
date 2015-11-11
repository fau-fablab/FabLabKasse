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


class SelectClientDialog(QtGui.QDialog, Ui_SelectClientDialog):
    """ GUI code for the dialog for selecting clients """

    def __init__(self, parent, shopping_backend):
        """ constructor for the ClientDialog
        :param parent: parent GUI dialog
        :type parent: QtGui.QDialog
        :param shopping_backend: current instance of ShoppingBackend
        :type shopping_backend: shopping.backend.abstract.AbstractShoppingBackend
        """
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)

        self.lineEdit_client.textEdited.connect(self.lineEditClientUpdate)
        self.lineEdit_pin.textEdited.connect(self.lineEditPINUpdate)
        self.comboBox_client.currentIndexChanged.connect(self.comboBoxClientUpdate)

        # Numpad
        self.pushButton_0.clicked.connect(lambda x: self.insertIntoLineEdit('0'))
        self.pushButton_9.clicked.connect(lambda x: self.insertIntoLineEdit('9'))
        self.pushButton_8.clicked.connect(lambda x: self.insertIntoLineEdit('8'))
        self.pushButton_7.clicked.connect(lambda x: self.insertIntoLineEdit('7'))
        self.pushButton_6.clicked.connect(lambda x: self.insertIntoLineEdit('6'))
        self.pushButton_5.clicked.connect(lambda x: self.insertIntoLineEdit('5'))
        self.pushButton_4.clicked.connect(lambda x: self.insertIntoLineEdit('4'))
        self.pushButton_3.clicked.connect(lambda x: self.insertIntoLineEdit('3'))
        self.pushButton_2.clicked.connect(lambda x: self.insertIntoLineEdit('2'))
        self.pushButton_1.clicked.connect(lambda x: self.insertIntoLineEdit('1'))

        # Function keys
        self.pushButton_backspace.clicked.connect(self.backspaceLineEdit)
        self.pushButton_back.clicked.connect(self.reject)
        self.pushButton_done.clicked.connect(self.accept)

        # Load clients and populate comboBox_client
        self._clients = shopping_backend.list_clients()
        # NOTE: clients are never updated between this call and closing the dialog
        self.comboBox_client.clear()
        self.comboBox_client.addItem(u'')
        for c in self._clients.itervalues():
            self.comboBox_client.addItem(c.name)

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
        newString = re.sub(r'[^0-9]', '', unicode(input))

        # remove leading zeros:
        newString = newString.lstrip('0')

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
            self.lineEdit_client.setText(u'')

    def lineEditPINUpdate(self):
        input = self.lineEdit_pin.text()
        # Getting rid of all special characters (everything but numbers)
        newString = re.sub(r'[^0-9]', '', unicode(input))

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

    def accept(self):
        # Check client number
        kunde = self.getClient()
        if kunde is None:
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"Unter der Kundennummer konnte leider nichts gefunden werden.")
            msgBox.exec_()
            return

        # Check PIN
        if kunde.test_pin(str(self.lineEdit_pin.text())):
            QtGui.QDialog.accept(self)
        else:
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"Falscher PIN oder Kundennummer.")
            msgBox.exec_()

    def reject(self):
        msgBox = QtGui.QMessageBox(self)
        msgBox.setText(u"Bezahlung abgebrochen.")
        msgBox.exec_()
        QtGui.QDialog.reject(self)
