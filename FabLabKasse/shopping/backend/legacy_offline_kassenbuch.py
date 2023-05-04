#!/usr/bin/env python3
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

"""adapter to legacy offline sqlite code ("Kasssenbuch", partly in german)
"""
from __future__ import print_function
from __future__ import absolute_import

import logging
from .abstract import Product, Category, PrinterError
from .offline_base import AbstractOfflineShoppingBackend, Client
from decimal import Decimal
from ..payment_methods import ManualCashPayment, FAUCardPayment
from ... import scriptHelper
from ...kassenbuch import Kasse, Rechnung, Buchung, Kunde
import socket
import itertools
import sqlite3
import urllib.request
import json


def load_json_from_url(url):
    """
    Fetch JSON from URL and decode it
    """
    with urllib.request.urlopen(url) as f:
        return json.load(f)


def load_categories_from_web(cfg) -> (list, int):
    """
    Download and parse list of categories

    return: (categories, root_category_id)

    example return value:
    categories = [
        Category(categ_id=0, name="All Products", parent_id=None),
        Category(categ_id=7, name="Lasercutter", parent_id=0),
        Category(categ_id=1, name="3D Printer", parent_id=0),
        Category(categ_id=42, name="Laser Material", parent_id=7),
        Category(categ_id=43, name="Laser Time", parent_id=7),
        Category(categ_id=44, name="Other", parent_id=0),
    ]
    root_category_id=0
    """
    categories = []
    CATEGORIES_JSON_URL = cfg.get("backend", "categories_json")
    categories_raw = load_json_from_url(CATEGORIES_JSON_URL)
    # [{'id': 1, 'property_stock_location': False, 'name': 'Alle Produkte', 'parent_id': False}, ..., {'id': 118, 'property_stock_location': False, 'name': 'Lasermaterial', 'parent_id': [117, 'Alle Produkte / Laser']}]
    root_category_id = None
    for c in categories_raw:
        parent_id = c["parent_id"]
        if c["parent_id"] is False:
            # root category -> remember ID
            root_category_id = c["id"]
            parent_id = None
        else:
            parent_id = c["parent_id"][0]
        categories.append(
            Category(categ_id=c["id"], name=c["name"], parent_id=parent_id)
        )
    if root_category_id is None:
        raise Exception(
            "Category list did not contain a root category (with parent_id=False)"
        )
    return (categories, root_category_id)


