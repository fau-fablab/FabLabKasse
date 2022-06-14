# Testing in a VM

- Install vagrant and virtualbox
- run `vagrant up`, wait a long time
- you now have a VirtualBox Ubuntu VM with the software running. The git repository is accessible from inside the VM as /home/vagrant/FabLabKasse.


Use `vagrant ssh` to get a shell inside the VM. From there you can:

- `cat .xsession_errors` to see the output of the running kassenterminal instance
- `export DISPLAY=:0`, then you can run X applications like xterm
- `sudo service nodm restart` to restart the terminal

When changing `install_debian.sh`, don't forget to:

- `vagrant rsync` to sync your changes and then
- `vagrant provision` to run the modified code
