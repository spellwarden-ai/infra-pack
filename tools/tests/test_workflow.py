"""The CI workflow: permissions, pins, and the commands of the two jobs. The file is parsed, not run."""
from __future__ import annotations

import re
import unittest

import yaml

import support

WORKFLOW = support.REPO / ".github" / "workflows" / "check.yml"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SCAN = "spellwarden-ai/scan@653350861eac5f98938eeaba0b91bf7143b83ddd"


class WorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)

    def steps(self, job: str) -> list[dict]:
        return self.data["jobs"][job]["steps"]

    def test_runs_on_push_and_pull_request(self) -> None:
        triggers = self.data.get("on", self.data.get(True))  # YAML 1.1 reads a bare `on` as true
        self.assertEqual(sorted(triggers), ["pull_request", "push"])

    def test_least_privilege_permissions(self) -> None:
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertNotIn("permissions", self.data["jobs"]["pack"])
        self.assertEqual(self.data["jobs"]["scan"]["permissions"], {"contents": "read", "security-events": "write"})

    def test_two_jobs_on_ubuntu_24_04(self) -> None:
        self.assertEqual(sorted(self.data["jobs"]), ["pack", "scan"])
        for job in self.data["jobs"].values():
            self.assertEqual(job["runs-on"], "ubuntu-24.04")

    def test_every_action_is_pinned_by_full_commit_with_a_version_comment(self) -> None:
        uses = [line for line in self.text.splitlines() if re.search(r"^\s*(-\s+)?uses:", line)]
        self.assertEqual(len(uses), 3)
        for line in uses:
            self.assertRegex(line, r"uses: [\w.-]+/[\w.-]+@[0-9a-f]{40}  # v\d+(\.\d+)*$")

    def test_the_pins_are_the_expected_ones(self) -> None:
        self.assertIn(f"uses: {CHECKOUT}  # v7.0.1", self.text)
        self.assertIn(f"uses: {SCAN}  # v1.2.1", self.text)

    def test_checkout_keeps_no_credentials(self) -> None:
        for job in ("pack", "scan"):
            self.assertEqual(self.steps(job)[0]["with"], {"persist-credentials": False})

    def test_pack_job_commands(self) -> None:
        self.assertEqual([step["run"] for step in self.steps("pack")[1:]], [
            "python3 -m venv .venv",
            ".venv/bin/pip install --require-hashes -r tools/requirements.txt",
            ".venv/bin/python tools/check_pack.py",
            ".venv/bin/python -m unittest discover -s tools/tests",
        ])

    def test_scan_job_action_inputs(self) -> None:
        action = self.steps("scan")[1]
        self.assertEqual(action["uses"], SCAN)
        self.assertEqual(action["with"], {"fail-on": "low", "comment": "false", "telemetry": "false",
                                          "sarif-upload": "${{ github.event_name == 'push' }}"})

    def test_scan_job_commands(self) -> None:
        self.assertEqual([step["run"] for step in self.steps("scan")[2:]], [
            "python3 -m venv .venv",
            ".venv/bin/pip install --require-hashes -r tools/requirements.txt",
            ".venv/bin/spellwarden scan . --format json --output scan.json --fail-on low",
            ".venv/bin/python tools/check_scan.py scan.json",
        ])

    def test_no_command_interpolates_an_expression(self) -> None:
        for job in self.data["jobs"].values():
            for step in job["steps"]:
                self.assertNotIn("${{", step.get("run", ""))


if __name__ == "__main__":
    unittest.main()
