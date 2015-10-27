#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2014  Julian Hammer <julian.hammer@fablab.fau.de>
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

"""Kassenbuch Backend mit doppelter Buchführung.

Usage:
  kassenbuch.py show [<from> [<until>]]
  kassenbuch.py export (book|invoices) <outfile> [<from> [<until>]] [--format=<fileformat>]
  kassenbuch.py summary [<from> [<until>]]
  kassenbuch.py transfer <source> <destination> <amount> <comment>...
  kassenbuch.py client (create|list)
  kassenbuch.py client (edit|show|summary) <name>
  kassenbuch.py client (charge|payup) <name> <amount> <comment>...
  kassenbuch.py receipt [--print] [--export] <id>
  kassenbuch.py (-h | --help)
  kassenbuch.py --version

Options:
  -h --help     Show this screen.
  --version     Show version.
  --format=<fileformat>  Export Dateityp [default: csv].

"""

import sqlite3
from datetime import datetime
from decimal import Decimal
import dateutil.parser
from docopt import docopt
import csv
import cStringIO
import codecs
import re
import sys
import random
import scriptHelper

import doctest

import libs.escpos.printer as escpos_printer


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
        s = u'Rechnungsnr.: {}\nDatum: {:%Y-%m-%d %H:%M}\n'.format(self.id, self.datum)

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
                r += u'{:^42.42}\n'.format(l)
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

            r += u'{:<28}  EUR {:>7} \n\n'.format(zahlungsart, moneyfmt(self.summe))

            # Add Footer
            for l in footer.split('\n'):
                r += u'{:^42.42}\n'.format(l)

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

    @property
    def buchungen(self):
        return self.get_buchungen()

    def get_buchungen(self, von=None, bis=None):
        buchungen = []

        self.cur.execute("SELECT id FROM buchung")
        for row in self.cur.fetchall():
            buchungen.append(Buchung.load_from_id(row[0], self.cur))

        # TODO move filters to SQL query
        if von:
            if isinstance(von, basestring):
                von = dateutil.parser.parse(von)
                print(von)
            buchungen = filter(lambda b: b.datum >= von, buchungen)
        if bis:
            if isinstance(bis, basestring):
                bis = dateutil.parser.parse(bis)
            buchungen = filter(lambda b: b.datum < bis, buchungen)

        return buchungen

    @property
    def rechnungen(self):
        return self.get_rechnungen()

    def get_rechnungen(self, von=None, bis=None):
        rechnungen = []

        self.cur.execute("SELECT id FROM rechnung")
        for row in self.cur.fetchall():
            rechnungen.append(Rechnung.load_from_id(row[0], self.cur))

        if von:
            if isinstance(von, basestring):
                von = dateutil.parser.parse(von)
            rechnungen = filter(lambda b: b.datum >= von, rechnungen)
        if bis:
            if isinstance(bis, basestring):
                bis = dateutil.parser.parse(bis)
            rechnungen = filter(lambda b: b.datum < bis, rechnungen)

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

    def to_string(self, von=None, bis=None):
        # TODO saldo vorher und nachher mit ausgeben
        s = u'Buchungen:\n'
        s += Buchung.header
        buchungen = self.get_buchungen(von, bis)
        for b in buchungen:
            s += b.to_string() + '\n'

        rechnungen = self.get_rechnungen(von, bis)
        s += '\n\nRechnungen:\n'
        for r in rechnungen:
            s += r.to_string() + '\n'

        konto_saldi = {}
        for b in buchungen:
            konto_saldi[b.konto] = konto_saldi.get(b.konto, Decimal(0)) + b.betrag

        s += '\nKonten:\n'
        s += 'KONTO               '
        if von or bis:
            s += 'SALDOAENDERUNG\n'
        else:
            s += 'SALDO\n'

        for konto, saldo in konto_saldi.items():
            s += '{:<16} {:>8.2f} EUR\n'.format(konto, saldo)

        return s


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
        if self.id is None:
            self.buchungen = []
            return

        cur.execute("SELECT id, datum, kunde, rechnung, betrag, kommentar FROM kundenbuchung " +
                    "WHERE kunde=? ORDER BY id ASC", (self.id,))

        self.buchunge = []
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
        summary = (u'Kunde {name} ({id}):\n    Schuldengrenze: {schuldengrenze:.2f} EUR\n    ' +
                   u'Mail: {email}\n    Telefon: {telefon}\n    Adresse: {adresse}\n    ' +
                   u'Kommentar: {kommentar}\n    PIN: {pin}').format(
            id=self.id, name=self.name, schuldengrenze=self.schuldengrenze,
            email=self.email, telefon=self.telefon, adresse=self.adresse,
            kommentar=self.kommentar, pin=self.pin)

        details = Kundenbuchung.header
        details += '\n'.join(map(lambda b: b.to_string(), self.buchungen))

        if short:
            return summary
        else:
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


