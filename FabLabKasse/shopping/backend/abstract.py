#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2013-2015 Julian Hammer <julian.hammer@fablab.fau.de>
#                         Maximilian Gaukler <max@fablab.fau.de>
#                         Timo Voigt <timo@fablab.fau.de>
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

"""abstract implementations of shopping and clients

base class and interface definition for specific implementations (see other files in this folder)
"""

from abc import ABCMeta, abstractmethod  # abstract base class support
from decimal import Decimal
import itertools

# counter for unique id values, use next(_id_counter) to get a new ID
_id_counter = itertools.count()


def float_to_decimal(number, digits):
    # conversion is guaranteed to be accurate at 1e12 for 0 digits
    # larger values are maybe not correctly represented in a float, so we are careful here
    assert isinstance(digits, int)
    assert 0 <= digits < 10, "invalid number of digits"
    result = Decimal(int(round(number * (10 ** digits)))) / (10 ** digits)
    assert abs(number) < 10 ** (10 + digits), "cannot precisely convert such a large float to Decimal"
    assert abs(float(result) - float(number)) < (10 ** -(digits + 3)), "attempted inaccurate conversion from {} to {}".format(repr(number), repr(result))
    return result

class Category(object):
    def __init__(self, categ_id, name, parent_id=None):
        self.categ_id = categ_id
        self.name = name
        self.parent_id = parent_id
    
    def __repr__(self):
        return "Category({}, {}, {})".format(self.categ_id, repr(self.name), self.parent_id)

class Product(object):
    """simple representation for a product
    prod_id: int
    categ_id: int or None
    name, location, unit: text
    price: Decimal
    qty_rounding: 0 (product can be bought in arbitrarily small quantities)
                  int or Decimal (product can only be bought in multiples of this quantity, GUI input can be rounded/truncated)
                  example: you cannot buy half a t-shirt, so you set qty_rounding = 1
                  
                  handling this is responsibility of the shopping backend
    """
    def __init__(self, prod_id, name, price, unit, location, categ_id=None, qty_rounding=0, text_entry_required=False):
        """price: Decimal
        
        categ_id may be None if the product is not visible""" # TODO hide these products from search, or a more explicit solution
        self.prod_id = prod_id
        self.name = name
        assert isinstance(price, (Decimal, int))
        self.price = price
        self.location = location
        self.categ_id = categ_id
        self.unit = unit
        self.text_entry_required = text_entry_required
        assert isinstance(qty_rounding, (Decimal, int))
        assert qty_rounding >= 0
        self.qty_rounding = qty_rounding

class OrderLine(object):
    def __init__(self, order_line_id, qty, unit, name, price_per_unit, price_subtotal, delete_if_zero_qty=True):
        """
        one order line (roughly equal to a product in a shopping cart, although there may be multiple entries for one product)
        
        id: id of order-line, *must be unique and non-changing* inside one Order() (if None: autogenerate id)
        
        qty: Decimal ("unlimited" number of digits)
        
        unit: text
        
        name: text
        
        price_per_unit: Decimal
        
        price_subtotal: Decimal
        
        delete_if_zero_qty: boolean - if the qty is zero and the user starts adding something else, then remove this line
           [ usually True, set to False for products that also may as comment limes costing nothing ]
        
        """
        self.order_line_id = order_line_id
        if order_line_id == None:
            self.order_line_id = next(_id_counter) # may cause problems after ca. 2**30 calls because QVariant in gui somewhere converts values to int32. but who cares...
        self.qty = qty
        self.unit = unit
        self.name = name
        assert isinstance(price_per_unit, (Decimal, int))
        self.price_per_unit = price_per_unit
        isinstance(price_subtotal, (Decimal, int))
        self.price_subtotal = price_subtotal
        self.delete_if_zero_qty = delete_if_zero_qty


class DebtLimitExceeded(Exception):
    """exception raised by pay_order_on_client: order not paid because
    the debt limit would have been exceeded"""
    pass

class ProductNotFound(Exception):
    "requested product not found"
    pass
    
class PrinterError(Exception):
    "cannot print receipt"
    pass

