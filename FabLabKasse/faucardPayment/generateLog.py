#!/usr/bin/env python3


import sys
import os

# WORKAROUND For absolute imports to work even if generateLog.py is called as a script - adapted from https://stackoverflow.com/a/49375740
if "FabLabKasse" not in sys.modules:
    sys.path.append(os.path.dirname(os.path.realpath(__file__)) + "/../../")


import argparse
from datetime import datetime, timedelta
import sqlite3
import codecs
from decimal import Decimal
from FabLabKasse.faucardPayment.faucardStates import Status, Info

# from FabLabKasse import scriptHelper


def query_yes_no():
    """Ask a yes/no question via input() and return the boolean representation.

    The return value is True for "yes" or False for "no".
    """
    truthtable = {"yes": True, "y": True, "no": False, "n": False}
    while True:
        choice = input().lower()
        if choice in truthtable:
            return truthtable[choice]
        else:
            print("\nPlease respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


def valid_date(s):
    """Returns a valid datetime from a string. Used for argparse datetime strings"""
    try:
        return datetime.strptime(s, "%Y-%m-%d_%H:%M:%S")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


def dummy_cards(s):
    """Returns a list of card numbers to ignore"""
    try:
        return s.split("|")
    except ValueError:
        msg = "Not valid card numbers: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


def verify_sum(curKb, start, end, magposSumWithoutIgnored, magposSumIgnored):
    """Checks wether the sum from the MagPosLog equals the Sum in Kassenbuch.
    Possible Failures are a missing transaction in the Kassenbuch if Kasse crashed
    after payment"""
    kbSumme = Decimal(0)
    try:
        curKb.execute(
            "SELECT betrag, kommentar, datum FROM buchung WHERE konto = 'FAUKarte' AND datum BETWEEN ? AND ?;",
            (start, end),
        )
        for row in curKb.fetchall():
            kbSumme += Decimal(row[0]).quantize(Decimal(".01"))

        if kbSumme != magposSumWithoutIgnored:
            print(
                f"Sum Difference: MagPos (excluding {magposSumIgnored} € ignored bookings): {magposSumWithoutIgnored} €. \tKassenbuch: {kbSumme} €"
            )
        else:
            print("No Sum Difference between MagPosLog and Kassenbuch")
        return kbSumme == magposSumWithoutIgnored

    except sqlite3.OperationalError as e:
        print("Failed to verify sum: {0}".format(e))
        return False
    return False


if __name__ == "__main__":
    seperator = ","

    parser = argparse.ArgumentParser(
        description="Generates a Summary and Log from Start Date to End Date of a given MagPosLog.sqlite3 file."
    )
    parser.add_argument(
        "-f", "--file", help="MagPosLog to build log from", required=True
    )
    parser.add_argument(
        "-s",
        "--startdate",
        help="The Start Date - format YYYY-MM-DD_HH:MM:SS",
        required=True,
        type=valid_date,
    )
    parser.add_argument(
        "-e",
        "--enddate",
        help="The End Date - format YYYY-MM-DD_HH:MM:SS",
        required=True,
        type=valid_date,
    )
    parser.add_argument(
        "-o",
        "--outputpath",
        help="Output path of csv and summary, e.g. /usr/var/test -> test.csv, testsummary.txt",
        required=True,
    )
    parser.add_argument(
        "-k", "--kassenbuch", help="Kassenbuch to build log from", required=True
    )
    parser.add_argument(
        "-i",
        "--ignore",
        help="Ingores the given card numbers",
        required=False,
        type=dummy_cards,
        default=[],
    )
    parser.add_argument(
        "-d",
        "--detail",
        help="Enables the output of an detailed CSV containing the single positions per Rechnung",
        const=True,
        default=False,
        nargs="?",
    )

    try:
        args = parser.parse_args()
    except argparse.ArgumentTypeError as e:
        print("ERROR: ArgumentTypeError '{0}'".format(e))
        print("Please refer argument format to given example in -help")
        raise
    except argparse.ArgumentError as e:
        print("ERROR: ArgumentParsing failed '{0}'".format(e))
        print("Please check if all arguments are valid")
        raise

    startdate = args.startdate + timedelta(milliseconds=0)
    enddate = args.enddate + timedelta(
        microseconds=999999
    )  # Assure that the full second is being included
    summe = Decimal(0)
    ignored = Decimal(0)

    if args.ignore:
        for card in args.ignore:
            print("Ignoring card number: {}".format(card))

    # cfg = scriptHelper.getConfig()

    print("Building Summary from {0} to {1}".format(startdate, enddate))

    try:
        con = sqlite3.connect(args.file)
        cur = con.cursor()
        con.text_factory = str
        cur.execute(
            "SELECT timestamp_payed, cardnumber, oldbalance, amount, newbalance,  datum, status, info, payed, ID FROM MagPosLog WHERE datum >= ? AND datum <= ? ORDER BY datum ASC",
            (startdate, enddate),
        )

        conKb = sqlite3.connect(args.kassenbuch)
        curKb = conKb.cursor()
        conKb.text_factory = str
    except sqlite3.OperationalError as e:
        print("ERROR: {0}".format(e))
        raise

    try:
        # Open csv filed
        outputfile = codecs.open(args.outputpath + ".csv", "w", encoding="utf-8")

        # Write header
        outputfile.write(
            "Zeitstempel Zahlung, Kartennummer, Old Balance, Zahlungsbetrag, New Balance, Rechnung\n"
        )
        outputfile.write(",,,,,\n")

        firstdate = None
        firstbooking = None
        lastdate = None
        lastbooking = None
        rechnungsliste = []
        nonbookedlist = []

        counter = 0
        # Write one row for each row in database
        for row in cur.fetchall():

            def str2date(x):
                """
                convert string x in format "2023-05-25 00:00:00.12309213" to datetime, ignoring milliseconds
                """
                if x is None:
                    return x
                else:
                    return datetime.strptime(x.split(".")[0], "%Y-%m-%d %H:%M:%S")

            timestamp = str2date(row[0])
            datum = str2date(row[5])

            amount = Decimal(row[3]).quantize(Decimal(".01"))

            status = Status(row[6])
            info = Info(row[7])
            paid = bool(row[8])

            booking_txt = f"MagPosBooking(datum={datum}, timestamp_payed={timestamp}, status={status}, info={info}, paid={paid}, amount={amount})"

            # print(booking_txt)

            if not paid:
                # Normal states for "not paid" are:
                # - initializing
                # - wait for card
                # - not enough balance on card
                # All other states are suspicious.
                if status not in [
                    Status.initializing,
                    Status.waiting_card,
                    Status.balance_underflow,
                ]:
                    print(
                        "WARNING: Found unpaid booking in suspicious state. Assuming that this booking exited BEFORE taking money from the FauCard. Please check manually: "
                        + booking_txt
                    )

            if paid:
                if status != Status.booking_done:
                    print(
                        "WARNING: Found paid booking in suspicious state. Assuming that this booking DID take money from the FauCard. Please check manually: "
                        + booking_txt
                    )

            # We assume that the "paid" flag in the database is correct (1 if money was taken from the FAUCard and 0 otherwise).
            if not paid:
                # ignore all bookings that did not take money (e.g., canceled by user)
                continue

            if timestamp is None:
                print(
                    f"WARNING: Booking at {datum} has no timestamp_payed. Maybe a crash occured?"
                )
                timestamp = datum

            if counter == 0:
                firstdate = timestamp
                counter += 1
            else:
                lastdate = timestamp

            # Determine corresponding rechnung
            curKb.execute(
                "SELECT rechnung, datum FROM buchung WHERE konto = 'FAUKarte' AND (abs(betrag - ?) < 1e-4) AND datum BETWEEN ? AND ? ",
                (str(amount), timestamp, timestamp + timedelta(seconds=20)),
            )
            safetyCounter = 0
            rechnungsnr = -1

            for rowKb in curKb.fetchall():
                safetyCounter += 1
                rechnungsnr = rowKb[0]

            # There should only be one result. Otherwise throw exception.
            if safetyCounter == 0:
                print(
                    "An Error occured: Can not find corresponding invoice (Rechnung) for amount {0} at timestamp {1}.".format(
                        str(amount), timestamp
                    )
                )
                nonbookedlist.append(
                    "ID: {0}, Card: {1}, timestamp: {2}, amount: {3}".format(
                        row[6], row[1], timestamp, str(amount)
                    )
                )  # append log for this error

            # Abort if multiple found
            assert (
                safetyCounter <= 1
            ), "Query for amount {0} at timestamp {1} failed. Found multiple.".format(
                row[3], timestamp
            )

            # Write CSV-Line
            line = "{1}{0}{2}{0}{3}{0}{4}{0}{5}{0}{6}\n".format(
                seperator,
                timestamp.strftime("%d-%m-%Y %H:%M:%S"),
                row[1],
                row[2],
                row[3],
                row[4],
                rechnungsnr,
            )
            # print "{0} - {1} - {2}".format(row[3], Decimal(row[3]), Decimal(row[3]).quantize(Decimal('.01')))
            if "{}".format(row[1]) in args.ignore:  # ignore the sum if testcard
                ignored += amount  # increment Sum for verify
            else:
                summe += amount  # increment Sum for summary

            outputfile.write(line)

            if safetyCounter == 0:  # need to skip last action as no rechnungsnr found
                continue
            if firstbooking is None:
                firstbooking = datetime.strptime(rowKb[1], "%Y-%m-%d %H:%M:%S.%f")
            lastbooking = datetime.strptime(rowKb[1], "%Y-%m-%d %H:%M:%S.%f")
            rechnungsliste += [rechnungsnr]  # add rechnungs nr.

        # Close magposlog csv file
        outputfile.close()

        # Set Booking dates to start and enddate if nothing was found to check kassenbuch
        if firstbooking is None:  # Did not find any data
            firstbooking = startdate
        print("first: {}".format(firstbooking))

        if args.detail is True:
            # Open detailed positons csv file
            outputfile = codecs.open(
                args.outputpath + "_positions.csv", "w", encoding="utf-8"
            )
            outputfile.write("Rechnung, Menge, Einzelpreis, Gesamtpreis\n")
            outputfile.write(",,,\n")

            for nr in rechnungsliste:
                curKb.execute(
                    "SELECT anzahl, einzelpreis FROM position WHERE rechnung = ?", [nr]
                )

                for row in curKb.fetchall():
                    line = "{1}{0}{2}{0}{3}{0}{4:.2f}\n".format(
                        seperator, nr, row[0], row[1], float(row[0]) * float(row[1])
                    )
                    outputfile.write(line)

            outputfile.close()

        # Open Summary file
        outputfile = codecs.open(args.outputpath + "summary.txt", "w", encoding="utf-8")

        # Write Summary file
        outputfile.write(
            "Abrechnung bargeldloser Umsaetze - Akzeptanzstelle FAU FabLab\n"
        )
        outputfile.write(
            "Abrechnungszeitraum: {0} bis {1}\n".format(
                startdate.strftime("%d-%m-%Y %H:%M:%S"),
                enddate.strftime("%d-%m-%Y %H:%M:%S"),
            )
        )
        outputfile.write(
            "Seriennummer der MagnaBox: MB211475\n"
        )  # .format(cfg.get('magna_carta', 'serial')))
        outputfile.write("Der anfallende Betrag betraegt: {0}\n".format(summe))
        outputfile.write("Testkarten: {}\n".format(", ".join(args.ignore)))
        if verify_sum(curKb, startdate, enddate, summe, ignored):
            outputfile.write(
                "Der Betrag im MagposLog entspricht dem im Kassenbuch: JA\n"
            )
        else:
            outputfile.write(
                "Der Betrag im MagposLog entspricht dem im Kassenbuch: NEIN\n"
            )
            print("VERIFY SUM FAILED")

        if nonbookedlist != []:
            outputfile.write("Some Payments were not booked:\n")
            nb_cnt = 1
            for payment in nonbookedlist:
                outputfile.write("{0} {1}\n".format(nb_cnt, payment))
                nb_cnt = nb_cnt + 1
        print("Ignored {}".format(str(ignored)))
    except IOError as e:
        print("ERROR: Saving CSV and / or Summary failed")
        print("IOERROR: {0}".format(e))
        raise
