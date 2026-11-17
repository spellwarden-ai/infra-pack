"""check_scan.py: the scanner's report must list exactly the five skills, no item
under tools/ and no finding, and its description lint must cover exactly the five skills.
The reports are dictionaries written here; the scanner is not run."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import support  # noqa: F401  (puts tools/ on sys.path)

import check_scan
from pack_common import SKILL_NAMES

SKILL_PATHS = [f"plugins/infra-pack/skills/{name}" for name in SKILL_NAMES]


def item(path: str, kind: str = "skill") -> dict:
    return {"kind": kind, "name": path.rsplit("/", 1)[-1], "path": path, "plugin": "infra-pack"}


NO_USE_WHEN = {"id": "SW-LINT-002", "severity": "info", "other_path": None,
               "message": "The description has no use-when clause, so an agent has to guess when the skill applies."}


def lint_entry(path: str, notes=(), left_out: int = 0) -> dict:
    """One entry of the description lint as scanner 1.17.0 writes it: every linted skill has one, notes or none."""
    return {"skill": path, "notes": list(notes), "left_out": left_out}


def report(skills=SKILL_PATHS, extra=(), findings=(), errors=(), lint=SKILL_PATHS) -> dict:
    """A report; `lint` lists linted skill paths or raw entries (a path becomes an entry), or is None for no lint."""
    items = [item(".claude-plugin/marketplace.json", "marketplace"),
             item("plugins/infra-pack/.claude-plugin/plugin.json", "plugin-manifest")]
    items += [item(path) for path in skills] + list(extra)
    data = {"schema": 1, "items": items, "findings": list(findings), "errors": list(errors)}
    if lint is not None:
        data["lint"] = [lint_entry(entry) if isinstance(entry, str) else entry for entry in lint]
    return data


class CheckScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.with_skills = Path(tempfile.mkdtemp(prefix="infra-pack-scan-"))
        self.skeleton = Path(tempfile.mkdtemp(prefix="infra-pack-scan-"))
        self.addCleanup(shutil.rmtree, self.with_skills, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.skeleton, ignore_errors=True)
        (self.with_skills / "plugins" / "infra-pack" / "skills").mkdir(parents=True)

    def rules(self, data: object, root: Path | None = None) -> list[str]:
        return [str(failure) for failure in check_scan.check_report(data, root or self.with_skills)]

    def test_five_skills_and_nothing_else_passes(self) -> None:
        self.assertEqual(self.rules(report()), [])

    def test_four_skills_fail(self) -> None:
        found = self.rules(report(skills=SKILL_PATHS[:4]))
        self.assertEqual(found, [f"{SKILL_PATHS[4]}:1: skills: the scanner did not list this skill"])

    def test_a_sixth_skill_fails(self) -> None:
        found = self.rules(report(skills=SKILL_PATHS + ["plugins/infra-pack/skills/extra-skill"]))
        self.assertEqual(found, ["plugins/infra-pack/skills/extra-skill:1: skills: the scanner listed a skill the layout does not have"])

    def test_a_skill_listed_twice_fails(self) -> None:
        found = self.rules(report(skills=SKILL_PATHS + [SKILL_PATHS[0]]))
        self.assertEqual(found, [f"{SKILL_PATHS[0]}:1: skills: the scanner listed this skill more than once"])

    def test_any_item_under_tools_fails(self) -> None:
        for kind in ("skill", "mcp-server", "hook"):
            with self.subTest(kind=kind):
                found = self.rules(report(extra=[item("tools/tests/fixture", kind)]))
                self.assertIn("tools/tests/fixture:1: tools: the scanner found an item under tools/", found)

    def test_one_finding_fails_and_names_rule_and_place(self) -> None:
        finding = {"rule_id": "SW-SKL-006", "severity": "medium", "suppressed": False,
                   "location": {"path": f"{SKILL_PATHS[1]}/SKILL.md", "line": 17}}
        self.assertEqual(self.rules(report(findings=[finding])), [f"{SKILL_PATHS[1]}/SKILL.md:17: finding: SW-SKL-006 (medium)"])

    def test_a_suppressed_finding_still_fails(self) -> None:
        finding = {"rule_id": "SW-SKL-031", "severity": "low", "suppressed": True, "location": {"path": "a", "line": 1}}
        self.assertEqual(len(self.rules(report(findings=[finding]))), 1)

    def test_a_scanner_error_fails(self) -> None:
        found = self.rules(report(errors=[{"code": "settings_invalid", "message": "x", "path": "y"}]))
        self.assertEqual(found, ["scan.json:1: scan: the scanner reported an error (settings_invalid)"])

    def test_skeleton_state_expects_no_skill(self) -> None:
        self.assertEqual(self.rules(report(skills=[]), self.skeleton), [])
        self.assertEqual(len(self.rules(report(), self.skeleton)), 5)

    def test_malformed_reports(self) -> None:
        self.assertEqual(len(self.rules([])), 1)
        self.assertEqual(len(self.rules({"findings": []})), 1)


class LintTest(unittest.TestCase):
    """The description lint of scanner 1.17.0: required with the skills, exactly the five, notes never a failure."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="infra-pack-lint-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        (self.root / "plugins" / "infra-pack" / "skills").mkdir(parents=True)

    def rules(self, data: object, root: Path | None = None) -> list[str]:
        return [str(failure) for failure in check_scan.check_report(data, root or self.root)]

    def test_a_report_without_lint_fails(self) -> None:
        self.assertEqual(self.rules(report(lint=None)),
                         ["scan.json:1: lint: the report has no description lint (scanner 1.17.0 or later writes one)"])

    def test_a_lint_that_is_not_a_list_fails(self) -> None:
        data = report()
        data["lint"] = {"skill": SKILL_PATHS[0]}
        self.assertEqual(len(self.rules(data)), 1)

    def test_all_five_skills_without_notes_pass(self) -> None:
        self.assertEqual(self.rules(report()), [])

    def test_one_skill_missing_from_the_lint_fails(self) -> None:
        found = self.rules(report(lint=SKILL_PATHS[1:]))
        self.assertEqual(found, [f"{SKILL_PATHS[0]}:1: lint: the description lint did not cover this skill"])

    def test_an_empty_lint_names_every_skill(self) -> None:
        self.assertEqual(len(self.rules(report(lint=[]))), 5)

    def test_an_extra_skill_in_the_lint_fails(self) -> None:
        found = self.rules(report(lint=SKILL_PATHS + ["skills/elsewhere"]))
        self.assertEqual(found, ["skills/elsewhere:1: lint: the description lint covered a skill the layout does not have"])

    def test_a_skill_linted_twice_fails(self) -> None:
        found = self.rules(report(lint=SKILL_PATHS + [SKILL_PATHS[2]]))
        self.assertEqual(found, [f"{SKILL_PATHS[2]}:1: lint: the description lint listed this skill more than once"])

    def test_an_entry_without_skill_or_notes_fails(self) -> None:
        for bad in ({"notes": [], "left_out": 0}, {"skill": SKILL_PATHS[0], "left_out": 0}, ["x"]):
            with self.subTest(entry=bad):
                found = self.rules(report(lint=SKILL_PATHS + [bad]))
                self.assertEqual(found, ["scan.json:1: lint: an entry of the description lint names no skill or has no list of notes"])

    def test_notes_never_fail(self) -> None:
        overlap = {"id": "SW-LINT-004", "severity": "info", "message": "overlaps", "other_path": SKILL_PATHS[1]}
        entries = [lint_entry(path, [NO_USE_WHEN, overlap], left_out=3) for path in SKILL_PATHS]
        self.assertEqual(self.rules(report(lint=entries)), [])

    def test_note_lines_name_skill_id_and_message(self) -> None:
        overlap = {"id": "SW-LINT-004", "severity": "info", "message": "overlaps", "other_path": SKILL_PATHS[1]}
        entries = [lint_entry(SKILL_PATHS[0], [NO_USE_WHEN, overlap], left_out=2)] + [lint_entry(p) for p in SKILL_PATHS[1:]]
        self.assertEqual(check_scan.lint_note_lines(report(lint=entries)), [
            f"{SKILL_PATHS[0]}: SW-LINT-002: {NO_USE_WHEN['message']}",
            f"{SKILL_PATHS[0]}: SW-LINT-004: overlaps (other skill: {SKILL_PATHS[1]})",
            f"{SKILL_PATHS[0]}: 2 more note(s) were not kept in the report",
        ])

    def test_no_note_lines_without_notes_or_without_lint(self) -> None:
        self.assertEqual(check_scan.lint_note_lines(report()), [])
        self.assertEqual(check_scan.lint_note_lines(report(lint=None)), [])
        self.assertEqual(check_scan.lint_note_lines([]), [])

    def test_skeleton_state_does_not_require_the_lint(self) -> None:
        skeleton = Path(tempfile.mkdtemp(prefix="infra-pack-lint-"))
        self.addCleanup(shutil.rmtree, skeleton, ignore_errors=True)
        self.assertEqual(self.rules(report(skills=[], lint=None), skeleton), [])
        self.assertEqual(self.rules(report(skills=[], lint=[]), skeleton), [])


