"""check_vsix.py: the file list of a packaged extension, its bytes against the checkout, its version and identity,
and the release-ref guard. Each package is written as a zip at run time; no .vsix is kept in the repository."""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import support
from support import TreeTestCase

import check_vsix

MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}" />
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.EnabledApiProposals" Value="{proposals}" />
    </Properties>
  </Metadata>
</PackageManifest>
"""
FIRST = "extension/plugins/infra-pack/skills/infra-change-safety/SKILL.md"


class CheckVsixTest(TreeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.build()
        icon = "plugins/infra-pack/.claude-plugin/icon.png"  # optional for check_pack, packaged by vsce
        (self.root / icon).write_bytes((support.REPO / icon).read_bytes())
        self.vsix = self.root / "out.vsix"

    def package(self, *, drop: str | None = None, extra: dict[str, bytes] | None = None,
                replace: dict[str, bytes] | None = None, **identity: str) -> Path:
        """Write a package of the tree at self.root, as vsce would, with the given changes."""
        entries = {inner: (self.root / rel).read_bytes() for inner, rel in check_vsix.PACKAGED.items()}
        fields = {"name": "infra-pack", "version": "0.9.0", "publisher": "spellwarden", "proposals": "", **identity}
        entries["extension.vsixmanifest"] = MANIFEST.format(**fields).encode()
        entries["[Content_Types].xml"] = b"<Types />"
        entries.update(replace or {})
        entries.update(extra or {})
        entries.pop(drop, None)
        with zipfile.ZipFile(self.vsix, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return self.vsix

    def check(self, release_ref: str | None = None) -> list[str]:
        return check_vsix.check_vsix(self.vsix, self.root, release_ref)

    def test_a_package_of_the_checkout_is_clean(self) -> None:
        self.package()
        self.assertEqual(self.check(), [])

    def test_an_extra_file_is_named(self) -> None:
        self.package(extra={"extension/node_modules/x/index.js": b"x"})
        self.assertEqual(self.check(), ["extension/node_modules/x/index.js: unexpected file in the package"])

    def test_a_missing_skill_is_named(self) -> None:
        self.package(drop=FIRST)
        self.assertEqual(self.check(), [f"{FIRST}: missing from the package"])

    def test_a_skill_that_differs_from_the_checkout(self) -> None:
        self.package(replace={FIRST: b"changed\n"})
        self.assertTrue(any(line.startswith(f"{FIRST}: differs from") for line in self.check()))

    def test_a_readme_that_is_not_the_marketplace_readme(self) -> None:
        self.package(replace={"extension/readme.md": (self.root / "README.md").read_bytes() + b"x"})
        self.assertTrue(any(line.startswith("extension/readme.md: differs") for line in self.check()))

    def test_identity_and_version_must_match(self) -> None:
        for identity in ({"publisher": "other"}, {"name": "other"}, {"version": "0.9.1"}):
            with self.subTest(identity=identity):
                self.package(**identity)
                self.assertTrue(any(line.startswith("extension.vsixmanifest: identity") for line in self.check()))

    def test_proposed_apis_are_refused(self) -> None:
        self.package(proposals="chatParticipantPrivate")
        self.assertTrue(any("proposed APIs" in line for line in self.check()))

    def test_a_file_that_is_not_a_zip(self) -> None:
        self.vsix.write_bytes(b"not a zip")
        self.assertEqual(len(self.check()), 1)
        self.assertIn("not a readable package", self.check()[0])

    def test_release_ref_accepts_released_text_and_refuses_other_text(self) -> None:
        git = ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgSign=false"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "release"], check=True)
        subprocess.run([*git, "tag", "v0.9.0"], check=True)
        self.package()
        self.assertEqual(self.check("refs/tags/v0.9.0"), [])
        skill = self.root / "plugins/infra-pack/skills/infra-change-safety/SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8") + "\nUnreleased line.\n", encoding="utf-8")
        self.package()
        self.assertEqual(self.check("refs/tags/v0.9.0"),
                         [f"{FIRST}: differs from plugins/infra-pack/skills/infra-change-safety/SKILL.md at refs/tags/v0.9.0, "
                          "so it is not released text"])
        self.assertEqual(len(self.check("refs/tags/v9.9.9")), 5)

    def test_the_expected_files_are_the_vscodeignore_allow_list(self) -> None:
        allowed = [line[1:] for line in (support.REPO / ".vscodeignore").read_text(encoding="utf-8").splitlines()
                   if line.startswith("!")]
        self.assertEqual(allowed, ["package.json", "LICENSE", "CHANGELOG.md", "plugins/infra-pack/.claude-plugin/icon.png",
                                   "plugins/infra-pack/skills/*/SKILL.md"])
        self.assertIn("**", (support.REPO / ".vscodeignore").read_text(encoding="utf-8").splitlines())
