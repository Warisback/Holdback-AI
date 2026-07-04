"""
HoldBack bill-splitting engine  —  PURE, ISOLATED, NO XERO, NO I/O.

WHAT THIS FILE DOES (and, just as important, what it does NOT do)
================================================================================
It takes ONE subcontractor bill and splits it into the two ACCPAY bills HoldBack
will create in Xero:

    pay-now bill   = (100% - retention%) of the work, paid now
    retention bill = retention% of the work, held back until a release trigger

Each of those two bills is split again into a LABOUR portion and a MATERIALS
portion, keeping the original labour:materials ratio. Why the second split
matters: in Xero the labour lines get coded to the CIS Labour Expense account
(so Xero applies the CIS deduction to them), while materials lines are coded to
a normal expense account and are EXCLUDED from the CIS base. If we split as a
lump sum we could not tell Xero which part is CIS-able. (HMRC CISR15040: a
retention payment can be "partly a contract payment due, and partly a payment
reimbursing the subcontractor for materials".)

WHAT THIS FILE DELIBERATELY DOES NOT DO
--------------------------------------------------------------------------------
1. It does NOT compute the CIS *deduction amount*. Xero does that, at APPROVAL,
   from the contact's CURRENT rate (0/20/30%). We must never hardcode or cache a
   rate. `indicative_cis()` below is a DISPLAY-ONLY preview for the confirm
   screen and must never be written to Xero.
2. It does NOT talk to Xero, read files, or read the clock. It is a pure
   function of its inputs so it can be unit-tested against hand-calculated
   numbers — which is the user's stand-in for a second reviewer.

THE ROUNDING CONTRACT (must always hold; enforced by assertions below)
--------------------------------------------------------------------------------
Every returned amount is quantised to 2dp, and:
    (1) pay_now.total + retention.total == original total
    (2) pay_now.labour + retention.labour == original labour
    (3) pay_now.materials + retention.materials == original materials

How we guarantee all three exactly despite rounding:
    - We round only the RETENTION side (ret_labour, ret_materials).
    - pay_materials is the exact remainder  materials - ret_materials  -> (3) exact.
    - pay_labour is the PLUG: total - ret_labour - ret_materials - pay_materials.
      This makes (1) hold by construction, and because materials already
      reconcile, it also forces (2) to hold. So every stray penny of rounding
      lands on the PAY-NOW LABOUR line.

Why push the residue onto pay-now labour specifically? Because CIS is deducted
from labour paid NOW. Letting pay-now labour absorb the penny means, on an exact
tie, we withhold one extra penny of CIS base now rather than one too few — the
safe direction (see the RESOLVED TIE-BREAK note below).

NB — keep the half-penny in perspective. The tie-break is the SMALL exposure. The
load-bearing constraint is reconciliation (2): labour across both bills == original
labour. Overstating materials (i.e. understating labour) on either bill is what
would create a real CIS under-deduction, and CIS340 puts that checking burden on
the contractor. Invariant (2), not the rounding tie, is the thing HMRC would care
about — lead with it.

PRECONDITION: labour + materials must equal total (to the penny). The three
reconciliations are only mutually satisfiable when the input is internally
consistent, so we refuse inconsistent input loudly rather than silently fudging
a figure the user would then have to reverse-engineer.

>>> RESOLVED TIE-BREAK — reviewed by the accountant contact, Option B, CONFIRMED <<<
When retention% * labour lands EXACTLY on a half-penny (e.g. £0.015), ret_labour
rounds DOWN, so the pay-now labour line (the CIS base paid now) keeps the extra
penny. Implemented as ROUND_HALF_DOWN on the retention lines only.

  IMPORTANT: this is ROUND_HALF_DOWN, NOT ROUND_DOWN. HALF_DOWN changes ONLY exact
  ties; non-tie amounts still round to nearest. ROUND_DOWN would truncate every
  line and understate retention by up to a penny on all of them — a different,
  more aggressive behaviour that would NOT read as reasonable care.

Why this direction (precise framing — do not overstate it):
  * FA 2004 s.61 attaches the deduction duty PER PAYMENT, on the non-materials
    element. Whichever way we split, Xero computes the statutorily correct
    deduction on that payment, so NEITHER option is an "under-deduction" and HMRC
    cannot raise a reg 13 (SI 2005/2045) determination against either. The
    tie-break is a derived posture choice, not compliance vs breach.
  * We still err toward the only direction the regime punishes (under-collection),
    and — more valuable — we create a documented, deliberate policy artefact:
    exactly the "reasonable care" evidence for a reg 9 Condition A direction (which
    relieves a contractor of under-deduction liability). Rounding the other way is
    the opposite kind of evidence.
  * Effect size is WEAKLY-more, never "always more": +1p of pay-now labour base
    raises the pre-Xero-rounding deduction by only 0.2p (20%) / 0.3p (30%), so after
    Xero rounds it is frequently IDENTICAL. Correct claim: "never less, occasionally
    1p more" (monotonic). Do NOT say "always more" — the flagship example ties.
  * Over-withholding costs the contractor nothing with HMRC: the penny goes to HMRC
    and is treated as tax paid by the subcontractor (FA 2004 s.62) — a company
    offsets it against monthly PAYE/NIC, a sole trader recovers via Self Assessment.
    It is NOT a "commercial" clawback against the contractor.
  * Property is PER-PAYMENT, not lifetime-invariant: if the sub's rate rises
    (20%->30%) before release, the retained penny was taxed earlier at the lower
    rate, so cumulative withholding can end 1p BELOW the other option. Still zero
    exposure (each payment correctly taxed at its own date) — but don't claim
    lifetime over-withholding.

If ground-truth fixtures ever contradict this, STOP and show the delta — never
edit a fixture.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_DOWN

# Rounding mode for the RETENTION lines. ROUND_HALF_DOWN = round to nearest, but on
# an exact half-penny tie round DOWN, leaving the extra penny on pay-now labour
# (over-withholding — Option B, accountant-CONFIRMED; see RESOLVED TIE-BREAK above).
# NOT ROUND_DOWN: that would truncate every line, not just ties.
_RETENTION_ROUNDING = ROUND_HALF_DOWN

_CENT = Decimal("0.01")


def _money(value) -> Decimal:
    """Coerce an int/str/float/Decimal to a 2dp Decimal (standard nearest rounding).

    We route floats through str() so that e.g. 1234.56 becomes Decimal('1234.56')
    and NOT Decimal('1234.5599999...'); binary-float noise has no place in money.
    Input coercion uses plain nearest (HALF_UP) — the deliberate tie-break bias
    (_RETENTION_ROUNDING) applies only to the computed retention lines, never to
    the amounts the user typed in.
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class BillLines:
    """The labour and materials amounts for one ACCPAY bill (VAT-exclusive)."""

    labour: Decimal
    materials: Decimal

    @property
    def total(self) -> Decimal:
        return self.labour + self.materials


