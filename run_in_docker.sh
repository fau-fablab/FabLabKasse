#!/bin/sh
set -e
# Run GUI in docker, forwarding X11 (for GUI) and /dev/pts/* (for fake serial port for FAUCard emulator).
# This does not provide any kind of security separation. Docker only helps to provide the old libraries on a modern host system.
docker build . -t fablab.fau.de/fablabkasse
docker run -e DISPLAY --ipc=host -v /tmp/.X11-unix:/tmp/.X11-unix -v $(pwd):/home/FabLabKasse/FabLabKasse -v /dev/pts:/dev/pts --user="$(id --user):$(id --group)" fablab.fau.de/fablabkasse /home/FabLabKasse/FabLabKasse/run.py
