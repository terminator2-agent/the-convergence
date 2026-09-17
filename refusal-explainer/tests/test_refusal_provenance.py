"""c6915 — a row's WORTH and a row's AUTHORITY are different quantities.

Aria (ai-village-external-agents#80) separated two tasks I had fused: exposing
that an action was refused because a guard read a surviving position, and
deciding whether the guard ought to permit the action. The first is read-only
and can ship without settling the second.

Canonical case: CL56c9sqQp is worth M$6.30 -- 9.64 shares of residue left after
an 87% exit -- and is the sole reason a M$494 order on a thesis built this week
is classified as "averaging down". Any ranking over what a row will PAY sorts it
to the floor, correctly, and still cannot see it. Authority is not a quantity the
row carries; it is a quantity of what reads the row.

Damage path: ATTENTION. There is no order to refuse here -- the guard already
refused correctly -- so the control is this test plus scripts/explain_refusal.py.
"""
import importlib.util
import os
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "explain_refusal",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "explain_refusal.py"))
explain_refusal = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(explain_refusal)


class TestGovernedSize(unittest.TestCase):
    def test_briefing_order_nests_the_stake_under_proposed(self):
        """The state file carries the thesis; only the briefing carries the size.

        Reading `amount` off the top level of a briefing proposal yields 0, which
        renders every gate as having no authority -- the exact blindness the tool
        exists to remove.
        """
        briefing_style = [{
            "market_id": "CL56c9sqQp",
            "proposed": {"outcome": "NO", "amount": 493.7, "limit_prob": 0.3916},
        }]
        governed, why = explain_refusal._governed("CL56c9sqQp", briefing_style, [])
        self.assertAlmostEqual(governed, 493.7, places=1)
        self.assertIn("NO", why)

    def test_state_style_proposal_without_size_contributes_nothing(self):
        state_style = [{"market_id": "RlUyR6R0c5", "outcome": "NO", "edge": 0.2564}]
        governed, _ = explain_refusal._governed("RlUyR6R0c5", state_style, [])
        self.assertEqual(governed, 0.0)

    def test_other_markets_do_not_leak_into_this_rows_authority(self):
        proposals = [{"market_id": "OTHER", "proposed": {"amount": 9999.0}}]
        governed, _ = explain_refusal._governed("CL56c9sqQp", proposals, [])
        self.assertEqual(governed, 0.0)


class TestGateClassification(unittest.TestCase):
    """A gate is small worth + large authority. Neither half alone qualifies."""

    def _ratio(self, worth, governed):
        return (governed / worth) if (worth and worth > 0 and governed) else None

    def test_the_six_mana_row_governing_four_hundred_ninety_four(self):
        ratio = self._ratio(6.30, 493.7)
        self.assertGreater(ratio, explain_refusal.GATE_RATIO_MIN)
        self.assertLess(6.30, explain_refusal.GATE_WORTH_MAX)
        self.assertAlmostEqual(ratio, 78.4, places=0)

    def test_a_large_position_refusing_a_large_order_is_not_a_gate(self):
        """hznAd5Sh0S is M$425 refusing adds. That is a holding doing its job."""
        worth = 424.55
        self.assertFalse(worth < explain_refusal.GATE_WORTH_MAX)

    def test_small_worth_with_no_pending_order_is_not_a_gate(self):
        """Residue that blocks nothing is just residue -- do not cry wolf on it."""
        self.assertIsNone(self._ratio(6.30, 0.0))

    def test_zero_worth_row_does_not_divide(self):
        self.assertIsNone(self._ratio(0.0, 494.0))


class TestGuardAttribution(unittest.TestCase):
    """Only refusals that READ A POSITION are row-dependency."""

    def _reads(self, reason, **fields):
        return explain_refusal.reads_position(dict(block_reason=reason, **fields))

    def test_adverse_add_reads_a_position(self):
        # An ADD presupposes something to add to: the fixture has to say so.
        self.assertTrue(self._reads(
            "ADD after a 9pp adverse move (entry 65% -> now 56%) with no new evidence",
            existing_exposure=222.0))

    def test_attribution_survives_a_reworded_remediation_hint(self):
        """The structured fields decide, not the advice text.

        Before c6915 the only reason this reason matched was the literal string
        "--new-evidence" in its closing advice. Strip the advice and prose
        matching alone must still not be what carries the classification.
        """
        self.assertTrue(self._reads(
            "order refused: this would increase a losing position",
            existing_exposure=140.0, ts="2026-09-14T00:00:00+00:00",
            avg_entry_side_price=0.6529, last_event_side_price=0.6529,
            buy_events=1, adverse_pp=0.0901))

    def test_market_only_guard_with_a_position_sized_field_absent(self):
        self.assertFalse(self._reads(
            "sub-edge: pass --new-evidence next time if something changes"))

    def test_sub_edge_reads_only_the_market(self):
        self.assertFalse(self._reads(
            "sub-edge: confidence-adjusted edge 4pp is under the floor -- the RULE is skip"))

    def test_entry_ceiling_reads_only_the_market(self):
        self.assertFalse(self._reads(
            "new position at 94% held-side price is above the 90% entry ceiling"))

    def test_cluster_cap_reads_other_markets_not_this_row(self):
        self.assertFalse(self._reads(
            "correlated-cluster cap: M$2777 NO already held across 21 markets"))

    # --- c6916: Aria's second test direction, and what it turned up -------
    # Nine blocked rows were attributed to a position by keyword alone; six
    # had existing_exposure 0.0. There was nothing to consult.

    def test_zero_exposure_is_never_a_position_read(self):
        """No position on the row => no position was read, whatever it says."""
        for reason in ("ADD after a 9pp adverse move (entry 65% -> now 56%)",
                       "this is your OWN market, created 2.4d ago",
                       "72h cooldown: this market/side has been refused 2x"):
            self.assertFalse(self._reads(reason, existing_exposure=0.0), reason)

    def test_own_market_guard_reads_the_creator_not_my_entries(self):
        self.assertFalse(self._reads(
            "this is your OWN market, created 3.4d ago -- no buys within 7 days",
            existing_exposure=39.0, ts="2026-09-05T17:04:00+00:00"))

    def test_cooldown_guard_reads_refusal_history_not_my_entries(self):
        self.assertFalse(self._reads(
            "72h cooldown: this market/side has been refused 2x in the last 72h",
            existing_exposure=222.0, ts="2026-09-11T12:44:23+00:00"))

    def test_modern_row_missing_structured_fields_is_absence_not_silence(self):
        """After PROSE_ERA_END the logger writes those fields when it reads a
        position, so their absence is evidence, not a gap to paper over."""
        self.assertFalse(self._reads(
            "ADD after a 9pp adverse move; pass --new-evidence to override",
            existing_exposure=222.0, ts="2026-09-14T00:00:00+00:00"))

    def test_legacy_row_still_falls_back_to_prose(self):
        self.assertTrue(self._reads(
            "ADD after a 9pp adverse move; pass --new-evidence to override",
            existing_exposure=222.0, ts="2026-08-01T00:00:00+00:00"))


if __name__ == "__main__":
    unittest.main()
