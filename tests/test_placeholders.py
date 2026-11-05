"""A template ships no placeholder that `aidd validate` cannot see.

The shapes of a placeholder live in `aidd.workitems.placeholders`. Every table below is read from the skill's assets, so a
new template is covered with no new code: it must hold a placeholder the shapes match, and one the shapes miss fails here.
"""

from __future__ import annotations

import re
import time
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, make_repo
from test_linked_docs import errors, spec_text, warnings

from aidd.kernel import text as kernel_text
from aidd.workitems import authoring, placeholders, validation

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
TEMPLATES = sorted(ASSETS.glob("*.md"))
# A template that is generated, so it ships no placeholder: the SRS says "none recorded" where the work items hold nothing.
NO_PLACEHOLDER = {"srs.md"}
# Text that looks like a placeholder, as a person would coin one. Each must match a shape in `placeholders`, or a template
# that uses it would pass `aidd validate` unedited.
LOOKS_LIKE_ONE = re.compile(
    r"\b[A-Z]+(?:-[A-Z]+)*-\?+|\?\?|\b[A-Z]\?(?![\w?])|\bYYYY[\w-]*|\bMM-DD\b|\bDD\b|\bN{3,}\b|\bX{3,}\b|\b(?:TBD|FIXME|CHANGEME)\b|\bLorem ipsum"
)


def filled(path: Path) -> str:
    """The template as `aidd new` writes it, every `{{token}}` given a value."""
    text = path.read_text(encoding="utf-8")
    return kernel_text.fill_template(text, **{t: "x" for t in set(re.findall(r"\{\{(\w+)\}\}", text))})


class FoundTests(unittest.TestCase):
    def test_each_shape_is_found(self):
        for text, expected in (
            ("TODO: the design", ["TODO"]),
            ("| 2026-01-01 | YYYY-MM-DD |", ["YYYY-MM-DD"]),
            ("renewal: YYYY-MM", ["YYYY-MM"]),
            ("| SPEC-? | INTENT-? | EC-?? |", ["SPEC-?", "INTENT-?", "EC-??"]),
            ("proves SPEC-?/A?", ["SPEC-?", "A?"]),
            ("covered by (A?)", ["A?"]),
            ("Expires: YYYY-MM-DDT00:00:00Z", ["YYYY-MM-DD"]),
        ):
            self.assertEqual(placeholders.found(text), expected, text)

    def test_text_that_is_not_a_placeholder_is_left_alone(self):
        for text in (
            "Does the test pass? Is it A or B?",
            "Written 2026-11-10 by the SRE.",
            "The format is `YYYY-MM-DD`.",  # a code span names a format
            "<!-- Write dates as YYYY-MM-DD. A TODO here is guidance. -->\n\nDone.",
            '---\ntype: runbook\n# tested_on: "YYYY-MM-DD"   # TODO\nid: x   # YYYY-MM-DD\n---\n\nDone.',
            "SPEC-9/A1 and EC-08 are real ids.",
        ):
            self.assertEqual(placeholders.found(text), [], text)

    def test_a_file_that_is_not_markdown_is_checked_for_the_word_alone(self):
        self.assertEqual(placeholders.found("<p>YYYY-MM-DD</p> <!-- x --> TODO", markdown=False), ["TODO"])
        self.assertEqual(placeholders.found('placeholder="YYYY-MM-DD"', markdown=False), [])


class LinearTimeTests(unittest.TestCase):
    """A document is text anyone can commit, so no pattern backtracks on a long run: each line below is 200 KB."""

    def test_a_long_adversarial_line_is_scanned_in_well_under_a_second(self):
        front = "---\ntype: x\n" + " " * 200_000 + "y\n---\n"
        for name, text in (
            ("hyphenated capitals", "A-" * 100_000),
            ("capitals and a late question mark", "A-" * 100_000 + "?"),
            ("spaces in the front matter", front),
            ("backticks", "`a" * 100_000),
            ("comment openers", "<!--" * 50_000),
        ):
            start = time.monotonic()
            placeholders.found(text)
            self.assertLess(time.monotonic() - start, 0.5, name)


class TemplateTests(unittest.TestCase):
    """Every template in the assets, as `aidd new` writes it."""

    def test_the_assets_are_read(self):
        self.assertGreater(len(TEMPLATES), 30)

    def test_each_template_ships_a_placeholder_that_validate_sees(self):
        for path in TEMPLATES:
            with self.subTest(path.name):
                found = placeholders.found(filled(path))
                self.assertEqual(bool(found), path.name not in NO_PLACEHOLDER, f"{path.name}: {found}")

    def test_each_text_that_looks_like_a_placeholder_matches_a_shape(self):
        """A template holds a shape the check does not know, such as `TBD` or `NNNN`: add the shape to `placeholders.FORMATS`."""
        for path in TEMPLATES:
            seen = LOOKS_LIKE_ONE.findall(_without_code(placeholders.visible(filled(path))))
            with self.subTest(path.name):
                for text in seen:
                    self.assertTrue(placeholders.found(text), f"{path.name}: {text!r} is a placeholder no shape matches")

    def test_a_template_with_every_placeholder_replaced_is_clean(self):
        for path in TEMPLATES:
            text = filled(path)
            for shape in (re.escape(placeholders.WORD), *placeholders.FORMATS):
                text = re.sub(shape, "real", text)
            with self.subTest(path.name):
                self.assertEqual(placeholders.found(text), [], path.name)


def _without_code(text: str) -> str:
    return re.sub(r"`[^`\n]*`", "", text)


class LinkedDocTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def test_every_linked_doc_unedited_is_warned_of_frozen_or_living(self):
        spec = self.root / "specs" / "SPEC-9.md"
        spec.parent.mkdir(exist_ok=True)
        spec.write_text(spec_text(), encoding="utf-8")
        wrote: dict[str, bool] = {}
        for doc_type in authoring.DOC_TEMPLATES:
            if doc_type in authoring.UNLINKED_DOCS:
                continue
            for living in (False, True) if doc_type == "test-plan" else (False,):
                path, _ = authoring.new_doc(self.root, authoring.NewDoc(doc_type=doc_type, topic="x", spec_id="SPEC-9", living=living))
                wrote[path.relative_to(self.root).as_posix()] = doc_type in authoring.LIVING_DOCS or doc_type == "threat-model" or living
        found = validation.validate_file(spec, "specs/SPEC-9.md")
        self.assertEqual(errors(found), [])
        for rel, is_living in wrote.items():
            with self.subTest(rel):
                shown = [w for w in warnings(found) if rel in w and "placeholders" in w]
                self.assertEqual(len(shown), 1, found)
                self.assertIn("living doc" if is_living else "frozen doc", shown[0])

    def test_every_repository_doc_unedited_is_warned_of(self):
        wrote = []
        for doc_type, files in authoring.repo_docs().items():
            try:
                authoring.new_repo_doc(self.root, doc_type=doc_type)
            except FileExistsError:
                continue
            wrote += [rel.replace("{docs}", "docs") for rel, tpl in files if tpl.endswith(".md")]
        self.assertGreater(len(wrote), 8, wrote)
        _, found = validation.check_repo(self.root)
        for rel in wrote:
            with self.subTest(rel):
                self.assertTrue(any(w.startswith(f"warning: {rel}: still holds placeholders") for w in found), found)


if __name__ == "__main__":
    unittest.main()
