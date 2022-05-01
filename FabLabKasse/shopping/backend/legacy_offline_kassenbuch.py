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

"""adapter to legacy offline sqlite code ("Kasssenbuch", partly in german)
"""

import logging
from abstract import Product, Category, PrinterError
from offline_base import AbstractOfflineShoppingBackend, Client
from decimal import Decimal
from ..payment_methods import ManualCashPayment, FAUCardPayment
from ... import scriptHelper
from ...kassenbuch import Kasse, Rechnung, Buchung, Kunde
from ...produkt import Produkt
import socket
import itertools
import sqlite3


class ShoppingBackend(AbstractOfflineShoppingBackend):
    def __init__(self, cfg):
        self._kasse = Kasse(cfg.get("general", "db_file"))

        produkte, produkte_wald = Produkt.load_from_dir("produkte/")
        categ_id_counter = itertools.count(start=1)
        categories = []
        products = []

        def convert_products(prod_list, current_category):
            for p in prod_list:
                qty_rounding = 0
                if p.verkaufseinheiten[p.basiseinheit]["input_mode"] == "INTEGER":
                    qty_rounding = 1
                else:
                    qty_rounding = Decimal("0.01")
                products.append(
                    Product(
                        prod_id=int(p.PLU),
                        name=p.name,
                        unit=p.basiseinheit,
                        price=p.verkaufseinheiten[p.basiseinheit]["preis"],
                        location="",
                        categ_id=current_category.categ_id,
                        qty_rounding=qty_rounding,
                        text_entry_required=("Kommentar" in p.name),
                    )
                )

        def create_category(name, super_category):
            new_categ = Category(
                categ_id=next(categ_id_counter),
                name=name,
                parent_id=super_category.categ_id,
            )
            categories.append(new_categ)
            return new_categ

        def recursively_add_categories(name, data, super_category):
            # add a category:
            # 1. the category itself
            current_category = create_category(name, super_category)
            # 2. the contained products
            convert_products(data[1], current_category)
            # 3. recurse: contained subcategories
            for (sub_name, sub_data) in data[
                0
            ].iteritems():  # walk through dict of subcategories
                recursively_add_categories(sub_name, sub_data, current_category)

        root = Category(
            categ_id=0, name="root pseudocategory, not used later", parent_id=None
        )
        categories.append(root)
        for (name, data) in produkte_wald.iteritems():
            recursively_add_categories(name, data, root)

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
                    is_admin=unicode(k.kommentar).startswith("#admin#"),
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
        origin = u"Besucher"
        if isinstance(method, ManualCashPayment):
            destination = u"Handkasse"
        elif isinstance(method, FAUCardPayment):
            destination = u"FAUKarte"
        else:
            raise Exception("unsupported payment method")
        rechnung = self._rechnung_from_order_lines()
        assert rechnung.summe == method.amount_paid - method.amount_returned
        rechnung.store(self._kasse.cur)
        logging.info("stored payment in Rechnung#{0}".format(rechnung.id))

        b1 = Buchung(unicode(destination), rechnung.summe, rechnung=rechnung.id)
        b2 = Buchung(
            unicode(origin), -rechnung.summe, rechnung=rechnung.id, datum=b1.datum
        )
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
        print rechnung.positionen
        return rechnung

    def print_receipt(self, order_id):
        order = self._get_order_by_id(order_id)
        assert hasattr(
            order, "rechnung_for_receipt"
        ), "given order is not ready for printing the receipt"
        try:
            order.rechnung_for_receipt.print_receipt(cfg=scriptHelper.getConfig())
        except socket.error, e:
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
