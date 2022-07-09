#!/bin/bash

# ensure VM is up and up-to-date
# (note: 'vagrant provision' is not run automatically)
vagrant up
vagrant rsync

# restart session
vagrant ssh -c "sudo service nodm restart"

# show logfile
vagrant ssh -c "tail -f .xsession-errors"
