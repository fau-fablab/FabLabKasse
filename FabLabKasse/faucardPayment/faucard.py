#!/usr/bin/env python3
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
import logging

from .MagPosLog import MagPosLog
from ..UI.FAUcardPaymentDialogCode import FAUcardPaymentDialog
from .FAUcardPaymentThread import FAUcardThread
from .faucardStates import Status, Info


class PayupFAUCard(QtCore.QObject):
    def __init__(self, parent, amount, shopping_backend):
        """
        Initializes the PayupFAUCard Process
        :param parent: Parent QObject
        :type parent: QtCore.QObject
        :param amount: amount to pay
        :type amount: Decimal
        :param shopping_backend: current instance of ShoppingBackend
        :type shopping_backend: shopping.backend.abstract.AbstractShoppingBackend
        """
        QtCore.QObject.__init__(self)
        assert isinstance(amount, Decimal), "PayupFAUCard: Amount to pay not Decimal"
        assert amount > 0, "PayupFAUCard: amount is negativ"

        self.amount = amount
        self.shopping_backend = shopping_backend
        self.thread = QtCore.QThread()
        self.dialog = FAUcardPaymentDialog(
            parent=parent, amount=self.amount, shopping_backend=self.shopping_backend
        )
        self.worker = FAUcardThread(
            dialog=self.dialog, amount=self.amount, thread=self.thread
        )

    def executePayment(self):
        """
        Runs the Payment-process: Open dialog, wait for payment to complete (or to fail), close dialog, clean up.

        Expected usage when the user requests "Start FAUCard payment":
        1. Call this function
        2. If it returned True:
             The payment has succeeded.
             a.  Write the corresponding booking into the accounting / cash register database.
             b. call finish_log(), which then notes in the FAUCard MagPosLog logging that the payment has been fully booked.
                Note that if a) crashes, then we can see this in the MagPos database status.
           Else:
             The payment has failed, go back to the shopping-cart view so that the user can restart the payment.

        :return: True on success, False otherwise
        :rtype: bool
        """
        # Start the process
        self.thread.start()
        self.dialog.show()

        # Execute the GUI and wait until the dialog has closed.
        success = self.dialog.exec_()

        # Now, the payment routine (FAUCardThread.run()) has returned (or raised an Exception).
        # double-check this:
        while not self.worker.run_finished:
            # TODO: rewrite the code so that it is obvious that this can not happen.
            #  --> FAUCardThread itself should subclass QThread and override run().
            logging.error(
                "Payment routine did not finish (deadlock?), waiting...   This should never happen."
            )
            time.sleep(10)

        # Stop thread's event loop, it is no longer needed
        self.thread.quit()
        while not self.thread.wait(10000):
            logging.error(
                "thread refuses to stop, waiting...    This should never happen except when e.g. the system is under extreme CPU load."
            )

        return success == QtWidgets.QDialog.Accepted

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
