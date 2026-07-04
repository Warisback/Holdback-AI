# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: STEP 1 done (PDF extraction + editable confirm screen + Stretch A).
Core flow already verified live (Candidate 1: CIS £190 pay-now, £10 retention).
NEXT: STEP 2 tranche splitter (needs user's hand-calc T1/T2 to lock fixtures).

DONE:
- Split engine (ROUND_HALF_DOWN tie-break) — 3 ground-truth fixtures green.
- OAuth (prompt=consent) + read/write to Xero; scopes incl. accounting.invoices.
- /new-bill -> two ACCPAY bills (labour 321 / materials 322 / INPUT2); first write verified.
- /dashboard: retention held sorted by release date; Release button re-reads CIS then approves.
- STEP 1: holdback/extract.py (pdfplumber text -> Gemini, provider-agnostic, anthropic
  stubbed; strict JSON {value,confidence}; ANY failure -> empty_terms -> blank screen).
  /upload (PDF) and /confirm (editable, amber Stretch A when confidence<0.8, "Skip PDF"
  manual entry). Confirmed terms saved per contact (terms_store.json) and prefill /new-bill.

TESTS: 28 passed, 0 skipped.

OPEN QUESTIONS (escalate exactly as written):
1. STEP 2 fixtures — CONFIRM these computed tranche outputs match your hand-calc, then I
   lock them + wire the live 2-tranche path (STOP on any delta):
   T1 (350.01/150.00, 50/50) -> t1 (175.00, 75.00), t2 (175.01, 75.00).
   T2 (333.33/166.67, 60/40) -> t1 (200.00, 100.00), t2 (133.33, 66.67).
2. (housekeeping) CISSettings field names still not echoed — will print on the next
   /dashboard Release run (or via /cis/<id>).

KEY DECISIONS:
- Tie-break ROUND_HALF_DOWN (Option B); pay-now labour is the plug.
- Bills: ACCPAY, Exclusive, NO CIS line (Xero deducts at approval); retention DRAFT +
  due-dated; VAT added on top (Total = net x 1.2).
- Extraction = Gemini (EXTRACT_PROVIDER/MODEL in .env), wrapper provider-agnostic; never
  crashes the flow (blank confirm on failure). Durable ROADMAP now lives in CLAUDE.md.
- Splitter list-based, hard-guarded to <=2 tranches (rule 7); engine + structural tests
  built (41 passed); exact T1/T2 fixtures + live 2-tranche wiring pending confirmation.

NEXT STEP: build STEP 2 tranche splitter as a LAYER on the verified engine (list-based,
hard-guarded to <=2 tranches per rule 7). Present computed T1/T2 for confirmation, then
lock fixtures + wire two-tranche bills into build_accpay_bills + /new-bill + /confirm.
