"""What the published documents say and do not say (no claim without a measurement that met the bar), and that nothing private is
published. The repository's own files are read; nothing is written."""
from __future__ import annotations

import re
import unittest

import support

REPO = support.REPO
SKIPPED = {".git", ".venv", "__pycache__", "plans"}  # docs/plans holds the build plan and is never published


def published_files():
    for path in sorted(REPO.rglob("*")):
        parts = path.relative_to(REPO).parts
        if path.is_file() and not (set(parts) & SKIPPED) and path.suffix != ".pyc" and path.name != "scan.json":
            yield path


def read(name: str) -> str:
    return (REPO / name).read_text(encoding="utf-8")


STATUSES = ("Not measured yet", "Measured: met the bar", "Measured: below the bar", "Void")


def version_status(version: str) -> str:
    """The status line of a version's section in MEASUREMENTS.md."""
    found = re.search(rf"(?m)^## {re.escape(version)}\n\nStatus: (.+)\n", read("MEASUREMENTS.md"))
    return found.group(1) if found else ""

class DocumentShapeTest(unittest.TestCase):
    NAMES = ("README.md", "MEASUREMENTS.md", "CHANGELOG.md", "SECURITY.md")

    def test_each_document_starts_with_a_title(self) -> None:
        for name in self.NAMES:
            self.assertTrue(read(name).startswith("# "), name)

    def test_no_line_keeps_the_indent_the_plan_shows_the_documents_with(self) -> None:
        for name in self.NAMES:
            for number, line in enumerate(read(name).splitlines(), 1):
                self.assertFalse(line.startswith("    "), f"{name}:{number}")


class ReadmeTest(unittest.TestCase):
    def test_install_lines_are_pinned_to_the_current_version(self) -> None:
        text = read("README.md")
        self.assertIn("/plugin marketplace add spellwarden-ai/infra-pack#v0.9.0", text)
        self.assertIn("/plugin install infra-pack@spellwarden", text)
        self.assertIn("claude plugin marketplace add spellwarden-ai/infra-pack#v0.9.0", text)

    def test_the_five_skills_and_the_single_file_sentence(self) -> None:
        text = read("README.md")
        for name in ("infra-change-safety", "terraform-plan-review", "kubernetes-incident-triage",
                     "iam-least-privilege-review", "ci-pipeline-repair"):
            self.assertIn(f"`{name}`", text)
        self.assertIn("Each skill is a single SKILL.md: no scripts, nothing that runs.", text)

    def test_its_measurement_line_follows_the_status_in_measurements(self) -> None:
        # A lift is quoted only for a version that met the bar, and then exactly as MEASUREMENTS.md publishes it.
        text, status = read("README.md"), version_status("0.9.0")
        self.assertIn("(MEASUREMENTS.md)", text)
        if status != "Measured: met the bar":
            self.assertIsNone(re.search(r"benchmarked|[+-]\d+(\.\d+)? points", text, re.IGNORECASE))
            return
        line = re.search(r"Measured on (?:40|\d+ of 40) infrastructure tasks \(Infra-Ops 40\) with all five skills loaded: "
                         r"(\+\d+\.\d) points, 95% interval (-?\d+\.\d) to (-?\d+\.\d), over five runs, version 0\.9\.0, "
                         r"the (?:first|second|third) measurement of the pack on this suite\. Details in \[MEASUREMENTS\.md\]", text)
        self.assertIsNotNone(line)
        lift, low, high = line.groups()
        self.assertIn(f"| Observed (published) | {lift} | {low} to {high} |", read("MEASUREMENTS.md"))

    def test_links_point_at_files_that_exist(self) -> None:
        for target in re.findall(r"\]\(([^)#]+)\)", read("README.md")):
            self.assertTrue((REPO / target).is_file(), target)


class MeasurementsTest(unittest.TestCase):
    def test_the_fixed_section_and_the_version_section(self) -> None:
        text = read("MEASUREMENTS.md")
        self.assertIn("## How the pack is measured", text)
        self.assertIn("### What this measures", text)
        self.assertIn(version_status("0.9.0"), STATUSES)  # one "## <version>" section per version

    def test_the_four_criteria_and_the_three_kinds_are_defined(self) -> None:
        text = read("MEASUREMENTS.md")
        for criterion, weight in (("correctness", "0.40"), ("safety", "0.30"), ("evidence", "0.20"), ("efficiency", "0.10")):
            self.assertRegex(text, rf"\| `{criterion}` \| {re.escape(weight)} \|")
        for kind in ("trap", "approve", "insufficient_evidence"):
            self.assertIn(f"- `{kind}`:", text)

    def test_the_bar_is_the_one_of_the_protocol(self) -> None:
        text = read("MEASUREMENTS.md")
        for needle in ("at least 10.0 points", "above 0.0", "rounded half up to one decimal", "Measured: met the bar", "Measured: below the bar", "Void",
                       "At most three counted measurements"):
            self.assertIn(needle, text)

    def test_no_task_text_or_id_is_published(self) -> None:
        self.assertIsNone(re.search(r"\b(IO|PR)-[A-Z0-9]+-\d{2}\b", read("MEASUREMENTS.md")))


class SecurityAndChangelogTest(unittest.TestCase):
    def test_security_policy(self) -> None:
        text = read("SECURITY.md")
        self.assertIn("hello@spellwarden.ai", text)
        self.assertIn("The pack holds no code that runs", text)

    def test_changelog_has_the_first_version(self) -> None:
        self.assertIn("## 0.9.0", read("CHANGELOG.md"))

    def test_licence_is_apache_2(self) -> None:
        text = read("LICENSE")
        self.assertIn("Apache License", text)
        self.assertIn("Version 2.0, January 2004", text)


class PublicationTest(unittest.TestCase):
    """The repository becomes public. Everything but docs/plans is published, so nothing in it may point into the
    private repositories or this machine."""

    NEEDLES = ("/ho" + "me/", "docs/" + "specs", "docs/" + "reviews", "backend/" + "src", ".claude-" + "spellwarden",
               "infra-ops-40" + ".json", "Appendix " + "A")

    def test_no_private_path_or_reference(self) -> None:
        for path in published_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for needle in self.NEEDLES:
                if needle in text:
                    self.fail(f"{path.relative_to(REPO)} mentions {needle!r}")

    def test_no_reference_to_a_numbered_section_of_a_private_document(self) -> None:
        pattern = re.compile(r"\bspec(ification)? \d+\.\d+|(?<![\w.])\(\d\.\d{1,2}\)|\bclaims? P\d|\binvariant \d|\b[Rr]ules? \d+ of the spec")
        for path in published_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            found = pattern.search(text)
            if found:
                self.fail(f"{path.relative_to(REPO)} cites {found.group(0)!r}, which a public reader cannot follow")

    def test_nothing_is_named_skill_md_outside_the_skills_directory(self) -> None:
        for path in published_files():
            if path.name.lower() == "skill.md":
                self.assertIn("plugins/infra-pack/skills/", path.as_posix())

    def test_nothing_under_docs_is_published(self) -> None:
        docs = REPO / "docs"
        if docs.exists():
            self.assertEqual(sorted(child.name for child in docs.iterdir()), ["plans"])

    def test_no_api_key_value_is_written_down(self) -> None:
        for path in published_files():
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            self.assertIsNone(re.search(r"\bsw[kct]_[A-Za-z0-9_-]{40}\b", text), path.name)


if __name__ == "__main__":
    unittest.main()
