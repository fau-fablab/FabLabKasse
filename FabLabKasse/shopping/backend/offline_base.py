"""basic functionality for offline backends

use case:
- categories and products are only loaded once at startup and then kept RAM for the whole application time.
- the carts are stored in RAM
"""

from abc import ABCMeta, abstractmethod  # abstract base class support
from abstract import AbstractShoppingBackend, AbstractClient, Category, OrderLine, ProductNotFound, PrinterError
from decimal import Decimal
from ... import scriptHelper
from natsort import natsorted
import re


class ProductBasedOrderLine(OrderLine):

    """OrderLine that references a Product"""

    def __init__(self, product, qty, comment=None):
        """create order line automatically just from Product instance and quantity
        The product can later be accessed by this.product
        """
        if comment is None:
            comment = ""
        if comment:
            comment = u": " + comment
        self.product = product
        self.price_per_unit = product.price  # duplicate because otherwise we get crashes from OrderLine.__init__ accessing qty.setter
        OrderLine.__init__(self, order_line_id=None, qty=0, unit=product.unit,
                           name=(product.name + comment), price_per_unit=product.price,
                           price_subtotal=0,
                           delete_if_zero_qty=(comment == ""))
        self.set_quantity_rounded(qty)

    @property
    def qty(self):
        """quantity (may only be set with set_quantity_rounded)"""
        return self._qty

    @qty.setter
    def qty(self, value):
        assert isinstance(value, (Decimal, int))
        value = Decimal(value)
        assert (self.product.qty_rounding == 0) or (value % self.product.qty_rounding == 0), "quantity must be a multiple of qty_rounding!"
        self._qty = value
        self.price_subtotal = self.price_per_unit * self._qty

    def set_quantity_rounded(self, qty):
        """update quantity, taking Product.qty_rounding into account"""
        qty = Decimal(qty)
        qty_rounding = self.product.qty_rounding
        if qty_rounding > 0:
            # round up to multiple of qty
            if qty % qty_rounding > 0:
                qty += qty_rounding - (qty % qty_rounding)
        self.qty = qty.normalize()  # use normalize() to strip trailing ,0000


class OfflineCategoryTree(object):

    """local storage for a tree of categories and products"""

    def __init__(self, root_category_id, categories=None, products=None, generate_root_category=True):
        if categories is None:
            categories = []
        if products is None:
            products = []
        self.root_category_id = root_category_id
        self.categories = {}
        self.products = {}
        if generate_root_category:
            categories += [Category(categ_id=root_category_id, name="root", parent_id=None)]

        for i in categories:
            self.add_category(i)
        for i in products:
            self.add_product(i)

        assert self.root_category_id in self.categories, "missing root category"
        cfg = scriptHelper.getConfig()
        assert cfg.getint('payup_methods', 'overpayment_product_id') in self.products, "missing product for overpayment"
        assert cfg.getint('payup_methods', 'payout_impossible_product_id') in self.products,\
            "missing product for payout_impossible"

    def add_category(self, category):
        categ_id = category.categ_id
        assert categ_id not in self.categories, "Category {0} {1} already exists: {2}".format(
            categ_id, repr(category.name), repr(self.categories[categ_id].name))
        self.categories[categ_id] = category

    def add_product(self, product):
        prod_id = product.prod_id
        assert prod_id not in self.products, "Product already exists"
        self.products[prod_id] = product

    def get_root_category(self):
        return self.categories[self.root_category_id]

    def get_subcategories(self, categ_id):
        return self._sort_categories(filter(lambda categ: categ.parent_id == categ_id, self.categories.itervalues()))

    @staticmethod
    def simplify_searchstring(string):
        # remove silly BOM
        string = string.replace(u"\ufeff", "")
        # all whitespace is treated equal
        string = re.sub(r'(\s+)', ' ', string, flags=re.UNICODE)
        string = string.replace(u'\u2010', '-')  # unicode dash
        return string.lower().strip()

    def _sort_products(self, product_list):
        return natsorted(product_list, key=lambda prod: OfflineCategoryTree.simplify_searchstring(prod.name))

    def _sort_categories(self, categ_list):
        return natsorted(categ_list, key=lambda cat: OfflineCategoryTree.simplify_searchstring(cat.name))

    def get_products(self, categ_id):
        return self._sort_products(filter(lambda prod: prod.categ_id == categ_id, self.products.itervalues()))

    def search_products(self, searchstr):
        searchlist = OfflineCategoryTree.simplify_searchstring(searchstr).split(" ")

        def matches(product):
            for keyword in searchlist:
                if keyword == "":
                    continue
                if not keyword in OfflineCategoryTree.simplify_searchstring(product.name):
                    return False
            return True

        return self._sort_products(filter(matches, self.products.itervalues()))

    def search_categories(self, searchstr):
        searchlist = OfflineCategoryTree.simplify_searchstring(searchstr).split(" ")

        def matches(categ):
            if categ == self.get_root_category():
                return False
            for keyword in searchlist:
                if not keyword in OfflineCategoryTree.simplify_searchstring(categ.name):
                    return False
            return True

        return self._sort_categories(filter(matches, self.categories.itervalues()))

    def get_product(self, prod_id):
        try:
            return self.products[prod_id]
        except KeyError:
            raise ProductNotFound()

    def get_category_path(self, categ_id):
        path = []
        assert categ_id in self.categories, "invalid category id {0}".format(categ_id)
        while categ_id not in [None, self.root_category_id]:
            try:
                path.insert(0, self.categories[categ_id])
            except KeyError:
                raise Exception("category references non-existing parent category {0}".format(categ_id))
            categ_id = self.categories[categ_id].parent_id
        return path


