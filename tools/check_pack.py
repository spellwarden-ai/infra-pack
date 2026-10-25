#!/usr/bin/env python3
"""Checks this repository against the rules of the pack, offline.

Run from anywhere: `.venv/bin/python tools/check_pack.py [--root DIR]`. It prints one line per
failure as `<path>:<line>: <rule>` and exits 1 on any failure, 0 otherwise. Python 3.11 or later; the
standard library plus PyYAML and, for the rules about skill text, the scanner package that
tools/requirements.txt pins (its frontmatter loader and its credential masker)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections.abc import Callable, Mapping
from pathlib import Path

import yaml
from spellwarden_scan import FrontmatterError, mask_credentials, parse_frontmatter

from pack_common import (
    MARKETPLACE_FILE,
    PLUGIN_DIR,
    PLUGIN_FILE,
    SKILL_NAMES,
    SKILLS_DIR,
    SKIPPED_DIRS,
    Failure,
    has_skills,
    repo_root,
    skill_file,
)

EXPECTED_MARKETPLACE = {
    "name": "spellwarden",
    "owner": {"name": "Spellwarden", "email": "hello@spellwarden.ai", "url": "https://spellwarden.ai"},
    "metadata": {"description": "Skills for infrastructure operations from Spellwarden."},
    "plugins": [
        {
            "name": "infra-pack",
            "source": "./plugins/infra-pack",
            "description": (
                "Five skills for infrastructure operations: change safety, Terraform plan review, "
                "Kubernetes incident triage, IAM least-privilege review and CI pipeline repair."
            ),
            "category": "infrastructure",
            "tags": ["terraform", "kubernetes", "iam", "ci", "infrastructure"],
        }
    ],
}

# Every key and value of plugin.json except the version, which has its own rule.
EXPECTED_PLUGIN = {
    "name": "infra-pack",
    "displayName": "Spellwarden Infra Pack",
    "description": (
        "Five skills for infrastructure operations: change safety, Terraform plan review, "
        "Kubernetes incident triage, IAM least-privilege review and CI pipeline repair."
    ),
    "author": {"name": "Spellwarden", "url": "https://spellwarden.ai"},
    "homepage": "https://github.com/spellwarden-ai/infra-pack",
    "repository": "https://github.com/spellwarden-ai/infra-pack",
    "license": "Apache-2.0",
    "keywords": ["terraform", "kubernetes", "iam", "ci", "infrastructure"],
}

EXPECTED_CONFIG = {"version": 1, "telemetry": False}

# Prose that is published: no em dash, no en dash, no exclamation mark.
DOC_FILES = ("README.md", "MEASUREMENTS.md", "CHANGELOG.md", "SECURITY.md")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")
TAG_RE = re.compile(r"refs/tags/v(\d+\.\d+\.\d+)")
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
FRONT_KEYS = ["name", "description", "license", "metadata"]
DESCRIPTION_MIN, DESCRIPTION_MAX = 200, 1024
SKILL_MAX_BYTES, SKILL_MAX_LINES, PACK_MAX_BYTES = 10_000, 250, 45_000

# Characters: no dash that reads as punctuation for the pack, no exclamation mark, no tab, no hidden text.
# This is the set rule SW-SKL-002 flags plus every other format character (category Cf).
HIDDEN_RE = re.compile(
    "[\u034f\u115f\u180b-\u180f\u200b-\u200f\u2028\u2029\u2060-\u2064\u202a-\u202e\u2066-\u2069\u3164"
    "\ufeff\uffa0\ufff9-\ufffb\ufe00-\ufe0f\U000e0000-\U000e007f\U000e0100-\U000e01ef]"
)
URL_RE = re.compile(r"https?://", re.IGNORECASE)
# Words aimed at whoever grades an answer, whole words, any case.
BANNED_WORDS = ("rubric", "grader", "graded", "judge", "benchmark", "eval", "evals", "infra-ops", "pass rate",
                "test task", "spellwarden")
# A phrase matches across any run of whitespace, a line break included, since Markdown may wrap it.
BANNED_RE = re.compile(r"(?<![A-Za-z0-9])("
                       + "|".join(r"\s+".join(re.escape(part) for part in word.split(" ")) for word in BANNED_WORDS)
                       + r")(?![A-Za-z0-9])", re.IGNORECASE)

Env = Mapping[str, str]
Check = Callable[[Path, Env], list[Failure]]


def required_files(skills_present: bool) -> tuple[str, ...]:
    """The files the repository's layout requires at its root and under `tools/`."""
    files = (
        MARKETPLACE_FILE.as_posix(),
        PLUGIN_FILE.as_posix(),
        ".spellwarden/config.yml",
        "tools/check_pack.py",
        "tools/pack_common.py",
        "tools/requirements.txt",
        "LICENSE",
        *DOC_FILES,
    )
    # SOURCES.md lists the public pages the skills were written from, so it exists with the skills.
    return (*files, "SOURCES.md") if skills_present else files


