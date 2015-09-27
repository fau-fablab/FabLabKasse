#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Patrick Kanzler <patrick.kanzler@fablab.fau.de>
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

# TODOs:
# * Weitere Bezahlmethoden implementieren
#   * Kundenkonten
#   * Bargeld (abgezählt)
#   * FAUcard
# * Über-/Unterzahlungen verarbeiten
# * Userinterface Verbessern
#   * Katergorienauswahl intuitiver machen (man weiß nicht das es quasi-knöpfe sind)
#   * Kategorienpfad besser gestalten
# * Statistik Teil von master importieren
# * mehrer Tabs für offene sale.orders (und automatischer import beim start)
# * Neustart wenn aktuelle session geschlossen wurde (regelmäßiger test?)
#   Geht das überhaupt bevor die alte session gebucht wurde?

import sys
import re
import locale
import logging
import datetime
import os
from decimal import Decimal, DecimalException
from PyQt4 import QtGui, QtCore, Qt
from libs.flickcharm import FlickCharm
from libs.pxss import pxss
import functools

# import UI
from UI.uic_generated.Kassenterminal import Ui_Kassenterminal
from UI.PaymentMethodDialogCode import PaymentMethodDialog
from UI.KeyboardDialogCode import KeyboardDialog

import scriptHelper
from cashPayment.client.PaymentDevicesManager import PaymentDevicesManager

from shopping.cart_from_app.cart_gui import MobileAppCartGUI

if __name__ == "__main__":
    # switching to german:
    locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")

    cfg = scriptHelper.getConfig()

from shopping.backend.abstract import ProductNotFound, PrinterError
import importlib
if __name__ == "__main__":
    backendname = cfg.get("backend", "backend")
else:
    print "WARNING: gui.py: fake import for documentation active, instead of conditional import of backend"
    backendname = "dummy"

assert backendname in ["dummy", "oerp", "legacy_offline_kassenbuch"]
# TODO there are probably nicer forms than the following import hack-magic
shopping_backend_module = importlib.import_module("FabLabKasse.shopping.backend." + backendname)
ShoppingBackend = shopping_backend_module.ShoppingBackend


def format_decimal(value):
    """convert float, Decimal, int to a string with a locale-specific decimal point"""
    return str(value).replace(".", locale.localeconv()['decimal_point'])


