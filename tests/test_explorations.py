"""Explore, get feedback, iterate: an exploration's one comparison page (two or three divergent directions side by side,
with their trade-offs, the rounds of screenshots paired with what changed and the feedback each change answers, and a
choice to copy), the feedback mode in the prototype, the rounds convention and its hints, the decision card, and the
`/aidd-team:explore` flow."""

import base64
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, make_repo, run_cli
from test_views import HOSTILE, PNG, page_problems

from aidd.views import html_parts
from aidd.workitems import validation
from aidd.workitems import explorations
from aidd.views import exploration_page
from aidd.kernel import resources
from aidd.knowledge import team_registry

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
TEAM = ROOT / "plugins" / "aidd-team"
PROTOTYPING = TEAM / "skills" / "prototyping" / "SKILL.md"
# A second, different image: one more pixel, so a round can change a screen.
PNG2 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAYAAAD0In+KAAAAEUlEQVR42mNkYPj/n4GBgQEAFQQC/w2+Ex4AAAAASUVORK5CYII=")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def exploration_text(title: str = "How should a customer split a bill?", timebox: str = "45 minutes") -> str:
    return f"""---
kind: exploration
question: '{title}'
owner: product-designer
timebox: '{timebox}'
status: open
decided_round: 0
---

# Exploration: {title}

## Direction A: One card per person {title}

Each person gets a card with an editable amount. {title}

- Wireframe: `directions/a.html?mode=wireframe`
- Screens: `rounds/1/split-cards-1024-light.png`

### Trade-offs

- Good: every amount is visible at once {title}
- Costs: long lists scroll at 320 px

## Direction B: Slider

Drag to set shares.

```mermaid
graph TD
  A[Cart {title}] --> B[Slider]
```

### Trade-offs

- Good: fast for equal shares
- Costs: hard to reach an exact amount by keyboard

## Direction C: By item

Assign each line item to a person. Screens: `../outside.png`

### Trade-offs

- Good: fair for shared meals
- Costs: slow for a large cart

## Recommendation

B for speed, if the exact-amount case is rare. {title}
"""


def write_folder(root: Path, title: str = "How should a customer split a bill?") -> Path:
    folder = root / "specs" / "SPEC-7" / "explore" / "split-bill"
    (folder / "rounds" / "1").mkdir(parents=True)
    (folder / "rounds" / "2").mkdir(parents=True)
    (folder / "exploration.md").write_text(exploration_text(title), encoding="utf-8")
    (folder / "rounds/1/split-cards-1024-light.png").write_bytes(PNG)
    (folder / "rounds/1/split-cards-1024-dark.png").write_bytes(PNG)
    (folder / "rounds/1/split-error-320-light.png").write_bytes(PNG)
    (folder / "rounds/2/split-cards-1024-light.png").write_bytes(PNG2)
    (folder / "rounds/2/split-cards-1024-dark.png").write_bytes(PNG)
    (folder / "rounds/2/split-empty-320-light.png").write_bytes(PNG)
    (root / "specs" / "SPEC-7" / "outside.png").write_bytes(PNG)
    feedback = {
        "round": 1,
        "items": [
            {"id": "r1-1", "testid": "split-amount", "note": f"the amount is too small {title}"},
            {"id": "r1-2", "testid": "split-add", "note": "where do I add a person?"},
        ],
    }
    (folder / "feedback-round-1.json").write_text(json.dumps(feedback), encoding="utf-8")
    changes = {"round": 2, "changes": [{"screen": "split", "state": "cards", "summary": f"larger amounts {title}", "answers": ["r1-1"]}]}
    (folder / "rounds/2/changes.json").write_text(json.dumps(changes), encoding="utf-8")
    return folder


class ComparisonPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def render(self, title: str = HOSTILE) -> str:
        return exploration_page.comparison_page(write_folder(self.root, title))

    def test_hostile_text_is_escaped_and_the_page_is_self_contained(self):
        page = self.render()
        self.assertEqual(page_problems(page), [])
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertIn(f"script-src '{html_parts.SCRIPT_HASH}'", html_csp(page))

    def test_directions_side_by_side_with_their_trade_offs_under_each(self):
        page = self.render("split")
        cards = re.findall(r'<article class="direction"[^>]*>(.*?)</article>', page, re.S)
        self.assertEqual(len(cards), 3)
        for card, name in zip(cards, ("One card per person", "Slider", "By item"), strict=True):
            self.assertIn(name, card)
            self.assertIn("Trade-offs", card)
            self.assertIn("Costs", card)
        self.assertIn("grid-template-columns:repeat(auto-fit", page.replace(" ", ""), "side by side on a wide screen, stacked on a phone")
        self.assertIn("graph TD", cards[1], "a Mermaid direction shows as its source")
        self.assertIn("data:image/png;base64," + base64.b64encode(PNG).decode(), cards[0])
        self.assertNotIn("data:image", cards[2], "an image outside the folder is never embedded")
        self.assertIn("leaves the folder", cards[2])
        for want in ("45 minutes", "product-designer", "Recommendation", "directions/a.html?mode=wireframe"):
            self.assertIn(want, page)

    def test_the_choice_is_copied_never_recorded(self):
        page = self.render("split")
        choice = page.split('id="choice"', 1)[1]
        for letter, name in (("A", "One card per person"), ("B", "Slider"), ("C", "By item")):
            self.assertRegex(choice, rf"<pre id=\"choice-{letter.lower()}\">[^<]*Direction {letter}: {name}")
        self.assertIn("Why:", choice)
        self.assertIn("DESIGN.md", choice)
        self.assertIn("ADR", choice)
        self.assertIn("never records", choice)
        for button in re.findall(r"<button\b[^>]*>", page):
            self.assertIn("data-copy=", button, "a button only copies")
        self.assertNotIn("<form", page)
        self.assertNotRegex(page, r"(?i)approve\b[^\n]*copy")

    def test_rounds_pair_each_screen_with_the_round_before_and_link_the_feedback_it_answers(self):
        page = self.render("split")
        rounds = page.split('id="rounds"', 1)[1].split('id="choice"', 1)[0]
        self.assertIn("Round 2", rounds)
        self.assertIn("split-cards-1024-light", rounds)
        self.assertIn("larger amounts split", rounds)
        self.assertIn("r1-1", rounds)
        self.assertIn("the amount is too small split", rounds, "the answered note is shown beside the change")
        self.assertIn("r1-2", rounds.split("Not answered yet", 1)[1], "an unanswered item is listed")
        self.assertIn("unchanged", rounds, "an identical screenshot says so")
        self.assertIn("new in round 2", rounds)
        self.assertIn("gone in round 2", rounds)
        self.assertIn("data:image/png;base64," + base64.b64encode(PNG2).decode(), rounds)

    def test_the_page_is_deterministic(self):
        folder = write_folder(self.root, "split")
        self.assertEqual(exploration_page.comparison_page(folder), exploration_page.comparison_page(folder))

    def test_a_broken_changes_file_is_named_not_fatal(self):
        folder = write_folder(self.root, "split")
        (folder / "rounds/2/changes.json").write_text("{nope", encoding="utf-8")
        page = exploration_page.comparison_page(folder)
        self.assertIn("changes.json is not JSON", page)
        self.assertEqual(page_problems(page), [])

    def test_a_folder_without_an_exploration_says_how_to_start_one(self):
        with self.assertRaisesRegex(ValueError, "aidd new exploration"):
            exploration_page.comparison_page(self.root)


