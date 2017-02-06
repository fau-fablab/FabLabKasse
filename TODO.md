# TODO

## Needed testing for FAU FabLab

    cp config.ini.example config.ini

edit config.ini:
 - set [backend] backend=legacy_offline_kassenbuch
 - set [openerp] user and password

        ./run.py

- play around, try to crash it
  - schauen ob alles korrekt in kassenbuch.py und cash.py auftaucht
    - Kundenzahlung
    - Bargeldzahlung (automat.)
    - Bargeldzahlung (manuell)

  - dabei jeweils die Fälle:
    - zuwenig eingezahlt
    - Spende (Überzahlung)
    - zuwenig Wechselgeld
    - abgebrochene Zahlung
    - abgebrochene, nicht vollständig wieder rückzahlbare Zahlung


  - Dabei schauen ob
    - dabei keine Cent-Bruchteile irgendwo in der DB landen
    - der Kassenzettel sinnvoll rauskommt # lokaler Server: nc -l -p 4242 | strings


## Showstoppers before going public

 - (not so important) kassenbuch scripts directly in first folder
 - (not so important) no working non-FAU-specific backend [except dummy, which works except for receipt printing]

 - TODO:

        fgrep -r TODO .

 - refactor receipt printing: copy code from kassenbuch and modify it to create a global implementation, change legacy_offline_kassenbuch backend to use global implementation

 - BUGS:
ganz selten Crash (zufallsabhängig?) beim Mülleimer-Button (in Zusammenhang mit Kommentar? oder auch nicht...) -- order_line_id nicht mehr gültig

 - seems to hang (no activity indication) when printing receipt is waiting for timeout
receipt print network timeout is way too high, the printer will be on a LAN!

 - Kundenliste nicht sinnvoll bedienbar bei >10 Kunden (Dropdown Scrollen doof - besser ListWidget + flickcharm)

 - TODO:
cash -> MDB testen, wenn man zwischen dev.poll() mehrere Münzen einwirft [bzw. in Logs nachschauen dass dieser Fall schonmal erfolgreich auftrat]

# NICE TO HAVE

- Make input rounding / min. qty nicer to use (needs some plumbing to work with backends not using AbstractOfflineShoppingBackend.ProductBasedOrderLine internally, because the GUI needs to know the rounding)
- Statistik-Feature (recyclecode from old master branch, leave out barcode reader)
- Mails an Kunden über ihre Einkäufe und Kontostand

-   Interface für "Das Produkt ist aus!" einbauen (z.B. Knopf auf der rechten seite von der Produkte Tabelle)

Features Frontend:
-   Temporäre Produkte unterstützen z.B: "Nachzahlung von ...", "Mitbestellung ..."
-   Mehrere Warenkörbe (z.B. via Tabs)
-   Import von Warenkörben (online, qr code, oder ähnliches)
