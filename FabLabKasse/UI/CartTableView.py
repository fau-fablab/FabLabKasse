#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Patrick Kanzler <patrick.kanzler@fablab.fau.de>
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

from qtpy.QtWidgets import QTableView
from qtpy import QtGui, QtCore
import functools
from FabLabKasse.UI.GUIHelper import resize_table_columns


class CartTableView(QTableView):
    """Extends the funxtionality of a normal QTableView in order to supply a cart-view

    for usage see the cart-view in Kassenterminal and the cart-view in the app-checkout
    """

    def update_cart(self, shoppingBackend):
        """update table with current order lines"""
        order_lines = shoppingBackend.get_order_lines()

        # Initialize basic model for table
        order_model = QtGui.QStandardItemModel(len(order_lines), 4)
        order_model.setHorizontalHeaderItem(0, QtGui.QStandardItem("Anzahl"))
        order_model.setHorizontalHeaderItem(1, QtGui.QStandardItem("Einheit"))
        order_model.setHorizontalHeaderItem(2, QtGui.QStandardItem("Artikel"))
        order_model.setHorizontalHeaderItem(3, QtGui.QStandardItem("Einzelpreis"))
        order_model.setHorizontalHeaderItem(4, QtGui.QStandardItem("Gesamtpreis"))

        # Update Order lines

        for i, line in enumerate(order_lines):
            qty = QtGui.QStandardItem(shoppingBackend.format_qty(line.qty))
            qty.setData(line.order_line_id)
            order_model.setItem(i, 0, qty)

            uos = QtGui.QStandardItem(line.unit)
            order_model.setItem(i, 1, uos)

            name = QtGui.QStandardItem(line.name)
            order_model.setItem(i, 2, name)

            price_unit = QtGui.QStandardItem(
                shoppingBackend.format_money(line.price_per_unit)
            )
            order_model.setItem(i, 3, price_unit)

            subtotal = QtGui.QStandardItem(
                shoppingBackend.format_money(line.price_subtotal)
            )
            order_model.setItem(i, 4, subtotal)

        # Set Model
        self.setModel(order_model)
        # Change column width to useful values
        # needs to be delayed so that resize events for the scrollbar happens first, otherwise it reports a scrollbar width of 100px at the very first call
        QtCore.QTimer.singleShot(
            0, functools.partial(resize_table_columns, self, [4, 6, 20, 5, 5])
        )
        # TODO the 100ms delay is a workaround that is necessary because the first call often comes too early.
        # this workaround looks not so good, a nicer solution would be good
        QtCore.QTimer.singleShot(
            100, functools.partial(resize_table_columns, self, [4, 6, 20, 5, 5])
        )
