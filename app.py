"""
HoldBack — Flask OAuth server + read-only smoke test ("OAuth OK" milestone).

Run:
    pip install -r requirements.txt
    # set XERO_CLIENT_SECRET in .env first (generate it at developer.xero.com)
    python app.py
    # open http://localhost:5000  and click "Connect to Xero"

⚠️  REMINDER (CLAUDE.md rule 1): this app performs Xero READS only. No bill is written
until the numbers are confirmed ("NUMBERS CONFIRMED") and the write module is built.
"""

import json
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, redirect, request, session, url_for

load_dotenv(override=True)  # populate os.environ from .env BEFORE importing the Xero client
# NOTE: .env is read ONCE here at startup. Flask's reloader only watches .py files, so
# after editing .env you must fully STOP and re-run this process for changes to apply.

from holdback import xero  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-only-change-me")


@app.route("/")
def index():
    if not xero.is_connected():
        return (
            "<h1>HoldBack</h1><p>Not connected to Xero.</p>"
            '<p><a href="/login">Connect to Xero</a></p>'
        )
    try:
        org = xero.get_organisation()["Organisations"][0]
        return (
            f"<h1>HoldBack</h1><p>Connected ✓ &mdash; organisation: "
            f"<b>{org.get('Name')}</b> ({org.get('CountryCode')})</p>"
            '<p><a href="/contacts">List contacts &rarr; inspect CIS settings</a></p>'
        )
    except Exception as exc:  # noqa: BLE001 - surface the raw error during the build
        return (
            f"<h1>HoldBack</h1><p>Connected, but the API call failed:</p>"
            f"<pre>{exc}</pre><p><a href='/login'>Reconnect</a></p>"
        )


@app.route("/login")
def login():
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    return redirect(xero.build_authorize_url(state))


@app.route("/callback")
def callback():
    # CSRF guard: the state we sent must come back unchanged.
    if request.args.get("state") != session.get("oauth_state"):
        return "State mismatch — possible CSRF. Start again at /login.", 400
    if request.args.get("error"):
        return f"Xero returned an error: {request.args.get('error')}", 400
    xero.exchange_code(request.args["code"])
    return redirect(url_for("index"))


@app.route("/contacts")
def contacts():
    """Helper to find a ContactID so we can inspect the live CISSettings field names."""
    rows = "".join(
        f'<li>{c.get("Name")} &mdash; <code>{c.get("ContactID")}</code> '
        f'&mdash; <a href="/cis/{c.get("ContactID")}">CIS settings</a></li>'
        for c in xero.get_contacts().get("Contacts", [])
    )
    return f"<h1>Contacts</h1><ul>{rows}</ul>"


@app.route("/cis/<contact_id>")
def cis(contact_id):
    """Echo raw CISSettings JSON so we can confirm exact field names before using them."""
    data = xero.get_contact_cis_settings(contact_id)
    return f"<h1>CISSettings</h1><pre>{json.dumps(data, indent=2)}</pre>"


@app.route("/accounts")
def accounts():
    """Find the CIS Labour Expense + materials account codes to use on bill lines."""
    rows = "".join(
        f"<tr><td><code>{a.get('Code')}</code></td><td>{a.get('Name')}</td>"
        f"<td>{a.get('Type')}</td><td>{a.get('TaxType')}</td></tr>"
        for a in xero.get_accounts().get("Accounts", [])
    )
    return (
        "<h1>Accounts</h1><table border=1 cellpadding=4>"
        "<tr><th>Code</th><th>Name</th><th>Type</th><th>TaxType</th></tr>"
        f"{rows}</table>"
    )


@app.route("/taxrates")
def taxrates():
    """Find the exact 20% VAT-on-expenses TaxType string for bill lines."""
    rows = "".join(
        f"<tr><td>{t.get('Name')}</td><td><code>{t.get('TaxType')}</code></td>"
        f"<td>{t.get('EffectiveRate')}</td><td>{t.get('Status')}</td></tr>"
        for t in xero.get_tax_rates().get("TaxRates", [])
    )
    return (
        "<h1>Tax rates</h1><table border=1 cellpadding=4>"
        "<tr><th>Name</th><th>TaxType</th><th>Rate</th><th>Status</th></tr>"
        f"{rows}</table>"
    )


if __name__ == "__main__":
    # Fail loud at boot, not deep inside /callback, if the secret didn't load.
    if not os.environ.get("XERO_CLIENT_SECRET"):
        print(
            "\n[!] XERO_CLIENT_SECRET is empty in the environment. Put it in .env and "
            "restart this process (editing .env does NOT hot-reload).\n"
        )
    else:
        print("[ok] XERO_CLIENT_SECRET loaded.")
    # Port 5000 to match the registered redirect URI http://localhost:5000/callback.
    app.run(host="localhost", port=5000, debug=True)