class Kassenterminal(Ui_Kassenterminal, QtGui.QMainWindow):

    def __init__(self):
        logging.info("GUI startup")
        Ui_Kassenterminal.__init__(self)
        QtGui.QMainWindow.__init__(self)

        self.setupUi(self)
        # maximize window - WORKAROUND because showMaximized() doesn't work
        # when a default geometry is set in the Qt designer file
        QtCore.QTimer.singleShot(0, lambda: self.setWindowState(QtCore.Qt.WindowMaximized))
        self.shoppingBackend = ShoppingBackend(cfg)

        # TODO check at startup for all cfg.get* calls
        cfg.getint('payup_methods', 'overpayment_product_id')
        cfg.getint('payup_methods', 'payout_impossible_product_id')

        # enable kinetic scrolling by touch-and-drag
        self.charm = FlickCharm()
        self.charm.activateOn(self.table_order, disableScrollbars=False)
        self.charm.activateOn(self.table_products, disableScrollbars=False)
        self.charm.activateOn(self.list_categories, disableScrollbars=False)

        for table in [self.table_products, self.table_order]:
            # forbid resizing columns
            table.verticalHeader().setResizeMode(QtGui.QHeaderView.Fixed)
            # forbid changing column order
            table.verticalHeader().setMovable(False)

            table.horizontalHeader().setResizeMode(QtGui.QHeaderView.Fixed)  # forbid resizing columns
            table.horizontalHeader().setMovable(False)  # forbid changing column order
            # Disable editing on table
            table.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)

        # Connect up the buttons. (lower half)
        self.pushButton_0.clicked.connect(lambda x: self.insertIntoLineEdit('0'))
        self.pushButton_1.clicked.connect(lambda x: self.insertIntoLineEdit('1'))
        self.pushButton_2.clicked.connect(lambda x: self.insertIntoLineEdit('2'))
        self.pushButton_3.clicked.connect(lambda x: self.insertIntoLineEdit('3'))
        self.pushButton_4.clicked.connect(lambda x: self.insertIntoLineEdit('4'))
        self.pushButton_5.clicked.connect(lambda x: self.insertIntoLineEdit('5'))
        self.pushButton_6.clicked.connect(lambda x: self.insertIntoLineEdit('6'))
        self.pushButton_7.clicked.connect(lambda x: self.insertIntoLineEdit('7'))
        self.pushButton_8.clicked.connect(lambda x: self.insertIntoLineEdit('8'))
        self.pushButton_9.clicked.connect(lambda x: self.insertIntoLineEdit('9'))
        # TODO setFocusPolicy none on push buttons.
        self.pushButton_backspace.clicked.connect(self.backspaceLineEdit)
        self.pushButton_delete.clicked.connect(self.buttonDelete)
        self.pushButton_OK.clicked.connect(self.on_ok_clicked)
        self.pushButton_decimal_point.clicked.connect(lambda x: self.insertIntoLineEdit(locale.localeconv()['decimal_point']))
        self.pushButton_decimal_point.setText(locale.localeconv()['decimal_point'])
        self.pushButton_payup.clicked.connect(self.payup)
        self.pushButton_clearCart.clicked.connect(self._clear_cart)

        # Connect keyboard buttons
        # TODO nicer code: for foo in layout_widgets():     foo.connect( functools.partial(insert ... foo.text().lower())
        self.pushButton_q.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('q'))
        self.pushButton_w.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('w'))
        self.pushButton_e.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('e'))
        self.pushButton_r.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('r'))
        self.pushButton_t.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('t'))
        self.pushButton_z.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('z'))
        self.pushButton_u.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('u'))
        self.pushButton_i.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('i'))
        self.pushButton_o.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('o'))
        self.pushButton_p.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('p'))
        self.pushButton_ue.clicked.connect(lambda x: self.insertIntoLineEdit_Suche(u'ü'))
        self.pushButton_a.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('a'))
        self.pushButton_s.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('s'))
        self.pushButton_d.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('d'))
        self.pushButton_f.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('f'))
        self.pushButton_g.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('g'))
        self.pushButton_h.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('h'))
        self.pushButton_j.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('j'))
        self.pushButton_k.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('k'))
        self.pushButton_l.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('l'))
        self.pushButton_oe.clicked.connect(lambda x: self.insertIntoLineEdit_Suche(u'ö'))
        self.pushButton_ae.clicked.connect(lambda x: self.insertIntoLineEdit_Suche(u'ä'))
        self.pushButton_y.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('y'))
        self.pushButton_x.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('x'))
        self.pushButton_c.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('c'))
        self.pushButton_v.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('v'))
        self.pushButton_b.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('b'))
        self.pushButton_n.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('n'))
        self.pushButton_m.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('m'))
        self.pushButton_a_1.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('1'))
        self.pushButton_a_2.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('2'))
        self.pushButton_a_3.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('3'))
        self.pushButton_a_4.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('4'))
        self.pushButton_a_5.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('5'))
        self.pushButton_a_6.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('6'))
        self.pushButton_a_7.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('7'))
        self.pushButton_a_8.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('8'))
        self.pushButton_a_9.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('9'))
        self.pushButton_a_0.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('0'))
        self.pushButton_sz.clicked.connect(lambda x: self.insertIntoLineEdit_Suche(u'ß'))

        self.pushButton_space.clicked.connect(lambda x: self.insertIntoLineEdit_Suche(' '))
        self.pushButton_minus.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('-'))
        self.pushButton_dot.clicked.connect(lambda x: self.insertIntoLineEdit_Suche('.'))
        self.pushButton_komma.clicked.connect(lambda x: self.insertIntoLineEdit_Suche(','))

        self.pushButton_backspace_3.clicked.connect(self.backspaceLineEdit_Suche)
        self.pushButton_enter.clicked.connect(self.searchItems)

        self.lineEdit_Suche.focused.connect(self.on_lineEdit_search_clicked)
        self.lineEdit_Suche.clicked.connect(self.on_lineEdit_search_clicked)  # this is necessary because in rare cases focused() is not emitted

        self.lineEdit_Suche.cursorPositionChanged.connect(lambda x: self.lineEdit_Suche.end(False))  # move cursor to end whenever it is moved
        self.lineEdit.cursorPositionChanged.connect(lambda x: self.lineEdit.end(False))  # move cursor to end whenever it is moved

        # Search if anything gets typed
        self.lineEdit_Suche.textEdited.connect(lambda x: self.searchItems(preview=True))

        # Search (and get rid of keyboard) on return key
        self.lineEdit_Suche.returnPressed.connect(lambda: self.searchItems())

        # Connect up the buttons. (upper half)
        self.pushButton_start.clicked.connect(self.on_start_clicked)

        # Connect category list to change category function
        self.list_categories.clicked.connect(self.on_category_clicked)

        # Connect lineEdit to produce useful strings
        # use textEdited instead of textChanged because this ignores events caused by setText()
        self.lineEdit.textEdited.connect(self.on_lineEdit_changed)

        # Connect lineEdit.returnPressed to be the same as clicking on ok button
        self.lineEdit.returnPressed.connect(self.on_ok_clicked)

        # Connect produktTree to add selected produkt
        self.table_products.clicked.connect(self.on_product_clicked)

        # Connect to table_order changed selection
        self.table_order.clicked.connect(lambda x: self.on_order_clicked())  # lambda is necessary because we don't want the second (default) parameter to be set

        # Disable vertical header on table_order
        self.table_order.verticalHeader().setVisible(False)

        # Shopping carts/orders
        self.updateOrder()

        # currently selected produkt group
        self.current_category = self.shoppingBackend.get_root_category()

        # Initialize categories and products later, after resize events are done
        QtCore.QTimer.singleShot(0, self.updateProductsAndCategories)

        # Give focus to lineEdit
        self.lineEdit.setFocus()

        # Loading dialog for cash payment system
        self.cashPayment = PaymentDevicesManager(cfg)
        self.startupProgress = QtGui.QProgressDialog(self)
        self.startupProgress.setMaximum(0)
        self.startupProgress.setCancelButton(None)
        self.startupProgress.setWindowModality(QtCore.Qt.WindowModal)
        self.startupProgress.setLabelText(u"Initialisiere Bezahlsystem")
        self.startupProgress.setValue(0)
        self.startupProgress.show()

        self.cashPollTimer = QtCore.QTimer()
        self.cashPollTimer.setInterval(500)  # start with fast interval, later reduced
        self.cashPollTimer.timeout.connect(self.pollCashDevices)
        self.cashPollTimer.start()

        # start and configure idle reset for category view
        if cfg.has_option("idle_reset", "enabled"):
            if cfg.getboolean("idle_reset", "enabled"):
                self.idleCheckTimer = QtCore.QTimer()
                self.idleCheckTimer.setInterval(10000)
                self.idleCheckTimer.timeout.connect(self._reset_if_idle)
                self.idleCheckTimer.start()

                if cfg.has_option("idle_reset", "threshold_time"):
                    self.idleTracker = pxss.IdleTracker(idle_threshold=1000 * cfg.getint("idle_reset", "threshold_time"))
                else:
                    # default value is 1800 s
                    # TODO use proper solution for default values
                    self.idleTracker = pxss.IdleTracker(1800000)
                (idle_state, _, _) = self.idleTracker.check_idle()
                if idle_state is 'disabled':
                    self.idleCheckTimer.stop()
                    logging.warning("Automatic reset on idle is disabled since idleTracker returned `disabled`.")

        self.pushButton_load_cart_from_app.setVisible(cfg.has_option("mobile_app", "enabled") and cfg.getboolean("mobile_app", "enabled"))

    def restart(self):
        dialog = QtGui.QMessageBox(self)
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setText(u"Ein Neustart löscht den aktuellen Warenkorb! Fortsetzen?")
        dialog.addButton(QtGui.QMessageBox.Cancel)
        dialog.addButton(QtGui.QMessageBox.Ok)
        dialog.setDefaultButton(QtGui.QMessageBox.Ok)
        dialog.setEscapeButton(QtGui.QMessageBox.Cancel)
        if dialog.exec_() == QtGui.QMessageBox.Ok:
            self.close()

    def serviceMode(self):
        """was the service mode enabled recently? check and disable again"""
        def checkServiceModeEnabled(showErrorMessage=True):
            # for enabling the service mode, the file ./serviceModeEnabled needs to be newer than 30sec
            try:
                lastEnabled = datetime.datetime.utcfromtimestamp(os.lstat("./serviceModeEnabled").st_mtime)
            except OSError:
                if showErrorMessage:
                    QtGui.QMessageBox.warning(self, "Ups",
                                              u"Servicemodus nicht aktiviert\n Bitte ./enableServiceMode ausführen")
                return

            delta = datetime.timedelta(0, 30, 0)
            now = datetime.datetime.utcnow()
            if not (now - delta < lastEnabled < now):
                if showErrorMessage:
                    QtGui.QMessageBox.warning(self, "Hey",
                                              u"Zu spät, Aktivierung gilt nur 30sec.")
                return False
            os.unlink("./serviceModeEnabled")
            return True
        if not checkServiceModeEnabled():
            return
        dialog = QtGui.QMessageBox(self)
        dialog.setText(u"Ausleeren aktivieren? (Nein für nachfüllen/Abbruch)")
        dialog.addButton(QtGui.QMessageBox.No)
        dialog.addButton(QtGui.QMessageBox.Yes)
        dialog.setDefaultButton(QtGui.QMessageBox.No)
        dialog.setEscapeButton(QtGui.QMessageBox.No)
        self.serviceProgress = QtGui.QProgressDialog(self)
        self.serviceProgress.setMaximum(0)
        self.serviceProgress.setWindowModality(QtCore.Qt.WindowModal)
        self.serviceProgress.setLabelText(u"Hier könnte Ihre Werbung stehen.")
        self.serviceProgress.setValue(0)
        self.serviceModeCanceled = False
        self.serviceTimer = QtCore.QTimer()
        self.serviceTimer.setInterval(500)
        self.serviceModeAction = "accept"

        def start():
            self.serviceProgress.canceled.connect(self.serviceModeCancel)
            self.serviceProgress.show()
            self.serviceTimer.timeout.connect(self.pollServiceMode)
            self.serviceTimer.start()
            if self.serviceModeAction == "empty":
                self.cashPayment.empty()
            elif self.serviceModeAction == "accept":
                self.cashPayment.payin(requested=999999, maximum=999999)
        if dialog.exec_() == QtGui.QMessageBox.Yes:
            self.serviceModeAction = "empty"
            start()
            return
        dialog.setText(u"Nachfüllen aktivieren?")
        if dialog.exec_() == QtGui.QMessageBox.Yes:
            self.serviceModeAction = "accept"
            start()
            return
        dialog.setText(u"Automat sperren?")
        if dialog.exec_() != QtGui.QMessageBox.Yes:
            return
        while True:
            dialog = QtGui.QMessageBox(self)
            dialog.setText(u"Der Automat ist wegen Wartungsarbeiten für kurze Zeit nicht verfügbar.\nBitte wende dich zur Bezahlung an einen Betreuer.\n\n(zum Entsperren: ./enableServiceMode ausführen und OK drücken)")
            dialog.addButton(QtGui.QMessageBox.Ok)
            dialog.setStyleSheet("background-color:red; color:white; font-weight:bold;")
            dialog.exec_()
            if checkServiceModeEnabled(showErrorMessage=False):
                return

    # Cancel button was pressed: exit manual-empty mode and wait for it to finish
    def serviceModeCancel(self):
        # do not run this function twice
        if self.serviceModeCanceled:
            return
        self.serviceModeCanceled = True
        if self.serviceModeAction == "empty":
            self.cashPayment.stopEmptying()
        elif self.serviceModeAction == "accept":
            self.cashPayment.abortPayin()
        else:
            assert False

        # show the progress dialog again, but without cancel button
        self.serviceProgress.setCancelButton(None)
        self.serviceProgress.show()
        # dialog will be closed by pollServiceMode when everything is finished

    def pollServiceMode(self):
        self.cashPayment.poll()
        self.serviceProgress.setLabelText(self.cashPayment.statusText())
        a = self.cashPayment.getFinalAmount()
        if a is None:
            # noch nicht fertig
            return
        self.serviceTimer.stop()
        self.serviceProgress.cancel()

        def formatCent(x):  # TODO deduplicate, this is copied from PaymentDevicesManager
            return u"{:.2f}\u2009€".format(float(x) / 100).replace(".", locale.localeconv()['decimal_point'])
        if self.serviceModeAction == "empty":
            text = u"Servicemodus manuell ausgeleert: {} "
        elif self.serviceModeAction == "accept":
            text = u"Servicemodus manuell eingefüllt: {} - Die Einzahlungen werden nicht im Kassenbuch verbucht, aber im Bargeldbestand."
        text = text.format(formatCent(a))
        logging.info(text)
        QtGui.QMessageBox.warning(self, "Service mode {}".format(self.serviceModeAction),
                                  text + u" \nBitte Bargeld- und Kassenstand per CLI prüfen.")

    def pollCashDevices(self):
        self.cashPayment.poll()
        if not self.cashPayment.startingUp() and not self.startupProgress.wasCanceled():
            # hide "payment startup" dialog as soon as as starting up is finished
            logging.info("cashPayment startup done")
            self.startupProgress.cancel()
            # lower poll frequency because the startup is finished
            # (PayupCashDialog also polls on its own at a faster rate)
            self.cashPollTimer.setInterval(2000)
            # we do not stop polling entirely so that crashes of the
            # CashPaymentClients are reported in time and not much later after
            # the user has completely entered his basket and started paying

    def changeProductCategory(self, category):
        # if search was done before, switch from keyboard to basket view
        self.leaveSearch()
        self.current_category = category
        self.updateProductsAndCategories()

    def on_start_clicked(self):
        """resets the categories to the root element

        * leaves current search
        * sets current category to the root element
        * triggers the update of the category-view
        """
        self.leaveSearch()
        self.current_category = self.shoppingBackend.get_root_category()
        self.updateProductsAndCategories()

    def on_category_clicked(self, index=None):
        self.current_category = index.data(QtCore.Qt.UserRole + 1).toInt()[0]  # TODO what does that mean
        self.leaveSearch()
        self.updateProductsAndCategories()

    def on_category_path_button_clicked(self):
        source = self.sender()
        self.current_category = source.category_id
        self.updateProductsAndCategories()

    def _add_to_category_path(self, name, categ_id, bold):
        """add button with text 'name' and callback for opening category categ_id to the category path"""
        # l = Qt.QLabel()
        # l.setText(u"►")
        # self.layout_category_path.addWidget(l)
        button = Qt.QPushButton(u" ► " + name)
        button.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        if categ_id is not None:
            button.category_id = categ_id
            button.clicked.connect(self.on_category_path_button_clicked)
        self.layout_category_path.addWidget(button)
        if bold:
            # set (last) button to bold
            font = button.font()
            font.setBold(True)
            button.setFont(font)

    def updateProductsAndCategories(self, categories=None, products=None, category_path=None):
        """update models for products, categories, and the category path

        categories: list(Category), products: list(Product), category_path: list(Category) or a string to display one non-clickable button"""
        if categories is None:
            categories = self.shoppingBackend.get_subcategories(self.current_category)

        if products is None:
            products = self.shoppingBackend.get_products(self.current_category)

        if category_path is None:
            category_path = self.shoppingBackend.get_category_path(self.current_category)

        categ_model = QtGui.QStandardItemModel(len(categories), 1)
        for i, c in enumerate(categories):
            item = QtGui.QStandardItem(c.name)
            item.setData(c.categ_id)
            categ_model.setItem(i, 0, item)
        self.list_categories.setModel(categ_model)

        # Clear all buttons in layout_category_path
        for i in range(self.layout_category_path.count()):
            self.layout_category_path.itemAt(i).widget().setVisible(False)
            self.layout_category_path.itemAt(i).widget().deleteLater()

        if isinstance(category_path, basestring):
            # special case: display a string
            # used for "Search Results"
            self._add_to_category_path(name=category_path, categ_id=None, bold=True)
        else:
            # Add buttons to layout_category_path
            for c in category_path[:-1]:
                self._add_to_category_path(c.name, c.categ_id, bold=False)
            # make last button with bold text
            if len(category_path) > 0:
                self._add_to_category_path(category_path[-1].name, category_path[-1].categ_id, bold=True)

        # set "all products" button to bold if the root category is selected
        font = self.pushButton_start.font()
        font.setBold(len(category_path) == 0)
        self.pushButton_start.setFont(font)

        prod_model = QtGui.QStandardItemModel(len(products), 4)
        for i, p in enumerate(products):
            name = QtGui.QStandardItem(p.name)
            name.setData(p.prod_id)
            prod_model.setItem(i, 0, name)

            loc = QtGui.QStandardItem()
            loc.setText(p.location)
            prod_model.setItem(i, 1, loc)

            uos = QtGui.QStandardItem(p.unit)
            prod_model.setItem(i, 2, uos)

            price = QtGui.QStandardItem(self.shoppingBackend.format_money(p.price))
            prod_model.setItem(i, 3, price)

        prod_model.setHorizontalHeaderItem(0, QtGui.QStandardItem("Artikel"))
        prod_model.setHorizontalHeaderItem(1, QtGui.QStandardItem("Lagerort"))
        prod_model.setHorizontalHeaderItem(2, QtGui.QStandardItem("Einheit"))
        prod_model.setHorizontalHeaderItem(3, QtGui.QStandardItem("Einzelpreis"))

        self.table_products.setModel(prod_model)
        # Change column width to useful values
        # needs to be delayed so that resize events for the scrollbar happens first, otherwise it reports a scrollbar width of 100px at the very first call
        QtCore.QTimer.singleShot(0, functools.partial(self._resize_table_columns, self.table_products, [5, 2.5, 2, 1]))

    def _resize_table_columns(self, table, widths):
        """resize Qt table columns by the weight factors specified in widths,
        using the whole width (excluding scrollbar width)
        """
        w = table.width() - table.verticalScrollBar().width() - 5
        for i, width in enumerate(widths):
            table.setColumnWidth(i, int(width * w / sum(widths)))

    def addOrderLine(self, prod_id, qty=0):
        logging.debug("addOrderLine " + str(prod_id) + " " + str(self.shoppingBackend.get_current_order()))
        if self.shoppingBackend.get_current_order() is None:
            order = self.shoppingBackend.create_order()
            self.shoppingBackend.set_current_order(order)
        text = None
        if self.shoppingBackend.product_requires_text_entry(prod_id):
            text = KeyboardDialog.askText('Kommentar:', parent=self)
            if text is None:
                return
        self.shoppingBackend.add_order_line(prod_id, qty, comment=text)
        self.updateOrder(selectLastItem=True)
        return

    def on_product_clicked(self):
        # delete all zero-quantity products
        for line in list(self.shoppingBackend.get_order_lines()):  # cast to list so that iterator is not broken when deleting items
            if line.qty == 0 and line.delete_if_zero_qty:
                self.shoppingBackend.delete_order_line(line.order_line_id)

        idx = self.table_products.currentIndex()
        row = idx.row()
        model = idx.model()
        if model is None:
            return
        prod_id = model.item(row, 0).data().toInt()[0]

        self.addOrderLine(prod_id)
        self.leaveSearch(keepResultsVisible=True)  # show basket, but also keep search results visible

    def payup(self):
        """ask the user to pay the current order.
        returns True if the payment was successful, False or None otherwise.
        """
        if self.shoppingBackend.get_current_order() is None:
            # There is no order. Thus payup does not make sense.
            return

        # rounding must take place in shoppingBackend
        total = self.shoppingBackend.get_current_total()
        if total == 0:
            return
        assert isinstance(total, Decimal)
        assert total >= 0
        assert total % Decimal("0.01") == 0, "current order total is not rounded to cents"

        logging.info(u"starting payment for cart: {}".format(self.shoppingBackend.get_order_lines()))

        if total > 250:
            # cash-accept is unlimited, but dispense is locked to maximum 200€ hardcoded. Limit to
            # a sensible amount here
            msgBox = QtGui.QMessageBox(self)
            msgBox.setText(u"Bezahlungen über 250 Euro sind leider nicht möglich. Bitte wende " +
                           u"dich an einen Betreuer, um es per Überweisung zu zahlen.")
            msgBox.exec_()
            return

        # Step 1: Choose payment method
        pm_diag = PaymentMethodDialog(parent=self, cfg=cfg, amount=total)
        paymentmethod = None

        if not pm_diag.exec_():
            # Has cancled request for payment method selection
            return

        paymentmethod = pm_diag.getSelectedMethodInstance(self, self.shoppingBackend, total)
        logging.info(u"started payment of {} with {}".format(self.shoppingBackend.format_money(total), str(type(paymentmethod))))
        paymentmethod.execute_and_store()
        logging.info(u"payment ended. result: {}".format(paymentmethod))
        assert paymentmethod.amount_paid >= 0

        def askUser():
            """ask the user whether he wants a receipt, return True if he does."""
            reply = QtGui.QMessageBox.question(self, 'Message',
                                               u"Brauchst du eine Quittung?",
                                               QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                               QtGui.QMessageBox.No)
            return (reply == QtGui.QMessageBox.Yes)

        # Receipt printing
        if cfg.getboolean('general', 'receipt'):
            if paymentmethod.print_receipt == "ask":
                paymentmethod.print_receipt = askUser()
            if paymentmethod.print_receipt:
                try:
                    # TOOD show amount returned on receipt (needs some rework, because it is not yet stored in the order and so we cannot re-print receipts)
                    self.shoppingBackend.print_receipt(paymentmethod.receipt_order_id)
                except PrinterError,  e:
                    QtGui.QMessageBox.warning(self, "Quittung", "Drucker scheint offline zu sein." +
                                              "\nFalls du wirklich eine Quittung brauchst, melde dich bei " +
                                              "kasse@fablab.fau.de mit Datum, Uhrzeit und Betrag.")
                    logging.warning("printing receipt failed: {}".format(repr(e)))
        if paymentmethod.successful:
            paymentmethod.show_thankyou()
            self.shoppingBackend.set_current_order(None)
            self.updateOrder()
            self.on_start_clicked()
        return paymentmethod.successful

    def payViaApp(self):
        p = MobileAppCartGUI(self, cfg)
        p.execute()

    def getSelectedOrderLineId(self):
        order_idx = self.table_order.currentIndex()
        if order_idx.model() and order_idx.isValid():
            order_line_id = order_idx.model().item(order_idx.row(), 0).data().toInt()[0]
            return order_line_id
        else:
            return None

    def on_order_clicked(self, leave_lineEdit_empty=False):
        order_idx = self.table_order.currentIndex()
        logging.debug("on_order_clicked " + str(order_idx.row()))
        order_line_id = self.getSelectedOrderLineId()
        if order_line_id is not None:
            order_line = self.shoppingBackend.get_order_line(order_line_id)
            self.label_unit.setText(order_line.unit)
        if leave_lineEdit_empty:
            self.lineEdit.setText('')
            self.on_lineEdit_changed()
            return
        if order_line_id is not None:
            self.lineEdit.setText(self.shoppingBackend.format_qty(order_line.qty))
            self.on_lineEdit_changed()

    def insertIntoLineEdit(self, char):
        self.lineEdit.setFocus()
        self.lineEdit.setText(self.lineEdit.text() + char)
        self.on_lineEdit_changed()

    def backspaceLineEdit(self):
        oldtext = self.lineEdit.text()
        if len(oldtext) > 0:
            self.lineEdit.setText(oldtext[:-1])
            self.on_lineEdit_changed()

    def on_lineEdit_changed(self):
        input = self.lineEdit.text()
        # convert comma to dot
        input = input.replace(locale.localeconv()['decimal_point'], ".")
        # Getting rid of all special characters (except for numbers and commas)
        newString = re.sub(r'[^0-9\.]', '', unicode(input))

        # remove multiple commas and only keep last (last = right most)
        comma_count = newString.count('.')
        if comma_count > 1:
            newString = newString.replace('.', '', comma_count - 1)

        selected_order_line_id = self.getSelectedOrderLineId()  # selected order line

        # switch on the "decimal point" button if
        # the user has not yet entered a decimal point
        # and we are not in PLU entry mode (= no product is currently selected)
        self.pushButton_decimal_point.setEnabled(comma_count < 1 and selected_order_line_id is not None)

        # Set correctly formated text, if anything changed (preserves cursor position)
        # replace back from dot to comma
        newString = newString.replace(".", locale.localeconv()['decimal_point'])
        newString = newString[0:8]  # limit input length
        if newString != input:
            self.lineEdit.setText(newString)

        # update currently selected product quantity
        qty = self.getLineEditDecimal()

        if selected_order_line_id is not None:
            self.shoppingBackend.update_quantity(selected_order_line_id, qty)
            order_line = self.shoppingBackend.get_order_line(selected_order_line_id)
            if order_line.qty != qty:
                # quantity was rounded up, notify user
                Qt.QToolTip.showText(self.label_unit.mapToGlobal(Qt.QPoint(0, -30)), u'Eingabe wird auf {} {} aufgerundet!'.format(format_decimal(order_line.qty), order_line.unit))
            else:
                Qt.QToolTip.hideText()
            self.updateOrder()
        else:
            # PLU input
            pass

    def buttonDelete(self):
        order_line = self.getSelectedOrderLineId()
        if order_line is not None:
            self.shoppingBackend.delete_order_line(order_line)
            self.updateOrder()
            self.start_plu_entry()  # update lineEdit_input and label_qty

    def start_plu_entry(self):
        """clear quantity textbox, start entering PLU. This is called e.g. after quantity-entry is finished"""
        # Change to PLU mode by deselecting the order
        self.table_order.setCurrentIndex(QtCore.QModelIndex())
        self.lineEdit.setText('')
        self.label_unit.setText('PLU / Artikelnummer:')
        self.pushButton_decimal_point.setEnabled(False)

    def on_ok_clicked(self):
        # "OK" button pressed
        order_idx = self.table_order.currentIndex()
        plu = unicode(self.lineEdit.text()).strip()

        if order_idx.isValid():
            # quantity entry is now finished.
            self.start_plu_entry()
        else:
            # PLU mode, because no order_line was selected or order was not yet created
            # only digits are allowed
            try:
                # Add order line and switch to qty mode
                self.addOrderLine(self.shoppingBackend.search_product_from_code(plu))
            except ProductNotFound:
                self.start_plu_entry()

    def getLineEditDecimal(self):
        amount = self.lineEdit.text()
        try:
            qty = Decimal(unicode(amount.replace(locale.localeconv()['decimal_point'], ".")))
        except DecimalException:
            qty = Decimal(0)
        return qty

    def updateOrder(self, selectLastItem=False):
        logging.debug("updateOrder")
        # delete sale order if last line was deleted
        if self.shoppingBackend.get_current_order() is not None \
                and not self.shoppingBackend.get_order_lines():
            self.shoppingBackend.delete_current_order()

        # Currently no open cart
        if self.shoppingBackend.get_current_order() is None:
            self.table_order.setModel(QtGui.QStandardItemModel(0, 0))
            self.summe.setText(u'0,00 €')
            self.pushButton_payup.setEnabled(False)
            self.pushButton_clearCart.setEnabled(False)
            self.start_plu_entry()
            return

        # TODO get_orders() ... and switch between tabs

        # Save row selection and count
        old_selected_row = self.table_order.currentIndex().row()
        old_row_count = self.table_order.model().rowCount()

        order_lines = self.shoppingBackend.get_order_lines()

        # Initialize basic model for table
        order_model = QtGui.QStandardItemModel(len(order_lines), 4)
        order_model.setHorizontalHeaderItem(0, QtGui.QStandardItem("Anzahl"))
        order_model.setHorizontalHeaderItem(1, QtGui.QStandardItem("Einheit"))
        order_model.setHorizontalHeaderItem(2, QtGui.QStandardItem("Artikel"))
        order_model.setHorizontalHeaderItem(3, QtGui.QStandardItem("Einzelpreis"))
        order_model.setHorizontalHeaderItem(4, QtGui.QStandardItem("Gesamtpreis"))

        # Update Order lines

        for i, line in enumerate(order_lines):
            qty = QtGui.QStandardItem(self.shoppingBackend.format_qty(line.qty))
            qty.setData(line.order_line_id)
            order_model.setItem(i, 0, qty)

            uos = QtGui.QStandardItem(line.unit)
            order_model.setItem(i, 1, uos)

            name = QtGui.QStandardItem(line.name)
            order_model.setItem(i, 2, name)

            price_unit = QtGui.QStandardItem(self.shoppingBackend.format_money(line.price_per_unit))
            order_model.setItem(i, 3, price_unit)

            subtotal = QtGui.QStandardItem(self.shoppingBackend.format_money(line.price_subtotal))
            order_model.setItem(i, 4, subtotal)

        # Set Model
        self.table_order.setModel(order_model)
        # Change column width to useful values
        # needs to be delayed so that resize events for the scrollbar happens first, otherwise it reports a scrollbar width of 100px at the very first call
        QtCore.QTimer.singleShot(0, functools.partial(self._resize_table_columns, self.table_order, [4, 6, 20, 5, 5]))
        # TODO the 100ms delay is a workaround that is necessary because the first call often comes too early.
        # this workaround looks not so good, a nicer solution would be good
        QtCore.QTimer.singleShot(100, functools.partial(self._resize_table_columns, self.table_order, [4, 6, 20, 5, 5]))

        if selectLastItem:
            # select last line - used when a new line was just added
            self.table_order.selectRow(self.table_order.model().rowCount() - 1)
            self.on_order_clicked(leave_lineEdit_empty=True)
        else:
            new_row_count = self.table_order.model().rowCount()
            if new_row_count == old_row_count:
                self.table_order.selectRow(old_selected_row)

        # Update summe:
        total = self.shoppingBackend.get_current_total()
        self.summe.setText(self.shoppingBackend.format_money(self.shoppingBackend.get_current_total()))

        # disable "pay now" button on empty bill
        self.pushButton_payup.setEnabled(total > 0)
        self.pushButton_clearCart.setEnabled(True)

    # keyboard search interaction
    def on_lineEdit_search_clicked(self):
        self.stackedWidget.setCurrentIndex(2)

    def insertIntoLineEdit_Suche(self, char):
        self.lineEdit_Suche.setFocus()
        self.lineEdit_Suche.setText(self.lineEdit_Suche.text() + char)
        self.searchItems(preview=True)

    def backspaceLineEdit_Suche(self):
        oldtext = self.lineEdit_Suche.text()
        if len(oldtext) > 0:
            self.lineEdit_Suche.setText(oldtext[:-1])
        self.lineEdit_Suche.setFocus()
        self.searchItems(preview=True)

    # list searched items in product tree
    def searchItems(self, preview=False):
        searchstr = unicode(self.lineEdit_Suche.text())
        (categories, products) = self.shoppingBackend.search_from_text(searchstr)
        self.updateProductsAndCategories(categories, products, "Suchergebnisse")

        if not preview:
            self.leaveSearch(keepResultsVisible=True)

    def leaveSearch(self, keepResultsVisible=False):
        self.lineEdit_Suche.clear()
        if self.stackedWidget.currentIndex() != 1:
            # after search set view from keyboard to basket
            self.stackedWidget.setCurrentIndex(1)
            if not keepResultsVisible:
                self.updateProductsAndCategories()
        # Give focus to lineEdit
        self.lineEdit.setFocus()

    def _check_idle(self):
        """checks whether the GUI is idle for a great time span

        Uses the information from screensaver to check whether the GUI is idle for a hardcoded time span.
        If the GUI is considered idle, then true is returned.
        :rtype: bool
        :return: true if GUI is idle
        """
        idle_state = self.idleTracker.check_idle()
        # check_idle() returns a tupel (state_change, suggested_time_till_next_check, idle_time)
        # the state "idle" is entered after the time configured in self.CATEGORY_VIEW_RESET_TIME
        idle_keyword = "idle"
        if idle_state[0] == idle_keyword:
            return True
        elif idle_state[0] is None and self.idleTracker.last_state == idle_keyword:
            return True
        else:
            return False

    def _reset_if_idle(self):
        """resets the category-view of the GUI if it is idle for a certain timespan

        The function uses self._check_idle() to check whether the screensaver thinks the GUI is idle.
        The timespan for considering the system idle is set in the config-file.

        This function might be called anytime. This means it could even execute during payup-dialogs and similar things.
        Therefore the current order must not be modified or updated by this method to prevent undefined interference
        with other processes.
        """
        if self._check_idle():
            logging.debug("idle timespan passed; execute GUI reset")
            self.on_start_clicked()

    def _clear_cart(self, hide_dialog=False):
        """clear the current cart

        :param show_dialog: whether the user should be asked
        :type show_dialog: bool
        """

        def ask_user():
            """ask the user whether he really wants to clear the cart, return True if he does."""
            reply = QtGui.QMessageBox.question(self, 'Message',
                                               u"Willst du den Warenkorb wirklich löschen?",
                                               QtGui.QMessageBox.Yes | QtGui.QMessageBox.No,
                                               QtGui.QMessageBox.No)
            return (reply == QtGui.QMessageBox.Yes)
        user_answer = True
        if hide_dialog is False:
            user_answer = ask_user()
        if user_answer:
            self.shoppingBackend.delete_current_order()
            self.updateOrder()


