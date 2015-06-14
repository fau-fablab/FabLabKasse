#!/bin/bash

# search for warning and error in logfiles (*.log, *.log-YYYY-MM-DD), send an email, gzip and/or remove old files
# it is recommended to run this script before midnight, because the logs wrap over at midnight and might change in the middle of running this script

cd "$(dirname $0)"
cd ../..
python2.7 -m FabLabKasse.scripts.logWatchAndCleanup