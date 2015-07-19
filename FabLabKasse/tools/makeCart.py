#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015 FAU FabLab team  members and others
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
Generate an example cart JSON for testing.

usage:

- set up a HTTP server, configure it config.ini
- go the webroot, you can now create carts with `makeCart.py <cart_id>`
- the script will generate a file with some JSON content for testing.
  Adjust the script to your needs.
- submitting the status (cancel/paid) of a cart cannot be simulated

"""


import json
from sys import argv
import time

if __name__ == "__main__":
    id = int(argv[1])

    data = {}
    data["cartCode"] = id
    data["items"] = []

    product = {}
    product["id"] = 44
    product["productId"] = "9011"
    #product["amount"] = "5."

    data["items"].append(product)
    data["status"] = "PENDING"
    data["pushId"] = "000"
    data["sendToServer"] = int(time.time())

    f = open(str(id), "w")
    f.write(json.dumps(data))
    f.close()
