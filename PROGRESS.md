# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: split engine green. OAuth scaffold written but NOT yet run —
reaching "OAuth OK" needs the client secret + a live browser consent + a successful
GET Organisation.

TESTS: 15 passed, 2 skipped (the 2 skips = ground-truth fixture slots, still empty).
No fixture deltas — the 3 hand-calculated fixtures have not been supplied yet.

OPEN QUESTIONS (escalate exactly as written):
1. "Here are 3 inputs — what are the exact expected pay-now / retention labour &
   materials pennies?" Need the 3 ground-truth fixtures; will assert against them and
   STOP on any delta rather than edit a fixture.
2. "Which exact granular scope authorises creating + approving ACCPAY *bills* —
   accounting.bills or accounting.invoices?" (App is post-2-Mar-2026 = granular ONLY;
   broad accounting.transactions is unavailable. Reads confirmed fine on
   accounting.settings.read + accounting.contacts.read + offline_access.)
3. "What are the exact field names returned by GET Contacts/{id}/CISSettings, and the
   exact name of the org's standard 20% VAT-on-expenses TaxType?" (Echo before use.)

DECISIONS MADE THIS SESSION:
- Half-penny tie-break = ROUND_HALF_DOWN (Option B, accountant-CONFIRMED). See
  holdback/split_engine.py "RESOLVED TIE-BREAK".
- Pay-now labour is the reconciliation plug; all rounding residue lands there.
- Xero access via direct HTTP (requests) — no Xero MCP connected this session.
- Xero scopes are granular-ONLY (app created after 2 Mar 2026); reads use
  accounting.settings.read + accounting.contacts.read; broad scopes unavailable.
- Minute 0-15 gate CLEARED: CIS is enable-able in Demo Company (UK), contractor mode set
  (confirmed via Financial settings screen, 4 Jul 2026).

NEXT STEP: user generates the client secret at developer.xero.com, pastes it into .env
(XERO_CLIENT_SECRET), runs `pip install -r requirements.txt` then `python app.py`, and
clicks "Connect to Xero" to complete consent -> app prints the org name.
