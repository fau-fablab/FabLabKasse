#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#

from PyQt4 import uic
import fnmatch
import os
import subprocess

def main():
    uic.compileUi("FAUcardPaymentDialog.ui", open("FAUcardPaymentDialog.py", "w"), execute=True)

if __name__ == "__main__":
    main()
