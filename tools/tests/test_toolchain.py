"""The pinned toolchain: the requirements file, the engine it installs and the
scanner's reading of .spellwarden/config.yml. Nothing here touches the network."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from importlib import metadata
from pathlib import Path

import support

REQUIREMENTS = support.TOOLS / "requirements.txt"
SPELLWARDEN = Path(sys.executable).with_name("spellwarden")


def local_env() -> dict[str, str]:
    """The environment without the variables of a CI job: on a pull or merge request the scanner reads the config of
    the base revision instead of the working tree, and these tests are about a scan of the working tree."""
    return {name: value for name, value in os.environ.items()
            if not name.startswith(("GITHUB_", "GITLAB_", "CI_", "RUNNER_")) and name != "CI"}


def scan(root: Path, output: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(SPELLWARDEN), "scan", ".", "--no-telemetry", "--fail-on", "low", "--format", "json", "--output", str(output)],
        cwd=root, capture_output=True, text=True, timeout=120, check=False, env=local_env(),
    )


class RequirementsTest(unittest.TestCase):
    def entries(self) -> dict[str, list[str]]:
        """{pin: [hashes]} read from the file; every line must belong to a pin."""
        found: dict[str, list[str]] = {}
        current = None
        for raw in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
            line = raw.strip().rstrip("\\").strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("--hash=sha256:"):
                self.assertIsNotNone(current, f"hash before any pin: {raw!r}")
                found[current].append(line.removeprefix("--hash=sha256:"))
            else:
                current = line
                found[current] = []
        return found

    def test_exactly_the_two_pins(self) -> None:
        self.assertEqual(sorted(self.entries()), ["pyyaml==6.0.3", "spellwarden==1.2.1"])

    def test_every_pin_has_sha256_hashes(self) -> None:
        for pin, hashes in self.entries().items():
            with self.subTest(pin=pin):
                self.assertTrue(hashes)
                for value in hashes:
                    self.assertRegex(value, r"^[0-9a-f]{64}$")

    def test_the_engine_wheel_and_sdist_are_listed(self) -> None:
        listed = self.entries()["spellwarden==1.2.1"]
        self.assertIn("1db3c9d549e66985a36a79825997525684c526192a5a7de28fe3bda8594d2663", listed)
        self.assertIn("8e33e731e258d9b6e1003a6a0835f595fc51b4651264353a0864b95c9f847605", listed)

    def test_the_environment_runs_the_pinned_versions(self) -> None:
        self.assertEqual(metadata.version("spellwarden"), "1.2.1")
        self.assertEqual(metadata.version("PyYAML"), "6.0.3")


class EngineTest(unittest.TestCase):
    def test_mask_credentials_is_importable_and_leaves_prose_alone(self) -> None:
        from spellwarden_scan import mask_credentials

        prose = "Pin each action to a full commit SHA and keep the permissions narrow.\n"
        self.assertEqual(mask_credentials(prose), prose)

    def test_mask_credentials_rewrites_a_bearer_value(self) -> None:
        from spellwarden_scan import mask_credentials

        self.assertNotEqual(mask_credentials("Authorization: Bearer abcdefghijklmnop1234567890\n"),
                            "Authorization: Bearer abcdefghijklmnop1234567890\n")


class ScannerConfigTest(unittest.TestCase):
    def test_the_repository_scans_clean_with_its_own_config(self) -> None:
        self.assertTrue(SPELLWARDEN.is_file(), f"run the tests with the virtual environment's python: {SPELLWARDEN}")
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "report.json"
            done = scan(support.REPO, output)
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["findings"], [])

    def test_the_scanner_does_read_the_config(self) -> None:
        """A control: the same scan on a tree with a config the scanner refuses must report it."""
        with tempfile.TemporaryDirectory() as scratch:
            tree = Path(scratch) / "tree"
            (tree / ".spellwarden").mkdir(parents=True)
            (tree / ".spellwarden" / "config.yml").write_text("version: 2\n", encoding="utf-8")
            output = Path(scratch) / "report.json"
            done = scan(tree, output)
            report = json.loads(output.read_text(encoding="utf-8"))
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual([item["code"] for item in report["errors"]], ["settings_invalid"])

    def test_the_repository_config_is_the_expected_mapping(self) -> None:
        text = (support.REPO / ".spellwarden" / "config.yml").read_text(encoding="utf-8")
        self.assertEqual(text, "version: 1\ntelemetry: false\n")
        self.assertIsNone(re.search(r"\t", text))


if __name__ == "__main__":
    unittest.main()
