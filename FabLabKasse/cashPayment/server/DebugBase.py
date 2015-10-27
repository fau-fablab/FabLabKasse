#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# base class for debugging purposes

# (C) 2015 Patrick Kanzler <patrick.kanzler@fablab.fau.de

#  This program is free software: you can redistribute it and/or modify
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

import logging

class DebugBase(object):
    """base class to supply logging code
    """

    def printDebug(self, s, debugLevel):
        logLevels = {-1: logging.ERROR,  0: logging.WARNING,  1: logging.INFO, 2: logging.DEBUG,  3: logging.DEBUG - 1}
        logging.getLogger(self.__repr__()).log(logLevels[debugLevel], s)

    def error(self, s):
        self.printDebug(s, -1)

    def log(self, s):
        self.printDebug(s, 1)

    def warn(self, s):
        self.printDebug(s, 0)

    def debug(self, s):
        self.printDebug(s, 2)

    def debug2(self, s):
        self.printDebug(s, 3)