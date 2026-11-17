CRAFTORIA.LOVE - STARTER E-COMMERCE WEBSITE
===========================================

1. Open this folder in Visual Studio Code.
2. Open Terminal > New Terminal.
3. Run these commands in PowerShell:

   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   python app.py

4. Open http://127.0.0.1:5000 in Chrome.

MANAGER LOGIN (LOCAL TESTING ONLY)
Manager ID: admin
Password: Craftoria@123

IMPORTANT BEFORE PUBLIC LAUNCH
- Change SECRET_KEY, MANAGER_ID and MANAGER_PASSWORD using hosting environment variables.
- The default manager password is for local testing only.
- This starter uses SQLite. Many free hosting services have temporary filesystems;
  the SQLite database may be lost on redeploy/restart. Use a managed persistent database
  (for example PostgreSQL) before accepting real customer orders.
- Checkout currently records an order for offline/Cash-on-Delivery arrangement.
  No online payment gateway is connected.
- Add privacy policy, terms, shipping/return policy and customer support details before launch.
- Use product images you own or have permission to use.
