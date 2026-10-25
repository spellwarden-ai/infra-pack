"""Layout, manifests and configuration rules of check_pack.py."""
from __future__ import annotations

import contextlib
import io
import json
import unittest

import support
from support import TreeTestCase

import check_pack

MARKET = ".claude-plugin/marketplace.json"
PLUGIN = "plugins/infra-pack/.claude-plugin/plugin.json"
SKILLS = "plugins/infra-pack/skills"


class RepositoryTest(unittest.TestCase):
    def test_this_repository_passes(self) -> None:
        self.assertEqual([str(item) for item in check_pack.check_repo(support.REPO, {})], [])


class LayoutTest(TreeTestCase):
    def test_skeleton_tree_is_clean(self) -> None:
        self.build(with_skills=False)
        self.assertClean()

    def test_full_tree_is_clean(self) -> None:
        self.build(with_skills=True)
        self.assertClean()

    def test_missing_required_file(self) -> None:
        self.build(with_skills=False, changes={"LICENSE": None})
        self.assertRuleFailed("layout", "LICENSE")

    def test_extra_file_under_plugins(self) -> None:
        self.build(with_skills=False, changes={"plugins/infra-pack/extra.md": "x\n"})
        self.assertRuleFailed("layout", "plugins/infra-pack/extra.md")

    def test_extra_file_inside_a_skill_directory(self) -> None:
        self.build(changes={f"{SKILLS}/infra-change-safety/notes.md": "x\n"})
        self.assertRuleFailed("layout", f"{SKILLS}/infra-change-safety/notes.md")

    def test_file_in_a_directory_the_scanner_skips_is_still_unexpected(self) -> None:
        # F1: node_modules, venv, .venv and __pycache__ are invisible to the scanner, never to the layout rule.
        for rel in (
            "plugins/infra-pack/node_modules/x.js",
            f"{SKILLS}/infra-change-safety/venv/y",
            "plugins/infra-pack/.venv/z",
            "plugins/infra-pack/__pycache__/w.pyc",
        ):
            with self.subTest(rel=rel):
                self.build(changes={rel: "x\n"})
                self.assertRuleFailed("layout: unexpected file under plugins/", rel)

    def test_symlinked_directory_under_plugins_is_unexpected(self) -> None:
        self.build(with_skills=False)
        link = self.root / "plugins/infra-pack/linked"
        link.symlink_to(self.root / "tools", target_is_directory=True)
        self.assertRuleFailed("layout: unexpected file under plugins/", "plugins/infra-pack/linked")

    def test_unknown_skill_directory(self) -> None:
        self.build(changes={f"{SKILLS}/other-skill/SKILL.md": support.skill_text("other-skill")})
        self.assertRuleFailed("layout", f"{SKILLS}/other-skill/SKILL.md")

    def test_skills_directory_present_but_one_skill_missing(self) -> None:
        self.build(changes={f"{SKILLS}/ci-pipeline-repair/SKILL.md": None})
        self.assertRuleFailed("layout", f"{SKILLS}/ci-pipeline-repair/SKILL.md")

    def test_file_named_skill_md_outside_the_skills(self) -> None:
        self.build(with_skills=False, changes={"tools/tests/fixture/SKILL.md": "x\n"})
        self.assertRuleFailed("layout", "tools/tests/fixture/SKILL.md")

    def test_lowercase_skill_md_is_caught_too(self) -> None:
        self.build(with_skills=False, changes={"docs/skill.md": "x\n"})
        self.assertRuleFailed("layout", "docs/skill.md")


