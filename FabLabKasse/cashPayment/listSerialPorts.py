#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# list usb-serial devices

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
import re
import serial.tools.list_ports


def main():
    print "Listing all serial devices, pick the one you want and use the line in config.ini.\n"
    for (port, name, hwid) in serial.tools.list_ports.comports():
        print "\ndeviceN_port={}".format(port)
        if hwid not in ["n/a", None]:
            print "or use the permanent URL:\ndeviceN_port=hwgrep://{}".format(re.escape(hwid))


if __name__ == "__main__":
    main()