def main():
    if "--debug" in sys.argv:
        print "waiting for debugger"
        print "please open winpdb [does also work on linux despite the name],\n set password to 'gui'\n, attach"
        print "(or use run.py --debug which does everything for you)"
        import rpdb2
        rpdb2.start_embedded_debugger("gui")
    # catch SIGINT
    scriptHelper.setupSigInt()
    # setup logging
    scriptHelper.setupLogging("gui.log")
    # error message on exceptions
    scriptHelper.setupGraphicalExceptHook()

    app = QtGui.QApplication(sys.argv)
    # Hide mouse cursor if configured
    if cfg.getboolean('general', 'hide_cursor'):
        app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.BlankCursor))

    # load locale for buttons, thanks to https://stackoverflow.com/questions/9128966/pyqt4-qfiledialog-and-qfontdialog-localization
    translator = QtCore.QTranslator()
    current_locale = QtCore.QLocale.system().name()
    translator.load('qt_%s' % current_locale, QtCore.QLibraryInfo.location(QtCore.QLibraryInfo.TranslationsPath))
    app.installTranslator(translator)

    # Set style to "oxygen"
    app.setStyle("oxygen")
    app.setFont(QtGui.QFont("Carlito"))
    QtGui.QIcon.setThemeName("oxygen")
    logging.debug("icon theme: {}".format(QtGui.QIcon.themeName()))
    logging.debug("icon paths: {}".format([str(x) for x in QtGui.QIcon.themeSearchPaths()]))

    kt = Kassenterminal()
    kt.show()

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
