"""One owner for what aidd says about itself: `schemas/product.json` holds the description and the keywords, and
`aidd gen-docs` writes them into every place that states one.

Invariant: for every place that states the description or the keywords, its text equals the owner's, and a stale copy
is rewritten, never kept.
"""

import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import __doc__ as package_doc
from aidd.cli import parser
from aidd.docsgen import blocks, generate, product
from aidd.kernel import resources

GITHUB_ABOUT_LIMIT = 350  # GitHub's cap on a repository's description


def read(*path: str) -> str:
    return ROOT.joinpath(*path).read_text(encoding="utf-8")


def block_text(page: str, name: str) -> str:
    """The text inside the page's one `<!-- aidd:gen NAME -->...<!-- aidd:end -->` block."""
    found = [m.group(3) for m in blocks.INLINE.finditer(read(page)) if m.group(2) == name]
    assert len(found) == 1, f"{page} holds {len(found)} blocks named {name}"
    return found[0]


class OwnerTests(unittest.TestCase):
    def test_the_owner_holds_both_forms_and_the_keywords(self):
        owner = resources.load_json("product.json")
        self.assertEqual(set(owner), {"description", "long", "short", "keywords"})
        self.assertLess(len(owner["short"]), len(owner["long"]))
        self.assertLessEqual(len(owner["long"]), GITHUB_ABOUT_LIMIT)
        for form in product.FORMS:
            # A form sits on one line of a Markdown inline block, which stops at `<`.
            self.assertNotRegex(owner[form], r"[\n<]", form)
        self.assertEqual(len(set(owner["keywords"])), len(owner["keywords"]))
        self.assertTrue(all(k == k.lower() and " " not in k for k in owner["keywords"]), "a keyword is a lower-case topic")

    def test_an_unknown_form_is_an_error(self):
        for form in ("", "medium", "LONG"):
            with self.subTest(form=form), self.assertRaises(KeyError):
                product.text(form)


class EveryPlaceTests(unittest.TestCase):
    """The places that state the description, each against the owner."""

    def setUp(self):
        self.owner = resources.load_json("product.json")

    def test_every_place_that_states_the_long_form_holds_it(self):
        long = self.owner["long"]
        places = {
            "pyproject.toml": tomllib.loads(read("pyproject.toml"))["project"]["description"],
            ".claude-plugin/plugin.json": json.loads(read(".claude-plugin", "plugin.json"))["description"],
            ".claude-plugin/marketplace.json": json.loads(read(".claude-plugin", "marketplace.json"))["metadata"]["description"],
            "the package docstring": (package_doc or "").split("\n")[0],
            "llms.txt": block_text("llms.txt", "product:long"),
        }
        for place, text in places.items():
            with self.subTest(place=place):
                self.assertEqual(text, long)

    def test_every_place_that_states_the_short_form_holds_it(self):
        short = self.owner["short"]
        places = {"aidd --help": parser.build_parser().description, "README.md": block_text("README.md", "product:short")}
        for place, text in places.items():
            with self.subTest(place=place):
                self.assertEqual(text, short)

    def test_the_keywords_match_in_both_manifests(self):
        project = tomllib.loads(read("pyproject.toml"))["project"]["keywords"]
        plugin = json.loads(read(".claude-plugin", "plugin.json"))["keywords"]
        self.assertEqual(project, self.owner["keywords"])
        self.assertEqual(plugin, self.owner["keywords"])


class SyncTests(unittest.TestCase):
    """`gen-docs` rewrites a stale copy, and leaves a current one as it is."""

    STALE = "an old description"

    def tree(self, root: Path, *, description: str) -> None:
        (root / "src" / "aidd").mkdir(parents=True)
        (root / ".claude-plugin").mkdir()
        (root / "pyproject.toml").write_text(f'[project]\nname = "x"\ndescription = "{description}"\nkeywords = ["old"]\nversion = "1"\n', encoding="utf-8")
        (root / "src" / "aidd" / "__init__.py").write_text(f'"""{description}\n\nMore text.\n"""\n', encoding="utf-8")
        (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "x", "description": description, "keywords": ["old"]}), encoding="utf-8")
        (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"name": "x", "metadata": {"description": description}}), encoding="utf-8")

    def sync(self, root: Path) -> dict[str, str]:
        written: dict[str, str] = {}

        def update(path: Path, new: str) -> None:
            written[path.relative_to(root).as_posix()] = new

        product.sync(root, update)
        return written

    def test_a_stale_copy_is_rewritten_and_the_rest_of_the_file_is_kept(self):
        long = product.text("long")
        keywords = resources.load_json("product.json")["keywords"]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.tree(root, description=self.STALE)
            written = self.sync(root)
        self.assertEqual(set(written), {"pyproject.toml", "src/aidd/__init__.py", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"})
        project = tomllib.loads(written["pyproject.toml"])["project"]
        self.assertEqual((project["description"], project["keywords"], project["version"]), (long, keywords, "1"))
        self.assertEqual(written["src/aidd/__init__.py"], f'"""{long}\n\nMore text.\n"""\n')
        plugin = json.loads(written[".claude-plugin/plugin.json"])
        self.assertEqual((plugin["description"], plugin["keywords"], plugin["name"]), (long, keywords, "x"))
        self.assertEqual(json.loads(written[".claude-plugin/marketplace.json"])["metadata"]["description"], long)

    def test_gen_docs_checks_the_copies_against_the_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.tree(root, description=self.STALE)
            stale = {p.relative_to(root).as_posix() for p in generate.gen_docs(root, check=True)}
            self.assertLessEqual({"pyproject.toml", "src/aidd/__init__.py", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"}, stale)
            self.assertIn(self.STALE, (root / "pyproject.toml").read_text(encoding="utf-8"), "a check writes nothing")

    def test_a_current_copy_is_written_back_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.tree(root, description=self.STALE)
            for path, text in self.sync(root).items():
                (root / path).write_text(text, encoding="utf-8")
            again = self.sync(root)
            for path, text in again.items():
                self.assertEqual((root / path).read_text(encoding="utf-8"), text, path)

    def test_a_tree_with_none_of_the_files_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.sync(Path(tmp)), {})

    def test_a_markdown_block_is_filled_from_the_owner(self):
        for form in product.FORMS:
            with self.subTest(form=form):
                page = f"Lead: <!-- aidd:gen product:{form} -->an old line<!-- aidd:end --> end.\n"
                self.assertEqual(generate.regenerate(page), f"Lead: <!-- aidd:gen product:{form} -->{product.text(form)}<!-- aidd:end --> end.\n")


if __name__ == "__main__":
    unittest.main()
