"""Design artifacts beyond the prototype and the design spec: user flows and a usability test in the design spec, a
component in DESIGN.md, and a journey in the Initiative's brief, never a file of their own; a wireframe mode in the one
prototype file, so rough directions and the full-fidelity prototype share it; and the docs that say which artifact a
change needs.
"""

import re
import unittest

from helpers import ROOT
from test_artifact_set import tables

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
TEAM = ROOT / "plugins" / "aidd-team"
PROTOTYPING = TEAM / "skills" / "prototyping"


# The switchers and hooks the prototype keeps in every mode: each one must still be there.
MOCK_TESTIDS = (
    "proto-skip-link",
    "proto-spec-link",
    *(f"proto-state-{s}" for s in ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run")),
    *(f"proto-frame-{f}" for f in ("320", "768", "1024", "1440", "ios", "android")),
    "proto-screens-toggle",
    "app-back",
    "signin-submit",
    "sitters-load-rest",
    "sitters-retry",
    "sitters-open-settings",
    "sitters-add-pet",
    "sitter-retry",
)


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def asset(name: str) -> str:
    return read(ASSETS / name)


def section(text: str, heading: str) -> str:
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


class WireframeTests(unittest.TestCase):
    """One prototype file, two fidelities: wireframe mode renders greyscale boxes with no brand tokens."""

    def test_the_prototype_has_a_wireframe_toggle(self):
        ui = asset("prototype.html")
        self.assertIn('data-mode="wireframe"', ui)
        self.assertIn('data-testid="proto-mode-wireframe"', ui)
        self.assertIn('data-testid="proto-mode-full"', ui)
        self.assertIn("mode=wireframe", ui)
        self.assertIn("parseLink(location.hash, location.search)", ui, "the mode is read from the deep link")
        # Wireframe mode is its own block after the tokens, so pasting a build's CSS over the tokens keeps it; it holds
        # no color of its own and turns the screens grey.
        wire = ui.split('<style id="wireframe">', 1)[1].split("</style>", 1)[0]
        self.assertNotIn('[data-mode="wireframe"]', ui.split('<style id="tokens">', 1)[1].split("</style>", 1)[0])
        self.assertNotRegex(wire, r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(", "no color of its own")
        self.assertIn("grayscale(1)", wire)
        self.assertIn("font-family: ui-monospace", wire, "the brand font is replaced too")
        self.assertIn("border-radius: 0", wire)

    def test_every_existing_switcher_and_hook_still_works(self):
        ui = asset("prototype.html")
        for testid in MOCK_TESTIDS:
            self.assertIn(f'data-testid="{testid}"', ui, testid)
        for state in ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run"):
            self.assertIn(f'data-state="{state}"', ui)
            self.assertIn(f'data-show="{state}"', ui)
        for frame in ("320", "768", "1024", "1440", "ios", "android"):
            self.assertIn(f'data-frame="{frame}"', ui)
        for tag in re.findall(r"<(?:button|a|input|select|textarea)\b[^>]*>", ui):
            self.assertIn("data-testid=", tag, tag)
        self.assertNotRegex(ui, r"<(?:script|link|img)[^>]+(?:src|href)=\"https?://", "still one self-contained file")
        self.assertEqual(ui.count("<html"), 1)

    def test_the_prototyping_skill_uses_wireframe_mode(self):
        text = read(PROTOTYPING / "SKILL.md")
        rough = text.split("## Pick a direction first", 1)[1].split("\n## ", 1)[0]
        self.assertIn("?mode=wireframe", rough)
        self.assertIn("full fidelity", rough)
        # At most three references a practice skill, so the design artifacts are a section of design-review.md.
        self.assertIn("references/design-review.md", text)
        self.assertFalse((PROTOTYPING / "references" / "design-artifacts.md").exists())
        detail = read(PROTOTYPING / "references" / "design-review.md")
        for home in ("`## Flows`", "`## Usability test`", "`DESIGN.md`", "`### Journey`"):
            self.assertIn(home, detail, home)
        self.assertNotRegex(detail, r"\]\((?:\.\./){2,}", "the skill links nothing outside its plugin")


class DocsTests(unittest.TestCase):
    """The recipe, the glossary, the artifact matrix, and the ceremony by team size name each artifact's one home."""

    def test_the_how_to_recipe(self):
        howto = read(ROOT / "docs" / "HOW-TO.md")
        recipe = howto.split("**…know which design artifact I need?**", 1)[1].split("\n**…", 1)[0]
        rows = [t for t in tables(recipe)][0]
        self.assertRegex(rows[0], r"\| Artifact \| When \| Who \| Frozen or living \|")
        body = "\n".join(rows)
        for home in ("aidd new design-spec --prototype", "aidd new design-spec", "`## Flows`", "`DESIGN.md`", "`### Journey`", "`## Usability test`"):
            self.assertIn(home, body, home)
        self.assertNotRegex(body, r"aidd new (flows|component|journey|usability|ui)\b")
        self.assertIn("wireframe", recipe)

    def test_the_glossary(self):
        glossary = read(ROOT / "docs" / "GLOSSARY.md")
        for term in ("Component spec", "Journey map", "Usability test", "User flows", "Wireframe mode"):
            self.assertRegex(glossary, rf"(?m)^\| {term} \|", term)

    def test_the_artifact_matrix(self):
        method = read(ROOT / "docs" / "METHOD.md").split("### 4.2 Spec", 1)[1].split("\n### 4.3", 1)[0]
        matrix = next(t for t in tables(method) if t[0].startswith("| Artifact | Proposal |"))
        body = "\n".join(matrix)
        for home in ("flows and usability test", "Components", "journey"):
            self.assertIn(home, body, home)
        for kind in ("flows", "component", "journey", "usability"):
            self.assertNotIn(f"`{kind}`", body, kind)

    def test_the_ceremony_table(self):
        for text in (read(SKILL / "references" / "profiles.md"), read(ROOT / "docs" / "METHOD.md")):
            part = text.split("Ceremony by team size", 1)[1]
            rows = next(t for t in tables(part) if t[0].startswith("| Team |"))
            solo = next(r for r in rows if r.startswith("| Solo"))
            self.assertIn("prototype", solo)
            self.assertRegex(solo, r"design spec'?s? light")
            for word in ("flows", "component", "journey", "usability"):
                self.assertNotIn(word, solo.split("|")[2], word)
            team = "\n".join(rows)
            for word in ("its flows", "DESIGN.md", "journey", "usability test"):
                self.assertIn(word, team, word)

    def test_the_skill_names_each_home(self):
        text = read(SKILL / "SKILL.md")
        row = next(line for line in text.splitlines() if "aidd new <kind> <topic> --spec <ID>" in line)
        for word in ("design-spec (the design spec, with its flows and usability test", "--prototype", "authz"):
            self.assertIn(word, row, word)


if __name__ == "__main__":
    unittest.main()
