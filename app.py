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

import datetime
import json
import os
import secrets

from dotenv import load_dotenv
from flask import Flask, redirect, request, session, url_for

load_dotenv(override=True)  # populate os.environ from .env BEFORE importing the Xero client
# NOTE: .env is read ONCE here at startup. Flask's reloader only watches .py files, so
# after editing .env you must fully STOP and re-run this process for changes to apply.

from holdback import xero  # noqa: E402
from holdback.bills import build_accpay_bills  # noqa: E402
from holdback.split_engine import split_bill  # noqa: E402

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
    except Exception as exc:  # noqa: BLE001 - surface the raw error during the build
        return (
            f"<h1>HoldBack</h1><p>Connected, but the API call failed:</p>"
            f"<pre>{exc}</pre><p><a href='/login'>Reconnect</a></p>"
        )
    scopes = xero.granted_scopes()
    write_ok = "accounting.invoices" in scopes
    warn = "" if write_ok else (
        "<p style='color:#b00'><b>No write permission yet.</b> 'accounting.invoices' is "
        "missing from your granted scopes, so creating a bill will 401. Fix: ensure .env "
        "has it, fully restart the app, then <a href='/login'>Reconnect to Xero</a> and "
        "approve the new permission.</p>"
    )
    return (
        f"<h1>HoldBack</h1><p>Connected &check; &mdash; <b>{org.get('Name')}</b> "
        f"({org.get('CountryCode')})</p>"
        f"<p>Granted scopes:<br><code>{scopes}</code></p>{warn}"
        "<p><a href='/new-bill'>Create bills</a> &middot; "
        "<a href='/contacts'>Contacts</a> &middot; "
        "<a href='/accounts'>Accounts</a> &middot; "
        "<a href='/login'>Reconnect (re-authorise scopes)</a></p>"
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


# --- WRITE PATH — runs ONLY on explicit form submit; needs the accounting.invoices scope --
# These come from the Demo Company (UK) chart of accounts / tax rates:
#   321 "CIS Labour Expense"      -> Xero applies the CIS deduction to labour coded here
#   322 "CIS Materials Purchased" -> materials, excluded from the CIS deduction
#   INPUT2 = "20% (VAT on Expenses)"
CIS_LABOUR_ACCOUNT = "321"
MATERIALS_ACCOUNT = "322"
VAT_TAX_TYPE = "INPUT2"


@app.route("/new-bill", methods=["GET"])
def new_bill_form():
    options = "".join(
        f'<option value="{c.get("ContactID")}">{c.get("Name")}</option>'
        for c in xero.get_contacts().get("Contacts", [])
    )
    today = datetime.date.today().isoformat()
    release = (datetime.date.today() + datetime.timedelta(days=180)).isoformat()
    return f"""
    <h1>Create HoldBack bills</h1>
    <p>Splits one subcontractor bill into a pay-now bill + a DRAFT retention bill.</p>
    <form method="post">
      <p>Subcontractor (pick the one set up as a CIS subcontractor):<br>
        <select name="contact_id" required>
          <option value="">-- choose --</option>{options}
        </select></p>
      <p>Total &pound;<input name="total" value="1500.00" size="10">
         = Labour &pound;<input name="labour" value="1000.00" size="10">
         + Materials &pound;<input name="materials" value="500.00" size="10"></p>
      <p>Retention <input name="retention_pct" value="5" size="3">%</p>
      <p>Bill date <input name="date" value="{today}" size="12">
         &nbsp; Retention release date <input name="retention_due_date" value="{release}" size="12"></p>
      <p>Pay-now bill:
        <label><input type="radio" name="pay_now_status" value="DRAFT" checked>
          Draft (review &amp; approve by hand)</label>
        <label><input type="radio" name="pay_now_status" value="AUTHORISED">
          Approve now</label></p>
      <button type="submit">Create bills in Xero</button>
    </form>"""


@app.route("/new-bill", methods=["POST"])
def new_bill_create():
    f = request.form
    split = split_bill(f["total"], f["labour"], f["materials"], f["retention_pct"])
    payloads = build_accpay_bills(
        split,
        contact_id=f["contact_id"],
        date=f["date"],
        retention_due_date=f["retention_due_date"],
        cis_labour_account_code=CIS_LABOUR_ACCOUNT,
        materials_account_code=MATERIALS_ACCOUNT,
        vat_tax_type=VAT_TAX_TYPE,
        pay_now_status=f["pay_now_status"],
        reference="HoldBack",
    )
    to_create = [payloads["pay_now"]]
    if payloads["retention"]:
        to_create.append(payloads["retention"])
    try:
        result = xero.create_bills(to_create)
    except Exception as exc:  # noqa: BLE001 - show Xero's raw validation error during the build
        return f"<h1>Create failed</h1><pre>{exc}</pre><p><a href='/new-bill'>Back</a></p>", 502
    rows = "".join(
        f"<tr><td>{inv.get('Type')}</td><td>{inv.get('InvoiceNumber')}</td>"
        f"<td>{inv.get('Status')}</td><td>{inv.get('Total')}</td>"
        f"<td>{inv.get('DueDate', '')}</td><td><code>{inv.get('InvoiceID')}</code></td></tr>"
        for inv in result.get("Invoices", [])
    )
    return f"""
    <h1>Created &check;</h1>
    <table border=1 cellpadding=4>
      <tr><th>Type</th><th>No.</th><th>Status</th><th>Total</th><th>Due</th><th>InvoiceID</th></tr>
      {rows}
    </table>
    <p>Open Xero &rarr; Business &rarr; Bills to see them. The CIS deduction shows on the
    labour line once the pay-now bill is approved.</p>
    <p><a href="/new-bill">Create another</a></p>"""


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
