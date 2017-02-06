#!/usr/bin/env python3
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
from PyQt4.QtCore import pyqtSignal, QObject
import unittest
from decimal import Decimal
from tempfile import NamedTemporaryFile
from base64 import b64decode


class InvalidCartJSONError(Exception):

    """Cart JSON object received was wrong."""

    def __init__(self, text=None, property_name=None, value=None):
        """
        Cart JSON object received was wrong.

        :param text: reason
        :param property_name: use property_name and value if an unexpected value for a property occurs.
                            The infotext is then filled automatically.
        :param value: see property_name
        """
        if not text:
            text = ""
        text = "Invalid Cart: " + text
        if property_name:
            text += "Property {0} has unexpected value: {1}".format(property_name, repr(value))
        Exception.__init__(self, text)


class MissingAPIKeyError(Exception):

    """No API key has been specified, cannot recover."""

    def __init__(self):
        """
        The Appserver needs an API key for communication without one, no communication is possible.
        """
        text = "No API key found for the APP-Server in config (key server_api_key)."
        logging.error(text)
        Exception.__init__(self, text)


class MaximumNumRetriesException(Exception):

    """The threshold number of retries has been passed"""

    def __init__(self):
        """
        After num_retries is the appserver still not reachable.
        """
        text = "The Appserver is after num_retries retries (see config) still not reachable."
        logging.error(text)
        Exception.__init__(self, text)


