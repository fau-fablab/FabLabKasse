#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
# PYTHON_ARGCOMPLETE_OK


# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and
# trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Patrick Kanzler <patrick.kanzler@fablab.fau.de>
#                     Timo Voigt <timo@fablab.fau.de>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.

"""
Kassenbuch Backend mit doppelter Buchführung.
"""

from __future__ import print_function

import sqlite3
import argparse
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
import dateutil.parser
import csv
import cStringIO
import codecs
import re
import sys
import os
import random
import doctest
try:
    import argcomplete
except ImportError:
    pass  # it's also working without argcomplete

import libs.escpos.printer as escpos_printer
import scriptHelper


def moneyfmt(value, places=2, curr='', sep='.', dp=',',
             pos='', neg='-', trailneg=''):
    """Convert Decimal to a money formatted string.
    ::

        :param places:  required number of places after the decimal point
        :param curr:    optional currency symbol before the sign (may be blank)
        :param sep:     optional grouping separator (comma, period, space, or blank)
        :param dp:      decimal point indicator (comma or period)
                        only specify as blank when places is zero
        :param pos:     optional sign for positive numbers: '+', space or blank
        :param neg:     optional sign for negative numbers: '-', '(', space or blank
        :param trailneg:optional trailing minus indicator:  '-', ')', space or blank

        >>> d = Decimal('-1234567.8901')
        >>> moneyfmt(d, curr='$')
        '-$1.234.567,89'
        >>> moneyfmt(d, places=0, sep=',', dp='', neg='', trailneg='-')
        '1,234,568-'
        >>> moneyfmt(d, curr='$', neg='(', trailneg=')')
        '($1.234.567,89)'
        >>> moneyfmt(Decimal(123456789), sep=' ')
        '123 456 789,00'
        >>> moneyfmt(Decimal('-0.02'), neg='<', trailneg='>')
        '<0,02>'

        Based on https://docs.python.org/2/library/decimal.html
    """
    q = Decimal(10) ** -places  # 2 places --> '0.01'
    sign, digits, exp = value.quantize(q).as_tuple()
    result = []
    digits = map(str, digits)
    build, next = result.append, digits.pop
    if sign:
        build(trailneg)
    for i in range(places):
        build(next() if digits else '0')
    build(dp)
    if not digits:
        build('0')
    i = 0
    while digits:
        build(next())
        i += 1
        if i == 3 and digits:
            i = 0
            build(sep)
    build(curr)
    build(neg if sign else pos)
    return ''.join(reversed(result))


def load_tests(loader, tests, ignore):
    """loader function to load the doctests in this module into unittest"""
    tests.addTests(doctest.DocTestSuite('FabLabKasse.kassenbuch'))
    return tests


class NoDataFound(Exception):
    pass


class Rechnung(object):

    def __init__(self, id=None, datum=None):
        self.id = id

        if not datum:
            self.datum = datetime.now()
        else:
            self.datum = datum

        self.positionen = []

    @property
    def summe(self):
        s = Decimal(0)
        for pos in self.positionen:
            s += self.summe_position(pos)

        return s

    def add_position(self, artikel, einzelpreis, anzahl=Decimal(1), einheit='', produkt_ref=None):
        self.positionen.append({'id': None, 'rechnung': None, 'anzahl': Decimal(anzahl),
                                'einheit': einheit, 'artikel': artikel, 'einzelpreis': Decimal(einzelpreis),
                                'produkt_ref': produkt_ref})

    def summe_position(self, pos):
        return pos['anzahl'] * pos['einzelpreis']

    def to_string(self):
        s = u'Rechnungsnr.: {0}\nDatum: {1:%Y-%m-%d %H:%M}\n'.format(self.id, self.datum)

        for p in self.positionen:
            s += u'    {anzahl:>7.2f} {einheit:<8} {artikel:<45} {einzelpreis:>8.3f} EUR {gesamtpreis:>8.2f} EUR\n'.format(
                gesamtpreis=self.summe_position(p), **p)

        s += u'Summe: ' + moneyfmt(self.summe) + ' EUR\n'

        return s

    def _load_positionen(self, cur):
        cur.execute(
            "SELECT id, rechnung, anzahl, einheit, artikel, einzelpreis, produkt_ref FROM position WHERE rechnung=?",
            (self.id,))
        for row in cur:
            self.positionen.append({'id': row[0], 'rechnung': row[1],
                                    'anzahl': Decimal(row[2]), 'einheit': unicode(row[3]), 'artikel': unicode(row[4]),
                                    'einzelpreis': Decimal(row[5]), 'produkt_ref': row[6]})

        self.positionen.sort(key=lambda p: p['id'])

    @classmethod
    def load_from_id(cls, id, cur):
        cur.execute("SELECT id, datum FROM rechnung WHERE id = ?", (id,))
        row = cur.fetchone()

        if row is None:
            raise NoDataFound()

        return cls.load_from_row(row, cur)

    @classmethod
    def load_from_row(cls, row, cur):
        datum = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f')
        b = cls(id=row[0], datum=datum)
        b._load_positionen(cur)
        return b

    def store(self, cur):
        cur.execute("INSERT INTO rechnung (datum) VALUES (?)", (self.datum,))
        self.id = cur.lastrowid

        for pos in self.positionen:
            pos['rechnung'] = self.id
            cur.execute("INSERT INTO position (rechnung, anzahl, einheit, artikel, einzelpreis, " +
                        "produkt_ref) VALUES (?, ?, ?, ?, ?, ?)",
                        (pos['rechnung'], unicode(pos['anzahl']), pos['einheit'], pos['artikel'],
                         unicode(pos['einzelpreis']), pos['produkt_ref']))
            pos['id'] = cur.lastrowid

    def receipt(self, zahlungsart="BAR", header="", footer="", export=False):
        r = u''
        if export:
            separator = ' '
            r += u'         Rechnnung Nr. {id}:\n         {datum:%Y-%m-%d}\n'.format(id=self.id, datum=self.datum)

        else:
            separator = '\n'
            for l in header.split('\n'):
                r += u'{0:^42.42}\n'.format(l)
            r += u'\n'

            r += u'{datum:%Y-%m-%d} {id:>31}\n'.format(id=self.id, datum=self.datum)

            # Insert Line
            r += u'-' * 42 + '\n'
            r += u'ANZAHL   EINHEIT               EINZELPREIS'
            r += separator
            r += 'ARTIKEL                              PREIS\n'
            r += u'-' * 42 + '\n'

        for p in self.positionen:
            if not export:
                r += '\n'
            r += u'{anzahl_fmt:>8} {einheit:<14.14} {einzelpreis_fmt:>18}'.format(
                einzelpreis_fmt=moneyfmt(p['einzelpreis'], places=3),
                anzahl_fmt='{:.2f}'.format(p['anzahl']).replace('.', ','), **p)
            r += separator
            r += u'{artikel:<29.29}  {gesamtpreis:>11}\n'.format(
                gesamtpreis=moneyfmt(self.summe_position(p), places=3), **p)

        if not export:
            # Insert double line
            r += u'=' * 42 + '\n'

            r += u'{0:<28}  EUR {1:>7} \n\n'.format(zahlungsart, moneyfmt(self.summe))

            # Add Footer
            for l in footer.split('\n'):
                r += u'{0:^42.42}\n'.format(l)

        return r

    def print_receipt(self, cfg, zahlungsart="BAR"):
        printer = escpos_printer.Network(cfg.get('receipt', 'host'),
                                         cfg.getint('receipt', 'port'))
        printer.image(cfg.get('receipt', 'logo'))
        printer.text('\n')
        printer.text(self.receipt(header=cfg.get('receipt', 'header'),
                                  footer=cfg.get('receipt', 'footer')))
        printer.cut()


