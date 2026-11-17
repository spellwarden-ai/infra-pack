#!/usr/bin/env python3
"""Checks the scanner's JSON report of this repository.

`spellwarden scan . --format json --output scan.json --fail-on low` exits 0 when nothing is found,
even when it found no skill at all, so a layout the scanner does not discover would pass unnoticed.
This check reads the report and requires: exactly the five skill directories of the layout as
skills, no item under `tools/`, no finding and no error. Before the skills exist (the skeleton
state of the repository), it requires no skill instead.

With the skills in place it also requires the report's description lint (scanner 1.17.0 or later):
the `lint` list, which holds one entry `{"skill", "notes", "left_out"}` for every skill the scanner
linted, an empty list of notes included, must name exactly the five skill directories of the layout,
each once. A report without `lint` comes from an older scanner and fails. The notes themselves are
informational and never fail the check: each is printed to stderr as `<skill>: <id>: <message>`, so
the CI log shows them. In the skeleton state the lint is not required.

Usage: `python tools/check_scan.py [--root DIR] scan.json`. One line per failure as
`<path>:<line>: <rule>` on stdout, one line per lint note on stderr; exit 1 on any failure, 2 when
the report cannot be read, else 0."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pack_common import SKILL_NAMES, SKILLS_DIR, Failure, has_skills, repo_root


def expected_skill_paths(root: Path) -> list[str]:
    if not has_skills(root):
        return []
    return sorted((SKILLS_DIR / name).as_posix() for name in SKILL_NAMES)


def check_report(report: object, root: Path, source: str = "scan.json") -> list[Failure]:
    if not isinstance(report, dict):
        return [Failure(source, 1, "scan: the report must be a JSON object")]
    failures: list[Failure] = []
    items = report.get("items")
    if not isinstance(items, list):
        return [Failure(source, 1, "scan: the report has no list of items")]
    paths = [str(item.get("path", "")) for item in items if isinstance(item, dict)]
    skills = sorted(str(item.get("path", "")) for item in items if isinstance(item, dict) and item.get("kind") == "skill")
    wanted = expected_skill_paths(root)
    for path in sorted(set(wanted) - set(skills)):
        failures.append(Failure(path, 1, "skills: the scanner did not list this skill"))
    for path in sorted(set(skills) - set(wanted)):
        failures.append(Failure(path, 1, "skills: the scanner listed a skill the layout does not have"))
    for path in sorted({path for path in skills if skills.count(path) > 1}):
        failures.append(Failure(path, 1, "skills: the scanner listed this skill more than once"))
    for path in paths:
        if path == "tools" or path.startswith("tools/"):
            failures.append(Failure(path, 1, "tools: the scanner found an item under tools/"))
    for finding in report.get("findings") or []:
        location = finding.get("location") if isinstance(finding, dict) else None
        location = location if isinstance(location, dict) else {}
        rule = finding.get("rule_id", "?") if isinstance(finding, dict) else "?"
        severity = finding.get("severity", "?") if isinstance(finding, dict) else "?"
        failures.append(Failure(str(location.get("path", source)), int(location.get("line") or 1),
                                f"finding: {rule} ({severity})"))
    for error in report.get("errors") or []:
        code = error.get("code", "?") if isinstance(error, dict) else "?"
        failures.append(Failure(source, 1, f"scan: the scanner reported an error ({code})"))
    if wanted:
        failures += check_lint(report, wanted, source)
    return sorted(failures, key=lambda failure: (failure.path, failure.line, failure.rule))


def lint_entries(report: dict) -> list[dict] | None:
    """The entries of the report's description lint, or None when the report has no `lint` list."""
    lint = report.get("lint")
    if not isinstance(lint, list):
        return None
    return lint


def is_linted_skill(entry: object) -> bool:
    """An entry as the scanner writes one for a skill it linted: a skill path and a list of notes."""
    return isinstance(entry, dict) and isinstance(entry.get("skill"), str) and isinstance(entry.get("notes"), list)


def check_lint(report: dict, wanted: list[str], source: str) -> list[Failure]:
    """The description lint must have run over exactly the skills of the layout. The scanner writes an
    entry for every skill it linted, with an empty list of notes when a description triggers none, so
    the set of entries is the set of skills the lint covered."""
    entries = lint_entries(report)
    if entries is None:
        return [Failure(source, 1, "lint: the report has no description lint (scanner 1.17.0 or later writes one)")]
    failures: list[Failure] = []
    linted = [entry["skill"] for entry in entries if is_linted_skill(entry)]
    for _ in range(len(entries) - len(linted)):
        failures.append(Failure(source, 1, "lint: an entry of the description lint names no skill or has no list of notes"))
    for path in sorted(set(wanted) - set(linted)):
        failures.append(Failure(path, 1, "lint: the description lint did not cover this skill"))
    for path in sorted(set(linted) - set(wanted)):
        failures.append(Failure(path, 1, "lint: the description lint covered a skill the layout does not have"))
    for path in sorted({path for path in linted if linted.count(path) > 1}):
        failures.append(Failure(path, 1, "lint: the description lint listed this skill more than once"))
    return failures


def lint_note_lines(report: object) -> list[str]:
    """One line per note of the description lint, `<skill>: <id>: <message>`, in the report's order, plus
    one line for a skill whose notes the scanner capped. Informational: never a failure."""
    entries = lint_entries(report) if isinstance(report, dict) else None
    lines: list[str] = []
    for entry in entries or []:
        if not is_linted_skill(entry):
            continue
        for note in entry["notes"]:
            note = note if isinstance(note, dict) else {}
            line = f"{entry['skill']}: {note.get('id', '?')}: {note.get('message', '')}"
            if note.get("other_path"):
                line += f" (other skill: {note['other_path']})"
            lines.append(line)
        left_out = entry.get("left_out")
        if isinstance(left_out, int) and left_out > 0:
            lines.append(f"{entry['skill']}: {left_out} more note(s) were not kept in the report")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the scanner's JSON report of this repository.")
    parser.add_argument("report", type=Path, help="the file written by `spellwarden scan --format json --output`")
    parser.add_argument("--root", type=Path, default=repo_root(), help="the repository root (default: this checkout)")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"check_scan: cannot read {args.report}: {exc}", file=sys.stderr)
        return 2
    failures = check_report(report, args.root, args.report.name)
    for line in lint_note_lines(report):
        print(f"check_scan: description lint (informational): {line}", file=sys.stderr)
    for failure in failures:
        print(failure)
    if failures:
        print(f"check_scan: {len(failures)} failure(s)", file=sys.stderr)
        return 1
    print("check_scan: ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
