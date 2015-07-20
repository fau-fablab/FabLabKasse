``cart_from_app`` - Loading carts via smartphone app
====================================================================

This module supports using your smartphone to enter (or scan) which products you would like to pay and transfer the cart (list of products and amounts) to the terminal.

The smartphone app https://github.com/FAU-Inf2/fablab-android has a java-based backend server https://github.com/FAU-Inf2/fablab-server which is used for communication by both the smartphone and the terminal.

You can use the HTML-based simulator as a replacement for FabLabKasse and also as a reference implementation:
    ``my-server.com/checkoutDummy/``

Workflow
--------
    
 - Generate random number (12345), show as a QR code to the user
    (this is to guard against DOS or collisions with other people also sending a cart at the same time)

 - User has his cart in the app, and pushes "send to cashdesk", scans code
 
 - app sends cart to server, authenticating with the random number

 - cashdesk polls for a cart:

    ``HTTP GET server/checkout/cart/12345``

   - -> If a cart was sent, the response is a JSON object containing the cart

 - ask for payment, process payment


 - When finished or aborted, send back the status to the server to notify the application:

   - success: ``HTTP POST server/checkout/paid/12345``
   - aborted: ``HTTP POST server/checkout/canceled/12345``

FabLabKasse.shopping.cart_from_app.cart_gui module
--------------------------------------------------

.. automodule:: FabLabKasse.shopping.cart_from_app.cart_gui
    :members:
    :undoc-members:
    :show-inheritance:

FabLabKasse.shopping.cart_from_app.cart_model module
----------------------------------------------------

.. automodule:: FabLabKasse.shopping.cart_from_app.cart_model
    :members:
    :undoc-members:
    :show-inheritance:


Module contents
---------------

.. automodule:: FabLabKasse.shopping.cart_from_app
    :members:
    :undoc-members:
    :show-inheritance:
