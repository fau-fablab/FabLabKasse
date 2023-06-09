#!/bin/bash
set -ex

# ensure VM is up and up-to-date
# (note: 'vagrant provision' is not run automatically)
vagrant up
vagrant rsync
# Note: sleep times are to avoid "Vagrant can't use the requested machine because it is locked" errors
sleep 1

# launch FAUCard emulator in background if available
vagrant ssh --no-tty -c "echo Stopping FAUCard emulator; killall -9 run_emulator.sh; echo Starting FAUCard emulator; /home/vagrant/FabLabKasse/FabLabKasse/faucardPayment/magpos/emulator/run_emulator.sh || echo FAUCard emulator not available or failed/exited" &
sleep 1

# launch printserver emulator in background
vagrant ssh --no-tty -c "echo Stopping Dummy Printserver; killall -9 dummy-printserver.py; echo Starting Dummy Printserver; /home/vagrant/FabLabKasse/FabLabKasse/tools/dummy-printserver.py || echo Dummy printserver failed/exited" &
sleep 1

# restart session
vagrant ssh --no-tty -c "echo Starting GUI; echo; sudo service nodm restart"

# show logfile
vagrant ssh --no-tty -c "tail -f .xsession-errors"