class AbstractShoppingBackend(object):
    "manages products, categories and orders (cart)"
    __metaclass__ = ABCMeta

    def __init__(self, cfg):
        "cfg: config from ScriptHelper.getConfig()"
        self.cfg = cfg

    def format_money(self, amount):
        "format float as money string"
        # format:
        # 1.23 -> 1,23 €
        # 3.741 -> 3,741 €
        formatted = u'{:.3f}'.format(amount)
        
        if formatted.endswith("0"):
            formatted = formatted[:-1]

        return u'{} €'.format(formatted).replace('.', ',')
        
    def qty_to_str(self, qty):
        s = str(float(qty)).replace(".", ",")
        if s.endswith(",0"):
            s = s[:-2]
        return s

    ##########################################    
    # categories
    ##########################################    


    @abstractmethod
    def get_root_category(self):
        """ return id of root category """
        pass

    @abstractmethod
    def get_subcategories(self, current_category):
        """return list(Category) of subclasses of the given category-id.
        """
        pass

    @abstractmethod
    def get_category_path(self, current_category):
        """ return the category path from the root to the current category,
        *excluding* the root category
        
        [child_of_root, ..., parent_of_current, current_category]
        
        return type: list(Category)"""
        pass
    
    
    ##########################################    
    # products
    ##########################################    

    @abstractmethod
    def get_products(self, current_category):
        """return products in current category
        
        return type: list(Product)
        """
        pass
    
    @abstractmethod
    def search_product_from_code(self, code):
        """search via barcode, PLU or similar unique-ID entry. code may be any string
        
        returns product id
        
        raises ProductNotFound() if nothing found"""
        pass

    @abstractmethod
    def search_from_text(self, searchstr):
        '''
        search searchstr in products and categories
        return tuple (list of categories, products for table)
        
        return type is like in (get_subcategories(), get_products())
        '''
        pass
    
    ##########################################    
    # order handling
    ##########################################    

    @abstractmethod
    def create_order(self):
        """ create a new order and return its id"""
        pass
    
    @abstractmethod
    def delete_current_order(self):
        """ delete currently selected order"""
        pass
        
    @abstractmethod
    def set_current_order(self, order_id):
        """ switch to another order (when the backend supports multiple orders) """
        pass
    
    @abstractmethod
    def get_current_order(self):
        """ get selected order (or return 0 if switching between multiple orders is not supported) """
        pass

    @abstractmethod
    def get_order_lines(self):
        """return current order lines
        
        return type: OrderLine"""
        pass
    
    @abstractmethod
    def get_order_line(self, order_line_id):
        """ get order line of current order """
        pass
    
    
    def get_current_total(self):
        """ calculate total sum of current order
        
        returns Decimal so that values are exactly comparable """
        total = 0
        for line in self.get_order_lines():
            total += line.price_subtotal
        return float_to_decimal(round(total, 2), 2)
    
    @abstractmethod
    def update_quantity(self, order_line_id, amount):
        """ change quantity of order-line.
        
        if not all float values are allowed,
        round upvalue to the next possible one """
        pass
    
    def product_requires_text_entry(self, prod_id):
        "when adding prod_id, should the user be asked for a text entry for entering comments like his name?"
        return False
    
    @abstractmethod
    def add_order_line(self, prod_id, qty, comment=None):
        """add product to cart
        
        if not all float values are allowed,
        round upvalue to the next possible one
        
        comment: textual comment from the user, or None. The user will only be asked for a comment if self.product_requires_text_entry(prod_id) == True"""
        pass
    
    def delete_order_line(self, order_line_id):
        "delete product from cart"
        pass

    ##########################################    
    # payment
    ##########################################    


    @abstractmethod    
    def pay_order(self, method):
        """store payment of current order to database
        @param method: payment method object, whose type is ued to determine where the order should be stored in the database
        method.amount_paid - method.amount_returned is how much money was gained by this sale, must be equal to self.get_current_total()
        """
        # TODO assert amount_paid - amount_returned == self.get_current_total()
        pass
    
    def pay_order_on_client(self, client):
        """charge the order on client's account

        client: AbstractClient

        raises DebtLimitExceeded when the client's debt limit would be exceeded
        """
        debt = client.get_debt()
        new_debt = debt + self.get_current_total()
        debt_limit = client.get_debt_limit()
        if new_debt > debt_limit:
            raise DebtLimitExceeded(
                u"Der Kontostand wäre mit dieser Buchung über seinem Limit.\n" +
                u"Aktuelles Guthaben: {:.2f}\n"
                u"Schuldengrenze für dieses Konto: {:.2f}\n\n"
                u"Bie Fragen bitte an kasse@fablab.fau.de wenden."
                .format(-debt, debt_limit))

        self._pay_order_on_client_unchecked(client)

        return new_debt

    @abstractmethod
    def _pay_order_on_client_unchecked(self, client):
        """charge the order on client's account, not checking for debt limit

        client: AbstractClient"""
        pass
    
    @abstractmethod
    def list_clients(self):
        """returns all selectable clients in a dict {id: Client(id), ...}"""
        pass
    
    @abstractmethod
    def print_receipt(self, order_id):
        """print the receipt for a given, already paid order_id
        
        The receipt data must be stored in the backend, because for accountability reasons all receipt texts need to be stored anyway."""
        pass


class AbstractClient(object):
    """ a client that can pay by pin """
    __metaclass__ = ABCMeta

    @abstractmethod
    def __init__(self, client_id=None, name=""):
        """create client object"""
        self.client_id = client_id
        self.name = name

    def test_pin(self, pin):
        "is the given pin (4-digit string) correct and the client enabled for paying?"
        return False

    def get_debt(self):
        "how much is the current debt (<0 = client has pre-paid)"
        return float("inf")

    def get_debt_limit(self):
        "how much is the limit for the debt that may not be exceeded"
        return 0


def basicUnitTests(shopping_backend): # for implentations
# TODO use these somewhere
    shopping_backend.search_product("")
    shopping_backend.search_product(u"öläöäl")
    shopping_backend.search_product(u"       ")
    