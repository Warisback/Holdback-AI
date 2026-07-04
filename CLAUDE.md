# HoldBack — UK construction retention & CIS agent for Xero

**Xero hack 2026 · solo build · ~13 h.** The user is personally responsible for
reviewing every piece of accounting logic before it touches real Xero data.
This file is the durable source of truth (survives session restarts / context
compaction). Where the base brief and the addendum conflict, **the addendum wins**
— it exists to resolve conflicts.

---

## CRITICAL OPERATING RULES — re-read every session

1. **HARD GATE.** No code path that *writes* to Xero may **execute** until the user
   sends the exact message `NUMBERS CONFIRMED`. Reads (e.g. `GET Organisation`,
   `GET Contacts/{id}/CISSettings`) and pure logic (split engine, tests) are fine
   before then.
2. **Minute 0–15, BEFORE any OAuth code (USER ACTION — Claude cannot do this):**
   open the **Demo Company (UK)**, verify **CIS can be ENABLED** at org level,
   enable contractor mode, set one contact as a CIS subcontractor.
   **If CIS cannot be enabled → STOP and tell the user** (plan changes: fresh UK trial org).
3. **Journal ban.** Never post a manual journal (debit CIS Labour Expense / credit
   retention liability). That is a *competing* method to the two-bill split;
   combining them double-counts. **Split method only.**
4. **No "single bill line" workaround** (zero-rating the retention line so Xero
   ignores it for CIS). It permanently excludes retention from CIS assessment →
   under-deducts tax. Confirmed flawed. Do not implement.
5. **Never hardcode or cache the CIS rate.** Read the contact's *current* rate via
   the Xero API every time an amount is fixed. Timing (addendum): **pay-now bill →
   read rate at split time; retention bill → re-fetch `CISSettings` immediately
   before APPROVING at release.** Xero fixes the deduction from the contact's rate
   at approval; HMRC CISR15040 requires the rate at date of payment.
6. **Retention bill = DRAFT at split time; APPROVE only at release** via the
   dashboard button. Retention cost hitting P&L at release is an accepted demo
   simplification.
7. **Test fixtures are ground truth.** The user hand-calculates expected outputs.
   Write pytest asserts against **their** numbers. **If code and a fixture disagree,
   STOP and show the delta — never edit a fixture to make a test pass.**
8. **When uncertain about CIS/retention treatment, STOP and flag it explicitly** —
   do not guess a plausible default. The user has limited windows with an
   accountant and an on-site Xero API mentor and needs the exact question to ask.
9. **Be verbose about WHY** in the split/CIS code — it must be auditable cold,
   without re-deriving the reasoning.
10. **Confirmation screen is a FEATURE**, not a limitation to remove. Every field on
    it is EDITABLE, so it doubles as manual entry and the demo can't die on a parse miss.

---

## What this does

1. **PDF upload** → one Anthropic API call extracts, as strict JSON. **Every field is
   wrapped as `{value, confidence: 0-1}`** — BOUNTY-01, schema change is IMMEDIATE
   (using the confidence in the UI is Stretch A, not required for the core flow):
   `{retention_pct:{value,confidence}, trigger1:{condition:{value,confidence},
   pct:{value,confidence}, expected_date:{value,confidence}}, trigger2:{...},
   contract_value:{value,confidence}}`.
2. **Confirm screen** (editable) shown before anything is written to Xero.
   "Practical completion" is a *condition, not a date* — the screen asks the user for
   an **expected date per trigger**; that date due-dates the draft retention bill and
   drives dashboard sorting.
3. **Entry point = OUR app** (fields: `total, labour amount, materials amount,
   subcontractor, date`; PDF optional later). The app creates **both bills**.
   Do NOT build Xero webhook-watching or void-and-replace of natively-created bills.
4. On invoice, split into **two `ACCPAY` bills**:
   - **Pay-now bill** = full amount − retention %, created at split time.
   - **Retention bill** = the retention %, created as **DRAFT**, due-dated to the
     release trigger, approved later from the dashboard.
