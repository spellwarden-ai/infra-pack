"""Helpers shared by the tests. Every tree a test needs is written to a temporary directory at run
time, from the strings below: no fixture is a file named SKILL.md (the scanner would take it for a
skill), and no test reads real evaluation data."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
REPO = TOOLS.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import check_pack  # noqa: E402
from pack_common import SKILL_NAMES  # noqa: E402

DESCRIPTION = (
    "Placeholder description for the {name} skill, written for the tests of this repository only. "
    "It says what the skill does and when to use it in plain words, so that its length falls inside "
    "the range the pack checker accepts for a description."
)
BODY = "# Placeholder\n\nPlaceholder body used by the tests.\n"


def marketplace() -> dict:
    return copy.deepcopy(check_pack.EXPECTED_MARKETPLACE)


def plugin(version: str = "0.9.0") -> dict:
    return {**copy.deepcopy(check_pack.EXPECTED_PLUGIN), "version": version}


def dump(data: object) -> str:
    return json.dumps(data, indent=2) + "\n"


def skill_text(name: str = "infra-change-safety", *, version: str = "0.9.0", body: str = BODY,
               front: str | None = None, description: str | None = None) -> str:
    """A valid SKILL.md made of placeholders. `front` replaces the whole frontmatter block."""
    if front is None:
        text = DESCRIPTION.format(name=name) if description is None else description
        front = (
            "---\n"
            f"name: {name}\n"
            f"description: {text}\n"
            "license: Apache-2.0\n"
            "metadata:\n"
            f'  version: "{version}"\n'
            "  author: Spellwarden\n"
            "---\n"
        )
    return front + "\n" + body


def valid_files(with_skills: bool = True) -> dict[str, str]:
    """Every file of a tree that passes every check, as {posix path: text}."""
    files = {
        ".claude-plugin/marketplace.json": dump(marketplace()),
        "plugins/infra-pack/.claude-plugin/plugin.json": dump(plugin()),
        ".spellwarden/config.yml": "version: 1\ntelemetry: false\n",
    }
    for rel in check_pack.required_files(with_skills):
        files.setdefault(rel, "placeholder\n")
    if with_skills:
        for name in SKILL_NAMES:
            files[f"plugins/infra-pack/skills/{name}/SKILL.md"] = skill_text(name)
    return files


def write_tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


class TreeTestCase(unittest.TestCase):
    """Each test gets an empty temporary directory as `self.root`."""

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="infra-pack-test-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def build(self, with_skills: bool = True, changes: dict[str, str | None] | None = None) -> None:
        """Empty the root, write a valid tree, then apply `changes`: {posix path: new text, or None to leave it out}."""
        for child in self.root.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        files = valid_files(with_skills)
        for rel, value in (changes or {}).items():
            if value is None:
                files.pop(rel, None)
            else:
                files[rel] = value
        write_tree(self.root, files)

    def failures(self, env: dict[str, str] | None = None) -> list[str]:
        return [str(item) for item in check_pack.check_repo(self.root, env or {})]

    def assertRuleFailed(self, rule: str, path: str | None = None, env: dict[str, str] | None = None) -> None:
        found = self.failures(env)
        for line in found:
            where, _, rest = line.partition(": ")
            if rest.startswith(rule) and (path is None or where.startswith(path + ":")):
                return
        self.fail(f"no failure for rule {rule!r} at {path!r} in {found!r}")

    def assertClean(self, env: dict[str, str] | None = None) -> None:
        self.assertEqual(self.failures(env), [])
