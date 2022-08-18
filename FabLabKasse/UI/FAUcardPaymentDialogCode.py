#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#


import logging
from PyQt4 import QtGui, QtCore, Qt
from .uic_generated.FAUcardPaymentDialog import Ui_FAUcardPaymentDialog

from ..faucardPayment.faucardStates import Status, Info
from decimal import Decimal


class FAUcardPaymentDialog(QtGui.QDialog, Ui_FAUcardPaymentDialog):
    """
    The FAUcardPaymentDialog works as the GUI for the FAUcardThread. It informs the user about the current state
    of the payment process and gives the ability to hold and cancel the FAUcardThread. The process waits after each
    step untill the FAUcardPaymentDialog signals readyness to continue further.
    """

    # Signal to tell the FAUcardThread to send response acknowledge to the MagnaBox + optional cancel of the process
    response_ack = QtCore.pyqtSignal(bool)

    # Signal to tell the payment handler to terminate the thread
    request_termination = QtCore.pyqtSignal()

    def __init__(self, parent, amount):
        """
        Initializes the FAUcardPaymentDialog. It sets it's member variables and sets up the GUI, including
        a QTimer to periodically update the GUI to show life sign.
        :param parent: parent of the Dialog
        :type parent: QObject
        :param amount: Amount the user has to pay (only used to display)
        :type amount: Decimal
        """
        QtGui.QDialog.__init__(self, parent)
        logging.info("FAUcardPayment: started")
        self.setupUi(self)
        self.setModal(True)

        assert isinstance(
            amount, Decimal
        ), "PayupFAUCard: Amount to pay not Decimal or float"

        # Set up member variables and fill GUI
        self.amount = amount
        self.label_betrag.setText(f"{str(self.amount)} €".replace(".", ","))
        self.label_status.setText("Starte FAUcard-Zahlung\n")
        self.counter = 0
        self.thread_aborted = False
        self.thread_broken = False
        self.timer_terminate = QtCore.QTimer()
        self.timer_terminate.timeout.connect(self.request_thread_termination)
        self.timer_terminate.setSingleShot(True)
        self.status = Status.initializing

        # Start a timer to periodically update the GUI (show life sign)
        self.utimer = QtCore.QTimer()
        QtCore.QObject.connect(
            self.utimer, QtCore.SIGNAL("timeout()"), self.show_active
        )
        QtCore.QObject.connect(
            self.pushButton_abbrechen, QtCore.SIGNAL("clicked()"), self.reject
        )
        self.utimer.start(1000)

    @QtCore.pyqtSlot()
    def thread_terminated(self):
        """
        A Slot to recognize if the Thread was terminated and tell the user
        """
        logging.error("FAUcardPayment: Thread was terminated")
        self.thread_aborted = True
        self.update_gui([Info.unknown_error])

    @QtCore.pyqtSlot(bool)
    def set_cancel_button_enabled(self, enabled):
        """
        Sets self.pushButton_abbrechen.setEnabled to the given bool enabled
        :param enabled: bool if Button should be enabled
        :type enabled: bool
        """
        self.pushButton_abbrechen.setEnabled(enabled)

    @QtCore.pyqtSlot()
    def show_transaction_error(self):
        """
        A Slot to inform the user about an occured transaction error.
        """
        QtGui.QMessageBox.warning(
            self,
            "Zahlung mit FAU-Karte",
            "Das Programm hat einen Fehler in der Abbuchung \
                                  festgestellt.\nFalls dir von der Karte mehr abgebucht wurde als es sollte melde \
                                  dich bitte unter kasse@fablab.fau.de mit Datum, Uhrzeit und Betrag.",
        )

    @QtCore.pyqtSlot()
    def process_aborted(self):
        """
        SLOT is called by the process's process_aborted signal, which is emitted if the process terminated on an
        expected error
        thread_aborted must be set to be able to abort the payment
        """
        self.thread_aborted = True

    @QtCore.pyqtSlot(list)
    def update_gui(self, response):
        """
        Displays different Messages on the GUI according to the thread's response which executes the payment.
        :param response: List of response data. First index always contains Status code or Info code
        :type response: list[Status] list[Info]
        """
        assert isinstance(response, list), "Thread response no list!"
        assert len(response) > 0, "Thread response is empty!"
        assert isinstance(
            response[0], (Status, Info)
        ), "Thread response code is not Status or Info!"

        self.thread_broken = False
        if self.timer_terminate.isActive():
            self.timer_terminate.stop()

        if isinstance(response[0], Info):
            # Abort if checking the last transaction failed
            if response[0] == Info.check_transaction_failed:
                self.utimer.stop()
                self.label_status.setText(
                    "Letzte Transaktion konnte nicht überprüft werden.\nBitte wechseln Sie die Zahlungsmethode"
                )
                self.utimer.singleShot(10000, self.reject)
                return
            # Abort if balance underflow would occur
            elif response[0] == Info.balance_underflow:
                self.utimer.stop()
                self.label_status.setText(
                    "Zu wenig Guthaben\nBitte wechseln Sie die Zahlungsmethode"
                )
                self.utimer.singleShot(10000, self.reject)
                self.response_ack.emit(True)
                return
            # Abort on an unknown / not processable error
            elif response[0] == Info.unknown_error:
                logging.error("FAUcardPayment: terminated on error")
                self.utimer.stop()
                self.label_status.setText(
                    "Fehler\nBitte wechseln Sie die Zahlungsmethode"
                )
                self.response_ack.emit(True)
                return
            # Inform the user about the lost connection to the MagnaBox
            elif response[0] == Info.con_error:
                self.label_status.setText(
                    "Verbindung zum Terminal verloren.\n Versuche wieder zu verbinden"
                )
                logging.warning(
                    "FAUcardPayment: Verbindung zur MagnaBox beim abbuchen verloren."
                )
                return
            # Inform the user about the reestablished connection to the MagnaBox
            elif response[0] == Info.con_back:
                self.label_status.setText(
                    f"Verbindung zum Terminal wieder da.\nBuche {str(self.amount)}€ ab\n".replace(
                        ".", ","
                    )
                )
                logging.warning(
                    "FAUcardPayment: Verbindung zur MagnaBox wieder aufgebaut."
                )
                return

        elif isinstance(response[0], Status):
            self.status = response[0]
            # Initializing: Do nothing
            if response[0] == Status.initializing:
                self.response_ack.emit(False)
            # Initialized: Inform user to lay card on reader
            elif response[0] == Status.waiting_card:
                self.label_status.setText("Warte auf Karte\n")
                self.response_ack.emit(False)
            # Card and Balance read: Check if balance is enough and inform user the balance will be decreased
            elif (
                response[0] == Status.decreasing_balance
            ):  # Card and Balance recognized
                self.label_status.setText(
                    f"Buche {str(self.amount)}€ ab\n".replace(".", ",")
                )
                self.response_ack.emit(False)
            # Successfully decreased: Inform the user the payment is done and close after 2 seconds
            elif response[0] == Status.decreasing_done:
                self.utimer.stop()
                self.label_status.setText(
                    f"Vielen Dank für deine Zahlung von {str(self.amount)}.\nBitte das Aufräumen nicht vergessen!"
                )
                self.utimer.singleShot(5000, self.accept)
                self.response_ack.emit(False)
                self.pushButton_abbrechen.hide()
                logging.info("FAUcardPayment: successfully payed")

    @QtCore.pyqtSlot()
    def show_active(self):
        """
        Periodically updates the GUI to show sign of life
        Checks if payment thread is done
        """
        self.counter = (self.counter + 1) % 4
        if self.counter == 0:
            self.label_status.setText(self.label_status.text().replace(".", ""))
        else:
            self.label_status.setText(self.label_status.text() + ".")

        if self.thread_aborted is True:
            self.label_status.setText("Breche Bezahlung ab.")
            self.pushButton_abbrechen.hide()
            Qt.QTimer.singleShot(2000, self.reject_final)

    @QtCore.pyqtSlot()
    def reject(self):
        """
        SLOT that handles the abortion of the payment process.
        If the process terminated on error it trys to abort, otherwises it tries in 1 second (to let the process finish)
        """
        if not self.pushButton_abbrechen.isEnabled():
            QtGui.QMessageBox.warning(
                None,
                "FAUCard Zahlung",
                "Du kannst zu diesem Zeitpunkt nicht mehr abbrechen",
            )
            return

        if self.thread_aborted is not True:
            Qt.QTimer.singleShot(1000, self.try_reject)
        else:
            self.try_reject()

    @QtCore.pyqtSlot()
    def try_reject(self):
        """
        Tries to do the final abortion
        If the thread is still not finished, Tell the user that it waits for the thread to abort.
        If the thread is finished tell the user the process is aborting and process the final abortion in 2 seconds
        """
        if self.thread_aborted is not True:
            QtGui.QMessageBox.warning(
                None,
                "FAUCard Zahlung",
                "Abbrechen gerade nicht möglich.\nBitte warten Sie, bis das Programm an der nächst \
                                      möglichen Stelle abbricht. Beachte bitte, das falls dein Geld schon abgebucht \
                                      wurde, es nicht automatisch rückabgewickelt wird.",
            )
            self.label_status.setText("Warte auf Möglichkeit zum Abbruch")
            if not self.timer_terminate.isActive():
                self.timer_terminate.start(60000)
        else:
            self.label_status.setText("Breche Bezahlung ab.")
            self.pushButton_abbrechen.hide()
            self.timer_terminate.stop()
            Qt.QTimer.singleShot(2000, self.reject_final)

    @QtCore.pyqtSlot()
    def reject_final(self):
        """
        Final rejection of the Payment
        """
        QtGui.QDialog.reject(self)

    @QtCore.pyqtSlot()
    def request_thread_termination(self):
        """
        Sets the thread_broken flag to let the user terminate the thread if necessary.
        """
        self.thread_broken = True
        terminate = QtGui.QMessageBox.question(
            None,
            "FAUCard Zahlung",
            "Willst du den Thread terminieren? Wenn du dir nicht sicher bist, antworte mit nein.",
            QtGui.QMessageBox.Yes,
            QtGui.QMessageBox.No,
        )
        if terminate == QtGui.QMessageBox.Yes:
            logging.error("FAUcardPayment: thread termination was requested")
            self.request_termination.emit()
            Qt.QTimer.singleShot(500, self.reject_final)
