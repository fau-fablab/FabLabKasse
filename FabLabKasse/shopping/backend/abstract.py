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
from decimal import Decimal, ROUND_HALF_UP
import itertools
import locale
import unittest
import doctest
from ConfigParser import Error as ConfigParserError

# counter for unique id values, use next(_id_counter) to get a new ID
_id_counter = itertools.count()


def float_to_decimal(number, digits):
    """
    convert float to decimal with rounding and strict error tolerances

    If the given number cannot be represented as decimal with an error
    within 1/1000 of the last digit, :exc:`ValueError` is raised.

    :param number: a float that is nearly equal to a decimal number
    :type number: float | Decimal
    :param digits: number of decimal places of the resulting value (max. 9)
    :type digits: int

    :raise: ValueError

    >>> float_to_decimal(1.424, 3)
    Decimal('1.424')
    >>> float_to_decimal(0.7, 1)
    Decimal('0.7')
    """

    # conversion is guaranteed to be accurate at 1e12 for 0 digits
    # larger values are maybe not correctly represented in a float, so we are careful here
    assert isinstance(digits, int)
    assert 0 <= digits < 10, "invalid number of digits"
    result = Decimal(int(round(number * (10 ** digits)))) / (10 ** digits)
    if not abs(number) < 10 ** (10 + digits):
        raise ValueError("cannot precisely convert such a large float to Decimal")
    if not abs(float(result) - float(number)) < (10 ** -(digits + 3)):
        raise ValueError("attempted inaccurate conversion from {0} to {1}".format(repr(number), repr(result)))
    return result


def format_qty(qty):
    """format quantity (number) as string

    :param qty: quantity in numbers
    :return: string-representation of qty, decimal sep is dependent on locale
    :rtype: unicode

    >>> format_qty(5)
    u'5'
    """
    s = unicode(float(qty))
    if s.endswith(".0"):
        s = s[:-2]
    s = s.replace(".", locale.localeconv()['decimal_point'])
    return s


def format_money(amount):
    """format float as money string

    You should best use Decimal as input.
    TODO: make moneysign interchangeable

    :param amount: amount of money
    :type amount: float|Decimal
    :return: amount formatted as string with Euro-Sign
    :rtype: unicode

    >>> format_money(1.23)
    u'1,23 \u20ac'
    >>> format_money(3.741)
    u'3,741 \u20ac'
    >>> format_money(42.4242)
    u'42,424 \u20ac'
    >>> format_money(5.8899)
    u'5,89 \u20ac'
    >>> format_money(Decimal('1.23'))
    u'1,23 \u20ac'
    >>> format_money(Decimal('3.741'))
    u'3,741 \u20ac'
    >>> format_money(Decimal('42.4242'))
    u'42,424 \u20ac'
    >>> format_money(Decimal('5.8899'))
    u'5,89 \u20ac'
    """
    formatted = u'{0:.3f}'.format(amount)

    if formatted.endswith("0"):
        formatted = formatted[:-1]

    return u'{0} €'.format(formatted).replace('.', ',')


class Category(object):
    """represents a category of Products"""

    def __init__(self, categ_id, name, parent_id=None):
        self.categ_id = categ_id
        self.name = name
        self.parent_id = parent_id

    def __repr__(self):
        return "Category({0}, {1}, {2})".format(self.categ_id, repr(self.name), self.parent_id)


