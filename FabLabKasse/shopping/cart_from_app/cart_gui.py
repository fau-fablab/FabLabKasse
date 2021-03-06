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

"""GUI + logic for loading the cart from a mobile application."""

from PyQt4 import Qt, QtGui
from FabLabKasse.UI.LoadFromMobileAppDialogCode import LoadFromMobileAppDialog
from FabLabKasse.UI.CheckCartAfterImportDialogCode import CheckCartAfterImportDialog
from FabLabKasse.shopping.cart_from_app.cart_model import MobileAppCartModel
from FabLabKasse.shopping.cart_from_app.cart_model import InvalidCartJSONError, MissingAPIKeyError, MaximumNumRetriesException
from FabLabKasse.shopping.backend.abstract import ProductNotFound
import logging

# check that current cart is empty


class MobileAppCartGUI(object):

    """GUI + logic for loading the cart from a mobile application.
    It shows a QR Code as one-time-token for authentication.
    """

    def __init__(self, parent, cfg):
        """
        :param parent: GUI main object. used as Qt GUI parent and for accessing shoppingBackend

        :param cfg: The config parser from gui.py
        """
        self.random_code = ""
        appstore_url = None
        if cfg.has_option('mobile_app', 'appstore_url'):
            appstore_url = cfg.get('mobile_app', 'appstore_url')
        self.diag = LoadFromMobileAppDialog(parent, appstore_url)
        self.checkdiag = CheckCartAfterImportDialog(parent, parent.shoppingBackend)
        self.parent = parent

        self.cart = MobileAppCartModel(cfg)
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

        self.poll_timer.start()
        self.diag.finished.connect(lambda x: self.dialog_finished)
        self.diag.show()

    def pay_cart(self, cart):
        """ import given cart (from server's response), let the user pay it

        :param cart: cart received from server
        :type cart: see MobileAppCartModel.load()
        :rtype: bool
        :return: True if successfully paid, False otherwise.
        """
        # cart received
        new_order = self.parent.shoppingBackend.create_order()
        self.parent.shoppingBackend.set_current_order(new_order)

        try:
            for (product, quantity) in cart:
                self.parent.shoppingBackend.add_order_line(prod_id=product, qty=quantity)

            # check total sum
            self.checkdiag.update()
            okay = self.checkdiag.exec_()
            okay = okay == 1
        except ProductNotFound:
            logging.warning(u"error importing cart from app: product not found"
                            u"Might be caused by outdated cache in the app, "
                            u"the terminal or somewhere else.")
            QtGui.QMessageBox.information(self.parent, "Warenkorb", u"Entschuldigung, beim Import ist leider ein Fehler aufgetreten.\n (Produkt nicht gefunden)")
            okay = False

        if okay:
            # try payup
            successful = (self.parent.payup() is True)
        else:
            successful = False
        print "feedback successful = {0}".format(successful)
        self.cart.send_status_feedback(successful)
        if not successful:
            self.parent.shoppingBackend.delete_current_order()
            QtGui.QMessageBox.information(self.parent, "Info", u"Die Zahlung wurde abgebrochen.")
        return successful

    def poll(self):
        """query the server if a cart was stored"""
        if not self.diag.isVisible():
            # this should not happen, maybe a race-condition
            return
        logging.debug(u"polling for cart {0}".format(self.cart.cart_id))
        try:
            response = self.cart.load()
        except InvalidCartJSONError:
            QtGui.QMessageBox.warning(self.parent, "Warenkorb", u"Entschuldigung, beim Import ist leider ein Fehler aufgetreten.\n(Fehlerhafte Warenkorbdaten)")
            self.diag.reject()
            return
        except MaximumNumRetriesException:
            QtGui.QMessageBox.critical(self.parent, "Serverfehler", u"Entschuldigung, dieses Feature ist momentan nicht verfügbar.\n(Server nicht erreichbar oder Antwort fehlerhaft)")
            self.diag.reject()
            return
        except MissingAPIKeyError:
            QtGui.QMessageBox.critical(self.parent, "Konfigurationsfehler", u"Entschuldigung, dieses Feature ist momentan nicht verfügbar.\n(API-Key fehlt.)")
            self.diag.reject()
            return

        if not response:
            self.poll_timer.start()
            return
        logging.debug("received cart: {0}".format(response))
        self.diag.setEnabled(False)
        self.pay_cart(response)
        self.diag.reject()
        self.parent.updateOrder()

    def dialog_finished(self):
        """user somehow exited the dialog. clean up everything."""
        self.poll_timer.stop()
        self.diag.deleteLater()
        self.poll_timer.deleteLater()
        self.cart.deleteLater()
