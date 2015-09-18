#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2014  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Patrick Kanzler <patrick.kanzler@fablab.fau.de>
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


import signal
import logging
import logging.handlers
import sys
import portalocker
import sqlite3
from ConfigParser import ConfigParser
import codecs
from PyQt4 import QtGui
import traceback


def setupLogging(logfile):
    """configures the logging and logrotation"""
    my_logger = logging.getLogger()
    # rotate every day at 00:00, delete after 14 days
    handler = logging.handlers.TimedRotatingFileHandler(logfile, when='midnight', interval=1, backupCount=14)
    # handler = logging.FileHandler('example.logfile')
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    my_logger.setLevel(0)  # change this to 0 to log everything, even DEBUG-1, change to DEBUG to limit the amount of useless messages
    my_logger.addHandler(handler)
    consolehandler = logging.StreamHandler()  # log to stderr
    consolehandler.setLevel(0)  # log everything, even DEBUG-1
    my_logger.addHandler(consolehandler)
    my_logger.info("started logging to " + logfile)


def setupSigInt():
    def sigint(num, frame):
        logging.error("killed")
        sys.exit(1)
    signal.signal(signal.SIGINT, sigint)


def setupGraphicalExceptHook():
    """open a Qt messagebox on fatal exceptions"""
    if "--debug" in sys.argv:
        # we don't want this when running in a debugger
        return
    sys.excepthook_old = sys.excepthook

    def myNewExceptionHook(exctype, value, tb):
        import datetime
        # logging.exception()
        try:
            msgbox = QtGui.QMessageBox()
            txt = u"Entschuldigung, das Programm wird wegen eines Fehlers beendet."
            infotxt = u"Wenn dir Rückgeld entgangen ist, melde dich bei kasse@fablab.fau.de und gebe " + \
                u"neben einer Fehlerbeschreibung folgende Uhrzeit an: "
            infotxt += u"\n{}.".format(str(datetime.datetime.today()))
            detailtxt = u"{}\n{}".format(str(datetime.datetime.today()), "".join(
                traceback.format_exception(exctype, value, tb, limit=10)))
            logging.fatal(txt)
            logging.fatal(u"Full exception details (stack limit 50):\n" + u"".join(
                traceback.format_exception(exctype, value, tb, limit=50)))
            msgbox.setText(txt)
            msgbox.setInformativeText(infotxt)
            msgbox.setDetailedText(detailtxt)
            msgbox.setIcon(QtGui.QMessageBox.Critical)
            msgbox.exec_()
        except Exception as e:
            try:
                logging.error("graphical excepthook failed: " + repr(e))
            except Exception:
                logging.error("graphical excepthook failed hard,  cannot print exception (IOCHARSET problems?)")
        sys.excepthook_old(exctype, value, tb)
        sys.exit(1)
    sys.excepthook = myNewExceptionHook


def getConfig(path="./"):
    cfg = ConfigParser()
    try:
        cfg.readfp(codecs.open(path + 'config.ini', 'r', 'utf8'))
    except IOError:
        raise Exception("Cannot open configuration file. If you want to try the program and do not have a config, start ./run.py --example or just copy config.ini.example to config.ini")
    return cfg


def getDB():
    cfg = getConfig()
    return sqlite3.connect(cfg.get('general', 'db_file'))


class FileLock(object):

    """
    exclusive file-lock, for locking a resource against other processes

    Uses portalocker for platform-independence
    """

    def __init__(self, name):
        self.file = open(name + ".lock", "w")
        try:
            portalocker.lock(self.file, portalocker.LOCK_EX | portalocker.LOCK_NB)
        except IOError:
            raise Exception("lock " + name + " already taken, is another process already running?")
