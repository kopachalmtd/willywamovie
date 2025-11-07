#!/usr/bin/env python3
# payhero_server.py
# Purpose: Flask backend to initiate PayHero STK pushes and handle PayHero callbacks.
# Reads PayHero credentials from environment and uses Firestore Admin SDK to persist payments
# and credit user balances at artifacts/{APP_ID}/users/{userId}/balances/main.

import os
import json
import hmac
import hashlib
import uuid
import requests
from flask import Flask, request, jsonify
from google.cloud import firestore
from datetime import datetime, timezone

app = Flask(__name__)

# --- Configuration from environment ---
PAYHERO_API_BASE = os.getenv("PAYHERO_API_BASE", "https://api.payhero.example")
PAYHERO_API_USERNAME = os.getenv("PAYHERO_API_USERNAME")
PAYHERO_API_PASSWORD = os.getenv("PAYHERO_API_PASSWORD")
PAYHERO_CHANNEL_ID = os.getenv("PAYHERO_CHANNEL_ID")

CALLBACK_PATH = os.getenv("PAYHERO_CALLBACK_PATH", "/payhero/callback")
PAYHERO_WEBHOOK_SECRET = os.getenv("PAYHERO_WEBHOOK_SECRET")  # used to verify webhook HMAC
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
APP_ID = os.getenv("APP_ID", "payhero-demo-app")
APP_BASE = os.getenv("APP_BASE", "")  # e.g., https://your-render-service.onrender.com

# Validate minimal required config
if not FIREBASE_PROJECT_ID:
    raise RuntimeError("FIREBASE_PROJECT_ID environment variable is required")

db = firestore.Client(project=FIREBASE_PROJECT_ID)

def make_account_ref(user_id: str) -> str:
    return f"dep-{user_id}-{uuid.uuid4().hex[:12]}"

def verify_webhook_signature(raw_body: bytes, header_signature: str) -> bool:
    if not PAYHERO_WEBHOOK_SECRET:
        # If no secret configured, reject by default for safety
        return False
    computed = hmac.new(PAYHERO_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, (header_signature or "").strip())

@app.route("/payhero/checkout", methods=["POST"])
def checkout():
    payload = request.get_json(force=True, silent=True) or {}
    user_id = payload.get("user_id")
    amount = payload.get("amount")
    phone = payload.get("phone")

    if not (user_id and amount and phone):
        return jsonify({"error": "missing user_id, amount, or phone"}), 400

    try:
        amount_val = float(amount)
        if amount_val <= 0:
            raise ValueError("amount must be > 0")
    except Exception:
        return jsonify({"error": "invalid amount"}), 400

    account_ref = make_account_ref(user_id)
    now = datetime.now(timezone.utc).isoformat()

    payment_doc = {
        "user_id": user_id,
        "amount": amount_val,
        "phone": phone,
        "account_reference": account_ref,
        "status": "pending",
        "provider_request_id": None,
        "provider_payload": None,
        "created_at": now,
        "updated_at": now,
    }

    payment_ref = db.collection("payhero_payments").document(account_ref)
    payment_ref.set(payment_doc)

    # Build callback URL to register with PayHero (use APP_BASE or leave blank and configure in PayHero dashboard)
    if APP_BASE:
        callback_url = APP_BASE.rstrip("/") + CALLBACK_PATH
    else:
        callback_url = os.getenv("PUBLIC_CALLBACK_URL", "")

    # Construct STK push payload adapted for PayHero fields you provided
    stk_payload = {
        "username": PAYHERO_API_USERNAME,
        "password": PAYHERO_API_PASSWORD,
        "channel_id": PAYHERO_CHANNEL_ID,
        "phone": phone,
        "amount": amount_val,
        "account_reference": account_ref,
        "callback_url": callback_url,
        "metadata": {"payment_doc": account_ref}
    }

    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": f"stk-{account_ref}"
    }

    try:
        resp = requests.post(f"{PAYHERO_API_BASE.rstrip('/')}/stkpush", json=stk_payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        # Save error in payment doc for debugging
        payment_ref.update({
            "status": "error",
            "provider_payload": str(exc),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        return jsonify({"error": "failed to initiate STK push"}), 502

    provider_req_id = data.get("request_id") or data.get("id") or None
    payment_ref.update({
        "provider_request_id": provider_req_id,
        "provider_payload": data,
        "updated_at": datetime.now(timezone.utc).isoformat()
    })

    return jsonify({"ok": True, "account_reference": account_ref, "provider": data}), 202

@app.route(CALLBACK_PATH, methods=["POST"])
def callback():
    raw = request.get_data()
    header_sig = request.headers.get("X-Payhero-Signature", "")
    if PAYHERO_WEBHOOK_SECRET:
        if not verify_webhook_signature(raw, header_sig):
            app.logger.warning("Invalid webhook signature")
            return "", 403

    payload = request.get_json(force=True, silent=True) or {}
    # Try common fields; adapt if PayHero has different names
    account_ref = payload.get("account_reference") or payload.get("merchant_ref") or payload.get("metadata", {}).get("payment_doc")
    status = payload.get("status") or payload.get("result") or payload.get("payment_status")
    provider_req_id = payload.get("request_id") or payload.get("id")

    if not account_ref:
        app.logger.warning("Callback missing account_reference or metadata.payment_doc")
        return "", 400

    payment_ref = db.collection("payhero_payments").document(account_ref)
    doc = payment_ref.get()
    if not doc.exists:
        app.logger.warning("Unknown payment callback for %s", account_ref)
        return "", 404

    payment = doc.to_dict()
    if payment.get("status") == "paid":
        return "", 200

    success_indicators = {"success", "paid", "completed"}
    if str(status).lower() in success_indicators:
        def txn_update(txn):
            pdoc = payment_ref.get(transaction=txn)
            if pdoc.exists and pdoc.to_dict().get("status") == "paid":
                return
            txn.update(payment_ref, {
                "status": "paid",
                "provider_request_id": provider_req_id,
                "provider_payload": payload,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "paid_at": datetime.now(timezone.utc).isoformat()
            })
            user_id = pdoc.to_dict().get("user_id")
            bal_ref = db.document(f"artifacts/{APP_ID}/users/{user_id}/balances/main")
            bal_doc = bal_ref.get(transaction=txn)
            current = bal_doc.to_dict().get("amount", 0) if bal_doc.exists else 0
            new_bal = float(current) + float(pdoc.to_dict().get("amount", 0))
            txn.set(bal_ref, {"amount": new_bal, "lastUpdated": datetime.now(timezone.utc).isoformat()}, merge=True)

        db.run_transaction(txn_update)
        app.logger.info("Payment %s marked paid and balance credited", account_ref)
        return "", 200

    # Non-success: record status and provider payload
    payment_ref.update({
        "status": status or "failed",
        "provider_payload": payload,
        "updated_at": datetime.now(timezone.utc).isoformat()
    })
    return "", 200

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
