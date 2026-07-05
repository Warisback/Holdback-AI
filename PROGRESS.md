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
- STEP 5 + REDESIGN: static/holdback.css now uses the Claude editorial design language
  (cream canvas, coral primary, serif display via Cormorant Garamond + Inter). App shell
  is a Jira-style LEFT SIDEBAR (Dashboard/New bill/Contracts/Contacts) + content area,
  wrapped site-wide via after_request. Dashboard = 3-column board (Held/Released/Paid)
  with cards, chips, tranche pills, page-head + primary action. Home = clean overview
  tiles (scopes moved to small diagnostics). Money £1,234.56 tabular; amber low-confidence
  survives (3px left-border + tint). Fonts load from Google Fonts CDN with system fallbacks.

FEATURES (stand-out set, all wired + rendering):
- CIS monthly return (/cis-return) grouped per subcontractor (labour/materials/CIS deducted)
  + CSV export; per-subbie Payment & Deduction Statement (/statement/<id>).
- Release forecast (/forecast): pure-CSS bar chart of retention releasing over 12 months.
- Reminders: "releasing in the next 30 days" banner on the dashboard.
- Xero deep links on every dashboard card ("Xero ↗").
- Term risk flags on the confirm screen (deterministic: >5%/0% retention, missing trigger
  date, shares not summing to 100, trigger 2 condition w/o date).
Sidebar nav now: Dashboard / New bill / Contracts / CIS return / Forecast / Contacts.

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
