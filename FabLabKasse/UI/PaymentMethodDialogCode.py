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

from PyQt4 import Qt, QtGui
from .uic_generated.PaymentMethodDialog import Ui_PaymentMethodDialog
from ..shopping.payment_methods import PAYMENT_METHODS
import functools


class PaymentMethodDialog(QtGui.QDialog, Ui_PaymentMethodDialog):

    def __init__(self, parent, cfg, amount):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        self.cfg = cfg

        self.method = None

        # Clear all method buttons
        for i in range(self.layout_methods.count()):
            self.layout_methods.itemAt(i).widget().setVisible(False)
            self.layout_methods.itemAt(i).widget().deleteLater()

        # select available methods (according to config file)
        for method in PAYMENT_METHODS:
            button = Qt.QPushButton(method.get_title())
            button.setSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Expanding)
            button.clicked.connect(functools.partial(self.acceptAndSetMethod, method))  # cannot use lambda here because variable method will change in next iteration... python is counterintuitive here....
            button.setVisible(method.is_enabled(self.cfg))
            self.layout_methods.addWidget(button)

        self.label_betrag.setText(self.parent().shoppingBackend.format_money(amount))
        self.update()

    def acceptAndSetMethod(self, method):
        self.method = method
        self.accept()

    def getSelectedMethodInstance(self, parent, shopping_backend, amount_to_pay):
        return self.method(parent, shopping_backend, amount_to_pay, self.cfg)