class MainTest(unittest.TestCase):
    def run_main(self, *argv: str) -> tuple[int, str]:
        return self.run_main_with_stderr(*argv)[:2]

    def run_main_with_stderr(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check_scan.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "tree"
            (root / "plugins" / "infra-pack" / "skills").mkdir(parents=True)
            good, bad = Path(scratch) / "good.json", Path(scratch) / "bad.json"
            good.write_text(json.dumps(report()), encoding="utf-8")
            bad.write_text(json.dumps(report(skills=SKILL_PATHS[:3])), encoding="utf-8")
            self.assertEqual(self.run_main("--root", str(root), str(good)), (0, ""))
            code, out = self.run_main("--root", str(root), str(bad))
            self.assertEqual(code, 1)
            self.assertEqual(len(out.splitlines()), 2)
            self.assertEqual(self.run_main(str(Path(scratch) / "missing.json"))[0], 2)

    def test_skeleton_root_accepts_an_empty_skill_list(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "scan.json"
            path.write_text(json.dumps(report(skills=[])), encoding="utf-8")
            skeleton = Path(scratch) / "skeleton"
            skeleton.mkdir()
            self.assertEqual(self.run_main("--root", str(skeleton), str(path)), (0, ""))

    def test_lint_notes_go_to_stderr_and_keep_exit_0(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "tree"
            (root / "plugins" / "infra-pack" / "skills").mkdir(parents=True)
            path = Path(scratch) / "scan.json"
            path.write_text(json.dumps(report(lint=[lint_entry(p, [NO_USE_WHEN]) for p in SKILL_PATHS])), encoding="utf-8")
            code, out, err = self.run_main_with_stderr("--root", str(root), str(path))
        self.assertEqual((code, out), (0, ""))
        notes = [line for line in err.splitlines() if "SW-LINT-002" in line]
        self.assertEqual(len(notes), 5)
        self.assertTrue(all(line.startswith("check_scan: description lint (informational): ") for line in notes))

    def test_a_report_without_lint_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "tree"
            (root / "plugins" / "infra-pack" / "skills").mkdir(parents=True)
            path = Path(scratch) / "scan.json"
            path.write_text(json.dumps(report(lint=None)), encoding="utf-8")
            code, out = self.run_main("--root", str(root), str(path))
        self.assertEqual(code, 1)
        self.assertEqual(out, "scan.json:1: lint: the report has no description lint (scanner 1.17.0 or later writes one)\n")


if __name__ == "__main__":
    unittest.main()
