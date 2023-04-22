#!/usr/bin/python3
# -*- coding: utf-8 -*-

# UNLICENSE

# Max Gaukler <max@fablab.fau.de>

""" a cheap dummy replacement for a ESC/P network receipt printer.
All network input from localhost:4242 is shown on standard output.
Non-ASCII characters including control commands and bitmap data are replaced
by placeholder characters """
from __future__ import print_function

import socket
import string
import sys

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
host = "localhost"
port = 4242
sock.bind((host, port))
sock.listen(0)
print("\nlistening on {}:{}\n".format(host, port))
while True:
    conn, addr = sock.accept()
    while True:
        data = conn.recv(1)
        if not data:
            print("\n\n========= client disconnected =======\n\n")
            break
        data = data.decode("ascii", errors="replace")
        sys.stdout.write(data)
        sys.stdout.flush()
