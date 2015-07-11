Installing
==========

0. Checkout
-----------

This project contains submodules. For this you have to checkout e.g. recursively:

`git clone --recursive git@github.com:fau-fablab/FabLabKasse.git`

1.  Dependencies
----------------

This software was mainly developed for Debian "jessie", but should also work on other OSes.

### 1a. Debian

 - needed debian packages:

        apt-get install python-qt4-dev python2.7 python-qt4 python-dateutil python-lxml pyqt4-dev-tools python-crypto python-termcolor python-serial python-natsort python-qrcode python-docopt python-requests python-simplejson
        pip install monotonic
        pip install oerplib # only for connection to OpenERP/odoo

 - for the real terminal implementation: xserver-xorg git nodm ssh
 - for the style: kde-style-oxygen kde-workspace-bin
 - for font: fonts-crosextra-carlito # or download Carlito-Regular.ttf from http://openfontlibrary.org/de/font/carlito#Carlito-Regular to ~/.fonts/
 - for development: qt4-designer
 - for graphical debugging: winpdb
 - for documentation: doxygen doxypy python-pygraphviz


Modem-Manager interferes with the serial port. It is highly recommended to remove it:
    apt-get remove modemmanager

### 1b. Mac OS

 - python installieren
 - Qt: http://qt-project.org/downloads
 - SIP: http://www.riverbankcomputing.com/software/sip/download (entpacken, `configure`, `make`, `make install`)
 - PyQt4: http://www.riverbankcomputing.com/software/pyqt/download (entpacken, `configure`, `make`, `make install`)
 - lxml: 

        cd /tmp
        wget http://lxml.de/files/lxml-2.2.2.tgz
        tar -xzvf lxml-2.2.2.tgz 
        cd lxml-2.2.2
        python setup.py build --static-deps --libxml2-version=2.7.3  --libxslt-version=1.1.24 
        sudo python setup.py install



2.  Configuration
-----------------

    cp config.ini.example config.ini
    edit config.ini file

Please use database name "production" for the real terminal, and something else for tests and development!

3.  Data import
---------------

TODO ... importProdukte.py ...

4.  Setting up the terminal
---------------------------

You need a touchscreen (preferably USB) with 1280x1024 resolution

    adduser kasse --disabled-password

If you want to use the reboot/shutdown option from the menu,
cp tools/sudoers.d/kassenterm-reboot-shutdown /etc/sudoers.d/

TODO: setup nodm for autologin of kasse

TODO touchscreen calibration: ssh kasse@terminal DISPLAY=:0 xinput_calibration, make permanent by copying output to /etc/X11/xorg.conf (or /etc/xorg.conf.d/someFile)

    sudo -u kasse -i
    kasse@terminal:$ git clone  ...
    kasse@terminal:$ ln -s FabLabKasse/scripts/xsession.sh .xsession

TODO: cronjobs
setup daily cronjobs for

    /home/kasse/FabLabKasse/scripts/logWatchAndCleanup.sh # mail warnings and errors in logfile, gzip and log cleanup -- without this files will be kept as uncompressed plaintext, but also deleted after 14 days
    /home/kasse/FabLabKasse/scripts/backup.sh # for SSH backup, needs adjusting (TODO make configurable)
    /home/kasse/FabLabKasse/scripts/databaseSnapshotAndSummary.sh # for some statistics, needs adjusting (TODO make configurable)

setup mail system so that you receive error messages from cronjobs

recommended setup firewall:

    apt-get install iptables-persistent
    cp tools/iptables/rules.v* /etc/iptables/
    service netfilter-persistent restart

5. Using
--------

TODO....

GUI for normal users
administrative tasks: `ssh kasse@terminal; cd FabLabKasse; ./kassenbuch.py`
-> see help output
