# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: split engine green + all 3 ground-truth fixtures GREEN (user sent
NUMBERS CONFIRMED). OAuth OK (Demo Company connected, reads working). ACCPAY bill
payload builder (holdback/bills.py) written + tested, but NOT yet POSTed to Xero.

TESTS: 27 passed, 0 skipped. The engine reproduces all 3 hand-calculated fixtures
exactly, including the tie-break (5.005->5.00, 2.515->2.51). No fixture deltas.

OPEN QUESTIONS (escalate exactly as written):
1. Before the first live write, fetch from the live org (reads only, scope already held;
   routes added): CIS Labour Expense account code + materials expense account code
   (/accounts), the exact 20% VAT-on-expenses TaxType (/taxrates), one CIS-subcontractor
   ContactID (/contacts), and the raw CISSettings JSON (/cis/<id>) — echo its field names
   before relying on them.
2. "Pay-now bill: create AUTHORISED now (fixes CIS at today's rate) or DRAFT so you can
   eyeball it in Xero and approve by hand?" Coded default = AUTHORISED. Retention bill is
   ALWAYS DRAFT until release regardless.

DECISIONS MADE THIS SESSION:
- Half-penny tie-break = ROUND_HALF_DOWN (Option B, accountant-CONFIRMED). See
  holdback/split_engine.py "RESOLVED TIE-BREAK".
- Pay-now labour is the reconciliation plug; all rounding residue lands there.
- All 3 ground-truth fixtures match the engine exactly (NUMBERS CONFIRMED).
- Bill payloads: Type=ACCPAY, LineAmountTypes=Exclusive, labour->CIS account,
  materials->normal account, one VAT TaxType/line. NO CIS line (Xero deducts at approval).
  Pay-now default AUTHORISED; retention always DRAFT + due-dated to release.
- UnitAmount sent as 2dp string; flip to float only if Xero rejects on first write.
- Xero via direct HTTP (no MCP). Scopes granular-only: reads = settings.read +
  contacts.read; writes = accounting.invoices (add at write step, triggers re-consent).

NEXT STEP: first live write. User: (a) add accounting.invoices to XERO_SCOPES + reconnect;
(b) paste /accounts + /taxrates + a ContactID + /cis/<id> output. Then I wire the POST and
create the two bills (pay-now + draft retention) for one candidate and we verify in Xero.
