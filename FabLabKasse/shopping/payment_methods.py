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

"""
Payment methods and their business logic

The GUI fetches the list of payment method classes from
``payment_methods.PAYMENT_METHODS`` and lets the user choose from all methods
that are enabled (:meth:`is_enabled`).

The selected method is instantiated and :meth:`execute_and_store` called.
The attributes described in :meth:`AbstractPaymentMethod._show_dialog` are
used to store the payment and print a receipt. Then, an optional thank-you
message is shown to the user (:meth:`_show_thankyou_message` ).

To implement a new payment method, subclass :class:`AbstractPaymentMethod` for
cash, credit card or similar methods. For client accounts (that are somehow
paid later or pre-paid), subclass :class:`AbstractClientPaymentMethod`. Add
your class to the list ``PAYMENT_METHODS`` at the end of ``payment_methods.py``
"""

import logging
from abc import ABCMeta, abstractmethod  # abstract base class support
from PyQt4 import QtGui
from decimal import Decimal
from ..UI.ClientDialogCode import SelectClientDialog
from ..UI.PayupManualDialogCode import PayupManualDialog
from .. import scriptHelper
from FabLabKasse.shopping.backend.abstract import DebtLimitExceeded
from FabLabKasse.faucardPayment.faucard import PayupFAUCard, finish_log


class AbstractPaymentMethod(object):

    """interface for payment methods

    :param QWidget parent: handle for main window - for Qt usage
    :param FabLabKasse.shopping.backend.abstract.AbstractShoppingBackend shopping_backend: ShoppingBackend instance
    :param Decimal amount_to_pay: requested amount (rounded to cents)
    :param cfg: config object
    """

    __metaclass__ = ABCMeta

    def __init__(self, parent, shopping_backend, amount_to_pay, cfg):
        self.parent = parent
        self.shopping_backend = shopping_backend
        self.amount_to_pay = amount_to_pay
        assert isinstance(amount_to_pay, Decimal)
        self.cfg = cfg
        self.successful = None
        self.amount_paid = None
        self.amount_returned = None
        self.print_receipt = False
        self.receipt_order_id = shopping_backend.get_current_order()

    def __repr__(self):
        return "<{0}(amount_to_pay={1}, amount_paid={2}, amount_returned={3}, successful={4}, ...)>".format(
            type(self).__name__,
            repr(self.amount_to_pay),
            repr(self.amount_paid),
            repr(self.amount_returned),
            self.successful,
        )

    @abstractmethod
    def _show_dialog(self):
        """show a GUI dialog and start payment. Return AFTER dialog has finished. The dialog MUST be modal, see ``QDialog.setModal()``.

        :rtype: None

        updates the following object properties:

        - ``self.successful``: if False the payment-process has to be retried,
          otherwise the transaction is complete
        - ``self.amount_paid``:  amount of money which has been inserted into
          the machine
        - ``self.amount_returned``: amount of money that the machine returned
          to the user


        There are two standard cases:

        - paid normally:
          ``success == True and amount_paid - amount_returned == amount_to_pay``
        - payment aborted normally:
          ``success == False and amount_paid == amount_returned``

        And two special cases for certain payment operations like paying in
        cash:

        - extra donation during payment process:
          ``success == True and amount_paid - amount_returned > amount_to_pay``
        - payment aborted, but some part of the paid money could not be paid
          out again (e.g. because the machine can accept but not dispense
          1-cent coins):
          ``success == False and amount_paid > amount_returned``
        """
        pass

    def _end_of_payment(self):
        """
        This function is called after the payment has been stored in the
        backend. It can be used if your payment method has its own logging
        features and wants to store that the transaction is now fully complete.

        The default implementation does nothing.

        .. NOTE:
           This function will be called even if the payment was not successful
           or no money has been paid.
           You can access the attributes `successful`, `amount_paid`,
           `amount_returned` to check if you need to log the finished payment
           or not.

        :rtype: None
        """

    def show_thankyou(self):
        """Show a thank-you messge dialog. Block until it is closed.

        This is called by the GUI after execute_and_store has ended and
        the receipt has been printed.

        You can safely override this with an empty method if you don't want
        this extra thank-you dialog.
        """
        pass
        # QtGui.QMessageBox.information(self.parent, "", u"Vielen Dank für deine Zahlung von {0}.\nBitte das Aufräumen nicht vergessen!".format(self.shopping_backend.format_money(self.amount_paid - self.amount_returned)))

    @staticmethod
    def is_enabled(cfg):
        """
        is this payment method available?

        :param cfg: configuration from ScriptHelper.getConfig()
        :rtype: bool
        """
        return False

    @staticmethod
    def get_title():
        """human-readable name of payment method

        :rtype: unicode"""
        return "title not implemented"

    @staticmethod
    def is_charge_on_client():
        """
        :return: ``False`` for normal payment (cash, credit card, etc.), ``True`` for virtual payment on client account
        :rtype: bool
        """
        return False

    def execute_and_store(self):
        """show dialog and process payment

        - show dialog, make payment, update the properties as described in :meth:`_show_dialog`
        - call :meth:`_end_of_payment` as soon as possible, but after the properties have been updated
        - show thankyou message :meth:`_show_thankyou_message`

        .. NOTE::
          If possible, only override _show_dialog and not this method.
        """
        self._show_dialog()
        assert isinstance(self.amount_paid, (Decimal, int))
        assert isinstance(self.amount_returned, (Decimal, int))
        assert self.amount_paid >= self.amount_returned
        if self.successful:
            assert self.amount_paid >= self.amount_to_pay
            if self.amount_paid > self.amount_to_pay:
                logging.info(
                    "user paid more than requested - adding product for overpayment to current order"
                )
                # Modify sale order according to overpayment
                # rather handle these two calls in shoppingBackend??
                prod_id = scriptHelper.getConfig().getint(
                    "payup_methods", "overpayment_product_id"
                )
                self.shopping_backend.add_order_line(
                    prod_id, self.amount_paid - self.amount_to_pay
                )
                assert (
                    self.shopping_backend.get_current_total() == self.amount_paid
                ), "adding product for overpayment failed"
            self.shopping_backend.pay_order(self)
        else:  # unsuccessful payment
            amount_not_paid_back = self.amount_paid - self.amount_returned
            if amount_not_paid_back == 0:
                # completely refunded aborted payment - no receipt necessary
                self.print_receipt = False
            else:
                logging.info(
                    "cannot pay back everything of aborted payment. issuing receipt for the remaining rest."
                )
                self.print_receipt = True
                old_order = self.shopping_backend.get_current_order()
                # create a new, separate order for the non-paid-back rest
                # set it as paid
                # and print a receipt for it
                new_order = self.shopping_backend.create_order()
                self.receipt_order_id = new_order
                self.shopping_backend.set_current_order(new_order)
                # todo add to cfg tests at startup
                prod_id = scriptHelper.getConfig().getint(
                    "payup_methods", "payout_impossible_product_id"
                )
                self.shopping_backend.add_order_line(prod_id, amount_not_paid_back)
                assert (
                    self.shopping_backend.get_current_total() == self.amount_paid
                ), "adding product for 'impossible payout' failed"
                self.shopping_backend.pay_order(self)

                # switch back to old order
                self.shopping_backend.set_current_order(old_order)

        self._end_of_payment()


