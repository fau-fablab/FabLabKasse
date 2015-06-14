#!/bin/bash
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


# change to FabLabKasse/ directory
cd "$(dirname $0)"
cd ..

# create tempfile, backup database into it
filename=`mktemp snapshotXXXXXXXXXXX.sqlite3` || exit 1
sqlite3 production.sqlite3 ".backup $filename"

# delete pins in tempfile
sqlite3 "$filename" 'UPDATE kunde SET pin = -1;'
# publish tempfile
mv "$filename" "./snapshotOhnePins.sqlite3"

# make statistics
PYTHONPATH=".." ./shopping/backend/legacy_offline_kassenbuch_tools/exportConsumptionMoney.py > consumptionMoney.txt

# upload
scp consumptionMoney.txt snapshotOhnePins.sqlite3 kassenterminal@macgyver.fablab.fau.de: