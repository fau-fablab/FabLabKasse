#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2014  Julian Hammer <julian.hammer@fablab.fau.de>
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


# export how much money was paid for each PLU
# TODO: group by categories, "tree view"?
# TODO: sorting?

# ATTENTION
# this script must be started from the git FabLabKasse/ directory with PYTHONPATH=".." set


import sys

import FabLabKasse.kassenbuch as kassenbuch
import re
import datetime


def aggregate_consumption(rechnungen):
    '''Returns consumption from given rechnungen'''
    consumption = {}
    consumptionUnits = {}
    name = {}
    for r in rechnungen:
        # how much was paid for each article in the current bill?
        sums = [p['anzahl'] * p['einzelpreis'] for p in r.positionen]
        total = sum(sums)
        positiveTotal = sum([s for s in sums if s > 0])
        # split negative positions (discount / not paid enough) equally among the positive-paid articles
        if total == 0:
            continue
        discountFactor = total / positiveTotal
        assert 0 <= discountFactor <= 1.00001,  "discount calculation error"
        for p in r.positionen:
            plu = p['produkt_ref']
            if plu is not None:
                plu = int(plu)
                if plu in name.keys() and name[plu] != p['artikel']:
                    name[plu] = u"{} (ID {}, verschiedene Bezeichnungen) ".format(p['artikel'],  plu)
                else:
                    name[plu] = p['artikel']
                preis = p['anzahl'] * p['einzelpreis'] * discountFactor
                if preis < 0:
                    continue
#                if plu==9998:
#                    print p
#                    print preis
                if plu not in consumption:
                    consumption[plu] = 0
                    consumptionUnits[plu] = {}
                consumption[plu] += preis
                if p['einheit'] not in consumptionUnits[plu]:
                    consumptionUnits[plu][p['einheit']] = 0
                consumptionUnits[plu][p['einheit']] += p['anzahl'] * discountFactor

    output = []
    for plu in consumption.keys():
        output.append({'plu': plu, 'description': name[plu], 'money': float(consumption[plu]),  'units': consumptionUnits[plu]})
    output.sort(key=lambda x: x['money'], reverse=True)
    return output


def printFiltered(consumption,  search=None, regexp=None, scaleFactor=1, ignoreCase=True):
    """print consumption items matching a string part: printFiltered("laser")
       or a regular expression: printFiltered(regexp=...)

       use scaleFactor for displaying a scaled-up sum (e.g. for normalizing to a whole year)
       """
    sumFiltered = 0

    if search == None:
        # filter by regexp
        search = ""
        filterStr = regexp

        def matchesRegexp(item):
            reFlags = 0
            if ignoreCase:
                reFlags = re.IGNORECASE
            return re.match(regexp, item['description'], reFlags) != None
        consumption = filter(matchesRegexp,  consumption)
    elif regexp == None:
        # filter by string part
        filterStr = "*" + search + "*"
        consumption = filter(lambda item: (search.lower() in item['description'].lower()),  consumption)
    else:
        raise Exception("you must not use both regexp and search string!")

    print "\nname " + filterStr + ":"

    def formatUnits(unitsDict, scaleFactor=1):
        # format unitsDict={"unit":123,"otherUnit":345} to printable text
        result = ""
        for (unit, num) in unitsDict.items():
            result += u"{}:\t{}\t".format(unit, round(float(num) * scaleFactor, 2))
        return result

    sumUnitsFiltered = {}
    for item in consumption:
        sumFiltered += item['money']
        print u"{} \t {:.2f} € \t {}\t{}".format(item['plu'],  item['money'], item['description'], formatUnits(item['units']))
        for (unit, number) in item['units'].items():
            if unit not in sumUnitsFiltered:
                sumUnitsFiltered[unit] = 0
            sumUnitsFiltered[unit] += number
    print "name *" + filterStr + "*:\t{} €\tGesamt\tSumme über Einheiten:\t{}\t{}".format(sumFiltered, round(sum(sumUnitsFiltered.values()), 2), formatUnits(sumUnitsFiltered))
    if scaleFactor != 1:
        print "name *" + filterStr + "*:\t{} €\tGesamt *{} hochgerechnet\tSumme über Einheiten:\t{}\t{}".format(round(float(sumFiltered) * scaleFactor, 2), scaleFactor,
                                                                                                                round(float(sum(sumUnitsFiltered.values())) * scaleFactor, 2), formatUnits(sumUnitsFiltered, scaleFactor))
    print ""


