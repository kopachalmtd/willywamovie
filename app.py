import os
from dotenv import load_dotenv
import requests
from flask import Flask, request, render_template_string

load_dotenv()

app = Flask(__name__)

PAYHERO_USERNAME = os.getenv("PAYHERO_USERNAME")
PAYHERO_PASSWORD = os.getenv("PAYHERO_PASSWORD")
CHANNEL_ID = os.getenv("PAYHERO_CHANNEL_ID")

@app.route('/')
def home():
    return render_template_string(open("templates/deposit_form.html").read())

@app.route('/deposit', methods=['POST'])
def deposit():
    phone = request.form['phone']
    amount = request.form['amount']

    payload = {
        "username": PAYHERO_USERNAME,
        "password": PAYHERO_PASSWORD,
        "channel": CHANNEL_ID,
        "phone": phone,
        "amount": amount,
        "reference": "Deposit via Flask"
    }

    response = requests.post("https://payhero.co.ke/api/stkpush", json=payload)
    return f"Response: {response.text}"