class Buchung(object):

    def __init__(self, konto, betrag, rechnung=None, kommentar=None, id=None, datum=None):
        self.id = id
        if not datum:
            self.datum = datetime.now()
        else:
            self.datum = datum
        self.konto = konto
        self.rechnung = rechnung
        self.betrag = betrag
        self.kommentar = kommentar

        if not rechnung and not kommentar:
            raise ValueError("Brauche zwingend Rechnungsreferenz oder Kommentar zu jeder Buchung.")

    @classmethod
    def load_from_id(cls, id, cur):
        cur.execute("SELECT id, datum, konto, rechnung, betrag, kommentar FROM buchung WHERE id = ?", (id,))
        row = cur.fetchone()

        if row is None:
            raise NoDataFound()

        return cls.load_from_row(row)

    @classmethod
    def load_from_row(cls, row):
        datum = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f')
        b = cls(id=row[0], datum=datum, konto=row[2], rechnung=row[3], betrag=Decimal(row[4]), kommentar=row[5])
        return b

    def _store(self, cur):
        cur.execute("INSERT INTO buchung (datum, konto, rechnung, betrag, kommentar) VALUES " +
                    "(?, ?, ?, ?, ?)", (self.datum, self.konto, self.rechnung, unicode(self.betrag), self.kommentar))
        self.id = cur.lastrowid

    @property
    def beschreibung(self):
        s = u''
        if self.rechnung:
            s += 'Rechnung: ' + unicode(self.rechnung)
            if self.kommentar:
                s += '(' + self.kommentar + ')'
        elif self.kommentar:
            s += self.kommentar
        else:
            s = u'KEINE BESCHREIBUNG'
        return s

    def to_string(self):
        formatstr = ''

        if self.betrag > 0:
            # Sollbuchung
            formatstr = u'{datum:%Y-%m-%d %H:%M}              {konto:<13}       {betrag:>7.2f} {beschreibung}'
        else:
            # Habenbuchung
            formatstr = u'{datum:%Y-%m-%d %H:%M} {konto:<13}            {betrag:>7.2f}         {beschreibung}'

        return formatstr.format(datum=self.datum, konto=self.konto, beschreibung=self.beschreibung,
                                betrag=abs(self.betrag))

    header = 'DATUM            SOLLKONTO    HABENKONTO    SOLL    HABEN   BESCHREIBUNG\n'

    def __repr__(self):
        s = u'<%s(id=%s, datum=%s, konto=%s, rechnung=%s, betrag=%s, kommentar=%s)>' % (
            self.__class__.__name__, self.id, self.datum.__repr__(), self.konto, self.rechnung,
            self.betrag.__repr__(), self.kommentar)
        return s.__repr__()  # workaround: python2.7 has trouble with __repr__ returning unicode strings - http://bugs.python.org/issue5876


