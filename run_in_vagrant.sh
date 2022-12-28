#!/bin/bash
set -ex

# ensure VM is up and up-to-date
# (note: 'vagrant provision' is not run automatically)
vagrant up
vagrant rsync

# launch FAUCard emulator in background if available
vagrant ssh --no-tty -c "echo Stopping FAUCard emulator; killall run_emulator.sh; echo Starting FAUCard emulator; /home/vagrant/FabLabKasse/FabLabKasse/faucardPayment/magpos/emulator/run_emulator.sh || echo FAUCard emulator not available or failed/exited" &

# launch printserver emulator in background
vagrant ssh --no-tty -c "echo Stopping Dummy Printserver; killall dummy-printserver.py; echo Starting Dummy Printserver; /home/vagrant/FabLabKasse/FabLabKasse/tools/dummy-printserver.py || echo Dummy printserver failed/exited" &

# restart session
vagrant ssh --no-tty -c "echo Starting GUI; echo; sudo service nodm restart"

# show logfile
vagrant ssh --no-tty -c "tail -f .xsession-errors"
