"""validate, render_markdown and the `report` command of lift.py."""
from __future__ import annotations

import copy
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

import runs as r

import lift
from pack_common import SKILL_NAMES


def good_runs() -> list[dict]:
    return r.make_runs(r.gains_and_losses(7, 0))


class ValidateTest(unittest.TestCase):
    def failures(self, runs: list[dict], **kwargs) -> list[str]:
        return lift.validate(runs, **kwargs)

    def assertFails(self, runs: list[dict], check: str, **kwargs) -> None:
        found = self.failures(runs, **kwargs)
        self.assertTrue(any(line.startswith(f"{check}:") for line in found), found)

    def test_five_matching_runs_are_valid(self) -> None:
        self.assertEqual(self.failures(good_runs()), [])

    def test_the_skill_list_is_the_one_of_the_tools(self) -> None:
        self.assertEqual(lift.PACK_SKILLS, SKILL_NAMES)

    def test_wrong_number_of_runs(self) -> None:
        self.assertFails(good_runs()[:4], "runs")

    def test_a_run_given_twice(self) -> None:
        runs = good_runs()
        runs[1] = copy.deepcopy(runs[0])
        self.assertFails(runs, "runs")

    def test_run_that_is_not_paired(self) -> None:
        runs = good_runs()
        runs[2]["run"]["kind"] = "tool_grades"
        self.assertFails(runs, "kind")

    def test_run_that_ended_in_error(self) -> None:
        runs = good_runs()
        runs[0]["run"]["status"] = "error"
        self.assertFails(runs, "status")

    def test_an_invalid_run_is_valid_and_needs_no_results(self) -> None:
        runs = good_runs()
        runs[0] = r.make_run(1, r.gains_and_losses(7, 0), status="invalid")
        self.assertEqual(self.failures(runs), [])

    def test_suite_sha256_differs(self) -> None:
        runs = good_runs()
        runs[3]["run"]["suite_sha256"] = "cd" * 32
        self.assertFails(runs, "suite")

    def test_runs_of_another_suite_fail_unless_it_is_recorded(self) -> None:
        runs = good_runs()
        for answer in runs:
            answer["run"]["suite_id"] = "some-other-suite"
        self.assertFails(runs, "suite")
        self.assertEqual(self.failures(runs, recorded={"suite_id": "some-other-suite"}), [])

    def test_suite_version_differs(self) -> None:
        runs = good_runs()
        runs[3]["run"]["suite_version"] = "1.0.1"
        self.assertFails(runs, "suite")

    def test_models_differ(self) -> None:
        runs = good_runs()
        runs[4]["run"]["models"] = {**r.MODELS, "effort": "low"}
        self.assertFails(runs, "models")

    def test_skill_order_differs(self) -> None:
        runs = good_runs()
        runs[1]["run"]["skills"][0], runs[1]["run"]["skills"][1] = runs[1]["run"]["skills"][1], runs[1]["run"]["skills"][0]
        self.assertFails(runs, "skills")

    def test_a_skill_sha256_differs(self) -> None:
        runs = good_runs()
        runs[1]["run"]["skills"][2]["sha256"] = "ee" * 32
        self.assertFails(runs, "skills")

    def test_a_skill_missing(self) -> None:
        runs = good_runs()
        del runs[0]["run"]["skills"][4]
        self.assertFails(runs, "skills")

    def test_a_whole_config_missing(self) -> None:
        runs = good_runs()
        runs[2] = r.make_run(3, r.gains_and_losses(7, 0), drop_config="with_pack")
        self.assertFails(runs, "rows")

    def test_a_single_missing_row_is_invalid_not_an_error(self) -> None:
        runs = good_runs()
        runs[0] = r.make_run(1, {**r.gains_and_losses(7, 0), "T-30": ("pass", "missing")})
        self.assertEqual(self.failures(runs), [])
        self.assertEqual(lift.measure(runs)["invalid"]["with_pack"], {"missing": 1})

    def test_a_task_row_twice(self) -> None:
        runs = good_runs()
        runs[0]["tasks"].append(copy.deepcopy(runs[0]["tasks"][0]))
        self.assertFails(runs, "rows")

    def test_fewer_than_forty_tasks(self) -> None:
        runs = good_runs()
        for answer in runs:
            answer["tasks"] = [row for row in answer["tasks"] if row["task_id"] != "T-40"]
        self.assertFails(runs, "tasks")
        self.assertFalse(any(line.startswith("tasks:") for line in self.failures(runs, expected_tasks=39)))

    def test_a_finished_runs_lift_must_match_its_own_results(self) -> None:
        for view in ("observed", "worst_case"):
            with self.subTest(view=view):
                runs = good_runs()
                runs[0]["run"]["results"][view]["lift_pp"] = 99.9
                self.assertFails(runs, "lift")

    def test_the_lift_comparison_is_numeric_not_textual(self) -> None:
        runs = r.make_runs(r.gains_and_losses(4, 0))
        runs[0]["run"]["results"]["observed"]["lift_pp"] = 10
        runs[0]["run"]["results"]["worst_case"]["lift_pp"] = 10
        self.assertEqual(self.failures(runs), [])

    def test_a_finished_run_without_results(self) -> None:
        runs = good_runs()
        runs[0]["run"]["results"] = None
        self.assertFails(runs, "results")

    def test_recorded_values(self) -> None:
        runs = good_runs()
        skills = [{"name": name, "sha256": r.SKILL_SHA[name]} for name in SKILL_NAMES]
        recorded = {"suite_id": "infra-ops-40", "suite_version": "1.0.0", "suite_sha256": r.SUITE_SHA,
                    "models": r.MODELS, "skills": skills}
        self.assertEqual(self.failures(runs, recorded=recorded), [])
        for key, bad in (("suite_sha256", "00" * 32), ("suite_version", "2.0.0"), ("models", {**r.MODELS, "judge": "other"}),
                         ("skills", [{**skills[0], "sha256": "11" * 32}] + skills[1:])):
            with self.subTest(key=key):
                self.assertTrue(self.failures(runs, recorded={**recorded, key: bad}))


