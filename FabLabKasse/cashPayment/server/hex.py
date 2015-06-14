# (C) 2013 Max Gaukler <development@maxgaukler.de>

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


def hex(x):
    if type(x) in [int, long]:
        if x < 0:
            return str(x)
        else:
            return '0x%02X' % (x)
    elif type(x) == list:
        return "[" + ", ".join([hex(val) for val in x]) + "]"
    else:
        return str(x)
