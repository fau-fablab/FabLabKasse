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

import os
import sys
import subprocess
import time
from FabLabKasse import scriptHelper
import shutil
scriptHelper.setupSigInt()

reallyPrint=print
def print(x):
    sys.stdout.write(x + "\n")
    sys.stdout.flush()



currentDir=os.path.dirname(__file__)+"/"
os.chdir(currentDir)
currentDir=os.getcwd() + "/"
os.chdir(currentDir+"/FabLabKasse/")

def file_exists(filename):
    try:
        os.stat(filename)
        return True
    except OSError:
        return False

if "--example" in sys.argv:
    # load example config
    # test that there is no config.ini yet
    if file_exists("config.ini"):
        print("Warning: Configuration FabLabKasse/config.ini already exists, will not overwrite it. You can just start run.py without the --example argument to make this message disappear.")
        time.sleep(2)
    else:
        print("loading example configuration file. edit FabLabKasse/config.ini to change. You do not need the --example parameter later.")
        shutil.copyfile("config.ini.example", "config.ini")


os.chdir(currentDir+"/FabLabKasse/UI/")
subprocess.call("./compile_all.py")

os.chdir(currentDir+"/FabLabKasse/")
#subprocess.call("./importProdukte.py")
myEnv=dict(os.environ)
myEnv["LANG"]="de_DE.UTF-8"
myEnv["PYTHONIOENCODING"]="UTF-8"
myEnv["PYTHONPATH"] = currentDir # FabLabKasse git folder should be the main module starting point

    
cfg = scriptHelper.getConfig()

if not ('--no-update' in sys.argv):
    # start product import for some offline methods that load from a text file
    print("updating products [use --no-update to skip]")
    if cfg.get("backend", "backend") == "legacy_offline_kassenbuch":
        subprocess.call("./shopping/backend/legacy_offline_kassenbuch_tools/importProdukteOERP.py", env=myEnv)



"run sudo <program> and wait forever until the system reboots / shuts down"
def runShutdown(program):
    print("calling {}".format(program))
    time.sleep(1)
    if subprocess.call(["sudo",program]) != 0:
        print("cannot sudo {}".format(program))
        time.sleep(5)
    else:
        while True:
            print("Waiting for system {}".format(program))
            sys.stdout.flush()
            time.sleep(1)

os.chdir(currentDir+"/FabLabKasse/")
print("starting GUI")
debug=""
if "--debug" in sys.argv:
    debug="--debug"
    fu=subprocess.Popen("winpdb -a gui.py".split(" "), stdin=subprocess.PIPE)
    fu.stdin.write("gui")
    fu.stdin.close()
subprocess.call("python2.7 -m FabLabKasse.gui {}".format(debug).split(" "), env=myEnv)
print("GUI exited")
if "--debug" in sys.argv:
    sys.exit(0)
if os.access("./reboot-now", os.R_OK):
    os.unlink("./reboot-now")
    runShutdown("reboot")
if os.access("./shutdown-now", os.R_OK):
    os.unlink("./shutdown-now")
    runShutdown("poweroff")
