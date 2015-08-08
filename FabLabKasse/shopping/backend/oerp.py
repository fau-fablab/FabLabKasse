#!/usr/bin/env python2.7
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

import oerplib
import re
import logging

from .abstract import AbstractClient, AbstractShoppingBackend, float_to_decimal, ProductNotFound, OrderLine, Product, Category


class Client(AbstractClient):

    """oerp implementation of AbstractClient.
    do not instantiate this yourself, but please rather use Client.from_oerp or ShoppingBackend.list_clients
    """

    @classmethod
    def from_oerp(cls, client_id, oerp):
        """ read raw data from oerp record """
        try:
            data = oerp.read('res.partner', client_id, ['name', 'x_pin', 'credit', 'credit_limit'])
            assert data['customer'] == True
            assert data['x_pin'] != False
            return data
        except:  # TODO catch specific exception
            raise Exception("Client not found")

        client = cls(client_id, data['name'])
        client.pin = data['x_pin']
        client._credit_limit = float_to_decimal(data['credit_limit'], 2)
        client._credit = float_to_decimal(data['credit'], 2)
        return client

    def get_debt(self):
        return self._credit

    def get_debt_limit(self):
        return self._credit_limit

    # TODO test_pin + check for disabled (=pin False or 0000 ?)


class ShoppingBackend(AbstractShoppingBackend):

    """OpenERP implementation of AbstractShoppingBackend"""

    def __init__(self, cfg):
        super(ShoppingBackend, self).__init__(cfg)
        self._current_order = None
        # TODO assert cfg has relevant entries
        self.cfg.getint('openerp', 'base_category_id')
        assert self.cfg.get('openerp', 'anonymous_partner_id', None) is not None, "no 'anonymous_partner_id' configured"

