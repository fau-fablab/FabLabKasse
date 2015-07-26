#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

# helper class for a nonblocking subprocess
# (wrapper around asyncproc)
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

import asyncproc
import time
import os


class nonblockingProcess(object):

    """non-blocking subprocess, based on asyncproc"""

    def __init__(self, cmd, env=None):
        self.process = asyncproc.Process(cmd, stderr=file("/dev/null", "w"),
                                         env=env or {})
        self._read_buffer = ""

    def write(self, string):
        self.process.write(string)

    def readline(self):
        """read line from process stdout, if available, else return None"""
        # hasLine() implicitly reads new data
        if not self.hasLine():
            return None

        # return line without trailing \n
        end = self._read_buffer.find("\n")
        line = self._read_buffer[0:end]
        # remove line from buffer
        self._read_buffer = self._read_buffer[end + 2:]
        return line

    def hasLine(self):
        self._read_buffer += self.process.read()
        return "\n" in self._read_buffer

    def isAlive(self):
        return (self.process.wait(os.WNOHANG) == None)


def demo():
    """small example that communicates with bc, the commandline calculator.
    Note that readline() never blocks!
    """

    k = nonblockingProcess("bc")

    for i in range(4):
        print "read nothing:", k.readline()
        s = "{}+{}".format(i, i)
        print "sending: " + s
        k.write(s + "\n")
        time.sleep(1)
        print "read result:", k.readline()
        print "still alive:", k.isAlive()

if __name__ == "__main__":
    demo()
