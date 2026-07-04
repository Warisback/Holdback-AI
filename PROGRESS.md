# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: STEP 2 complete (tranche splitter wired end-to-end). Core flow verified
live earlier (Candidate 1: CIS £190 pay-now, £10 retention). NEXT: STEP 3 dashboard
grouping + lifecycle (Held/Released/Paid from Xero status).

DONE:
- Split engine (ROUND_HALF_DOWN tie-break) — 3 ground-truth fixtures green.
- OAuth (prompt=consent) + read/write to Xero; scopes incl. accounting.invoices.
- STEP 1: /upload (pdfplumber -> Gemini, provider-agnostic, anthropic stubbed; strict
  {value,confidence}; any failure -> blank confirm, never crashes) + /confirm (editable,
  amber Stretch A <0.8, Skip-PDF manual). Terms persist per contact, prefill /new-bill.
- STEP 2: split_tranches (list-based, hard-guarded <=2, rule 7) wired via
  build_accpay_bills -> {pay_now, retention_bills[]}; /new-bill has trigger1/trigger2
  (share%+date); Trigger 2 blank => single release. Refs "HoldBack (retention 1/2)"/"(2/2)"
  or "(retention)" for single. Fixtures T1/T2 + composition C1 locked and green.
- /dashboard: retention held sorted by release date; Release re-reads CIS then approves.

TESTS: 46 passed, 0 skipped.

OPEN QUESTIONS:
- (housekeeping) CISSettings field names still not echoed — print on next /dashboard
  Release run (or hit /cis/<24-locks-id>).

KEY DECISIONS:
- Tie-break ROUND_HALF_DOWN (Option B); pay-now labour is the plug.
- Bills: ACCPAY, Exclusive, NO CIS line (Xero deducts at approval); retention DRAFT +
  due-dated; VAT added on top (Total = net x 1.2).
- Splitter list-based, hard-guarded to <=2 tranches (rule 7); durable roadmap in CLAUDE.md.
- Tranche fixtures derived independently by review layer from spec and matched against
  implementation output (rule 7 deviation recorded: dual independent derivation replaced
  user hand-calc under time pressure).

NEXT STEP: STEP 3 — dashboard: group by job/contact with per-job subtotal ("£X held across
N invoices"), lifecycle from Xero Status (DRAFT=Held, AUTHORISED=Released, PAID=Paid),
soonest-first within groups, Released/Paid greyed, total-held = DRAFT tranches only.
Then Stretch B, then rehearse -> git tag demo-safe -> Jira board polish (<=90 min).
