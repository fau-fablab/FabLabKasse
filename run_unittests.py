#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# (C) 2015 Patrick Kanzler <patrick.kanzler@fablab.fau.de>
#
# This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  The text of the license conditions can be read at
#  <http://www.gnu.org/licenses/>.
#
""" Runs all unittests, automatically searches all tests in the project """

import sys
import unittest

if __name__ == "__main__":
    suite = unittest.TestLoader().discover(".", "*.py")

    testresult = unittest.TextTestRunner(verbosity=1).run(suite)
    sys.exit(0 if testresult.wasSuccessful() else 1)