def _walk_files(root: Path, prune: bool = True):
    """Every file under `root` as a posix path relative to it.

    With `prune` the directories nobody scans are left out. Without it nothing is left out, and a symlinked
    directory counts as a file, because os.walk does not enter it (the layout rule under plugins/, F1).
    """
    for directory, names, files in os.walk(root):
        if prune:
            names[:] = sorted(name for name in names if name not in SKIPPED_DIRS)
        else:
            names.sort()
            files = [*files, *(name for name in names if (Path(directory) / name).is_symlink())]
        for file in sorted(files):
            yield (Path(directory) / file).relative_to(root).as_posix()


def _line_of(text: str, needle: str) -> int:
    """The 1-based line of the first occurrence of `needle`, else 1."""
    index = text.find(needle)
    return text.count("\n", 0, index) + 1 if index >= 0 else 1


def check_layout(root: Path, env: Env) -> list[Failure]:
    failures: list[Failure] = []
    skills_present = has_skills(root)
    for rel in required_files(skills_present):
        if not (root / rel).is_file():
            failures.append(Failure(rel, 1, "layout: required file is missing"))
    allowed = {PLUGIN_FILE.as_posix()}
    if skills_present:
        for name in SKILL_NAMES:
            rel = (SKILLS_DIR / name / "SKILL.md").as_posix()
            allowed.add(rel)
            if not (root / rel).is_file():
                failures.append(Failure(rel, 1, "layout: skill file is missing"))
    plugins = root / "plugins"
    if plugins.is_dir():
        for rel in _walk_files(plugins, prune=False):
            rel = f"plugins/{rel}"
            if rel not in allowed:
                failures.append(Failure(rel, 1, "layout: unexpected file under plugins/"))
    return failures


def check_skill_filenames(root: Path, env: Env) -> list[Failure]:
    """Test fixtures are never files named SKILL.md: the scanner would take them for skills."""
    failures: list[Failure] = []
    allowed = {(SKILLS_DIR / name / "SKILL.md").as_posix() for name in SKILL_NAMES}
    for rel in _walk_files(root):
        if rel.rsplit("/", 1)[-1].lower() == "skill.md" and rel not in allowed:
            failures.append(Failure(rel, 1, "layout: a file named SKILL.md outside plugins/infra-pack/skills/<name>/"))
    return failures


def _load_json(root: Path, rel: str, failures: list[Failure]) -> tuple[object, str] | None:
    path = root / rel
    if not path.is_file():
        return None  # check_layout already reports the missing file
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text), text
    except json.JSONDecodeError as exc:
        failures.append(Failure(rel, exc.lineno, f"manifest: invalid JSON ({exc.msg})"))
        return None


