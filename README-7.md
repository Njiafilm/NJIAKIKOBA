# NJIAKIKOBA

Professional Flask starter for the NJIAKIKOBA savings/loans platform.

## Folder structure (must match exactly — case-sensitive)
```
app.py
requirements.txt
.env.example
templates/
  ├── index.html
  ├── login.html
  ├── register.html
  ├── register_leaders.html
  ├── dashboard.html
  ├── developer_login.html
  └── developer_dashboard.html
static/
  ├── style.css
  └── assets/
      ├── njiakikoba-hero.png
      ├── njiakikoba-mobile.jpg
      └── njiakikoba-ui-showcase.png
```
Flask requires the folders to be named exactly `templates` and `static` (lowercase, `templates` with an "s"). On Linux-based hosts (Render, etc.) folder names are case-sensitive — `template`, `Templates`, `Static`, etc. will cause `jinja2.exceptions.TemplateNotFound` or missing CSS/images.

## Run locally
1. Create a virtual environment.
2. Install `requirements.txt`.
3. Set the environment variables in `.env.example`.
4. Run `python app.py`.

## Deploy on Render
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app`
- Set all variables from `.env.example` under Render → Environment.

## Important payment rule
`/api/payment/create` creates a **pending** transaction only. A real payment provider webhook must confirm the transaction before member balances are changed. Do not claim that money has been transferred until the provider confirms it.

## Developer Room
There is no public navigation link to the Developer Room. Its route is intentionally separate and protected by a developer session. Keep all payout credentials in server-side environment variables or a secrets manager.

## Brand assets
The supplied NJIAKIKOBA images are stored under `static/assets/`.

## Real payments
This version removes the fake `pending` creation-only flow and integrates the server-side BLMPay API:
- Member payment request uses `POST /api/v1/payments` with mobile-money USSD push.
- The signed `payment.completed` webhook is the source of truth before member balances are updated.
- 2% operating fee is calculated server-side.
- The 2% operating fee can be paid to the secret `DEVELOPER_PAYOUT_ACCOUNT`.
- The 98% group amount can be paid to the secret `GROUP_SETTLEMENT_PHONE`.
- Idempotency keys prevent accidental duplicate payment/payout attempts.
- Provider secrets and payout numbers never appear in public HTML/JavaScript.

**Production requirement:** obtain a BLMPay production API key with the required `collection:create` and `disbursement:create` scopes, register the HTTPS webhook, and configure the server secrets. The code deliberately refuses to fake a successful payment when credentials are missing.


## Siri za malipo
- Namba ya Developer imewekwa kama `DEVELOPER_LIPA_NUMBER` kwenye server environment tu; haijawekwa kwenye public HTML/JavaScript wala `.env.example`.
- Mwanachama hujaza namba yake mwenyewe ya malipo na mtandao wakati wa kufungua akaunti, na anaweza kuibadilisha kwenye Dashboard.
- Malipo yanatumwa kwa namba ya mwanachama kupitia BLMPay; uthibitisho wa mwisho unatoka kwenye signed webhook.
- 2% ya operating fee inahesabiwa server-side.
- Muhimu: BLMPay API iliyopo kwa sasa inaonyesha payout kwa `recipient_phone`, bank account au Selcom Pesa, si kutuma moja kwa moja kwenda Lipa Namba. Kwa hiyo hatujadanganya mfumo kuwa 2% imetumwa kwa 168603063. Ili 2% itulizwe moja kwa moja kwenye Lipa Namba 168603063, tunahitaji API/merchant settlement ya Mixx/Tigo au provider anayeunga mkono Lipa Namba settlement.
