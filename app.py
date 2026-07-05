"""
HoldBack. Flask app for UK construction CIS retention on Xero.

Home is the New bill entry (upload a subcontract PDF or enter manually). Bills are split
into a pay-now bill and a dated retention bill; the dashboard forecasts and releases them.
Run: pip install -r requirements.txt, set the .env values, then python app.py.
"""

import calendar
import csv
import datetime
import html
import io
import os
import re
import secrets
import urllib.parse
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import Flask, Response, redirect, request, session, url_for

load_dotenv(override=True)  # .env is read once at startup; restart after editing it.

from holdback import extract, terms_store, xero  # noqa: E402
from holdback.bills import build_accpay_bills  # noqa: E402
from holdback.split_engine import split_bill  # noqa: E402

app = Flask(__name__)
# No public fallback secret: a known key lets anyone forge the session (and the OAuth CSRF
# guard). Use the .env value, or a fresh random key per process for local dev.
app.secret_key = os.environ.get("FLASK_SECRET") or secrets.token_hex(32)

UPLOAD_SVG = ("<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='#2563EB' "
              "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
              "<path d='M12 15V4'/><path d='M7 9l5-5 5 5'/><path d='M5 19h14'/></svg>")
SHIELD_SVG = ("<svg width='13' height='13' viewBox='0 0 24 24' fill='none' stroke='#2BC48A' "
              "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
              "<path d='M12 3l7 3v6c0 4-3 7-7 8-4-1-7-4-7-8V6z'/><path d='M9 12l2 2 4-4'/></svg>")


def esc(value) -> str:
    """HTML-escape any dynamic value (Xero names/refs are user data, treat as untrusted)."""
    return html.escape(str(value), quote=True)


def _err(message: str, href: str = "/", label: str = "Back") -> str:
    """Themed error fragment. `message` may contain pre-escaped HTML."""
    return (
        "<div class='page-head'><div><h1>That needs a look</h1></div></div>"
        f"<div class='warn'>{message}</div>"
        f"<p style='margin-top:16px'><a class='btn' href='{href}'>{label}</a></p>"
    )


_ORG_NAME = None


def _org_name() -> str:
    """Org name for the header, cached until reconnect."""
    global _ORG_NAME
    if _ORG_NAME:
        return _ORG_NAME
    try:
        _ORG_NAME = xero.get_organisation()["Organisations"][0].get("Name", "")
    except Exception:  # noqa: BLE001
        return ""
    return _ORG_NAME


def _clear_org_cache():
    global _ORG_NAME
    _ORG_NAME = None


# path -> which nav tab is active, and which content width class to use.
def _active_tab(path):
    if path in ("/", "/new-bill", "/upload", "/confirm"):
        return "/"
    if path in ("/dashboard", "/forecast"):
        return "/dashboard"
    if path.startswith("/cis-return") or path.startswith("/statement"):
        return "/cis-return"
    if path.startswith("/reminders"):
        return "/reminders"
    return ""


def _width_cls(path):
    if path == "/":
        return "home"
    if path in ("/dashboard", "/forecast"):
        return "dash"
    if path in ("/new-bill", "/confirm"):
        return "narrow"
    return "wide"


def _page(body: str) -> str:
    """Wrap a body fragment in the app shell: full-width navy app bar + centered content."""
    path = request.path
    active = _active_tab(path)
    tabs = [("/", "New bill"), ("/dashboard", "Dashboard"),
            ("/cis-return", "CIS return"), ("/reminders", "Reminders")]

    def _tab(href, label):
        cls = " class='active'" if href == active else ""
        return f"<a href='{href}'{cls}>{label}</a>"

    nav = "".join(_tab(h, lbl) for h, lbl in tabs)
    org = _org_name()
    org_html = (f"<span class='dot'></span>{esc(org)}" if org
                else "<span class='dot off'></span>Not connected")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>HoldBack</title>"
        "<link rel='preconnect' href='https://fonts.googleapis.com'>"
        "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
        "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?"
        "family=Instrument+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&"
        "family=JetBrains+Mono:wght@400;500;600;700&display=swap'>"
        "<link rel='stylesheet' href='/static/holdback.css'></head><body>"
        "<div class='appbar'><div class='appbar-inner'>"
        "<a class='brand' href='/'><span class='wm'>Hold<b>Back</b></span></a>"
        f"<nav>{nav}</nav>"
        f"<div class='org'>{org_html}</div>"
        "</div></div>"
        f"<main class='content {_width_cls(path)}'>{body}</main></body></html>"
    )


@app.before_request
def _require_connection():
    """Data routes need a Xero connection; bounce to home (connect) when not connected."""
    p = request.path
    if p in ("/", "/login", "/callback") or p.startswith("/static"):
        return None
    if not xero.is_connected():
        return redirect(url_for("index"))
    return None


@app.after_request
def _wrap_html(resp):
    if (resp.content_type or "").startswith("text/html"):
        body = resp.get_data(as_text=True)
        head = body[:40].lower()
        if body and "<!doctype" not in head and "<html" not in head:
            resp.set_data(_page(body))
    return resp


