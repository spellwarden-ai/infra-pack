"""Frontmatter, size, version and tag rules of check_pack.py.
The skill trees are written to a temporary directory from placeholders at run time."""
from __future__ import annotations

import contextlib
import io
import shutil
import unittest

import support
from support import TreeTestCase

import check_pack

SKILLS = "plugins/infra-pack/skills"
PLUGIN = "plugins/infra-pack/.claude-plugin/plugin.json"
FIRST = f"{SKILLS}/infra-change-safety/SKILL.md"


def front(*, name="infra-change-safety", description=None, license="Apache-2.0", version='"0.9.0"',
          author="Spellwarden", order=("name", "description", "license", "metadata"), extra="", meta_extra="",
          drop=()) -> str:
    text = description if description is not None else support.DESCRIPTION.format(name=name)
    blocks = {
        "name": f"name: {name}\n",
        "description": f"description: {text}\n",
        "license": f"license: {license}\n",
        "metadata": f"metadata:\n  version: {version}\n  author: {author}\n{meta_extra}",
    }
    body = "".join(blocks[key] for key in order if key not in drop)
    return f"---\n{body}{extra}---\n"


def sized(name: str, size: int) -> str:
    """A valid skill of exactly `size` bytes."""
    base = len(support.skill_text(name, body="\n").encode("utf-8"))
    return support.skill_text(name, body="x" * (size - base) + "\n")


class FrontmatterTest(TreeTestCase):
    def broken(self, front_text: str) -> None:
        self.build(changes={FIRST: support.skill_text(front=front_text)})

    def test_valid_tree_is_clean(self) -> None:
        self.build()
        self.assertClean()

    def test_skeleton_state_skips_the_skill_rules(self) -> None:
        self.build(with_skills=False)
        self.assertClean()

    def test_no_frontmatter(self) -> None:
        self.build(changes={FIRST: "# Just a heading\n"})
        self.assertRuleFailed("frontmatter", FIRST)

    def test_unclosed_frontmatter(self) -> None:
        self.build(changes={FIRST: "---\nname: infra-change-safety\n"})
        self.assertRuleFailed("frontmatter", FIRST)

    def test_yaml_the_loader_rejects(self) -> None:
        self.build(changes={FIRST: "---\nname: [unclosed\n---\n"})
        self.assertRuleFailed("frontmatter", FIRST)

    def test_frontmatter_that_is_not_a_mapping(self) -> None:
        self.build(changes={FIRST: "---\n- a\n- b\n---\n"})
        self.assertRuleFailed("frontmatter", FIRST)

    def test_wrong_key_order(self) -> None:
        self.broken(front(order=("name", "license", "description", "metadata")))
        self.assertRuleFailed("frontmatter: the keys", FIRST)

    def test_extra_key(self) -> None:
        self.broken(front(extra="allowed-tools: Read\n"))
        self.assertRuleFailed("frontmatter: the keys", FIRST)

    def test_missing_key(self) -> None:
        self.broken(front(drop=("license",)))
        self.assertRuleFailed("frontmatter: the keys", FIRST)

    def test_name_must_equal_the_directory(self) -> None:
        self.broken(front(name="terraform-plan-review"))
        self.assertRuleFailed("frontmatter: name", FIRST)

    def test_description_length_bounds(self) -> None:
        for size, ok in ((199, False), (200, True), (1024, True), (1025, False)):
            with self.subTest(size=size):
                self.broken(front(description="d" * size))
                if ok:
                    self.assertClean()
                else:
                    self.assertRuleFailed("frontmatter: description", FIRST)

    def test_license(self) -> None:
        self.broken(front(license="MIT"))
        self.assertRuleFailed("frontmatter: license", FIRST)

    def test_metadata_must_hold_exactly_version_and_author(self) -> None:
        self.broken(front(meta_extra="  tags: x\n"))
        self.assertRuleFailed("frontmatter: metadata", FIRST)

    def test_author(self) -> None:
        self.broken(front(author="Someone"))
        self.assertRuleFailed("frontmatter: metadata.author", FIRST)

    def test_unquoted_version_that_loads_as_a_number(self) -> None:
        self.broken(front(version="1.0"))
        self.assertRuleFailed("frontmatter: metadata.version", FIRST)

    def test_version_differs_from_plugin_json(self) -> None:
        self.build(changes={FIRST: support.skill_text(version="0.9.1")})
        self.assertRuleFailed("version", FIRST)

    def test_version_follows_plugin_json(self) -> None:
        files = {PLUGIN: support.dump(support.plugin("1.0.0"))}
        for name in support.SKILL_NAMES:
            files[f"{SKILLS}/{name}/SKILL.md"] = support.skill_text(name, version="1.0.0")
        self.build(changes=files)
        self.assertClean()


