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


import signal
import logging
import logging.handlers
import sys
import fcntl
import sqlite3
from ConfigParser import ConfigParser
import codecs
import time
from PyQt4 import QtGui
import traceback

def setupLogging(logfile):
    my_logger=logging.getLogger()
     # rotate every day at 00:00, delete after 14 days
    handler = logging.handlers.TimedRotatingFileHandler(logfile, when='midnight', interval=1, backupCount=14)
    #handler = logging.FileHandler('example.logfile')
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S'))
    my_logger.setLevel(0) # change this to 0 to log everything, even DEBUG-1, change to DEBUG to limit the amount of useless messages
    my_logger.addHandler(handler)
    consoleHandler=logging.StreamHandler() # log to stderr
    consoleHandler.setLevel(0) # log everything, even DEBUG-1
    my_logger.addHandler(consoleHandler)
    my_logger.info("started logging to "+logfile)



def setupSigInt():
    def sigint(num, frame):
        logging.error("killed")
        sys.exit(1)
    signal.signal(signal.SIGINT, sigint)

def setupGraphicalExceptHook():
    "open a Qt messagebox on fatal exceptions"
    if "--debug" in sys.argv:
        # we don't want this when running in a debugger
        return
    sys.excepthook_old=sys.excepthook
    def myNewExceptionHook(exctype, value, tb):
        import datetime
        #logging.exception()
        try:
            msgBox = QtGui.QMessageBox()
            txt = u"Entschuldigung, das Programm wird wegen eines Fehlers beendet. \n"
            txt += u" Wenn dir Rückgeld entgangen ist, melde dich bei kasse@fablab.fau.de und gebe " + \
                   u"folgende Uhrzeit an:"
            txt += u"{}.\n{}".format(str(datetime.datetime.today()),"".join(
                traceback.format_exception(exctype, value, tb, limit=10)))
            logging.fatal(txt)
            logging.fatal(u"Full exception details (stack limit 50):\n"+u"".join(
                traceback.format_exception(exctype, value, tb, limit=50)))
            msgBox.setText(txt)
            msgBox.exec_()
        except Exception as e:
            try:
                logging.error("graphical excepthook failed: " + repr(e))
            except Exception:
                logging.error("graphical excepthook failed hard,  cannot print exception (IOCHARSET problems?)")
        sys.excepthook_old(exctype, value, tb)
        sys.exit(1)
    sys.excepthook=myNewExceptionHook

def getConfig():
    cfg = ConfigParser()
    try:
        cfg.readfp(codecs.open('config.ini', 'r', 'utf8'))
    except IOError:
        raise Exception("Cannot open configuration file. If you want to try the program and do not have a config, start ./run.py --example or just copy config.ini.example to config.ini")
    return cfg

def getDB():
    cfg=getConfig()
    return sqlite3.connect(cfg.get('general', 'db_file'))

class FileLock(object):
    """
    exclusive file-lock, for locking a resource against other processes
    """
    def __init__(self, name):
        self.f=open(name+".lock", "w")
        try:
            fcntl.flock(self.f.fileno(),  fcntl.LOCK_EX|fcntl.LOCK_NB)
        except IOError:
            raise Exception("lock " + name + " already taken, is another process already running?")
class Timer:
    def __init__(self, name):
        self.name = name
        
    def __enter__(self):
        self.start = time.clock()
        return self

    def __exit__(self, *args):
        self.end = time.clock()
        self.interval = self.end - self.start
        print self.name, self.interval