# TODO check donation product for price_unit
# Add donation to order
#            order_line_data = oerp.execute(
#                'sale.order.line', 'product_id_change', [], order['pricelist_id'][0],
#                prod_id, return_value['amount_paid']-order['amount_total'],
# UOM  qty_uos UOS    Name   partner_id
#                False, 0,      False, False, order['partner_id'][0])['value']
#            order_line_data.update({'order_id': order_id, 'product_id': prod_id,
#                                    'product_uom_qty':
#                                         return_value['amount_paid']-order['amount_total'],
#                                    'price_unit': 1.0})
#            order_line_id = oerp.create('sale.order.line', order_line_data)
#

        self.oerp = oerplib.OERP(server=cfg.get('openerp', 'server'), protocol='xmlrpc+ssl',
                                 database=cfg.get('openerp', 'database'), port=cfg.getint('openerp', 'port'),
                                 version=cfg.get('openerp', 'version'))
        self.oerp.login(user=cfg.get('openerp', 'user'), passwd=cfg.get('openerp', 'password'))

        self.oerp_jcnt = oerplib.rpc.ConnectorJSONRPCSSL(cfg.get('openerp', 'server'),
                                                         port=cfg.getint('openerp', 'port'),
                                                         version=cfg.get('openerp', 'version'))
        self.oerp_jcnt.proxy.web.session.authenticate(db=cfg.get('openerp', 'database'),
                                                      login=cfg.get('openerp', 'user'),
                                                      password=cfg.get('openerp', 'password'))

    def get_root_category(self):
        return self.cfg.getint('openerp', 'base_category_id')

    def get_subcategories(self, current_category):
        oerp = self.oerp
        category_child_ids = oerp.search(
            'product.category', [('parent_id', '=', current_category)])

        # Update Category List
        categories = list(oerp.read('product.category', category_child_ids,
                                    ['name', 'sequence'],
                                    context=oerp.context))
        categories.sort(key=lambda c: c['sequence'])
        return [Category(categ_id=c['id'], name=c['name']) for c in categories]

    def get_category_path(self, current_category):
        oerp = self.oerp
        c = oerp.read('product.category', current_category,
                      ['name', 'parent_id'], context=oerp.context)
        category_path = []
        # TODO change to new Category() interface
        while c and c['id'] != self.get_root_category():
            category_path.append(c)
            c = oerp.read('product.category', c['parent_id'][0], ['name', 'parent_id'],
                          context=oerp.context)
        category_path.reverse()
        return [Category(categ_id=cat['id'], name=cat['name']) for cat in category_path]

    def set_current_order(self, order_id):
        self._current_order = order_id

    def create_order(self):
        partner_id = self.cfg.getint('openerp', 'anonymous_partner_id')
        order_data = self.oerp.execute('sale.order', 'onchange_partner_id', [], partner_id)
        print order_data
        assert not order_data.has_key('warning'), u"failed getting default values for sale.order: {}".format(order_data['warning'])
        order_data = order_data['value']
        order_data.update({'partner_id': partner_id,
                           'order_policy': 'manual',
                           'picking_policy': 'one'})
        order_id = self.oerp.create('sale.order', order_data)
        return order_id

    def get_current_order(self):
        return self._current_order

    def update_quantity(self, order_line_id, amount):
        oerp = self.oerp
        order_line = oerp.read('sale.order.line', order_line_id, ['product_uom_qty'],
                               context=oerp.context)
        if order_line['product_uom_qty'] != amount:
            oerp.write('sale.order.line', order_line_id, {'product_uom_qty': float(amount)})

    def get_order_line(self, order_line_id):
        return self._order_lines_from_oerp([order_line_id])[0]

    def get_current_total(self):
        order = self.oerp.read('sale.order', self.get_current_order(),
                               ['amount_total', 'amount_paid', 'state', 'pricelist_id', 'partner_id'])
        # TODO update total first ???
        return float_to_decimal(order['amount_total'], 2)

    def pay_order(self, method):
        raise Exception("TODO")
        # TODO update code to match new interface definition -- method is now an object and needs to be checked with isinstance, see legacy_offline_kassenbuch
        if method == "cash_manual":
            pay_journal_id = self.cfg.getint('payup_methods', 'cash_manual_journal_id')
        else:
            raise Exception("unknown method")
        oerp = self.oerp
        order_id = self.get_current_order()
        oerp.exec_workflow('sale.order', 'order_confirm', order_id)
        picking_id = oerp.read('sale.order', order_id, ['picking_ids'])['picking_ids']
        if picking_id:
            # No picking list is created if only services are bought
            picking_id = picking_id[0]
            oerp.write('stock.picking.out', picking_id, {'auto_picking': True})

        invoice_id = oerp.execute('sale.order', 'action_invoice_create', [order_id])
        oerp.exec_workflow('account.invoice', 'invoice_open', invoice_id)

        current_period = oerp.execute('account.period', 'find')[0]
        pay_account_id = oerp.read(
            'account.journal',
            pay_journal_id,
            ['default_debit_account_id'])['default_debit_account_id'][0]

        # and the actual payment:
        oerp.execute('account.invoice', 'pay_and_reconcile',
                     [invoice_id],
                     float(method.amount_paid - method.amount_returned),
                     pay_account_id, current_period, pay_journal_id,
                     False, False, False,
                     oerp.context)

        paid = oerp.read('account.invoice', invoice_id, ['state'])['state'] == 'paid'
        if paid:
            oerp.execute('sale.order', 'action_done', order_id)
        else:
            raise Exception("Payment failed/insufficient :(")

    def _pay_order_on_client_unchecked(self, client):
        """
        charge the order on client account and return new account balance
        """
        # TODO
        return NotImplementedError()
        self.oerp.write('sale.order', self.get_current_order(), {'partner_id': client.client_id,
                                                                 'partner_shipping_id': client.client_id,
                                                                 'partner_invoice_id': client.client_id})

    def add_order_line(self, prod_id, qty, comment=None):
        # TODO comment currently unused

        partner_id = self.cfg.getint('openerp', 'anonymous_partner_id')
        oerp = self.oerp
        order_id = self.get_current_order()
        order_data = oerp.read('sale.order', order_id, ['pricelist_id'])

        try:
            oerp.browse('product.product', prod_id)
        except:
            # TODO this exception is not caught at the callers!!!
            raise ProductNotFound("product disapeared: {}".format(prod_id))  # most likely

        # Calculate price
        order_line_data = oerp.execute(
            'sale.order.line', 'product_id_change', [],
            order_data['pricelist_id'][0], prod_id, qty,
            # UOM  qty_uos UOS    Name   partner_id
            False, 0,      False, False, partner_id)['value']
        order_line_data.update({'order_id': order_id, 'product_id': prod_id,
                                'product_uom_qty': float(qty)})
        oerp.create('sale.order.line', order_line_data)

    def delete_order_line(self, order_line_id):
        # TODO test that line is actually in current order
        # TODO test that the current order may be written (state not paid...)
        self.oerp.unlink('sale.order.line', [order_line_id])

    def delete_current_order(self):
        order_id = self.get_current_order()
        oerp = self.oerp
        if not oerp.read('sale.order', order_id, ['order_line'])['order_line']:
            oerp.unlink('sale.order', [order_id])
        self.set_current_order(None)

    def search_product_from_code(self, code):
        code = unicode(code)
        code = re.sub(r'[^0-9]', '', code)
        code = int(code)

        # lookup code
        ids = self.oerp.search('product.product', [('default_code', '=', code),
                                                   ('sale_ok', '=', True)], limit=1)
        if ids:
            return ids[0]
        else:
            raise ProductNotFound()

    def search_from_text(self, searchstr):
        oerp = self.oerp
        # Build search pattern
        searchstr = searchstr.lower().strip()
        searchpattern = searchstr.split(' ')
        searchpattern = map(lambda s: ('name', 'ilike', u'%' + s + u'%'), searchpattern)

        # We don't do empty (full) searches
        if not searchstr:
            # TODO
            return

        # Do the actual search:
        category_ids = oerp.search('product.category', searchpattern)
        # Update Category List
        categories = list(oerp.read('product.category', category_ids,
                                    ['name', 'sequence'],
                                    context=oerp.context))

        # TODO change to new Category() interface
        # tODO sort by sequence?
        return (self._get_products_from_oerp(searchpattern), categories)

    def _get_products_from_oerp(self, query):
        """ queries openerp for products with the specified query,
        returns them in a format suitable for self.get_products()
        """
        oerp = self.oerp
        product_ids = self.oerp.search('product.product', query + [('sale_ok', '=', True)])
        # TODO read category from product, then fetch all categs.
        current_category = self.get_root_category()  # WORKAROUND
        c = self.oerp.read('product.category', current_category,
                           ['name', 'parent_id', 'property_stock_location'], context=oerp.context)
        category_default_location = c['property_stock_location']

        # Update products
        products = oerp.read(
            'product.product',
            product_ids,
            ['name', 'property_stock_location', 'uos_id', 'uom_id', 'list_price'],
            context=oerp.context)

        # get pricelist
        try:
            pricelist_id = oerp.read(
                'res.partner', self.cfg.getint('openerp', 'anonymous_partner_id'),
                ['property_product_pricelist'],
                context=oerp.context)['property_product_pricelist'][0]
        except:
            raise Exception("Could not get pricelist from anonymous_client, " +
                            "probably wrong id in config.ini.")
        product_prices = self.oerp_jcnt.proxy.web.dataset.call(
            model='product.pricelist', method='price_get_multi',
            args=[[pricelist_id],
                  map(lambda i: (i, 1, None), product_ids),
                  oerp.context])

        if 'error' in product_prices:
            raise Exception("Could not get prices. Is the anonymous_partner_id set correctly?")

        # TODO change to new Product() interface
        products_preprocessed = []
        for p in products:
            if p['uos_id']:
                unit = p['uos_id'][1]
            else:
                unit = p['uom_id'][1]
            if p['property_stock_location']:
                location = p['property_stock_location'][1].replace(
                    self.cfg.get('openerp', 'strip_location'), '').strip()
            else:
                # TODO only if product is in this category :(
                location = category_default_location
            location = unicode(location)
            data = Product(prod_id=p['id'], name=p['name'], price=float_to_decimal(p['list_price'], 3), unit=unit, location=location, categ_id=None)
            products_preprocessed.append(data)
        return products_preprocessed

    def _order_lines_from_oerp(self, ids):
        assert type(ids) == list
        for i in ids:
            assert type(i) == int
        "convert openerp order_line_id, type list(int), to list(OrderLine()) filled with data"
        lines = self.oerp.read('sale.order.line', ids, ['product_id', 'product_uom_qty',
                                                        'product_uom', 'price_unit',
                                                        'product_uos', 'price_subtotal'],
                               context=self.oerp.context)
        result = []
        for line in lines:
            data = OrderLine(order_line_id=line['id'],
                             qty=unicode(line['product_uom_qty']),
                             unit=line['product_uom'][1],
                             name=line['product_id'][1],
                             price_per_unit=float_to_decimal(line['price_unit'], 3),
                             price_subtotal=float_to_decimal(line['price_subtotal'], 3))
            if line['product_uos']:
                data.unit = line['product_uos'][1]
            result.append(data)
        return result

    def get_order_lines(self):
        oerp = self.oerp
        # Retrieve current order
        if self.get_current_order() is None:
            return []
        print self.get_current_order()
        order = oerp.read('sale.order', self.get_current_order(), ['order_line', 'amount_total'],
                          context=oerp.context)
        if not 'order_line' in order or not order['order_line']:
            return []
        return self._order_lines_from_oerp(order['order_line'])

    def get_products(self, current_category):
        return self._get_products_from_oerp([('categ_id', '=', current_category)])

    def list_clients(self):
        client_ids = self.oerp.search('res.partner', [('customer', '=', True), ('x_pin', '!=', False)])
        return [Client.from_oerp(i, self.oerp) for i in client_ids]
