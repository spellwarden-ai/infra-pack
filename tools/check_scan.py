#!/usr/bin/env python3
"""Checks the scanner's JSON report of this repository.

`spellwarden scan . --format json --output scan.json --fail-on low` exits 0 when nothing is found,
even when it found no skill at all, so a layout the scanner does not discover would pass unnoticed.
This check reads the report and requires: exactly the five skill directories of the layout as
skills, no item under `tools/`, no finding and no error. Before the skills exist (the skeleton
state of the repository), it requires no skill instead.

Usage: `python tools/check_scan.py [--root DIR] scan.json`. One line per failure as
`<path>:<line>: <rule>`; exit 1 on any failure, 2 when the report cannot be read, else 0."""
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
    return sorted(failures, key=lambda failure: (failure.path, failure.line, failure.rule))


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
    for failure in failures:
        print(failure)
    if failures:
        print(f"check_scan: {len(failures)} failure(s)", file=sys.stderr)
        return 1
    print("check_scan: ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
