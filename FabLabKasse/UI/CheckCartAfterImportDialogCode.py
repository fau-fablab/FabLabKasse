#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Patrick Kanzler <patrick.kanzler@fablab.fau.de
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
from FabLabKasse.UI.uic_generated.CheckCartAfterImportDialog import Ui_AppWarenkorb
from FabLabKasse.libs.flickcharm import FlickCharm


class CheckCartAfterImportDialog(QtGui.QDialog, Ui_AppWarenkorb):
    """dialog for showing the imported cart during app-import
    """

    def __init__(self, parent, shoppingBackend):
        """ constructor

        :param parent: parent dialog
        :param shoppingBackend: instance of a shoppingBackend
        :type shoppingBackend: FabLabKasse.shopping.backend.abstract.AbstractShoppingBackend
        """
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        # maximize window - WORKAROUND because showMaximized() doesn't work
        # when a default geometry is set in the Qt designer file
        QtCore.QTimer.singleShot(0, lambda: self.setWindowState(QtCore.Qt.WindowMaximized))
        self.shoppingBackend = shoppingBackend
        self.charm = FlickCharm()
        self.charm.activateOn(self.table_order, disableScrollbars=False)

    def update(self):
        """update table with current order lines"""
        self.table_order.update_cart(self.shoppingBackend)

        sumText = self.shoppingBackend.format_money(self.shoppingBackend.get_current_total())
        self.sumText.setText(u"Gesamtsumme {}".format(sumText))