def html_csp(page: str) -> str:
    import html

    return html.unescape(re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', page).group(1))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(Path(self.tmp.name).resolve() / "repo")
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)

    def test_new_writes_the_template_then_explore_renders_one_page(self):
        folder = "specs/SPEC-9/explore/refund-button"
        code, out = run_cli("new", "exploration", folder, "--title", "Where does the refund button go?", "--timebox", "30 minutes")
        self.assertEqual(code, 0, out)
        code, out = run_cli("explore", folder)
        self.assertEqual(code, 0, out)
        text = read(self.root / folder / "exploration.md")
        self.assertIn("Where does the refund button go?", text)
        self.assertIn("30 minutes", text)
        self.assertNotIn("{{", text)
        page = read(self.root / ".aidd/views/explore-SPEC-9-refund-button.html")  # the item and the slug: slugs repeat across items
        self.assertEqual(page_problems(page), [])
        self.assertIn("Where does the refund button go?", page)
        code2, out2 = run_cli("explore", folder, "--out", "p.html")
        self.assertEqual(code2, 0, out2)
        self.assertEqual(read(self.root / "p.html"), page)
        code3, out3 = run_cli("new", "exploration", folder, "--title", "again")
        self.assertNotEqual(code3, 0, "an exploration is never overwritten")
        self.assertIn("exists", out3)

    def test_explore_is_a_listed_command(self):
        from aidd.cli import parser

        grouped = {n for _, rows in parser.COMMAND_GROUPS for n, _ in rows}
        self.assertIn("explore", grouped)