class Product(object):

    """simple representation for a product

    :param prod_id: numeric unique product ID
    :type prod_id: int
    :param categ_id: category ID of product, or None if the product is not directly visible

                     TODO hide these products from search, or a more explicit solution
    :type categ_id: int | None
    :param name: Name of product
    :type name: unicode
    :param location: Location of product (shown to the user)
    :type location: unicode
    :param unit: Unit of sale for this product (e.g. piece, kilogram)
    :type unit: unicode
    :type price: Decimal
    :param price: price for one unit of this product
    :param qty_rounding: Product can only be bought in multiples of this quantity, user (GUI) input will be rounded/truncated to the next multiple of this.

                         Set to 0 so that the product can be bought in arbitrarily small quantities.

                         example: you cannot buy half a t-shirt, so you set qty_rounding = 1

                         handling this is responsibility of the shopping backend

    :type qty_rounding: int | Decimal
    """

    def __init__(self, prod_id, name, price, unit, location, categ_id=None, qty_rounding=0, text_entry_required=False):

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
    """
    one order line (roughly equal to a product in a shopping cart,
    although there may be multiple entries for one product)

    :param id: id of order-line, *must be unique and non-changing* inside one Order() (if None: autogenerate id)

    :param Decimal qty: amount ("unlimited" number of digits is okay)

    :param unicode unit: product unit of sale

    :param unicode name: product name

    :param Decimal price_per_unit: price for one unit

    :param Decimal price_subtotal: price for ``qty`` * ``unit``  of this product

    :param boolean delete_if_zero_qty: if the qty is zero and the user starts adding something else, then remove this line


       [ usually True, set to False for products that also may as comment limes costing nothing ]
    """

    def __init__(self, order_line_id, qty, unit, name, price_per_unit, price_subtotal, delete_if_zero_qty=True):

        self.order_line_id = order_line_id
        if order_line_id is None:
            self.order_line_id = next(_id_counter)  # may cause problems after ca. 2**30 calls because QVariant in gui somewhere converts values to int32. but who cares...
        self.qty = qty
        self.unit = unit
        self.name = name
        assert isinstance(price_per_unit, (Decimal, int))
        self.price_per_unit = price_per_unit
        isinstance(price_subtotal, (Decimal, int))
        self.price_subtotal = price_subtotal
        self.delete_if_zero_qty = delete_if_zero_qty

    def __unicode__(self):
        return u"{0} {1} {2} = {3}".format(format_qty(self.qty), self.unit, self.name, format_money(self.price_subtotal))

    def __repr__(self):
        return "<{0}(id={1}, qty={2}, unit={3}, name={4}, price_per_unit={5}, price_subtotal={6})>".format(self.__class__.__name__, repr(self.order_line_id), repr(self.qty), repr(self.unit), repr(self.name), repr(self.price_per_unit), repr(self.price_subtotal))


class DebtLimitExceeded(Exception):

    """exception raised by pay_order_on_client: order not paid because
    the debt limit would have been exceeded"""
    pass


class ProductNotFound(Exception):

    """requested product not found"""
    pass


class PrinterError(Exception):

    """cannot print receipt"""
    pass