def _differences(actual: object, expected: object, prefix: str = "") -> list[str]:
    """Dotted names of the keys whose values differ, extra and missing keys included."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        found: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                found.append(f"{prefix}{key} (missing)")
            elif key not in expected:
                found.append(f"{prefix}{key} (not allowed)")
            else:
                found.extend(_differences(actual[key], expected[key], f"{prefix}{key}."))
        return found
    return [] if actual == expected else [prefix.rstrip(".") or "(document)"]


def _bracket_delta(line: str) -> int:
    """Opening minus closing brackets of a JSON line, outside strings (a JSON string never spans lines)."""
    delta, in_string, escaped = 0, False, False
    for char in line:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            delta += 1
        elif char in "]}":
            delta -= 1
    return delta


def _check_layout_of_json(rel: str, text: str) -> list[Failure]:
    """A final newline, and every line indented by two spaces per open bracket before it (an object or a list
    may stay on one line, as the repository's manifests keep `owner` and `tags`)."""
    failures: list[Failure] = []
    if not text.endswith("\n"):
        failures.append(Failure(rel, text.count("\n") + 1, "manifest: the file must end with a newline"))
    depth = 0
    for number, line in enumerate(text.split("\n"), 1):
        stripped = line.lstrip(" \t")
        indent = len(line) - len(stripped)
        if "\t" in line[:indent]:
            failures.append(Failure(rel, number, "manifest: indent with spaces, not tabs"))
        elif stripped and indent != 2 * (depth - (1 if stripped[0] in "]}" else 0)):
            failures.append(Failure(rel, number, "manifest: indent two spaces per level"))
        depth += _bracket_delta(line)
    return failures


def _json_key_line(text: str, path: list[str]) -> int:
    """The line of the last key of `path`, each key looked for after the one before it, else that of the last found."""
    start = 0
    for key in path:
        index = text.find(f'"{key}"', start)
        if index < 0:
            break
        start = index
    return text.count("\n", 0, start) + 1


def _differences_as_failures(rel: str, text: str, actual: object, expected: object) -> list[Failure]:
    failures: list[Failure] = []
    for key in _differences(actual, expected):
        failures.append(Failure(rel, _json_key_line(text, key.split(" ")[0].split(".")),
                                f"manifest: {key} differs from the expected manifest"))
    return failures


def check_manifests(root: Path, env: Env) -> list[Failure]:
    failures: list[Failure] = []
    rel = MARKETPLACE_FILE.as_posix()
    loaded = _load_json(root, rel, failures)
    if loaded is not None:
        data, text = loaded
        failures.extend(_check_layout_of_json(rel, text))
        failures.extend(_differences_as_failures(rel, text, data, EXPECTED_MARKETPLACE))
    rel = PLUGIN_FILE.as_posix()
    loaded = _load_json(root, rel, failures)
    if loaded is not None:
        data, text = loaded
        failures.extend(_check_layout_of_json(rel, text))
        if isinstance(data, dict):
            version = data.get("version")
            if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
                failures.append(Failure(rel, _line_of(text, '"version"'), "manifest: version must be a string x.y.z"))
            rest = {key: value for key, value in data.items() if key != "version"}
            failures.extend(_differences_as_failures(rel, text, rest, EXPECTED_PLUGIN))
        else:
            failures.append(Failure(rel, 1, "manifest: the document must be an object"))
    return failures


def check_docs(root: Path, env: Env) -> list[Failure]:
    failures: list[Failure] = []
    for rel in DOC_FILES:
        path = root / rel
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for char, reason in (("\u2014", "an em dash"), ("\u2013", "an en dash"), ("!", "an exclamation mark")):
                if char in line:
                    failures.append(Failure(rel, number, f"docs: {reason}"))
    return failures


def check_config(root: Path, env: Env) -> list[Failure]:
    rel = ".spellwarden/config.yml"
    path = root / rel
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return [Failure(rel, 1, "config: not valid YAML")]
    if data != EXPECTED_CONFIG:
        return [Failure(rel, 1, "config: must hold exactly version: 1 and telemetry: false")]
    return []


def _plugin_version(root: Path) -> str | None:
    """The version of plugin.json, or None when the file is unreadable (check_manifests reports that)."""
    try:
        data = json.loads((root / PLUGIN_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) else None


def _skills(root: Path) -> list[tuple[str, str, str]]:
    """(name, posix path, text) of every skill file that exists and is UTF-8 (check_skill_text reports one that is not)."""
    found = []
    for name in SKILL_NAMES:
        path = skill_file(root, name)
        if path.is_file():
            try:
                text = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                continue
            found.append((name, path.relative_to(root).as_posix(), text))
    return found


def _key_line(text: str, key: str) -> int:
    """The 1-based line where `key:` starts a line (nested keys included), else 1."""
    match = re.search(rf"^[ ]*{re.escape(key)}[ ]*:", text, re.MULTILINE)
    return text.count("\n", 0, match.start()) + 1 if match else 1


def check_skill_frontmatter(root: Path, env: Env) -> list[Failure]:
    """The layout and the frontmatter of each skill, loaded as the scanner loads it."""
    if not has_skills(root):
        return []
    failures: list[Failure] = []
    plugin_version = _plugin_version(root)
    for name, rel, text in _skills(root):
        try:
            front, _ = parse_frontmatter(text)
        except FrontmatterError as exc:
            failures.append(Failure(rel, 1, f"frontmatter: {exc.reason}"))
            continue
        keys = list(front)
        if keys != FRONT_KEYS:
            wrong = next((key for key, want in zip(keys, FRONT_KEYS) if key != want), None)
            if wrong is None and len(keys) > len(FRONT_KEYS):
                wrong = keys[len(FRONT_KEYS)]
            failures.append(Failure(rel, _key_line(text, str(wrong)) if wrong else 1,
                                    "frontmatter: the keys must be name, description, license, metadata, in this order"))
        value = front.get("name")
        if value != name:
            failures.append(Failure(rel, _key_line(text, "name"), f"frontmatter: name must equal the directory name {name}"))
        elif NAME_RE.fullmatch(value) is None or len(value) > 64:
            failures.append(Failure(rel, _key_line(text, "name"), "frontmatter: name must be lowercase words joined by hyphens, 64 characters at most"))
        value = front.get("description")
        if not isinstance(value, str) or not DESCRIPTION_MIN <= len(value) <= DESCRIPTION_MAX:
            size = len(value) if isinstance(value, str) else 0
            failures.append(Failure(rel, _key_line(text, "description"),
                                    f"frontmatter: description must be {DESCRIPTION_MIN} to {DESCRIPTION_MAX} characters, it has {size}"))
        if front.get("license") != "Apache-2.0":
            failures.append(Failure(rel, _key_line(text, "license"), "frontmatter: license must be Apache-2.0"))
        meta = front.get("metadata")
        if not isinstance(meta, dict) or set(meta) != {"version", "author"}:
            failures.append(Failure(rel, _key_line(text, "metadata"), "frontmatter: metadata must hold exactly version and author"))
            continue
        version = meta["version"]
        if not isinstance(version, str):
            failures.append(Failure(rel, _key_line(text, "version"),
                                    f"frontmatter: metadata.version must be a quoted string, it loads as {type(version).__name__}"))
        elif plugin_version is not None and version != plugin_version:
            failures.append(Failure(rel, _key_line(text, "version"),
                                    f"version: metadata.version {version} differs from plugin.json {plugin_version}"))
        if meta["author"] != "Spellwarden":
            failures.append(Failure(rel, _key_line(text, "author"), "frontmatter: metadata.author must be Spellwarden"))
    return failures


def check_skill_sizes(root: Path, env: Env) -> list[Failure]:
    """The sizes: bytes and lines per skill, bytes for the pack."""
    if not has_skills(root):
        return []
    failures: list[Failure] = []
    total = 0
    for _, rel, text in _skills(root):
        size = len(text.encode("utf-8"))
        total += size
        lines = len(text.split("\n")) - (1 if text.endswith("\n") else 0)
        if size > SKILL_MAX_BYTES:
            failures.append(Failure(rel, 1, f"size: {size} bytes, over {SKILL_MAX_BYTES}"))
        if lines > SKILL_MAX_LINES:
            failures.append(Failure(rel, SKILL_MAX_LINES + 1, f"size: {lines} lines, over {SKILL_MAX_LINES}"))
    if total > PACK_MAX_BYTES:
        failures.append(Failure(SKILLS_DIR.as_posix(), 1, f"size: the skills total {total} bytes, over {PACK_MAX_BYTES}"))
    return failures


def _body_offset(text: str) -> int | None:
    """How many lines come before the body (frontmatter included), or None when there is no frontmatter."""
    try:
        _, body = parse_frontmatter(text)
    except FrontmatterError:
        return None
    return text.count("\n") - body.count("\n")


def check_skill_text(root: Path, env: Env) -> list[Failure]:
    """The text of each skill: characters, URLs, words aimed at a grader, and the credential masker."""
    if not has_skills(root):
        return []
    failures: list[Failure] = []
    for name in SKILL_NAMES:
        path = skill_file(root, name)
        if path.is_file():
            raw = path.read_bytes()
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                failures.append(Failure(path.relative_to(root).as_posix(), raw.count(b"\n", 0, exc.start) + 1,
                                        "chars: the file is not UTF-8 text"))
    for _, rel, text in _skills(root):
        lines = text.split("\n")
        offset = _body_offset(text)
        for number, line in enumerate(lines, 1):
            for char, reason in (("\u2014", "an em dash"), ("\u2013", "an en dash"), ("!", "an exclamation mark"),
                                 ("\t", "a tab"), ("\r", "a carriage return, use LF line endings")):
                if char in line:
                    failures.append(Failure(rel, number, f"chars: {reason}"))
            if not line.isascii() and any(HIDDEN_RE.match(char) or unicodedata.category(char) == "Cf" for char in line):
                failures.append(Failure(rel, number, "chars: a hidden or format character"))
            if URL_RE.search(line):
                failures.append(Failure(rel, number, "url: a URL has no place in a skill"))
        if offset is not None:
            body_start = sum(len(line) + 1 for line in lines[:offset])
            found = {(text.count("\n", 0, match.start()) + 1, " ".join(match.group(1).lower().split()))
                     for match in BANNED_RE.finditer(text, body_start)}
            for number, word in sorted(found):
                failures.append(Failure(rel, number, f"words: the body must not contain {word!r}"))
        if not text.endswith("\n"):
            failures.append(Failure(rel, len(lines), "chars: the file must end with a newline"))
        masked = mask_credentials(text)
        if masked != text:
            masked_lines = masked.split("\n")
            number = next((index for index, (a, b) in enumerate(zip(lines, masked_lines), 1) if a != b),
                          min(len(lines), len(masked_lines)) + 1)
            failures.append(Failure(rel, number, "masker: the credential masker rewrites this text; write a pin as "
                                                 "actions/checkout@<full commit SHA> and a digest as @sha256:<digest>"))
    return failures


def check_tag(root: Path, env: Env) -> list[Failure]:
    """On a tag build (GITHUB_REF is refs/tags/v...) the tag must be v<x.y.z> and equal the plugin version."""
    ref = env.get("GITHUB_REF", "")
    if not ref.startswith("refs/tags/v"):
        return []
    try:
        line = _line_of((root / PLUGIN_FILE).read_text(encoding="utf-8"), '"version"')
    except OSError:
        line = 1
    if not has_skills(root):
        return [Failure(PLUGIN_FILE.as_posix(), line,
                        "tag: a release tag needs the five skills under plugins/infra-pack/skills")]
    match = TAG_RE.fullmatch(ref)
    if match is None:
        return [Failure(PLUGIN_FILE.as_posix(), line, f"tag: {ref[len('refs/tags/'):]} is not a release tag v<x.y.z>")]
    version = _plugin_version(root)
    if version is None or match.group(1) == version:
        return []
    return [Failure(PLUGIN_FILE.as_posix(), line, f"tag: v{match.group(1)} differs from the plugin version {version}")]


CHECKS: tuple[Check, ...] = (
    check_layout,
    check_skill_filenames,
    check_manifests,
    check_config,
    check_docs,
    check_skill_frontmatter,
    check_skill_sizes,
    check_skill_text,
    check_tag,
)


def check_repo(root: Path, env: Env | None = None) -> list[Failure]:
    """Every failure of every check, in path and line order."""
    environment = os.environ if env is None else env
    failures: list[Failure] = []
    for check in CHECKS:
        failures.extend(check(root, environment))
    return sorted(failures, key=lambda failure: (failure.path, failure.line, failure.rule))


def main(argv: list[str] | None = None, env: Env | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the pack repository against its rules.")
    parser.add_argument("--root", type=Path, default=repo_root(), help="the repository root (default: this checkout)")
    args = parser.parse_args(argv)
    failures = check_repo(args.root, env)
    for failure in failures:
        print(failure)
    if failures:
        print(f"check_pack: {len(failures)} failure(s)", file=sys.stderr)
        return 1
    if not has_skills(args.root):
        print("check_pack: notice: plugins/infra-pack/skills does not exist yet, so the skill rules were skipped",
              file=sys.stderr)
    print("check_pack: ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
