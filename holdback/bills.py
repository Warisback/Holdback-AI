"""
Build the two ACCPAY bill payloads for the Xero Invoices endpoint.

PURE — this module constructs dicts only; it does NOT POST to Xero. The actual write
wiring is separate and only runs after "NUMBERS CONFIRMED" (which has now been given).

CIS handling — why there is no CIS line here:
    We never compute or post a CIS deduction line (journal ban, CLAUDE.md rules 3 & 5).
    We simply code the LABOUR lines to the CIS Labour Expense account and leave MATERIALS
    on a normal expense account. Xero then applies the CIS deduction automatically at
    APPROVAL, from the contact's live rate, because (a) the contact is a CIS subcontractor
    and (b) the line uses a CIS-enabled account. This is exactly why:
      - the PAY-NOW bill is approved now  -> its CIS rate is fixed now;
      - the RETENTION bill stays DRAFT    -> its CIS rate is fixed later, at release,
        after we re-fetch the contact's CISSettings (CLAUDE.md rule 5 / addendum).

Everything is Type="ACCPAY" (a BILL — never ACCREC) and LineAmountTypes="Exclusive",
with one fixed VAT TaxType on every line (CLAUDE.md API specifics).
"""

from __future__ import annotations

from decimal import Decimal

from .split_engine import BillLines, Split


def _line(description: str, amount: Decimal, account_code: str, tax_type: str) -> dict:
    # UnitAmount is sent as a 2dp string to avoid binary-float noise. If Xero's
    # validation rejects string amounts on the first live write, switch to float(amount)
    # — 2dp values round-trip cleanly through JSON either way. (Flagged in PROGRESS.md.)
    return {
        "Description": description,
        "Quantity": 1,
        "UnitAmount": str(amount),
        "AccountCode": account_code,
        "TaxType": tax_type,
    }


def _lines_for(lines: BillLines, *, cis_labour_account_code: str,
               materials_account_code: str, vat_tax_type: str) -> list[dict]:
    # Omit any zero-value line — Xero shouldn't receive a £0.00 labour or materials line
    # (e.g. a materials-only job, or 0% retention).
    out: list[dict] = []
    if lines.labour != Decimal("0.00"):
        out.append(_line("Labour (CIS)", lines.labour, cis_labour_account_code, vat_tax_type))
    if lines.materials != Decimal("0.00"):
        out.append(_line("Materials", lines.materials, materials_account_code, vat_tax_type))
    return out


def _bill(*, contact_id: str, date: str, status: str, line_items: list[dict],
          due_date: str | None = None, reference: str | None = None) -> dict:
    bill = {
        "Type": "ACCPAY",                       # BILL — never ACCREC
        "Contact": {"ContactID": contact_id},
        "Date": date,                           # ISO "YYYY-MM-DD"
        "LineAmountTypes": "Exclusive",
        "Status": status,
        "LineItems": line_items,
    }
    if due_date:
        bill["DueDate"] = due_date
    if reference:
        bill["Reference"] = reference
    return bill


def build_accpay_bills(
    split: Split,
    *,
    contact_id: str,
    date: str,
    retention_due_date: str,
    cis_labour_account_code: str,
    materials_account_code: str,
    vat_tax_type: str,
    pay_now_status: str = "AUTHORISED",
    pay_now_due_date: str | None = None,
    reference: str | None = None,
) -> dict:
    """Return {"pay_now": <bill dict>, "retention": <bill dict or None>}.

    Parameters
    ----------
    split               : output of split_engine.split_bill
    contact_id           : the CIS subcontractor's Xero ContactID
    date                 : bill date, ISO "YYYY-MM-DD"
    retention_due_date   : expected release date for the retention bill (drives the
                           dashboard sort) — ISO "YYYY-MM-DD"
    cis_labour_account_code : account code for CIS Labour Expense (Xero applies CIS here)
    materials_account_code  : account code for a normal materials expense (excluded from CIS)
    vat_tax_type            : the org's 20% VAT-on-expenses TaxType (confirm exact name)
    pay_now_status          : "AUTHORISED" fixes CIS now (default); "DRAFT" if you want to
                              eyeball the bill in Xero and approve it by hand first.
    pay_now_due_date        : optional ISO date; omitted -> Xero defaults it.
    reference               : optional text stamped on both bills (useful on the dashboard).

    The RETENTION bill is ALWAYS created as DRAFT and due-dated to release; it is approved
    later from the dashboard (after re-fetching the contact's CIS rate).
    """
    codes = dict(
        cis_labour_account_code=cis_labour_account_code,
        materials_account_code=materials_account_code,
        vat_tax_type=vat_tax_type,
    )

    base_ref = reference or "HoldBack"

    pay_now = _bill(
        contact_id=contact_id,
        date=date,
        status=pay_now_status,
        line_items=_lines_for(split.pay_now, **codes),
        due_date=pay_now_due_date,
        reference=f"{base_ref} (pay now)",
    )

    retention_lines = _lines_for(split.retention, **codes)
    retention = None
    if retention_lines:  # skip entirely when retention is 0
        retention = _bill(
            contact_id=contact_id,
            date=date,
            status="DRAFT",                      # never auto-approved (rule 6)
            line_items=retention_lines,
            due_date=retention_due_date,
            reference=f"{base_ref} (retention)",  # the dashboard filters on this
        )

    return {"pay_now": pay_now, "retention": retention}
