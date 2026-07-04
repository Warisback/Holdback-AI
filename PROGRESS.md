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
1. STEP 2 fixtures — confirm my computed tranche outputs match your hand-calc for
   T1 (labour_r 350.01, materials_r 150.00, 50/50) and T2 (labour_r 333.33,
   materials_r 166.67, 60/40) BEFORE I lock exact-value asserts. STOP on any delta.
2. (housekeeping) CISSettings field names still not echoed — will print on the next
   /dashboard Release run (or via /cis/<id>).

KEY DECISIONS:
- Tie-break ROUND_HALF_DOWN (Option B); pay-now labour is the plug.
- Bills: ACCPAY, Exclusive, NO CIS line (Xero deducts at approval); retention DRAFT +
  due-dated; VAT added on top (Total = net x 1.2).
- Extraction = Gemini (EXTRACT_PROVIDER/MODEL in .env), wrapper provider-agnostic; never
  crashes the flow (blank confirm on failure). Durable ROADMAP now lives in CLAUDE.md.

NEXT STEP: build STEP 2 tranche splitter as a LAYER on the verified engine (list-based,
hard-guarded to <=2 tranches per rule 7). Present computed T1/T2 for confirmation, then
lock fixtures + wire two-tranche bills into build_accpay_bills + /new-bill + /confirm.
