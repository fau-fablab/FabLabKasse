Cash Payment
============

Using
-----

All cash movements are logged in a database on a per-coin level, which can be shown with `./cash`

    ./cash show
    ./cash log

Routinemäßige Kassenzählung
---------------------------

auf Deutsch, weil auch die ganze GUI auf Deutsch ist


### 0. Servicemodus aktivieren und den Automat sperren

 - Damit man nicht durcheinander kommt, dürfen keine Zahlungen laufen während man die Auswertung macht! Dazu kann man den Automat sperren.

 - warten bis aktuelle Zahlung abgeschlossen

 - `./enableServiceMode.sh`

 - in der GUI Menü->Servicemodus aktivieren

 - Ausleeren -> Nein, Nachfüllen -> Nein, Absperren -> Ja

 - Jetzt kann der Automat nicht mehr benutzt werden, bis man wieder durch ./enableServiceMode.sh und OK klicken entsperrt. 

### 1. Abgleich interner Stand mit Kassenbuch:

 - Es gibt zwei Buchhaltungen:
   - Kassenbuch: ernsthafte doppelte Buchführung
   - Bargeld: nach Werten und Speicherorten getrennte Bestandszählung, zu Diagnosezwecken.

 - Bargeld == Kassenbuch?

       ./cash verify

 - Bei Abweichung die beiden Datenquellen vergleichen:

        ./kassenbuch.py summary
        ./cash show

### 2. Zählung/Leerung der Automatenkasse im Servicemodus

 - `./enableServiceMode.sh`

 - in der GUI `Menü->Servicemodus` aktivieren

 - Ausleeren Ja -> der (nicht zugängliche) Speicher des Scheinwechslers wird in die Cashbox umgefüllt.

 - Cashbox des Scheinwechslers entnehmen und zählen 
   - Aktuellen Stand abfragen per: `./cash show`
   - oder auch vergleichen mit gezähltem Stand -> z.B. 3x50€, 1x20€

         ./cash check schein.main /3x50E,1x20E/

 - zum Setzen, falls es nicht passt,
### `./cash set schein.main /4x50E,1x20E/` nachgezählt korrigiert
   - oder zum Addieren (hier äquivalent)
### `./cash add schein.main /1x50E/` nachgezählt korrigiert

 - Münzwechsler Kasse (Plastikbox zur Ausgabe) zählen und vergleichen wie oben
`./cash check muenz.cash /1x1c,7x2E/`

 - Münzwechsler-Röhren (muenz.tubeN) bzw manuell daraus ausgegebene Münzen (muenz.manual) zählen und vergleichen

 - Die Münzwechsler-Röhren kann man entweder von Hand ausschütten, oder halbautomatisch  während des Servicemodus in das Ausgabefach entleeren.
   - Dazu Knopf A-E am Wechsler drücken/halten
   - Dies wird automatisch als Verschiebung (move) von muenz.tubeN nach muenz.manual verbucht, wobei es vorkommen kann dass der Wechsler sich um wenige Münzen verzählt.

 - Alles zählen, die Gesamtzählung muss mit dem Kassenbuchstand übereinstimmen.


### 3. Entnahme von Geld

 - Wenn alles passt, Geld entnehmen und die entnommenen Beträge in das Kassenbuch und die einzelnen Geldkanäle eintragen
z.B.
    `./kassenbuch.py transfer Automatenkasse Lehrstuhl 123.45` zur Einzahlung entnommen
    `./cash add bla.foo /-42x10E/` entnommen

 - Eine Abrechnung per Mail schicken
   TODO (wie bisher)

 - Prüfen dass wieder Bargeld == Kassenbuch:

        ./cash verify


### 4. Wiederbefüllen und Korrigieren der Speicherorte

 - Der Gesamt-Kassenbestand stimmt jetzt zwar, aber nicht unbedingt die Aufteilung auf die Speicherplätze innerhalb des Automats.

 - Die Münzer-Röhren können (zu beliebiger Zeit) von Hand befüllt werden, dies erscheint natürlich nicht im Bargeldlog.
Korrigieren des Orts wird per ./cash move gebucht. Dieses Kommand kann den Gesamtbestand nicht verändern.
Dies damit `./cash move muenz.manual muenz.tubeN /123x50c/` zurückgefüllt

 - Außerdem gibt es den Befüll-Servicemodus:

        ./enableServiceMode.sh

 - GUI: Servicemodus - Ausleeren? `Nein` - Befüllen? `Ja`
 - Jetzt Geld reinwerfen, dieses wird nicht im Kassenbuch verbucht, aber im Bargeldlog.
 - Da das Geld ja irgendwo aus dem Automaten herkam, muss von Hand der Bargeldbestand wieder korrigiert werden.

 - Geldscheinleser: Max. 30 Scheine, möglichst abwechselnd 20-5-10€
 - Geldscheine aus der Cashbox zur Wiederbefüllung entnehmen, Entnahme mit add (negative Anzahl!) verbuchen.
 - `./cash add schein.main /-2x20E,-1x10E/` Entnahme zur Wiederbefuellung
 - Jetzt Geldscheine reinfüttern
 - Prüfen dass Kassenstand wieder stimmt per

        ./cash verify


### 5. Abschließender Check:

    ./cash show

Configuration 
-------------

see config.ini.example

order of devices is important! Payout is in ascending order of the device number. Payin is in parallel.
Sort the devices from large to small denominations. (banknote payout first)

options are:

    deviceN = drivername (valid drivers are currently mdb, nv11, exampleServer)
    deviceN_name = mydevicename123 (choose as you like)
    deviceN_port = /dev/ttyUSBwhatever

or for USB vendorID/productID/serial number, call ./cashPayment/listSerialPorts.py and use one of the output lines e.g.:

    deviceN_port=hwgrep://USB\ VID\:PID\=10c4\:ea60\ SNR\=0001

Cash devices implementation
---------------------------

GUI side: cashPayment.client.PaymentDevicesManager keeps a list of cashPayment.client.PaymentDeviceClient instances.
These call the "server side" (a separate process for each device) and communicate with it via a protocol described in cashPayment/protocol.txt
Server side: cashPayment.server.<drivername> inherits from cashPayment.server.cashServer. See cashPayment.server.exampleServer for a sample implementation.

Troubleshooting
---------------

Logging will be output in cash-<name>.log
If you want to launch a driver without the GUI, look for a line in gui.log like

    starting cashPayment server: PYTHONPATH=.. /usr/bin/env python2.7 -m FabLabKasse.cashPayment.server.mdbCoinChanger KGRwMApWbmFtZQpwMQpWbXVlbnoKcDIKc1Zwb3J0CnAzClZod2dyZXA6Ly9VU0JcdTAwNWMgVklEXHUwMDVjOlBJRFx1MDA1Yz0wNDAzXHUwMDVjOjYwMDFcdTAwNWMgU05SXHUwMDVjPUExMDBRT0YyCnA0CnMu

and run (in FabLabKasse/) the specified command starting with PYTHONPATH=../ 
The argument is a base64 encoded pickled dictionary of the per-deivce options specified in config.ini
You can then communicate with this via stdin/stdout and use commands like POLL, ACCEPT 1234, STOP, DISPENSE 234, STOP according to cashPayment/protocol.txt


MDB
---

Multi-Drop-Bus for coin accept/dispense.
needed interface hardware: https://github.com/fau-fablab/kassenautomat.mdb-interface
specification: http://www.vending.org/images/pdfs/technology/mdb_version_4-2.pdf
PDF page 60 for electrical specs
