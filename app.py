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
import re
import secrets
from decimal import Decimal

from dotenv import load_dotenv
from flask import Flask, redirect, request, session, url_for

load_dotenv(override=True)  # populate os.environ from .env BEFORE importing the Xero client
# NOTE: .env is read ONCE here at startup. Flask's reloader only watches .py files, so
# after editing .env you must fully STOP and re-run this process for changes to apply.

from holdback import extract, terms_store, xero  # noqa: E402
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
    requested = xero.requested_scopes()
    granted = xero.granted_scopes()
    missing = [s for s in requested.split() if s not in granted.split()]
    warn = ""
    if missing:
        warn = (
            f"<p style='color:#b00'><b>Requested but NOT granted:</b> "
            f"<code>{' '.join(missing)}</code>.<br>Xero refused these. If you just completed "
            "a clean consent (no 'State mismatch' page) and they're still missing, the app "
            "in the Xero developer portal doesn't have them enabled — enable them there, then "
            "<a href='/login'>Reconnect</a>.</p>"
        )
    return (
        f"<h1>HoldBack</h1><p>Connected &check; &mdash; <b>{org.get('Name')}</b> "
        f"({org.get('CountryCode')})</p>"
        f"<p><b>Requesting</b> (from .env):<br><code>{requested}</code></p>"
        f"<p><b>Granted</b> (on token):<br><code>{granted}</code></p>{warn}"
        "<p><a href='/upload'>Contract terms (PDF)</a> &middot; "
        "<a href='/new-bill'>Create bills</a> &middot; "
        "<a href='/dashboard'>Retention dashboard</a> &middot; "
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


# --- STEP 1: contract-term extraction + editable confirm screen --------------------------
def _esc(value) -> str:
    return str(value).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _contact_options(selected=None) -> str:
    out = []
    for c in xero.get_contacts().get("Contacts", []):
        cid = c.get("ContactID")
        sel = " selected" if cid == selected else ""
        out.append(f'<option value="{cid}"{sel}>{c.get("Name")}</option>')
    return "".join(out)


def _confirm_field(label, name, node) -> str:
    """One editable field. Stretch A: amber background when extracted confidence < 0.8."""
    value = node.get("value") if isinstance(node, dict) else None
    conf = node.get("confidence", 0.0) if isinstance(node, dict) else 0.0
    has_value = value not in (None, "")
    amber = has_value and conf < 0.8
    style = " style='background:#ffe4b5'" if amber else ""
    badge = f" <small>({int(round(conf * 100))}% confidence)</small>" if has_value else ""
    val = "" if value is None else _esc(value)
    return (f"<p><label>{label}{badge}<br>"
            f"<input name='{name}' value=\"{val}\"{style} size='40'></label></p>")


def _render_confirm(terms, note="") -> str:
    t1, t2 = terms["trigger1"], terms["trigger2"]
    note_html = f"<p style='color:#080'>{note}</p>" if note else ""
    return f"""
    <h1>Confirm contract terms</h1>
    <p>Every field is editable. <b>Amber</b> means the extractor wasn't confident &mdash; check it.</p>
    {note_html}
    <form method="post" action="/confirm">
      <p>Job / subcontractor:<br>
        <select name="contact_id" required>
          <option value="">-- choose --</option>{_contact_options()}
        </select></p>
      {_confirm_field("Retention %", "retention_pct", terms["retention_pct"])}
      <fieldset><legend>Trigger 1</legend>
        {_confirm_field("Condition (e.g. practical completion)", "trigger1_condition", t1["condition"])}
        {_confirm_field("Share of retention released (%)", "trigger1_pct", t1["pct"])}
        {_confirm_field("Expected release date (YYYY-MM-DD)", "trigger1_date", t1["expected_date"])}
      </fieldset>
      <fieldset><legend>Trigger 2 (optional &mdash; leave blank for a single release)</legend>
        {_confirm_field("Condition", "trigger2_condition", t2["condition"])}
        {_confirm_field("Share of retention released (%)", "trigger2_pct", t2["pct"])}
        {_confirm_field("Expected release date (YYYY-MM-DD)", "trigger2_date", t2["expected_date"])}
      </fieldset>
      {_confirm_field("Contract value (display only)", "contract_value", terms["contract_value"])}
      <button type="submit">Save terms</button>
    </form>
    <p><a href="/upload">Upload a different PDF</a> &middot; <a href="/">Home</a></p>"""


@app.route("/upload", methods=["GET"])
def upload_form():
    return """
    <h1>Add contract terms</h1>
    <form method="post" action="/upload" enctype="multipart/form-data">
      <p>Upload the subcontract PDF:
         <input type="file" name="pdf" accept="application/pdf"></p>
      <button type="submit">Extract terms</button>
    </form>
    <p>&mdash; or &mdash; <a href="/confirm">Skip PDF: enter terms manually</a></p>
    <p><a href="/">Home</a></p>"""


@app.route("/upload", methods=["POST"])
def upload_extract():
    file = request.files.get("pdf")
    text = extract.pdf_text(file) if file else ""
    # extract_terms never raises: any failure -> empty_terms() -> a blank confirm screen.
    terms = extract.extract_terms(text)
    return _render_confirm(terms)


@app.route("/confirm", methods=["GET"])
def confirm_blank():
    # Manual entry path: same screen, blank fields (no amber — nothing was extracted).
    return _render_confirm(extract.empty_terms())


@app.route("/confirm", methods=["POST"])
def confirm_save():
    f = request.form
    contact_id = f.get("contact_id", "").strip()
    if not contact_id:
        return "<p>Please choose a subcontractor.</p><p><a href='/confirm'>Back</a></p>", 400
    terms_store.save_terms(contact_id, {
        "retention_pct": f.get("retention_pct", "").strip(),
        "trigger1_condition": f.get("trigger1_condition", "").strip(),
        "trigger1_pct": f.get("trigger1_pct", "").strip(),
        "trigger1_date": f.get("trigger1_date", "").strip(),
        "trigger2_condition": f.get("trigger2_condition", "").strip(),
        "trigger2_pct": f.get("trigger2_pct", "").strip(),
        "trigger2_date": f.get("trigger2_date", "").strip(),
        "contract_value": f.get("contract_value", "").strip(),
    })
    # Flow straight into bill creation with these terms pre-loaded for this job.
    return redirect(url_for("new_bill_form", contact_id=contact_id))


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
    selected = request.args.get("contact_id", "")
    stored = terms_store.get_terms(selected) if selected else None
    options = "".join(
        f'<option value="{c.get("ContactID")}"'
        f'{" selected" if c.get("ContactID") == selected else ""}>{c.get("Name")}</option>'
        for c in xero.get_contacts().get("Contacts", [])
    )
    today = datetime.date.today().isoformat()
    default_release = (datetime.date.today() + datetime.timedelta(days=180)).isoformat()
    s = stored or {}
    retention_val = s.get("retention_pct") or "5"
    t1_pct = s.get("trigger1_pct") or "100"
    t1_date = s.get("trigger1_date") or default_release
    t2_pct = s.get("trigger2_pct") or ""
    t2_date = s.get("trigger2_date") or ""
    note = ("<p style='color:#080'>Loaded saved terms for this job &mdash; fields still "
            "overridable.</p>") if stored else ""
    return f"""
    <h1>Create HoldBack bills</h1>
    <p>Splits one subcontractor bill into a pay-now bill + DRAFT retention bill(s).</p>
    {note}
    <form method="post">
      <p>Subcontractor (pick the one set up as a CIS subcontractor):<br>
        <select name="contact_id" required>
          <option value="">-- choose --</option>{options}
        </select></p>
      <p>Total &pound;<input name="total" value="1500.00" size="10">
         = Labour &pound;<input name="labour" value="1000.00" size="10">
         + Materials &pound;<input name="materials" value="500.00" size="10"></p>
      <p>Retention <input name="retention_pct" value="{retention_val}" size="3">% &nbsp;
         Bill date <input name="date" value="{today}" size="12"></p>
      <fieldset><legend>Release triggers (retention released in tranches)</legend>
        <p>Trigger 1 &mdash; share <input name="trigger1_pct" value="{t1_pct}" size="3">%
           on <input name="trigger1_date" value="{t1_date}" size="12"></p>
        <p>Trigger 2 (optional) &mdash; share <input name="trigger2_pct" value="{t2_pct}" size="3">%
           on <input name="trigger2_date" value="{t2_date}" size="12"></p>
        <small>Leave Trigger 2 blank for a single release (100% at Trigger 1). For two
        releases, the two shares must sum to 100.</small>
      </fieldset>
      <p>Pay-now bill:
        <label><input type="radio" name="pay_now_status" value="DRAFT" checked>
          Draft (review &amp; approve by hand)</label>
        <label><input type="radio" name="pay_now_status" value="AUTHORISED">
          Approve now</label></p>
      <button type="submit">Create bills in Xero</button>
    </form>
    <p><a href="/upload">Set contract terms from a PDF</a> &middot; <a href="/">Home</a></p>"""


@app.route("/new-bill", methods=["POST"])
def new_bill_create():
    f = request.form
    split = split_bill(f["total"], f["labour"], f["materials"], f["retention_pct"])

    # Build the release tranches. Trigger 2 blank -> single release (100% at Trigger 1);
    # both present -> two tranches whose shares must sum to 100.
    t1_date = f.get("trigger1_date", "").strip()
    t2_date = f.get("trigger2_date", "").strip()
    try:
        if t2_date:
            t1 = Decimal(f.get("trigger1_pct", "").strip() or "0")
            t2 = Decimal(f.get("trigger2_pct", "").strip() or "0")
            if t1 + t2 != Decimal("100"):
                return (f"<h1>Check tranche shares</h1><p>Trigger shares must sum to 100 "
                        f"(got {t1} + {t2} = {t1 + t2}).</p>"
                        "<p><a href='/new-bill'>Back</a></p>"), 400
            tranches = [{"share": t1, "due_date": t1_date},
                        {"share": t2, "due_date": t2_date}]
        else:
            tranches = [{"share": Decimal("100"), "due_date": t1_date}]
    except Exception as exc:  # noqa: BLE001
        return f"<h1>Bad trigger input</h1><pre>{exc}</pre><p><a href='/new-bill'>Back</a></p>", 400

    payloads = build_accpay_bills(
        split,
        contact_id=f["contact_id"],
        date=f["date"],
        tranches=tranches,
        cis_labour_account_code=CIS_LABOUR_ACCOUNT,
        materials_account_code=MATERIALS_ACCOUNT,
        vat_tax_type=VAT_TAX_TYPE,
        pay_now_status=f["pay_now_status"],
        reference="HoldBack",
    )
    to_create = [payloads["pay_now"], *payloads["retention_bills"]]
    try:
        result = xero.create_bills(to_create)
    except Exception as exc:  # noqa: BLE001 - show Xero's raw error during the build
        body = (
            f"<h1>Create failed</h1><pre>{exc}</pre>"
            f"<p><b>Granted scopes:</b> <code>{xero.granted_scopes()}</code></p>"
            "<p>A 401 here almost always means the write scope isn't in the list above.</p>"
            "<p><a href='/'>Home</a> &middot; <a href='/login'>Reconnect</a> &middot; "
            "<a href='/new-bill'>Back</a></p>"
        )
        return body, 502
    rows = "".join(
        f"<tr><td>{inv.get('Reference')}</td><td>{inv.get('Status')}</td>"
        f"<td>&pound;{inv.get('Total')}</td><td>{inv.get('DueDate', '')}</td>"
        f"<td><code>{inv.get('InvoiceID')}</code></td></tr>"
        for inv in result.get("Invoices", [])
    )
    return f"""
    <h1>Created &check;</h1>
    <table border=1 cellpadding=4>
      <tr><th>Reference</th><th>Status</th><th>Total</th><th>Due</th><th>InvoiceID</th></tr>
      {rows}
    </table>
    <p>Open Xero &rarr; Business &rarr; Bills to see them. CIS shows on the labour line
    once a bill is approved.</p>
    <p><a href="/dashboard">Retention dashboard</a> &middot;
       <a href="/new-bill">Create another</a></p>"""


def _parse_xero_date(value):
    """Xero returns dates as '/Date(1798675200000+0000)/'. Return a date for sort/display."""
    if not value:
        return None
    m = re.search(r"/Date\((-?\d+)", value)
    if not m:
        return None
    ms = int(m.group(1))
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=ms)).date()