if __name__ == '__main__':
    print "warning: this script operates on snapshotOhnePins.sqlite3 and not on the fresh database!"
    k = kassenbuch.Kasse("snapshotOhnePins.sqlite3")
    if sys.getdefaultencoding() != "utf-8":
        # hack around python2.7 problems
        print "working around python2.7 utf8 problem."
        reload(sys)
        sys.setdefaultencoding("utf-8")

    rechnungen = k.get_rechnungen()
    dateFrom = datetime.datetime.min
    dateTo = datetime.datetime.max
    if len(sys.argv) == 3:
        dateFrom = datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d")
        dateTo = datetime.datetime.strptime(sys.argv[2], "%Y-%m-%d")
        print "filtering from {} to {}".format(dateFrom, dateTo)
        rechnungen = filter(lambda r: dateFrom < r.datum < dateTo, rechnungen)

    dauer = rechnungen[-1].datum - rechnungen[0].datum
    hochrechnenFaktor = round(365. / dauer.days, 2)
    print "Auswertung von {} bis {}, {} Tage, Faktor für 1 Jahr: *{}".format(rechnungen[0].datum, rechnungen[-1].datum, dauer.days, hochrechnenFaktor)
    tageSeitLetzterRechnung = (datetime.datetime.now() - rechnungen[-1].datum).days
    print "{} Tage seit letzter Rechnung".format(tageSeitLetzterRechnung)
    if tageSeitLetzterRechnung > 5:
        print "ACHTUNG: Datenbank ist alt! Bitte neuen Snapshot erstellen (letzte Rechnung aelter als 5 Tage)."

    kunden = k.kunden

    print "--- start of integrity check ---"
    summeAlles = 0
    kundenrechnungen = []
    for kunde in kunden:
        summe = 0
        for b in kunde.buchungen:
            if b.rechnung != None:
                kundenrechnungen.append(b.rechnung)
            for r in rechnungen:
                if r.id != b.rechnung:
                    continue
                for p in r.positionen:
                    summe += p['anzahl'] * p['einzelpreis']
        # print "{}: {}".format(kunde.name, summe)
        summeAlles += summe
    print summeAlles

    summe = 0
    for r in rechnungen:
        if r.id in kundenrechnungen:
            continue
        for p in r.positionen:
            summe += p['anzahl'] * p['einzelpreis']
            # print summe,  p['anzahl']*p['einzelpreis']
    print summe

    rechnungen = k.get_rechnungen()
    import copy
    alleRechnungen = copy.deepcopy(k.get_rechnungen())
    if len(sys.argv) == 3:
        dateFrom = datetime.datetime.strptime(sys.argv[1], "%Y-%m-%d")
        dateTo = datetime.datetime.strptime(sys.argv[2], "%Y-%m-%d")
        print "filtering from {} to {}".format(dateFrom, dateTo)
        rechnungen = filter(lambda r: dateFrom < r.datum < dateTo, rechnungen)

    summeBuchungen = 0
    buchungen = k.get_buchungen()
    habenBuchung = False  # alternate between positive and negative entries
    buchungsRechnungen = set()
    for b in buchungen:
        if not dateFrom < b.datum < dateTo:
            continue
        if b.konto == "Besucher":
            summeBuchungen += b.betrag
        if b.rechnung == None:
            if b.konto == "Besucher":
                print "Warning: Buchung ohne Rechnung wird nicht berücksichtigt", b
            continue
        buchungsRechnungen.add(b.rechnung)
        foundRechnung = False
        for r in alleRechnungen:
            if r.id == b.rechnung:
                foundRechnung = True
                habenBuchung = not habenBuchung
                if habenBuchung:
                    assert r.summe == b.betrag
                else:
                    assert r.summe == -b.betrag
                # print r.datum, b.datum
                # print rechnungssumme,  b.betrag
                break
        assert foundRechnung,  "cannot find rechnung {}".format(b.rechnung)
    rechnungsIds = set(map(lambda r: r.id, rechnungen))
    assert buchungsRechnungen.difference(rechnungsIds) == set()
    print "Buchungen:", summeBuchungen
    print "alle Rechnungen:", sum(map(lambda r: r.summe, rechnungen))

    print "--- end of integrity check ---"

    # FabLab-Eigenverbrauch herausfiltern
    fablabId = None
    for kunde in kunden:
        if kunde.name == "fablab":
            fablabKunde = kunde
            break

    fablabRechnungen = []
    for b in fablabKunde.buchungen:
        if b.rechnung != None:
            fablabRechnungen.append(b.rechnung)

    rechnungenOhneFablab = filter(lambda r: r.id not in fablabRechnungen,   rechnungen)
    rechnungenFablab = filter(lambda r: r.id in fablabRechnungen,   rechnungen)

    consumption = aggregate_consumption(rechnungenOhneFablab)
    consumptionFablab = aggregate_consumption(rechnungenFablab)

    print "Eigenverbrauch:"
    printFiltered(consumptionFablab, '',  scaleFactor=hochrechnenFaktor)
    print ""

    print "Alles außer Eigenverbrauch:"
    printFiltered(consumption, '',  scaleFactor=hochrechnenFaktor)

    print ""

