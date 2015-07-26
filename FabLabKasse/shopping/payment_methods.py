# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Timo Voigt <timo@fablab.fau.de>
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program. If not,
# see <http://www.gnu.org/licenses/>.

"payment methods and their business logic"

import logging
from abc import ABCMeta, abstractmethod  # abstract base class support
from PyQt4 import QtGui
from decimal import Decimal
from ..UI.ClientDialogCode import SelectClientDialog
from ..UI.PayupCashDialogCode import PayupCashDialog
from ..UI.PayupManualDialogCode import PayupManualDialog
from .. import scriptHelper
from backend.abstract import DebtLimitExceeded

# to register a new payment method, add it to the list at the bottom of this file


class AbstractPaymentMethod(object):

    "interface for payment methods"
    __metaclass__ = ABCMeta

    def __init__(self, parent, shopping_backend, amount_to_pay):
        """
        parent: handle for main window - for Qt usage

        shopping_backend: ShoppingBackend instance

        amount_to_pay: Decimal value (rounded to cents) of requested amount
        """
        self.parent = parent
        self.shopping_backend = shopping_backend
        self.amount_to_pay = amount_to_pay
        self.successful = None
        self.amount_paid = None
        self.amount_returned = None
        self.print_receipt = False
        self.receipt_order_id = shopping_backend.get_current_order()

    def __repr__(self):
        return u"<{}(amount_to_pay={}, amount_paid={}, amount_returned={}, successful={}, ...)>".format(type(self).__name__, self.amount_to_pay, self.amount_paid, self.amount_returned, self.successful)

    @abstractmethod
    def _show_dialog(self):
        """show a GUI dialog and start payment. block until dialog has finished."""
        pass

    def show_thankyou(self):
        """ show a generic thank-you messge dialog. this is called after the dialog has ended. """
        QtGui.QMessageBox.information(self.parent, "", u"Vielen Dank für deine Zahlung von {}.\nBitte das Aufräumen nicht vergessen!".format(self.shopping_backend.format_money(self.amount_paid - self.amount_returned)))

    @staticmethod
    def is_enabled(cfg):
        """
        is this payment method available?

        cfg: configuration from ScriptHelper.getConfig()
        """
        return False

    @staticmethod
    def get_title():
        """ return human-readable name of payment method """
        return "title not implemented"

    @staticmethod
    def is_charge_on_client():
        """ return False for normal payment (cash), True for virtual payment on client account """
        return False

    def execute_and_store(self):
        """show dialog, make payment, store in shopping_backend, show thankyou message

        (if possible, only override _show_dialog and not this method)

        update attributes for return state:

        self.successful
        if False the payment-process has to be retried, otherwise the transaction is complete

        self.amount_paid
        describes the amount of money, which has been inserted into the machine

        self.amount_returned
        describes the amount of money, that the machine returned to the user


        there are four possible cases of return values:

        paid normally: (success == True) and (amount_paid - amount_returned == amount_to_pay)

        extra donation during payment process: (success == True) and (amount_paid - amount_returned > amount_to_pay)

        payment aborted normally: (success == False) and (amount_paid == amount_returned)

        payment aborted, but some part of the paid money could not be paid out again (e.g. because the machine can accept but not dispense 1cent coins):
            (success == False) and (amount_paid > amount_returned)
        """
        self._show_dialog()
        assert self.amount_paid >= self.amount_returned
        if not self.successful:
            amount_not_paid_back = self.amount_paid - self.amount_returned
            if amount_not_paid_back == 0:
                # completely refunded aborted payment - no receipt necessary
                self.print_receipt = False
            else:
                logging.info("cannot pay back everything of aborted payment. issuing receipt for the remaining rest.")

                self.print_receipt = True
                old_order = self.shopping_backend.get_current_order()
                # create a new, separate order for the non-paid-back rest
                # set it as paid
                # and print a receipt for it
                new_order = self.shopping_backend.create_order()
                self.receipt_order_id = new_order
                self.shopping_backend.set_current_order(new_order)
                # todo add to cfg tests at startup
                prod_id = scriptHelper.getConfig().getint('payup_methods', 'payout_impossible_product_id')
                self.shopping_backend.add_order_line(prod_id, amount_not_paid_back)
                assert self.shopping_backend.get_current_total() == self.amount_paid, "adding product for 'impossible payout' failed"
                self.shopping_backend.pay_order(self)

                # switch back to old order
                self.shopping_backend.set_current_order(old_order)
            return
        if self.successful:
            if self.amount_paid > self.amount_to_pay:
                # Modify sale order according to overpayment
                # rather handle these two calls in shoppingBackend??
                logging.info("user paid more than requested - adding product for overpayment to current order")
                prod_id = scriptHelper.getConfig().getint('payup_methods', 'overpayment_product_id')
                self.shopping_backend.add_order_line(prod_id, self.amount_paid - self.amount_to_pay)
                assert self.shopping_backend.get_current_total() == self.amount_paid, "adding product for overpayment failed"
            self.shopping_backend.pay_order(self)
        return self.successful


