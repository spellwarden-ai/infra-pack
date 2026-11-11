"""The publish workflow: triggers, the environment and the OIDC permission only on the publish job, pins, and the
package check before publishing. The file is parsed, not run."""
from __future__ import annotations

import json
import re
import unittest

import yaml

import support

WORKFLOW = support.REPO / ".github" / "workflows" / "publish-vscode.yml"
PINS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/setup-node": ("949feb2413d6458794dcd2491c4babbbce0c15c1", "v7.1.0"),
    "actions/upload-artifact": ("cf430e030ddbb5b0abf93d22962f4752f3646cd9", "v7.0.2"),
    "actions/download-artifact": ("9000827ccba6bdab643e8b6fd33ac0654aef8333", "v8.0.2"),
}


class PublishWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = WORKFLOW.read_text(encoding="utf-8")
        self.data = yaml.safe_load(self.text)
        self.jobs = self.data["jobs"]

    def runs(self, job: str) -> list[str]:
        return [step["run"] for step in self.jobs[job]["steps"] if "run" in step]

    def test_runs_on_release_tags_and_by_hand_only(self) -> None:
        triggers = self.data.get("on", self.data.get(True))  # YAML 1.1 reads a bare `on` as true
        self.assertEqual(triggers, {"push": {"tags": ["v*"]}, "workflow_dispatch": None})

    def test_only_the_publish_job_can_ask_for_an_oidc_token(self) -> None:
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertNotIn("permissions", self.jobs["package"])
        self.assertEqual(self.jobs["publish"]["permissions"], {"contents": "read", "id-token": "write"})

    def test_the_publish_job_runs_in_the_environment_the_marketplace_policy_names(self) -> None:
        self.assertEqual(self.jobs["publish"]["environment"], "vscode-marketplace")
        self.assertEqual(self.jobs["publish"]["needs"], "package")
        self.assertNotIn("environment", self.jobs["package"])

    def test_two_jobs_on_ubuntu_24_04_and_no_parallel_publish(self) -> None:
        self.assertEqual(sorted(self.jobs), ["package", "publish"])
        for job in self.jobs.values():
            self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertEqual(self.data["concurrency"], {"group": "publish-vscode", "cancel-in-progress": False})

    def test_every_action_is_pinned_by_full_commit_with_its_version(self) -> None:
        uses = re.findall(r"uses: ([\w./-]+)@([0-9a-f]+)  # (v[\d.]+)", self.text)
        self.assertEqual(len(uses), len(re.findall(r"uses:", self.text)))
        for action, sha, version in uses:
            self.assertEqual(PINS[action], (sha, version), action)

    def test_no_checkout_keeps_its_credentials(self) -> None:
        for job in self.jobs.values():
            for step in job["steps"]:
                if step.get("uses", "").startswith("actions/checkout@"):
                    self.assertIs(step["with"]["persist-credentials"], False)

    def test_the_package_is_checked_against_the_release_tag_before_it_is_kept(self) -> None:
        runs = self.runs("package")
        order = [next(i for i, run in enumerate(runs) if needle in run)
                 for needle in ("tools/check_pack.py", "unittest discover", "vsce package", "tools/check_vsix.py")]
        self.assertEqual(order, sorted(order))
        self.assertIn('--release-ref "refs/tags/v${VERSION}"', next(run for run in runs if "check_vsix" in run))
        self.assertIn("--readme-path vscode/README.md", next(run for run in runs if "vsce package" in run))
        self.assertIs(self.jobs["package"]["steps"][0]["with"]["fetch-depth"], 0)

    def test_vsce_comes_from_the_lockfile_without_install_scripts(self) -> None:
        for job in ("package", "publish"):
            self.assertIn("npm ci --prefix tools/vsce --ignore-scripts --no-audit --no-fund", self.runs(job))
        self.assertNotIn("npx", self.text)
        lock = json.loads((support.REPO / "tools" / "vsce" / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["packages"]["node_modules/@vscode/vsce"]["version"], "4.1.0")
        for name, entry in lock["packages"].items():
            if name:
                self.assertTrue(entry.get("integrity", "").startswith("sha512-"), name)

    def test_it_publishes_the_checked_package_with_oidc(self) -> None:
        publish = self.runs("publish")[-1]
        self.assertIn("vsce publish --oidc", publish)
        self.assertIn('--packagePath "infra-pack-${VERSION}.vsix"', publish)
        self.assertNotIn("VSCE_PAT", self.text)
        self.assertNotIn("secrets.", self.text)
        self.assertNotIn("vsce package", "\n".join(self.runs("publish")))
