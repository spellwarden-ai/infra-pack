"""Character, URL, word and masker rules of check_pack.py.
Every skill is a placeholder written to a temporary directory at run time."""
from __future__ import annotations

import unittest

import support
from support import TreeTestCase

FIRST = "plugins/infra-pack/skills/infra-change-safety/SKILL.md"
HEX40 = "6929f1c0a3b4d5e6f708192a3b4c5d6e7f809a1b"
HEX64 = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
FRONT_LINES = 9  # the placeholder frontmatter is 8 lines (its two fences and six fields), then one blank line


class TextRulesTest(TreeTestCase):
    def body(self, text: str) -> None:
        self.build(changes={FIRST: support.skill_text(body=text)})

    def line_of(self, rule: str) -> int:
        for line in self.failures():
            where, _, rest = line.partition(": ")
            if rest.startswith(rule) and where.startswith(FIRST + ":"):
                return int(where.rsplit(":", 1)[1])
        self.fail(f"no failure for {rule!r} in {self.failures()!r}")

    def test_valid_placeholder_is_clean(self) -> None:
        self.body("Check the plan before acting. Always get approval first.\n")
        self.assertClean()

    def test_em_dash_en_dash_and_exclamation_mark(self) -> None:
        for label, char in (("em dash", "—"), ("en dash", "–"), ("exclamation", "!")):
            with self.subTest(char=label):
                self.body(f"First line.\nSecond {char} line.\n")
                self.assertRuleFailed("chars", FIRST)
                self.assertEqual(self.line_of("chars"), FRONT_LINES + 2)

    def test_the_rule_covers_the_frontmatter_too(self) -> None:
        text = support.skill_text(description=support.DESCRIPTION.format(name="x") + " Done!")
        self.build(changes={FIRST: text})
        self.assertRuleFailed("chars", FIRST)

    def test_tab_character(self) -> None:
        self.body("A\tB\n")
        self.assertRuleFailed("chars", FIRST)

    def test_crlf_line_endings(self) -> None:
        self.build(changes={FIRST: support.skill_text().replace("\n", "\r\n")})
        self.assertRuleFailed("chars", FIRST)

    def test_missing_final_newline(self) -> None:
        self.build(changes={FIRST: support.skill_text().rstrip("\n")})
        self.assertRuleFailed("chars", FIRST)

    def test_hidden_characters(self) -> None:
        for label, char in (("zero width space", "​"), ("bidi override", "‮"), ("tag character", "\U000e0041"),
                            ("byte order mark", "﻿")):
            with self.subTest(char=label):
                self.body(f"Plain{char}text.\n")
                self.assertRuleFailed("chars", FIRST)

    def test_ordinary_non_ascii_text_is_allowed(self) -> None:
        self.body("The café example uses an accented letter.\n")
        self.assertClean()

    def test_a_file_that_is_not_utf8_fails_with_its_line(self) -> None:
        self.build()
        (self.root / FIRST).write_bytes(support.skill_text().encode("utf-8") + b"Caf\xe9 in Latin-1.\n")
        self.assertRuleFailed("chars", FIRST)
        self.assertEqual(self.line_of("chars"), FRONT_LINES + 4)  # after the three lines of the placeholder body

    def test_url_in_the_body_and_in_the_frontmatter(self) -> None:
        self.body("See https://example.com/docs for more.\n")
        self.assertRuleFailed("url", FIRST)
        self.body("See HTTP://example.com for more.\n")
        self.assertRuleFailed("url", FIRST)
        self.build(changes={FIRST: support.skill_text(description=support.DESCRIPTION.format(name="x") + " http://a.example")})
        self.assertRuleFailed("url", FIRST)

    def test_each_banned_word_fails_in_any_case(self) -> None:
        words = ("rubric", "grader", "graded", "judge", "benchmark", "eval", "evals", "infra-ops", "pass rate", "test task",
                 "spellwarden")
        for word in words:
            for form in (word, word.upper(), word.capitalize()):
                with self.subTest(word=form):
                    self.body(f"Some text with the {form} inside.\n")
                    self.assertRuleFailed("words", FIRST)

    def test_banned_word_line_number(self) -> None:
        self.body("One.\nTwo.\nThe judge reads this.\n")
        self.assertEqual(self.line_of("words"), FRONT_LINES + 3)

    def test_a_banned_phrase_wrapped_across_a_line_break_fails_on_its_first_line(self) -> None:
        self.body("One.\nPlaceholder that raises the pass\nrate and names a test\n  task.\n")
        found = [item for item in self.failures() if ": words:" in item]
        self.assertEqual(len(found), 2, found)
        self.assertTrue(found[0].startswith(f"{FIRST}:{FRONT_LINES + 2}: words: the body must not contain 'pass rate'"))
        self.assertTrue(found[1].startswith(f"{FIRST}:{FRONT_LINES + 3}: words: the body must not contain 'test task'"))

    def test_banned_words_are_whole_words_only(self) -> None:
        self.body("Evaluate the change. The benchmarks differ. A performance job ran. Judgement stays human.\n")
        self.assertClean()

    def test_frontmatter_author_may_name_the_vendor(self) -> None:
        self.body("Plain body.\n")
        self.assertIn("author: Spellwarden", (self.root / FIRST).read_text())
        self.assertClean()


class MaskerTest(TreeTestCase):
    def body(self, text: str) -> None:
        self.build(changes={FIRST: support.skill_text(body=text)})

    def test_text_the_masker_rewrites_fails_with_its_line(self) -> None:
        samples = {
            "commit pin": f"Steps:\nuses: actions/checkout@{HEX40}\n",
            "permission value": "Steps:\nid-token: write\n",
            "token assignment": "Steps:\nGITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n",
            "image digest": f"Steps:\nimage: app@sha256:{HEX64}\n",
            "managed policy arn": "Steps:\narn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess\n",
            "bearer value": "Steps:\nAuthorization: Bearer abcdefghijklmnop1234567890\n",
        }
        for label, text in samples.items():
            with self.subTest(sample=label):
                self.body(text)
                found = [line for line in self.failures() if ": masker:" in line]
                self.assertEqual(len(found), 1, found)
                self.assertTrue(found[0].startswith(f"{FIRST}:{FRONT_LINES + 2}:"), found)

    def test_legible_wording_passes_unchanged(self) -> None:
        self.body("Pin an action as actions/checkout@<full commit SHA> and an image as app@sha256:<digest>.\n"
                  "Grant the permission `id-token` with the value write only where it is needed.\n")
        self.assertClean()


if __name__ == "__main__":
    unittest.main()
