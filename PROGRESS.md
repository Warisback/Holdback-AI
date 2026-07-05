# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: UI v3 (blue issue-tracker) rebuilt to the two Claude Design exports +
a full readiness pass (5-lens audit, 70 findings addressed). Core flow verified live
earlier (Candidate 1: CIS £190). 47 tests pass; every route renders.

DONE:
- Split engine (ROUND_HALF_DOWN tie-break) + tranches; ground-truth fixtures green.
- OAuth (prompt=consent); read/write to Xero; scopes incl. accounting.invoices.
- Create flow: Home (/) = New-bill entry (2-col: headline + 3-step rail + PDF dropzone).
  "Enter manually" -> /new-bill directly. PDF -> /upload POST -> /confirm review -> saves
  terms -> /new-bill. /confirm is post-PDF only (GET redirects to /new-bill), themed.
- Dashboard = forecast: KPI card + "releasing by month" bar chart + Upcoming-releases table
  (due-soon amber, in-N-days, INV->Xero link, outlined Release). Absorbs the old board and
  the /forecast page (/forecast redirects to /dashboard).
- CIS return (+ CSV, formula-injection-safe) + per-subcontractor statement. Reminders drip
  (mailto). New bill: pay-now due date + 30d.
- Nav trimmed to 4 tabs: New bill / Dashboard / CIS return / Reminders. Tagline removed.
  Removed dead/insecure routes: /contacts, /cis (404), /accounts, /taxrates.
- Security/readiness: debug OFF by default (FLASK_DEBUG=1 to enable); FLASK_SECRET no longer
  falls back to a known string (real value in .env, placeholder in .env.example); all Xero
  reads guarded (before_request connection gate + global error handler, no raw tracebacks or
  scope leaks); every dynamic Xero value HTML-escaped (was stored-XSS); tables in scroll
  wrappers; responsive breakpoints (960/820); app bar full-width, content centered per page
  (home 1120 / dashboard+wide 1280 / forms 720).
- Copy: professional, British, NO em-dashes / &mdash; / &middot; (verified 0 in rendered HTML).

TESTS: 47 passed, 0 skipped.

DESIGN SOURCES (gitignored): design/home.html, design/forecast.html (extracted from the
Claude Design .dc bundles the user dropped in; the design MCP needs interactive /design-login).

NEXT: live click-through on the new UI; then optional automations (CIS month-end pack,
subbie verify, deadline reminders) and the outbound "chase" drip variant.
