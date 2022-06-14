#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#


from __future__ import absolute_import
import sqlite3
from datetime import datetime
from decimal import Decimal

from .faucardStates import Status, Info
import logging


class MagPosLog:
    """MagPosLog
    The MagPosLog is a logfile class to log the current state and info code of a MagnaBox transaction in a SQL File for
    debugging and error handling purpose.
    """

    def __init__(self, amount, cur, con):
        """
        Initializes the MagPosLog by creating the sql table if it does not exist and setting the member variables.
        :param amount: Amount which the payment is about
        :type amount: Decimal
        :param cur: Cursor of the sql connection
        :type cur: sqlite3.Cursor
        :param con: Connection to the sql database
        :type con: sqlite3.Connection
        """

        assert isinstance(amount, Decimal), u"MagPosLog: Amount to pay not Decimal"

        # Set up member variables
        self.id = 0
        self.cardnumber = 0
        self.datum = datetime.now()
        self.status = Status.initializing.value
        self.info = Info.OK.value
        self.payed = False
        self.cur = cur
        self.con = con
        self.amount = amount
        self.timestamp_payed = None
        self.oldbalance = 0
        self.newbalance = 0

        # Create table if it does not exist
        self.cur.execute(
            "CREATE TABLE IF NOT EXISTS MagPosLog(id INTEGER PRIMARY KEY AUTOINCREMENT, datum, cardnumber INT, amount TEXT, oldbalance INT, newbalance INT, timestamp_payed, status INT, info INT, payed)"
        )
        con.commit()

    def set_status(self, new_status, new_info=Info.OK):
        """
        Logs the given new_status and info in to the MagPosLob Table. Automatically converts status and info to
        their corresponding int values
        :param new_status: New Status code
        :type new_status: Status int
        :param info: New Info code
        :type info: Info int
        """
        assert isinstance(new_status, (int, Status)) and isinstance(
            new_info, (int, Info)
        ), "Wrong param type"

        if isinstance(new_status, Status):
            self.status = new_status.value
        else:
            self.status = new_status

        if isinstance(new_info, Info):
            self.info = new_info.value
        else:
            self.info = new_info

        if self.status is Status.decreasing_done.value and self.info is Info.OK.value:
            self.payed = True

        # Stores the current state in the MagPosLog table
        self._store()

    def set_cardnumber(self, cardnumber):
        """
        Logs the cardnumber to the database entry
        :param cardnumber: Cardnumber of the FAU-card, the payment will be dealt from
        :type cardnumber: int
        """
        assert self.id != 0, "Can't set cardnumber if there is no id"
        self.cardnumber = cardnumber
        self.cur.execute(
            "UPDATE MagPosLog SET cardnumber = ? WHERE id = ?", (cardnumber, self.id)
        )
        self.con.commit()

    def set_oldbalance(self, oldbalance):
        """
        Logs the old card balance of customer
        ;param oldbalance: Old Card Balance
        :type oldbalance: int
        """
        assert self.id != 0, "Can't set oldbalance if there is no id"
        self.oldbalance = oldbalance
        self.cur.execute(
            "UPDATE MagPosLog SET oldbalance = ? WHERE id = ?",
            (self.oldbalance, self.id),
        )
        self.con.commit()

    def set_newbalance(self, newbalance):
        """
        Logs the new card balance of customer
        ;param newbalance: New Card Balance
        :type newbalance: int
        """
        assert self.id != 0, "Can't set newbalance if there is no id"
        self.newbalance = newbalance
        self.cur.execute(
            "UPDATE MagPosLog SET newbalance = ? WHERE id = ?", (newbalance, self.id)
        )
        self.con.commit()

    def set_timestamp_payed(self, timestamp):
        """
        Logs the timestamp which is closest to the time of payment
        ;param timestamp: Timestamp of payment
        :type timestamp: datetime
        """
        assert self.id != 0, "Can't set timestamp payed if there is no id"
        self.timestamp_payed = timestamp
        self.cur.execute(
            "UPDATE MagPosLog SET timestamp_payed = ? WHERE id = ?",
            (timestamp, self.id),
        )
        self.con.commit()

    def _store(self):
        """
        Stores the Instance of MagPosLog in the database
        """
        # Grab ID if instance has none
        if self.id is 0 or self.id is None:
            self.cur.execute(
                "INSERT INTO MagPosLog (cardnumber, amount, datum, status, info, payed) VALUES (?,?,?,?,?,?)",
                (
                    self.cardnumber,
                    unicode(self.amount),
                    datetime.now(),
                    self.status,
                    self.info,
                    self.payed,
                ),
            )
            self.cur.execute("SELECT id from MagPosLog ORDER BY id DESC LIMIT 1")
            temp = self.cur.fetchone()

            assert isinstance(temp, tuple), "Cannot fetch id of new MagPosLog-Entry"
            self.id = temp[0]

        # Update Database entry
        self.cur.execute(
            "UPDATE MagPosLog SET cardnumber = ?, amount = ?, datum = ?, status = ?, info = ?, payed = ? WHERE id = ?",
            (
                self.cardnumber,
                unicode(self.amount),
                datetime.now(),
                self.status,
                self.info,
                self.payed,
                self.id,
            ),
        )
        self.con.commit()

    @staticmethod
    def save_transaction_result(cur, con, kartennummer, betrag, info):
        """
        Static function to save a transaction result
        :param cur: Database cursor
        :type cur: sqlite3.Cursor
        :param con: Database connection
        :type con: sqlite3.Connection
        :param kartennummer: Card number of the last transaction
        :type kartennummer: int
        :param betrag: Amount what should have been decreased
        :type betrag: float
        :param info: Information about success or error on transaction
        :type info: Info int
        """
        if isinstance(info, Info):
            info = new_info.value

        cur.execute(
            "INSERT INTO MagPosLog (cardnumber, amount, datum, status, info, payed) VALUES (?,?,?,?,?,?)",
            (
                kartennummer,
                unicode(betrag),
                datetime.now(),
                Status.transaction_result.value,
                info,
                info == Info.transaction_ok.value,
            ),
        )
        con.commit()

    @staticmethod
    def check_last_entry(cur, con):
        """
        Static function to check the last entry for errors
        :param cur: Database cursor
        :type cur: sqlite3.Cursor
        :param con: Database connection
        :type con: sqlite3.Connection
        :return: True if nothing found, False otherwise
        :rtype: Bool
        """

        cur.execute(
            "SELECT ID, Status,Info,Payed from MAGPOSLOG ORDER BY ID Desc LIMIT 1;"
        )
        for row in cur.fetchall():  # might be no entry yet
            entry_id = row[0]
            entry_payed = row[3] == 1
            entry_status = None
            entry_info = None
            try:
                entry_status = Status(row[1])
                entry_info = Info(row[2])
            except ValueError as e:
                logging.error(
                    u"MagPosLog: Last entry with ID {} has invalid Status or Info code".format(
                        entry_id
                    )
                )
                return False

            if entry_payed and entry_status == Status.decreasing_done:
                logging.error(
                    u"MagPosLog: Entry with ID{0} was not booked. Please review it for further action".format(
                        entry_id
                    )
                )
                return False

        return True
