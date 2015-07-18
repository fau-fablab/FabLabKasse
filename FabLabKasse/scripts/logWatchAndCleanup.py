#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015 Maximilian Gaukler <max@fablab.fau.de>
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


"""
a cronjob for cleaning up and gzipping old logfiles

- report errors and warnings in the newest logfiles (the current one, foo.log, and the archive files foo.log.2012-12-31 created after the last run of this script [i.e. the non-gzipped ones])
- gzip old logfiles and remove too old ones

run this script by starting logWatchAndCleanup.sh which lives in the same directory

# it is recommended to run this script before midnight, because the logs wrap over at midnight and might change in the middle of running this script

"""
# this script should work without changes under python3. ScriptHelpers dependencies (ConfigParser) are currently not ported to python3, so this remains python2.7

from __future__ import print_function
import sys
import os
import re
import subprocess
import dateutil.parser
import datetime
from ..scriptHelper import FileLock

def main():
    runOnlyOnce = FileLock("./logWatchAndCleanup.lock")
    
    
    os.chdir(os.path.dirname(os.path.realpath(__file__))+"/../")
    
    
    def isWarningLine(line):
        return "ERROR" in line or "WARN" in line
    
    MAX_ERRORS_PER_LOG = 100
    LOG_MAX_AGE = 14  # after how many days will the log be deleted
    errorLines = {}
    # gzip all old logfiles blafu.log.2014-12-24
    for f in os.listdir("."):
        isOldUnzippedLog = bool(re.match(r'[^/]*\.log\.[0-9]{4}-[0-9]{2}-[0-9]{2}$', f))
        isNewLog = f.endswith(".log")
        oldZippedLog = re.match(r'[^/]*\.log\.([0-9]{4}-[0-9]{2}-[0-9]{2}).gz$', f)
        if oldZippedLog:  # something like "asf.log.2015-04-12.gz"
            fileDate = dateutil.parser.parse(oldZippedLog.group(1))  # get file date
            if datetime.datetime.now() - fileDate > datetime.timedelta(LOG_MAX_AGE, 0, 0):
                # print("cleaning up: "+f)
                os.unlink(f)
        if isOldUnzippedLog or isNewLog:
            errorLinesCounter = 0
            for line in open(f, "r"):
                if isWarningLine(line):
                    if f not in errorLines:
                        errorLines[f] = []
                    errorLines[f].append(line)
                    if len(errorLines[f]) > MAX_ERRORS_PER_LOG:
                        break
    
            # found gzip old logfile
            if isOldUnzippedLog:
                assert subprocess.call(["gzip", f]) == 0,  "calling gzip failed"
    
    
    if len(errorLines) == 0:
        sys.exit(0)
    
    print("Hi, this is FabLabKasse/scripts/logWatch.sh.\nThere were warnings or errors in the recent logfile.\nPrinting the recent {} ones per file:\n".format(MAX_ERRORS_PER_LOG))
    for file in sorted(errorLines.keys()):
        print("\n\n========\n{}\n========".format(file))
        for line in errorLines[file]:
            print(line.strip())
        if len(errorLines[file]) >= MAX_ERRORS_PER_LOG:
            print("...")
    sys.exit(0)


if __name__ == "__main__":
    main()
