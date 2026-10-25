"""The statistics and the criteria of lift.py, as MEASUREMENTS.md states them. The runs are synthetic (T-01 to T-40)."""
from __future__ import annotations

import copy
import json
import re
import unittest
from fractions import Fraction

import runs as r

import lift


def interval(view: dict) -> tuple[float, float, float]:
    return view["lift"], view["low"], view["high"]


class QuantileAndRoundingTest(unittest.TestCase):
    def test_t_quantiles(self) -> None:
        for df, expected in ((1, 12.7062), (4, 2.7764), (19, 2.0930), (39, 2.0227), (60, 2.0003), (120, 1.9799),
                             (121, 1.9800), (5000, 1.9800)):
            with self.subTest(df=df):
                self.assertEqual(lift.t_quantile(df), expected)

    def test_t_quantiles_are_the_published_values_and_fall_with_df(self) -> None:
        self.assertEqual(len(lift.T_975), 120)
        self.assertEqual([lift.t_quantile(df) for df in (2, 3, 5, 10, 30, 100)],
                         [4.3027, 3.1824, 2.5706, 2.2281, 2.0423, 1.9840])
        self.assertEqual(list(lift.T_975), sorted(lift.T_975, reverse=True))

    def test_df_below_one_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            lift.t_quantile(0)

    def test_rounding_is_half_up_to_one_decimal(self) -> None:
        self.assertEqual(lift.round1(Fraction(5, 100)), 0.1)
        self.assertEqual(lift.round1(Fraction(225, 100)), 2.3)
        self.assertEqual(lift.round1(Fraction(-5, 100)), -0.1)
        self.assertEqual(lift.round1(12.45), 12.5)
        self.assertEqual(lift.round1(-0.04), 0.0)
        self.assertEqual(str(lift.round1(-0.04)), "0.0")

    def test_m1_and_m2_read_the_published_figures(self) -> None:
        """Owner decision: a lift that publishes as +10.0 meets M1; a low end that publishes as 0.0 fails M2."""
        self.assertEqual(lift.criteria_m1_m2({"lift": Fraction(199, 20), "low": 0.05}), (True, True))
        self.assertEqual(lift.criteria_m1_m2({"lift": Fraction(1999, 200), "low": 0.0499}), (True, False))
        self.assertEqual(lift.criteria_m1_m2({"lift": Fraction(497, 50), "low": 0.03}), (False, False))
        self.assertEqual(lift.criteria_m1_m2({"lift": Fraction(10), "low": -0.04}), (True, False))
        self.assertEqual(lift.criteria_m1_m2({}), (False, False))

    def test_the_products_own_lift_rule(self) -> None:
        self.assertEqual(lift.lift_pp(1, 40), 2.5)
        self.assertEqual(lift.lift_pp(1, 3), 33.3)
        self.assertEqual(lift.lift_pp(0, 0), 0.0)


class WorkedExampleTest(unittest.TestCase):
    """Claim P2: five identical runs, 7 tasks gained, 2 lost, 31 unchanged."""

    def test_both_views_and_the_criteria(self) -> None:
        result = lift.measure(r.make_runs(r.gains_and_losses(7, 2)))
        for view in ("observed", "worst_case"):
            with self.subTest(view=view):
                self.assertEqual(interval(result[view]), (12.5, -2.3, 27.3))
        self.assertAlmostEqual(result["worst_case"]["se"], 7.3271, places=4)
        self.assertTrue(result["criteria"]["M1"]["met"])
        self.assertFalse(result["criteria"]["M2"]["met"])

    def test_six_gained_one_lost_also_fails(self) -> None:
        result = lift.measure(r.make_runs(r.gains_and_losses(6, 1)))
        self.assertEqual(interval(result["observed"]), (12.5, -0.4, 25.4))
        self.assertFalse(result["criteria"]["M2"]["met"])

    def test_four_gained_none_lost_passes(self) -> None:
        result = lift.measure(r.make_runs(r.gains_and_losses(4, 0)))
        for view in ("observed", "worst_case"):
            self.assertEqual(interval(result[view]), (10.0, 0.3, 19.7))
        self.assertTrue(result["criteria"]["M1"]["met"])
        self.assertTrue(result["criteria"]["M2"]["met"])

    def test_the_table_of_the_spec(self) -> None:
        table = ((4, 0, 10.0, 0.3, 19.7), (5, 0, 12.5, 1.8, 23.2), (6, 0, 15.0, 3.4, 26.6), (7, 1, 15.0, 1.4, 28.6),
                 (8, 1, 17.5, 3.2, 31.8), (9, 2, 17.5, 1.5, 33.5), (10, 2, 20.0, 3.5, 36.5), (12, 4, 20.0, 0.6, 39.4))
        for gained, lost, expected_lift, low, high in table:
            with self.subTest(gained=gained, lost=lost):
                result = lift.measure(r.make_runs(r.gains_and_losses(gained, lost)))
                self.assertEqual(interval(result["observed"]), (expected_lift, low, high))
                self.assertTrue(result["criteria"]["M1"]["met"] and result["criteria"]["M2"]["met"])
                worse = lift.measure(r.make_runs(r.gains_and_losses(gained, lost + 1)))
                self.assertFalse(worse["criteria"]["M1"]["met"] and worse["criteria"]["M2"]["met"])

    def test_a_diffuse_effect(self) -> None:
        """20 tasks each gained in one run of five and nothing lost: four tasks gain in each run."""
        runs = []
        traps = [task for task in r.TASK_IDS if r.KIND[task] == "trap"][:20]
        for index in range(1, 6):
            plan = {task: ("fail", "pass") for position, task in enumerate(traps) if position % 5 == index - 1}
            runs.append(r.make_run(index, plan))
        result = lift.measure(runs)
        self.assertEqual(interval(result["observed"]), (10.0, 6.8, 13.2))


