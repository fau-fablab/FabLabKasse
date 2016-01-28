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

from PyQt4 import QtCore, QtGui, QtNetwork
from .uic_generated.WebDialog import Ui_WebDialog


class WhiteListNetworkAccessManager(QtNetwork.QNetworkAccessManager):
    def __init__(self, parent=None):
        QtNetwork.QNetworkAccessManager.__init__(self, parent)
        
        self.allowed_urls = []
    
    def addAllowedUrlBase(self, url_base):
        self.allowed_urls.append(url_base)
        
    def createRequest(self, op, req, device=None):
        for u in self.allowed_urls:
            if req.url().toString().startsWith(u):
                # URL is ok
                return QtNetwork.QNetworkAccessManager.createRequest(self, op, req, device)
        
        # No allowed url matched
        print req.url().toString(), "DENIED"
        req.setUrl(QtCore.QUrl("forbidden://localhost/"))
        return QtNetwork.QNetworkAccessManager.createRequest(self, op, req, device)

class WebDialog(QtGui.QDialog, Ui_WebDialog):
    def __init__(self, parent):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        
        # Function keys
        self.pushButton_close.clicked.connect(self.close)
        self.pushButton_back.clicked.connect(self.back)
        
        # Set Whitelist Proxy
        self.proxy = WhiteListNetworkAccessManager(parent=self);
        self.webView.page().setNetworkAccessManager(self.proxy);

    def close(self):
        QtGui.QDialog.accept(self)

    def back(self):
        # FIXME make sure we can not go back to an empty page
        history = self.webView.page().history()
        
        if history.canGoBack():
        	history.back()
