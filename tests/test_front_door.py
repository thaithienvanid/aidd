"""The front door claims no more than the code delivers (the 2026-11 public-face audit, a14).

Invariant: no page a stranger reads first states a claim the audit showed the code does not hold, and the README shows
what aidd does before it asks for an install, and says what aidd does not do.
"""

import re
import unittest
from xml.etree import ElementTree

from helpers import ROOT, anchors, says

FRONT_DOOR = (
    "README.md",
    "llms.txt",
    "llms-install.md",
    "docs/GUIDE.md",
    "SECURITY.md",
    "pyproject.toml",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
)

# Each phrase is a claim a finding contradicted. The honest wording sits in the page, so a phrase that returns is a
# page claiming more than the code does.
OVERCLAIMS = {
    "proven on its exact commit": "a run of no tests exits 0, so 'proven' is not what the evidence says (a2 #4)",
    "proven at every step": "Deploy and Maintain have no runner (a5 #20)",
    "auditable after": "the evidence is a git-ignored folder and a 90-day CI artifact (a5 #10)",
    "frictionless": "an ask a harness rule holds is asked twice (a10 #10)",
    "record you can check": "a record is the agent's note after it acts, never proof (a2 #8)",
    "whoever writes the tests never makes them pass": "the roles are told, not held (a3 C15)",
    "never reads what your machine has installed": "init's hint reads the machine (a6 F9)",
    "you need no commands to start": "the person still restarts the agent and protects the branch (a10 #10)",
    "one default for each ecosystem": "Ruby, Elixir, Scala, MySQL, and Redis have none (a9 #19)",
    "tools you already trust": "only branch protection stops, and the person sets it (a5 #3)",
}


class OverclaimTests(unittest.TestCase):
    def test_no_front_door_page_holds_a_claim_the_code_does_not_deliver(self):
        for page in FRONT_DOOR:
            text = " ".join((ROOT / page).read_text(encoding="utf-8").lower().split())
            for phrase, why in OVERCLAIMS.items():
                with self.subTest(page=page, phrase=phrase):
                    self.assertFalse(phrase in text, f"{page} says '{phrase}', which the code does not deliver: {why}")


class ReadmeTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.headings = re.findall(r"^## (.+)$", self.text, re.M)

    def test_the_example_comes_before_the_install_and_the_limits_are_stated(self):
        for needed in ("What it looks like", "Install", "What aidd does not do"):
            self.assertIn(needed, self.headings)
        self.assertLess(self.headings.index("What it looks like"), self.headings.index("Install"))

    def test_the_example_shows_what_aidd_adds(self):
        """A change to risky code, with the Spec approval question and the tests failing first: what an agent alone lacks."""
        example = self.text.split("## What it looks like", 1)[1].split("\n## ", 1)[0].split("```text", 1)[1].split("```", 1)[0]
        for needed in ("Spec", "Approve SPEC-", "fail"):
            self.assertIn(needed, example)

    def test_every_link_in_the_top_nav_goes_to_a_place_that_exists(self):
        nav = self.text.split('<p align="center">', 2)[2].split("</p>", 1)[0]
        for href in re.findall(r'href="([^"]+)"', nav):
            path, _, fragment = href.partition("#")
            page = ROOT / (path or "README.md")
            with self.subTest(href=href):
                self.assertTrue(page.is_file(), href)
                self.assertTrue(not fragment or fragment in anchors(page), href)


class FirstScreenTests(unittest.TestCase):
    """The README says what aidd is before its picture, and the picture stays readable on a phone.

    GitHub draws a README image at most as wide as the column, 324 CSS px on a 390-px phone (measured on 2026-11-11), so
    a label of size f in a picture whose `viewBox` is W wide draws at f * 324 / W px.
    """

    PHONE_COLUMN = 324
    SMALLEST_TEXT_PX = 12

    def setUp(self):
        self.text = (ROOT / "README.md").read_text(encoding="utf-8")

    def test_one_title_then_what_aidd_is_then_the_picture(self):
        prose = re.sub(r"^```.*?^```", "", self.text, flags=re.M | re.S)
        titles = re.findall(r"^# (.+)$", prose, re.M) + re.findall(r"<h1\b", prose)
        self.assertEqual(titles, ["aidd"], "one level-1 heading, the name")
        self.assertLess(prose.index("# aidd"), prose.index("<!-- aidd:gen product:short -->"))
        self.assertLess(prose.index("<!-- aidd:gen product:short -->"), prose.index('src="docs/assets/hero.svg"'))
        self.assertRegex(prose, r'<img src="docs/assets/hero\.svg" alt="[^"]{40,}"')

    def test_the_picture_is_self_contained_labelled_and_readable_on_a_phone(self):
        svg_text = (ROOT / "docs" / "assets" / "hero.svg").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"https?://[^\s\"']+", svg_text), ["http://www.w3.org/2000/svg"], "nothing loads from outside")
        svg = ElementTree.fromstring(svg_text)
        ns = "{http://www.w3.org/2000/svg}"
        for tag in ("script", "image", "foreignObject"):
            self.assertIsNone(svg.find(f".//{ns}{tag}"), tag)
        self.assertTrue(svg.findtext(f"{ns}title") and svg.findtext(f"{ns}desc"))
        width = float(svg.get("viewBox", "").split()[2])
        parents = {child: parent for parent in svg.iter() for child in parent}

        def size(element) -> float:
            while element is not None and element.get("font-size") is None:
                element = parents.get(element)
            return float(element.get("font-size")) if element is not None else 16.0

        smallest = min(size(text) for text in svg.iter(f"{ns}text"))
        self.assertGreaterEqual(smallest * self.PHONE_COLUMN / width, self.SMALLEST_TEXT_PX)


class RunbookTests(unittest.TestCase):
    """The install runbook asks only what is the person's to decide, and says one thing about unreleased code."""

    def setUp(self):
        self.text = (ROOT / "llms-install.md").read_text(encoding="utf-8")

        def section(title: str) -> str:
            return self.text.split(f"\n## {title}", 1)[1].split("\n## ", 1)[0]

        self.section = section

    def test_the_team_and_the_plugins_are_two_questions_and_the_plugins_need_a_yes(self):
        questions = [line for line in self.section("2. Adopt it").split("```text", 1)[1].split("```", 1)[0].splitlines() if line[:1].isdigit()]
        asked = {line.split(".")[0]: line.lower() for line in questions}
        self.assertEqual(len(asked), 4, "who decides, the CI, the team, and (Claude Code) the plugins")
        self.assertIn("team", asked["3"])
        self.assertNotIn("plugin", asked["3"])
        self.assertIn("plugin", asked["4"])
        self.assertTrue(says(self.section("2. Adopt it"), "--claude-plugins", "only on their yes"))

    def test_unreleased_code_has_one_rule_for_the_install_and_the_update(self):
        for part in ("1. Install the CLI", "Keep it current"):
            with self.subTest(part=part):
                self.assertIn("unreleased", self.section(part))
                self.assertTrue(says(self.section(part), "say", "one line"), part)

    def test_the_runbook_points_to_the_skill_for_the_rules_of_work(self):
        part = self.section("Work in a repository that uses aidd")
        self.assertIn("SKILL.md", part)
        self.assertTrue(says(part, "wins over this page"))

    def test_the_setup_commit_count_counts_files_not_folders(self):
        """`git status -s` shows an untracked folder as one line, so the count lists every untracked file (`-uall`)."""
        self.assertIn("git status -s -uall", self.section("4. Commit"))


if __name__ == "__main__":
    unittest.main()
