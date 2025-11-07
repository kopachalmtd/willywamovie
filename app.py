import os
import logging
from dotenv import load_dotenv
from flask import Flask, request, render_template, jsonify, url_for
import requests
from urllib.parse import urljoin

# Load local .env for development only; Render will provide env vars
load_dotenv()

# Basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Config
PAYHERO_API_URL = os.getenv("PAYHERO_API_URL", "https://payhero.co.ke/api/stkpush")
PAYHERO_USERNAME = os.getenv("PAYHERO_USERNAME")
PAYHERO_PASSWORD = os.getenv("PAYHERO_PASSWORD")
PAYHERO_CHANNEL_ID = os.getenv("PAYHERO_CHANNEL_ID")
FLASK_SECRET = os.getenv("FLASK_SECRET", "dev-secret")

app = Flask(__name__)
app.config["SECRET_KEY"] = FLASK_SECRET


def canonicalize_phone(raw: str) -> str:
    p = raw.strip()
    # quick canonicalization: allow 07... or +2547... or 2547...
    if p.startswith("+"):
        p = p[1:]
    if p.startswith("07") and len(p) == 10:
        return "254" + p[1:]
    if p.startswith("7") and len(p) == 9:
        return "254" + p
    return p


def credentials_ok() -> bool:
    return all([PAYHERO_USERNAME, PAYHERO_PASSWORD, PAYHERO_CHANNEL_ID])


@app.route("/", methods=["GET"])
def home():
    return render_template("deposit_form.html")


@app.route("/deposit", methods=["POST"])
def deposit():
    if not credentials_ok():
        logger.error("Missing PayHero credentials in environment")
        return jsonify({"error": "server misconfiguration: missing credentials"}), 500

    phone_raw = request.form.get("phone", "").strip()
    amount_raw = request.form.get("amount", "").strip()
    reference = request.form.get("reference", "Deposit via Flask")

    if not phone_raw or not amount_raw:
        return jsonify({"error": "phone and amount are required"}), 400

    try:
        amount = float(amount_raw)
        if amount <= 0:
            raise ValueError("amount must be > 0")
    except Exception as e:
        return jsonify({"error": "invalid amount", "detail": str(e)}), 400

    phone = canonicalize_phone(phone_raw)

    payload = {
        "username": PAYHERO_USERNAME,
        "password": PAYHERO_PASSWORD,
        "channel": PAYHERO_CHANNEL_ID,
        "phone": phone,
        "amount": int(amount),  # PayHero may expect integer amounts
        "reference": reference,
    }

    # Log payload without sensitive fields
    safe_payload = {k: v for k, v in payload.items() if k != "password"}
    logger.info("Sending STKPush payload: %s", safe_payload)

    try:
        resp = requests.post(PAYHERO_API_URL, json=payload, timeout=15, allow_redirects=False)
    except requests.RequestException as e:
        logger.exception("HTTP request failed")
        return jsonify({"error": "request_failed", "detail": str(e)}), 502

    logger.info("PayHero status: %s", resp.status_code)
    logger.info("PayHero content-type: %s", resp.headers.get("Content-Type"))
    body_snippet = resp.text[:2000]
    logger.debug("PayHero body (snippet): %s", body_snippet)

    # If PayHero returns HTML or a redirect to docs, include snippet for debugging
    content_type = resp.headers.get("Content-Type", "")
    if resp.status_code >= 400 or "text/html" in content_type:
        return jsonify({
            "status_code": resp.status_code,
            "content_type": content_type,
            "body_snippet": body_snippet
        }), 502

    # Return their JSON if available, otherwise raw text
    try:
        return jsonify(resp.json()), resp.status_code
    except ValueError:
        return resp.text, resp.status_code


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not_found", "path": request.path}), 404


if __name__ == "__main__":
    # For local dev only
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=os.getenv("FLASK_DEBUG", "0") == "1")
