#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import os
from decimal import Decimal
import fnmatch
import ast
import codecs


class Produkt:

    def __init__(self, plu, name, basiseinheit, basispreis, verkaufseinheiten=None, input_mode='DECIMAL'):
        self.PLU = plu
        self.name = name
        self.basiseinheit = basiseinheit
        if not verkaufseinheiten:
            self.verkaufseinheiten = {}
        else:
            self.verkaufseinheiten = verkaufseinheiten
        self.add_verkaufseinheit(basiseinheit, basispreis, 1, input_mode)

    def add_verkaufseinheit(self, verkaufseinheit, preis, basismenge=None, input_mode='DECIMAL'):
        """Fügt eine neue Verkaufseinheit zum Produkt hinzu.

        :param basestr verkaufseinheit: ist ein string, welcher die Einheit beschreibt, z.B. "Platte (600x300mm)"
        :param preis: ist der Preis für _eine_ solche Einheit
        :param basismenge: (optional) ein Umrechnungsfaktor: eine Basisheinheit mal Basismenge entspricht einer Verkaufseinheit
        :param input_mode: (optional) kann DECIMAL, INTEGER oder MINUTES sein. Ändert nichts an dem gespeicherten Wert, dieser ist immer Decimal.
        """
        preis = Decimal(preis)
        if basismenge is not None:
            basismenge = Decimal(basismenge)
        basismenge = basismenge

        self.verkaufseinheiten[verkaufseinheit] = {'preis': preis, 'basismenge': basismenge,
                                                   'input_mode': input_mode, 'name': verkaufseinheit}

    def gesamtpreis(self, menge, einheit=None):
        """Berechnet den Gesamtpreis für *menge* *einheit*. Wenn *einheit* nicht gegeben ist wird
        die Basiseinheit verwenden."""
        if not einheit:
            einheit = self.basiseinheit

        return self.verkaufseinheiten[einheit]['preis'] * Decimal(menge)

    @classmethod
    def load_from_file(cls, filename):
        produkte = {}
        baum = ({}, [])

        p = None
        f = codecs.open(filename, 'r', 'utf8').read()
        for l in f.split('\n'):
            if len(l.strip()) == 0 or l.startswith('#'):
                continue

            l = l.split(';')
            if not (l[0].startswith(' ') or l[0].startswith('\t')):
                p = Produkt(plu=l[0].strip(),
                            name=l[1].strip(),
                            basiseinheit=l[2].strip(),
                            basispreis=Decimal(l[3].strip()),
                            input_mode=l[4].strip())
                produkte[l[0].strip()] = p

                # Decorating the christmas-tree...
                leaf = baum
                for kategorie in ast.literal_eval(l[5]):
                    if kategorie not in leaf[0]:
                        leaf[0][kategorie] = ({}, [])
                    leaf = leaf[0][kategorie]

                leaf[1].append(p)

            else:
                basismenge = l[2].strip()
                if basismenge == 'None':
                    basismenge = None
                else:
                    basismenge = Decimal(basismenge)
                p.add_verkaufseinheit(verkaufseinheit=l[0].strip(),
                                      preis=Decimal(l[1].strip()),
                                      basismenge=basismenge,
                                      input_mode=l[3].strip())

        return produkte, baum

    @classmethod
    def load_from_dir(cls, path):
        produkte = {}
        wald = {}

        for l in os.listdir(path):
            if fnmatch.fnmatch(l, '*.txt'):
                p, baum = cls.load_from_file(path + '/' + l)

                for element in p.iterkeys():
                    assert element not in produkte, \
                        "Duplicate product ID {} when loading file {} \n" \
                        "[already present in a file loaded earlier.]\n Do you have stale files in produkte/ ?".format(
                            element, l)

                produkte.update(p)
                wald[l[:-4]] = baum

        return produkte, wald

    def __repr__(self):
        return '<%s(name=%s, basiseinheit=%s, basispreis=%s, verkaufseinheiten=%s)>' % (
            self.__class__.__name__, self.name.__repr__(), self.basiseinheit.__repr__(),
            self.verkaufseinheiten[self.basiseinheit].__repr__(), self.verkaufseinheiten.__repr__())


if __name__ == '__main__':
    Produkt.load_from_dir('./produkte/')
