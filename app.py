import os
import logging
from dotenv import load_dotenv
import requests
from flask import Flask, request, render_template_string, jsonify

load_dotenv()  # ok for local; Render uses real env vars

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

PAYHERO_USERNAME = os.getenv("PAYHERO_USERNAME")
PAYHERO_PASSWORD = os.getenv("PAYHERO_PASSWORD")
CHANNEL_ID = os.getenv("PAYHERO_CHANNEL_ID")
API_URL = "https://payhero.co.ke/api/stkpush"

@app.route('/deposit', methods=['POST'])
def deposit():
    phone = request.form.get('phone', '').strip()
    amount = request.form.get('amount', '').strip()

    payload = {
        "username": PAYHERO_USERNAME,
        "password": PAYHERO_PASSWORD,
        "channel": CHANNEL_ID,
        "phone": phone,
        "amount": amount,
        "reference": "Deposit via Flask"
    }

    logging.info("Payload to PayHero: %s", {k:v for k,v in payload.items() if k not in ("password",)})
    try:
        resp = requests.post(API_URL, json=payload, timeout=15, allow_redirects=False)
    except Exception as e:
        logging.exception("HTTP request to PayHero failed")
        return jsonify({"error": "request failed", "detail": str(e)}), 500

    logging.info("PayHero status: %s", resp.status_code)
    logging.info("PayHero headers: %s", resp.headers)
    logging.info("PayHero body (first 1000 chars): %s", resp.text[:1000])

    # If PayHero sent HTML (documentation) you'll see it in resp.text here
    if resp.status_code >= 400 or 'text/html' in resp.headers.get('Content-Type',''):
        return jsonify({
            "status_code": resp.status_code,
            "content_type": resp.headers.get('Content-Type'),
            "body_snippet": resp.text[:1000]
        }), 502

    # otherwise return their JSON to the client
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return resp.text, resp.status_code
