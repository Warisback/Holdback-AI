"""
Tests for the tranche splitter (split_tranches) — a layer on the verified engine.

Two kinds, as with the split engine:
1. STRUCTURAL invariants (objective — asserted now): tranche sums reconcile to the
   retention lines exactly; the ≤2 hard guard; share validation; and the ORIGINAL three
   reconciliations across ALL bills (pay-now + every tranche).
2. GROUND-TRUTH T1/T2 (TRANCHE_FIXTURES, empty until you confirm the exact pennies) —
   I do not invent these. When you confirm, they get asserted; on any delta we STOP.
"""

from decimal import Decimal

import pytest

from holdback.split_engine import BillLines, split_bill, split_tranches


def D(x):
    return Decimal(str(x))


# --- structural invariants --------------------------------------------------
RET_CASES = [
    (BillLines(labour=D("350.01"), materials=D("150.00")), [50, 50]),   # T1 inputs (tie)
    (BillLines(labour=D("333.33"), materials=D("166.67")), [60, 40]),   # T2 inputs
    (BillLines(labour=D("50.00"), materials=D("25.00")), [50, 50]),
    (BillLines(labour=D("75.00"), materials=D("0.00")), [30, 70]),
    (BillLines(labour=D("75.00"), materials=D("0.00")), [100]),          # single tranche
]


@pytest.mark.parametrize("retention,shares", RET_CASES)
def test_tranche_sums_reconcile_per_line_type(retention, shares):
    tranches = split_tranches(retention, shares)
    assert sum(t.labour for t in tranches) == retention.labour
    assert sum(t.materials for t in tranches) == retention.materials
    assert len(tranches) == len(shares)
    for t in tranches:  # every amount is exactly 2dp
        assert t.labour == t.labour.quantize(Decimal("0.01"))
        assert t.materials == t.materials.quantize(Decimal("0.01"))


def test_all_bills_reconcile_to_original_across_pay_now_and_tranches():
    """The brief's three reconciliations must hold across pay-now + every tranche."""
    s = split_bill(1500.00, 1000.00, 500.00, 5)          # retention: labour 50, materials 25
    tranches = split_tranches(s.retention, [50, 50])
    labour_bills = [s.pay_now.labour] + [t.labour for t in tranches]
    materials_bills = [s.pay_now.materials] + [t.materials for t in tranches]
    assert sum(labour_bills) == D("1000.00")             # (2) labour
    assert sum(materials_bills) == D("500.00")           # (3) materials
    assert sum(labour_bills) + sum(materials_bills) == D("1500.00")  # (1) total


def test_more_than_two_tranches_is_guarded():
    with pytest.raises(NotImplementedError):
        split_tranches(BillLines(labour=D("90"), materials=D("10")), [40, 30, 30])


@pytest.mark.parametrize("bad", [[50, 40], [60, 41], [0, 100], [-10, 110], [50, 50, 0]])
def test_invalid_shares_rejected(bad):
    # shares must be >0 and sum to exactly 100 (the last case also trips the >2 guard first)
    with pytest.raises((ValueError, NotImplementedError)):
        split_tranches(BillLines(labour=D("100"), materials=D("50")), bad)


def test_single_tranche_returns_retention_unchanged():
    ret = BillLines(labour=D("50.00"), materials=D("25.00"))
    (only,) = split_tranches(ret, [100])
    assert only.labour == ret.labour and only.materials == ret.materials


# --- ground-truth T1/T2 (fill in with YOUR hand-calc; do not invent) --------
# T1: retention labour £350.01, materials £150.00, shares 50/50 (labour tie at 175.005)
# T2: retention labour £333.33, materials £166.67, shares 60/40
# Each entry: {"retention": (labour, materials), "shares": [...],
#              "expected": [(t1_labour, t1_materials), (t2_labour, t2_materials)]}
TRANCHE_FIXTURES: list[dict] = []


@pytest.mark.parametrize("fx", TRANCHE_FIXTURES)
def test_matches_hand_calculated_tranches(fx):
    ret = BillLines(labour=D(fx["retention"][0]), materials=D(fx["retention"][1]))
    got = split_tranches(ret, fx["shares"])
    for i, (lab, mat) in enumerate(fx["expected"]):
        assert got[i].labour == D(lab), f"tranche {i+1} labour: {got[i].labour} vs {lab}"
        assert got[i].materials == D(mat), f"tranche {i+1} materials: {got[i].materials} vs {mat}"


def test_tranche_ground_truth_present():
    if not TRANCHE_FIXTURES:
        pytest.skip("Waiting on the user's hand-calculated T1/T2 tranche numbers.")
    assert len(TRANCHE_FIXTURES) >= 2