class SizeTest(TreeTestCase):
    def test_one_skill_at_the_byte_limit_passes_and_one_byte_over_fails(self) -> None:
        self.build(changes={FIRST: sized("infra-change-safety", 10_000)})
        self.assertClean()
        self.build(changes={FIRST: sized("infra-change-safety", 10_001)})
        self.assertRuleFailed("size", FIRST)

    def test_line_limit(self) -> None:
        head = len(support.skill_text(body="").splitlines())
        self.build(changes={FIRST: support.skill_text(body="a\n" * (250 - head))})
        self.assertClean()
        self.build(changes={FIRST: support.skill_text(body="a\n" * (251 - head))})
        self.assertRuleFailed("size", FIRST)

    def test_pack_total(self) -> None:
        at_limit = {f"{SKILLS}/{name}/SKILL.md": sized(name, 9_000) for name in support.SKILL_NAMES}
        self.build(changes=at_limit)
        self.assertClean()
        over = dict(at_limit)
        over[FIRST] = sized("infra-change-safety", 9_001)
        self.build(changes=over)
        self.assertRuleFailed("size: the skills total", SKILLS)


class TagTest(TreeTestCase):
    def test_tag_equal_to_the_version(self) -> None:
        self.build()
        self.assertClean({"GITHUB_REF": "refs/tags/v0.9.0"})

    def test_tag_that_differs(self) -> None:
        self.build(with_skills=False)
        self.assertRuleFailed("tag", PLUGIN, {"GITHUB_REF": "refs/tags/v0.9.1"})

    def test_a_tag_failure_names_the_version_line_of_plugin_json(self) -> None:
        self.build()
        line = next(number for number, text in enumerate(support.dump(support.plugin()).split("\n"), 1) if '"version"' in text)
        self.assertGreater(line, 1)
        self.assertIn(f"{PLUGIN}:{line}: tag: v0.9.1 differs from the plugin version 0.9.0",
                      self.failures({"GITHUB_REF": "refs/tags/v0.9.1"}))

    def test_a_release_tag_that_is_not_x_y_z_fails(self) -> None:
        self.build()
        for ref in ("refs/tags/v0.9", "refs/tags/v0.9.0-rc1", "refs/tags/vnext"):
            with self.subTest(ref=ref):
                self.assertRuleFailed("tag", PLUGIN, {"GITHUB_REF": ref})

    def test_other_refs_are_ignored(self) -> None:
        self.build(with_skills=False)
        for ref in ("refs/heads/main", "refs/tags/next", "refs/pull/3/merge", ""):
            with self.subTest(ref=ref):
                self.assertClean({"GITHUB_REF": ref})

    def test_skeleton_state_fails_on_a_release_tag(self) -> None:
        self.build(with_skills=False)
        self.assertRuleFailed("tag", PLUGIN, {"GITHUB_REF": "refs/tags/v0.9.0"})

    def test_partial_skill_tree_still_fails(self) -> None:
        self.build()
        shutil.rmtree(self.root / SKILLS / "ci-pipeline-repair")
        self.assertTrue(self.failures())


class NoticeTest(TreeTestCase):
    def test_skeleton_state_prints_a_notice(self) -> None:
        self.build(with_skills=False)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = check_pack.main(["--root", str(self.root)], env={})
        self.assertEqual(code, 0)
        self.assertIn("notice", err.getvalue())


if __name__ == "__main__":
    unittest.main()