@dataclass(frozen=True)
class Split:
    """Result of splitting one subcontractor bill into pay-now + retention."""

    pay_now: BillLines
    retention: BillLines
    original: BillLines          # echoed back for the confirm screen / audit
    retention_pct: Decimal       # e.g. Decimal('5') for 5%

    def check(self) -> None:
        """Re-assert the three reconciliations. Cheap insurance; run in tests."""
        assert self.pay_now.total + self.retention.total == self.original.total, (
            "reconciliation (1) total broken"
        )
        assert self.pay_now.labour + self.retention.labour == self.original.labour, (
            "reconciliation (2) labour broken"
        )
        assert self.pay_now.materials + self.retention.materials == self.original.materials, (
            "reconciliation (3) materials broken"
        )


def split_bill(total, labour, materials, retention_pct) -> Split:
    """Split one subcontractor bill into a pay-now bill and a retention bill.

    Parameters (all VAT-exclusive money, 2dp; retention_pct is a PERCENT number)
    --------------------------------------------------------------------------
    total          : the whole bill, e.g. 1234.56
    labour          : labour portion of `total`, e.g. 880.24
    materials       : materials portion of `total`, e.g. 354.32
    retention_pct   : percentage held back, e.g. 5  (means 5%, NOT 0.05)

    Returns a `Split`. Raises ValueError on inconsistent / out-of-range input.

    Worked example (the adversarial fixture):
        split_bill(1234.56, 880.24, 354.32, 5)
        -> retention: labour 44.01, materials 17.72  (total 61.73)
           pay_now:  labour 836.23, materials 336.60 (total 1172.83)
        1172.83 + 61.73 == 1234.56;  836.23 + 44.01 == 880.24;
        336.60 + 17.72 == 354.32.
    """
    total = _money(total)
    labour = _money(labour)
    materials = _money(materials)

    # --- input validation: fail loud, never silently fudge ------------------
    if not isinstance(retention_pct, Decimal):
        retention_pct = Decimal(str(retention_pct))
    if retention_pct < 0 or retention_pct > 100:
        raise ValueError(f"retention_pct must be 0..100, got {retention_pct}")
    if labour < 0 or materials < 0:
        raise ValueError(f"labour/materials must be >= 0, got {labour}/{materials}")
    if labour + materials != total:
        raise ValueError(
            "PRECONDITION labour + materials == total is violated: "
            f"{labour} + {materials} = {labour + materials}, but total = {total} "
            f"(delta {total - (labour + materials)}). Fix the input on the confirm "
            "screen — the split cannot reconcile an inconsistent bill."
        )

    r = retention_pct / Decimal("100")  # exact Decimal fraction, e.g. 0.05

    # --- the split ----------------------------------------------------------
    # Round ONLY the retention side; derive the pay-now side by exact
    # subtraction so all rounding residue is forced onto pay-now labour.
    ret_labour = (labour * r).quantize(_CENT, rounding=_RETENTION_ROUNDING)
    ret_materials = (materials * r).quantize(_CENT, rounding=_RETENTION_ROUNDING)

    pay_materials = materials - ret_materials                       # -> (3) exact
    pay_labour = total - ret_labour - ret_materials - pay_materials  # plug -> (1) exact, (2) exact

    result = Split(
        pay_now=BillLines(labour=pay_labour, materials=pay_materials),
        retention=BillLines(labour=ret_labour, materials=ret_materials),
        original=BillLines(labour=labour, materials=materials),
        retention_pct=retention_pct,
    )
    result.check()  # defence in depth: never return a bill that doesn't reconcile
    return result


def indicative_cis(labour_amount, cis_rate_pct) -> Decimal:
    """DISPLAY-ONLY preview of the CIS deduction for the confirm screen.

    ⚠️  This is NOT the figure written to Xero. Xero computes the authoritative
    deduction at APPROVAL from the contact's live rate. Never persist this, never
    cache the rate, never feed it into a bill line. It exists purely so the
    confirm screen can show the user a "you'll withhold roughly £X" number.
    """
    labour_amount = _money(labour_amount)
    if not isinstance(cis_rate_pct, Decimal):
        cis_rate_pct = Decimal(str(cis_rate_pct))
    return (labour_amount * cis_rate_pct / Decimal("100")).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )
