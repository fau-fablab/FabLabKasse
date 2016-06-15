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

# for mirroring the touchscreen, do:
#DISPLAY=:0 xinput set-prop "Mouse0" --type=float "Coordinate Transformation Matrix" -1 0 0 0 1 0 0 0 1

# allow kde style
export QT_PLUGIN_PATH=/usr/lib/kde4/plugins/

# blue background and xeyes - appears during start and exit
xsetroot -solid blue
xeyes -geometry 300x200+600+400 &

echo "Start" >&2

# terminal window showing log output
xterm ~/FabLabKasse/FabLabKasse/scripts/xsession-tail-helper.sh &

# start GUI
~/FabLabKasse/run.py

echo "Program exited. Restart in 3 seconds..." >&2
sleep 3
