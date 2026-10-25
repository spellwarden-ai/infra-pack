"""The documents rule and the full list of required files of check_pack.py."""
from __future__ import annotations

import unittest

import support
from support import TreeTestCase

import check_pack


class RequiredFilesTest(TreeTestCase):
    def test_every_file_of_the_layout_is_required(self) -> None:
        self.build(with_skills=False)
        self.assertClean()
        for rel in check_pack.required_files(False):
            with self.subTest(file=rel):
                self.build(with_skills=False, changes={rel: None})
                self.assertRuleFailed("layout", rel)

    def test_sources_md_is_required_only_with_the_skills(self) -> None:
        self.assertNotIn("SOURCES.md", check_pack.required_files(False))
        self.assertIn("SOURCES.md", check_pack.required_files(True))
        self.build(with_skills=True, changes={"SOURCES.md": None})
        self.assertRuleFailed("layout", "SOURCES.md")

    def test_the_required_list_names_the_files_this_repository_has(self) -> None:
        for rel in check_pack.required_files(False):
            self.assertTrue((support.REPO / rel).is_file(), rel)


class DocsRuleTest(TreeTestCase):
    def test_dashes_and_exclamation_marks_fail_in_each_document(self) -> None:
        for rel in check_pack.DOC_FILES:
            for label, char in (("em dash", "—"), ("en dash", "–"), ("exclamation mark", "!")):
                with self.subTest(file=rel, char=label):
                    self.build(with_skills=False, changes={rel: f"First line.\nA {char} B.\n"})
                    self.assertRuleFailed("docs", rel)
                    self.assertTrue(any(line.startswith(f"{rel}:2:") for line in self.failures()))

    def test_plain_prose_and_hyphens_pass(self) -> None:
        self.build(with_skills=False, changes={"README.md": "A well-known, plain sentence - with a spaced hyphen.\n"})
        self.assertClean()

    def test_other_files_are_not_covered(self) -> None:
        self.build(with_skills=False, changes={"tools/notes.txt": "Wow!\n"})
        self.assertClean()


if __name__ == "__main__":
    unittest.main()
