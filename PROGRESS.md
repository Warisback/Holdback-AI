# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: DASHBOARD built. Core flow verified live earlier (Candidate 1:
pay-now CIS £190, retention CIS £10, materials untouched). Remaining: PDF extraction +
confirm screen (priority #2/#3), then stretch A/B.

DONE:
- Split engine (pure, tie-break ROUND_HALF_DOWN) — all 3 ground-truth fixtures green.
- OAuth (prompt=consent fix) + read/write to Xero. Scopes: settings.read, contacts.read,
  offline_access, accounting.invoices.
- /new-bill: split -> two ACCPAY bills (labour 321 / materials 322, INPUT2 VAT). First
  live write verified in Xero.
- /dashboard: retention held across jobs, sorted by release date; "Release (approve)"
  button re-reads the contact's CIS rate then AUTHORISES the draft retention bill.
- Bills tagged Reference "HoldBack (pay now)" / "HoldBack (retention)" so the dashboard
  can filter retention bills.

TESTS: 28 passed, 0 skipped.

OPEN QUESTIONS:
- Need an Anthropic API key (ANTHROPIC_API_KEY in .env) to build PDF extraction (#2).

KEY DECISIONS:
- Tie-break ROUND_HALF_DOWN (Option B, accountant-confirmed); pay-now labour is the plug.
- Bills: Type=ACCPAY, Exclusive, NO CIS line (Xero deducts at approval); retention always
  DRAFT + due-dated; VAT added on top by Xero (Total = net x 1.2).
- Release button re-fetches CISSettings before approving (rate-at-payment rule); best-effort
  (Xero applies the current rate on approval regardless).

NEXT STEP: user smoke-tests /dashboard (create 2-3 retention bills via /new-bill with
different subcontractors + release dates, confirm sort order, release one). Then build PDF
extraction + editable confirm screen (needs Anthropic key).
