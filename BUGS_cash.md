

 - wish: ask *before* the end of CashPaymentDialog whether the user wants a receipt


# Error and crash reporting

 - wish: more immediate reporting of warnings and errors by mail

 - a crashing cashDevice kills the whole GUI, even if the user wants to use another payment method

 - wish: do something (better than the daily logwatch mail) so that a crash during cash payment is noticed automatically
(currently, at least start/stop is logged to cash DB and gui.log)

 - Crashes at the very beginning of starting a cash payment device, like crashes before setting up logging or missing imports
are not reported nicely. The log just tells to run the commandline yourself and see what happens, it should rather give the last n lines of STDERR.

 - Nonexistent cash payment drivers should cause a clear and early error message.




# firmware-related bugs:

 - WORKAROUND-fixed cashPayment/server/mdb.py (search there for "BUG"): the device may send BUSY even while we are not doing payout/payin, and then CashServer raises an Exception. Now this busy flag is filtered out in idle state. Problems may only arise when service operations are performed during payin/payout operations.

 - WORKAROUND-fixed NV11: very seldom POLL_WITH_ACK replies with the previous "note dispensed" 0xD2 event again, although ACK was sent. I suspect this is a firmware bug and not our fault. Full logging has been re-enabled and we now use POLL instead of POLL_WITH_ACK. No loss of functionality or reliability, except for rare edge-cases during startup, is expected from this because the lower layer also does retransmissions.
