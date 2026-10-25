"""Names and small helpers shared by the tools of this repository (standard library only)."""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

MARKETPLACE_NAME = "spellwarden"
PLUGIN_NAME = "infra-pack"
PLUGIN_DIR = Path("plugins") / PLUGIN_NAME
SKILLS_DIR = PLUGIN_DIR / "skills"
MARKETPLACE_FILE = Path(".claude-plugin") / "marketplace.json"
PLUGIN_FILE = PLUGIN_DIR / ".claude-plugin" / "plugin.json"

# The five skills, in the order a counted run loads them (see MEASUREMENTS.md).
SKILL_NAMES = (
    "infra-change-safety",
    "terraform-plan-review",
    "kubernetes-incident-triage",
    "iam-least-privilege-review",
    "ci-pipeline-repair",
)

# Directories no tool walks into (the scanner skips the same ones).
SKIPPED_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__"})


class Failure(NamedTuple):
    """One failed check, printed as `<path>:<line>: <rule>`."""

    path: str
    line: int
    rule: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}"


def has_skills(root: Path) -> bool:
    """True once `plugins/infra-pack/skills` exists. Before that the repository is a skeleton: the
    manifests and the tools are in place and the skills are still to be written, so the checks that
    need the five skills are skipped. From the moment the directory exists, all five are required."""
    return (root / SKILLS_DIR).is_dir()


def skill_file(root: Path, name: str) -> Path:
    return root / SKILLS_DIR / name / "SKILL.md"


def repo_root() -> Path:
    """The repository root: the parent of the `tools` directory this file sits in."""
    return Path(__file__).resolve().parents[1]