class FeedbackModeTests(unittest.TestCase):
    """The prototype's feedback mode: click an element by its data-testid, type a note, copy the round as JSON or a prompt."""

    def setUp(self):
        self.ui = read(ASSETS / "prototype.html")

    def test_the_controls_and_their_hooks(self):
        for testid in (
            "proto-feedback-toggle",
            "proto-feedback-target",
            "proto-feedback-note",
            "proto-feedback-add",
            "proto-feedback-copy-json",
            "proto-feedback-copy-prompt",
            "proto-feedback-round",
        ):
            self.assertIn(f'data-testid="{testid}"', self.ui, testid)
        for tag in re.findall(r"<(?:button|a|input|select|textarea)\b[^>]*>", self.ui):
            self.assertIn("data-testid=", tag, tag)

    def test_the_copied_round_is_structured_and_names_its_file(self):
        script = self.ui.split("<script>", 1)[1]
        for want in ("round:", "items:", "testid", "note", "feedback-round-", 'closest("[data-testid]")', "navigator.clipboard"):
            self.assertIn(want, script, want)
        self.assertIn("sessionStorage", script)
        self.assertRegex(script, r"try \{[^}]*sessionStorage", "storage is optional: a refusal never breaks the page")
        self.assertNotIn("localStorage", script, "notes live in the tab")
        self.assertNotRegex(script, r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket", "nothing leaves the page")

    def test_feedback_mode_keeps_one_self_contained_file(self):
        self.assertEqual(self.ui.count("<html"), 1)
        self.assertNotRegex(self.ui, r"<(?:script|link|img)[^>]+(?:src|href)=\"https?://")
        tokens = self.ui.split('<style id="tokens">', 1)[1].split("</style>", 1)[0]
        self.assertNotRegex(self.ui.replace(tokens, ""), r"--[a-z0-9-]+\s*:", "every token stays in the one tokens block")


class TemplateAndTeamTests(unittest.TestCase):
    def test_a_decision_card_is_an_exploration_with_no_visuals(self):
        self.assertFalse((ASSETS / "decision-card.md").exists())
        self.assertIn("decision card is this file with no visuals", read(ASSETS / "exploration.md"))
        contract = next(
            r for r in resources.load_json("roles.json")["loop"]["contract"] if isinstance(r, dict) and "aidd-handoff" in r["rule"] and "Needs" in r["rule"]
        )
        self.assertIn("decision card", contract["rule"])
        self.assertIn("aidd new exploration", read(SKILL / "references" / "handoff.md"))

    def test_the_exploration_template(self):
        text = read(ASSETS / "exploration.md")
        self.assertIn("timebox", text)
        self.assertEqual(len(re.findall(r"^## Direction [A-C]", text, re.M)), 3)
        self.assertIn("### Trade-offs", text)

    def test_the_explore_flow_and_command(self):
        flows = {f["command"]: f for f in team_registry.roles()["loop"]["flows"]}
        f = flows["explore"]
        self.assertEqual({r for g in f["runs"] for r in g}, {"product-designer", "architect"})
        self.assertIn("picks", f["stops_at"])
        text = read(TEAM / "commands" / "explore.md")
        for want in ("?mode=wireframe", "Mermaid", "aidd explore", "timebox", "DESIGN.md", "ADR", "divergent", "feedback-round-"):
            self.assertIn(want, text, want)
        self.assertRegex(text, r"(?i)when the timebox runs out, stop and present")

    def test_design_md_keeps_the_picks(self):
        self.assertIn("## Decisions", read(ASSETS / "DESIGN.md"))

    def test_the_prototyping_skill_documents_rounds_feedback_and_checks(self):
        text = read(PROTOTYPING)
        rounds = text.split("## Rounds", 1)[1].split("\n## ", 1)[0]
        for want in ("rounds/<N>/", "feedback-round-<N>.json", "changes.json", "axe", "both themes", "320", "aidd explore"):
            self.assertIn(want, rounds, want)
        self.assertIn("never lorem ipsum", text)


class HintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(Path(self.tmp.name).resolve() / "repo", branch=None)

    def warnings(self) -> list[str]:
        return validation.check_repo(self.root)[1]

    def test_a_round_without_a_dark_screenshot_while_dark_mode_is_on(self):
        folder = write_folder(self.root, "split")
        (folder / "rounds/3").mkdir()
        (folder / "rounds/3/split-cards-1024-light.png").write_bytes(PNG)
        found = [w for w in self.warnings() if "dark screenshot" in w]
        self.assertEqual(len(found), 1, found)
        self.assertIn("specs/SPEC-7/explore/split-bill/rounds/3", found[0])
        cfg = self.root / ".aidd/config.yaml"
        cfg.write_text(read(cfg) + "\nproject:\n  defaults:\n    disabled: {dark_mode: a print-only report}\n", encoding="utf-8")
        self.assertEqual([w for w in self.warnings() if "dark screenshot" in w], [])

    def test_lorem_ipsum_in_a_design_folder(self):
        write_folder(self.root, "split")
        design = self.root / "specs" / "SPEC-7" / "design"
        design.mkdir(parents=True)
        (design / "prototype.html").write_text("<p>Lorem ipsum dolor sit amet</p>", encoding="utf-8")
        found = [w for w in self.warnings() if "lorem ipsum" in w.lower()]
        self.assertEqual(len(found), 1, found)
        self.assertIn("specs/SPEC-7/design/prototype.html", found[0])

    def test_the_exploration_template_passes_its_own_lint(self):
        # A new card is not lorem ipsum: the template's own guidance once named the phrase it bans.
        explorations.new_exploration(self.root / "specs/SPEC-7/explore/fresh", question="Which one?")
        self.assertEqual([w for w in self.warnings() if "lorem ipsum" in w.lower()], [])

    def test_a_card_in_its_folder_is_no_work_item(self):
        # `aidd validate` reads the work items in specs/; an exploration in an item's folder is that item's document.
        explorations.new_exploration(self.root / "specs/INIT-1/explore/langfuse", question="Langfuse in the clock?")
        errors, _ = validation.check_repo(self.root)
        self.assertFalse([e for e in errors if "kind must be" in e], errors)


def spike_text(timebox: str = "2026-09-20", outcome: str = "", evidence: str = "", status: str = "open") -> str:
    """A technical spike: an architecture exploration with a dated timebox, and the outcome a person records."""
    return f"""---
kind: exploration
question: "Can Postgres alone carry the job queue at 500 jobs a second?"
owner: architect
timebox: "{timebox}"
status: {status}
{outcome}
{evidence}
---

# Exploration: the job queue

## Direction A: Postgres with SKIP LOCKED

One table, no new service.

### Trade-offs

- Good: nothing new to run
- Costs: vacuum load at peak

## Direction B: Redis streams

### Trade-offs

- Good: fast
- Costs: one more service to run
"""


class SpikeTests(unittest.TestCase):
    """A technical spike is an exploration too: its question, a timebox that ends on a date, the outcome a person
    records (adopted, rejected, or inconclusive, with by and on), and the evidence it found."""

    OUTCOME = 'outcome: {decision: adopted, by: "@ana", decided_on: "2026-09-19"}'
    EVIDENCE = "evidence: [specs/explore/queue/bench.md, https://example.com/queue-load-test]"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(Path(self.tmp.name).resolve() / "repo", branch=None)
        self.folder = self.root / "specs" / "explore" / "queue"
        self.folder.mkdir(parents=True)

    def spike(self, **kw) -> Path:
        (self.folder / "exploration.md").write_text(spike_text(**kw), encoding="utf-8")
        return self.folder

    def front(self, **kw) -> dict:
        from aidd.kernel import documents

        return documents.split_front_matter(spike_text(**kw), "exploration.md")[0]

    def test_the_schema_takes_an_outcome_and_evidence(self):
        from aidd.kernel import json_schema

        done = self.front(outcome=self.OUTCOME, evidence=self.EVIDENCE, status="decided")
        self.assertEqual(json_schema.validate(done, "exploration.schema.json"), [])
        self.assertEqual(done["outcome"]["decision"], "adopted")
        for decision in ("adopted", "rejected", "inconclusive"):
            self.assertEqual(json_schema.validate(dict(done, outcome=dict(done["outcome"], decision=decision)), "exploration.schema.json"), [], decision)
        # A closed list, a person who decided, and a day.
        self.assertTrue(json_schema.validate(dict(done, outcome=dict(done["outcome"], decision="maybe")), "exploration.schema.json"))
        for key in ("by", "decided_on", "decision"):
            less = {k: v for k, v in done["outcome"].items() if k != key}
            self.assertTrue(json_schema.validate(dict(done, outcome=less), "exploration.schema.json"), key)
        # A recorded outcome decides the exploration.
        self.assertTrue(json_schema.validate(dict(done, status="open"), "exploration.schema.json"))
        self.assertTrue(json_schema.validate(dict(done, evidence="bench.md"), "exploration.schema.json"))
        self.assertTrue(json_schema.validate(dict(done, evidence=[""]), "exploration.schema.json"))

    def test_validate_warns_when_the_timebox_date_passed_with_no_outcome(self):
        today = dt.date(2026, 9, 28)
        self.spike()
        found = [w for w in validation.check_repo(self.root, today)[1] if "timebox" in w]
        self.assertEqual(len(found), 1, found)
        self.assertIn("specs/explore/queue/exploration.md", found[0])
        self.assertIn("2026-09-20", found[0])
        self.assertIn("outcome", found[0])
        # Not yet past, recorded, or a timebox in minutes: no warning.
        for kw, when in (
            ({"timebox": "2026-09-28"}, today),
            ({}, dt.date(2026, 9, 20)),
            ({"outcome": self.OUTCOME, "status": "decided"}, today),
            ({"timebox": "45 minutes"}, today),
            ({"status": "decided"}, today),
        ):
            self.spike(**kw)
            self.assertEqual([w for w in validation.check_repo(self.root, when)[1] if "timebox" in w], [], kw)

    def test_an_agent_never_records_the_outcome(self):
        self.spike(outcome=self.OUTCOME.replace("@ana", "agent:architect"), status="decided")
        found = [w for w in validation.check_repo(self.root, dt.date(2026, 9, 28))[1] if "outcome.by" in w]
        self.assertEqual(len(found), 1, found)
        self.assertIn("a person", found[0])

    def test_an_agent_in_any_form_never_records_the_outcome(self):
        """The repository's one test of an agent: any case, a tenant prefix, a [bot] login, a configured bot, or a
        login the baseline names as an agent. A person's handle is not one."""
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8").replace("bots: []", "bots: [release-robot]", 1), encoding="utf-8")
        today = dt.date(2026, 9, 28)
        for who in ("Agent:architect", "acme:agent:architect", "claude[bot]", "github-actions[bot]", "@release-robot", "copilot-swe-agent"):
            self.spike(outcome=self.OUTCOME.replace("@ana", who), status="decided")
            found = [w for w in validation.check_repo(self.root, today)[1] if "is an agent account" in w]
            self.assertEqual(len(found), 1, who)
            self.assertIn(who, found[0])
        for who in ("@ana", "acme:@ana", "email:ana@example.com"):
            self.spike(outcome=self.OUTCOME.replace("@ana", who), status="decided")
            self.assertEqual([w for w in validation.check_repo(self.root, today)[1] if "is an agent account" in w], [], who)

    def test_validate_schema_checks_the_front_matter_as_warnings(self):
        """`aidd explore` refuses front matter the schema rejects; `aidd validate` names it first, as a warning."""
        today = dt.date(2026, 9, 28)

        def found(text: str) -> tuple[list[str], list[str]]:
            (self.folder / "exploration.md").write_text(text, encoding="utf-8")
            errors, warnings = validation.check_repo(self.root, today)
            mine = "specs/explore/queue/exploration.md"
            return [e for e in errors if mine in e], [w for w in warnings if mine in w]

        errors, warnings = found(spike_text(outcome=self.OUTCOME.replace("decision: adopted", "decision: maybe"), status="decided"))
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("outcome.decision", warnings[0])
        self.assertIn("adopted, rejected, inconclusive", warnings[0])
        # A recorded outcome makes the status decided (the schema's if/then).
        errors, warnings = found(spike_text(outcome=self.OUTCOME, status="open"))
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn("status", warnings[0])
        self.assertIn("decided", warnings[0])
        # Front matter that does not parse is named too.
        self.assertTrue(found(spike_text().replace("status: open", "status: open"))[1])
        # A valid spike and a valid decision card: nothing.
        self.assertEqual(found(spike_text(outcome=self.OUTCOME, evidence=self.EVIDENCE, status="decided")), ([], []))
        card = (
            '---\nkind: exploration\nquestion: "Do we keep the nightly export?"\nowner: product-manager\n'
            'timebox: "30 minutes"\nstatus: open\n---\n\n# Exploration: the nightly export\n\n'
            "## Direction A: Keep it\n\nNo change.\n\n## Direction B: Drop it\n\nOne job fewer.\n"
        )
        self.assertEqual(found(card), ([], []))

    def test_a_timebox_that_looks_like_a_date_but_is_not_one(self):
        today = dt.date(2026, 9, 28)
        for timebox in ("2026-9-20", "2026-02-30", "2026/09/20"):
            self.spike(timebox=timebox)
            found = [w for w in validation.check_repo(self.root, today)[1] if "looks like a date" in w]
            self.assertEqual(len(found), 1, timebox)
            self.assertIn("YYYY-MM-DD", found[0])
        for timebox in ("2026-09-20", "45 minutes", "2 USD"):
            self.spike(timebox=timebox)
            self.assertEqual([w for w in validation.check_repo(self.root, today)[1] if "looks like a date" in w], [], timebox)

    def test_the_page_shows_the_outcome_and_the_evidence(self):
        page = exploration_page.comparison_page(self.spike(outcome=self.OUTCOME, evidence=self.EVIDENCE, status="decided"))
        self.assertEqual(page_problems(page), [])
        for want in ("adopted", "@ana", "2026-09-19", "specs/explore/queue/bench.md", "https://example.com/queue-load-test"):
            self.assertIn(want, page)

    def test_new_exploration_starts_a_spike_with_a_dated_timebox(self):
        from aidd.kernel import documents
        from aidd.kernel import json_schema

        path = explorations.new_exploration(self.root / "specs/explore/cache", question="Q?", owner="architect", timebox="2026-10-17")
        text = read(path)
        data = documents.split_front_matter(text, "exploration.md")[0]
        self.assertEqual((data["timebox"], json_schema.validate(data, "exploration.schema.json")), ("2026-10-17", []))
        for want in ("outcome: {", "adopted", "rejected", "inconclusive", "evidence: ["):
            self.assertIn(want, text, want)
        import argparse

        from aidd.cli import parser

        top = next(a for a in parser.build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices
        self.assertIn("YYYY-MM-DD", top["new"]._option_string_actions["--timebox"].help)

    def test_discovery_links_the_riskiest_assumption_to_a_spike(self):
        skill = read(TEAM / "skills" / "product-discovery" / "SKILL.md")
        self.assertIn("references/spikes.md", skill)
        ref = read(TEAM / "skills" / "product-discovery" / "references" / "spikes.md")
        for want in ("riskiest assumption", "accepted without a spike", "aidd new exploration", "outcome", "evidence", "timebox"):
            self.assertIn(want, ref, want)


@unittest.skipUnless(shutil.which("git"), "git is required")
class OutcomeGuardTests(unittest.TestCase):
    """The guard keeps a spike's outcome a person's, as it keeps a proposal's decisions: an aidd-team role's
    edit that adds or changes `outcome` in exploration.md is denied; the rest of the file stays the role's."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(Path(self.tmp.name).resolve() / "repo", branch=None)

    def hook(self, rel: str, tool: str, tool_input: dict, agent: str | None = "aidd-team:tech-writer"):
        from aidd.guard import edit_check

        event = {"tool_name": tool, "tool_input": {"file_path": str(self.root / rel), **tool_input}}
        if agent:
            event["agent_type"] = agent
        return edit_check.check_agent_edit(str(self.root), rel, event)

    def test_an_agent_never_records_the_outcome(self):
        outcome = SpikeTests.OUTCOME
        for rel in ("specs/explore/queue/exploration.md", "specs/SPEC-9/explore/refund-button/exploration.md"):
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            open_text, decided = spike_text(), spike_text(outcome=outcome, status="decided")
            # A new file that already carries an outcome, and an Edit or a Write that adds one: denied, for any role.
            for agent in ("aidd-team:tech-writer", "aidd-team:architect", "aidd-team:product-designer"):
                decision, reason = self.hook(rel, "Write", {"content": decided}, agent)
                self.assertEqual(decision, "deny", (rel, agent))
                self.assertIn("outcome, which only a person records", reason)
            path.write_text(open_text, encoding="utf-8")
            add = {"old_string": "status: open\n", "new_string": "status: decided\n" + outcome + "\n"}
            self.assertEqual(self.hook(rel, "Edit", add)[0], "deny", rel)
            broken = decided.replace("kind: exploration", "kind = ")
            self.assertEqual(self.hook(rel, "Write", {"content": broken})[0], "deny", rel)  # cannot compare, and names it
            # Changing a recorded outcome: denied too.
            path.write_text(decided, encoding="utf-8")
            change = {"edits": [{"old_string": "decision: adopted", "new_string": "decision: rejected"}]}
            self.assertEqual(self.hook(rel, "MultiEdit", change)[0], "deny", rel)
            # The rest of the file stays its owner's, with the recorded outcome untouched; the tech writer owns docs/, not explorations.
            tidy = {"old_string": "One table, no new service.", "new_string": "One table."}
            self.assertEqual(self.hook(rel, "Edit", tidy, "aidd-team:architect")[0], "allow", rel)
            self.assertEqual(self.hook(rel, "Edit", tidy, "aidd-team:tech-writer")[0], "deny", rel)
            # The person's own session (no subagent) records it.
            path.write_text(open_text, encoding="utf-8")
            self.assertEqual(self.hook(rel, "Edit", add, agent=None)[0], "allow", rel)
        from aidd.guard import denial_log

        self.assertEqual(denial_log.reason_code("x: this edit adds or changes an exploration's outcome, which only a person records"), "exploration_decision")


@unittest.skipUnless(shutil.which("git"), "git is required")
class DocsTests(unittest.TestCase):
    def test_how_to_glossary_and_changelog(self):
        glossary = read(ROOT / "docs" / "GLOSSARY.md")
        for term in ("| Decision card |", "| Exploration |", "| Round |"):
            self.assertIn(term, glossary)
        self.assertIn("aidd explore", read(ROOT / "CHANGELOG.md"))
        self.assertIn("aidd explore", read(ROOT / "docs" / "CLI.md"))


if __name__ == "__main__":
    unittest.main()
