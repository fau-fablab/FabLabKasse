#!/usr/bin/env python
import argparse
from datetime import datetime, timedelta
import sqlite3
import codecs
from decimal import Decimal
import re

from faucardStates import Status, Info
#from FabLabKasse import scriptHelper

class TransactionEntry:
    ''' Class that stores all relevant information about a Transaction from MagPosLog.
        Has functions to perform checks against FabLabKasse Kassenbuch
    '''
    def __init__(self, timestamp, cardnumber, oldbalance, newbalance, amount, datum, ID, status, info):
        ''' Init function that sets up all member variables
            :param timestamp: Timestamp of transaction
            :type timestamp: datetime
            :param cardnumber: Cardnumber of user
            :type cardnumber: str
            :param oldbalance: Old Card Balance in Cents
            :type oldbalance: int
            :param newbalance: New Card Balance in Cents
            :type newbalance: int
            :param amount: Amount that the user should have payed
            :type amount: Decimal
            :param datum: MagPosLog Entry datum of last edit
            :type datum: datetime
            :param status: Status of Transaction Entry
            :type status: faucardStates.Status
            :param info: Info Code to transaction status
            :type info: faucardStates.Info
            
        '''
        self.timestamp_payed = timestamp
        self.cardnumber = cardnumber
        self.oldbalance = oldbalance
        self.amount = Decimal(amount)
        self.newbalance = newbalance
        self.datum = datum
        self.ID = ID
        self.status = status
        self.info = info

        # Initialize Status Flags
        self.isTransactionResult = (status == Status.transaction_result)
        self.isTransactionError = (status == Status.decreasing_balance and info == Info.unkown_error)
        self.searchedKbMatch = False
        self.possibleKbMatch = False
        self.definitiveKbMatch = False

        self.ignoreInSum = False

        # Initialize Kassenbuch match
        self.kbMatchID = -1
        self.kbMatchRechnung = -1
        self.kbMatchDatum = None
        self.kbMatchCount = 0

    def toCSVLine(self, separator):
        '''
        Returns this Transaction Entry as a CSV style line for reporting.
        :param separator: CSV separator
        :type separator: str
        :return: CSV line string
        :rtype: str       
        '''
        return u"{1}{0}{2}{0}{3}{0}{4}{0}{5}{0}{6}\n".format(separator, self.timestamp_payed.strftime("%d-%m-%Y %H:%M:%S"),
                                                             self.cardnumber, self.oldbalance, self.amount, self.newbalance, self.kbMatchRechnung)

    def toConsoleLine(self):
        '''
        Returns a line string that displays the most important information for debugging
        :return: Information string
        :rtype: str
        '''
        return u"ID: {0} - {1} - card: {2} - amount: {3}\n".format(self.ID, self.timestamp_payed.strftime("%d-%m-%Y %H:%M:%S"),
                                                                   self.cardnumber, self.amount)

    def searchForKbMatch(self, con):
        '''
        Searches for matching entry in kassenbuch using the database connection 'con'.
        :param con: Kassenbuch database connection
        :type con: sqlite3.Connection
        :return: True if definitive match was found, False otherwise
        :rtype: Bool
        '''
        curKb = con.cursor()

        # Determine corresponding rechnung
        curKb.execute("SELECT rechnung, datum, ID FROM buchung WHERE konto = 'FAUKarte' AND (abs(betrag - ?) < 1e-4) AND datum BETWEEN ? AND ? ",(unicode(self.amount), self.timestamp_payed, self.timestamp_payed + timedelta(seconds=20)))
        safetyCounter = 0
        rechnungsnr = -1
        kbDatum = None
        kbID = -1
        for rowKb in curKb.fetchall():
            safetyCounter += 1
            rechnungsnr = rowKb[0]
            kbDatum = datetime.strptime(rowKb[1].split(".")[0],"%Y-%m-%d %H:%M:%S")
            kbID = rowKb[2]

        # Search for Late Bookings
        if safetyCounter == 0:
            curKb.execute("SELECT rechnung, datum, ID, kommentar FROM buchung WHERE konto = 'FAUKarte' AND (abs(betrag - ?) < 1e-4) AND kommentar LIKE ? ",(unicode(self.amount), "%Nachtrag%" ))
            for rowKb in curKb.fetchall():
                comment = rowKb[3]
                
                # Try to get datetime out of comment
                regEx= "[0-9]{4}\\-[0-9]{2}\\-[0-9]{2}\\ [0-9]{2}\\:[0-9]{2}\\:[0-9]{2}"
                match = re.search(regEx, comment)
                if match == None:
                    continue

                # Convert from string to datetime
                dateStr = match.group()
                date = datetime.strptime(dateStr,"%Y-%m-%d %H:%M:%S")
                # If date is within +5 -0.5 seconds to timestamp_payed we assume its right 
                if date >= self.timestamp_payed - timedelta(seconds=0.5) and date <= self.timestamp_payed + timedelta(seconds=5):
                    safetyCounter += 1
                    rechnungsnr = rowKb[0]
                    kbDatum = datetime.strptime(rowKb[1].split(".")[0],"%Y-%m-%d %H:%M:%S")
                    kbID = rowKb[2]
                

        # Evaluate
        self.searchedKbMatch = True
        self.kbMatchCount = safetyCounter

        if safetyCounter == 0:
            # No Match
            self.possibleKbMatch = False
            self.definitiveKbMatch = False
            return False
        elif safetyCounter == 1:
            # DefinitveMatch
            self.possibleKbMatch = True
            self.definitiveKbMatch = True
            self.kbMatchID = kbID
            self.kbMatchDatum = kbDatum
            self.kbMatchRechnung = rechnungsnr
            return True
        else:
            self.possibleKbMatch = True
            self.definitiveKbMatch = False
            return False

        
            
        