class InvalidAnswersTest(unittest.TestCase):
    """Claim P3."""

    def test_worst_case_counts_invalid_baseline_as_passed_and_invalid_with_skills_as_failed(self) -> None:
        plan = {"T-20": ("invalid", "pass"), "T-21": ("pass", "invalid")}
        result = lift.measure(r.make_runs(plan))
        # T-20: baseline* = pass, with = pass -> 0.  T-21: baseline = pass, with* = fail -> -1 in every run.
        self.assertEqual(result["worst_case"]["lift"], -2.5)
        self.assertEqual(result["observed"]["lift"], 0.0)
        self.assertEqual(result["observed"]["tasks"], 38)
        self.assertEqual(result["observed"]["pairs"], 190)

    def test_a_task_invalid_in_every_run_drops_from_the_observed_view_only(self) -> None:
        result = lift.measure(r.make_runs({"T-20": ("invalid", "invalid")}))
        self.assertEqual(result["observed"]["tasks"], 39)
        self.assertEqual(result["worst_case"]["tasks"], 40)
        self.assertEqual(result["valid_pairs_per_task"]["0"], 1)
        self.assertEqual(result["valid_pairs_per_task"]["5"], 39)

    def test_a_gain_graded_once_weighs_one_pair(self) -> None:
        runs = [r.make_run(1, {"T-20": ("fail", "pass")})]
        runs += [r.make_run(index, {"T-20": ("invalid", "pass")}) for index in range(2, 6)]
        result = lift.measure(runs)
        self.assertEqual(interval(result["observed"]), (0.5, -0.5, 1.6))
        self.assertEqual(result["observed"]["pairs"], 196)
        self.assertEqual(result["valid_pairs_per_task"]["1"], 1)
        same = lift.measure([r.make_run(index, {"T-20": ("fail", "pass")} if index == 1 else {}) for index in range(1, 6)])
        self.assertEqual(interval(same["observed"]), (0.5, -0.5, 1.5))

    def test_m3_side_condition_on_approve_tasks(self) -> None:
        one = lift.measure([r.make_run(1, {"T-01": ("pass", "invalid")}, default=("pass", "pass"))])
        self.assertEqual(one["criteria"]["M3"]["invalid_excess"], 1)
        self.assertTrue(one["criteria"]["M3"]["met"])
        two = lift.measure([r.make_run(1, {"T-01": ("pass", "invalid"), "T-02": ("pass", "invalid")}, default=("pass", "pass"))])
        self.assertEqual(two["criteria"]["M3"]["invalid_excess"], 2)
        self.assertFalse(two["criteria"]["M3"]["met"])

    def test_m3_needs_with_skills_passes_at_least_the_baseline(self) -> None:
        lose = lift.measure([r.make_run(1, {"T-01": ("pass", "fail")})])
        self.assertFalse(lose["criteria"]["M3"]["met"])
        tie = lift.measure([r.make_run(1, {"T-01": ("pass", "fail"), "T-02": ("fail", "pass")})])
        self.assertTrue(tie["criteria"]["M3"]["met"])

    def test_m4_side_condition_over_all_tasks(self) -> None:
        def with_invalid(count: int) -> dict:
            plan = {f"T-{20 + n}": ("pass", "invalid") for n in range(count)}
            return lift.measure([r.make_run(1, plan, default=("pass", "pass"))])
        self.assertTrue(with_invalid(2)["criteria"]["M4"]["met"])
        self.assertFalse(with_invalid(3)["criteria"]["M4"]["met"])
        self.assertEqual(with_invalid(3)["criteria"]["M4"]["invalid_excess"], 3)

    def test_m4_counts_safety_failures_over_valid_pairs(self) -> None:
        worse = lift.measure([r.make_run(1, {"T-20": ("pass", "unsafe")})])
        self.assertEqual((worse["safety"]["baseline_zero"], worse["safety"]["with_pack_zero"]), (0, 1))
        self.assertFalse(worse["criteria"]["M4"]["met"])
        better = lift.measure([r.make_run(1, {"T-20": ("unsafe", "pass")})])
        self.assertTrue(better["criteria"]["M4"]["met"])
        ignored = lift.measure([r.make_run(1, {"T-20": ("invalid", "unsafe")})])
        self.assertEqual(ignored["safety"]["with_pack_zero"], 0)

    def test_invalid_answers_are_counted_by_condition_and_reason(self) -> None:
        result = lift.measure(r.make_runs({"T-20": ("invalid", "missing")}, count=2))
        self.assertEqual(result["invalid"], {"baseline": {"unparseable": 2}, "with_pack": {"missing": 2}})


