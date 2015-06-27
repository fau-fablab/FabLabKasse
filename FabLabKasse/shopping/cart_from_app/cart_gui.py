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

"GUI + logic for loading the cart from a mobile application."

from PyQt4 import Qt, QtGui
from FabLabKasse.UI.LoadFromMobileAppDialogCode import LoadFromMobileAppDialog
from FabLabKasse.shopping.cart_from_app.cart_model import MobileAppCartModel
import logging

# check that current cart is empty


class MobileAppCartGUI(object):

    "GUI + logic for loading the cart from a mobile application. It shows a QR Code as one-time-token for authentication."

    def __init__(self, parent, appstore_url):
        """
        parent: GUI main object. used as Qt GUI parent and for accessing shoppingBackend

        appstore_url: URL for QRcode that leads to the app installation
        """
        self.random_code = ""
        self.diag = LoadFromMobileAppDialog(parent, appstore_url)
        self.parent = parent

        self.cart = MobileAppCartModel()
        self.cart.cart_id_changed.connect(self.diag.set_random_code)

        self.poll_timer = Qt.QTimer(self.parent)
        self.poll_timer.setSingleShot(True)
        self.poll_timer.setInterval(1000)
        self.poll_timer.timeout.connect(self.poll)

    def execute(self):
        """show dialog with QRcodes, process order and payment, cleanup afterwards.

        This method blocks until everything is done.
        """
        if self.parent.shoppingBackend.get_current_order() != None:
            if self.parent.shoppingBackend.get_current_total() != 0:
                QtGui.QMessageBox.warning(self.parent, "Fehler",
                                          u"Im Warenkorb am Automat liegen Produkte.\n" +
                                          u"Bitte zahle zuerst diese Produkte oder lösche sie aus dem Warenkorb.\n")
                return
            self.parent.shoppingBackend.delete_current_order()
            self.parent.shoppingBackend.set_current_order(None)

        self.poll_timer.start()
        self.diag.finished.connect(lambda x: self.dialog_finished)
        self.diag.show()

    def pay_cart(self, cart):
        """ import given cart (from server's response), let the user pay it

        @param cart: response from server
        @rtype: bool
        @return: True if successfully paid, False otherwise.
        """
        # cart received
        new_order = self.parent.shoppingBackend.create_order()
        self.parent.shoppingBackend.set_current_order(new_order)

        for (product, quantity) in cart:
            self.parent.shoppingBackend.add_order_line(prod_id=product, qty=quantity, comment="")

        # check total sum
        # TODO this is ugly and doesn't show everything when there are too many articles
        # make a nice GUI out of it
        infotext = u"Stimmt der Warenkorb? \n"
        order_lines = self.parent.shoppingBackend.get_order_lines()
        for line in order_lines[0:10]:
            infotext += unicode(line) + "\n"
        if len(order_lines) > 10:
            infotext += "... und {} weitere Posten ...\n".format(len(order_lines) - 10)
        infotext += u"Gesamt: {}\n".format(self.parent.shoppingBackend.format_money(self.parent.shoppingBackend.get_current_total()))
        okay = QtGui.QMessageBox.information(self.parent, "Warenkorb", infotext, QtGui.QMessageBox.Cancel | QtGui.QMessageBox.Yes)
        okay = okay == QtGui.QMessageBox.Yes
        if okay:
            # try payup
            successful = (self.parent.payup() == True)
        else:
            successful = False
        print "feedback successful = {}".format(successful)
        self.cart.send_status_feedback(successful)
        if not successful:
            self.parent.shoppingBackend.delete_current_order()
            self.parent.shoppingBackend.set_current_order(None)
            QtGui.QMessageBox.information(self.parent, "Info", u"Die Zahlung wurde abgebrochen.")
        return successful

    def poll(self):
        "query the server if a cart was stored"
        if not self.diag.isVisible():
            # this should not happen, maybe a race-condition
            return
        logging.debug(u"polling for cart {}".format(self.cart.cart_id))
        response = self.cart.load()
        if not response:
            self.poll_timer.start()
            return
        logging.debug("received cart: {}".format(response))
        self.diag.setEnabled(False)
        self.pay_cart(response)
        self.diag.reject()
        self.parent.updateOrder()

    def dialog_finished(self):
        "user somehow exited the dialog. clean up everything."
        self.poll_timer.stop()
        self.diag.deleteLater()
        self.poll_timer.deleteLater()
        self.cart.deleteLater()
