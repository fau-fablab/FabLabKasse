#!/bin/bash
set -e
# provisioning for Debian / Ubuntu
echo "ONLY RUN THIS SCRIPT on a disposable VM or a PC specially for setting up kasse. It will change your xsession and uninstall some packages."
echo "press ctrl-c to exit, Enter to continue (will continue automatically under Vagrant provisioner)"
read

[ -d /home/vagrant ] && echo "Running under Vagrant, using the vagrant user" && RUNNING_IN_VAGRANT=true || RUNNING_IN_VAGRANT=false

# change to the git directory
if $RUNNING_IN_VAGRANT; then
    cd /vagrant
fi
if [ ! -f requirements.txt ]; then
    pwd
    ls -l
    echo "This script must be run in the FabLabKasse main git directory which contains requirements.txt"
    exit 1
fi

# Install dependencies
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install git
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install python-pip python-qt4-dev python2.7 python-qt4 python-dateutil python-lxml pyqt4-dev-tools python-crypto python-termcolor python-serial python-qrcode python-docopt python-requests python-simplejson python-sphinx
sudo pip install -r requirements.txt
sudo DEBIAN_FRONTEND=noninteractive apt-get -y install xserver-xorg git nodm ssh x11-apps xterm kde-style-oxygen fonts-crosextra-carlito curl
# try to install xrandr command
apt-get -y install x11-xserver-utils || true
# Setup user and 'kiosk mode' desktop manager that autostarts FabLabKasse
$RUNNING_IN_VAGRANT && INSTALL_USER=vagrant || INSTALL_USER=kasse
$RUNNING_IN_VAGRANT || adduser kasse --disabled-password # not used in Vagrant, but in real system
# not needed: qt4-designer winpdb
# some package installs lightdm; we don't want it.
sudo apt-get -y remove lightdm
echo "NODM_ENABLED=true" | sudo tee -a /etc/default/nodm
echo "NODM_USER=$INSTALL_USER" | sudo tee -a /etc/default/nodm
# modemmanager interferes with serial port devices:
sudo apt-get -y remove modemmanager

rm /home/$INSTALL_USER/.xsession || true
if $RUNNING_IN_VAGRANT; then
	[ -d /home/$INSTALL_USER/FabLabKasse ] || ln -s /vagrant /home/$INSTALL_USER/FabLabKasse
else
	sudo -u $INSTALL_USER git clone --recursive https://github.com/fau-fablab/FabLabKasse /home/$INSTALL_USER/FabLabKasse
fi

if $RUNNING_IN_VAGRANT; then
    # In the Vagrant VM, the shared folder is not mounted immediately on power-up but with some delay.
    # Therefore, a symlink to xsession doesn't work.
    echo "while [ ! -f /home/$INSTALL_USER/FabLabKasse/FabLabKasse/scripts/xsession.sh ]; do sleep 1; echo Waiting for git repo; done; /home/$INSTALL_USER/FabLabKasse/FabLabKasse/scripts/xsession.sh" > /home/$INSTALL_USER/.xsession
else
    ln -s /home/$INSTALL_USER/FabLabKasse/FabLabKasse/scripts/xsession.sh /home/$INSTALL_USER/.xsession
fi

# the OpenERP import requires a german locale -- add it.
echo 'de_DE.UTF-8 UTF-8' | sudo tee -a /etc/locale.gen
# cd /usr/share/locales && sudo ./install-language-pack de_DE
sudo DEBIAN_FRONTEND=noninteractive dpkg-reconfigure locales

# allow shutdown/reboot for any user
sudo cp /home/$INSTALL_USER/FabLabKasse/FabLabKasse/tools/sudoers.d/kassenterm-reboot-shutdown /etc/sudoers.d/

# load example config if no config.ini exists
cd /home/$INSTALL_USER/FabLabKasse/ && sudo -u $INSTALL_USER ./run.py --example --only-load-config
echo "Warning: if no config exists, an example config will be installed. Please change it if you use this for a real system"
echo "Warning: For using it on a real system, cronjobs must be setup manually, please see INSTALLING.md"

sudo service nodm stop
sleep 2
sudo service nodm start
