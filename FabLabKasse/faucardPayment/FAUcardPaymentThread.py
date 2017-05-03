#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#

import codecs
import logging
import sqlite3
from PyQt4 import QtCore, Qt
from decimal import Decimal
from datetime import datetime

from faucardStates import Status, Info
from MagPosLog import MagPosLog
from ..shopping.backend.abstract import float_to_decimal


try:                    # Test if interface is available
    from magpos import magpos, codes
except ImportError as e:     # Load Dummy otherwise
    print e
    from dinterface import magpos, codes

from FabLabKasse import scriptHelper
from ConfigParser import ConfigParser


class FAUcardThread(QtCore.QObject):
    """
    The FAUcardThread class is an QObject worker class which implements a routine to pay with the MagnaBox.
    It can work in a dedicated thread, but needs a FAUcardPaymentDialog as a GUI to get feedback from the user and system.
    """

    # Signal zum auslesen der Antwort
    response_ready = QtCore.pyqtSignal([list])
    # Signal signalieren eines Transaction Fehlers
    transaction_error = QtCore.pyqtSignal()
    # Signal to change the Enabled state of Dialogs cancel button
    set_cancel_button_enabled = QtCore.pyqtSignal(bool)
    # Signals process end
    process_aborted = QtCore.pyqtSignal()

    class UserAbortionError(Exception):
        def __init__(self, func):
            self.func = func

        def __str__(self):
            return "PayupFAUCard: User aborted at {}".format(self.func)

    class ConnectionError(Exception):
        def __str__(self):
            return "Could not establish connection to the MagnaBox"

    class BalanceUnderflowError(Exception):
        def __str__(self):
            return "Zu wenig Guthaben auf der FAU-Karte."

    class CheckLastTransactionFailed(Exception):
        def __str__(self):
            return "Failed to check last transaction"

    def __init__(self, dialog, amount, thread=QtCore.QThread.currentThread()):
        """
        Initializes the FAUcardThread. Needs to set up some runtime values and moves the whole class to a
        dedicated thread. To establish communication to the GUI it connects signals and slots to the GUI-Dialog
        :param dialog: GUI Dialog guiding the User
        :type dialog: FAUcardPaymentDialog
        :param amount: Amount to be paid
        :type amount: float
        :param thread: Thread the process should work in
        :type thread: Qt.QThread
        """
        self.cfg = scriptHelper.getConfig()
        QtCore.QObject.__init__(self)
        logging.info("FAU-Terminal: thread is being initialized")

        assert isinstance(amount, (Decimal)), "PayupFAUCard: Amount to pay not Decimal"
        
        # Initialize class variables
        self.status = Status.initializing
        self.info = Info.OK
        self.card_number = 0
        self.old_balance = 0
        self.new_balance = 0
        self.amount = amount
        self.amount_cents = int(float_to_decimal(amount * 100, 0))		# Floating point precision causes error -> round with float_to_decimal.
        self.cancel = False
        self.ack = False
        self.sleep_counter = 0
        self.last_sleep = 0
        self.should_finish_log = True

        self.timestamp_payed = None

        # Can not create sql connection here, needs to be done in worker thread
        self.con = None
        self.cur = None
        self.log = None
        self.pos = None

        # Enable multithreading
        self.moveToThread(thread)
        # Connect signal and slots from GUI and thread
        self.response_ready.connect(dialog.update_gui, type=QtCore.Qt.QueuedConnection)
        self.transaction_error.connect(dialog.show_transaction_error, type=QtCore.Qt.QueuedConnection)
        self.set_cancel_button_enabled.connect(dialog.set_cancel_button_enabled, type=QtCore.Qt.QueuedConnection)
        self.process_aborted.connect(dialog.process_aborted, type=QtCore.Qt.QueuedConnection)
        dialog.response_ack[bool].connect(self.set_ack, type=QtCore.Qt.QueuedConnection)
        dialog.pushButton_abbrechen.clicked.connect(self.user_abortion, type=QtCore.Qt.QueuedConnection)
        dialog.rejected.connect(self.user_abortion, type= QtCore.Qt.QueuedConnection)
        thread.started.connect(self.run, type=QtCore.Qt.QueuedConnection)
        thread.terminated.connect(dialog.thread_terminated, type=QtCore.Qt.QueuedConnection)
        thread.terminated.connect(self.terminate, type=QtCore.Qt.QueuedConnection)

    # set response-flag
    @QtCore.pyqtSlot(bool)
    def set_ack(self, cf):
        """
        Sets the Acknowledge flag and Cancel flag
        """
        logging.debug("FAUcardThread: Called set_ack with cancel_flag '{}'".format(cf))
        self.ack = True
        self.cancel = cf

    # set if thread should finish logfile with booking entry
    @QtCore.pyqtSlot(bool)
    def set_should_finish_log(self, val):
        """
        Sets the finish logfile flag
        :param val: Contains information if the thread should finish the log file
        :type val: bool
        """
        self.should_finish_log = val


    @QtCore.pyqtSlot()
    def user_abortion(self):
        """ ets cancel flag to cancel the payment """
        self.cancel = True

    @QtCore.pyqtSlot()
    def terminate(self):
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

    def check_user_abort(self, msg):
        """
        Checks Eventloop to process SLOT-Calls from Dialog
        Checks if Cancel Flag was set and aborts process by Exception
        :param msg: Exception message
        :type msg: str
        """
        QtCore.QCoreApplication.processEvents()  # Retrieves SLOT event to get Dialog input
        if self.cancel == True:
            raise self.UserAbortionError(msg)

    def sleep(self, seconds):
        """ Sleep function for the thread """
        if seconds is 0:
            return

        counter = self.sleep_counter
        while self.sleep_counter is not seconds*10:
            if self.cancel == True:
                raise self.UserAbortionError("sleep")
            if counter == self.sleep_counter:
                Qt.QTimer.singleShot(100, self.sleep_timer)
                counter += 1
            else:
                # Process SLOT calls to retrieve new sleep_counter
                QtCore.QCoreApplication.processEvents()

        self.sleep_counter = 0

    @QtCore.pyqtSlot()
    def sleep_timer(self):
        """ Increases the sleep_counter by one"""
        self.sleep_counter +=1

    @QtCore.pyqtSlot()
    def quit(self):
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

    @QtCore.pyqtSlot()
    def run(self):
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
        self.con = sqlite3.connect(self.cfg.get('magna_carta', 'log_file'))
        self.cur = self.con.cursor()
        self.con.text_factory = unicode
        self.log = MagPosLog(self.amount, self.cur, self.con)

        try:
            # 1. Check last Transaction
            if not self.check_last_transaction(self.cur, self.con):
                raise self.CheckLastTransactionFailed

            # 2. start connection
            self._start_connection()

            # 3. read card
            value = self._read_card()
            self.card_number = value[0]
            self.log.set_cardnumber(self.card_number)
            self.old_balance = value[1]
            self.log.set_oldbalance(self.old_balance)


            # let user short time to stop transaction if wanted
            self.sleep(2)
            self.check_user_abort("Before decreasing")

            # 4. decrease balance
            self.new_balance = self._decrease_balance()
            self.log.set_newbalance(self.new_balance)
            self.log.set_timestamp_payed(self.timestamp_payed)

            # 5. finish log entry
            self._wait_for_ack()
            if self.should_finish_log is True:
                self.finish_log()

        except (magpos.ResponseError, self.ConnectionError) as e:
            logging.error("FAUcardThread: {}".format(e))
            self.terminate()
        except magpos.TransactionError as e:
            logging.fatal("FAUcardThread: TransactionError occured\n{0}".format(e))
            self.transaction_error.emit()
            self.terminate()
        except (magpos.serial.SerialException, magpos.ConnectionTimeoutError, IOError) as e:
            logging.error("FAUcardThread: serial exception forced termination\nException:\n{}".format(e))
            self.terminate()
        except self.UserAbortionError as e:
            logging.info(e)
            if self.status is Status.decreasing_balance and self.info is not Info.con_error:
                self.pos.response_ack()  # Befehl zum abbuchen löschen
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
    def check_last_transaction(cur, con):
        """
        Prüfe auf Fehler bei Zahlung mit der FAU-Karte und speichere das Ergebnis in MagPosLog
        :return: True on success, False otherwise
        :rtype: bool
        :param cur: database cursor
        :type cur: sqlite3.Cursor
        :param con: database connection
        :type con: sqlite3.Connection
        """
        cfg = scriptHelper.getConfig()
        value = [False]
        try:
            pos = magpos.MagPOS(cfg.get('magna_carta', 'device_port'))
            if pos.start_connection() is True:
                value = pos.get_last_transaction_result()
                pos.response_ack()
            pos.close()
        except (magpos.serial.SerialException, magpos.ConnectionTimeoutError):
            logging.error("CheckTransaction: Magnabox COM-Port '{}', serial malfunction".format(
                          cfg.get('magna_carta', 'device_port')))
            return False
        except magpos.ResponseError as e:
            logging.error("CheckTransaction: {}".format(e))
            return False

        if value[0] is magpos.codes.OK:  # Last transaction was successful
            logging.warning("CheckTransaction: Kassenterminal vor erfolgreicher Buchung abgestürzt.")
            MagPosLog.save_transaction_result(cur, con, value[1], Decimal(value[2])/100, Info.transaction_ok.value)
            logging.warning(u"CheckTransaction: Buchung für Karte {0} über Betrag {1} EURCENT fehlt".format(value[1], value[2]) )
        elif value[0] is 0 and value[1] is 0 and value[2] is 0:  # Last transaction was acknowledged
            return True
        else:  # Failure during last transaction
            logging.warning("CheckTransaction: Letzter Bezahlvorgang nicht erfolgreich ausgeführt.")
            MagPosLog.save_transaction_result(cur, con, value[1], Decimal(value[2])/100, Info.transaction_error.value)

        return True

    def _start_connection(self):
        """
        Initializes connection to MagnaBox by following steps:
        1. Logs status initializing
        2. Creates the MagPos Object
        3. sends start_connection command
        4. Sets display mode
        """
        # 1. Log status
        self.status = Status.initializing
        self.log.set_status(self.status, self.info)

        # 2. Create MagPos Object
        self.pos = magpos.MagPOS(self.cfg.get('magna_carta', 'device_port'))
        # 3. Try to start connection
        if not self.pos.start_connection():
            raise self.ConnectionError()

        # 4. Set display mode
        self.pos.set_display_mode()

        # Update GUI and wait for response
        self.response_ready.emit([Status.waiting_card])
        self._wait_for_ack()

    def _read_card(self):
        """
        Waits till there is a card on the reader and reads its data by following steps:
        1. Log Status "waiting for card"
        2. Check MagnaBox flag if there is a card on reader until its True
        3. Try to read the card data, ignore the NO_CARD Error if user took the card away again
        4. Check if the decreasing would end in balance underflow and stop routine at that point if True
        :return: Card number and old balance on success, [0,0] otherwise
        :rtype: list[int,int]
        """
        # 1. Log status
        self.status = Status.waiting_card
        self.log.set_status(self.status, self.info)

        card_number = 0
        old_balance = 0
        value = False

        # 2. Check if card on reader
        while value is not True:
            self.check_user_abort("read card: is card on reader?")
            value = self.pos.card_on_reader()  # Is there a card on reader?

        # 3. Read card data
        retry = True
        while retry is True:
            self.check_user_abort("read card: read card data")
            try:
                retry = False
                value = self.pos.get_long_card_number_and_balance()
                card_number = value[0]
                old_balance = value[1]
            except magpos.ResponseError as e:
                if e.code is magpos.codes.NO_CARD:
                    retry = True
                else:
                    raise e

        # 4. Check if enough balance on card
        if old_balance < self.amount_cents:
            raise self.BalanceUnderflowError()

        # Update GUI and wait for response
        self.response_ready.emit([Status.decreasing_balance])
        self._wait_for_ack()

        return [card_number, old_balance]

    def _decrease_balance(self):
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
             -> b: it aborted on error:
                4. Quit the process
             -> c: the transaction has not been executed:
                4: Go back to step 1
        5. Check if payment was correct and log it
        :return: New balance on success, 0 otherwise
        :rtype: int
        :param card_number: Card number the balance should be decreased off
        :type card_number: int
        :param old_balance: The old balance of the card
        :type old_balance: int
        """
        # Log new status
        self.status = Status.decreasing_balance
        self.log.set_status(self.status, self.info)

        new_balance = 0
        retry = True
        lost = False

        value = []

        while retry:
            retry = False
            self.set_cancel_button_enabled.emit(True)   # User must be able to abort if he decides to
            # 1. Try to decrease balance
            try:
                self.check_user_abort("decreasing balance: User Aborted")  # Will only be executed if decrease command has not yet been executed
                value = self.pos.decrease_card_balance_and_token(self.amount_cents, self.card_number)

            # Catch ResponseError if not Card on Reader and retry
            except magpos.ResponseError as e:
                if e.code is magpos.codes.NO_CARD:
                    self.pos.response_ack()
                    retry = True
                    continue
                else:
                    raise e
            # 1.b Connection error
            except (magpos.serial.SerialException, magpos.ConnectionTimeoutError, IOError), e:
                logging.warning("FAUcardThread: {0}".format(e))
                self.Info = Info.con_error
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
                value = []
                while lost:
                    lost = False

                    # 2 Try to reastablish connect
                    try:
                        # release serial port
                        self.pos.close()

                        # retry serial connection
                        self.pos = magpos.MagPOS(self.cfg.get('magna_carta', 'device_port'))

                        # clear previous command and response
                        self.pos.start_connection()

                        # 3. Check transaction result
                        value = self.pos.get_last_transaction_result()

                    # Ignore expected errors
                    except (magpos.serial.SerialException, magpos.ConnectionTimeoutError, IOError):
                        lost = True

                self.Info = Info.con_back
                self.response_ready.emit([Info.con_back])

                # 3. Check last payment details
                if value[1] == self.card_number and value[2] == self.amount_cents:
                    if value[0] == magpos.codes.OK:
                        # 3.a The payment was successfully executed
                        value[0] = value[1]
                        value[1] = self.old_balance
                        value[2] = self.old_balance - self.amount_cents
                        break
                    else:
                        # 3.b The payment aborted on error
                        self.response_ready.emit([Info.unknown_error])
                        self.info = Info.unknown_error
                        self.quit()
                        return
                else:
                    # 3.b The transaction has not been executed
                    retry = True
                    continue

        # 5. Check if payment was correct and log it
        if value[0] == self.card_number and value[1] == self.old_balance and (value[2]+self.amount_cents) == self.old_balance:
            self.status = Status.decreasing_done
            self.info = Info.OK
            self.log.set_status(self.status, self.info)
            new_balance = value[2]
        else:
            raise magpos.TransactionError(value[0], value[1], value[2], self.amount_cents)


        self.timestamp_payed = datetime.now()
        # Update GUI and wait for response
        self.response_ready.emit([Status.decreasing_done])

        self._wait_for_ack()
        self.pos.response_ack()
        return new_balance

    def _wait_for_ack(self):
        """
        Waits for Acknowledge of the controlling Dialog,
        to send an acknowledge to the MagnaBox and continue the process
        """
        while self.ack is False:
            self.check_user_abort("wait for acknowledge")  # contains processEvents
        self.ack = False

    def finish_log(self, info=Info.OK):
        """
        Finishes the log file after the GUI has done the booking.
        :param info: The info code for booking process
        :type info: Info
        """
        self.status = Status.booking_done
        self.info = info
        self.log.set_status(self.status, self.info)

    def get_amount_payed(self):
        """
        Returns the amount the card has been decreased
        :return: amount payed if transaction complete, 0 otherwise
        :rtype: decimal
        """
        if self.card_number != 0 and self.new_balance != 0 and self.old_balance != 0:
            payed = Decimal(self.old_balance-self.new_balance)
            payed = payed/100
            return payed
        else:
            return Decimal(0)