class AbstractClientPaymentMethod(AbstractPaymentMethod):

    """
    abstract base for virtual payment on client account (no real money is
    being) transfered, the client account balance just becomes lower)
    """

    __metaclass__ = ABCMeta

    @staticmethod
    def is_charge_on_client():
        return True

    @abstractmethod
    def execute_and_store(self):
        pass


class ClientPayment(AbstractClientPaymentMethod):
    "pay on client account with PIN and client number"

    @staticmethod
    def is_enabled(cfg):
        return cfg.getboolean("payup_methods", "client")

    @staticmethod
    def get_title():
        return "Kundenkonto + PIN"

    def show_thankyou(self):
        pass  # we already show our own thankyou dialog.

    def _show_dialog(self):
        client_diag = SelectClientDialog(
            parent=self.parent, shopping_backend=self.shopping_backend
        )
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
            self.amount_paid = self.amount_to_pay
            self.successful = True
            self._end_of_payment()
            QtGui.QMessageBox.information(
                self.parent,
                "Information",
                u"Vielen Dank.\n Dein neuer Kontostand beträgt "
                + u"{0}. \n(Positiv ist Guthaben)".format(
                    self.shopping_backend.format_money(-new_debt)
                ),
            )
        except DebtLimitExceeded as e:
            self.successful = False
            self._end_of_payment()
            msgBox = QtGui.QMessageBox(self.parent)
            msgBox.setText(e.message)
            msgBox.setIcon(QtGui.QMessageBox.Warning)
            msgBox.exec_()


class ManualCashPayment(AbstractPaymentMethod):
    """
    Pay in cash, but enter manually how much money was put into the cashbox.
    """

    @staticmethod
    def is_enabled(cfg):
        return cfg.getboolean("payup_methods", "cash_manual")

    @staticmethod
    def get_title():
        return "Bargeld (Vertrauenskasse)"

    def _show_dialog(self):
        pay_diag = PayupManualDialog(
            parent=self.parent, amount_total=self.amount_to_pay
        )
        ok = bool(pay_diag.exec_())
        if ok:
            self.amount_paid = pay_diag.getPaidAmount()
        else:
            self.amount_paid = 0
        self.amount_returned = Decimal(0)
        self.successful = ok
        self.print_receipt = True


class FAUCardPayment(AbstractPaymentMethod):
    "Pay using the FAU-Magnacard using the FauCardPayment-Plugin which is not available to public."

    @staticmethod
    def get_title():
        return "FAUCard"

    @staticmethod
    def is_enabled(cfg):
        return cfg.getboolean("payup_methods", "FAUcard")

    def _show_dialog(self):
        pay_func = PayupFAUCard(parent=self.parent, amount=self.amount_to_pay)
        self.print_receipt = True
        self.successful = pay_func.executePayment()
        self.amount_paid = pay_func.getPaidAmount()
        self.amount_returned = 0

        pay_func.close()

    def _end_of_payment(self):
        """
        Is required to complete the MagPosLog logging after the payment routine.
        On a successful payment, the last log entry will be set to status.booking_done
        """
        if self.successful:
            finish_log()


PAYMENT_METHODS = [FAUCardPayment, ManualCashPayment, ClientPayment]