def load_products_from_web(cfg):
    """
    Download and parse list of products

    Example return value:
        products = [
        Product(
            prod_id=1,
            name="Laser Time commercial",
            price=1,
            unit="minute",
            location="-",
            categ_id=43,
        ),
        Product(
            prod_id=9212,
            name="Comment / enter price",
            unit="Euro",
            location="-",
            price=1,
            categ_id=44,
            text_entry_required=True,
        )
    ]

    Example JSON Web format (not all fields are used):

    {"0834": {"_price_str": "0,15\u202f\u20ac", "code": "0834", "_supplier_name": "MEW", "uom_id": 1, "_location_str": "Elektrowerkstatt / Regal / Schublade S6 (S6)", "default_code": "0834", "property_stock_location": false, "id": 693, "description": false, "sale_ok": true, "categ_id": [195, "Alle Produkte / Mechanik / Beilagscheiben"], "lst_price": 0.15, "_uom_rounding": 1.0, "_supplier_name_code": "MEW: 82.230.130", "_code_str": "0834", "_categ_list": ["Mechanik", "Beilagscheiben"], "_per_uom_str": "pro St\u00fcck", "manufacturer_pname": false, "_uom_str": "St\u00fcck", "_categ_str": "Mechanik / Beilagscheiben", "active": true, "manufacturer_pref": false, "manufacturer": false, "_supplier_all_infos": "MEW: 82.230.130", "name": "Karosseriescheibe\u00a0DIN\u00a09021\u00a0\u2010 13\u00a0\u2010\u00a0St. ", "_supplierinfo": {"pricelist_ids": [563], "name": [49, "MEW"], "product_uom": [1, "St\u00fcck"], "sequence": 1, "product_name": false, "company_id": [1, "FAU FabLab"], "qty": 0.0, "delay": 7, "min_qty": 0.0, "product_code": "82.230.130", "id": 578, "product_id": [693, "False"]}, "_name_and_description": "Karosseriescheibe\u00a0DIN\u00a09021\u00a0\u2010 13\u00a0\u2010\u00a0St. ", "_supplier_code": "82.230.130", "seller_ids": [578]},

    "0836": {"_price_str": "0,18\u202f\u20ac", "code": "0836", "_supplier_name": "Amazon (Sammellieferant f\u00fcr Auslagen/Vorkassebestellungen)", "uom_id": 1, "_location_str": "Elektrowerkstatt / Regal / Schublade S3 (S3)", "default_code": "0836", "property_stock_location": [121, "tats\u00e4chliche Lagerorte  / FAU FabLab / Elektrowerkstatt / Regal / Schublade S3"], "id": 3657, "description": false, "sale_ok": true, "categ_id": [32, "Alle Produkte / Elektronik / Geh\u00e4usebau"], "lst_price": 0.18, "_uom_rounding": 1.0, "_supplier_name_code": "Amazon (Sammellieferant f\u00fcr Auslagen/Vorkassebestellungen): ", "_code_str": "0836", "_categ_list": ["Elektronik", "Geh\u00e4usebau"], "_per_uom_str": "pro St\u00fcck", "manufacturer_pname": false, "_uom_str": "St\u00fcck", "_categ_str": "Elektronik / Geh\u00e4usebau", "active": true, "manufacturer_pref": false, "manufacturer": false, "_supplier_all_infos": "Amazon (Sammellieferant f\u00fcr Auslagen/Vorkassebestellungen): ", "name": "Antirutsch Pads selbstklebend \u00d8 10 mm", "_supplierinfo": {"pricelist_ids": [1889], "name": [175, "Amazon (Sammellieferant f\u00fcr Auslagen/Vorkassebestellungen)"], "product_uom": [1, "St\u00fcck"], "sequence": 1, "product_name": "108 x Antirutsch Pads aus EPDM/Zellkautschuk | rund | \u00d8 10 mm | Schwarz | selbstklebend | Rutschhemmende Pads inTop-Qualit\u00e4t", "company_id": [1, "FAU FabLab"], "qty": 108.0, "delay": 1, "min_qty": 108.0, "product_code": false, "id": 2293, "product_id": [2495, "False"]}, "_name_and_description": "Antirutsch Pads selbstklebend \u00d8 10 mm", "_supplier_code": "", "seller_ids": [2293]},

    ...
    }
    """
    PRODUCTS_JSON_URL = cfg.get("backend", "products_json")

    products = []
    products_raw = load_json_from_url(PRODUCTS_JSON_URL)
    for p in products_raw.values():
        price = Decimal(str(p["lst_price"]))
        if price <= 0:
            # skip products with price 0 until we have a better UI (price labels show "please donate" if the price is 0, the GUI here doesn't support that)
            continue
        products.append(
            Product(
                prod_id=int(p["code"].lstrip("0")),
                name=p["name"],  # or _name_and_description if we have more space
                price=price,
                unit=p["_uom_str"],
                location=p["_location_str"],
                categ_id=p["categ_id"][0],
                text_entry_required=("Kommentar" in p["name"]),
                qty_rounding=Decimal(str(p["_uom_rounding"])),
            )
        )
    return products


def remove_empty_categories(products: list, categories: list) -> list:
    """
    take a list of Products and Categories. Recursively remove all categories that contain no products.
    """
    # iterate until nothing changes (simplified: just iterate enough times)
    for i in range(99):
        # keep a category if...
        # it is the root category
        keep_categories = [c.categ_id for c in categories if c.parent_id is None]
        # or it contains another category
        keep_categories += [c.parent_id for c in categories]
        # or it contains a product
        keep_categories += [p.categ_id for p in products]
        categories = list([c for c in categories if c.categ_id in keep_categories])
    return categories


