"""
Tests for the ACCPAY bill payload builder. These assert STRUCTURE and that the money
lines match the split — they don't hit Xero. The CIS deduction is Xero's job at
approval, so it never appears in these payloads.
"""

from decimal import Decimal

from holdback.bills import build_accpay_bills
from holdback.split_engine import split_bill

# Candidate 2 numbers, plus placeholder org codes (real ones come from the live org).
SPLIT = split_bill(1234.56, 880.24, 354.32, 5)  # retention: labour 44.01, materials 17.72
KW = dict(
    contact_id="CID-123",
    date="2026-07-04",
    tranches=[{"share": 100, "due_date": "2027-01-31"}],  # single release
    cis_labour_account_code="CISLBR",
    materials_account_code="310",
    vat_tax_type="INPUT2",
)


def _line_by_desc(bill, prefix):
    return next(li for li in bill["LineItems"] if li["Description"].startswith(prefix))


def _all_bills(bills):
    return [bills["pay_now"], *bills["retention_bills"]]


def test_two_bills_are_accpay_never_accrec():
    bills = build_accpay_bills(SPLIT, **KW)
    for bill in _all_bills(bills):
        assert bill["Type"] == "ACCPAY"
        assert bill["LineAmountTypes"] == "Exclusive"
        assert bill["Contact"] == {"ContactID": "CID-123"}


def test_pay_now_bill_always_has_a_due_date():
    # Xero rejects approval of a bill with no due date; default to the bill date.
    assert build_accpay_bills(SPLIT, **KW)["pay_now"]["DueDate"] == "2026-07-04"
    explicit = build_accpay_bills(SPLIT, pay_now_due_date="2026-08-04", **KW)["pay_now"]
    assert explicit["DueDate"] == "2026-08-04"


def test_retention_bill_is_draft_and_due_dated_to_release():
    ret = build_accpay_bills(SPLIT, **KW)["retention_bills"][0]
    assert ret["Status"] == "DRAFT"
    assert ret["DueDate"] == "2027-01-31"
    assert "(retention)" in ret["Reference"]


def test_pay_now_status_defaults_to_authorised_but_is_overridable():
    assert build_accpay_bills(SPLIT, **KW)["pay_now"]["Status"] == "AUTHORISED"
    draft = build_accpay_bills(SPLIT, pay_now_status="DRAFT", **KW)["pay_now"]
    assert draft["Status"] == "DRAFT"


def test_labour_uses_cis_account_materials_does_not():
    bills = build_accpay_bills(SPLIT, **KW)
    for bill in _all_bills(bills):
        assert _line_by_desc(bill, "Labour")["AccountCode"] == "CISLBR"
        assert _line_by_desc(bill, "Materials")["AccountCode"] == "310"
        for li in bill["LineItems"]:
            assert li["TaxType"] == "INPUT2"


def test_line_amounts_match_the_split():
    bills = build_accpay_bills(SPLIT, **KW)
    assert _line_by_desc(bills["pay_now"], "Labour")["UnitAmount"] == "836.23"
    assert _line_by_desc(bills["pay_now"], "Materials")["UnitAmount"] == "336.60"
    ret = bills["retention_bills"][0]
    assert _line_by_desc(ret, "Labour")["UnitAmount"] == "44.01"
    assert _line_by_desc(ret, "Materials")["UnitAmount"] == "17.72"


def test_no_cis_deduction_line_is_ever_added():
    # We must not fabricate a CIS line — Xero computes the deduction at approval.
    for bill in _all_bills(build_accpay_bills(SPLIT, **KW)):
        assert len(bill["LineItems"]) == 2  # labour + materials only
        for li in bill["LineItems"]:
            assert "CIS" not in li["Description"].upper() or li["Description"].startswith("Labour")


def test_zero_retention_creates_no_retention_bill():
    bills = build_accpay_bills(split_bill(1000.00, 600.00, 400.00, 0), **KW)
    assert bills["retention_bills"] == []
    assert bills["pay_now"]["LineItems"][0]["UnitAmount"] == "600.00"


def test_references_distinguish_pay_now_and_retention():
    bills = build_accpay_bills(SPLIT, **KW)
    assert "(pay now)" in bills["pay_now"]["Reference"]
    assert "(retention)" in bills["retention_bills"][0]["Reference"]


def test_materials_only_job_omits_labour_line():
    bills = build_accpay_bills(split_bill(500.00, 0.00, 500.00, 10), **KW)
    descs = [li["Description"] for li in bills["pay_now"]["LineItems"]]
    assert descs == ["Materials"]  # no zero-value labour line


def test_two_tranche_retention_bills():
    """Two dated draft retention bills, references 1/2 and 2/2, reconciling to retention."""
    kw = {**KW, "tranches": [
        {"share": 50, "due_date": "2027-01-31"},
        {"share": 50, "due_date": "2027-07-31"},
    ]}
    rb = build_accpay_bills(SPLIT, **kw)["retention_bills"]
    assert len(rb) == 2
    assert "(retention 1/2)" in rb[0]["Reference"] and rb[0]["DueDate"] == "2027-01-31"
    assert "(retention 2/2)" in rb[1]["Reference"] and rb[1]["DueDate"] == "2027-07-31"
    # tranche lines reconcile to SPLIT.retention (labour 44.01, materials 17.72)
    labour = sum(Decimal(_line_by_desc(b, "Labour")["UnitAmount"]) for b in rb)
    materials = sum(Decimal(_line_by_desc(b, "Materials")["UnitAmount"]) for b in rb)
    assert labour == Decimal("44.01")
    assert materials == Decimal("17.72")