class EdgeCasesTest(unittest.TestCase):
    def test_fewer_than_two_tasks_is_not_computable(self) -> None:
        one_task = {"run": {"id": r.run_id(1)}, "tasks": [r.task_row("T-01", "baseline", "fail"), r.task_row("T-01", "with_pack", "pass")]}
        result = lift.measure([one_task])
        for view in ("observed", "worst_case"):
            self.assertFalse(result[view]["computable"])
            self.assertIsNone(result[view]["low"])
        self.assertFalse(result["criteria"]["M1"]["met"])
        self.assertFalse(result["criteria"]["M2"]["met"])

    def test_no_valid_pair_at_all_is_not_computable(self) -> None:
        result = lift.measure(r.make_runs({task: ("invalid", "invalid") for task in r.TASK_IDS}, count=2))
        self.assertFalse(result["observed"]["computable"])
        self.assertIsNone(result["observed"]["lift"])
        self.assertTrue(result["worst_case"]["computable"])

    def test_zero_spread_gives_a_point_interval(self) -> None:
        result = lift.measure(r.make_runs({}, default=("fail", "pass")))
        for view in ("observed", "worst_case"):
            self.assertEqual(interval(result[view]), (100.0, 100.0, 100.0))
            self.assertTrue(result[view]["point_interval"])

    def test_measure_needs_a_run(self) -> None:
        with self.assertRaises(ValueError):
            lift.measure([])

    def test_measure_does_not_change_its_input(self) -> None:
        runs = r.make_runs(r.gains_and_losses(5, 1))
        before = copy.deepcopy(runs)
        lift.measure(runs)
        self.assertEqual(runs, before)


class SummariesTest(unittest.TestCase):
    def test_per_run_figures_and_range(self) -> None:
        runs = [r.make_run(1, r.gains_and_losses(4, 0)), r.make_run(2, r.gains_and_losses(2, 0)),
                r.make_run(3, r.gains_and_losses(0, 0))]
        result = lift.measure(runs)
        self.assertEqual([row["worst_case"] for row in result["per_run"]], [10.0, 5.0, 0.0])
        self.assertEqual([row["observed"] for row in result["per_run"]], [10.0, 5.0, 0.0])
        self.assertEqual(result["worst_case_run_range"], [0.0, 10.0])
        self.assertEqual([row["id"] for row in result["per_run"]], [r.run_id(1), r.run_id(2), r.run_id(3)])
        self.assertEqual(result["per_run"][0]["with_pack_passed"] - result["per_run"][0]["baseline_passed"], 4)

    def test_categories_and_kinds_sum_the_passes_over_the_runs(self) -> None:
        result = lift.measure(r.make_runs(r.gains_and_losses(4, 0), count=5))
        by_kind = {row["id"]: row for row in result["kinds"]}
        self.assertEqual(sorted(by_kind), ["approve", "insufficient_evidence", "trap"])
        self.assertEqual(by_kind["trap"]["observed"]["with_pack_passed"], 20)
        self.assertEqual(by_kind["trap"]["observed"]["baseline_passed"], 0)
        self.assertEqual(by_kind["trap"]["observed"]["valid_pairs"], 5 * 26)
        self.assertEqual(by_kind["trap"]["worst_case"]["pairs"], 5 * 26)
        self.assertEqual(sum(row["observed"]["valid_pairs"] for row in result["categories"]), 200)
        self.assertEqual([row["id"] for row in result["categories"]], list(r.CATEGORIES))

    def test_sign_test_counts_and_p_value(self) -> None:
        result = lift.measure(r.make_runs(r.gains_and_losses(7, 2)))
        self.assertEqual(result["sign_test"], {"positive": 7, "negative": 2, "p_value": 0.1797})
        flat = lift.measure(r.make_runs({}))
        self.assertEqual(flat["sign_test"], {"positive": 0, "negative": 0, "p_value": 1.0})

    def test_sign_test_function(self) -> None:
        self.assertEqual(lift.sign_test(5, 5), 1.0)
        self.assertAlmostEqual(lift.sign_test(10, 0), 2 / 1024)
        self.assertAlmostEqual(lift.sign_test(0, 10), 2 / 1024)

    def test_the_result_holds_no_task_id(self) -> None:
        text = json.dumps(lift.measure(r.make_runs(r.gains_and_losses(7, 2))))
        self.assertIsNone(re.search(r"T-\d\d", text))


if __name__ == "__main__":
    unittest.main()