class Order(object):

    """simple shopping cart for use in ShoppingBackend"""

    def __init__(self):
        self._lines = []
        self._finished = False

    def _idx_from_id(self, order_line_id):
        for i, line in enumerate(self._lines):
            if line.order_line_id == order_line_id:
                return i
        raise KeyError("invalid order_line_id")

    def update_quantity(self, order_line_id, qty):
        assert not self._finished, "finished orders may not be modified"
        assert isinstance(qty, (Decimal, int))
        order_line = self._lines[self._idx_from_id(order_line_id)]
        order_line.set_quantity_rounded(qty)

    def get_order_lines(self):
        return self._lines

    def get_order_line(self, order_line_id):
        return self._lines[self._idx_from_id(order_line_id)]

    def delete_order_line(self, order_line_id):
        assert not self._finished, "finished orders may not be modified"
        del self._lines[self._idx_from_id(order_line_id)]

    def add_order_line(self, product, qty, comment=None):
        """ add a Product() object with specified quantity to the cart"""
        assert not self._finished, "finished orders may not be modified"
        assert comment is None or isinstance(comment, basestring)
        self._lines.append(ProductBasedOrderLine(product, qty, comment))
        # call update_quantity so that qty_rounding is checked
        self.update_quantity(self._lines[-1].order_line_id, qty)

    def set_finished(self):
        self._finished = True

    @property
    def finished(self):
        return self._finished

    def print_receipt(self):
        raise PrinterError("not yet implemented")