class ShoppingBackend(AbstractOfflineShoppingBackend):
    def __init__(self, cfg):
        self._kasse = Kasse(cfg.get("general", "db_file"))

        products = load_products_from_web(cfg)
        (categories, root_category_id) = load_categories_from_web(cfg)
        categories = remove_empty_categories(products, categories)

        assert (
            cfg.getint("payup_methods", "overpayment_product_id") == 9999
        ), "for this payment method you need to configure overpayment_product_id = 9999"
        assert (
            cfg.getint("payup_methods", "payout_impossible_product_id") == 9994
        ), "for this payment method you need to configure 'payout_impossible_product_id == 9994"
        # products.append(Product(prod_id=9994, name=u"nicht rückzahlbarer Rest", unit=u"Euro", location="-", price=Decimal("1"), categ_id=None))
        AbstractOfflineShoppingBackend.__init__(
            self,
            cfg,
            categories,
            products,
            generate_root_category=False,
            root_category_id=root_category_id,
        )

    def list_clients(self):
        clients = {}
        for k in self._kasse.kunden:
            debt_limit = k.schuldengrenze
            if debt_limit < 0:
                debt_limit = Decimal("Infinity")
            if k.pin != "0000":
                # do not add client when pin is 0000 (client disabled)
                # payment will also be prevented by the check in AbstractOfflineShoppingBackend -> Client.check_pin
                clients[k.id] = Client(
                    client_id=k.id,
                    name=k.name,
                    pin=k.pin,
                    debt_limit=debt_limit,
                    debt=-k.summe,
                    is_admin=str(k.kommentar).startswith("#admin#"),
                )
        return clients

    def add_client(self, name, email, address, pin, comment, debt_limit):
        kunde = Kunde("")
        kunde.name = name
        kunde.email = email
        kunde.adresse = address
        kunde.pin = str(pin)
        kunde.kommentar = comment
        kunde.schuldengrenze = Decimal(debt_limit)
        kunde.telefon = ""
        try:
            kunde.store(self._kasse.cur)
        except sqlite3.IntegrityError:
            raise Exception("Name already exists")
        self._kasse.con.commit()
        return kunde.id

    def _store_payment(self, method):
        origin = "Besucher"
        if isinstance(method, ManualCashPayment):
            destination = "Handkasse"
        elif isinstance(method, FAUCardPayment):
            destination = "FAUKarte"
        else:
            raise Exception("unsupported payment method")
        rechnung = self._rechnung_from_order_lines()
        assert rechnung.summe == method.amount_paid - method.amount_returned
        rechnung.store(self._kasse.cur)
        logging.info("stored payment in Rechnung#{0}".format(rechnung.id))

        b1 = Buchung(str(destination), rechnung.summe, rechnung=rechnung.id)
        b2 = Buchung(str(origin), -rechnung.summe, rechnung=rechnung.id, datum=b1.datum)
        self._kasse.buchen([b1, b2])  # implies database commit

        self._get_current_order_obj().rechnung_for_receipt = rechnung

    def _rechnung_from_order_lines(self):
        """create Rechnung() object from current order"""

        assert self._get_current_order_obj().finished
        rechnung = Rechnung()
        for line in self.get_order_lines():
            # this is hardcoded for prod_id used as four-digit product_code!
            rechnung.add_position(
                line.name,
                line.price_per_unit,
                anzahl=line.qty,
                einheit=line.unit,
                produkt_ref="{0:04}".format(line.product.prod_id),
            )
        total = self.get_current_total()
        assert abs(rechnung.summe - total) < Decimal(
            "0.01"
        ), "sum mismatch when converting to rechnung"
        # rounding can cause a difference of up to 1 cent between the non-rounded Rechnung() object and our rounding get_total() function
        if rechnung.summe != total:
            # TODO hardcoded product id
            rechnung.add_position(
                "Rundung",
                Decimal(1),
                anzahl=(total - rechnung.summe),
                einheit="Euro",
                produkt_ref="9996",
            )
        assert rechnung.summe == total
        print(rechnung.positionen)
        return rechnung

    def print_receipt(self, order_id):
        order = self._get_order_by_id(order_id)
        assert hasattr(
            order, "rechnung_for_receipt"
        ), "given order is not ready for printing the receipt"
        try:
            order.rechnung_for_receipt.print_receipt(cfg=scriptHelper.getConfig())
        except socket.error as e:
            raise PrinterError("Socket error: " + str(e))

    def get_orders(self):
        # TODO implement this function, currently not used by GUI
        raise NotImplementedError()

    def _store_client_payment(self, client):
        kunde = Kunde.load_from_id(client.client_id, self._kasse.cur)
        rechnung = self._rechnung_from_order_lines()
        rechnung.store(self._kasse.cur)
        logging.info("stored client payment in Rechnung#{0}".format(rechnung.id))

        kunde.add_buchung(-rechnung.summe, rechnung=rechnung.id)
        kunde.store(self._kasse.cur)
        self._kasse.con.commit()
