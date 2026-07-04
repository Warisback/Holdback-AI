# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: OAuth OK + all 3 ground-truth fixtures GREEN (NUMBERS CONFIRMED).
Write path wired (holdback/xero.create_bills + /new-bill form) but NO live bill created
yet. Org codes captured from the live Demo Company.

TESTS: 27 passed, 0 skipped. Engine matches all 3 fixtures exactly incl. tie-break.

ORG VALUES (Demo Company UK, confirmed from /accounts + /taxrates):
- CIS Labour Expense account = 321 (Xero applies CIS here)
- CIS Materials Purchased account = 322 (materials, excluded from CIS)
- VAT TaxType = INPUT2 ("20% (VAT on Expenses)", ACTIVE)

OPEN QUESTIONS (escalate exactly as written):
1. "Which contact is set up as a CIS SUBCONTRACTOR (in that contact's CIS Settings)?"
   Xero only applies the deduction if the bill's contact is flagged as a subcontractor.
   Org-level contractor mode is on, but a specific subcontractor contact must exist.
   (CISSettings field names still to be echoed via /cis/<id> once we know the contact.)
2. "Pay-now bill on first write: DRAFT (review then approve) or AUTHORISED now?"
   Form default = DRAFT.

DECISIONS MADE THIS SESSION:
- Half-penny tie-break = ROUND_HALF_DOWN (Option B, accountant-CONFIRMED).
- Pay-now labour is the reconciliation plug; residue lands there.
- All 3 ground-truth fixtures match exactly (NUMBERS CONFIRMED).
- Bills: Type=ACCPAY, Exclusive, labour->321, materials->322, TaxType INPUT2, NO CIS
  line (Xero deducts at approval). Retention always DRAFT + due-dated; pay-now default DRAFT.
- UnitAmount sent as 2dp string; flip to float only if Xero rejects.
- Scopes granular-only; writes need accounting.invoices (add + reconnect before first write).

NEXT STEP: first live write. User: (a) add accounting.invoices to XERO_SCOPES, restart app,
reconnect; (b) confirm which contact is the CIS subcontractor; (c) open /new-bill, pick that
contact, leave Candidate 1 prefilled, click Create. Then verify the two bills in Xero.