class Kasse(object):

    def __init__(self, sqlite_file=':memory:'):
        self.con = sqlite3.connect(sqlite_file)
        self.cur = self.con.cursor()
        self.con.text_factory = unicode

        cur = self.cur
        cur.execute(
            "CREATE TABLE IF NOT EXISTS buchung(id INTEGER PRIMARY KEY AUTOINCREMENT, datum, konto, rechnung INT, betrag TEXT, kommentar TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS rechnung(id INTEGER PRIMARY KEY AUTOINCREMENT, datum)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS position(id INTEGER PRIMARY KEY AUTOINCREMENT, rechnung INT, anzahl TEXT, einheit TEXT, artikel TEXT, einzelpreis TEXT, produkt_ref TEXT)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS bargeld(datum, cent_1 INT, cent_2 INT, cent_5 INT, cent_10 INT, cent_20 INT, cent_50 INT, euro_1 INT, euro_2 INT, euro_5 INT, euro_10 INT, euro_20 INT, euro_50 INT, euro_100 INT, euro_200 INT, euro_500 INT, kommentar TEXT)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS kunde(id INTEGER PRIMARY KEY AUTOINCREMENT, name UNIQUE NOT NULL, pin, schuldengrenze, email, telefon, adresse, kommentar)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS kundenbuchung(id INTEGER PRIMARY KEY AUTOINCREMENT, datum, kunde, rechnung INT, betrag TEXT, kommentar TEXT)")
        cur.execute(
            "CREATE TABLE IF NOT EXISTS statistik(id INTEGER PRIMARY KEY AUTOINCREMENT, datum, gruppe, user, rechnung INT, betrag)")

        # search indexes for faster execution
        cur.execute("CREATE INDEX IF NOT EXISTS buchungDateIndex ON buchung(datum)")
        cur.execute("CREATE INDEX IF NOT EXISTS buchungRechnungIndex ON buchung(rechnung)")
        cur.execute("CREATE INDEX IF NOT EXISTS rechnungDateIndex ON rechnung(datum)")
        cur.execute("CREATE INDEX IF NOT EXISTS positionRechnungIndex ON position(rechnung)")
        cur.execute("CREATE INDEX IF NOT EXISTS bargeldDateIndex ON bargeld(datum)")
        cur.execute("CREATE INDEX IF NOT EXISTS kundenbuchungDateIndex ON kundenbuchung(datum)")
        cur.execute("CREATE INDEX IF NOT EXISTS kundenbuchungKundeIndex ON kundenbuchung(kunde)")
        cur.execute("CREATE INDEX IF NOT EXISTS statistikDateIndex ON statistik(datum)")
        cur.execute("CREATE INDEX IF NOT EXISTS statistikRechnungIndex ON statistik(rechnung)")

    @staticmethod
    def _date_query_generator(from_table=None, from_date=None, until_date=None):
        """
        returns a string for a SQL query to rechnung or buchung

        :param from_table: which table should be queried
        :param from_date: datetime start date (included)
        :param until_date: datetime end date (not included)
        :type from_date: datetime.datetime | None
        :type until_date: datetime.datetime | None
        :return: query string
        """
        # TODO comparing against these strings might make problems with py3
        # --> best import unicode_literals from future
        # --> check whole file if this import is problematic
        known_tables = ["buchung", "rechnung"]
        if from_table not in known_tables:
            raise NotImplementedError("unimplemented table {0}".format(from_table))

        query = "SELECT id FROM {0}".format(from_table)
        if from_date and until_date:
            query = query + " WHERE datum >= Datetime('{from_date}') AND datum < Datetime('{until_date}')".format(
                from_date=from_date, until_date=until_date
            )
        elif from_date:
            query = query + " WHERE datum >= Datetime('{from_date}')".format(
                from_date=from_date
            )
        elif until_date:
            query = query + " WHERE datum < Datetime('{until_date}')".format(
                until_date=until_date
            )

        return query

    @property
    def buchungen(self):
        return self.get_buchungen()

    def get_buchungen(self, from_date=None, until_date=None):
        """
        get accounting records between the given dates. If a date is ``None``, no filter will be applied.

        :param from_date: start datetime (included)
        :param until_date: end datetime (not included)
        :type from_date: datetime.datetime | None
        :type until_date: datetime.datetime | None
        """
        buchungen = []

        query = Kasse._date_query_generator(from_table="buchung", from_date=from_date, until_date=until_date)
        self.cur.execute(query)
        for row in self.cur.fetchall():
            buchungen.append(Buchung.load_from_id(row[0], self.cur))

        return buchungen

    @property
    def rechnungen(self):
        return self.get_rechnungen()

    def get_rechnungen(self, from_date=None, until_date=None):
        """
        get invoices between the given dates. If a date is ``None``, no filter will be applied.

        :param from_date: start datetime (included)
        :param until_date: end datetime (not included)
        :type from_date: datetime.datetime | None
        :type until_date: datetime.datetime | None
        """
        rechnungen = []

        query = Kasse._date_query_generator(from_table="rechnung", from_date=from_date, until_date=until_date)
        self.cur.execute(query)
        for row in self.cur.fetchall():
            rechnungen.append(Rechnung.load_from_id(row[0], self.cur))

        return rechnungen

    @property
    def kunden(self):
        kunden = []

        self.cur.execute("SELECT id FROM kunde")
        for row in self.cur.fetchall():
            kunden.append(Kunde.load_from_id(row[0], self.cur))

        return kunden

    def buchen(self, buchungen):
        saldo = Decimal()
        konten = []
        daten = set()
        for b in buchungen:
            assert isinstance(b.betrag, (Decimal, int)), "amount must be Decimal"
            assert b.betrag % Decimal("0.01") == 0, "amount must be a multiple of 0.01 - half cents are not allowed"
            saldo += b.betrag
            konten.append(b.konto)
            daten.add(b.datum)

        assert len(konten) >= 2, "Ein Buchungsfall muss mindestens zwei Konten umfassen."
        assert saldo == 0, "Ein Buchungsfall muss ein Saldo von genau Null haben."
        assert len(daten) == 1, "Alle Buchungen in einem Buchungsfall muessen das selbe Datum haben."

        for b in buchungen:
            b._store(self.cur)
        self.con.commit()

    def to_string(self, from_date=None, until_date=None, snapshot_time=None, show_receipts=True):
        # TODO saldo vorher und nachher mit ausgeben
        """
        get detailled accounting information as text

        :param from_date: see :meth:`get_buchungen`
        :param until_date: see :meth:`get_buchungen`
        :param snapshot_time: to guard against race-conditions, fetch ``datetime.datetime.now()`` at the startup of your script and pass it to :meth:`to_string` and :meth:`summary_to_string`. It will be used if `until_date` is not set.
        :type snapshot_time: datetime.datetime | None
        :param boolean show_receipts: output receipts
        """

        s = ''
        if not snapshot_time:
            snapshot_time = datetime.now()
        filter_until_date = until_date or snapshot_time
        if until_date and until_date > snapshot_time:
            # the guard against race conditions doesn't work here -- exit.
            raise Exception("The requested end date is in the future. If you called kassenbuch.py, please omit the parameter <until>. If you want to, you can also specify an exact time shortly in the past like '2015-12-31 12:49:00', if you use quotes for the shell argument.")

        if from_date:
            s += self.summary_to_string(from_date) + '\n\n\n'
        s += u'Buchungen:\n'
        s += Buchung.header
        buchungen = self.get_buchungen(from_date, filter_until_date)
        for b in buchungen:
            s += b.to_string() + '\n'

        if show_receipts:
            rechnungen = self.get_rechnungen(from_date, filter_until_date)
            s += '\n\nRechnungen:\n'
            for r in rechnungen:
                s += r.to_string() + '\n'

        konto_saldi = {}
        for b in buchungen:
            konto_saldi[b.konto] = konto_saldi.get(b.konto, Decimal(0)) + b.betrag

        s += '\nKonten:\n'
        s += 'KONTO               '
        if from_date or until_date:
            s += 'SALDOAENDERUNG\n'
        else:
            s += 'SALDO\n'

        for konto, saldo in konto_saldi.items():
            s += '{0:<16} {1:>8.2f} EUR\n'.format(konto, saldo)

        s += '\n\n\n' + self.summary_to_string(filter_until_date)

        return s

    def summary_to_string(self, date=None, snapshot_time=None):
        """
        Output account totals at given date.

        :type date: datetime.datetime | None
        :type snapshot_time: datetime.datetime | None
        :rtype: unicode
        """
        string = ""
        date = date or snapshot_time or datetime.now()

        buchungen = self.get_buchungen(from_date=None, until_date=date)

        string += "Kassenstand am {0}:\n".format(date)
        if not buchungen:
            string += "(noch keine Buchungen an diesem Datum -- 0 EUR)\n"
            return string
        else:
            string += u"(letzte darin enthaltene Buchung ist '{title}' vom {end})\n".format(title=buchungen[-1].beschreibung, end=buchungen[-1].datum)

        konto_haben = {}
        konto_soll = {}
        konto_saldi = {}
        for b in buchungen:
            if b.betrag > 0:
                konto_haben[b.konto] = konto_haben.get(b.konto, Decimal(0)) + b.betrag
            else:
                konto_soll[b.konto] = konto_soll.get(b.konto, Decimal(0)) - b.betrag

            konto_saldi[b.konto] = konto_saldi.get(b.konto, Decimal(0)) + b.betrag

        string += u'{:<16} {:>10} {:>10} {:>10}\n'.format("KONTO", "HABEN", "SOLL", "SALDO").encode('utf-8')
        for konto, saldo in konto_saldi.items():
            string += u'{0:<16} {1:>10.2f} {2:>10.2f} {3:>10.2f} EUR\n'.format(
                konto,
                konto_haben.get(konto, Decimal(0)),
                konto_soll.get(konto, Decimal(0)),
                saldo)
        return string


