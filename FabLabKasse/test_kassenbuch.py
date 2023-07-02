#!/usr/bin/env python3
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
from __future__ import unicode_literals

import unittest
from .kassenbuch import (
    Kasse,
    Kunde,
    Buchung,
    Rechnung,
    NoDataFound,
    parse_args,
)
from .kassenbuch import argparse_parse_date, argparse_parse_currency
from hypothesis import given, reproduce_failure
from hypothesis.strategies import text, datetimes
import dateutil
from datetime import datetime, timedelta
from decimal import Decimal
import subprocess
import os
import random
import tempfile
from pathlib import Path


class KassenbuchTestCase(unittest.TestCase):
    """unittests for kassenbuch.py"""

    def test_argparse(self):
        """
        test the argparser
        """
        # test show
        args = parse_args("show".split(" "))
        self.assertEqual(args.action, "show")
        self.assertFalse(args.hide_receipts)
        self.assertIsNone(args.from_date)
        self.assertIsNone(args.until_date)
        args = parse_args("show --hide-receipts".split(" "))
        self.assertEqual(args.action, "show")
        self.assertTrue(args.hide_receipts)
        self.assertIsNone(args.from_date)
        self.assertIsNone(args.until_date)
        args = parse_args(["show", "--hide-receipts", "--from", "2016-12-31 13:37:42"])
        self.assertEqual(args.action, "show")
        self.assertTrue(args.hide_receipts)
        self.assertEqual(args.from_date, dateutil.parser.parse("2016-12-31 13:37:42"))
        self.assertIsNone(args.until_date)
        args = parse_args(
            "show --hide-receipts " "--from 2016-12-31 " "--until 2017-1-23".split(" ")
        )
        self.assertEqual(args.action, "show")
        self.assertTrue(args.hide_receipts)
        self.assertEqual(args.from_date, dateutil.parser.parse("2016-12-31"))
        self.assertEqual(args.until_date, dateutil.parser.parse("2017-1-23"))

        # test ensure_dummy_db
        args = parse_args("--ensure-dummy-db show".split(" "))
        self.assertTrue(args.ensure_dummy_db)
        args = parse_args("show".split(" "))
        self.assertFalse(args.ensure_dummy_db)
        # TODO more tests: Everytime you fix a bug in argparser, add a test

    def test_shell_interface(self):
        """
        test calling kassenbuch.py from shell
        """

        def call_kb(command: str) -> str:
            """
            call kassenbuch.py --ensure-dummy-db $command

            command is a single string containing the space-separated arguments

            Return value is the script output.

            Raise an exception if the script doesn't return with 0.

            Note that this requires that the database name in config.ini is set to "development.sqlite3"
            """
            path_to_here = os.path.dirname(os.path.realpath(__file__))
            cmd = [
                path_to_here + "/kassenbuch.py",
                "--ensure-dummy-db",
            ] + command.split(" ")
            cmd = [x.encode("UTF-8") for x in cmd]
            result = subprocess.run(cmd, encoding="UTF-8", capture_output=True)
            self.assertEqual(result.returncode, 0, "Command failed: " + repr(result))
            return result.stdout

        call_kb("summary")
        call_kb("show")
        call_kb("client list")
        randstr = str(random.randint(0, int(1e30)))
        comment = "My Comment Äöü " + randstr
        call_kb("transfer TestA TestB 123.45 " + comment)
        result_show = call_kb("show")
        self.assertTrue(comment in result_show)
        with tempfile.TemporaryDirectory() as d:
            call_kb(f"export book {d}/book.csv");
            self.assertTrue(comment in Path(f"{d}/book.csv").read_text());
            call_kb(f"export invoices {d}/invoices.csv");
            # output of invoices is currently not tested

    def test_parsing(self):
        """test argument parsing helper"""
        self.assertEqual(argparse_parse_currency(" 13,37€ "), Decimal("13.37"))
        self.assertAlmostEqual(
            argparse_parse_date("today"), datetime.today(), delta=timedelta(minutes=5)
        )
        self.assertAlmostEqual(
            argparse_parse_date("yesterday"),
            datetime.today() - timedelta(1),
            delta=timedelta(minutes=5),
        )
        self.assertEqual(
            argparse_parse_date("2016-12-31 13:37:42"),
            dateutil.parser.parse("2016-12-31 13:37:42"),
        )

    def test_accounting_database_setup(self):
        """tests the creation of the accounting database"""
        kasse = Kasse(sqlite_file=":memory:")
        kasse.con.commit()
        # TODO check the database instead of the functions of Kasse
        self.assertFalse(kasse.kunden)
        self.assertFalse(kasse.rechnungen)
        self.assertFalse(kasse.buchungen)

    @given(clientname=text())
    def test_accounting_database_client_creation(self, clientname):
        """very basically test the creation of a new client"""
        kasse = Kasse(sqlite_file=":memory:")
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

    @given(
        from_date=datetimes(),
        until_date=datetimes(),
    )
    def test_datestring_generator(self, from_date, until_date):
        """test the datestring_generator in Kasse"""
        # Test removed because it was just a 1:1 copy of the code.
        # This function is not tested separately, but indirectly via the test of get_rechnungen.
        pass

    @given(
        rechnung_date=datetimes(min_value=datetime(1900, 1, 1)),
        from_date=datetimes(min_value=datetime(1900, 1, 1)),
        until_date=datetimes(min_value=datetime(1900, 1, 1)),
    )
    def test_get_rechnungen(self, rechnung_date, from_date, until_date):
        """test the get_rechnungen function"""
        kasse = Kasse(sqlite_file=":memory:")
        rechnung = Rechnung(datum=rechnung_date)
        rechnung.store(kasse.cur)
        kasse.con.commit()

        query = kasse.get_rechnungen(from_date, until_date)
        if from_date <= rechnung_date < until_date:
            self.assertTrue(query)
        else:
            self.assertFalse(query)

    @given(
        buchung_date=datetimes(min_value=datetime(1900, 1, 1)),
        from_date=datetimes(min_value=datetime(1900, 1, 1)),
        until_date=datetimes(min_value=datetime(1900, 1, 1)),
    )
    def test_get_buchungen(self, buchung_date, from_date, until_date):
        """test the get_buchungen function"""
        kasse = Kasse(sqlite_file=":memory:")
        rechnung = Rechnung(datum=buchung_date)
        rechnung.store(kasse.cur)
        buchung = Buchung(
            konto="somewhere",
            betrag="0",
            rechnung=rechnung.id,
            kommentar="Passing By And Thought I'd Drop In",
            datum=buchung_date,
        )
        buchung._store(kasse.cur)
        kasse.con.commit()

        query = kasse.get_buchungen(from_date, until_date)
        if from_date <= buchung_date < until_date:
            self.assertTrue(query)
        else:
            self.assertFalse(query)
