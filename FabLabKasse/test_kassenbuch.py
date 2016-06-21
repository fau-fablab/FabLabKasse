#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Patrick Kanzler <patrick.kanzler@fablab.fau.de>
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

"""unittests for kassenbuch.py"""

import unittest
from FabLabKasse.kassenbuch import Kasse, Kunde, Buchung, Rechnung, NoDataFound, parse_args
from FabLabKasse.kassenbuch import argparse_parse_date, argparse_parse_currency
from hypothesis import given
from hypothesis.strategies import text
import hypothesis.extra.datetime as hypothesis_datetime
import dateutil
from datetime import datetime, timedelta
from decimal import Decimal


class KassenbuchTestCase(unittest.TestCase):
    """unittests for kassenbuch.py"""

    def test_argparse(self):
        """
        test the argparser
        """
        # test show
        args = parse_args("show".split(' '))
        self.assertEqual(args.action, 'show')
        self.assertFalse(args.hide_receipts)
        self.assertIsNone(args.from_date)
        self.assertIsNone(args.until_date)
        args = parse_args("show --hide-receipts".split(' '))
        self.assertEqual(args.action, 'show')
        self.assertTrue(args.hide_receipts)
        self.assertIsNone(args.from_date)
        self.assertIsNone(args.until_date)
        args = parse_args(['show', '--hide-receipts',
                          '--from', '2016-12-31 13:37:42'])
        self.assertEqual(args.action, 'show')
        self.assertTrue(args.hide_receipts)
        self.assertEquals(args.from_date, dateutil.parser.parse("2016-12-31 13:37:42"))
        self.assertIsNone(args.until_date)
        args = parse_args("show --hide-receipts "
                          "--from 2016-12-31 "
                          "--until 2017-1-23".split(' '))
        self.assertEqual(args.action, 'show')
        self.assertTrue(args.hide_receipts)
        self.assertEquals(args.from_date, dateutil.parser.parse("2016-12-31"))
        self.assertEquals(args.until_date, dateutil.parser.parse("2017-1-23"))
        # TODO more tests: Everytime you fix a bug in argparser, add a test

    def test_parsing(self):
        """test argument parsing helper"""
        self.assertEqual(argparse_parse_currency(' 13,37€ '), Decimal('13.37'))
        self.assertAlmostEqual(argparse_parse_date('today'), datetime.today(),
                               delta=timedelta(minutes=5))
        self.assertAlmostEqual(argparse_parse_date('yesterday'),
                               datetime.today() - timedelta(1),
                               delta=timedelta(minutes=5))
        self.assertEqual(argparse_parse_date("2016-12-31 13:37:42"),
                         dateutil.parser.parse("2016-12-31 13:37:42"))

    def test_accounting_database_setup(self):
        """tests the creation of the accounting database"""
        kasse = Kasse(sqlite_file=':memory:')
        kasse.con.commit()
        # TODO check the database instead of the functions of Kasse
        self.assertFalse(kasse.kunden)
        self.assertFalse(kasse.rechnungen)
        self.assertFalse(kasse.buchungen)

    @given(clientname=text())
    def test_accounting_database_client_creation(self, clientname):
        """very basically test the creation of a new client"""
        kasse = Kasse(sqlite_file=':memory:')
        self.assertFalse(kasse.kunden)
        # TODO thouroughly test client creation, this seems to be fishy somewhere
        bob = Kunde(clientname, schuldengrenze=0)
        bob.store(cur=kasse.cur)
        kasse.con.commit()
        try:
            Kunde.load_from_name(clientname, kasse.cur)
        except NoDataFound:
            self.fail("client entry in database has not been created")
        # TODO test integrity checking (no double creation of same ID)
        # TODO code crashes when reading Kunde with "None" in e.g. schuldengrenze

    @given(from_date=hypothesis_datetime.datetimes(), until_date=hypothesis_datetime.datetimes())
    def test_datestring_generator(self, from_date, until_date):
        """test the datestring_generator in Kasse"""
        query = Kasse._date_query_generator('buchung', from_date=from_date, until_date=until_date)
        pristine_query = "SELECT id FROM buchung WHERE datum >= Datetime('{from_date}') AND " \
                         "datum < Datetime('{until_date}')".format(from_date=from_date, until_date=until_date)
        assert(query == pristine_query)
        query = Kasse._date_query_generator('buchung', until_date=until_date)
        pristine_query = "SELECT id FROM buchung WHERE datum < Datetime('{until_date}')".format(until_date=until_date)
        assert(query == pristine_query)
        query = Kasse._date_query_generator('buchung', from_date=from_date)
        pristine_query = "SELECT id FROM buchung WHERE datum >= Datetime('{from_date}')".format(from_date=from_date)
        assert(query == pristine_query)

    @given(rechnung_date=hypothesis_datetime.datetimes(min_year=1900, timezones=[]),
           from_date=hypothesis_datetime.datetimes(min_year=1900, timezones=[]),
           until_date=hypothesis_datetime.datetimes(min_year=1900, timezones=[]))
    def test_get_rechnungen(self, rechnung_date, from_date, until_date):
        """test the get_rechnungen function"""
        kasse = Kasse(sqlite_file=':memory:')
        rechnung = Rechnung(datum=rechnung_date.strftime('%Y-%m-%d %H:%M:%S.%f'))
        rechnung.store(kasse.cur)
        kasse.con.commit()

        query = kasse.get_rechnungen(from_date, until_date)
        if from_date <= rechnung_date < until_date:
            assert query
        else:
            assert(not query)

    @given(buchung_date=hypothesis_datetime.datetimes(min_year=1900, timezones=[]),
           from_date=hypothesis_datetime.datetimes(min_year=1900, timezones=[]),
           until_date=hypothesis_datetime.datetimes(min_year=1900, timezones=[]))
    def test_get_buchungen(self, buchung_date, from_date, until_date):
        """test the get_buchungen function"""
        kasse = Kasse(sqlite_file=':memory:')
        rechnung = Rechnung(datum=buchung_date.strftime('%Y-%m-%d %H:%M:%S.%f'))
        rechnung.store(kasse.cur)
        buchung = Buchung(konto='somewhere',
                          betrag='0',
                          rechnung=rechnung.id,
                          kommentar="Passing By And Thought I'd Drop In",
                          datum=buchung_date.strftime('%Y-%m-%d %H:%M:%S.%f'))
        buchung._store(kasse.cur)
        kasse.con.commit()

        #TODO load_from_row ist sehr anfällig gegen kaputte datetimes, das sollte am besten schon sauber in die Datenbank
        query = kasse.get_buchungen(from_date, until_date)
        if from_date <= buchung_date < until_date:
            assert query
        else:
            assert(not query)