class AbstractShoppingBackend(object):

    """manages products, categories and orders (cart)"""
    __metaclass__ = ABCMeta

    def __init__(self, cfg):
        """:param cfg: config from ScriptHelper.getConfig()"""
        self.cfg = cfg

    def format_money(self, amount):
        return format_money(amount)

    def format_qty(self, qty):
        return format_qty(qty)

    @staticmethod
    def round_money(value):
        """rounds money in Decimal representation to 2 places

        Main purpose is shopping.backend.abstract.AbstractShoppingBackend.get_current_total(),
        since round() does behave weird. But maybe there are other applications too.

        :param value: an amount of money to be rounded
        :type value: float | Decimal
        :return: money, rounded to 2 digits
        :rtype: Decimal

        >>> AbstractShoppingBackend.round_money(Decimal('0.005'))
        Decimal('0.01')
        >>> AbstractShoppingBackend.round_money(Decimal('0.004'))
        Decimal('0.00')
        """
        value = Decimal(value).quantize(Decimal('1.00'), rounding=ROUND_HALF_UP)
        return value

    # ====================================
    # categories
    # ====================================

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

        :rtype: list(Category)
        """
        pass

    # ====================================
    # products
    # ====================================

    @abstractmethod
    def get_products(self, current_category):
        """return products in current category

        :rtype: list(Product)
        """
        pass

    @abstractmethod
    def search_product_from_code(self, code):
        """search via barcode, PLU or similar unique-ID entry. code may be any string

        :returns: product id

        :raises: ProductNotFound() if nothing found"""
        pass

    @abstractmethod
    def search_from_text(self, searchstr):
        """
        search searchstr in products and categories
        :return: tuple (list of categories, products for table)

        :rtype: list(Product)
        """
        pass

    #
    # order handling
    #

    @abstractmethod
    def create_order(self):
        """ create a new order and return its id"""
        pass

    @abstractmethod
    def delete_current_order(self):
        """ delete currently selected order, implies set_current_order(None) """
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

        :rtype: OrderLine
        """
        pass

    @abstractmethod
    def get_order_line(self, order_line_id):
        """ get order line of current order """
        pass

    def get_current_total(self):
        """
        :return: total sum of current order
        :rtype: Decimal

        Note: The internal rounding *must* be consistent, which is needed by
        :class: FabLabKasse.shopping.payment_methods. That means that x,xx5 €
        must always be rounded up or always down. "Fair rounding" like
        Decimal.ROUND_HALF_EVEN is not allowed.

        For example:

        - add article costing 1,015 € -> get_current_total == x
        - add article costing 0,990 € -> get_current_total == x + 0,99

        This would not be true with the fair strategy "round second digit to
        even value if the third one is exactly 5" (1,02€ and 2,00€).
        """
        total = 0
        for line in self.get_order_lines():
            total += line.price_subtotal
        return self.round_money(total)

    @abstractmethod
    def update_quantity(self, order_line_id, amount):
        """ change quantity of order-line.

        if not all float values are allowed,
        round upvalue to the next possible one """
        pass

    def product_requires_text_entry(self, prod_id):
        """when adding prod_id, should the user be asked for a text entry for entering comments like his name?"""
        return False

    @abstractmethod
    def add_order_line(self, prod_id, qty, comment=None):
        """add product to cart

        if not all values are allowed, ``qty`` is rounded *up*
        to the next possible amount.

        The user should only be asked for a comment by the GUI if
        ``self.product_requires_text_entry(prod_id) == True``

        :param prod_id: product
        :type prod_id: int
        :param qty: amount of product
        :type qty: Decimal
        :type comment: (basestring, None)
        :param comment: textual comment from the user, or None.
        :raise: ProductNotFound
        """
        pass

    def delete_order_line(self, order_line_id):
        """delete product from cart"""
        pass

    #
    # payment
    #

    @abstractmethod
    def pay_order(self, method):
        """store payment of current order to database
        :param method: payment method object, whose type is used to determine where the order should be stored in the database
        method.amount_paid - method.amount_returned is how much money was gained by this sale, must be equal to self.get_current_total()
        """
        # TODO assert amount_paid - amount_returned == self.get_current_total()
        pass

    def pay_order_on_client(self, client):
        """charge the order on client's account

        :param client: AbstractClient

        :raises: DebtLimitExceeded when the client's debt limit would be exceeded
        """
        debt = client.get_debt()
        new_debt = debt + self.get_current_total()
        debt_limit = client.get_debt_limit()
        if new_debt > debt_limit:
            try:
                email = self.cfg.get('general', 'support_mail')
            except ConfigParserError:
                email = u"einen zuständigen Betreuer"
            raise DebtLimitExceeded(
                u"Der Kontostand wäre mit dieser Buchung über seinem Limit.\n"
                u"Aktuelles Guthaben: {0:.2f}\n"
                u"Schuldengrenze für dieses Konto: {1:.2f}\n\n"
                u"Bie Fragen wende dich bitte an {2}."
                .format(-debt, debt_limit, email))

        self._pay_order_on_client_unchecked(client)

        return new_debt

    @abstractmethod
    def _pay_order_on_client_unchecked(self, client):
        """charge the order on client's account, not checking for debt limit

        :param client: AbstractClient
        """
        pass

    @abstractmethod
    def list_clients(self):
        """returns all selectable clients in a dict {id: Client(id), ...}"""
        pass

    @abstractmethod
    def print_receipt(self, order_id):
        """print the receipt for a given, already paid order_id

        The receipt data must be stored in the backend, because for accountability reasons all receipt texts
        need to be stored anyway.
        """
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
        """is the given pin (4-digit string) correct and the client enabled for paying?"""
        return False

    def get_debt(self):
        """how much is the current debt (<0 = client has pre-paid)"""
        return float("inf")

    def get_debt_limit(self):
        """how much is the limit for the debt that may not be exceeded"""
        return 0


def basicUnitTests(shopping_backend):  # for implentations
    # TODO use these somewhere, integrate into unittest below
    shopping_backend.search_product("")
    shopping_backend.search_product(u"öläöäl")
    shopping_backend.search_product(u"       ")

def load_tests(loader, tests, ignore):
    """loader function to load the doctests in this module into unittest"""
    tests.addTests(doctest.DocTestSuite('FabLabKasse.shopping.backend.abstract'))
    return tests


class AbstractShoppingBackendTest(unittest.TestCase):

    """test the AbstractShoppingBackend class

    TODO extend this test
    """

    def test_round_money_subcent_values(self):
        """test the money-rounding function

        the test checks the rounding of subcent values
        """
        for i in range(1000):
            # round up 0.005  -> 0.01
            reference = (i + 1) * Decimal("0.01")
            self.assertEqual(AbstractShoppingBackend.round_money(Decimal("0.005") + Decimal("0.01") * i), reference)


if __name__ == "__main__":
    unittest.main()
