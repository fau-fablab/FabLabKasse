#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
from enum import Enum


class Status(Enum):
    """
    Status Codes from FAUcardPayment for MagPosLog logging
    MagPosLog saves them as int values
    """

    initializing = 0  # The process starts connection to MagnaBox
    waiting_card = 1  # Init done: Now waiting for card to read its balance and check it
    decreasing_balance = 2  # Card read: Now sending decreasing command to MagnaBox
    decreasing_done = 3  # Card balance decreased: Now executing booking
    booking_done = 4  # Payment fully booked and payed
    transaction_result = (
        5  # Got last transaction details which were not acknowledged by program
    )
    balance_underflow = 8  # Not enough balance on card to decrease
    unknown_error = 9  # Payment canceled on error the program cant handle on its self
    con_lost = 10  # Payment was canceled during a lost connection to the MagnaBox


class Info(Enum):
    """
    Info code containing OK / Error codes from FAUcardPayment for MagPosLog logging
    MagPosLog saves them as int values
    """

    OK = 0  # Everything OK, No Error
    con_error = 1  # Connection was lost during Payment
    balance_underflow = 2  # Card balance was lower than the amount to pay
    unknown_error = 3  # Error that could not be handled by program
    user_abort = 4  # User aborted execution before decreasing
    transaction_ok = 5  # Last transaction marked as successfully executed
    transaction_error = 6  # Last transaction marked as aborted on error
    con_back = 7  # Connection has been retrieved
    check_transaction_failed = 8  # Failed to check transaction
    booking_error = 9  # Error occured during booking