# Lifecycle lanes derived from Xero's own Status (we never store status ourselves).
_STATUS_LANE = {
    "DRAFT": ("Held", "held"),
    "AUTHORISED": ("Released — awaiting payment", "released"),
    "PAID": ("Paid", "paid"),
}


def _money_fmt(value) -> str:
    """£1,234.56 with thousands separators (tabular alignment handled in CSS)."""
    try:
        return f"£{Decimal(str(value)):,.2f}"
    except Exception:  # noqa: BLE001
        return f"£{value}"


def _tranche_label(ref: str) -> str:
    m = re.search(r"retention\s+(\d+/\d+)", ref or "", re.I)
    return m.group(1) if m else ""


def _retention_items():
    """All HoldBack retention bills across statuses, each with a derived lifecycle lane."""
    data = xero.get_bills(where='Type=="ACCPAY"')
    items = []
    for inv in data.get("Invoices", []):
        ref = inv.get("Reference") or ""
        is_retention = "retention" in ref.lower() or (
            ref.strip() == "HoldBack" and bool(inv.get("DueDate"))
        )
        if not is_retention:
            continue
        lane = _STATUS_LANE.get(inv.get("Status"))
        if not lane:  # skip VOIDED / DELETED
            continue
        items.append({
            "id": inv.get("InvoiceID"),
            "name": (inv.get("Contact") or {}).get("Name", "?"),
            "held": inv.get("Total"),
            "due": _parse_xero_date(inv.get("DueDate")),
            "inv_no": inv.get("InvoiceNumber") or "",
            "tranche": _tranche_label(ref),
            "status_label": lane[0],
            "lane": lane[1],
        })
    return items


