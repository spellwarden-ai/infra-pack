"""check_scan.py: the scanner's report must list exactly the five skills, no item
under tools/ and no finding. The reports are dictionaries written here; the scanner is not run."""
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


def report(skills=SKILL_PATHS, extra=(), findings=(), errors=()) -> dict:
    items = [item(".claude-plugin/marketplace.json", "marketplace"),
             item("plugins/infra-pack/.claude-plugin/plugin.json", "plugin-manifest")]
    items += [item(path) for path in skills] + list(extra)
    return {"schema": 1, "items": items, "findings": list(findings), "errors": list(errors)}


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


class MainTest(unittest.TestCase):
    def run_main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = check_scan.main(list(argv))
        return code, out.getvalue()

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


if __name__ == "__main__":
    unittest.main()
