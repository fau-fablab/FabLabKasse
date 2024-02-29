#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

from __future__ import print_function
from __future__ import absolute_import
import codecs
import logging
import sqlite3
from qtpy import QtCore, QtWidgets
from decimal import Decimal
from datetime import datetime

from .faucardStates import Status, Info
from .MagPosLog import MagPosLog
from ..shopping.backend.abstract import float_to_decimal

from typing import List, Optional
from ..UI.FAUcardPaymentDialogCode import (
    FAUcardPaymentDialog,
)  # only needed for type annotations

try:  # Test if interface is available
    from .magpos import magpos, codes
except ImportError as e:  # Load Dummy otherwise
    logging.warning(
        "failed to import 'magpos' plugin class, falling back to dummy interface: "
        + repr(e)
    )
    print(e)
    from .dinterface import magpos, codes

    # BUG: mypy typechecking is unhappy with this; instead, e.g., magpos.xxx should subclass dinterface.xxx (or should have a common parent abstract class?)

from FabLabKasse import scriptHelper
from configparser import ConfigParser


class FAUcardThread(QtCore.QObject):
    """
    The FAUcardThread class is an QObject worker class which implements a routine to pay with the MagnaBox.
    It can work in a dedicated thread, but needs a FAUcardPaymentDialog as a GUI to get feedback from the user and system.
    """

    # Signal zum auslesen der Antwort
    response_ready = QtCore.Signal([list])
    # Signal signalieren eines Transaction Fehlers
    transaction_error = QtCore.Signal()
    # Signal to change the Enabled state of Dialogs cancel button
    set_cancel_button_enabled = QtCore.Signal(bool)
    # Signals process end
    process_aborted = QtCore.Signal()

    class UserAbortionError(Exception):
        def __init__(self, func: str) -> None:
            self.func = func

        def __str__(self) -> str:
            return "PayupFAUCard: User aborted at {}".format(self.func)

    class ConnectionError(Exception):
        def __str__(self) -> str:
            return "Could not establish connection to the MagnaBox"

    class BalanceUnderflowError(Exception):
        def __str__(self) -> str:
            return "Zu wenig Guthaben auf der FAU-Karte."

    class CheckLastTransactionFailed(Exception):
        def __str__(self) -> str:
            return "Failed to check last transaction"

    def __init__(
        self,
        dialog: FAUcardPaymentDialog,
        amount: Decimal,
        thread=QtCore.QThread.currentThread(),
    ) -> None:
        """
        Initializes the FAUcardThread. Needs to set up some runtime values and moves the whole class to a
        dedicated thread. To establish communication to the GUI it connects signals and slots to the GUI-Dialog
        :param dialog: GUI Dialog guiding the User
        :type dialog: FAUcardPaymentDialog
        :param amount: Amount to be paid
        :type amount: Decimal
        :param thread: Thread the process should work in
        :type thread: QtCore.QThread
        """
        self.cfg = scriptHelper.getConfig()
        QtCore.QObject.__init__(self)
        logging.info("FAU-Terminal: thread is being initialized")

        assert isinstance(amount, (Decimal)), "PayupFAUCard: Amount to pay not Decimal"

        # Initialize class variables
        self.status = Status.initializing
        self.info = Info.OK
        self.card_number: Optional[int] = None
        self.old_balance: Optional[int] = None
        self.new_balance: Optional[int] = None

        assert amount > 0
        self.amount = amount
        self.amount_cents = int(
            float_to_decimal(amount * 100, 0)
        )  # Floating point precision causes error -> round with float_to_decimal.
        self.cancel = False
        self.ack = False
        self.sleep_counter = 0
        self.last_sleep = 0
        self.should_finish_log = True

        self.timestamp_payed: Optional[datetime] = None

        # Can not create sql connection here, needs to be done in worker thread
        self.con: Optional[sqlite3.Connection] = None
        self.cur: Optional[sqlite3.Cursor] = None
        self.log: Optional[MagPosLog] = None
        self.pos: Optional[magpos.MagPOS] = None

        # Enable multithreading
        self.moveToThread(thread)
        # Connect signal and slots from GUI and thread
        self.response_ready.connect(dialog.update_gui, type=QtCore.Qt.QueuedConnection)
        self.transaction_error.connect(
            dialog.show_transaction_error, type=QtCore.Qt.QueuedConnection
        )
        self.set_cancel_button_enabled.connect(
            dialog.set_cancel_button_enabled, type=QtCore.Qt.QueuedConnection
        )
        self.process_aborted.connect(
            dialog.process_aborted, type=QtCore.Qt.QueuedConnection
        )
        dialog.response_ack[bool].connect(self.set_ack, type=QtCore.Qt.QueuedConnection)
        dialog.pushButton_abbrechen.clicked.connect(
            self.user_abortion, type=QtCore.Qt.QueuedConnection
        )
        dialog.rejected.connect(self.user_abortion, type=QtCore.Qt.QueuedConnection)
        thread.started.connect(self.run, type=QtCore.Qt.QueuedConnection)
        thread.finished.connect(
            dialog.thread_terminated, type=QtCore.Qt.QueuedConnection
        )
        thread.finished.connect(self.terminate, type=QtCore.Qt.QueuedConnection)

    # set response-flag
    @QtCore.Slot(bool)
    def set_ack(self, cf: bool) -> None:
        """
        Sets the Acknowledge flag and Cancel flag
        """
        logging.debug("FAUcardThread: Called set_ack with cancel_flag '{}'".format(cf))
        self.ack = True
        self.cancel = cf

    # set if thread should finish logfile with booking entry
    @QtCore.Slot(bool)
    def set_should_finish_log(self, val: bool) -> None:
        """
        Sets the finish logfile flag
        :param val: Contains information if the thread should finish the log file
        :type val: bool
        """
        self.should_finish_log = val

    @QtCore.Slot()
    def user_abortion(self) -> None:
        """sets cancel flag to cancel the payment"""
        self.cancel = True

    @QtCore.Slot()
    def terminate(self) -> None:
        """
        Terminates the Process on fatal Error
        """
        self.cancel = True
        self.info = Info.unknown_error
        self.response_ready.emit([Info.unknown_error])
        if self.log is not None:
            self.log.set_status(self.status, self.info)
        if self.pos is not None:
            self.pos.close()
        logging.info("Fau-Terminal: thread terminated")
        self.set_cancel_button_enabled.emit(True)

    def check_user_abort(self, msg: str) -> None:
        """
        Checks Eventloop to process SLOT-Calls from Dialog
        Checks if Cancel Flag was set and aborts process by Exception
        :param msg: Exception message
        :type msg: str
        """
        QtCore.QCoreApplication.processEvents()  # Retrieves SLOT event to get Dialog input
        if self.cancel == True:
            raise self.UserAbortionError(msg)

    def sleep(self, seconds: int) -> None:
        """Sleep function for the thread"""
        if seconds is 0:
            return

        counter = self.sleep_counter
        # BUG? what happens if sleep_counter accidentally (timing glitch, ...) becomes larger than seconds*10?
        while self.sleep_counter is not seconds * 10:
            if self.cancel == True:
                raise self.UserAbortionError("sleep")
            if counter == self.sleep_counter:
                QtCore.QTimer.singleShot(100, self.sleep_timer)
                counter += 1
            else:
                # Process SLOT calls to retrieve new sleep_counter
                QtCore.QCoreApplication.processEvents()

        self.sleep_counter = 0

    @QtCore.Slot()
    def sleep_timer(self) -> None:
        """Increases the sleep_counter by one"""
        self.sleep_counter += 1

    @QtCore.Slot()
    def quit(self) -> None:
        """
        Quits the Process on user cancel or balance underflow
        """
        self.cancel = True

        if self.info == Info.OK and self.status is not Status.decreasing_done:
            self.info = Info.user_abort
        if self.log is not None:
            self.log.set_status(self.status, self.info)
        if self.pos is not None:
            self.pos.close()
        self.set_cancel_button_enabled.emit(True)

    @QtCore.Slot()
    def run(self) -> None:
        """
        Billing routine for FAU-Card payment. Runs following steps:
        1. Check last transaction result
        2. Initialize log class and connection to MagnaBox
        3. Read the card the user puts on the reader
        4. Decrease the amount from card balance
        (Optional: 5. finish log file)
        After each step the routine waits till the GUI sends a positive feedback by set_ack slot.
        The GUI can send a cancel flag with the response_ack signal and is able to quit the process after every step.
        """
        # Cancel if aborted
        if self.cancel:
            self.quit()
            return

        # Init MagPosLog in worker thread
        self.con = sqlite3.connect(self.cfg.get("magna_carta", "log_file"))
        self.cur = self.con.cursor()
        self.con.text_factory = str
        self.log = MagPosLog(self.amount, self.cur, self.con)

        try:
            logging.debug("FAUcardThread: Checking for unacknowledged transaction")
            # 0. Check log file if last entry was not booked
            MagPosLog.check_last_entry(self.cur, self.con)

            # 1. Check last Transaction
            if not self.check_last_transaction(self.cur, self.con):
                raise self.CheckLastTransactionFailed

            logging.debug("FAUcardThread: Starting Connection")
            # 2. start connection
            self._start_connection()

            logging.debug("FAUcardThread: Reading Payment Card Information")
            # 3. read card
            self.card_number, self.old_balance = self._read_card()
            self.log.set_cardnumber(self.card_number)
            self.log.set_oldbalance(self.old_balance)
            logging.debug(
                "FAUcardThread: Card Number: {0} ; Old Balance: {1}".format(
                    self.card_number, self.old_balance
                )
            )

            # let user short time to stop transaction if wanted
            self.sleep(2)
            self.check_user_abort("Before decreasing")

            logging.debug("FAUcardThread: Decreasing balance of Payment Card")
            # 4. decrease balance
            self.new_balance = self._decrease_balance()
            self.log.set_newbalance(self.new_balance)
            self.log.set_timestamp_payed(self.timestamp_payed)
            logging.debug("FAUcardThread: New Balance: {}".format(self.new_balance))

            # 5. finish log entry
            if self.should_finish_log is True:
                self.finish_log()

        except (magpos.ResponseError, self.ConnectionError) as e:
            logging.error("FAUcardThread: {}".format(e))
            self.terminate()
        except magpos.TransactionError as e:
            logging.fatal("FAUcardThread: TransactionError occured\n{0}".format(e))
            self.transaction_error.emit()
            self.terminate()
        except (
            magpos.serial.SerialException,
            magpos.ConnectionTimeoutError,
            IOError,
        ) as e:
            logging.error(
                "FAUcardThread: serial exception forced termination\nException:\n{}".format(
                    e
                )
            )
            self.terminate()
        except self.UserAbortionError as e:
            logging.info(e)
            # User canceled.
            # Note: we do not need to call self.pos.response_ack() here. The previous code is responsible for that.
            self.quit()
        except self.BalanceUnderflowError as e:
            logging.info(e)
            self.response_ready.emit([Info.balance_underflow])
            self.info = Info.balance_underflow
            self.quit()
        except self.CheckLastTransactionFailed as e:
            self.response_ready.emit([Info.check_transaction_failed])
            self.info = Info.check_transaction_failed
            self.quit()
        except NotImplementedError as e:
            logging.error("FAUcardThread: MagPos not implemented, maybe dummy loaded.")
            self.terminate()
        except Exception:
            self.terminate()
            raise
        else:
            # close the connection to MagnaBox
            if self.pos is not None:
                self.pos.close()

        if self.info is not Info.OK:
            self.process_aborted.emit()
        logging.info("Fau-Terminal: thread finished")

    @staticmethod
    def check_last_transaction(cur: sqlite3.Cursor, con: sqlite3.Connection) -> bool:
        """
        Prüfe auf Fehler bei Zahlung mit der FAU-Karte und speichere das Ergebnis in MagPosLog
        :return: True if the check could be performed, False otherwise (does not take result of check into account)
        :rtype: bool
        :param cur: database cursor
        :type cur: sqlite3.Cursor
        :param con: database connection
        :type con: sqlite3.Connection
        """
        cfg = scriptHelper.getConfig()
        last_transaction_result = None
        try:
            pos = magpos.MagPOS(cfg.get("magna_carta", "device_port"))
            pos.start_connection()
            last_transaction_result = pos.get_last_transaction_result()
            # BUG? what happens if there is an Exception during Response_ACK? Should this be delayed to the end of the function? Rewrite "return False"-logic?
            pos.response_ack()
            pos.close()
        except (magpos.serial.SerialException, magpos.ConnectionTimeoutError):
            logging.error(
                "CheckTransaction: Magnabox COM-Port '{}', serial malfunction".format(
                    cfg.get("magna_carta", "device_port")
                )
            )
            return False
        except magpos.ResponseError as e:
            logging.error("CheckTransaction: {}".format(e))
            return False

        # Choose logging or nop based on check result
        if (
            last_transaction_result.status is magpos.codes.OK
        ):  # Last transaction was successful
            logging.error(
                "CheckTransaction: Kassenterminal ist während des letzten Bezahlvorgangs abgestürzt. Dem Benutzer wurde bereits Geld von der Karte abgebucht. Es gab wahrscheinlich noch KEINE Buchung im Kassenterminal."
            )
            logging.error(
                "CheckTransaction: Achtung - Manuelle Korrekturbuchung erforderlich!"
            )
            MagPosLog.save_transaction_result(
                cur,
                con,
                last_transaction_result.card_number,
                Decimal(last_transaction_result.amount) / 100,
                Info.transaction_ok.value,
            )
            logging.error(
                "CheckTransaction: Buchung für Karte {0} über Betrag {1} EURCENT fehlt".format(
                    last_transaction_result.card_number, last_transaction_result.amount
                )
            )
        elif (
            last_transaction_result.status == 0
            and last_transaction_result.card_number == 0
            and last_transaction_result.amount == 0
        ):  # Last transaction was acknowledged
            pass
        else:  # Failure during last transaction
            logging.warning(
                "CheckTransaction: Kassenterminal ist während des letzten Bezahlvorgangs abgestürzt. Dem Benutzer wurde noch KEIN Geld von der Karte abgebucht. Es gab KEINE Buchung im Kassenterminal. Dieser Fehler ist harmlos."
            )
            MagPosLog.save_transaction_result(
                cur,
                con,
                last_transaction_result.card_number,
                Decimal(last_transaction_result.amount) / 100,
                Info.transaction_error.value,
            )

        return True

    def _start_connection(self) -> None:
        """
        Initializes connection to MagnaBox by following steps:
        1. Logs status initializing
        2. Creates the MagPos Object
        3. sends start_connection command
        4. Sets display mode
        """
        assert self.log is not None

        # 1. Log status
        self.status = Status.initializing
        self.log.set_status(self.status, self.info)

        # 2. Create MagPos Object
        self.pos = magpos.MagPOS(self.cfg.get("magna_carta", "device_port"))
        # 3. Try to start connection
        if not self.pos.start_connection():
            raise self.ConnectionError()

        # 4. Set display mode
        self.pos.set_display_mode()

        # Update GUI and wait for response
        self.response_ready.emit([Status.waiting_card])
        self._wait_for_ack()

    def _read_card(
        self,
    ) -> List[
        int
    ]:  # BUG: change from List[int] to Tuple[int, int] and change the code accordingly. Lists are only for variable length structures.
        """
        Waits till there is a card on the reader and reads its data by following steps:
        1. Log Status "waiting for card"
        2. Check MagnaBox flag if there is a card on reader until its True
        3. Try to read the card data, ignore the NO_CARD Error if user took the card away again
        4. Check if the decreasing would end in balance underflow and stop routine at that point if True
        :return: Card number and old balance on success
        :rtype: list[int,int]
        """

        assert self.log is not None
        assert self.pos is not None

        # 1. Log status
        self.status = Status.waiting_card
        self.log.set_status(self.status, self.info)

        # 2. Check if card on reader
        while True:
            self.check_user_abort("read card: is card on reader?")
            if self.pos.card_on_reader():  # Is there a card on reader?
                break

        # 3. Read card data
        retry = True
        while retry is True:
            self.check_user_abort("read card: read card data")
            try:
                card_number, old_balance = self.pos.get_long_card_number_and_balance()
                retry = False
            except magpos.ResponseError as e:
                if e.code != magpos.codes.NO_CARD:
                    raise e
                else:
                    # here retry is still True => stay in while loop
                    pass

        # 4. Check if enough balance on card
        if old_balance < self.amount_cents:
            raise self.BalanceUnderflowError()

        # Update GUI and wait for response
        self.response_ready.emit([Status.decreasing_balance])
        self._wait_for_ack()

        return [card_number, old_balance]

    def _decrease_balance(self) -> int:
        """
        Decreases card balance by self.amount_cents by following steps:
        1. Try to decrease balance
         -> a: Successful
            2. Continue with step 5
         -> b: Connection was lost?
            2. Try to reestablish connection, ignore connection relevant errors
            3. Check if the payment you tried has been successfully executed
             -> a: was successfully executed:
                4. Continue with step 5
             -> b: the payment was not executed:
                4: Go back to step 1
             -> c: it is unclear if the payment was executed or not:
                4. Quit the process by raising an Exception
        5. Check if payment was correct and log it
        :return: New balance on success. Otherwise an exception will be raised.
        :rtype: int
        :param card_number: Card number the balance should be decreased off
        :type card_number: int
        :param old_balance: The old balance of the card
        :type old_balance: int
        """

        assert self.log is not None
        assert self.pos is not None
        assert self.amount_cents is not None
        assert self.card_number is not None
        assert self.old_balance is not None

        # Log new status
        self.status = Status.decreasing_balance
        self.log.set_status(self.status, self.info)

        new_balance = 0
        retry = True
        lost = False

        decrease_result = None

        # 1. Try to decrease balance
        while retry:
            retry = False
            self.set_cancel_button_enabled.emit(
                True
            )  # User must be able to abort if he decides to
            try:
                self.check_user_abort(
                    "decreasing balance: User Aborted"
                )  # Will only be executed if decrease command has not yet been executed
                logging.debug("FAUcard: Trying to decrease balance")
                decrease_result = self.pos.decrease_card_balance_and_token(
                    self.amount_cents, self.card_number
                )

            # Catch ResponseError if not Card on Reader and retry
            except magpos.ResponseError as e:
                if e.code is magpos.codes.NO_CARD:
                    logging.info("FAUcard: No card, retrying...")
                    self.pos.response_ack()
                    retry = True
                    continue
                else:
                    raise e
            # 1.b Connection error
            except (
                magpos.serial.SerialException,
                magpos.ConnectionTimeoutError,
                IOError,
            ) as e:
                logging.warning("FAUcardThread: {0}".format(e))
                self.info = Info.con_error
                self.log.set_status(self.status, self.info)
                self.response_ready.emit([Info.con_error])
                lost = True

            # Abortion of the process not allowed
            # self.set_cancel_button_enabled.emit(False)
            # Clear cancel Flag if user tried to abort: no abortion allowed after this tep
            QtCore.QCoreApplication.processEvents()
            self.cancel = False

            # if connection lost (1.b)
            if lost:
                logging.warning("FAUcard: connection lost (1.b)")
                last_transaction_result: Optional[magpos.LastTransactionResult] = None
                while lost:
                    lost = False

                    logging.debug("FAUcard: 2 Try to reastablish connect")
                    try:
                        # release serial port
                        self.pos.close()

                        # retry serial connection
                        self.pos = magpos.MagPOS(
                            self.cfg.get("magna_carta", "device_port")
                        )

                        # clear previous command and response
                        self.pos.start_connection()

                        # 3. Check transaction result
                        last_transaction_result = self.pos.get_last_transaction_result()

                    # Ignore expected errors
                    except (
                        magpos.serial.SerialException,
                        magpos.ConnectionTimeoutError,
                        IOError,
                    ):
                        lost = True

                self.info = Info.con_back
                self.response_ready.emit([Info.con_back])

                assert (
                    last_transaction_result is not None
                )  # None is not possible because last_transaction_result = self.pos.get_last_transaction_result() must have been called
                assert self.old_balance is not None

                # 3. Check last payment details
                if (
                    last_transaction_result.status == magpos.codes.OK
                    and last_transaction_result.card_number == self.card_number
                    and last_transaction_result.amount == self.amount_cents
                ):
                    logging.info("FAUcard: 3.a The payment was successfully executed")
                    decrease_result = magpos.DecreaseCardBalanceAndTokenResult(
                        card_number=last_transaction_result.card_number,
                        old_balance=self.old_balance,
                        new_balance=self.old_balance - self.amount_cents,
                        token_id=0,  # token id is not used
                    )
                    # Note: Response-ACK will be sent later, at the very end of this function.
                    break
                elif last_transaction_result.status in [
                    magpos.codes.BALANCE_UNDERFLOW_OR_OVERFLOW,
                    magpos.codes.USER_CANCELLED,
                    magpos.codes.NO_CARD,
                    magpos.codes.TOKEN_UNDERFLOW,
                ]:
                    logging.info("FAUcard: 3.b The payment was not executed. Retrying.")
                    retry = True
                    self.pos.response_ack()  # Note: if we get a broken connection here, the whole function will raise an Exception, the whole payment process will fail, and the case will be handled by check_last_transaction at the start of the next payment.
                    continue
                else:
                    # Unexpected status or wrong amount or card number

                    # TODO: General: check usage of self.log.set_status, sometimes the status/info is changed without calling log.set_status. --> Add a setter/getter for status/info? Or a "update_status" function?
                    # TODO: General: check usage of Status values. Some of the defined values like Status.balance_underflow or Status.unknown_error are never used.
                    logging.error(
                        "FAUcard: 3.c Cannot determine whether the payment was executed or not: Unexpected reply after reconnect. This is a serious error."
                    )
                    # Note: we do not send a response-ACK here since we don't know what to do. The case will be handled by check_last_transaction at the start of the next payment.
                    raise magpos.TransactionError(
                        card=self.card_number,
                        old=float("NaN"),
                        new=float("NaN"),
                        amount=self.amount_cents,
                    )

        assert (
            decrease_result is not None
        )  # decrease_result has been set either in case 1a or in case 3a

        # 5. Check if payment was correct and log it
        if (
            decrease_result.card_number == self.card_number
            and decrease_result.old_balance == self.old_balance
            and (decrease_result.new_balance + self.amount_cents) == self.old_balance
        ):
            logging.info("FAUCard: payment correct, writing to log")
            self.status = Status.decreasing_done
            self.info = Info.OK
            self.log.set_status(self.status, self.info)
            new_balance = decrease_result.new_balance
        else:
            logging.error(
                "FAUCard: Payment went wrong (double booking, wrong amount, or similar error). This is a serious error. Check kassenbuch, the MagPosLog database, and gui.log to find out what exactly went wrong."
            )
            raise magpos.TransactionError(
                card=decrease_result.card_number,
                old=decrease_result.old_balance,
                new=decrease_result.new_balance,
                amount=self.amount_cents,
            )

        self.timestamp_payed = datetime.now()
        # Update GUI. Do not wait for response because it is important that the result gets returned and later written to the database, independent of what the UI does.
        self.response_ready.emit([Status.decreasing_done])

        # Send ACK to decrease_card_balance_and_token command (1.a) or to get_last_transaction_result command (3.a)
        self.pos.response_ack()
        return new_balance

    def _wait_for_ack(self) -> None:
        """
        Waits for Acknowledge of the controlling Dialog,
        to send an acknowledge to the MagnaBox and continue the process.

        WARNING: This function calls check_user_abort().
        Do not call it in process steps where user abortion is not allowed (e.g. between decreasing balance and saving to the database).

        TODO: Why is this function needed?
        """
        while self.ack is False:
            self.check_user_abort("wait for acknowledge")  # contains processEvents
        self.ack = False

    def finish_log(self, info=Info.OK) -> None:
        """
        Finishes the log file after the GUI has done the booking.
        :param info: The info code for booking process
        :type info: Info
        """
        assert self.log is not None
        self.status = Status.booking_done
        self.info = info
        self.log.set_status(self.status, self.info)

    def get_amount_payed(self) -> Decimal:
        """
        Returns the amount the card has been decreased
        :return: amount payed if transaction complete, 0 otherwise
        :rtype: decimal
        """
        if (
            self.card_number is not None
            and self.new_balance is not None
            and self.old_balance is not None
        ):
            payed = Decimal(self.old_balance - self.new_balance)
            payed = payed / 100
            return payed
        else:
            return Decimal(0)
