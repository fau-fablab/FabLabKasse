#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Patrick Kanzler <patrick.kanzler@fablab.fau.de>
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

"""Model for loading the cart from a mobile application"""

import requests
import logging
# from FabLabKasse.shopping
from FabLabKasse.shopping.backend.abstract import float_to_decimal
import simplejson
import random
import os
from PyQt4.QtCore import pyqtSignal, QObject
import unittest
from decimal import Decimal
# TODO self-signed ssl , we need HTTPS :(


class InvalidCartJSONError(Exception):

    """Cart JSON object received was wrong."""

    def __init__(self, text=None, property_name=None, value=None):
        """
        Cart JSON object received was wrong.

        :param text: reason
        :param property_name: use property_name and value if an unexpected value for a property occurs. The infotext is then filled automatically.
        :param value: see property_name
        """
        if not text:
            text = u""
        text = u"Invalid Cart: " + text
        if property_name:
            text += u"Property {} has unexpected value: {}".format(property_name, repr(value))
        Exception.__init__(self, text)


class MobileAppCartModel(QObject):

    """loads a cart from a mobile application"""

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
        if self._server_url is None:
            self._server_url = self.cfg.get('mobile_app', 'server_url')
        return self._server_url

    @property
    def timeout(self):
        """
        Timeout for single requests
        """
        if self._timeout is None:
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
        """update cart_id"""
        assert isinstance(value, basestring)
        self._cart_id = value
        self.cart_id_changed.emit(value)

    def load(self):
        """Load cart from server and return it, or ``False`` if no cart has
        been uploaded yet for the current id or if an error occured

        :return:  list of tuples (product_code, quantity) or False
        :rtype: list[(int, Decimal)] | bool

        :raise: InvalidCartJSONError
        if an invalid cart response was received from the server, (otherwise just returns False in normal cases of error)

        If the cart id seems already used, the random cart id is updated. please connect to the cart_id_changed() signal
        and update the shown QR code.
        """
        if self.cart_id is None:
            self.generate_random_id()
            return False
        try:
            req = requests.get(self.server_url + self.cart_id, timeout=self.timeout)  # , HTTPAdapter(max_retries=5))
            # TODO retries
            req.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            logging.debug(u"app-checkout: app server responded with HTTP error {}".format(exc))
            return False
        except requests.exceptions.RequestException as exc:
            logging.debug(u"app-checkout: general error in HTTP request: {}".format(exc))
            return False
        if req.text == "":
            # logging.debug("app-checkout: empty response from server")
            # no logging here since this is a standard use-case
            return False
        try:
            return self._decode_json_cart(req.text)
        except InvalidCartJSONError, exception:
            logging.warning("Cannot decode Cart JSON: {}".format(exception))
            raise

    def _decode_json_cart(self, json):
        """decode JSON data containing the cart

        :param json: JSON encoded data
        :type json: unicode
        :raise: InvalidCartJSONError
        """
        try:
            data = simplejson.loads(json)
        except simplejson.JSONDecodeError:
            raise InvalidCartJSONError("app-checkout: JSONDecodeError")
        logging.debug(u"received cart: {}".format(repr(data)))
        try:
            if data["status"] != "PENDING":
                raise InvalidCartJSONError(property_name="status", value=data["status"])
            if unicode(data["cartCode"]) != self.cart_id:
                raise InvalidCartJSONError(property_name="cartCode", value=data["cartCode"])
            cart = []
            for entry in data["items"]:
                if not isinstance(entry, dict):
                    raise InvalidCartJSONError(property_name="items", value=data["items"])
                item = (int(entry["productId"]), float_to_decimal(float(entry["amount"]), 3))
                if item[1] < 0:
                    raise InvalidCartJSONError(property_name="item.amount", value=item[1])
                cart.append(item)
        except KeyError:
            raise InvalidCartJSONError("a required key is missing in JSON")
        except ValueError:
            raise InvalidCartJSONError("invalid field value in JSON (probably amount or productId)")
        return cart

    def send_status_feedback(self, success):
        """send response to server

        :param success: was the payment successful (True) or canceled (False)
        :type success: boolean

        :return: None
        :raise: None (hopefully)
        """
        if success:
            status = "paid"
        else:
            status = "cancelled"
        try:
            req = requests.post(self.server_url + status + "/" + self.cart_id, timeout=self.timeout)  # , HTTPAdapter(max_retries=5))
            logging.debug("response: {}".format(repr(req.text)))
            req.raise_for_status()
        except IOError:
            logging.warn("sending cart feedback failed")
            # TODO what do we do on failure?


class MobileAppCartModelTest(unittest.TestCase):

    """ Test MobileAppCartModel """

    def test_decode_json_cart(self):
        """unittest: load cart from JSON.

        Test normal use and various input format errors
        """
        def prepare():
            """
            return a list of three objects for MobileAppCartModel._decode_json_cart():

            - model: MobileAppCartModel
            - valid_data: data for json encoding
            - valid_cart: decoded cart like it should be output by _decode_json_cart()
            """
            model = MobileAppCartModel(None)
            model.generate_random_id()
            valid_data = {}
            valid_data["cartCode"] = model.cart_id
            valid_data["items"] = []

            product = {}
            product["id"] = 44
            product["productId"] = "9011"
            product["amount"] = "5."

            valid_data["items"].append(product)
            valid_data["status"] = "PENDING"
            valid_data["pushId"] = "000"
            valid_data["sendToServer"] = 12398234781237

            valid_cart = [(int(product["productId"]), Decimal(5))]

            return [model, valid_data, valid_cart]

        # test valid cart
        [model, data, valid_cart] = prepare()
        self.assertEqual(model._decode_json_cart(simplejson.dumps(data)), valid_cart)

        # test deleted fields and wrong datatype/value
        # (pushID and sendToServer are unused and therefore ignored)
        for field in ["status", "items", "cartCode"]:
            [model, data, _] = prepare()
            with self.assertRaises(InvalidCartJSONError):
                del data[field]
                model._decode_json_cart(simplejson.dumps(data))

            [model, data, _] = prepare()
            with self.assertRaises(InvalidCartJSONError):
                data[field] = "fooo"
                model._decode_json_cart(simplejson.dumps(data))

        # wrong datatype inside items list
        [model, data, _] = prepare()
        with self.assertRaises(InvalidCartJSONError):
            data["items"][0] = "fooo"
            model._decode_json_cart(simplejson.dumps(data))

        # test missing fields (productId, amount) in item, or wrong datatype
        # (id is ignored)
        for field in ["amount", "productId"]:
            [model, data, _] = prepare()
            with self.assertRaises(InvalidCartJSONError):
                del data["items"][0][field]
                model._decode_json_cart(simplejson.dumps(data))

        # invalid values for amount
        for invalid_amount_value in ["-5", "1.241234234232343242342234", "1e20"]:
            [model, data, _] = prepare()
            data["items"][0]["amount"] = invalid_amount_value
            with self.assertRaises(InvalidCartJSONError):
                model._decode_json_cart(simplejson.dumps(data))

        # invalid values for product id
        for invalid_id_value in ["1.5", ""]:
            [model, data, _] = prepare()
            data["items"][0]["productId"] = invalid_id_value
            with self.assertRaises(InvalidCartJSONError):
                model._decode_json_cart(simplejson.dumps(data))


if __name__ == "__main__":
    unittest.main()