class AbstractOfflineShoppingBackend(AbstractShoppingBackend):

    """manages products, categories and orders (cart)"""
    __metaclass__ = ABCMeta

    def __init__(self, cfg, categories, products, generate_root_category=False):
        super(AbstractOfflineShoppingBackend, self).__init__(cfg)
        self._current_order = None

        self.tree = OfflineCategoryTree(root_category_id=0,
                                        categories=categories,
                                        products=products, generate_root_category=generate_root_category)
        self.orders = []

    # ==============================
    # categories
    # ==============================

    def get_root_category(self):
        """ return id of root category """
        return 0

    def get_subcategories(self, current_category):
        # return [Category(categ_id=7, name="Lasercutter"), Category(categ_id=1, name="3D Printer")]
        return self.tree.get_subcategories(current_category)

    def get_category_path(self, current_category):
        # return [Category(categ_id=7, name="Lasercutter"), Category(categ_id=1, name="Laser Material")]
        return self.tree.get_category_path(current_category)

    # ==============================
    # products
    # ==============================

    def get_products(self, current_category):
        """return products in current category

        as a sorted list of dicts:
         {'name': text, 'id': int, 'unit': text, 'location': text, 'price': float}
        """
        # return [Product(prod_id=123, name="Acrylic 3mm", unit="Sheet 60x30cm", location="Shelf E3.1", price=11.31, categ_id=current_category)]
        return self.tree.get_products(current_category)

    def search_product_from_code(self, code):
        """search via barcode, PLU or similar unique-ID entry. code may be any string

        :returns: *valid* product id

        :raises: ProductNotFound() if nothing found"""
        if code.isdigit() and int(code) in self.tree.products:
            return int(code)
        else:
            raise ProductNotFound()

    def search_from_text(self, searchstr):
        # 1. search by product code
        try:
            matching_product = self.search_product_from_code(searchstr)
            matching_product = [self.tree.get_product(matching_product)]
        except ProductNotFound:
            matching_product = []

        # 2. search by string
        return (self.tree.search_categories(searchstr), matching_product + self.tree.search_products(searchstr))

    # ==============================
    # order handling
    # ==============================

    # TODO order_id must be a nonchanging unique id...
    # use some uniqueIdFactory singleton class?

    def get_orders(self):
        # return [(o.order_id, "todo title") for o in self.orders]
        raise NotImplementedError()

    def create_order(self):
        new_order = Order()
        self.orders.append(new_order)
        return id(new_order)

    def delete_current_order(self):
        self.orders.remove(self._get_current_order_obj())
        self.set_current_order(None)

    def set_current_order(self, order_id):
        self._current_order = order_id

    def _get_order_by_id(self, order_id):
        for i in self.orders:
            if id(i) == order_id:
                return i
        raise KeyError("invalid order_id")

    def _get_current_order_obj(self):
        try:
            return self._get_order_by_id(self._current_order)
        except KeyError:
            raise KeyError("invalid _current_order index. this must not happen.")

    def get_current_order(self):
        """ get selected order id (or return 0 if switching between multiple orders is not supported) """
        return self._current_order

    def get_order_line(self, order_line_id):
        """ get order line of current order """
        return self._get_current_order_obj().get_order_line(order_line_id)

    def get_order_lines(self):
        if self.get_current_order() is None:
            return []
        return self._get_current_order_obj().get_order_lines()

    def update_quantity(self, order_line_id, amount):
        self._get_current_order_obj().update_quantity(order_line_id, amount)

    def product_requires_text_entry(self, prod_id):
        return self.tree.products[prod_id].text_entry_required

    def add_order_line(self, prod_id, qty, comment=None):
        try:
            product = self.tree.products[prod_id]
        except KeyError:
            raise ProductNotFound()
        self._get_current_order_obj().add_order_line(product, qty, comment)

    def delete_order_line(self, order_line_id):
        self._get_current_order_obj().delete_order_line(order_line_id)

    # ==============================
    # payment
    # ==============================

    def pay_order(self, method):
        assert method.amount_paid - method.amount_returned == self.get_current_total(), "Paid amount does not match current total. Payment method returned: {}, expected total: {}, current order: {} ".format(method, repr(self.get_current_total()), repr(self.get_order_lines()))
        self._get_current_order_obj().set_finished()
        self._store_payment(method)

    @abstractmethod
    def _store_payment(self, method):
        """store payment of current order to database
        see pay_order
        """
        pass

    def _pay_order_on_client_unchecked(self, client):
        self._get_current_order_obj().set_finished()
        self._store_client_payment(client)

    @abstractmethod
    def _store_client_payment(self, client):
        """save client payment of current order to database

        :param client: AbstractClient"""
        pass

    def print_receipt(self, order_id):
        self._get_current_order_obj().print_receipt()

    @abstractmethod
    def list_clients(self):
        pass


class Client(AbstractClient):

    """ a client that can pay by pin """

    def __init__(self, client_id=None, name="", pin=None, debt=None, debt_limit=None, is_admin=None):
        AbstractClient.__init__(self, client_id, name)
        if debt is not None:
            self._debt = debt
        self._pin = str(pin)
        if debt_limit is not None:
            self._debt_limit = debt_limit
        self._admin = is_admin

    def test_pin(self, pin):
        return self._pin == pin and not pin == "0000"

    def get_debt(self):
        return self._debt

    def get_debt_limit(self):
        return self._debt_limit
    
    def is_admin(self):
        return self._admin