5. Both bills split **proportionally by LABOUR vs MATERIALS** (the original ratio),
   not as a lump sum. Labour lines → **CIS Labour Expense** account code (Xero applies
   CIS there); materials lines are **excluded from the CIS base**.
6. **Dashboard**: functional table of retention held per job, sortable by release
   date, with a button to raise/approve the retention bill. No visual polish.

---

## Verified accounting logic — HMRC CISR15040 (primary source, do not deviate)

- "There are no special rules for retention payments. They are treated in the same
  way as any other payments. Whether the retention payment is made gross or under
  deduction depends on the subcontractor's payment status **at the date of payment**,
  not when the work was done."
- The retention payment can be partly a contract payment and partly a materials
  reimbursement (hence the labour/materials split).
- Subcontractor status (0 % / 20 % / 30 %) can change during a multi-month/year
  retention period → always read the **current** rate (see rule 5).

---

## API specifics — DO NOT GUESS

- These are **BILLS**: **Invoices** endpoint, **`Type="ACCPAY"`** everywhere. **Never `ACCREC`.**
- Current CIS rate: **`GET Contacts/{ContactID}/CISSettings`** (UK orgs). **Verify the
  exact field names in the first live session and echo them to the user before use.**
- OAuth: redirect URI **`http://localhost:5000/callback`** — exact match, no trailing
  slash, `localhost` not `127.0.0.1`. Scopes **must include `offline_access`** (access
  tokens expire ~30 min; build is ~13 h). Post-March-2026 **granular scopes** — confirm
  exact scope names for Contacts, Invoices/Bills, Organisation before assuming old broad scopes.
- `LineAmountTypes="Exclusive"`; **one fixed `TaxType` on every line** — the demo org's
  standard **20 % VAT-on-expenses** code (**confirm its exact name in the org first**).
  Domestic reverse charge is **deliberately out of scope**.
- **Xero MCP server** may become available — if so, prefer its tools over raw HTTP.
  **Ask the user to confirm it's connected before assuming.**
- Contacts must be set up as CIS subcontractors (Contacts → CIS Settings) before
  CIS-coded bills can be created — Xero prerequisite, not optional.

---

## Split / rounding rule — MUST be tested

Round each line to 2dp, then these three reconciliations hold **exactly**:
1. `pay_now_total + retention_total == original total`
2. labour across both bills `== original labour`
3. materials across both bills `== original materials`

Precondition: `labour + materials == total`. Any penny residue goes onto the
**pay-now LABOUR line** (over-deducting a penny of CIS is safe; under-deducting is not).
Adversarial fixture (must pass): **total £1,234.56, 71.3 % labour, 5 % retention**,
asserting all three.

---

## Build order & priorities (if time runs short, stop after each is solid)

1. **Correct split logic** (pure, isolated, testable — build FIRST, verify by hand).
2. Working end-to-end flow on **one** PDF format.
3. Confirmation screen.
4. Minimal dashboard.
5. **Stretch A** — amber low-confidence highlight (only after the dashboard works). See BOUNTY-01.
6. **Stretch B** — messy-phrasing test contract (demo prep, not code). See BOUNTY-01.

Stop after Stretch B — no visual polish beyond Stretch A's amber highlight, no second
PDF *format* support, no edge cases (multi-site, VAT reverse charge, re-verification
thresholds) unless everything above is solid.

**Stack:** Python backend, basic React frontend. **Milestone commits:** OAuth OK /
split engine green / first live write / confirm screen / dashboard.

---

## BOUNTY-01 additions (do not reorder core priorities)

- **Extraction confidence — IMMEDIATE schema change.** Every extracted field returns
  `{value, confidence: 0-1}`, not a bare value. Change the extraction schema now;
  *using* the confidence in the UI is a stretch goal (Stretch A), not core.
- **Stretch A — amber low-confidence highlight (only after the dashboard works).** On
  the confirm screen, highlight any field with `confidence < 0.8` in amber. That is the
  **only** additional styling permitted — no other visual work.
- **Stretch B — messy-phrasing test (demo prep, not code).** Run a second test contract
  with awkward wording ("five per cent", "moiety on practical completion") through the
  **same** pipeline to show robustness. **NOT** second-format support — no parser changes.