class Kunde(object):

    def __init__(self, name, pin='0000', schuldengrenze=None, email=None, telefon=None,
                 adresse=None, kommentar=None, id=None):
        self.id = id
        self.name = name
        self.pin = pin
        self.schuldengrenze = schuldengrenze
        self.email = email
        self.telefon = telefon
        self.adresse = adresse
        self.kommentar = kommentar

        self.buchungen = []

    @classmethod
    def load_from_id(cls, id, cur):
        cur.execute("SELECT id, name, pin, schuldengrenze, email, telefon, adresse, kommentar " +
                    "FROM kunde WHERE id = ?", (id,))
        row = cur.fetchone()

        if row is None:
            raise NoDataFound()

        return cls.load_from_row(row, cur)

    @classmethod
    def load_from_name(cls, name, cur):
        cur.execute("SELECT id, name, pin, schuldengrenze, email, telefon, adresse, kommentar " +
                    "FROM kunde WHERE name = ?", (name,))
        row = cur.fetchone()

        if row is None:
            raise NoDataFound()

        return cls.load_from_row(row, cur)

    @classmethod
    def load_from_row(cls, row, cur):
        b = cls(id=row[0], name=row[1], pin=row[2], schuldengrenze=Decimal(row[3]), email=row[4],
                telefon=row[5], adresse=row[6], kommentar=row[7])

        b._load_buchungen(cur)

        return b

    def store(self, cur):
        if self.id is None:
            cur.execute("INSERT INTO kunde (name, pin, schuldengrenze, email, telefon, adresse, " +
                        "kommentar) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (self.name, self.pin, unicode(self.schuldengrenze), self.email,
                         self.telefon, self.adresse, self.kommentar))
            self.id = cur.lastrowid
        else:
            cur.execute("UPDATE kunde SET name=?, pin=?, schuldengrenze=?, email=?, telefon=?, " +
                        "adresse=?, kommentar=? WHERE id=?",
                        (self.name, self.pin, unicode(self.schuldengrenze), self.email,
                         self.telefon, self.adresse, self.kommentar, self.id))

        for b in self.buchungen:
            b.store(cur)

        return self.id

    def _load_buchungen(self, cur):
        """loads all transactions of a client (by id) and discards current transactions

        This function loads all transactions of a client. The id of the client is specified in
        :py:attr:`FabLabKasse.kassenbuch.Kunde.id`. It discards the content of
        :py:attr:`FabLabKasse.kassenbuch.Kunde.buchungen`.
        :param cur: sqlite cursor to database
        :type cur: sqlite3.Cursor
        """
        self.buchungen = []

        if self.id is None:
            return

        cur.execute("SELECT id, datum, kunde, rechnung, betrag, kommentar FROM kundenbuchung " +
                    "WHERE kunde=? ORDER BY id ASC", (self.id,))

        for row in cur:
            self.buchungen.append(Kundenbuchung.load_from_row(row))

    def add_buchung(self, betrag, rechnung=None, kommentar=None, datum=None):
        self.buchungen.append(Kundenbuchung(self.id, betrag, rechnung=rechnung,
                                            kommentar=kommentar, datum=datum))

    @property
    def summe(self):
        summe = Decimal(0)

        for b in self.buchungen:
            summe += b.betrag

        return summe

    def to_string(self, short=False):
        summary = u"""Kunde: {name} (#{id}):
    Schuldengrenze: {schuldengrenze:.2f} EUR
    Mail:           {email}
    Telefon:        {telefon}
    Adresse:        {adresse}
    Kommentar:      {kommentar}
    PIN:            {pin}""".format(
            id=self.id, name=self.name, schuldengrenze=self.schuldengrenze,
            email=self.email, telefon=self.telefon, adresse=self.adresse,
            kommentar=self.kommentar, pin=self.pin)

        if short:
            return summary
        else:
            details = Kundenbuchung.header
            details += '\n'.join((b.to_string() for b in self.buchungen))
            return summary + '\n\n' + details

    def __repr__(self):
        s = u'<%s(id=%s, name=%s, pin=%s' % (self.__class__.__name__, self.id, unicode(self.name), self.pin)
        if self.schuldengrenze is not None:
            s += u', schuldengrenze=%s' % self.schuldengrenze.__repr__()
        if self.email is not None:
            s += u', email=%s' % self.email
        if self.telefon is not None:
            s += u', telefon=%s' % self.telefon
        if self.adresse is not None:
            s += u', adresse=%s' % self.adresse
        if self.kommentar is not None:
            s += u', kommentar=%s' % self.kommentar
        s += ')>'
        return s.__repr__()  # workaround: python2.7 has trouble with __repr__ returning unicode strings - http://bugs.python.org/issue5876