@app.errorhandler(Exception)
def _on_error(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    app.logger.exception("Unhandled error")
    return _page(_err("Something went wrong. Try again, or reconnect to Xero.",
                      "/login", "Reconnect to Xero")), 500


# --- home (New bill entry) -------------------------------------------------------------
def _home_left() -> str:
    steps = [
        ("1", " on", "Upload the subcontract",
         "We read the retention %, release triggers and contract value from the PDF."),
        ("2", "", "Confirm the terms",
         "You review and sign off every figure before anything is written to Xero."),
        ("3", "", "Bills created in Xero",
         "A pay-now bill and a held retention bill, released later in tranches."),
    ]
    rail = "".join(
        f"<li class='step'><span class='step-n{on}'>{n}</span>"
        f"<div><div class='step-t'>{t}</div><div class='step-d'>{d}</div></div></li>"
        for n, on, t, d in steps)
    return (
        "<div class='home-left'>"
        "<div class='eyebrow'>New bill</div>"
        "<h1 class='home-h1'>Bill a subcontractor.<br>Retention handled.</h1>"
        "<p class='home-lead'>HoldBack splits every subcontractor bill in Xero into a pay-now "
        "bill and a retention bill. You keep sight of the money you hold back, release it on the "
        "right date, and CIS is deducted on labour only.</p>"
        f"<ol class='steps'>{rail}</ol></div>"
    )


@app.route("/")
def index():
    if not xero.is_connected():
        right = (
            "<div class='home-right'><div class='upload-card'><div class='connect-body'>"
            "<div class='dz-title'>Connect your Xero organisation</div>"
            "<div class='dz-hint'>Link Xero to start splitting subcontractor bills, tracking "
            "retention, and getting CIS right.</div>"
            "<a class='btn btn-primary' href='/login'>Connect to Xero</a>"
            "</div></div></div>"
        )
        return f"<div class='home-grid'>{_home_left()}{right}</div>"
    try:
        org = xero.get_organisation()["Organisations"][0]
    except Exception:  # noqa: BLE001
        app.logger.exception("organisation fetch failed")
        return _err("Connected, but Xero did not respond. Try reconnecting.", "/login", "Reconnect"), 502
    org_name, cc = org.get("Name", ""), org.get("CountryCode", "")
    missing = [s for s in xero.requested_scopes().split() if s not in xero.granted_scopes().split()]
    warn = (f"<div class='conn-warn'>Missing permission <code>{esc(' '.join(missing))}</code>. "
            "<a href='/login'>Reconnect</a> to grant it.</div>") if missing else ""
    right = (
        "<div class='home-right'><div class='upload-card'>"
        "<form method='post' action='/upload' enctype='multipart/form-data'>"
        "<label class='dropzone'>"
        f"<span class='dz-icon'>{UPLOAD_SVG}</span>"
        "<span class='dz-title'>Upload the subcontract PDF</span>"
        "<span class='dz-hint'>We pull out the retention terms for you to confirm.</span>"
        "<span class='dz-btn'>Choose PDF</span>"
        "<input type='file' name='pdf' accept='application/pdf' class='dz-input' onchange='this.form.submit()'>"
        "</label>"
        "<div class='dz-manual'>Prefer to type it in? <a href='/new-bill'>Enter the bill manually.</a></div>"
        "</form>"
        f"<div class='card-strip'>{SHIELD_SVG}<span>Nothing is written to Xero without your "
        "sign-off. Bills are created as drafts you approve.</span></div></div>"
        f"{warn}"
        f"<div class='conn'><span class='dot'></span>Connected to <b>{esc(org_name)}</b>"
        f"{(' (' + esc(cc) + ')') if cc else ''}.</div></div>"
    )
    return f"<div class='home-grid'>{_home_left()}{right}</div>"


@app.route("/login")
def login():
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    return redirect(xero.build_authorize_url(state))


@app.route("/callback")
def callback():
    if request.args.get("state") != session.get("oauth_state"):
        return _err("Your sign-in session expired or did not match. Start again.", "/login",
                    "Connect to Xero"), 400
    if request.args.get("error"):
        return _err("Xero did not authorise the connection. Try again.", "/login",
                    "Connect to Xero"), 400
    code = request.args.get("code")
    if not code:
        return _err("Authorisation was cancelled. Try again.", "/login", "Connect to Xero"), 400
    try:
        xero.exchange_code(code)
    except Exception:  # noqa: BLE001
        app.logger.exception("token exchange failed")
        return _err("Could not complete the Xero connection. Try again.", "/login",
                    "Connect to Xero"), 502
    _clear_org_cache()
    return redirect(url_for("index"))


# --- PDF extraction + confirm-terms review ---------------------------------------------
def _contact_options(selected=None) -> str:
    out = []
    for c in xero.get_contacts().get("Contacts", []):
        cid = c.get("ContactID")
        sel = " selected" if cid == selected else ""
        out.append(f'<option value="{esc(cid)}"{sel}>{esc(c.get("Name"))}</option>')
    return "".join(out)


def _confirm_field(label, name, node) -> str:
    """One editable field. Amber left-border when the extractor's confidence was under 0.8."""
    value = node.get("value") if isinstance(node, dict) else None
    conf = node.get("confidence", 0.0) if isinstance(node, dict) else 0.0
    has_value = value not in (None, "")
    cls = " class='low-confidence'" if (has_value and conf < 0.8) else ""
    badge = f" <span class='conf'>{int(round(conf * 100))}%</span>" if has_value else ""
    val = "" if value is None else esc(value)
    return (f"<div class='field'><label>{label}{badge}</label>"
            f"<input name='{name}' value=\"{val}\"{cls}></div>")


def _term_flags(terms) -> list:
    """Deterministic checks on the entered terms, surfaced on the confirm screen."""
    def val(node):
        v = node.get("value") if isinstance(node, dict) else None
        return v if v not in (None, "") else None

    if not any(val(n) for n in (
            terms["retention_pct"], terms["contract_value"],
            terms["trigger1"]["condition"], terms["trigger1"]["pct"], terms["trigger1"]["expected_date"],
            terms["trigger2"]["condition"], terms["trigger2"]["pct"], terms["trigger2"]["expected_date"])):
        return []

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    flags = []
    rp = num(val(terms["retention_pct"]))
    if rp is not None:
        if rp == 0:
            flags.append("Retention is 0%, so no money will be held back.")
        elif rp > 10:
            flags.append(f"Retention of {rp:g}% is unusually high. Double-check the contract.")
        elif rp > 5:
            flags.append(f"Retention of {rp:g}% is above the typical 5%.")
    if not val(terms["trigger1"]["expected_date"]):
        flags.append("No expected release date on Trigger 1. It is needed to due-date the retention bill.")
    a, b = num(val(terms["trigger1"]["pct"])), num(val(terms["trigger2"]["pct"]))
    if a is not None and b is not None and abs((a + b) - 100) > 0.001:
        flags.append(f"Trigger shares {a:g}% and {b:g}% do not add up to 100%.")
    if val(terms["trigger2"]["condition"]) and not val(terms["trigger2"]["expected_date"]):
        flags.append("Trigger 2 has a condition but no expected date.")
    return flags


def _render_confirm(terms) -> str:
    t1, t2 = terms["trigger1"], terms["trigger2"]
    flags = _term_flags(terms)
    flag_html = ("<div class='flags'><div class='flags-h'>Check these before saving</div><ul>"
                 + "".join(f"<li>{esc(f)}</li>" for f in flags) + "</ul></div>") if flags else ""
    return f"""
    <div class="page-head"><div><h1>Confirm the contract terms</h1>
      <p class="sub">Read from your PDF. Every field is editable. Check anything in amber, then
      save. Nothing reaches Xero until you do.</p></div></div>
    {flag_html}
    <form method="post" action="/confirm" class="form">
      <div class="field"><label>Job / subcontractor</label>
        <select name="contact_id" required>
          <option value="">Choose a subcontractor</option>{_contact_options()}</select></div>
      {_confirm_field("Retention (%)", "retention_pct", terms["retention_pct"])}
      <fieldset><legend>Trigger 1, first release</legend>
        {_confirm_field("Condition (e.g. practical completion)", "trigger1_condition", t1["condition"])}
        <div class="field-row two">
          {_confirm_field("Share of retention (%)", "trigger1_pct", t1["pct"])}
          {_confirm_field("Expected release date", "trigger1_date", t1["expected_date"])}
        </div>
      </fieldset>
      <fieldset><legend>Trigger 2, final release (optional)</legend>
        {_confirm_field("Condition", "trigger2_condition", t2["condition"])}
        <div class="field-row two">
          {_confirm_field("Share of retention (%)", "trigger2_pct", t2["pct"])}
          {_confirm_field("Expected release date", "trigger2_date", t2["expected_date"])}
        </div>
      </fieldset>
      {_confirm_field("Contract value (display only)", "contract_value", terms["contract_value"])}
      <div class="actions">
        <button class="btn-primary" type="submit">Save terms</button>
        <a class="btn" href="/">Upload a different PDF</a>
      </div>
    </form>"""


@app.route("/upload", methods=["GET"])
def upload_form():
    return redirect(url_for("index"))  # the home page is the upload entry


@app.route("/upload", methods=["POST"])
def upload_extract():
    file = request.files.get("pdf")
    text = extract.pdf_text(file) if file else ""
    # extract_terms never raises: any failure gives empty terms and a blank confirm screen.
    return _render_confirm(extract.extract_terms(text))


@app.route("/confirm", methods=["GET"])
def confirm_blank():
    return redirect(url_for("new_bill_form"))  # manual entry goes straight to the bill form


@app.route("/confirm", methods=["POST"])
def confirm_save():
    f = request.form
    contact_id = f.get("contact_id", "").strip()
    if not contact_id:
        return _err("Please choose a subcontractor.", "/", "Back"), 400
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
    return redirect(url_for("new_bill_form", contact_id=contact_id))


# --- new bill (the split form) ---------------------------------------------------------
# From the Demo Company (UK) chart of accounts / tax rates:
#   321 CIS Labour Expense (Xero applies CIS here), 322 CIS Materials Purchased (excluded),
#   INPUT2 = 20% VAT on Expenses.
CIS_LABOUR_ACCOUNT = "321"
MATERIALS_ACCOUNT = "322"
VAT_TAX_TYPE = "INPUT2"


@app.route("/new-bill", methods=["GET"])
def new_bill_form():
    selected = request.args.get("contact_id", "")
    stored = terms_store.get_terms(selected) if selected else None
    options = "".join(
        f'<option value="{esc(c.get("ContactID"))}"'
        f'{" selected" if c.get("ContactID") == selected else ""}>{esc(c.get("Name"))}</option>'
        for c in xero.get_contacts().get("Contacts", []))
    today = datetime.date.today().isoformat()
    default_release = (datetime.date.today() + datetime.timedelta(days=180)).isoformat()
    pay_due = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()
    s = stored or {}
    retention_val = s.get("retention_pct") or "5"
    t1_pct = s.get("trigger1_pct") or "100"
    t1_date = s.get("trigger1_date") or default_release
    t2_pct = s.get("trigger2_pct") or ""
    t2_date = s.get("trigger2_date") or ""
    note = ("<div class='saved-terms'>Loaded saved terms for this job. Every field is still "
            "editable.</div>") if stored else ""
    return f"""
    <div class="page-head"><div><h1>Create the bills</h1>
      <p class="sub">One bill in. A pay-now bill and a draft retention bill out, split and
      CIS correct.</p></div></div>
    {note}
    <form method="post" class="form">
      <div class="field"><label>Subcontractor</label>
        <select name="contact_id" required>
          <option value="">Choose a subcontractor</option>{options}</select>
        <div class="hint">Pick the contact set up as a CIS subcontractor in Xero.</div></div>
      <div class="field-row three">
        <div class="field"><label>Total (&pound;)</label><input name="total" value="1500.00"></div>
        <div class="field"><label>Labour (&pound;)</label><input name="labour" value="1000.00"></div>
        <div class="field"><label>Materials (&pound;)</label><input name="materials" value="500.00"></div>
      </div>
      <div class="hint">CIS is deducted on labour only. Materials are never part of the CIS base.</div>
      <div class="field-row three">
        <div class="field"><label>Retention (%)</label><input name="retention_pct" value="{retention_val}"></div>
        <div class="field"><label>Bill date</label><input name="date" value="{today}"></div>
        <div class="field"><label>Pay-now due date</label><input name="pay_now_due_date" value="{pay_due}"></div>
      </div>
      <fieldset><legend>Release triggers</legend>
        <div class="field-row two">
          <div class="field"><label>Trigger 1 share (%)</label><input name="trigger1_pct" value="{t1_pct}"></div>
          <div class="field"><label>Trigger 1 release date</label><input name="trigger1_date" value="{t1_date}"></div>
        </div>
        <div class="field-row two">
          <div class="field"><label>Trigger 2 share (%)</label><input name="trigger2_pct" value="{t2_pct}"></div>
          <div class="field"><label>Trigger 2 release date</label><input name="trigger2_date" value="{t2_date}"></div>
        </div>
        <div class="hint">Leave Trigger 2 blank for a single release (100% at Trigger 1). For two
          releases, the shares must add up to 100.</div>
      </fieldset>
      <div class="field"><label>Pay-now bill</label>
        <label class="radio"><input type="radio" name="pay_now_status" value="DRAFT" checked>
          Draft, review and approve by hand</label>
        <label class="radio"><input type="radio" name="pay_now_status" value="AUTHORISED">
          Approve now</label></div>
      <div class="actions">
        <button class="btn-primary" type="submit">Create bills in Xero</button>
        <a class="btn" href="/">Set terms from a PDF</a>
      </div>
    </form>"""


@app.route("/new-bill", methods=["POST"])
def new_bill_create():
    f = request.form
    t1_date = f.get("trigger1_date", "").strip()
    t2_date = f.get("trigger2_date", "").strip()
    try:
        split = split_bill(f.get("total", ""), f.get("labour", ""),
                           f.get("materials", ""), f.get("retention_pct", ""))
        if t2_date:
            t1 = Decimal(f.get("trigger1_pct", "").strip() or "0")
            t2 = Decimal(f.get("trigger2_pct", "").strip() or "0")
            if t1 + t2 != Decimal("100"):
                return _err(f"Trigger shares must add up to 100 (you entered {t1} and {t2}).",
                            "/new-bill", "Back to the form"), 400
            tranches = [{"share": t1, "due_date": t1_date}, {"share": t2, "due_date": t2_date}]
        else:
            tranches = [{"share": Decimal("100"), "due_date": t1_date}]
        payloads = build_accpay_bills(
            split, contact_id=f.get("contact_id", ""), date=f.get("date", ""), tranches=tranches,
            cis_labour_account_code=CIS_LABOUR_ACCOUNT, materials_account_code=MATERIALS_ACCOUNT,
            vat_tax_type=VAT_TAX_TYPE, pay_now_status=f.get("pay_now_status", "DRAFT"),
            pay_now_due_date=f.get("pay_now_due_date", "").strip() or None, reference="HoldBack")
    except (ValueError, ArithmeticError, InvalidOperation, KeyError) as exc:
        return _err(f"Check the figures. {esc(str(exc))}", "/new-bill", "Back to the form"), 400

    to_create = [payloads["pay_now"], *payloads["retention_bills"]]
    try:
        result = xero.create_bills(to_create)
    except Exception:  # noqa: BLE001
        app.logger.exception("create_bills failed")
        return _err("Could not create the bills in Xero. Check you are connected with write "
                    "access, then try again.", "/new-bill", "Back to the form"), 502
    rows = "".join(
        f"<tr><td>{esc(inv.get('Reference'))}</td><td>{esc(inv.get('Status'))}</td>"
        f"<td class='num'>{_money_fmt(inv.get('Total'))}</td>"
        f"<td>{_parse_xero_date(inv.get('DueDate')) or ''}</td></tr>"
        for inv in result.get("Invoices", []))
    return f"""
    <div class="page-head"><div><h1>Bills created</h1>
      <p class="sub">Open Xero, then Business, then Bills to see them. CIS shows on the labour
      line once a bill is approved.</p></div></div>
    <div class="table-wrap"><table><thead><tr><th>Reference</th><th>Status</th>
      <th class='num'>Total</th><th>Due</th></tr></thead><tbody>{rows}</tbody></table></div>
    <p style="margin-top:16px"><a class="btn btn-primary" href="/dashboard">Go to the dashboard</a>
      <a class="btn" href="/new-bill" style="margin-left:8px">Create another</a></p>"""


# --- dashboard data helpers ------------------------------------------------------------
def _parse_xero_date(value):
    """Xero returns dates as '/Date(1798675200000+0000)/'. Return a date for sort/display."""
    if not value:
        return None
    m = re.search(r"/Date\((-?\d+)", value)
    if not m:
        return None
    ms = int(m.group(1))
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=ms)).date()


