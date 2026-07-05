# PROGRESS — HoldBack session bridge

CURRENT MILESTONE: UI v3 rebuilt to the two Claude Design exports (Home = New-bill entry;
Dashboard = forecast) + a full readiness/security pass (5-lens audit, 70 findings addressed).
Committed at 296b386. 47 tests pass; every route renders 200. Core flow verified live earlier
(Candidate 1: pay-now CIS £190 in Xero).

TESTS: 47 passed, 0 skipped. All routes render via the test client.

OPEN QUESTIONS / TODO (escalate exactly as written):
- USER hasn't done a live click-through of the new UI yet (Home upload, dashboard, release,
  CIS return, statement, reminders). After restart, RECONNECT to Xero ONCE (FLASK_SECRET
  changed, so the old signed session is invalid).
- Does the CIS-return "CIS deducted" column populate? It reads Xero's CISDeduction on each
  bill and only appears once a bill is approved. Verify on the live org.
- Xero deep link uses View.aspx?InvoiceID=<guid>; confirm it lands on the right bill.
- Which automation next: CIS month-end pack / subbie verify+rate check / deadline reminders?
  And the outbound "chase" drip (subcontractor-side, needs a retention-receivable data model).

KEY DECISIONS:
- Tie-break ROUND_HALF_DOWN (Option B, accountant-confirmed); pay-now labour is the plug.
- Tranche splitter list-based, hard-guarded to <=2 tranches (rule 7); roadmap in CLAUDE.md.
- Bills: Type=ACCPAY, Exclusive, NO CIS line (Xero deducts at approval); retention always
  DRAFT + due-dated; pay-now needs a due date (defaults to bill date); VAT on top (Total=net*1.2).
- Scopes granular-only; writes = accounting.invoices. Xero via direct HTTP (no MCP connected).
- Removed dead/insecure routes: /contacts, /cis (Xero 404s CISSettings), /accounts, /taxrates.
- Security: Flask debug OFF by default (FLASK_DEBUG=1 to enable); FLASK_SECRET has no known
  fallback; all dynamic Xero values HTML-escaped (was stored-XSS); Xero reads guarded
  (before_request gate + global error handler); CSV formula-injection-safe.
- Nav = New bill / Dashboard / CIS return / Reminders; tagline removed; content centered per
  page (home 1120 / dashboard+wide 1280 / forms 720); copy has zero em-dashes (verified).
- Fonts via Google Fonts CDN with system fallbacks (deviates from the earlier no-CDN rule,
  per the design direction).
- Design MCP needs interactive /design-login (unavailable in this session): user exports the
  .dc bundle into the repo and we extract it. Sources gitignored: design/home.html, design/forecast.html.

NEXT STEP: user restarts, reconnects once, and does the click-through; report anything off.
Then choose the next automation to build.