class RenderTest(unittest.TestCase):
    def render(self, runs: list[dict]) -> str:
        return lift.render_markdown(lift.measure(runs))

    def test_worked_example_numbers_appear(self) -> None:
        text = self.render(r.make_runs(r.gains_and_losses(7, 2)))
        self.assertIn("| Observed (published) | +12.5 | -2.3 to 27.3 | 40 | 200 |", text)
        self.assertIn("| M1: lift at least 10.0, in both views | observed +12.5, worst case +12.5 | yes |", text)
        self.assertIn("| M2: low end of the interval above 0.0, in both views | observed -2.3, worst case -2.3 | no |", text)
        self.assertIn("Tasks with a net gain: 7. Tasks with a net loss: 2. Two-sided exact p-value: 0.1797.", text)

    def test_no_dash_exclamation_or_task_id(self) -> None:
        text = self.render(r.make_runs(r.gains_and_losses(7, 2)))
        for char in ("—", "–", "!"):
            self.assertNotIn(char, text)
        self.assertIsNone(re.search(r"T-\d\d", text))

    def test_ungradable_answers_are_listed_by_condition_and_reason(self) -> None:
        text = self.render(r.make_runs({"T-20": ("invalid", "invalid")}, count=2))
        self.assertIn("| Baseline | unparseable | 2 |", text)
        self.assertIn("| With skills | unparseable | 2 |", text)

    def test_none_ungradable(self) -> None:
        self.assertIn("No answer was ungradable.", self.render(good_runs()))

    def test_a_point_interval_is_said_to_be_one(self) -> None:
        text = self.render(r.make_runs({}, default=("fail", "pass")))
        self.assertIn("a single point", text)

    def test_valid_pair_distribution_row(self) -> None:
        text = self.render(r.make_runs({"T-20": ("invalid", "invalid")}))
        self.assertIn("| Valid pairs | 5 | 4 | 3 | 2 | 1 | 0 |", text)
        self.assertIn("| Tasks | 39 | 0 | 0 | 0 | 0 | 1 |", text)

    def test_signs_are_written_out(self) -> None:
        self.assertEqual(lift.signed(12.5), "+12.5")
        self.assertEqual(lift.signed(-2.3), "-2.3")
        self.assertEqual(lift.signed(0.0), "0.0")
        self.assertEqual(lift.signed(None), "not computable")


class ReportCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name)

    def write_runs(self, runs: list[dict]) -> list[str]:
        paths = []
        for answer in runs:
            path = self.path / f"{answer['run']['id']}.json"
            path.write_text(json.dumps(answer), encoding="utf-8")
            paths.append(str(path))
        return paths

    def call(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = lift.main(list(argv), env={}, out=out, err=err)
        return code, out.getvalue(), err.getvalue()

    def test_writes_json_and_markdown_and_exits_zero(self) -> None:
        files = self.write_runs(r.make_runs(r.gains_and_losses(7, 2)))
        code, out, err = self.call("report", "--json", str(self.path / "m.json"), "--markdown", str(self.path / "m.md"), *files)
        self.assertEqual((code, out, err), (0, "", ""))
        data = json.loads((self.path / "m.json").read_text())
        self.assertEqual((data["observed"]["lift"], data["observed"]["low"], data["observed"]["high"]), (12.5, -2.3, 27.3))
        self.assertEqual(data["consistency"], "passed")
        self.assertFalse(data["criteria"]["M2"]["met"])
        self.assertIn("### Criteria", (self.path / "m.md").read_text())
        self.assertIsNone(re.search(r"T-\d\d", (self.path / "m.json").read_text()))

    def test_default_output_is_markdown_on_standard_output(self) -> None:
        code, out, _ = self.call("report", *self.write_runs(good_runs()))
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("### Result"))

    def test_invalid_runs_exit_one_name_the_check_and_write_nothing(self) -> None:
        runs = good_runs()
        runs[0]["run"]["models"] = {**r.MODELS, "effort": "low"}
        code, out, err = self.call("report", "--json", str(self.path / "m.json"), *self.write_runs(runs))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("lift: models:", err)
        self.assertFalse((self.path / "m.json").exists())

    def test_unreadable_input_exits_two(self) -> None:
        code, _, err = self.call("report", str(self.path / "missing.json"))
        self.assertEqual(code, 2)
        self.assertIn("cannot read", err)

    def test_a_malformed_recorded_file_exits_two_without_a_traceback(self) -> None:
        files = self.write_runs(good_runs())
        recorded = self.path / "recorded.json"
        for bad in ({"skills": [{"name": "x"}]}, [], {"suite_id": 3}, {"models": "x"}, {"other": 1}):
            with self.subTest(bad=bad):
                recorded.write_text(json.dumps(bad), encoding="utf-8")
                code, out, err = self.call("report", "--recorded", str(recorded), *files)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("lift: the recorded file cannot be used:", err)

    def test_recorded_file_is_used(self) -> None:
        files = self.write_runs(good_runs())
        recorded = self.path / "recorded.json"
        recorded.write_text(json.dumps({"suite_sha256": "00" * 32}), encoding="utf-8")
        code, _, err = self.call("report", "--recorded", str(recorded), *files)
        self.assertEqual(code, 1)
        self.assertIn("suite_sha256", err)


if __name__ == "__main__":
    unittest.main()
