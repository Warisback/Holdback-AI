"""
Tests for the pure bill-splitting engine.

Two kinds of tests live here:

1. STRUCTURAL / RECONCILIATION tests (below) assert the three invariants from the
   brief. These are objective facts about any correct split, so I can assert them
   without your hand-calculated numbers. The adversarial fixture (£1,234.56 /
   71.3% labour / 5% retention) is required by the brief and is checked here.

2. GROUND-TRUTH fixtures (`GROUND_TRUTH_FIXTURES`, currently empty). You said you
   will hand-calculate expected outputs for 3 inputs. Paste them there and the
   parametrized test will assert the code's output equals YOUR numbers, penny for
   penny. RULE: if a fixture and the code disagree, we STOP and look at the delta
   together — we never edit a fixture to make the test go green.
"""

from decimal import Decimal

import pytest

from holdback.split_engine import split_bill


def D(x) -> Decimal:
    return Decimal(str(x))


# --- 1. Structural / reconciliation tests -----------------------------------

# (total, labour, materials, retention_pct). Every case must satisfy the three
# reconciliations. The 2nd entry is the brief's mandated adversarial fixture:
# £1,234.56 with 71.3% labour  ->  labour = round(1234.56 * 0.713) = 880.24,
# materials = 1234.56 - 880.24 = 354.32.
RECONCILIATION_CASES = [
    (1000.00, 600.00, 400.00, 5),
    (1234.56, 880.24, 354.32, 5),   # <-- adversarial fixture (71.3% labour, 5%)
    (1234.56, 880.24, 354.32, 0),   # 0% retention -> nothing held back
    (1234.56, 880.24, 354.32, 100), # 100% retention -> everything held back
    (0.05, 0.05, 0.00, 50),         # sub-penny stress: 50% of 5p
    (999.99, 333.33, 666.66, 33),
    (100.00, 0.00, 100.00, 10),     # materials only
    (100.00, 100.00, 0.00, 10),     # labour only
]


@pytest.mark.parametrize("total,labour,materials,pct", RECONCILIATION_CASES)
def test_three_reconciliations_hold(total, labour, materials, pct):
    s = split_bill(total, labour, materials, pct)

    # (1) pay_now + retention == original total
    assert s.pay_now.total + s.retention.total == D(total)
    # (2) labour across both bills == original labour
    assert s.pay_now.labour + s.retention.labour == D(labour)
    # (3) materials across both bills == original materials
    assert s.pay_now.materials + s.retention.materials == D(materials)

    # every amount is exactly 2dp
    for amount in (s.pay_now.labour, s.pay_now.materials,
                   s.retention.labour, s.retention.materials):
        assert amount == amount.quantize(Decimal("0.01"))


def test_adversarial_fixture_exact_values():
    """The brief's headline example, spelled out so a regression is obvious."""
    s = split_bill(1234.56, 880.24, 354.32, 5)
    assert s.retention.labour == D("44.01")
    assert s.retention.materials == D("17.72")
    assert s.retention.total == D("61.73")
    assert s.pay_now.labour == D("836.23")
    assert s.pay_now.materials == D("336.60")
    assert s.pay_now.total == D("1172.83")


def test_inconsistent_input_is_rejected():
    """labour + materials != total must raise, not silently reconcile."""
    with pytest.raises(ValueError, match="PRECONDITION"):
        split_bill(1000.00, 600.00, 399.00, 5)   # components sum to 999.00


@pytest.mark.parametrize("bad_pct", [-1, 101, 250])
def test_out_of_range_retention_pct_is_rejected(bad_pct):
    with pytest.raises(ValueError):
        split_bill(1000.00, 600.00, 400.00, bad_pct)


# --- 2. Ground-truth fixtures (YOUR hand-calculated numbers) ----------------
#
# Fill this in with your 3 inputs and expected outputs, e.g.:
#
#   {"total": 5000.00, "labour": 3000.00, "materials": 2000.00, "retention_pct": 5,
#    "expected": {"pay_labour": 2850.00, "pay_materials": 1900.00,
#                 "ret_labour": 150.00, "ret_materials": 100.00}},
#
# Leave empty for now; the test below skips until you supply numbers.
GROUND_TRUTH_FIXTURES: list[dict] = []


@pytest.mark.parametrize("fx", GROUND_TRUTH_FIXTURES)
def test_matches_hand_calculated_ground_truth(fx):
    s = split_bill(fx["total"], fx["labour"], fx["materials"], fx["retention_pct"])
    exp = fx["expected"]
    # On any mismatch, STOP and show the delta — do not touch the fixture.
    assert s.pay_now.labour == D(exp["pay_labour"]), (
        f"pay_labour delta: code {s.pay_now.labour} vs fixture {exp['pay_labour']}"
    )
    assert s.pay_now.materials == D(exp["pay_materials"]), (
        f"pay_materials delta: code {s.pay_now.materials} vs fixture {exp['pay_materials']}"
    )
    assert s.retention.labour == D(exp["ret_labour"]), (
        f"ret_labour delta: code {s.retention.labour} vs fixture {exp['ret_labour']}"
    )
    assert s.retention.materials == D(exp["ret_materials"]), (
        f"ret_materials delta: code {s.retention.materials} vs fixture {exp['ret_materials']}"
    )


def test_ground_truth_fixtures_are_present():
    """Reminder that we still owe 3 hand-calculated fixtures (brief requirement)."""
    if not GROUND_TRUTH_FIXTURES:
        pytest.skip("Waiting on 3 hand-calculated ground-truth fixtures from the user.")
    assert len(GROUND_TRUTH_FIXTURES) >= 3
