# Loading carts via app

You can use the HTML-based simulator as a replacement for FabLabKasse and also as a reference implementation:
my-server.com/checkoutDummy/

Generate random number (12345), show as a QR code to the user

User opens cart in app and pushes "send to cashdesk"

cashdesk polls for a cart:

HTTP GET server/checkout/cart/12345

-> If a cart was sent, the response is a JSON object containing the cart

ask for payment, process payment


When finished or aborted, send back the status to the server to notify the application:

success: HTTP POST server/checkout/paid/12345
aborted: HTTP POST server/checkout/canceled/12345