def query_yes_no(quiet = False):
    """Ask a yes/no question via raw_input() and return the boolean representation.
    
    The return value is True for "yes" or False for "no".
    """
    truthtable = {"yes": True, "y": True, "no": False, "n": False}
    if quiet is True:
        print("No")
        return False
    
    while True:
        choice = raw_input().lower()
        if choice in truthtable:
            return truthtable[choice]
        else:
            print("\nPlease respond with 'yes' or 'no' "
                             "(or 'y' or 'n').")


def valid_date(s):
    ''' Returns a valid datetime from a string. Used for argparse datetime strings'''
    try:
        return datetime.strptime(s,"%Y-%m-%d_%H:%M:%S")
    except ValueError:
        msg = "Not a valid date: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)

def dummy_cards(s):
    ''' Returns a list of card numbers to ignore'''
    try:
        return s.split("|")
    except ValueError:
        msg = "Not valid card numbers: '{0}'.".format(s)
        raise argparse.ArgumentTypeError(msg)


def verify_sum(curKb, start, end, magposSum, transactionList, quiet = False):
    ''' Checks wether the sum from the MagPosLog equals the Sum in Kassenbuch.
        Possible Failures are a missing transaction in the Kassenbuch if Kasse crashed
        after payment'''
    kbSumme = Decimal(0);
    kbNotes = ""
    try:
        curKb.execute("SELECT betrag, kommentar, datum, ID FROM buchung WHERE konto = 'FAUKarte' AND datum BETWEEN ? AND ?;",(start, end));
        for row in curKb.fetchall():

            if Decimal(row[0]) < 0: # STORNO can only be due to testing -> ignore
                print "Found negative booking in Kassenbuch: ID {0}".format(row[3])
                kbNotes += "Found negative booking in Kassenbuch: ID {0} - Kommentar: {1}\n".format(row[4], row[1])
                continue;

            # Check if there is a matching transaction in magposlog
            foundTransaction = False
            for transaction in transactionList:
                if transaction.kbMatchID == row[3]:
                    foundTransaction = True
                    break

            if foundTransaction is False:
                print "Kassenbuch-entry not present in MagPosLog: \nID: {0} - Datum: {1} - Amount: {2} - Kommentar: {3}".format(row[3], row[2], row[0], row[1])
                kbNotes += "Kassenbuch-entry not present in MagPosLog: \nID {0} - Datum {1} - Amount {2} - Kommentar {3}\n".format(row[3], row[2], row[0], row[1])
            
            
            if foundTransaction is False and isinstance(row[1],(str, unicode)) and "Nachtrag" in row[1]: # Found possible Manual Transfer to fix crash of Kassenterminal, ask to skip
                print "It is possibly a late booking. Ignore the amount in verification? (y/n)"
                if query_yes_no(quiet) == True:	# Skip this
                    kbNotes += "Ignored kassenbuch fix: ID {0} - Datum {1} - Amount {2} - Kommentar {3}\n".format(row[3], row[2], row[0], row[1])
                    continue;
                kbNotes += "Kassenbuch fix detected: ID {0} - Datum {1} - Amount {2} - Kommentar {3}\n".format(row[3], row[2], row[0], row[1])

            
            kbSumme += Decimal(row[0]).quantize(Decimal('.01'));

        if kbSumme != magposSum:
            print "Sum Difference: MagPos: {0} \tKassenbuch: {1}".format(magposSum, kbSumme);
        else:
            print "No Sum Difference between MagPosLog and Kassenbuch"
        return kbSumme, kbNotes

    except sqlite3.OperationalError as e:
        print "Failed to verify sum: {0}".format(e);
        return kbSumme, kbNotes
    return kbSumme, kbNotes



if __name__ == '__main__':
    separator = u','

    parser = argparse.ArgumentParser(description="Generates a Summary and Log from Start Date to End Date of a given MagPosLog.sqlite3 file.")
    parser.add_argument('-f', "--file", help="MagPosLog to build log from", required=True)
    parser.add_argument('-s', "--startdate", help="The Start Date - format YYYY-MM-DD_HH:MM:SS", required=True, type=valid_date)
    parser.add_argument('-e', "--enddate", help = "The End Date - format YYYY-MM-DD_HH:MM:SS", required=False, type=valid_date)
    parser.add_argument('-o', "--outputpath", help="Output path of csv and summary, e.g. /usr/var/test -> test.csv, testsummary.txt", required=True)
    parser.add_argument('-k', "--kassenbuch", help="Kassenbuch to build log from", required=True)
    parser.add_argument('-i', "--ignore", help="Ingores the given card numbers", required = False, type=dummy_cards, default= []);
    parser.add_argument('-d', "--detail", help="Enables the output of an detailed CSV containing the single positions per Rechnung", const=True, default=False, nargs = '?')
    parser.add_argument('-q', "--quiet", help="Quiet Operation, ignores all errors and questions.", const=True, default=False, nargs="?")

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

    startdate = args.startdate + timedelta(milliseconds=0)
    enddate = args.enddate+ timedelta(microseconds=999999)	# Assure that the full second is being included
    summe = Decimal(0)
    ignored = Decimal(0)

    if args.ignore:
        for card in args.ignore:
            print "Ignoring card number: {}".format(card);


    #cfg = scriptHelper.getConfig()

    print "Building Summary from {0} to {1}".format(startdate,enddate);

    try:
        con = sqlite3.connect(args.file)
        cur = con.cursor()
        con.text_factory = unicode
        

        conKb = sqlite3.connect(args.kassenbuch)
        curKb = conKb.cursor()
        conKb.text_factory = unicode
    except sqlite3.OperationalError as e:
        print "ERROR opening database connections: {0}".format(e)
        raise

    try:
        pass                 
        
                
    except sqlite3.OperationalError as e:
        print "ERROR: {0}".format(e)
        raise

    try:
        # 0. Data Initialization
        # Transactions
        transactionList = []

        # Metrics
        firstDate = None
        #firstBookingDate = None
        lastDate = None
        #lastBookingDate = None
        firstID = -1

        # Result containers
        summaryNotes = ""
        hasSuspiciousEntry = False          # If last entry of timeframe in MagPosLog is crashed transaction (might have a
        hasSusupiciousEntryTransaction = False  # If first entry after timeframe in MagPosLog is transaction result (might point towards suspicious transaction)
        hasSuspiciousTransaction = False    # If first entry of timeframe in MagPosLog is transaction result (might point towards old transaction)


        # 1. Data Gathering
        # 1.1 Gather Metrics
        # 1.1.1 Get first MagPosLog Entry ID of timeframe
        cur.execute("SELECT ID FROM MagPosLog WHERE datum >= ? AND datum <= ? ORDER BY datum ASC LIMIT 1;",(startdate, enddate))
        for row in cur.fetchall():
            firstID = row[0]

        # There should be at least one entry!
        assert firstID != -1, \
            "Error gathering metrics. There are no entries in MagPosLog"

        
        # 1.2 Searching for normal transactions
        cur.execute("SELECT timestamp_payed, cardnumber, oldbalance, amount, newbalance,  datum, ID, info, status FROM MagPosLog WHERE timestamp_payed >= ? AND timestamp_payed <= ? ORDER BY timestamp_payed ASC",(startdate, enddate))
        
        for row in cur.fetchall():
            # Create TransactionEntry from MagPosLog
            timestamp = datetime.strptime(row[0].split(".")[0],"%Y-%m-%d %H:%M:%S")
            amount = Decimal(row[3]).quantize(Decimal('.01'))
            
            entry = TransactionEntry(timestamp = timestamp,
                                     cardnumber = row[1],
                                     oldbalance = row[2],
                                     newbalance = row[4],
                                     amount = amount,
                                     datum = datetime.strptime(row[5].split(".")[0],"%Y-%m-%d %H:%M:%S"),
                                     ID = row[6],
                                     status = Status(row[7]),
                                     info = Info(row[8]))

            # Extract Metrics
            if len(transactionList) == 0:
                firstdate = timestamp
            else:
                lastdate = timestamp

            # Search for Kassenbuch match
            entry.searchForKbMatch(conKb)

            ## Evaluate Search
            # There should only be one result. Otherwise throw exception.
            if entry.kbMatchCount == 0:
                print "An Error occured for this transaction: \n" + entry.toConsoleLine() + "\n Please verify that proceeding is ok! (y/n)\n"
                if query_yes_no(args.quiet) == False:	# Abort if choice
                    print "Cancled log generation";
                    outputfile.close();
                    con.close();
                    quit();
                entry.ignoreInSum = True
                
            # Abort if multiple found
            assert entry.kbMatchCount <= 1, \
                "Query for transaction '" + entry.toConsoleLine() + "' failed. Found multiple."

            """
            if entry.kbMatchCount == 0: 	# need to skip last action as no rechnungsnr found
                continue
            if firstbooking is None:
                firstbooking = entry.kbMatchDatum
            lastbooking = entry.kbMatchDatum
            """
            transactionList.append(entry)
        # End For 


        # 1.3 Search for transaction results (unacknowledged transactions)
        cur.execute("SELECT timestamp_payed, cardnumber, oldbalance, amount, newbalance,  datum, ID FROM MagPosLog WHERE datum >= ? AND datum <= ? AND status == ? AND info == ? ORDER BY datum ASC",(startdate, enddate, Status.transaction_result.value, Info.transaction_ok.value))
        for row in cur.fetchall():
            # Create TransactionEntry from MagPosLog
            timestamp = datetime.strptime(row[5].split(".")[0],"%Y-%m-%d %H:%M:%S")
            amount = Decimal(row[3]).quantize(Decimal('.01'))
            
            entry = TransactionEntry(timestamp = timestamp,
                                     cardnumber = row[1],
                                     oldbalance = row[2],
                                     newbalance = row[4],
                                     amount = amount,
                                     datum = datetime.strptime(row[5].split(".")[0],"%Y-%m-%d %H:%M:%S"),
                                     ID = row[6],
                                     status = Status.transaction_result,
                                     info = Info.transaction_ok)

            entry.searchForKbMatch(conKb)
            
            # Append to List
            transactionList.append(entry)

        # 1.4 Check if last MagPosLog entry is a crashed transaction (Status = Status.decreasing_balance and Info = Info.unkown_error)
        # If last transaction of the month crashed, there is no predictable time frame in which this will be captured in MagPosLog.
        # Therefor check if last entry of MagPosLog hints at possible transaction_result
        cur.execute("SELECT status, info, cardnumber, amount, payed, datum,  ID FROM MagPosLog WHERE datum >= ? AND datum <= ? ORDER BY datum DESC LIMIT 1",(startdate, enddate))
        for entry in cur.fetchall():
            hasSuspiciousEntry = entry[0] == Status.decreasing_balance.value and entry[1] == Info.unkown_error.value
            if hasSuspiciousEntry is True:
                print "Last entry in MagPosLog hints at possible unacknowledged transaction result at next ID"
                print "ID: {0} - {1} - card: {2} - amount: {3}".format(entry[6], entry[5], entry[2], Decimal(entry[3]).quantize(Decimal('0.01')))
                summaryNotes += "Last entry in MagPosLog hints at possible unacknowledged transaction result at next ID\n" + \
                                "ID: {0} - {1} - card: {2} - amount: {3}\n".format(entry[6], entry[5], entry[2], Decimal(entry[3]).quantize(Decimal('0.01')))
            
        # Try to find transaction result (should be next entry)
        if hasSuspiciousEntry is True:
            cur.execute("SELECT status, info, cardnumber, amount, payed, datum,  ID FROM MagPosLog WHERE ID == ?",(entry[6] + 1))
            for row in cur.fetchall():
                if row[0] == Status.transaction_result.value and row[1] == Info.transaction_ok.value:
                    amount = Decimal(row[3]).quantize(Decimal('.01'))
                    summe += amount
                    hasSusupiciousEntryTransaction = True
                    print "Found possible matching transaction result"
                    print "ID: {0} - {1} - card: {2} - amount: {3}".format(entry[6], entry[5], entry[2], Decimal(entry[3]).quantize(Decimal('0.01')))
                    summaryNotes += "Found possible matching transaction result" + \
                                    "ID: {0} - {1} - card: {2} - amount: {3}".format(entry[6], entry[5], entry[2], Decimal(entry[3]).quantize(Decimal('0.01')))

        # 1.5 Sanitze Metrics
        # Set Booking dates to start and enddate if nothing was found to check kassenbuch
        """if firstBookingDate is None: #Did not find any data 
            firstBookingDate = startdate;
        if lastBookingDate is None: #Did not find any data
            lastBookingDate = enddate;
        print "first: {}".format(firstbooking)
        """
        
        # 2. Evaluation
        print "\nEvaluating Data:"
        # 2.1 Building Sum
        SummeOK = Decimal(0)
        SummeTransactionResults = Decimal(0)
        SummeMissingBooking = Decimal(0)
        SummeTestCards = Decimal(0)
        SummePreviousTimeframe = Decimal(0)
        SummeKassenbuch = Decimal(0)
        SummeBilling = Decimal(0)
        strSummen = ""
        strNoKbMatch = "No Kassenbuch entries for these transactions:\n"


        for entry in transactionList:
            if entry.kbMatchID == -1:
                strNoKbMatch += entry.toConsoleLine() + "\n"
            
            if (entry.cardnumber in args.ignore):
                SummeTestCards += entry.amount  # ignore the sum if testcard
                
            elif entry.isTransactionResult is True:
                # Tell user about it
                print "Unacknowledged transaction " + entry.toConsoleLine()
                summaryNotes += "Unacknowledged transaction " + entry.toConsoleLine()
                # If Transaction result is first entry in time frame, it refers to date before it
                if entry.ID == firstID:
                    hasSuspiciousTransaction = True
                    print "Unacknowledged transaction ID #{0} is most probably refering to payment before {1}".format(entry.ID, entry.datum.strftime("%d-%m-%Y %H:%M:%S"))
                    summaryNotes += "Unacknowledged transaction ID #{0} is most probably refering to payment before {1}\n".format(entry.ID, entry.datum.strftime("%d-%m-%Y %H:%M:%S"))
                    SummePreviousTimeframe += entry.amount
                else:
                    SummeTransactionResults += entry.amount
                    
            elif entry.definitiveKbMatch is False and entry.possibleKbMatch is False:
                SummeMissingBooking += entry.amount 
                print "Not-booked transaction " + entry.toConsoleLine()
                summaryNotes += "Not-booked transaction " + entry.toConsoleLine()
                
            elif entry.definitiveKbMatch is True:
                SummeOK += entry.amount   # increment Sum for summary
            else:
                print "Invalid code path. Transaction has multiple matches. " + entry.toConsoleLine()
                raise

        SummeBilling = SummeOK + SummeMissingBooking + SummeTransactionResults
        

        strSummen += "Detailed balances:\n"
        strSummen += "Total: {0}\n".format(SummeOK + SummeMissingBooking + SummeTransactionResults)
        strSummen += "Transactions OK: {0}\n".format(SummeOK )
        strSummen += "Transactions Unacknowledged: {0}\n".format(SummeTransactionResults)
        strSummen += "Transactions MissingBookings: {0}\n".format(SummeMissingBooking)
        strSummen += "Testcards: {0}\n".format(SummeTestCards)
        strSummen += "From Previous Time Frame: {0}\n".format(SummePreviousTimeframe)


        print strNoKbMatch
        # 2.2 Performing Sanity Check against Kassenbuch
        SummeKassenbuch, notesKb = verify_sum(curKb, startdate, enddate,
                                              SummeOK + SummeMissingBooking + SummeTransactionResults + SummeTestCards,
                                              transactionList, args.quiet)
        strSummen += "Kassenbuch: {0}\n".format(SummeKassenbuch)

        
        # 2.3 CSV Output
        # 2.3.1 Writing CSV File
        # Open csv file
        outputfile = codecs.open(args.outputpath+".csv", 'w', encoding="utf-8")
        # Write header
        outputfile.write(u"Zeitstempel Zahlung, Kartennummer, Old Balance, Zahlungsbetrag, New Balance, Rechnung\n")
        outputfile.write(u",,,,,\n")
        for entry in transactionList:
            # Write CSV-Line
            line = entry.toCSVLine(separator)
            outputfile.write(line.encode('utf-8'))
            
        # Close magposlog csv file
        outputfile.close()


        # 2.3.1 Writing CSV Detailed output
        if args.detail is True:
            # Open detailed positons csv file
            outputfile = codecs.open(args.outputpath+"_positions.csv", 'w', encoding="utf-8")
            outputfile.write(u"Rechnung, Menge, Einzelpreis, Gesamtpreis\n")
            outputfile.write(u",,,\n")

            for entry in transactionList:
                if (entry.definitiveKbMatch is False) or (entry.kbMatchID == -1):
                    continue
                curKb.execute("SELECT anzahl, einzelpreis FROM position WHERE ID = ?", entry.kbMatchID)

                for row in curKb.fetchall():
                    line = u"{1}{0}{2}{0}{3}{0}{4:.2f}\n".format(separator, nr, row[0], row[1], float(row[0])*float(row[1]))
                    outputfile.write(line.encode('utf-8'))

            outputfile.close()


        # 2.4 Write Summary File
        # Open File
        outputfile = codecs.open(args.outputpath+"_summary.txt", 'w', encoding="utf-8")

        # Write Summary file
        outputfile.write(u"Abrechnung bargeldloser Umsaetze - Akzeptanzstelle FAU FabLab\n")
        outputfile.write(u"Abrechnungszeitraum: {0} bis {1}\n".format(startdate.strftime("%d-%m-%Y %H:%M:%S"), enddate.strftime("%d-%m-%Y %H:%M:%S")))
        outputfile.write(u"Seriennummer der MagnaBox: MB211475\n")#.format(cfg.get('magna_carta', 'serial')))
        outputfile.write(u"Der anfallende Betrag betraegt: {0}\n\n\n".format(SummeBilling))
        outputfile.write(u"#################################################################\nAddition information:\n" +
                         u"#################################################################\n\n")
        outputfile.write(u"Testkarten: {}\n\n".format(", ".join(args.ignore)))

        
        outputfile.write(u"Kassenbuch-Check:\n")

        if SummeKassenbuch == (SummeOK + SummeMissingBooking + SummeTransactionResults + SummeTestCards + SummePreviousTimeframe):
            outputfile.write(u"Der Betrag im MagposLog entspricht dem im Kassenbuch: JA\n")
        else:
            outputfile.write(u"Der Betrag im MagposLog entspricht dem im Kassenbuch: NEIN\n")
            print "VERIFY SUM FAILED: \n" + notesKb;
            
        outputfile.write(u"\n{0}\n".format(strNoKbMatch))
        outputfile.write(u"\n{0}\n".format(notesKb))

        outputfile.write(u"\n{0}\n".format(strSummen))

        outputfile.write(u"\nNotes:\n")
        outputfile.write(summaryNotes)
        
    except IOError as e:
        print "ERROR: Saving CSV and / or Summary failed"
        print "IOERROR: {0}".format(e)
        raise

 	