_STATUS_LANE = {
    "DRAFT": ("Held", "held"),
    "AUTHORISED": ("Awaiting payment", "released"),
    "PAID": ("Paid", "paid"),
}


def _money_fmt(value) -> str:
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
            ref.strip() == "HoldBack" and bool(inv.get("DueDate")))
        if not is_retention:
            continue
        lane = _STATUS_LANE.get(inv.get("Status"))
        if not lane:  # skip VOIDED / DELETED
            continue
        items.append({
            "id": inv.get("InvoiceID"),
            "name": (inv.get("Contact") or {}).get("Name", "?"),
            "contact_id": (inv.get("Contact") or {}).get("ContactID", ""),
            "held": inv.get("Total"),
            "due": _parse_xero_date(inv.get("DueDate")),
            "inv_no": inv.get("InvoiceNumber") or "",
            "tranche": _tranche_label(ref),
            "lane": lane[1],
        })
    return items


@app.route("/dashboard")
def dashboard():
    """Forecast dashboard: KPI card, retention-by-month chart, and an upcoming-releases table.
    Lifecycle read from Xero status (DRAFT=Held, AUTHORISED=Released, PAID=Paid)."""
    lanes = {"held": [], "released": [], "paid": []}
    for i in _retention_items():
        lanes[i["lane"]].append(i)
    lanes["held"].sort(key=lambda i: (i["due"] is None, i["due"] or datetime.date.max))
    held = lanes["held"]
    today = datetime.date.today()

    def lane_total(lane):
        return sum(float(i["held"] or 0) for i in lanes[lane])

    # month buckets: this month out to the furthest held release (6 to 12 months).
    base = today.year * 12 + today.month - 1
    dues = [i["due"] for i in held if i["due"]]
    span = min(12, max(6, (max(d.year * 12 + d.month - 1 for d in dues) - base + 1))) if dues else 6
    labels = [datetime.date((base + k) // 12, (base + k) % 12 + 1, 1) for k in range(span)]
    totals = [0.0] * span
    for i in held:
        if i["due"]:
            pos = (i["due"].year * 12 + i["due"].month - 1) - base
            if 0 <= pos < span:
                totals[pos] += float(i["held"] or 0)
    max_m = max(totals + [1.0])
    bars = "".join(
        (f"<div class='bar'><span class='bar-val{'' if t else ' faint'}'>"
         f"{_money_fmt(t) if t else ''}</span>"
         f"<div class='bar-fill{'' if t else ' faint'}' style='height:{max(6, round(t / max_m * 128)) if t else 2}px'></div></div>")
        for t in totals)
    xlabels = "".join(
        f"<div class='bar-x{'' if t else ' faint'}'>{lab.strftime('%b')}</div>"
        for lab, t in zip(labels, totals))

    next_item = next((i for i in held if i["due"]), None)
    if next_item:
        next_txt = next_item["due"].strftime("%d %b %Y")
        next_sub = f"{esc(next_item['name'])}, {_money_fmt(next_item['held'])}"
    else:
        next_txt, next_sub = "None scheduled", "nothing currently held"

    kpi = (
        "<div class='kpi'>"
        f"<div><div class='kpi-label'>Total held</div><div class='kpi-value'>{_money_fmt(lane_total('held'))}</div>"
        f"<div class='kpi-sub'>releasing over the next {span} months</div></div>"
        "<div class='kpi-split'>"
        f"<div><div class='kpi-label'>Released</div><div class='kpi-num rel'>{_money_fmt(lane_total('released'))}</div></div>"
        f"<div><div class='kpi-label'>Paid</div><div class='kpi-num paid'>{_money_fmt(lane_total('paid'))}</div></div></div>"
        f"<div class='kpi-next'><div class='kpi-label'>Next release due</div>"
        f"<div class='kpi-nextv'>{next_txt}</div><div class='kpi-sub'>{next_sub}</div></div></div>"
    )
    chart = (
        "<div class='chart-card'><div class='chart-title'>Retention releasing by month</div>"
        f"<div class='chart'>{bars}</div><div class='chart-x'>{xlabels}</div></div>"
    )

    def row(i):
        d = i["due"]
        days = (d - today).days if d else None
        due_cls = " due-soon" if (days is not None and 0 <= days <= 30) else ""
        due_txt = d.strftime("%d %b %Y") if d else "no date"
        indays = "" if days is None else ("overdue" if days < 0 else "today" if days == 0 else f"in {days} days")
        inv_txt = esc(i["inv_no"]) if i["inv_no"] else "Open in Xero"
        rel = (f"<form method='post' action='/dashboard/approve/{i['id']}' "
               "onsubmit=\"return confirm('Release this retention now? HoldBack will change the "
               "bill from Draft to Authorised in Xero.')\"><button class='btn-rel'>Release</button></form>")
        return (
            "<div class='rel-row'>"
            f"<div class='rel-due{due_cls}'>{due_txt}</div>"
            f"<div class='rel-name'>{esc(i['name'])}</div>"
            f"<div><a class='rel-inv' href='{_xero_link(i['id'])}' target='_blank' rel='noopener'>{inv_txt} ↗</a></div>"
            f"<div class='rel-tr'>{esc(i['tranche'])}</div>"
            f"<div class='rel-days'>{indays}</div>"
            f"<div class='rel-amt'>{_money_fmt(i['held'])}</div>"
            f"<div class='rel-act'>{rel}</div></div>"
        )
    body = "".join(row(i) for i in held) or "<div class='rel-empty'>No retention currently held.</div>"
    releases = (
        "<div class='releases'><div class='releases-head'><span class='releases-h'>Upcoming releases</span>"
        "<span class='releases-sub'>soonest first, held only</span></div>"
        f"<div class='table-wrap'>{body}</div></div>"
    )
    return f"<div class='dash'><div class='dash-row1'>{kpi}{chart}</div>{releases}</div>"


@app.route("/dashboard/approve/<invoice_id>", methods=["POST"])
def dashboard_approve(invoice_id):
    """Release a retention bill (Draft -> Authorised). Xero fixes the CIS deduction at the
    contact's current rate on approval, which is the HMRC rate-at-payment rule."""
    try:
        xero.approve_invoice(invoice_id)
    except Exception:  # noqa: BLE001
        app.logger.exception("approve failed")
        return _err("Could not release that retention in Xero. Try again.", "/dashboard"), 502
    return redirect(url_for("dashboard"))


# --- CIS monthly return + per-subcontractor statement ----------------------------------
XERO_BILL_URL = "https://go.xero.com/AccountsPayable/View.aspx?InvoiceID="


def _xero_link(invoice_id: str) -> str:
    return XERO_BILL_URL + (invoice_id or "")


def _line_sum(inv: dict, account_code: str) -> Decimal:
    total = Decimal("0")
    for li in inv.get("LineItems", []):
        if str(li.get("AccountCode")) == account_code:
            amt = li.get("LineAmount")
            if amt is None:
                amt = li.get("UnitAmount", 0)
            total += Decimal(str(amt or 0))
    return total


def _holdback_bills() -> list:
    return [inv for inv in xero.get_bills(where='Type=="ACCPAY"').get("Invoices", [])
            if (inv.get("Reference") or "").startswith("HoldBack")]


def _cis_by_subcontractor() -> dict:
    rows: dict = {}
    for inv in _holdback_bills():
        c = inv.get("Contact") or {}
        r = rows.setdefault(c.get("Name", "?"), {
            "cid": c.get("ContactID", ""), "labour": Decimal("0"),
            "materials": Decimal("0"), "deduction": Decimal("0")})
        r["labour"] += _line_sum(inv, CIS_LABOUR_ACCOUNT)
        r["materials"] += _line_sum(inv, MATERIALS_ACCOUNT)
        ded = inv.get("CISDeduction")
        if ded not in (None, ""):
            r["deduction"] += Decimal(str(ded))
    return rows


@app.route("/cis-return")
def cis_return():
    rows = _cis_by_subcontractor()
    tot_lab = tot_mat = tot_ded = Decimal("0")
    body = ""
    for name, r in sorted(rows.items()):
        tot_lab += r["labour"]; tot_mat += r["materials"]; tot_ded += r["deduction"]
        body += (f"<tr><td>{esc(name)}</td><td class='num'>{_money_fmt(r['labour'] + r['materials'])}</td>"
                 f"<td class='num'>{_money_fmt(r['materials'])}</td>"
                 f"<td class='num'>{_money_fmt(r['labour'])}</td>"
                 f"<td class='num'>{_money_fmt(r['deduction'])}</td>"
                 f"<td><a href='/statement/{esc(r['cid'])}'>Statement</a></td></tr>")
    if not body:
        body = "<tr><td colspan='6'>No HoldBack bills yet.</td></tr>"
    else:
        body += (f"<tr><th>Total</th><th class='num'>{_money_fmt(tot_lab + tot_mat)}</th>"
                 f"<th class='num'>{_money_fmt(tot_mat)}</th><th class='num'>{_money_fmt(tot_lab)}</th>"
                 f"<th class='num'>{_money_fmt(tot_ded)}</th><th></th></tr>")
    return (
        "<div class='page-head'><div><h1>CIS monthly return</h1>"
        "<p class='sub'>Every deduction this month, by subcontractor. Ready for your CIS300 and "
        "the statements you owe each subcontractor.</p></div>"
        "<a class='btn' href='/cis-return.csv'>Export CSV</a></div>"
        "<div class='table-wrap'><table><thead><tr><th>Subcontractor</th><th class='num'>Total payments</th>"
        "<th class='num'>Materials</th><th class='num'>Labour (CIS base)</th>"
        "<th class='num'>CIS deducted</th><th>Statement</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        "<p class='hint' style='margin-top:14px'>CIS deducted reflects Xero's figure on each bill, "
        "shown once a bill is approved. Materials are excluded from the CIS base.</p>"
    )


@app.route("/cis-return.csv")
def cis_return_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Subcontractor", "Total payments", "Materials", "Labour (CIS base)", "CIS deducted"])

    def safe(s):  # neutralise spreadsheet formula injection
        s = str(s)
        return ("'" + s) if s[:1] in ("=", "+", "-", "@") else s

    for name, r in sorted(_cis_by_subcontractor().items()):
        w.writerow([safe(name), f"{r['labour'] + r['materials']:.2f}", f"{r['materials']:.2f}",
                    f"{r['labour']:.2f}", f"{r['deduction']:.2f}"])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=cis-return.csv"})


@app.route("/statement/<contact_id>")
def statement(contact_id):
    bills = [inv for inv in _holdback_bills()
             if (inv.get("Contact") or {}).get("ContactID") == contact_id]
    if not bills:
        return "<div class='page-head'><div><h1>Statement</h1><p class='sub'>No HoldBack bills for this contact.</p></div></div>"
    name = (bills[0].get("Contact") or {}).get("Name", "?")
    tl = tm = td = Decimal("0")
    rows = ""
    for inv in bills:
        lab = _line_sum(inv, CIS_LABOUR_ACCOUNT)
        mat = _line_sum(inv, MATERIALS_ACCOUNT)
        ded = inv.get("CISDeduction")
        ded = Decimal(str(ded)) if ded not in (None, "") else Decimal("0")
        tl += lab; tm += mat; td += ded
        rows += (f"<tr><td>{_parse_xero_date(inv.get('Date')) or ''}</td>"
                 f"<td>{esc(inv.get('Reference'))}</td><td class='num'>{_money_fmt(lab)}</td>"
                 f"<td class='num'>{_money_fmt(mat)}</td><td class='num'>{_money_fmt(ded)}</td>"
                 f"<td>{esc(inv.get('Status'))}</td></tr>")
    return (
        "<div class='page-head'><div><h1>Payment and deduction statement</h1>"
        f"<p class='sub'>{esc(name)}</p></div><a class='btn' href='/cis-return'>Back to CIS return</a></div>"
        "<div class='table-wrap'><table><thead><tr><th>Date</th><th>Bill</th><th class='num'>Labour</th>"
        "<th class='num'>Materials</th><th class='num'>CIS deducted</th><th>Status</th></tr></thead>"
        f"<tbody>{rows}<tr><th colspan='2'>Total</th><th class='num'>{_money_fmt(tl)}</th>"
        f"<th class='num'>{_money_fmt(tm)}</th><th class='num'>{_money_fmt(td)}</th><th></th></tr></tbody></table></div>"
        "<p class='hint' style='margin-top:14px'>Give this to the subcontractor for the tax month "
        "(an HMRC CIS requirement). Materials are excluded from the CIS deduction.</p>"
    )


@app.route("/forecast")
def forecast():
    return redirect(url_for("dashboard"))  # the dashboard is the forecast now


# --- escalating release-reminder drafts ------------------------------------------------
_MONTHS_BEFORE = [12, 6, 3, 1]


def _sub_months(d, n):
    total = d.year * 12 + (d.month - 1) - n
    y, m = divmod(total, 12)
    m += 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _mailto(email, subject, body):
    q = urllib.parse.urlencode({"subject": subject, "body": body}, quote_via=urllib.parse.quote)
    return f"mailto:{email or ''}?{q}"


def _reminder_email(name, amount, tranche, org, due_str, n):
    tr = f"tranche {tranche}" if tranche else "the retention"
    close = f"\n\nBest regards,\n{org}"
    if n >= 12:
        return (f"Retention release scheduled: {amount} for {name}",
                f"Hi {name},\n\nA note that {amount} of {tr} is scheduled for release on {due_str}. "
                f"Nothing is needed from you yet. We will be in touch nearer the date.{close}")
    if n >= 6:
        return (f"Retention release in about six months: {amount}",
                f"Hi {name},\n\n{amount} of {tr} is due for release on {due_str}, about six months "
                f"away. Please let us know if your payment or contact details have changed.{close}")
    if n >= 3:
        return (f"Retention release approaching: {amount}, due {due_str}",
                f"Hi {name},\n\n{amount} of {tr} is due for release on {due_str}. We will process it "
                f"on or shortly after that date. Please confirm your details are current.{close}")
    return (f"Retention due for release next month: {amount}",
            f"Hi {name},\n\n{amount} of {tr} is due for release on {due_str}. We are preparing to "
            f"release it. Please confirm your bank details so payment is not delayed.{close}")


@app.route("/reminders")
def reminders():
    """Escalating release-reminder drafts. Each opens in the user's mail client via mailto;
    timed auto-send would be a post-demo add-on (email provider plus scheduler)."""
    org = _org_name() or "HoldBack"
    emails = {c.get("ContactID"): (c.get("EmailAddress") or "")
              for c in xero.get_contacts().get("Contacts", [])}
    today = datetime.date.today()
    held = sorted((i for i in _retention_items() if i["lane"] == "held" and i["due"]),
                  key=lambda i: i["due"])
    rows = ""
    for i in held:
        due_str = i["due"].strftime("%d %b %Y")
        sched = [(n, _sub_months(i["due"], n)) for n in _MONTHS_BEFORE]
        due_ns = [n for n, sd in sched if sd <= today]
        current = min(due_ns) if due_ns else _MONTHS_BEFORE[0]
        chips = "".join(
            f"<span class='rem-chip{' due' if (n == current and due_ns) else ''}'>"
            f"{n}mo, {sd.strftime('%d %b %y')}</span>" for n, sd in sched)
        subj, body = _reminder_email(i["name"], _money_fmt(i["held"]), i["tranche"], org, due_str, current)
        state = ("<span class='rem-chip due'>reminder due now</span>" if due_ns
                 else f"<span class='rem-chip'>first reminder {sched[0][1].strftime('%d %b %y')}</span>")
        sub = f"releases {due_str}" + (f", tranche {i['tranche']}" if i["tranche"] else "")
        rows += (
            f"<article class='card'><div class='card-top'><div style='min-width:0'>"
            f"<div class='card-name'>{esc(i['name'])}</div><div class='card-sub'>{sub}</div></div>"
            f"<div class='card-amt'>{_money_fmt(i['held'])}</div></div>"
            f"<div class='rem-sched'>{chips}</div>"
            f"<div class='card-meta'>{state}"
            f"<a class='btn btn-primary rem-send' href=\"{_mailto(emails.get(i['contact_id'], ''), subj, body)}\">"
            "Draft reminder email</a></div></article>"
        )
    rows = rows or "<div class='rel-empty'>No held retention to remind on yet.</div>"
    return (
        "<div class='page-head'><div><h1>Release reminders</h1>"
        "<p class='sub'>An escalating cadence at 12, 6, 3 and 1 month before each release, so "
        "retention never slips. HoldBack drafts each email; click to open it in your mail app.</p>"
        "</div></div>"
        f"{rows}"
        "<p class='hint' style='margin-top:14px'>Drafts open in your email client, no mail server "
        "needed. Automatic timed sending would need an email provider and a scheduler, a post-demo "
        "add-on.</p>"
    )


if __name__ == "__main__":
    if not os.environ.get("XERO_CLIENT_SECRET"):
        print("\n[!] XERO_CLIENT_SECRET is empty. Set it in .env and restart.\n")
    else:
        print("[ok] XERO_CLIENT_SECRET loaded.")
    # debug off by default; set FLASK_DEBUG=1 locally if you want the reloader/debugger.
    app.run(host="localhost", port=5000, debug=os.environ.get("FLASK_DEBUG") == "1")