- **Priority order now:** split engine → e2e on one PDF → confirm screen → dashboard →
  Stretch A → Stretch B. Stop there.

---

## Verbatim briefs (for audit)

<details><summary>Base brief</summary>

```
PROJECT: HoldBack — UK construction retention & CIS agent for Xero
CONTEXT: Solo hackathon build, ~13 hours total remaining, no partner. I need you to
act as my second set of hands on implementation while I stay personally responsible
for reviewing every piece of accounting logic before it touches real Xero data.

WHAT THIS DOES
1. User uploads a subcontract PDF. Extract: retention %, release trigger 1 (condition
   + %), release trigger 2 (condition + %), contract value.
2. Show extracted terms on a "please confirm" screen before anything is written to
   Xero. This confirmation step is a FEATURE (trust/audit trail), not a limitation to
   remove for "full automation."
3. Once confirmed, when this subcontractor is invoiced: split the bill into two Xero
   invoices — "Pay now" invoice: full amount minus retention %; "Retention held"
   invoice: the retention %, due-dated to the release trigger.
4. Both invoices must be split proportionally by LABOUR vs MATERIALS, matching the
   original invoice's ratio — not treated as a lump sum. Labour-coded lines use the
   CIS Labour Expense account code; materials lines are excluded from the CIS base.
5. Dashboard: a basic table of retention currently held across jobs, sortable by
   release date, with a button to raise the retention invoice. Functional only.

THE VERIFIED ACCOUNTING LOGIC — DO NOT DEVIATE  (HMRC CISR15040):
- "There are no special rules for retention payments. They are treated in the same way
  as any other payments. Whether the retention payment is made gross or under deduction
  depends on the subcontractor's payment status at the date of payment, not when the
  work was done."
- "The retention payment can also be made up of different components... partly a
  contract payment due, and partly a payment reimbursing the subcontractor for
  materials supplied for the contract."
- Subcontractor status (0%/20%/30%) can change during a multi-month/year retention
  period. ALWAYS read the contact's CURRENT CIS status via the Xero API at the moment
  each invoice is created — never cache or reuse the rate from the original invoice.

DO NOT BUILD, EVEN IF IT SEEMS SIMPLER OR FASTER
- A manual journal correction (debit CIS Labour Expense / credit retention liability) —
  different, competing method to the two-invoice split. Combining both double-counts.
- The "Single Bill Line" workaround (post-retention labour on one line, zero-rate the
  retention on a separate line so Xero "ignores" it for CIS) — permanently excludes the
  retention from CIS assessment, which under-deducts tax. Confirmed flawed.
- Any hardcoded CIS rate — always read the contact's actual rate via the API.

TECH CONTEXT
- Xero Developer account + Demo Company org (UK/GB edition), OAuth app registered
- Redirect URI: http://localhost:5000/callback (exact — no trailing slash, "localhost"
  not "127.0.0.1")
- Post-March-2026 granular OAuth scopes — confirm exact scope names for Contacts,
  Invoices/Bills, Organisation before assuming old broad scopes apply
- Xero MCP server may be available — if so, use its tools; ask to confirm first
- Stack: Python backend, basic React frontend
- Contacts must be set up as CIS subcontractors before CIS-coded bills can be created

SOLO-SPECIFIC WORKING STYLE
- Build the bill-splitting engine as an ISOLATED, PURE, TESTABLE FUNCTION FIRST,
  separate from any API wiring. Manually verify output against hand-calculated examples
  before it touches live Xero data.
- When uncertain about correct CIS/retention treatment, STOP and flag it explicitly
  rather than guessing.
- Be more verbose than usual about WHY logic works, especially splitting/CIS code.
- Priority if time runs short: (1) correct split logic, (2) working end-to-end flow on
  one PDF format, (3) confirmation screen, (4) minimal dashboard. Stop there.

WHAT TO DO RIGHT NOW
Start with the OAuth flow and one successful test API call (GET Organisation) before
any business logic. Then build the bill-splitting function in isolation with 3-4
hardcoded example inputs so I can check its output by hand immediately. Do not wire it
to live Xero writes until I've confirmed the numbers are correct.
```
</details>