class ManifestTest(TreeTestCase):
    def test_wrong_marketplace_name(self) -> None:
        data = support.marketplace()
        data["name"] = "other"
        self.build(with_skills=False, changes={MARKET: support.dump(data)})
        self.assertRuleFailed("manifest", MARKET)

    def test_extra_marketplace_key_is_named(self) -> None:
        data = support.marketplace()
        data["plugins"][0]["version"] = "0.9.0"
        self.build(with_skills=False, changes={MARKET: support.dump(data)})
        self.assertTrue(any("plugins" in line and "differs" in line for line in self.failures()))

    def test_changed_plugin_description(self) -> None:
        data = support.plugin()
        data["description"] = "Something else."
        self.build(with_skills=False, changes={PLUGIN: support.dump(data)})
        self.assertRuleFailed("manifest", PLUGIN)

    def test_plugin_urls_are_accepted(self) -> None:
        self.build(with_skills=False)
        self.assertIn("https://github.com/spellwarden-ai/infra-pack", (self.root / PLUGIN).read_text())
        self.assertClean()

    def test_version_must_be_x_y_z(self) -> None:
        for bad in ("1.0", "v0.9.0", "0.9.0-rc1"):
            with self.subTest(version=bad):
                self.build(with_skills=False, changes={PLUGIN: support.dump(support.plugin(bad))})
                self.assertRuleFailed("manifest", PLUGIN)

    def test_version_may_change_without_failing_the_manifest_rule(self) -> None:
        self.build(with_skills=False, changes={PLUGIN: support.dump(support.plugin("1.2.3"))})
        self.assertClean()

    def test_invalid_json(self) -> None:
        self.build(with_skills=False, changes={MARKET: '{"name": \n'})
        self.assertRuleFailed("manifest", MARKET)

    def test_missing_final_newline(self) -> None:
        self.build(with_skills=False, changes={PLUGIN: support.dump(support.plugin()).rstrip("\n")})
        self.assertRuleFailed("manifest", PLUGIN)

    def test_odd_indentation(self) -> None:
        self.build(with_skills=False, changes={PLUGIN: json.dumps(support.plugin(), indent=3) + "\n"})
        self.assertRuleFailed("manifest", PLUGIN)

    def test_four_space_indentation(self) -> None:
        self.build(with_skills=False, changes={MARKET: json.dumps(support.marketplace(), indent=4) + "\n"})
        self.assertRuleFailed("manifest: indent two spaces per level", MARKET)

    def test_objects_kept_on_one_line_as_the_spec_writes_them(self) -> None:
        real = (support.REPO / MARKET).read_text(encoding="utf-8")
        self.assertIn('  "owner": {"name": "Spellwarden"', real)  # the repository's manifest keeps owner on one line
        self.build(with_skills=False, changes={MARKET: real})
        self.assertClean()

    def test_a_difference_names_the_line_of_the_nested_key(self) -> None:
        data = support.marketplace()
        data["owner"]["name"] = "Someone else"
        text = support.dump(data)
        self.build(with_skills=False, changes={MARKET: text})
        line = text.split("\n").index('    "name": "Someone else",') + 1
        self.assertIn(f"{MARKET}:{line}: manifest: owner.name differs from the expected manifest", self.failures())

    def test_tab_indentation(self) -> None:
        self.build(with_skills=False, changes={PLUGIN: json.dumps(support.plugin(), indent="\t") + "\n"})
        self.assertRuleFailed("manifest", PLUGIN)

    def test_document_must_be_an_object(self) -> None:
        self.build(with_skills=False, changes={PLUGIN: "[]\n"})
        self.assertRuleFailed("manifest", PLUGIN)


class ConfigTest(TreeTestCase):
    CONFIG = ".spellwarden/config.yml"

    def test_telemetry_must_be_off(self) -> None:
        self.build(with_skills=False, changes={self.CONFIG: "version: 1\ntelemetry: true\n"})
        self.assertRuleFailed("config", self.CONFIG)

    def test_version_is_required(self) -> None:
        self.build(with_skills=False, changes={self.CONFIG: "telemetry: false\n"})
        self.assertRuleFailed("config", self.CONFIG)

    def test_not_yaml(self) -> None:
        self.build(with_skills=False, changes={self.CONFIG: "version: [1\n"})
        self.assertRuleFailed("config", self.CONFIG)


class MainTest(TreeTestCase):
    def run_main(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = check_pack.main(["--root", str(self.root)], {})
        return code, out.getvalue()

    def test_exit_zero_and_silent_stdout_when_clean(self) -> None:
        self.build(with_skills=False)
        self.assertEqual(self.run_main(), (0, ""))

    def test_exit_one_and_one_line_per_failure(self) -> None:
        self.build(with_skills=False, changes={"LICENSE": None})
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), ["LICENSE:1: layout: required file is missing"])


if __name__ == "__main__":
    unittest.main()