class Kundenbuchung(Buchung):

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


if __name__ == '__main__':
    arguments = docopt(__doc__, version='Kassenbuch 1.0')

    # Decode all arguments with proper utf-8 decoding:
    arguments.update(
        dict(map(lambda t: (t[0], t[1].decode('utf-8')),
                 filter(lambda t: isinstance(t[1], str), arguments.items()))))

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

    if arguments['show'] and not arguments['client']:
        print(k.to_string(von=arguments['<from>'], bis=arguments['<until>']).encode('utf-8'))

    elif arguments['export'] and arguments['book']:
        assert arguments['--format'] == 'csv', "Format not supported."

        with open(arguments['<outfile>'], 'wb') as csvfile:
            writer = UnicodeWriter(csvfile)
            # Header
            writer.writerow(['DATUM', 'KONTO', 'BETRAG', 'RECH.NR.', 'KOMMENTAR'])
            # Content
            for b in k.buchungen:
                writer.writerow([unicode(b.datum), unicode(b.konto), u'{:.2f}'.format(b.betrag),
                                 unicode(b.rechnung), unicode(b.kommentar)])

    elif arguments['export'] and arguments['invoices']:
        assert arguments['--format'] == 'csv', "Format not supported."

        with open(arguments['<outfile>'], 'wb') as csvfile:
            writer = UnicodeWriter(csvfile)
            # Header
            writer.writerow(
                ['RECH.NR.', 'DATUM', 'ARTIKEL', 'ANZAHL', 'EINHEIT', 'EINZELPREIS', 'SUMME', 'PRODUKT NR.'])
            # Content
            for r in k.rechnungen:
                for p in r.positionen:
                    writer.writerow([str(r.id), str(r.datum), p['artikel'], str(p['anzahl']),
                                     p['einheit'], '{:.2f}'.format(p['einzelpreis']),
                                     '{:.2f}'.format(r.summe_position(p)),
                                     p['produkt_ref']])
                writer.writerow([])

    elif arguments['summary'] and not arguments['client']:
        buchungen = k.get_buchungen(arguments['<from>'], arguments['<until>'])

        if not buchungen:
            print("Keine Buchungen gefunden")
            print(arguments['<from>'] + " " + arguments['<until>'])
            exit()

        print("Kassenbuch Kurzfassung:")
        print("Von " + buchungen[0].datum.strftime('%Y-%m-%d') + " bis " + buchungen[-1].datum.strftime('%Y-%m-%d'))

        konto_haben = {}
        konto_soll = {}
        konto_saldi = {}
        for b in buchungen:
            if b.betrag > 0:
                konto_haben[b.konto] = konto_haben.get(b.konto, Decimal(0)) + b.betrag
            else:
                konto_soll[b.konto] = konto_soll.get(b.konto, Decimal(0)) - b.betrag

            konto_saldi[b.konto] = konto_saldi.get(b.konto, Decimal(0)) + b.betrag

        print(u'{:<16} {:>8} {:>8} {:>8}'.format("KONTO", "HABEN", "SOLL", "SALDO").encode('utf-8'))
        for konto, saldo in konto_saldi.items():
            print(u'{:<16} {:>8.2f} {:>8.2f} {:>8.2f} EUR'.format(
                konto,
                konto_haben.get(konto, Decimal(0)),
                konto_soll.get(konto, Decimal(0)),
                saldo).encode('utf-8'))

    elif arguments['transfer']:
        try:
            betrag = Decimal(arguments['<amount>'])
        except ValueError:
            print("Amount has to be of a Decimal parsable string.")
            exit(1)

        comment = unicode(' '.join(arguments['<comment>']).decode('utf-8'))

        b1 = Buchung(unicode(arguments['<source>']), -betrag, kommentar=comment)
        b2 = Buchung(unicode(arguments['<destination>']), betrag, kommentar=comment, datum=b1.datum)
        k.buchen([b1, b2])

        print("done")

    elif arguments['client'] and arguments['create']:
        # Name
        while True:
            name = raw_input('Name (ohne Leer- und Sonderzeichen!): ')

            if k.cur.execute('SELECT id FROM kunde WHERE name=?', (name,)).fetchone() is not None:
                print("Name ist bereits in Verwendung.")
                continue

            kunde = Kunde(name)
            break

        # PIN
        while True:
            print("zufällige PIN-Vorschläge: {:04} {:04} {:04}".format(random.randint(1, 9999), random.randint(1, 9999),
                                                                       random.randint(1, 9999)))
            pin = raw_input(u'PIN (vier Ziffern, 0000 bedeutet deaktiviert): ')

            if re.match(r'[0-9]{4}', pin):
                kunde.pin = pin
                break
            else:
                print("Nur vier Ziffern sind erlaubt.")

        # Schuldengrenze
        while True:
            schuldengrenze = raw_input('Schuldengrenze (>=0 beschraenkt, -1 unbeschraenkt): ')

            try:
                schuldengrenze = Decimal(schuldengrenze)
            except:
                print("Formatierung ungueltig. Korrekt waere z.B. '100.23' oder '-1'.")
                continue

            if schuldengrenze >= Decimal('0') or schuldengrenze == Decimal('-1'):
                kunde.schuldengrenze = schuldengrenze
                break

        # Email
        while True:
            email = raw_input('Email: ')

            if re.match(r'^[A-Za-z0-9\.\+_-]+@[A-Za-z0-9\._-]+\.[a-zA-Z]*$', email):
                kunde.email = email
                break
            else:
                print("Ungueltige Mailadresse.")

        # Telefon
        while True:
            telefon = raw_input('Telefonnummer: ')

            if re.match(r'[0-9 \+\-#\*\(\)/]+', telefon):
                kunde.telefon = telefon
                break
            else:
                print("Nur Ziffern, Leer, Raute, ... sind erlaubt.")

        # Adresse
        while True:
            adresse = raw_input('Adresse (nur eine Zeile): ')
            if adresse:
                kunde.adresse = adresse
            break

        # Kommentar
        while True:
            kommentar = raw_input('Kommentar (nur eine Zeile): ')
            if kommentar:
                kunde.kommentar = kommentar
            break

        try:
            kunde.store(k.cur)
        except sqlite3.IntegrityError as e:
            print("Name ist bereits in Verwendung.")
            sys.exit(2)

        k.con.commit()
        print("Gespeichert. Kundennummer lautet: " + str(kunde.id))

    elif arguments['client'] and arguments['edit']:
        print("Work-in-progress...")
        print("IMPLEMENT ME!")

    elif arguments['client'] and arguments['show']:
        try:
            kunde = Kunde.load_from_name(arguments['<name>'], k.cur)
        except NoDataFound:
            print(u"Konnte keinen Kunde unter '%s' finden." % arguments['<name>'])
            sys.exit(2)

        print(kunde.to_string(short=False))

        print("Kontostand: " + moneyfmt(kunde.summe) + ' EUR')

    elif arguments['client'] and arguments['summary']:
        try:
            kunde = Kunde.load_from_name(arguments['<name>'], k.cur)
        except NoDataFound:
            print(u"Konnte keinen Kunde unter '%s' finden." % arguments['<name>'])
            sys.exit(2)

        print(kunde.to_string(short=True))

        print("Kontostand: " + moneyfmt(kunde.summe) + ' EUR')

    elif arguments['client'] and arguments['charge']:
        try:
            kunde = Kunde.load_from_name(arguments['<name>'], k.cur)
        except NoDataFound:
            print(u"Konnte keinen Kunde unter '%s' finden." % arguments['<name>'])
            sys.exit(2)

        comment = unicode(' '.join(arguments['<comment>']).decode('utf-8'))

        kunde.add_buchung(-Decimal(arguments['<amount>']), comment)
        kunde.store(k.cur)

        k.con.commit()

    elif arguments['client'] and arguments['payup']:
        try:
            kunde = Kunde.load_from_name(arguments['<name>'], k.cur)
        except NoDataFound:
            print(u"Konnte keinen Kunde unter '%s' finden." % arguments['<name>'])
            sys.exit(2)

        comment = unicode(' '.join(arguments['<comment>']).decode('utf-8'))

        kunde.add_buchung(Decimal(arguments['<amount>']), comment)
        kunde.store(k.cur)

        k.con.commit()

    elif arguments['client'] and arguments['list']:
        print("KdNr|                     Name|  Kontostand|  Grenze| Letzte Zahlung")
        print("----+-------------------------+------------+--------+---------------")

        for k in k.kunden:
            letzte_zahlung = sorted(map(lambda b: b.datum, filter(lambda b: b.betrag > 0,
                                                                  k.buchungen)))[:1]

            if not letzte_zahlung:
                letzte_zahlung = "n/a"
            else:
                letzte_zahlung = letzte_zahlung[0].strftime('%Y-%m-%d')

            print(u'{:>5}|{:>25}|{:>8} EUR|{:>8}| {:>14}'.format(
                k.id, k.name, moneyfmt(k.summe), moneyfmt(k.schuldengrenze), letzte_zahlung))

    elif arguments['receipt']:
        r = Rechnung.load_from_id(int(arguments['<id>']), k.cur)
        print(r.receipt(header=cfg.get('receipt', 'header'), footer=cfg.get('receipt', 'footer'),
                        export=bool(arguments["--export"])))

        if arguments['--print']:
            r.print_receipt(cfg)

    else:
        print("This should not have happend. Option not implemented.")
        print(arguments)