class Kundenbuchung(object):

    def __init__(self, kunde, betrag, rechnung=None, kommentar=None, id=None, datum=None):
        self.id = id
        if not datum:
            self.datum = datetime.now()
        else:
            self.datum = datum
        self.kunde = kunde
        self.rechnung = rechnung
        self.betrag = betrag
        self.kommentar = kommentar

        if not rechnung and not kommentar:
            raise ValueError("Brauche zwingend Rechnungsreferenz oder Kommentar zu jeder Buchung.")

    @classmethod
    def load_from_id(cls, id, cur):
        cur.execute("SELECT id, datum, kunde, rechnung, betrag, kommentar FROM kundenbuchung " +
                    "WHERE id = ?", (id,))
        row = cur.fetchone()

        if row is None:
            raise NoDataFound()

        return cls.load_from_row(row)

    @classmethod
    def load_from_row(cls, row):
        datum = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S.%f')
        b = cls(id=row[0], datum=datum, kunde=row[2], rechnung=row[3], betrag=Decimal(row[4]),
                kommentar=row[5])
        return b

    def store(self, cur):
        if self.id is None:
            cur.execute("INSERT INTO kundenbuchung (datum, kunde, rechnung, betrag, kommentar) " +
                        "VALUES (?, ?, ?, ?, ?)", (self.datum, self.kunde, self.rechnung,
                                                   unicode(self.betrag), self.kommentar))
            self.id = cur.lastrowid
        else:
            cur.execute("UPDATE kundenbuchung SET datum=?, kunde=?, rechnung=?, betrag=?, " +
                        "kommentar=? WHERE id=?", (self.datum, self.kunde, self.rechnung,
                                                   unicode(self.betrag), self.kommentar, self.id))

        return self.id

    @property
    def beschreibung(self):
        s = u''
        if self.rechnung:
            s += 'Rechnung: ' + unicode(self.rechnung)
            if self.kommentar:
                s += '(' + self.kommentar + ')'
        elif self.kommentar:
            s += self.kommentar
        else:
            s = u'KEINE BESCHREIBUNG'
        return s

    def to_string(self):
        formatstr = ''

        formatstr = u'{datum:%Y-%m-%d %H:%M}    {betrag:>8.2f}    {beschreibung}'

        return formatstr.format(datum=self.datum, beschreibung=self.beschreibung,
                                betrag=self.betrag)

    header = 'DATUM              BETRAG       BESCHREIBUNG\n'

    def __repr__(self):
        s = u'<%s(id=%s, datum=%s, kunde=%s, rechnung=%s, betrag=%s, kommentar=%s)>' % (
            self.__class__.__name__, self.id, self.datum.__repr__(), self.kunde, self.rechnung,
            self.betrag.__repr__(), self.kommentar)
        return s.__repr__()  # workaround: python2.7 has trouble with __repr__ returning unicode strings - http://bugs.python.org/issue5876


