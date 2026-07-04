# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: STEPS 1-5 built. Tag `demo-safe` marks the functional baseline
(pre-design-pass fallback). Remaining: Stretch B (demo prep), a live click-through +
screenshots, and optional Step 6 (edit-terms).

DONE:
- Split engine (ROUND_HALF_DOWN tie-break) — 3 ground-truth fixtures green.
- OAuth (prompt=consent) + read/write; scopes incl. accounting.invoices.
- STEP 1: /upload (pdfplumber -> Gemini; strict {value,confidence}; any failure -> blank
  confirm, never crashes) + /confirm (editable, amber Stretch A <0.8, Skip-PDF manual);
  terms persist per contact and prefill /new-bill.
- STEP 2: split_tranches (list-based, guarded <=2, rule 7) wired: /new-bill trigger1/
  trigger2 (share%+date) -> build_accpay_bills {pay_now, retention_bills[]}; refs
  "(retention 1/2)"/"(2/2)" or "(retention)". Fixtures T1/T2 + composition C1 locked.
- STEP 3: /dashboard lifecycle from Xero status (DRAFT=Held, AUTHORISED=Released,
  PAID=Paid); "held £X across N jobs" = DRAFT tranches only.
- STEP 5: static/holdback.css (design tokens, self-contained, no CDN/pico); site-wide
  page shell + header via after_request; dashboard = 3-column Jira-style board (cards,
  chips, tranche pills, Released/Paid greyed); money formatted £1,234.56 tabular; amber
  low-confidence = 3px left-border + #FFF8E6.

TESTS: 46 passed, 0 skipped.

OPEN / TODO:
- Stretch B (demo prep, not code): run a messy-phrasing contract ("five per cent",
  "moiety on practical completion") through /upload — same pipeline, no parser changes.
- USER: live click-through of /, /new-bill, /confirm, /dashboard + screenshots. If any
  flow breaks after the design pass, revert the template change (not the CSS) — demo
  runs from tag `demo-safe`.
- (housekeeping) CISSettings field names still not echoed — print on next Release run.

KEY DECISIONS:
- Tie-break ROUND_HALF_DOWN (Option B); pay-now labour is the plug.
- Bills: ACCPAY, Exclusive, NO CIS line (Xero deducts at approval); retention DRAFT +
  due-dated; VAT on top (Total = net x 1.2).
- Splitter list-based, hard-guarded to <=2 tranches (rule 7); roadmap in CLAUDE.md.
- Tranche fixtures derived independently by review layer from spec and matched against
  implementation (rule 7 deviation: dual independent derivation replaced user hand-calc).
- Design pass is self-contained CSS (skipped pico CDN to honour "no CDN downloads").

NEXT STEP: user does the click-through + screenshots (and Stretch B). Then Step 6
(edit-terms) only if time — v1.1 in CLAUDE.md roadmap.