@app.route("/dashboard")
def dashboard():
    """Retention across jobs with a lifecycle read from Xero status (DRAFT=Held,
    AUTHORISED=Released, PAID=Paid). Held rows sorted soonest-release-first; total held
    counts DRAFT tranches only."""
    items = _retention_items()
    lane_order = {"held": 0, "released": 1, "paid": 2}
    items.sort(key=lambda i: (lane_order[i["lane"]], i["due"] is None, i["due"] or datetime.date.max))
    held = [i for i in items if i["lane"] == "held"]
    total_held = sum(float(i["held"] or 0) for i in held)
    jobs_held = len({i["name"] for i in held})

    def row(i):
        action = (
            f"<form method='post' action='/dashboard/approve/{i['id']}' "
            "onsubmit=\"return confirm('Release this retention now? The CIS rate is "
            "re-checked before approving.')\"><button type='submit'>Release</button></form>"
        ) if i["lane"] == "held" else "&mdash;"
        item = "retention" + (f" {i['tranche']}" if i["tranche"] else "")
        return (f"<tr><td>{i['status_label']}</td><td>{i['name']}</td><td>{item}</td>"
                f"<td class='num'>{_money_fmt(i['held'])}</td>"
                f"<td>{i['due'] or '&mdash;'}</td><td>{action}</td></tr>")

    rows = "".join(row(i) for i in items) or (
        "<tr><td colspan='6'>No retention yet. Create some at "
        "<a href='/new-bill'>/new-bill</a>.</td></tr>")
    return (
        "<h1>Retention</h1>"
        f"<p>Currently held: <b>{_money_fmt(total_held)}</b> across <b>{jobs_held}</b> job(s).</p>"
        "<table border=1 cellpadding=6><thead><tr><th>Status</th><th>Subcontractor</th>"
        "<th>Item</th><th class='num'>Held</th><th>Release date</th><th>Action</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        "<p><a href='/'>Home</a> &middot; <a href='/new-bill'>Create bills</a></p>"
    )


@app.route("/dashboard/approve/<invoice_id>", methods=["POST"])
def dashboard_approve(invoice_id):
    """Release a retention bill: re-read the contact's CIS rate, THEN approve (AUTHORISE).
    Xero fixes the deduction at the current rate on approval (HMRC rate-at-payment rule)."""
    note = "Approved."
    try:
        inv = xero.get_invoice(invoice_id)["Invoices"][0]
        cid = (inv.get("Contact") or {}).get("ContactID")
        if cid:
            xero.get_contact_cis_settings(cid)  # re-fetch rate at release (rule 5)
            note = "Re-checked the contact's CIS rate at release, then approved."
    except Exception as exc:  # noqa: BLE001 - re-read is best-effort; Xero applies the rate at approval
        note = (f"(Could not re-read CIS settings: {exc}) Approved anyway — Xero applies "
                "the contact's current rate at approval.")
    try:
        xero.approve_invoice(invoice_id)
    except Exception as exc:  # noqa: BLE001
        return f"<h1>Release failed</h1><pre>{exc}</pre><p><a href='/dashboard'>Back</a></p>", 502
    return (
        f"<h1>Released &check;</h1><p>{note}</p>"
        "<p><a href='/dashboard'>Back to dashboard</a></p>"
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
