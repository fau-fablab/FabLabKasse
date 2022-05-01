.. FabLabKasse documentation master file, created by
   sphinx-quickstart on Tue Jul 14 00:11:04 2015.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to FabLabKasse's documentation!
=======================================

Contents:

.. toctree::
   :maxdepth: 1

   buildyourown/index
   FabLabKasse


Code structure overview
=======================

- :mod:`run` is the launcher, it starts :mod:`FabLabKasse.gui`
- the rest of the code is in folder FabLabKasse
- kassenbuch.py (currently still german) accounting CLI for legacy_offline_kassenbuch shopping backend
- produkt.py is directly in FabLabKasse-folder for legacy reasons

- shopping:

  - backend: backends that provide connection to a webshop, ERP system, database etc and manages products, categories, carts and financial accounting (storage of payments)

    - abstract: abstract base class
    - offline_base: abstract base class for backends that read products only once at the start and keep the cart in memory; as opposed to a always-online system that has its whole state somewhere in the cloud
    - dummy: has some fake products, just silently accepts all payments without storing them somewhere
    - oerp: OpenERP / odoo implementation, still needs testing.
    - legacy_offline_kassenbuch: backend with product importing from a python script, SQLite based double-entry bookkeeping, contains many german database field names and is therefore marked as legacy. With some re-writing it would make a decent SQLite backend. Has a management CLI kassenbuch.py in the main folder.

  - payment_methods: different methods of payment like manual cash entry, cashless payment, charge on client account, ...
- libs: some helping libraries
- produkte: empty directory for local caching of product data (TODO rename)
- scripts: some helping cronjobs
  - TODO


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