class MobileAppCartModel(QObject):

    """loads a cart from a mobile application"""

    cart_id_changed = pyqtSignal(str)

    def __init__(self, config):
        """
        :param config: the config parser from gui.py
        """
        QObject.__init__(self)
        self.cfg = config
        if config.has_option('mobile_app', 'ssl_cert'):
            self._ssl_cert = str(config.get('mobile_app', 'ssl_cert'))
            if self._ssl_cert.startswith("base64://"):
                # write contents of base64 to temporary file
                f = NamedTemporaryFile(delete=False)
                f.write(b64decode(self._ssl_cert[len("base64://"):]))
                self._ssl_cert = f.name
                f.close()
        else:
            self._ssl_cert = None
        self._server_url = None
        self._api_key = None
        self._timeout = None
        self._cart_id = None
        self._num_retries = None
        self._retries_counter = 0

    def _get_cart_id(self):
        """
        query app server for current cart id

        :raise: requests.exceptions.HTTPError
        :raise: requests.exceptions.RequestException
        :rtype: None
        """
        get_params = {'password': self.api_key}
        req = requests.get(self.server_url + "createCode", params=get_params,
                           timeout=self.timeout, verify=self._ssl_cert)
        req.raise_for_status()
        if req.text == "":
            return
        self.cart_id = req.text.strip()

    @property
    def server_url(self):
        """
        Return the appservers query url
        """
        if self._server_url is None:
            self._server_url = self.cfg.get('mobile_app', 'server_url')
        return self._server_url

    @property
    def api_key(self):
        """
        Return the appservers api key

        :raise: MissingAPIKeyError
        """
        if self._api_key is None:
            if self.cfg.has_option('mobile_app', 'server_api_key'):
                self._api_key = self.cfg.get('mobile_app', 'server_api_key')
            else:
                raise MissingAPIKeyError()

        return self._api_key

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
                logging.info("using default timeout value '10' as it wasn't set in the config")
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
        assert isinstance(value, str)
        self._cart_id = value
        self.cart_id_changed.emit(value)

    @property
    def num_retries(self):
        """maximum number of retries before the server is considered down"""
        if self._num_retries is None:
            if self.cfg.has_option('mobile_app', 'num_retries'):
                self._num_retries = self.cfg.getint('mobile_app', 'num_retries')
            else:
                self._num_retries = 10
                logging.info("using default number of retries '10' as it wasn't set in the config")
        return self._num_retries

    def _tick_error_counter(self):
        """Raises an Exception after num_retries
        Call this function whenever the HTTP request to the server returns an error.
        After the specified number of retries this function raises a MaximumNumRetriesException

        :raise: MaximumNumRetriesException
        """
        self._retries_counter += 1
        if self._retries_counter > self.num_retries:
            raise MaximumNumRetriesException

    def _reset_error_counter(self):
        """call this function if there has been a succesfull request to reset the error counter"""
        self._retries_counter = 0

    def load(self):
        """Load cart from server and return it, or ``False`` if no cart has
        been uploaded yet for the current id or if an error occurred

        :return:  list of tuples (product_code, quantity) or False
        :rtype: list[(int, Decimal)] | bool

        :raise: InvalidCartJSONError

        raises InvalidCartJSONError if an invalid cart response was received from the server,
        (otherwise just returns False in normal cases of error)

        If the cart id seems already used, the random cart id is updated. please connect to the cart_id_changed() signal
        and update the shown QR code.
        """
        try:
            if self.cart_id is None:
                self._get_cart_id()
                return False
            req = requests.get(self.server_url + self.cart_id, timeout=self.timeout, verify=self._ssl_cert)
            req.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            logging.debug("app-checkout: app server responded with HTTP error {0}".format(exc))
            self._tick_error_counter()
            return False
        except requests.exceptions.RequestException as exc:
            # WORKAROUND: SSLError is somehow broken, sometimes its __str__()  method does not return a string
            # therefore we use repr()
            logging.debug("app-checkout: general error in HTTP request: {0}".format(repr(exc)))
            self._tick_error_counter()
            return False
        if req.text == "":
            # logging.debug("app-checkout: empty response from server")
            # no logging here since this is a standard use-case
            self._reset_error_counter()
            return False
        try:
            cart = self._decode_json_cart(req.text)
            self._reset_error_counter()
            return cart
        except InvalidCartJSONError as exception:
            logging.warning("Cannot decode Cart JSON: {0}".format(exception))
            raise

    def _decode_json_cart(self, json):
        """decode JSON data containing the cart

        :param json: JSON encoded data
        :type json: str
        :raise: InvalidCartJSONError
        """
        try:
            data = simplejson.loads(json)
        except simplejson.JSONDecodeError:
            raise InvalidCartJSONError("app-checkout: JSONDecodeError")
        logging.debug("received cart: {0}".format(repr(data)))
        try:
            if data["status"] != "PENDING":
                raise InvalidCartJSONError(property_name="status", value=data["status"])
            if str(data["cartCode"]) != self.cart_id:
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
        if not cart:
            raise InvalidCartJSONError("empty cart imported")
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
            req = requests.post(self.server_url + status + "/" + self.cart_id, timeout=self.timeout, verify=self._ssl_cert)  # , HTTPAdapter(max_retries=5))
            logging.debug("response: {0}".format(repr(req.text)))
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
            from configparser import ConfigParser
            model = MobileAppCartModel(ConfigParser())
            model._cart_id = "FAU15596984"

            product = {}
            product["id"] = 44
            product["productId"] = "9011"
            product["amount"] = "5."

            valid_data = {}
            valid_data["cartCode"] = model.cart_id
            valid_data["items"] = []
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

        # test wrong datatype inside items list
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

        # test invalid values for amount
        for invalid_amount_value in ["-5", "1.241234234232343242342234", "1e20"]:
            [model, data, _] = prepare()
            data["items"][0]["amount"] = invalid_amount_value
            with self.assertRaises(InvalidCartJSONError):
                model._decode_json_cart(simplejson.dumps(data))

        # test invalid values for product id
        for invalid_id_value in ["1.5", ""]:
            [model, data, _] = prepare()
            data["items"][0]["productId"] = invalid_id_value
            with self.assertRaises(InvalidCartJSONError):
                model._decode_json_cart(simplejson.dumps(data))

        # test empty cart
        [model, data, _] = prepare()
        data["items"] = []
        with self.assertRaises(InvalidCartJSONError):
            model._decode_json_cart(simplejson.dumps(data))

        # test naughty strings
        from os.path import dirname, abspath
        import codecs
        naughtystrings = ""
        naughtyfile = abspath(dirname(__file__) + "/../../libs/naughtystrings/blns.txt")
        with codecs.open(naughtyfile, 'r', "utf-8") as f:
            naughtystrings = f.readlines()
            naughtystrings.insert(0, "")
        [model, data1, _] = prepare()
        data2 = data1.copy()
        for nstring in naughtystrings:
            nstring = nstring.strip('\n')
            if not nstring.startswith('#'):
                data1["status"] = nstring
                data2["items"][0]["productId"] = nstring
                with self.assertRaises(InvalidCartJSONError):
                    model._decode_json_cart(simplejson.dumps(data1))
                    model._decode_json_cart(simplejson.dumps(data2))


if __name__ == "__main__":
    unittest.main()