class UnicodeWriter(object):
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([unicode(s).encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)


def parse_date(value):
    """
    parse date from string or None

    :type value: basestr | None
    :rtype: datetime.datetime | None
    """
    if isinstance(value, basestring) and value != '':
        value = value.lower().strip()
        if value in ['now', 'today']:
            return datetime.today()
        elif value == 'yesterday':
            return datetime.today() - timedelta(1)
        else:
            return dateutil.parser.parse(value)
    if not value:
        return None
    else:
        raise ValueError('cannot parse date value')


def argparse_parse_date(date):
    """
    a wrapper for parings dates for argparse

    :type date: see :meth:`parse_date`
    :rtype: see :meth:`parse_date`
    """
    try:
        return parse_date(date)
    except ValueError as e:
        raise argparse.ArgumentTypeError(e.message)


def date_argcomplete(prefix, **kwargs):
    """tab completion for date"""
    years = range(2010, datetime.today().year + 1)
    months = range(1, 13)
    days = range(1, 32)
    lst = ["{y}-{m}-{d}".format(y=y, m=m, d=d) for y in years
           for m in months for d in days]
    lst += ['yesterday', 'today', 'now']
    return [d for d in lst if d.startswith(prefix)]


def argparse_parse_currency(amount):
    """parse currencies for argparse"""
    try:
        amount = amount.replace(',', '.').replace('€', '')
        amount = amount.replace('EUR', '').strip()
        return Decimal(amount)
    except InvalidOperation as e:
        raise argparse.ArgumentTypeError(e.message)


def argparse_parse_client(value):
    """get a client out of the database by name or id"""
    cfg = scriptHelper.getConfig()
    k = Kasse(cfg.get('general', 'db_file'))
    try:
        return Kunde.load_from_id(int(value), k.cur)
    except (ValueError, NoDataFound):
        pass  # ok, maybe it's not an ID but a name:
    try:
        return Kunde.load_from_name(value, k.cur)
    except NoDataFound:
        raise argparse.ArgumentTypeError(
            u"Konnte keinen Kunde unter '{0}' finden.".format(value))


def client_argcomplete(prefix, **kwargs):
    """tab completion for clients"""
    cfg = scriptHelper.getConfig()
    k = Kasse(cfg.get('general', 'db_file'))
    lst = [c.name for c in k.kunden if c.name.startswith(prefix)]
    lst += [str(c.id) for c in k.kunden if str(c.id).startswith(prefix)]
    return lst


def argparse_parse_receipt(rid):
    """get the receipt from its id"""
    cfg = scriptHelper.getConfig()
    k = Kasse(cfg.get('general', 'db_file'))
    try:
        return Rechnung.load_from_id(int(rid), k.cur)
    except (ValueError, NoDataFound):
        raise argparse.ArgumentTypeError(
            u"Konnte keine Rechnung mit der ID '{0}' finden.".format(rid))


def receipt_argcomplete(prefix, **kwargs):
    """tab completion for receipts"""
    cfg = scriptHelper.getConfig()
    k = Kasse(cfg.get('general', 'db_file'))
    return [str(r.id) for r in k.rechnungen if str(r.id).startswith(prefix)]


def parse_args(argv=sys.argv[1:]):
    """
    Parse arguments
    :return: the parse arguments as object (see argparse doc)
    :rtype: object
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(title='actions',
                                       dest='action')

    DATE_HELP = "datetime e.g. ISO formatted, (2016-12-31 [13:37:42])"
    # show
    parser_show = subparsers.add_parser(
        'show',
        help='show receipts',
    )
    parser_show.add_argument(
        '--hide-receipts',
        action='store_true',
        dest='hide_receipts',
        default=False,
        help="Don't show receipts in summary output, just the account balances"
    )
    parser_show.add_argument(
        '--from',
        action='store',
        type=argparse_parse_date,
        metavar='date',
        dest='from_date',
        help=DATE_HELP,
    ).completer = date_argcomplete
    parser_show.add_argument(
        '--until',
        action='store',
        type=argparse_parse_date,
        metavar='date',
        dest='until_date',
        help=DATE_HELP,
    ).completer = date_argcomplete
    # export
    parser_export = subparsers.add_parser(
        'export',
        help='export books or invoices',
    )
    parser_export.add_argument(
        'what',
        action='store',
        choices=['book', 'invoices'],
        help="what do you want to export (book|invoices)",
    )
    parser_export.add_argument(
        'outfile',
        action='store',
        type=argparse.FileType('wb'),
        default='-',
        help="the output file, - for stdout",
    )
    parser_export.add_argument(
        '--from',
        action='store',
        type=argparse_parse_date,
        metavar='date',
        dest='from_date',
        help=DATE_HELP,
    ).completer = date_argcomplete
    parser_export.add_argument(
        '--until',
        action='store',
        type=argparse_parse_date,
        metavar='date',
        dest='until_date',
        help=DATE_HELP,
    ).completer = date_argcomplete
    parser_export.add_argument(
        '--format',
        action='store',
        dest='format',
        metavar='fileformat',
        default='csv',
        choices=['csv'],
        help="format for the output file (default csv)",
    )
    # summary
    parser_summary = subparsers.add_parser(
        'summary',
        help='show the summary',
    )
    parser_summary.add_argument(
        '--until',
        action='store',
        type=argparse_parse_date,
        metavar='date',
        dest='until_date',
        help=DATE_HELP,
    ).completer = date_argcomplete
    # transfer
    parser_transfer = subparsers.add_parser(
        'transfer',
        help="transfer money from one resource to another",
    )
    parser_transfer.add_argument(
        'source',
        action='store',
        type=str,  # TODO What is a valid source? -> provide tab completion
        help="the source",
    )
    parser_transfer.add_argument(
        'destination',
        action='store',
        type=str,  # TODO What is a valid dest? -> provide tab completion
        help="the destination",
    )
    parser_transfer.add_argument(
        'amount',
        action='store',
        type=argparse_parse_currency,
        help="the amount",
    )
    parser_transfer.add_argument(
        'comment',
        action='store',
        type=str,
        nargs='+',
        help="a comment",
    )
    # receipt
    parser_receipt = subparsers.add_parser(
        'receipt',
        help="View and print receipts (Rechnungen)",
    )
    parser_receipt.add_argument(
        '--print',
        action='store_true',
        dest='print_receipt',
        default=False,
        help="print it with a connected printer",
    )
    parser_receipt.add_argument(
        '--export',
        action='store_true',
        dest='export',
        default=False,
        help="export?",
    )
    parser_receipt.add_argument(
        'receipt',
        metavar='id',
        action='store',
        type=argparse_parse_receipt,
        help="the receipt ID (Rechnungsnummer)",
    ).completer = receipt_argcomplete
    # client
    parser_client = subparsers.add_parser(
        'client',
        help="Add, show, edit, list clients",
    )
    client_subparsers = parser_client.add_subparsers(title='actions',
                                                     dest='client_action')
    # client create
    parser_client_create = client_subparsers.add_parser(
        'create',
        help="Create/add a new client in interactive mode",
    )
    # client list
    parser_client_list = client_subparsers.add_parser(
        'list',
        help="List all existing clients",
    )
    parser_client_list.add_argument(
        '--maxbalance', '-m', metavar='MAX', type=Decimal,
        help='Restricts output to clients with a balance of MAX or below.')
    parser_client_list.add_argument(
        '--inactive', '-i', metavar='N', type=int,
        help='Restricts output to clients with no activity for atleast N days.')
    parser_client_list.add_argument(
        '--remove-zeros', '-z', action='store_true', default=False,
        help='Removes all clients with exactly zero balance.')
    # client edit
    parser_client_edit = client_subparsers.add_parser(
        'edit',
        help="Edit an existing client",
    )
    parser_client_edit.add_argument(
        'client',
        action='store',
        type=argparse_parse_client,
        help="The name or id of the client",
    ).completer = client_argcomplete
    # client show
    parser_client_show = client_subparsers.add_parser(
        'show',
        help="Shows details for an existing client " +
        "(--transactions for transactions)"
    )
    parser_client_show.add_argument(
        'client',
        action='store',
        type=argparse_parse_client,
        help="The name or id of the client",
    ).completer = client_argcomplete
    parser_client_show.add_argument(
        '--transactions',
        action='store_true',
        dest='transactions',
        default=False,
        help="Show transactions of the client",
    )  # replaces old 'client summary'
    # client charge
    parser_client_charge = client_subparsers.add_parser(
        'charge',
        help="Charge the credit of an client (remove money from account)",
    )
    parser_client_charge.add_argument(
        'client',
        action='store',
        type=argparse_parse_client,
        help="The name or id of the client",
    ).completer = client_argcomplete
    parser_client_charge.add_argument(
        'amount',
        action='store',
        type=argparse_parse_currency,
        help="The amount to charge in Euro",
    )
    parser_client_charge.add_argument(
        'comment',
        action='store',
        type=str,
        nargs='+',
        help="A comment for this charging",
    )
    # client payup
    parser_client_payup = client_subparsers.add_parser(
        'payup',
        help="Pay up the credit of an client (add money to account)",
    )
    parser_client_payup.add_argument(
        'client',
        action='store',
        type=argparse_parse_client,
        help="The name or id of the client",
    ).completer = client_argcomplete
    parser_client_payup.add_argument(
        'amount',
        action='store',
        type=argparse_parse_currency,
        help="The amount to payup in Euro",
    )
    parser_client_payup.add_argument(
        'comment',
        action='store',
        type=str,
        nargs='+',
        help="A comment for this payup",
    )

    if 'argcomplete' in globals():
        argcomplete.autocomplete(parser)

    args = parser.parse_args(argv)

    return args


def main():
    """parse args, run the desired action"""
    args = parse_args()

    # go to script dir (configs are relative path names)
    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    cfg = scriptHelper.getConfig()
    k = Kasse(cfg.get('general', 'db_file'))

    # r = Rechnung()
    # r.add_position(u"Plexiglas 5mm gruen", Decimal("0.015"), anzahl=100, einheit='qcm', produkt_ref='1000')
    # r.add_position(u"Papier A4", Decimal("0.1"), anzahl=1, einheit='Seiten', produkt_ref='1001'))
    # r.add_position(u"Laserzeit (Plastik)", Decimal("0.1"), anzahl=30.2, einheit='min', produkt_ref='1002'))
    # r.store(k.cur)
    # b1 = Buchung(u"Barkasse", Decimal(4.57), rechnung=r.id)
    # b2 = Buchung(u"Besucher", Decimal(-2.57), rechnung=r.id, datum=b1.datum)
    # b3 = Buchung(u"Gutschein_10", Decimal(-2.00), rechnung=r.id, datum=b1.datum)
    # k.buchen([b1,b2,b3])

    # set current date to guard against race conditions
    startup_time = datetime.now()
    # TODO does not help if until argument is given that is greater than the current date
    # (and doesn't work at timezone jumps etc.)

    if 'comment' in args:
        args.comment = ' '.join(args.comment)

    if args.action == 'show':
        print(k.to_string(from_date=args.from_date,
                          until_date=args.until_date,
                          snapshot_time=startup_time,
                          show_receipts=not args.hide_receipts).
              encode('utf-8'))
    elif args.action == 'export':
        if args.what == 'book':
            # TODO Use csv.DictWriter
            writer = UnicodeWriter(args.outfile)
            # Header
            writer.writerow(['DATUM',
                             'KONTO',
                             'BETRAG',
                             'RECH.NR.',
                             'KOMMENTAR'])
            # Content
            for b in k.buchungen:
                writer.writerow([unicode(b.datum),
                                 unicode(b.konto),
                                 u'{0:.2f}'.format(b.betrag),
                                 unicode(b.rechnung),
                                 unicode(b.kommentar)])
        elif args.what == 'invoices':
            # TODO Use csv.DictWriter
            writer = UnicodeWriter(args.outfile)
            # Header
            writer.writerow(['RECH.NR.',
                             'DATUM',
                             'ARTIKEL',
                             'ANZAHL',
                             'EINHEIT',
                             'EINZELPREIS',
                             'SUMME',
                             'PRODUKT NR.'])
            # Content
            for r in k.rechnungen:
                for p in r.positionen:
                    writer.writerow(
                        [
                            str(r.id),
                            str(r.datum),
                            p['artikel'],
                            str(p['anzahl']),
                            p['einheit'],
                            '{0:.2f}'.format(p['einzelpreis']),
                            '{0:.2f}'.format(r.summe_position(p)),
                            p['produkt_ref']
                        ])
                writer.writerow([])
    elif args.action == 'summary':
        print(k.summary_to_string(date=args.until_date,
                                  snapshot_time=startup_time).
              encode('utf-8'))
    elif args.action == 'transfer':

        b1 = Buchung(args.source,
                     -args.amount,
                     kommentar=args.comment)
        b2 = Buchung(args.destination,
                     args.amount,
                     kommentar=args.comment,
                     datum=b1.datum)
        k.buchen([b1, b2])
        print("[i] done")

    elif args.action == 'receipt':
        print(args.receipt.receipt(header=cfg.get('receipt', 'header'),
                                   footer=cfg.get('receipt', 'footer'),
                                   export=args.export))
        if args.print_receipt:
            args.receipt.print_receipt(cfg)

    elif args.action == 'client':

        if "client" in args:
            kunde = args.client
        elif args.client_action == 'create':
            kunde = Kunde('')  # will be filled in later

        if args.client_action == 'create' or args.client_action == 'edit':
            edit = args.client_action == 'edit'  # to shorten expressions

            def fetch_input(explanation, default_input=None,
                            allowed_regexp=None, extra_checks=None):
                """
                Fetches an input from stdin or uses the default
                if no input was given and checks it
                :param explanation: the explanation text of this input
                :param default_input: the default value for this input or None
                :param allowed_regexp: a regexp to check if input is allowed
                :param extra_checks: a function or lambda expression that
                        requires an input as str and returns a bool
                :type default_input: basestr | None
                :type explanation: basestr
                :type allowed_regexp: basestr | None
                :type extra_checks: function | None
                """
                default_str = u" [{0}]".format(unicode(default_input)) if default_input is not None else ""
                allowed_regexp = allowed_regexp if allowed_regexp is not None else ur".*"
                extra_checks = extra_checks if extra_checks else lambda x: True

                while True:
                    input_str = raw_input(u"{e}{d}: ".format(
                        e=explanation, d=default_str)).decode(sys.stdin.encoding)

                    if input_str == '' and default_input is not None:
                        input_str = unicode(default_input)

                    if not re.match(allowed_regexp, input_str):
                        print(u'[!] Eingabe ungültig!', file=sys.stderr)
                        continue  # retry
                    elif extra_checks(input_str):
                        return input_str  # success
                    else:
                        continue  # retry

            # Name
            def check_name_unique(name):
                """
                Check function for fetch_input
                checks if the given client name is unique (or unchanged)
                :param name: the name to check if it is unique
                :type name: basestr
                :rtype : bool
                """
                if edit and kunde and name == kunde.name:
                    return True  # kunde keeps old name -> that's allowed
                if k.cur.execute('SELECT id FROM kunde WHERE name=?', (name,)).fetchone() is not None:
                    print("[!] Name ist bereits in Verwendung.", file=sys.stderr)
                    return False
                return True

            default = kunde.name if edit else None
            kunde.name = fetch_input(
                explanation=u'Name (ohne Leer- und Sonderzeichen!)',
                default_input=default,
                allowed_regexp=ur'^[a-zA-Z0-9\/_-]{1,}$',
                extra_checks=check_name_unique
            )

            # PIN
            print("[i] zufällige PIN-Vorschläge: {0:04} {1:04} {2:04}".format(
                random.randint(1, 9999),
                random.randint(1, 9999),
                random.randint(1, 9999)))

            default = kunde.pin if edit else None
            kunde.pin = fetch_input(
                explanation=u'PIN (4 Ziffern, 0000: deaktiviert)',
                default_input=default,
                allowed_regexp=ur'^[0-9]{4}$'
            )

            # Schuldengrenze
            def check_number_decimal(n):
                """
                Check function for fetch_input; checks if n is a Decimal
                :param n: the number to check
                :type n: unicode, str
                :rtype : bool
                """
                try:
                    Decimal(n)
                    return True
                except InvalidOperation:
                    print(u"[!] Formatierung ungültig.\n \
                                Korrekt wäre z.B. '100.23' oder '-1'.",
                          file=sys.stderr)
                    return False

            def check_number_greater_zero_or_minus_one(n):
                """
                Check function for fetch_input; checks if n >= 0 or == -1
                :param n: the number to check
                :type n: unicode, str
                :rtype : bool
                """
                if Decimal(n) >= Decimal('0') or Decimal(n) == Decimal('-1'):
                    return True
                else:
                    print("[!] Schuldengrenze muss >= 0 oder = -1 sein",
                          file=sys.stderr)
                    return False

            default = kunde.schuldengrenze if edit else None
            kunde.schuldengrenze = Decimal(
                fetch_input(
                    explanation=u'Schuldengrenze (>=0: beschraenkt oder -1: unbeschraenkt)',
                    default_input=default,
                    allowed_regexp=ur'^[0-9-+,.]+$',
                    extra_checks=lambda n: check_number_decimal(n) and check_number_greater_zero_or_minus_one(n))
            )

            # Email
            default = kunde.email if edit else None
            kunde.email = fetch_input(
                explanation=u'Email',
                default_input=default,
                allowed_regexp=ur'^[A-Za-z0-9\.\+_-]+@[A-Za-z0-9\._-]+\.[a-zA-Z]*$'
            )

            # Telefon
            default = kunde.telefon if edit else None
            kunde.telefon = fetch_input(
                explanation=u'Telefonnummer (optional; Ziffern, Leer, Raute, ... )',
                default_input=default,
                allowed_regexp=ur'^[0-9 \+\-#\*\(\)/]*$'
            )

            # Adresse
            default = kunde.adresse if edit else None
            kunde.adresse = fetch_input(
                explanation=u'Adresse (optional; nur eine Zeile)',
                default_input=default
            )

            # Kommentar
            default = kunde.kommentar if edit else None
            kunde.kommentar = fetch_input(
                explanation=u'Kommentar (optional; nur eine Zeile)',
                default_input=default
            )

            try:
                kunde.store(k.cur)
            except sqlite3.IntegrityError:
                print("[!] Name ist bereits in Verwendung.", file=sys.stderr)
                sys.exit(2)

            k.con.commit()
            print("[i] Gespeichert. Kundennummer lautet: {0}".format(kunde.id))

        elif args.client_action == 'show':

            print(kunde.to_string(short=not args.transactions))

            print("Kontostand: " + moneyfmt(kunde.summe) + ' EUR')

        elif args.client_action == 'charge':

            kunde.add_buchung(-args.amount, args.comment)
            kunde.store(k.cur)

            k.con.commit()

        elif args.client_action == 'payup':

            kunde.add_buchung(args.amount, args.comment)
            kunde.store(k.cur)

            k.con.commit()

        elif args.client_action == 'list':

            print("""
KdNr|                     Name|  Kontostand|  Grenze| Letzte Zahlung | Letzte Buchung |
----+-------------------------+------------+--------+----------------+----------------+""")

            for k in k.kunden:
                last_payment = sorted(
                    [b.datum for b in k.buchungen if b.betrag > 0], reverse=True
                )[:1]
                last_charge = sorted(
                    [b.datum for b in k.buchungen if b.betrag < 0], reverse=True
                )[:1]
                
                # Using a skip flag, to allow overlapping filtering, where any filter will allow
                # an entry to pass
                skip = True
                if args.inactive is not None and last_charge:
                    # skip sufficiently active clients
                    if (datetime.now()-last_charge[0]).days >= args.inactive:
                        skip = False
                if args.maxbalance is not None and k.summe < args.maxbalance:
                    # skip clients with sufficient balance
                    skip = False
                if args.maxbalance is None and args.inactive is None:
                    # Let everything pass if not filters were given
                    skip = False
                if args.remove_zeros and abs(k.summe) < 0.005:
                    skip = True                
                if skip: continue

                if not last_payment:
                    last_payment = "n/a"
                else:
                    last_payment = last_payment[0].strftime('%Y-%m-%d')
                if not last_charge:
                    last_charge = "n/a"
                else:
                    last_charge = last_charge[0].strftime('%Y-%m-%d')

                print(u'{0:>4}|{1:>25}|{2:>8} EUR|{3:>8}| {4:>14} | {5:>14}'.format(
                    k.id, k.name, moneyfmt(k.summe), moneyfmt(k.schuldengrenze),
                    last_payment, last_charge))

    else:
        print("[!] This should not have happend. Option not implemented.",
              file=sys.stderr)
        print(args, file=sys.stderr)


if __name__ == '__main__':
    main()
