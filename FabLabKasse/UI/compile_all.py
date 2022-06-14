#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2014  Julian Hammer <julian.hammer@fablab.fau.de>
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

from __future__ import print_function
from PyQt4 import uic
import fnmatch
import os
import subprocess


def main():
    for file in os.listdir(os.path.dirname(__file__)):
        filename = os.path.dirname(__file__) + "/" + file
        prefix = os.path.dirname(__file__) + "/uic_generated/"
        if fnmatch.fnmatch(filename, "*.ui"):
            print(file)
            uic.compileUi(file, open(prefix + file[:-2] + "py", "w"), execute=True)
        if fnmatch.fnmatch(filename, "*.qrc"):
            print(file)
            subprocess.call(["pyrcc4", filename, "-o", prefix + file[:-4] + "_rc.py"])


if __name__ == "__main__":
    main()
