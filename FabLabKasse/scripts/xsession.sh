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


echo "WORKAROUND FOR TOUCHSCREEN _ AAAAAH why does xinput_calibrate not work as it should?"
# set hardcoded calibration matrix, repeat every few second to allow for reconnects
( while true; do xinput set-prop "EloTouchSystems,Inc Elo TouchSystems 2216 AccuTouch® USB Touchmonitor Interface" --type=float "Coordinate Transformation Matrix" 1.215 0 -.085 0 -1.29 1.13 0 0 1 || true; sleep 2; done ) &

# allow kde style
export QT_PLUGIN_PATH=/usr/lib/kde4/plugins/

# blue background and xeyes - appears during start and exit
xsetroot -solid blue
xeyes -geometry 300x200+600+400 &

# terminal window showing log output
xterm ~/FabLabKasse/FabLabKasse/scripts/xsession-tail-helper.sh &

for i in $(seq 1 10); do
    curl -q --max-time 1 google.de > /dev/null && break || true
    echo "" >&2
    date >&2
    echo "Waiting for internet connection (max. 60 seconds)" >&2
    sleep 5
done
echo "" >&2
echo "Start" >&2

# start GUI
~/FabLabKasse/run.py

echo "Program exited. Restart in 3 seconds..." >&2
sleep 3
