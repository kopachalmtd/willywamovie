# PayHero Backend (Flask) for PayHero STK Push and Firestore balance credit

Overview
- Small Flask service to initiate PayHero STK pushes and handle PayHero callbacks.
- Uses Google Firestore Admin SDK to persist payment records and credit balances at:
  artifacts/{APP_ID}/users/{userId}/balances/main

Deploy to Render
1. Create a GitHub repo and push these files (do NOT include service account JSON or .env).
2. On Render create a new Web Service and connect the repo.
3. Add the environment variables in Render Settings (see below).
4. Deploy.

Required environment variables on Render
- FIREBASE_PROJECT_ID (your Google Cloud project id)
- FIREBASE_SERVICE_ACCOUNT_JSON (full service account JSON content)
- PAYHERO_API_USERNAME
- PAYHERO_API_PASSWORD
- PAYHERO_CHANNEL_ID
- PAYHERO_API_BASE (PayHero API base URL)
- PAYHERO_WEBHOOK_SECRET (secret for HMAC verification)
- APP_BASE (optional, public URL for callback construction)
- APP_ID (optional, default payhero-demo-app)
- PORT (optional, default 8000)

Security
- Do not commit secrets to GitHub.
- Use Render environment variables for secrets.
- Rotate keys if they were exposed.

Testing
- POST /payhero/checkout to initiate (returns account_reference).
- POST to {APP_BASE}{PAYHERO_CALLBACK_PATH} to simulate callback (include signature header X-Payhero-Signature if using webhook secret).
