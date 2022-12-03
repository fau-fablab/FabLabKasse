#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#

from __future__ import absolute_import
import codecs
from FabLabKasse import scriptHelper
from configparser import ConfigParser

import sqlite3
from datetime import datetime
from decimal import Decimal
from qtpy import QtCore, QtWidgets, QtGui

from .MagPosLog import MagPosLog
from ..UI.FAUcardPaymentDialogCode import FAUcardPaymentDialog
from .FAUcardPaymentThread import FAUcardThread
from .faucardStates import Status, Info


class PayupFAUCard(QtCore.QObject):
    def __init__(self, parent, amount):
        """
        Initializes the PayupFAUCard Process
        :param parent: Parent QObject
        :type parent: QtCore.QObject
        :param amount: amount to pay
        :type amount: Decimal
        """
        QtCore.QObject.__init__(self)
        assert isinstance(amount, Decimal), "PayupFAUCard: Amount to pay not Decimal"
        assert amount > 0, "PayupFAUCard: amount is negativ"

        self.amount = amount
        self.thread = QtCore.QThread()
        self.dialog = FAUcardPaymentDialog(parent=parent, amount=self.amount)
        self.dialog.request_termination.connect(
            self.threadTerminationRequested, type=QtCore.Qt.DirectConnection
        )
        self.worker = FAUcardThread(
            dialog=self.dialog, amount=self.amount, thread=self.thread
        )

    def executePayment(self):
        """
        Starts the Payment-process and Dialog
        :return: True on success, False otherwise
        :rtype: bool
        """
        # Start the process
        self.thread.start()
        self.dialog.show()

        # Execute the GUI
        success = self.dialog.exec_()

        if success == QtWidgets.QDialog.Accepted:
            return True
        else:
            # Wait for thread to finish cleanup
            self.thread.wait(1000)
            return False

    def getPaidAmount(self):
        """
        Returns the amount the user has payed with his FAUCard
        :return: the amount payed
        :rtype: Decimal
        """
        return self.worker.get_amount_payed()

    def getWantReceipt(self):
        """
        Returns if the user wants a receipt
        :return: bool if user wants receipt
        :rtype: bool
        """
        # always output a receipt due to legal requirements
        return True

    def finishLogEntry(self):
        """
        Completes the log entry in the MagPosLog and closes all open threads and dialogs
        """
        if self.thread.isRunning():
            QtCore.QMetaObject.invokeMethod(
                self.worker,
                "set_ack",
                QtCore.Qt.QueuedConnection,
                Qt.Q_ARG(bool, False),
            )
        self.close()

    @QtCore.Slot()
    def threadTerminationRequested(self):
        """
        Terminates the self.thread if requested.
        """
        self.thread.wait(100)
        self.thread.quit()
        if not self.thread.wait(1000):
            self.thread.terminate()

    def close(self):
        """
        Quits self.thread, closes self.dialog
        """
        self.dialog.close()
        if self.thread.isRunning():
            QtCore.QMetaObject.invokeMethod(
                self.worker,
                "set_should_finish_log",
                QtCore.Qt.QueuedConnection,
                Qt.Q_ARG(bool, False),
            )
            QtCore.QMetaObject.invokeMethod(
                self.worker,
                "set_ack",
                QtCore.Qt.QueuedConnection,
                Qt.Q_ARG(bool, False),
            )
            self.thread.wait(100)
            if not self.thread.isRunning():
                return
            self.thread.quit()
            if not self.thread.wait(1000):
                self.thread.terminate()


def check_last_transaction():
    """
    Dummy function to easier access check_last_transaction from code outside of faucard.py
    :return: True on success reading last transaction details, False otherwise
    :rtype: bool
    """
    cfg = scriptHelper.getConfig()
    con = sqlite3.connect(cfg.get("magna_carta", "log_file"))
    cur = con.cursor()
    con.text_factory = str
    return FAUcardThread.check_last_transaction(cur=cur, con=con)


def finish_log(info=Info.OK):
    """
    Part
    Finishes last MagPosLog Entry by setting its state to Status.booking_done after the internal booking was done
    """
    cfg = scriptHelper.getConfig()
    con = sqlite3.connect(cfg.get("magna_carta", "log_file"))
    cur = con.cursor()
    con.text_factory = str

    cur.execute("SELECT id, status, info FROM MagPosLog ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()

    # Check if last entry was about an not yet booked but payed payment
    if row[1] == Status.decreasing_done.value and row[2] == Info.OK.value:
        id = row[0]
        cur.execute(
            "UPDATE MagPosLog SET datum=(?), status=(?), info=(?) WHERE id=(?)",
            (datetime.now(), Status.booking_done.value, info.value, id),
        )
        con.commit()
