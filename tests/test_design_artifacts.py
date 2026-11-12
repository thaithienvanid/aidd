"""Design artifacts beyond the prototype and the design spec: user flows and a usability test in the design spec, a
component in DESIGN.md, and a journey in the Intent's map, never a file of their own; a wireframe mode in the one
prototype file, so rough directions and the full-fidelity prototype share it; and the docs that say which artifact a
change needs.
"""

import json
import re
import unittest

from helpers import PROTOTYPE_EXAMPLE, PROTOTYPE_VIEWER, ROOT
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


class FidelityTests(unittest.TestCase):
    """One fidelity: a direction is picked in an exploration, then the prototype is built at full fidelity."""

    def test_every_existing_switcher_and_hook_still_works(self):
        ui = PROTOTYPE_VIEWER.read_text(encoding="utf-8") + PROTOTYPE_EXAMPLE.read_text(encoding="utf-8")
        for testid in MOCK_TESTIDS:
            self.assertIn(f'data-testid="{testid}"', ui, testid)
        for state in ("empty", "loading", "partial", "error", "offline", "permission-denied", "success", "first-run"):
            self.assertIn(f'data-state="{state}"', ui)
            self.assertIn(f'data-show="{state}"', ui)
        for frame in ("320", "768", "1024", "1440", "ios", "android"):
            self.assertIn(f'data-frame="{frame}"', ui)
        for tag in re.findall(r"<(?:button|a|input|select|textarea)\b[^>]*>", ui):
            self.assertIn("data-testid=", tag, tag)
        self.assertNotRegex(ui, r"<(?:script|link|img)[^>]+(?:src|href)=\"https?://", "the design and the viewer load nothing remote")
        self.assertEqual(ui.count("<html"), 2, "two files: the viewer and the design")

    def test_a_direction_is_picked_before_full_fidelity(self):
        # No wireframe mode: a rough direction is an exploration's, and the prototype is built at full fidelity.
        text = read(PROTOTYPING / "SKILL.md")
        rough = text.split("### Size it, then pick a direction", 1)[1].split("\n### ", 1)[0]
        self.assertIn("aidd explore", rough)
        self.assertIn("full fidelity", rough)
        # Sized to the request: one prototype file may be the whole job, and directions come only when the approach is open.
        self.assertIn("one prototype file, maybe the whole job", rough)
        self.assertIn("only when the approach is open", rough)
        self.assertIn("never start one unasked", text)
        self.assertNotIn("wireframe mode", text.lower())
        # At most three references a practice skill, so the design artifacts are a section of design-review.md.
        self.assertIn("references/design-review.md", text)
        self.assertFalse((PROTOTYPING / "references" / "design-artifacts.md").exists())
        detail = read(PROTOTYPING / "references" / "design-review.md")
        for home in ("`## Flows`", "`## Usability test`", "`DESIGN.md`", "`## Map`"):
            self.assertIn(home, detail, home)
        self.assertNotRegex(detail, r"\]\((?:\.\./){2,}", "the skill links nothing outside its plugin")

    def test_every_rule_on_who_runs_the_fidelity_pass_names_one_trigger(self):
        # Three rules once disagreed on who reviews a small UI change, so the lead picked by habit (a26 T1). The design review
        # owns the trigger; every place that says who runs the pass names the same change, and AGENTS.md points to it.
        trigger = "a new or reshaped screen or flow, a change to a component's look or states, or a new or redrawn diagram or picture in a document"
        roles = json.loads(read(ROOT / "schemas" / "roles.json"))["roles"]
        places = {
            "the design review": read(PROTOTYPING / "references" / "design-review.md"),
            "the designer's starts_when": roles["product-designer"]["starts_when"],
            "the developer's done_when": roles["developer"]["done_when"],
            "the review flow": read(TEAM / "commands" / "review.md"),
            "the glossary": read(ROOT / "docs" / "GLOSSARY.md"),
            "AGENTS.md": read(ROOT / "AGENTS.md"),
        }
        for place, text in places.items():
            with self.subTest(place=place):
                if place == "AGENTS.md":
                    self.assertIn("`aidd-team:prototyping`'s design review", text)
                else:
                    self.assertIn(trigger, text)
                self.assertNotIn("the designer's for a new screen", text)
                self.assertNotIn("a new or reshaped screen, flow, or component", text)


class DocsTests(unittest.TestCase):
    """The glossary, the ceremony by team size, and the skill name each artifact's one home."""

    def test_the_glossary(self):
        glossary = read(ROOT / "docs" / "GLOSSARY.md")
        for term in ("Component spec", "Journey map", "Usability test", "User flows"):
            self.assertRegex(glossary, rf"(?m)^\| {term} \|", term)

    def test_the_ceremony_table(self):
        for text in (read(SKILL / "references" / "profiles.md"),):
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
        text = read(SKILL / "references" / "spec-docs.md")
        # The intro names the command and the prototype; the `type` row of the table is the one list of the types.
        intro = next(line for line in text.splitlines() if "aidd new <type> <topic> --spec <ID>" in line)
        self.assertIn("--prototype", intro)
        types = next(line for line in text.splitlines() if line.startswith("| `type` |"))
        for word in ("design-spec", "authz-matrix"):
            self.assertIn(f"`{word}`", types, word)


if __name__ == "__main__":
    unittest.main()
