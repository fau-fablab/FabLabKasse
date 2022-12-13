#!/bin/sh

# ensure VM is up and up-to-date
# (note: 'vagrant provision' is not run automatically)
vagrant up
vagrant rsync

# restart session
vagrant ssh -c "sudo service nodm restart"

# run all unittest cases in all .py files inside FabLabKasse
vagrant ssh -c "cd FabLabKasse && python3 -m unittest discover -v"