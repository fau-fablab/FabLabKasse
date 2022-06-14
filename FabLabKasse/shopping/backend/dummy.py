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

"""offline dummy backend
"""
from __future__ import absolute_import

import logging
from .abstract import Product, Category
from .offline_base import AbstractOfflineShoppingBackend, Client
from decimal import Decimal


class ShoppingBackend(AbstractOfflineShoppingBackend):
    def __init__(self, cfg):
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
                prod_id=4212,
                name="Comment / enter price",
                unit=u"Euro",
                location="-",
                price=1,
                categ_id=44,
                text_entry_required=True,
            ),
            Product(
                prod_id=9999,
                name="Donation",
                unit=u"Euro",
                location="-",
                price=1,
                categ_id=44,
            ),
            Product(
                prod_id=9994,
                name="Rest that could not be paid out",
                unit=u"Euro",
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

        AbstractOfflineShoppingBackend.__init__(
            self, cfg, categories, products, generate_root_category=True
        )

    def add_client(self, name, email, address, pin, comment, debt_limit):
        # not implemented
        pass

    def list_clients(self):
        clients = {
            1: Client(
                client_id=1,
                name="dummy 1234",
                pin="1234",
                debt=Decimal(13.37),
                debt_limit=Decimal("Infinity"),
            ),
            2: Client(
                client_id=2,
                name="poor guy 2345",
                pin="2345",
                debt=Decimal(42.21),
                debt_limit=Decimal("42.31"),
            ),
        }
        return clients

    def _store_payment(self, method):
        logging.warning("pay order is only a dummy function...")

    def _store_client_payment(self, client):
        logging.warning("pay order on client is only a dummy function...")