<details><summary>Addendum (resolves conflicts — authoritative)</summary>

```
CORRECTION TO ITEM 3 (critical): Create the retention bill as a DRAFT at split time;
APPROVE it only at release via the dashboard button. Xero fixes the CIS deduction from
the contact's rate at approval, and HMRC CISR15040 requires the rate at the date of
payment — so re-fetch the contact's CISSettings immediately before approving the
retention bill. "Read current rate at creation" means: pay-now bill → at split time;
retention bill → at RELEASE. Journal ban stands. Retention cost hitting P&L at release
is a known, accepted demo simplification.

API SPECIFICS — DO NOT GUESS:
- These are BILLS: Invoices endpoint, Type="ACCPAY", everywhere. Never ACCREC.
- Current rate: GET Contacts/{ContactID}/CISSettings (UK orgs). Verify the exact field
  names in the first live session and echo them to me before use.
- Scopes must include offline_access (tokens expire in ~30 min; build is 13h).
- LineAmountTypes="Exclusive"; one fixed TaxType on every line — use the demo org's
  standard 20% VAT-on-expenses code (confirm its exact name in the org first). Domestic
  reverse charge is deliberately out of scope.

FLOW ENTRY POINT: The subbie invoice enters through OUR app (fields: total, labour
amount, materials amount, subcontractor, date; PDF upload optional later). The app
creates both ACCPAY bills. Do NOT build Xero webhook-watching or void-and-replace of
bills created natively in Xero.

ROUNDING RULE (must be tested): Round each line to 2dp, then enforce three
reconciliations exactly: (1) payNow + retention == original total; (2) labour sums
across both bills == original labour; (3) materials sums == original materials. Push any
penny residue onto the pay-now LABOUR line (over-deducting a penny of CIS is the safe
direction; under-deducting is not). Include an adversarial fixture, e.g. total
£1,234.56, 71.3% labour, 5% retention, asserting all three.

TEST FIXTURES ARE GROUND TRUTH: I will hand-calculate expected outputs for 3 inputs and
supply them. Write pytest asserts against MY numbers. If code and fixture disagree, STOP
and show me the delta — never edit a fixture to make tests pass.

EXTRACTION + FALLBACK: PDF terms via one Anthropic API call returning strict JSON:
{retention_pct, trigger1:{condition, pct, expected_date}, trigger2:{...},
contract_value}. Every field on the confirm screen is EDITABLE — that screen doubles as
manual entry, so the demo cannot die on a parsing miss.

RELEASE DATES: "Practical completion" is a condition, not a date. The confirm screen
asks me for an expected date per trigger; that date due-dates the draft retention bill
and drives dashboard sorting.

WORKING PRACTICE:
- Save this entire brief as CLAUDE.md in the repo root FIRST.
- git init; commit at each milestone: OAuth OK / split engine green / first live write /
  confirm screen / dashboard.
- Hard gate: no code path that writes to Xero may execute until I send the exact message
  "NUMBERS CONFIRMED".
- Minute 0-15, before any OAuth code: open the Demo Company (UK) and verify CIS can be
  ENABLED at org level; enable contractor mode and set one contact as a CIS
  subcontractor. If the demo org cannot enable CIS, STOP and tell me — the plan changes
  (fresh UK trial org).
```
</details>

<details><summary>BOUNTY-01 additions</summary>

```
BOUNTY-01 ADDITIONS (do not reorder core priorities):
- Extraction JSON: every field returns {value, confidence: 0-1}. Schema change is
  IMMEDIATE; UI use is a stretch goal.
- STRETCH A (only after dashboard works): confirm screen highlights any field with
  confidence < 0.8 in amber. No other styling work.
- STRETCH B (demo prep, not code): second test contract with messy phrasing
  ("five per cent", "moiety on practical completion") through the SAME pipeline.
  No second format support.
- Priority order now: split engine → e2e on one PDF → confirm screen → dashboard →
  Stretch A → Stretch B. Stop there.
```
</details>
