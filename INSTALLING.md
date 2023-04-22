Installing
==========

0. Checkout
-----------

This project contains submodules. For this you have to checkout e.g. recursively:

`git clone --recursive git@github.com:fau-fablab/FabLabKasse.git`

Please note that currently you need a github account and attach your public SSH key to it. If this is not possible, you can manually edit .gitmodules to use https checkout.

1.  Dependencies
----------------

This software was mainly developed for Debian stretch, but should also work on other OSes.

If you just want to play, you can try Vagrant to automatically setup a VM (see notes in Vagrantfile).

### 1a. Debian

If you have a standalone PC or VM only for FabLabKasse, you can also use `FabLabKasse/scripts/install_debian.sh`, which sets up a kiosk system that autostarts FabLabKasse.

Else, you can set up a Debian or Ubuntu system and apply the section "install dependencies" of the above script.

Modem-Manager interferes with the serial port. It is highly recommended to remove it:
    apt-get remove modemmanager

### 1b. Mac OS

 - python 2.7
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


### 1c. Fedora

 - needed fedora packages:

        dnf install python python-qt4 python-qt4-devel python-dateutil python-lxml python-crypto python-termcolor python-natsort python-qrcode python-docopt python-requests python-simplejson python-monotonic
        pip install -r requirements

 - for development: qt4-designer
 - for documentation: dnf: doxygen python-pygraphviz; pip: doxypy

### 1d. Windows

 TODO

### 1e. Virtualenv

 - install system packages for your OS, and python-virtualenv

        virtualenv --system-site-packages .env  # create virtualenv and use system python packages
        source .env/bin/activate                # enter the environment
        pip install -r requirements.txt         # install python requirements using pip

 - you have to be "in" the virtual environment to run FabLabKasse and other programs (see your shell prompt):

        source .env/bin/activate                # enter the environment
        ./run.py                                # run programs
        ./FabLabKasse/kassenbuch.py
        # [...]

2.  Configuration
-----------------

    cd FabLabKasse/
    cp config.ini.example config.ini
    # now edit config.ini file

Please use database name "production" for the real terminal, and something else for tests and development!

Moreover for push-access of the submodules, you should execute configure_git_submodules in root directory. This sets the pushurl of submodules to the git one.

3.  Data import
---------------

TODO ... importProdukte.py ...

4.  Setting up the terminal
---------------------------

Please take a look at install_debian.sh, which does most of the tasks described in this section.

(Internal note for FAU FabLab: Cronjobs, mail, firewall etc are set up by `FabLabKasse-interna/install.sh` which lives in a separate repo.)

You need a touchscreen (preferably USB with 1280x1024 resolution, preferably a model which does not require special calibration).

    adduser kasse --disabled-password

If you want to use the reboot/shutdown option from the menu,
cp tools/sudoers.d/kassenterm-reboot-shutdown /etc/sudoers.d/

Setup nodm for autologin of the 'kasse' user.

sudo -u kasse -i
    kasse@terminal:$ git clone  ...
    kasse@terminal:$ ln -s FabLabKasse/scripts/xsession.sh .xsession

TODO: cronjobs
setup daily cronjobs for

    /home/kasse/FabLabKasse/scripts/logWatchAndCleanup.sh # mail warnings and errors in logfile, gzip and log cleanup -- without this files will be kept as uncompressed plaintext, but also deleted after 14 days

and according to your needs, set up your own backup, statistics et cetera.

Setup mail system so that you receive error messages from cronjobs.

Setup firewall as desired.

5. Using
--------

TODO....

 - GUI for normal users
 - administrative tasks: `ssh kasse@terminal; cd FabLabKasse; ./kassenbuch.py -h`
    - see help output
    - run `activate-global-python-argcomplete` to enable tab completion
