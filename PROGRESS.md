# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: FIRST LIVE WRITE VERIFIED end-to-end. /new-bill created two ACCPAY
DRAFT bills for Candidate 1 (contact "24 Locks"), and Xero computed CIS correctly:
- Pay-now: net £1,425 (labour £950 @321 + materials £475 @322), VAT £285, Total £1,710,
  CIS deduction £190 (20% of £950 labour), Amount Due £1,520.
- Retention: net £75, VAT £15, Total £90, CIS £10 (preview), due 2026-12-31.
Materials never touched by CIS. The whole split -> bills -> CIS chain is proven.

TESTS: 27 passed, 0 skipped. Engine matches all 3 fixtures incl. tie-break.

OPEN QUESTIONS (escalate exactly as written):
- (none blocking) Need an Anthropic API key to build PDF extraction (priority #2).

DECISIONS MADE THIS SESSION:
- Half-penny tie-break = ROUND_HALF_DOWN (Option B, accountant-CONFIRMED).
- Pay-now labour is the reconciliation plug; residue lands there.
- All 3 ground-truth fixtures match exactly (NUMBERS CONFIRMED).
- Bills: Type=ACCPAY, Exclusive, labour->321, materials->322, TaxType INPUT2, NO CIS line
  (Xero deducts at approval). Retention always DRAFT + due-dated; pay-now chosen DRAFT for
  the first write. VAT (20%) is added on top by Xero -> Total = net x 1.2.
- Xero scope gate was NOT the reference list on the config page; fix was prompt=consent on
  the authorize URL so Xero re-shows consent and grants accounting.invoices.
- Scopes now granted: settings.read, contacts.read, offline_access, accounting.invoices.

NEXT STEP: after CIS is verified, build the priority-2/3 pieces — PDF term extraction
(one Anthropic call -> {field:{value,confidence}}) + an editable confirm screen that
feeds /new-bill. Then the dashboard (retention held, sort by release date, approve button).
