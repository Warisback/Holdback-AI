# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: FIRST LIVE WRITE done. /new-bill created two ACCPAY DRAFT bills in
the Demo Company for Candidate 1 (contact "24 Locks"): pay-now net £1,425 (labour £950
@321 + materials £475 @322), retention net £75 (£50 + £25), due ~2026-12-31. Xero adds
20% VAT (INPUT2) on top, so shown Totals are £1,710 / £90 — net split is correct.

TESTS: 27 passed, 0 skipped. Engine matches all 3 fixtures incl. tie-break.

VERIFYING NOW (user): approve the pay-now bill in Xero and confirm CIS = £190 (20% of the
£950 labour line only; materials untouched).

OPEN QUESTIONS (escalate exactly as written):
1. "Once approved, does the pay-now bill show CIS £190 withheld on the £950 labour line?"
   (Confirms the contact's 20% rate + CIS account coding are wired correctly.)

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
