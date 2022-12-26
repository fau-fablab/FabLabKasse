#!/usr/bin/env python3
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


"""
Miscellaneous utility functions for gui.py, the Qt main GUI.
"""


def resize_table_columns(table, widths):
    """resize Qt table columns by the weight factors specified in widths,
    using the whole width (excluding scrollbar width)
    """
    w = table.viewport().width()
    for i, width in enumerate(widths):
        table.setColumnWidth(i, int(width * w / sum(widths)))
    # if we mess up, stretch the last column (comment out for debugging)
    table.horizontalHeader().setStretchLastSection(True)


def connect_button(btn, my_slot):
    # connect a button signal to a slot,
    # using the button text in lowercase as slot argument.
    # For connect_button(self.pushButton_0, self.insertIntoLineEdit), the result is similar to:
    # self.pushButton_0.clicked.connect(lambda x: self.insertIntoLineEdit("0"))
    btn.clicked.connect(lambda x: my_slot(btn.text().lower()))


def connect_button_to_lineedit(gui_instance, btn_suffix):
    # connect self.pushButton_<btn_suffix> to self.insertIntoLineEdit(<text of the button>)
    btn = getattr(gui_instance, "pushButton_" + str(btn_suffix))
    connect_button(btn, gui_instance.insertIntoLineEdit)
