#!/usr/bin/env python3
"""Checks a packaged VS Code extension (.vsix) before it is published, offline.

Run from anywhere: `.venv/bin/python tools/check_vsix.py PACKAGE.vsix [--root DIR] [--release-ref REF]`. It prints one
line per failure as `<path>: <rule>` and exits 1 on any failure, 0 otherwise. Standard library only.

The package must hold exactly the manifest, the README the Marketplace shows, the changelog, the licence, the icon and
the five skills, each byte for byte as in the checkout, at the version of plugin.json. With `--release-ref` (the
publish workflow passes refs/tags/v<version>) every packaged skill must also equal its text at that ref, so only
released skill text is ever published."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from pack_common import EXTENSION_FILE, EXTENSION_README, ICON_FILE, PLUGIN_FILE, SKILL_NAMES, SKILLS_DIR, repo_root

PUBLISHER, NAME = "spellwarden", "infra-pack"
VSIX_NS = "{http://schemas.microsoft.com/developer/vsx-schema/2011}"
SKILL_FILES = tuple((SKILLS_DIR / name / "SKILL.md").as_posix() for name in SKILL_NAMES)

# Each packaged file and the checkout file it must equal byte for byte. vsce renames the README, the changelog and
# the licence; everything else keeps its path under extension/.
PACKAGED = {
    "extension/package.json": EXTENSION_FILE.as_posix(),
    "extension/readme.md": EXTENSION_README.as_posix(),
    "extension/changelog.md": "CHANGELOG.md",
    "extension/LICENSE.txt": "LICENSE",
    f"extension/{ICON_FILE.as_posix()}": ICON_FILE.as_posix(),
    **{f"extension/{rel}": rel for rel in SKILL_FILES},
}
# vsce's own files, which have no counterpart in the checkout.
GENERATED = ("extension.vsixmanifest", "[Content_Types].xml")


def _plugin_version(root: Path) -> str | None:
    try:
        version = json.loads((root / PLUGIN_FILE).read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) else None


def _show(root: Path, ref: str, rel: str) -> bytes | None:
    """The bytes of `rel` at `ref` in the repository at `root`, or None when the ref or the path does not exist."""
    result = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{rel}"], capture_output=True, check=False)
    return result.stdout if result.returncode == 0 else None


def _check_manifest(text: bytes, version: str | None) -> list[str]:
    failures: list[str] = []
    try:
        metadata = ET.fromstring(text).find(f"{VSIX_NS}Metadata")
    except ET.ParseError:
        return ["extension.vsixmanifest: not valid XML"]
    identity = metadata.find(f"{VSIX_NS}Identity") if metadata is not None else None
    if identity is None:
        return ["extension.vsixmanifest: no Identity element"]
    found = (identity.get("Publisher"), identity.get("Id"), identity.get("Version"))
    if found != (PUBLISHER, NAME, version):
        failures.append(f"extension.vsixmanifest: identity {found} is not {(PUBLISHER, NAME, version)}")
    for prop in metadata.iter(f"{VSIX_NS}Property"):
        if prop.get("Id") == "Microsoft.VisualStudio.Code.EnabledApiProposals" and prop.get("Value"):
            failures.append(f"extension.vsixmanifest: uses proposed APIs ({prop.get('Value')}), which the Marketplace refuses")
    return failures


def check_vsix(vsix: Path, root: Path, release_ref: str | None = None) -> list[str]:
    """Every failure, in a stable order."""
    try:
        archive = zipfile.ZipFile(vsix)
    except (OSError, zipfile.BadZipFile) as error:
        return [f"{vsix.name}: not a readable package ({error})"]
    failures: list[str] = []
    with archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        expected = {*PACKAGED, *GENERATED}
        failures.extend(f"{name}: unexpected file in the package" for name in sorted(set(names) - expected))
        failures.extend(f"{name}: missing from the package" for name in sorted(expected - set(names)))
        failures.extend(f"{name}: in the package more than once" for name in sorted({n for n in names if names.count(n) > 1}))
        present = set(names)
        for inner, rel in PACKAGED.items():
            if inner not in present:
                continue
            data = archive.read(inner)
            try:
                if data != (root / rel).read_bytes():
                    failures.append(f"{inner}: differs from {rel} in the checkout")
            except OSError:
                failures.append(f"{inner}: {rel} is missing from the checkout")
            if release_ref is not None and rel in SKILL_FILES and data != _show(root, release_ref, rel):
                failures.append(f"{inner}: differs from {rel} at {release_ref}, so it is not released text")
        version = _plugin_version(root)
        if version is None:
            failures.append(f"{PLUGIN_FILE.as_posix()}: no version to compare the package with")
        if "extension/package.json" in present:
            try:
                packaged_version = json.loads(archive.read("extension/package.json")).get("version")
            except (ValueError, AttributeError):
                packaged_version = None
            if packaged_version != version:
                failures.append(f"extension/package.json: version {packaged_version} is not plugin.json's {version}")
        if "extension.vsixmanifest" in present:
            failures.extend(_check_manifest(archive.read("extension.vsixmanifest"), version))
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a packaged VS Code extension before it is published.")
    parser.add_argument("vsix", type=Path, help="the .vsix file vsce wrote")
    parser.add_argument("--root", type=Path, default=repo_root(), help="the repository root (default: this checkout)")
    parser.add_argument("--release-ref", help="a git ref whose skill text every packaged skill must equal")
    args = parser.parse_args(argv)
    failures = check_vsix(args.vsix, args.root, args.release_ref)
    for failure in failures:
        print(failure)
    if failures:
        print(f"check_vsix: {len(failures)} failure(s)", file=sys.stderr)
        return 1
    print("check_vsix: ok", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