class AbstractClientPaymentMethod(AbstractPaymentMethod):

    "interface for payment methods"
    __metaclass__ = ABCMeta

    @staticmethod
    def is_charge_on_client():
        return True


class ClientPayment(AbstractClientPaymentMethod):

    @staticmethod
    def is_enabled(cfg):
        return cfg.getboolean('payup_methods', 'client')

    @staticmethod
    def get_title():
        return "Kundenkonto + PIN"

    def show_thankyou(self):
        pass  # we already show our own thankyou dialog.

    def _show_dialog(self):
        client_diag = SelectClientDialog(parent=self.parent, shopping_backend=self.shopping_backend)
        okay = client_diag.exec_()
        self.successful = bool(okay)
        self.client = client_diag.getClient()

    def execute_and_store(self):
        self._show_dialog()
        self.amount_paid = 0
        self.amount_returned = 0
        self.print_receipt = False  # never allow receipts because the account money is pre- or postpaid and for these payments there will be an extra receipt.

        if not self.successful:
            return

        try:
            new_debt = self.shopping_backend.pay_order_on_client(self.client)
            QtGui.QMessageBox.information(self.parent, "Information", u"Vielen Dank.\n Dein neuer Kontostand beträgt " +
                                          u"{}. \n(Positiv ist Guthaben)".format(self.shopping_backend.format_money(-new_debt)))
            self.amount_paid = self.amount_to_pay
            self.successful = True
        except DebtLimitExceeded, e:
            self.successful = False
            msgBox = QtGui.QMessageBox(self.parent)
            msgBox.setText(e.message)
            msgBox.setIcon(QtGui.QMessageBox.Warning)
            msgBox.exec_()


class ManualCashPayment(AbstractPaymentMethod):

    @staticmethod
    def is_enabled(cfg):
        return cfg.getboolean('payup_methods', 'cash_manual')

    @staticmethod
    def get_title():
        return "Bargeld (Vertrauenskasse)"

    def _show_dialog(self):
        pay_diag = PayupManualDialog(parent=self.parent, amount_total=self.amount_to_pay)
        ok = bool(pay_diag.exec_())
        if ok:
            self.amount_paid = pay_diag.getPaidAmount()
        else:
            self.amount_paid = 0
        self.amount_returned = Decimal(0)
        self.successful = ok
        self.print_receipt = "ask"


class AutoCashPayment(AbstractPaymentMethod):

    @staticmethod
    def is_enabled(cfg):
        return cfg.getboolean('payup_methods', 'cash')

    def show_thankyou(self):
        pass  # we already show our own thankyou message in the dialog.

    @staticmethod
    def get_title():
        return "Bargeld (Automatenkasse)"

    def _show_dialog(self):
        pay_diag = PayupCashDialog(parent=self.parent, amount_total=self.amount_to_pay)
        ok = bool(pay_diag.exec_())
        paid_amount = pay_diag.getPaidAmount()
        self.amount_paid = paid_amount  # TODO add amount_returned
        self.amount_returned = Decimal(0)  # TODO read from dialog
        self.successful = ok
        self.print_receipt = pay_diag.get_receipt_wanted()


class FAUCardPayment(AbstractPaymentMethod):

    @staticmethod
    def get_title():
        return "FAUCard"

    @staticmethod
    def is_enabled(cfg):
        return cfg.getboolean('payup_methods', 'FAUcard')

    def _show_dialog(self):
        QtGui.QMessageBox.warning(self.parent, "", "Not yet implemented")
        self.amount_paid = 0
        self.amount_returned = 0
        self.successful = False

PAYMENT_METHODS = [FAUCardPayment, AutoCashPayment, ManualCashPayment, ClientPayment]
