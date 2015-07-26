#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Timo Voigt <timo@fablab.fau.de>
#                     and others
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

"""dialog for loading the cart from a mobile application.
It shows a QR Code as one-time-token for authentication."""

from PyQt4 import QtGui, QtCore
from FabLabKasse.UI.uic_generated.LoadFromMobileAppDialog import Ui_LoadFromMobileAppDialog
import qrcode
import StringIO


def set_layout_items_visible(layout, visible):
    """
    hide/show all widgets in a QLayout

    :type layout: QtGui.QLayout

    :type visible: boolean
    """
    for i in range(layout.count()):
        if isinstance(layout.itemAt(i), QtGui.QLayout):
            # recurse to sub-layout
            set_layout_items_visible(layout.itemAt(i), visible)
        widget = layout.itemAt(i).widget()
        if widget is not None:
            widget.setVisible(visible)


class LoadFromMobileAppDialog(QtGui.QDialog, Ui_LoadFromMobileAppDialog):

    """dialog for loading the cart from a mobile application.
    It shows a QR Code as one-time-token for authentication."""

    def __init__(self, parent, app_url):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        # maximize window - WORKAROUND because showMaximized() doesn't work
        # when a default geometry is set in the Qt designer file
        QtCore.QTimer.singleShot(0, lambda: self.setWindowState(QtCore.Qt.WindowMaximized))
        set_layout_items_visible(self.verticalLayout_app_download, False)
        self.pushButton_app.clicked.connect(self._show_app_download)
        if app_url == None:
            self.pushButton_app.setVisible(False)
        else:
            LoadFromMobileAppDialog.set_qr_label(self.label_qr_app, app_url)
            self.label_qr_app_url.setText(app_url)

    def _show_app_download(self):
        """hide the random QR code, show the one for the appstore"""
        set_layout_items_visible(self.verticalLayout_qr, False)
        set_layout_items_visible(self.verticalLayout_app_download, True)
        self.buttonBox.setStandardButtons(QtGui.QDialogButtonBox.Ok)

    def set_random_code(self, random_code):
        """update the QR code showing the cart id"""
        LoadFromMobileAppDialog.set_qr_label(self.label_qr_random, random_code)

    @staticmethod
    def set_qr_label(label, text):
        """
        set qrcode image on QLabel

        :param label: QLabel
        :param text: text for the QR code
        """
        buf = StringIO.StringIO()
        img = qrcode.make(text)
        img.save(buf, "PNG")
        label.setText("")
        qt_pixmap = QtGui.QPixmap()
        qt_pixmap.loadFromData(buf.getvalue(), "PNG")
        label.setPixmap(qt_pixmap)
