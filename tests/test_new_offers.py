"""`aidd new` offers only a type it can start: each type it lists either writes a file or refuses in one plain line that names the
next step, and a type with no template to write is not listed."""

import contextlib
import io
import re
import unittest

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import RepoTemplateCase, make_repo, run_cli

from aidd import config
from aidd.cli import grammar, parser

NAMES_A_STEP = re.compile(r"`aidd |--[a-z]")
A_BARE_KEY = re.compile(r"aidd: '[^']*'")


class TheTypesItOffers(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "solo", branch=None)

    def test_each_offered_type_writes_a_file_or_refuses_with_its_next_step(self):
        for name in grammar.new_types():
            with self.subTest(type=name), contextlib.chdir(self.root):
                code, out = run_cli("new", name)
                lines = out.strip().splitlines()
                if code == 0:
                    self.assertTrue((self.root / lines[0]).is_file(), f"{name} says it wrote {lines[0]!r}")
                else:
                    self.assertEqual(code, 2)
                    self.assertFalse(A_BARE_KEY.fullmatch(lines[0]), f"{name}: {lines[0]}")
                    self.assertTrue(NAMES_A_STEP.search(lines[0]), f"{name} names no next step: {lines[0]}")

    def test_a_typed_document_with_no_template_is_offered_nowhere(self):
        rows = config.item_type_rows()
        unoffered = {t for t, row in rows.items() if row["form"] == "typed_document" and "templates" not in row and "files" not in row}
        with contextlib.redirect_stdout(io.StringIO()) as printed, self.assertRaises(SystemExit):
            parser.build_parser().parse_args(["new", "--list"])
        listing = printed.getvalue()
        _, help_text = run_cli("help", "new")
        for name in unoffered:  # every typed document of the registry has a template today, so the rule is also tried on rows of its own
            with self.subTest(type=name):
                self.assertNotIn(name, grammar.new_types())
                self.assertFalse(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", listing), listing)
                self.assertFalse(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", help_text))

    def test_the_rule_holds_for_rows_of_its_own(self):
        rows = {
            "spec": {"group": "work_items", "form": "work_item", "templates": {"default": "spec.md"}},
            "draft": {"group": "product_scope", "form": "typed_document"},
            "guide": {"group": "repository", "form": "document"},
        }
        groups = {"work_items": "work items", "product_scope": "the product scope", "repository": "the repository's one of each"}
        self.assertEqual(grammar.new_types(rows), ["spec", "guide"], "a typed document with no template is not offered")
        self.assertEqual([label for label, _ in grammar.new_type_groups(rows, groups)], ["work items", "the repository's one of each"])

    def test_the_article_before_a_type_in_a_refusal_agrees_with_it(self):
        with contextlib.chdir(self.root):
            for name, article in (("adr", "an adr"), ("api", "an api"), ("tech-spec", "a tech-spec")):
                with self.subTest(type=name):
                    code, out = run_cli("new", name)
                    self.assertEqual(code, 2)
                    self.assertIn(f"an id is required for {article}:", out)
            code, out = run_cli("new", "intent")
            self.assertIn("--title is required for an intent,", out)


if __name__ == "__main__":
    unittest.main()
