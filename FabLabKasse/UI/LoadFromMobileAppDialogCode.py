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

from PyQt4 import QtGui
from uic_generated.LoadFromMobileAppDialog import Ui_LoadFromMobileAppDialog
import qrcode
import StringIO

class LoadFromMobileAppDialog(QtGui.QDialog, Ui_LoadFromMobileAppDialog):
    def __init__(self, parent, random_code, app_url):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        LoadFromMobileAppDialog.set_qr_label(self.label__qr_app, app_url)
        LoadFromMobileAppDialog.set_qr_label(self.label_qr_random, random_code)
    

    @staticmethod
    def set_qr_label(label, text):
        """
        set qrcode image on QLabel
        
        @param label: QLabel
        @param text: text for the QR code
        """
        buf = StringIO.StringIO()
        img = qrcode.make(text)
        img.save(buf, "PNG")
        label.setText("")
        qt_pixmap = QtGui.QPixmap()
        qt_pixmap.loadFromData(buf.getvalue(), "PNG")
        label.setPixmap(qt_pixmap)
    
    