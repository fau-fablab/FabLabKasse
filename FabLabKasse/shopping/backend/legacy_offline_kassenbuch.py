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


class ShoppingBackend(AbstractOfflineShoppingBackend):
    def __init__(self, cfg):
        self._kasse = Kasse(cfg.get("general", "db_file"))

        categories = [
            Category(categ_id=7, name="Lasercutter", parent_id=0),
            Category(categ_id=1, name="3D Printer", parent_id=0),
            Category(categ_id=42, name="Laser Material", parent_id=7),
            Category(categ_id=43, name="Laser Time", parent_id=7),
            Category(categ_id=44, name="Other", parent_id=0),
        ]

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
                prod_id=2,
                name="Laser Time noncommercial",
                price=Decimal(".5"),
                unit="minute",
                location="-",
                categ_id=43,
            ),
            Product(
                prod_id=123,
                name="Acrylic 3mm",
                unit="Sheet 60x30cm",
                location="Shelf E3.1",
                price=Decimal("11.31"),
                categ_id=42,
            ),
            Product(
                prod_id=9212,
                name="Comment / enter price",
                unit="Euro",
                location="-",
                price=1,
                categ_id=44,
                text_entry_required=True,
            ),
            Product(
                prod_id=9999,
                name="Donation",
                unit="Euro",
                location="-",
                price=1,
                categ_id=44,
            ),
            Product(
                prod_id=9994,
                name="Rest that could not be paid out",
                unit="Euro",
                location="-",
                price=Decimal("1"),
                categ_id=None,
            ),
        ]

        assert (
            cfg.getint("payup_methods", "overpayment_product_id") == 9999
        ), "for this payment method you need to configure overpayment_product_id = 9999"
        assert (
            cfg.getint("payup_methods", "payout_impossible_product_id") == 9994
        ), "for this payment method you need to configure 'payout_impossible_product_id == 9994"
        # products.append(Product(prod_id=9994, name=u"nicht rückzahlbarer Rest", unit=u"Euro", location="-", price=Decimal("1"), categ_id=None))
        AbstractOfflineShoppingBackend.__init__(
            self, cfg, categories, products, generate_root_category=False
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