#    for item in consumption:
#        print u"{} \t {:.2f} \t {}".format(item['plu'],  item['money'], item['description'])

    printFiltered(consumption, "platine",  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, "spende",  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'3D',  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'Laserzeit',  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'Shirt',  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'Thermotransferpresse',  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'folie',  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'drucken',  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, regexp=ur'^Acryl', scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, 'Leuchtschild', scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, regexp=ur'^Wordclock', scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, regexp=u'^(MDF|HDF|Sperr)', scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, ignoreCase=False,  regexp=u'(Batterie|Diode|Drehknopf|LM|OP|SMD|Spannung|Spul|Litze|Elko|kondensator|LED|ATmega|ATtiny|Netzteil|Poti|Quarz|schalter|Sicherung|Sockel|Buchse|Stecker|Stift|Transistor|Widerstand)', scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'DIN',  scaleFactor=hochrechnenFaktor)

    fraesenstart = datetime.datetime(2014, 05, 10, 12, 00)
    print "Achtung anderer Faktor für Fräse, weil erst etwa ab {} in Betrieb:".format(fraesenstart)
    printFiltered(consumption, u'Fräs', scaleFactor=365. / (rechnungen[-1].datum - fraesenstart).days)
    printFiltered(consumption, u'Dreh',  scaleFactor=hochrechnenFaktor)
    printFiltered(consumption, u'Alu',  scaleFactor=hochrechnenFaktor)

    print "Fräsenflat aus freier Preiseingabe:"
    summeFraesenflat = 0

    def printFilteredFreiePreiseingabe(rechnungen, searchwords):
        summe = 0
        for r in rechnungen:
            for p in r.positionen:
                if p['produkt_ref'] != '9997':
                    continue
                foundWord = False
                for searchword in searchwords:
                    if searchword.lower() in p['artikel'].lower():
                        foundWord = True
                        break
                if foundWord:
                    summe += float(p['anzahl'] * p['einzelpreis'])
        print "{}:  {} , hochgerechnet {} ".format(searchwords, summe,  summe * 365. / (rechnungen[-1].datum - rechnungen[0].datum).days)
    printFilteredFreiePreiseingabe(rechnungen, ["flat"])
    printFilteredFreiePreiseingabe(rechnungen, ["reichelt", "bestell", "PO",  "MEW",  "MW"])

    printFiltered(consumption, "freie preiseingabe",  scaleFactor=hochrechnenFaktor)
