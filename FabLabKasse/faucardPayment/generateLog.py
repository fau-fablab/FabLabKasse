import argparse
from datetime import datetime, timedelta
import sqlite3
import codecs
from decimal import Decimal

def valid_date(s):
    try:
        return datetime.strptime(s,"%Y-%m-%d_%H:%M:%S")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


if __name__ == '__main__':
    seperator = u','

    parser = argparse.ArgumentParser(description="Generates a Summary and Log from Start Date to End Date of a given MagPosLog.sqlite3 file.")
    parser.add_argument('-f', "--file", help="MagPosLog to build log from", required=True)
    parser.add_argument('-s', "--startdate", help="The Start Date - format YYYY-MM-DD_HH:MM:SS", required=True, type=valid_date)
    parser.add_argument('-e', "--enddate", help = "The End Date - format YYYY-MM-DD_HH:MM:SS", required=False, type=valid_date)
    parser.add_argument('-o', "--outputpath", help="Output path of csv and summary, e.g. /usr/var/test -> test.csv, testsummary.txt", required=True)
    parser.add_argument('-k', "--kassenbuch", help="Kassenbuch to build log from", required=True)

    try:
        args = parser.parse_args()
    except argparse.ArgumentTypeError as e:
        print "ERROR: ArgumentTypeError '{0}'".format(e)
        print "Please refer argument format to given example in -help"
        raise
    except argparse.ArgumentError as e:
        print "ERROR: ArgumentParsing failed '{0}'".format(e)
        print "Please check if all arguments are valid"
        raise

    startdate = args.startdate
    enddate = args.enddate
    summe = Decimal(0)

    try:
        con = sqlite3.connect(args.file)
        cur = con.cursor()
        con.text_factory = unicode
        cur.execute("SELECT timestamp_payed, cardnumber, oldbalance, amount, newbalance,  datum FROM MagPosLog WHERE timestamp_payed >= ? AND timestamp_payed <= ? ORDER BY timestamp_payed ASC",(startdate, enddate))


        conKb = sqlite3.connect(args.kassenbuch)
        curKb = conKb.cursor()
        conKb.text_factory = unicode
    except sqlite3.OperationalError as e:
        print "ERROR: {0}".format(e)
        raise


    try:
        # Open csv filed
        outputfile = codecs.open(args.outputpath+".csv", 'w', encoding="utf-8")

        # Write header
        outputfile.write(u"Zeitstempel Zahlung, Kartennummer, Old Balance, Zahlungsbetrag, New Balance, Rechnung\n")
        outputfile.write(u",,,,,\n")

        firstdate = None
        lastdate = None
        rechnungsliste = []

        counter = 0
        # Write one row for each row in database
        for row in cur.fetchall():
            timestamp = datetime.strptime(row[0].split(".")[0],"%Y-%m-%d %H:%M:%S")

            if counter == 0:
                firstdate = timestamp
                counter += 1
            else:
                lastdate = timestamp

            # Determine corresponding rechnung
            curKb.execute("SELECT rechnung FROM buchung WHERE (betrag = ? OR betrag = ?) AND datum BETWEEN ? AND ? ",(unicode(row[3]), "{:.3f}".format(row[3]), timestamp, timestamp + timedelta(seconds=20)))
            safetyCounter = 0
            rechnungsnr = -1

            for rowKb in curKb.fetchall():
                safetyCounter += 1
                rechnungsnr = rowKb[0]

            #assert safetyCounter == 1

            # Write CSV-Line
            line = u"{1}{0}{2}{0}{3}{0}{4}{0}{5}{0}{6}\n".format(seperator, timestamp.strftime("%d-%m-%Y %H:%M:%S"), row[1], row[2], row[3], row[4], rechnungsnr)
            # print "{0} - {1} - {2}".format(row[3], Decimal(row[3]), Decimal(row[3]).quantize(Decimal('.01')))
            summe += Decimal(row[3]).quantize(Decimal('.01'))   # increment Sum for summary
            rechnungsliste += [rechnungsnr]                     # add rechnungs nr.
            outputfile.write(line.encode('utf-8'))

        # Close magposlog csv file
        outputfile.close()


        # Open detailed positons csv file
        outputfile = codecs.open(args.outputpath+"_positions.csv", 'w', encoding="utf-8")
        outputfile.write(u"Rechnung, Menge, Einzelpreis, Gesamtpreis\n")
        outputfile.write(u",,,\n")

        for nr in rechnungsliste:
            curKb.execute("SELECT anzahl, einzelpreis FROM position WHERE rechnung = ?", [nr])

            for row in curKb.fetchall():
                line = u"{1}{0}{2}{0}{3}{0}{4:.2f}\n".format(seperator, nr, row[0], row[1], float(row[0])*float(row[1]))
                outputfile.write(line.encode('utf-8'))

        outputfile.close()


        # Open Summary file
        outputfile = codecs.open(args.outputpath+"summary.txt", 'w', encoding="utf-8")

        # Write Summary file
        outputfile.write(u"Abrechnung bargeldloser Umsaetze - Akzeptanzstelle FabLab\n")
        outputfile.write(u"Abrechnungszeitraum: {0} bis {1}\n".format(firstdate.strftime("%d-%m-%Y %H:%M:%S"), lastdate.strftime("%d-%m-%Y %H:%M:%S")))
        outputfile.write(u"Seriennummer der MagnaBox: MB211475 \n")
        outputfile.write(u"Der anfallende Betrag betraegt: {0}\n".format(summe))
    except IOError as e:
        print "ERROR: Saving CSV and / or Summary failed"
        print "IOERROR: {0}".format(e)
        raise


