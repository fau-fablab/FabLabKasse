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

"Model for loading the cart from a mobile application"

import requests
import logging
# from FabLabKasse.shopping
from FabLabKasse.shopping.backend.abstract import float_to_decimal
import simplejson
import random
import os
from PyQt4.QtCore import pyqtSignal, QObject

# TODO self-signed ssl , we need HTTPS :(


class MobileAppCartModel(QObject):

    "loads a cart from a mobile application"
    cart_id_changed = pyqtSignal(unicode)

    def __init__(self, config):
        """
        config: the config parser from gui.py
        """
        QObject.__init__(self)
        self.cfg = config
        self._server_url = None
        self._timeout = None
        self._cart_id = None

    def generate_random_id(self):
        """set random_id to a securely generated random value

        Debugging: set environment variable MOBILE_APP_FORCE_CODE=12345 to force a specific code"""
        rng = random.SystemRandom()
        self.cart_id = os.environ.get("MOBILE_APP_FORCE_CODE", str(rng.randint(0, 2 ** 63))).strip()

    @property
    def server_url(self):
        """
        Return the appservers query url
        """
        if self._server_url == None:
            self._server_url = self.cfg.get('mobile_app', 'server_url')
        return self._server_url

    @property
    def timeout(self):
        """
        Timeout for single requests
        """
        if self._timeout == None:
            if self.cfg.has_option('mobile_app', 'timeout'):
                self._timeout = self.cfg.getint('mobile_app', 'timeout')
            else:
                self._timeout = 10
                logging.info(u"using default timeout value '10' as it wasn't set in the config")
        return self._timeout

    @property
    def cart_id(self):
        """the random string (authentication token, cart identifier) that is shown to the client as a QR Code

        emits cart_id_changed(value) on change
        """
        return self._cart_id

    @cart_id.setter
    def cart_id(self, value):
        "update cart_id"
        assert isinstance(value, basestring)
        self._cart_id = value
        self.cart_id_changed.emit(value)

    def load(self):
        """Load cart from server

        Returns:
            list of tuples (product_code, quantity)
            or False

        If the cart id seems already used, the random code is updated. please connect to the cart_id_changed() signal and update the shown QR code.
        """
        if self.cart_id == None:
            self.generate_random_id()
            return False
        try:
            req = requests.get(self.server_url + self.cart_id, timeout=self.timeout)  # , HTTPAdapter(max_retries=5))
            # TODO retries
        except requests.exceptions.RequestException:
            return False
        if req.text == "":
            return False
        try:
            data = req.json()
        except simplejson.JSONDecodeError:
            return False
        logging.debug(u"received cart: {}".format(repr(data)))
        if data["status"] != "PENDING":
            logging.info("rejecting cart with status {}. Regenerating random id.".format(data["status"]))
            self.generate_random_id()
            return False
        cart = []
        for entry in data["items"]:
            try:
                item = (int(entry["productId"]), float_to_decimal(entry["amount"], 3))
                cart.append(item)
            except ValueError:
                # TODO notify user of import error
                return False
        return cart

    def send_status_feedback(self, success):
        """send response from server

        Args:
           success (boolean): was the payment successful (True) or canceled (False)

        Returns:
            nothing

        Raises:
           nothing (hopefully)
        """
        if success:
            status = "paid"
        else:
            status = "cancelled"
        try:
            req = requests.post(self.server_url + status + "/" + self.cart_id, timeout=self.timeout)  # , HTTPAdapter(max_retries=5))
            logging.debug("response: {}".format(repr(req.text)))
        except IOError:
            logging.warn("sending cart feedback failed")
            # TODO what do we do on failure?


# if __name__ == "__main__":
#    print getCart(str(1234))
#    print setCartFeedback(str(1234),False)
