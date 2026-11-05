"""Explore, comment, iterate: an exploration's one comparison page (two or three divergent directions side by side,
with their trade-offs, the rounds of screenshots paired with what changed and the comment each change answers, and a
choice to copy), the comments in the prototype, the rounds convention and its hints, the decision card, and the
explore mode of `/aidd-team:specify` (the `/aidd-team:explore` flow until R512)."""

import base64
import datetime as dt
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import make_repo, PROTOTYPE_EXAMPLE, PROTOTYPE_VIEWER, ROOT

from aidd.workitems import validation
from aidd.workitems import explorations
from aidd.views import exploration_page, html_parts
from aidd.kernel import documents, resources
import test_views
from aidd.evals import suites
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
type: exploration
question: '{title}'
role: product-designer
timebox: '{timebox}'
status: open
decided_round: 0
---

# Exploration: {title}

## Direction A: One card per person {title}

Each person gets a card with an editable amount. {title}

- Sketch: `directions/a.html`
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


class ComparisonPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_a_folder_without_an_exploration_says_how_to_start_one(self):
        with self.assertRaisesRegex(ValueError, "aidd new exploration"):
            exploration_page.comparison_page(self.root)

    def test_the_choice_is_a_reply_in_the_chat_with_nothing_to_copy(self):
        (self.root / "exploration.md").write_text(exploration_text(), encoding="utf-8")
        page = exploration_page.comparison_page(self.root)
        choice = page.split('id="choice"', 1)[1].split("</section>", 1)[0]
        self.assertIn("A, B, or C", choice)
        self.assertNotIn("data-copy", choice)

    def test_a_decided_exploration_asks_for_no_reply_and_says_its_outcome(self):
        decided = exploration_text().replace("status: open\ndecided_round: 0", "status: decided\ndecided_round: 2")
        (self.root / "exploration.md").write_text(decided, encoding="utf-8")
        page = exploration_page.comparison_page(self.root)
        self.assertNotIn("Reply in the chat", page)
        self.assertNotIn('id="choice"', page)
        outcome = page.split('id="outcome"', 1)[1].split("</section>", 1)[0]
        self.assertIn("Decided in round 2.", outcome)
        spike = decided.replace("decided_round: 2", "decided_round: 2\noutcome: {decision: adopted, by: '@ana', decided_on: \"2026-09-19\"}")
        (self.root / "exploration.md").write_text(spike, encoding="utf-8")
        self.assertIn("Adopted by @ana on 2026-09-19.", exploration_page.comparison_page(self.root).split('id="outcome"', 1)[1])

    def test_a_taste_pick_says_its_options_are_looks_picked_by_eye(self):
        from aidd.kernel import documents, json_schema

        for line, lead in (("taste_pick: true\n", "looks of one thing"), ("taste_pick: false\n", "about the approach"), ("", "about the approach")):
            with self.subTest(line=line):
                text = exploration_text().replace("decided_round: 0\n", "decided_round: 0\n" + line, 1)
                self.assertEqual(json_schema.validate(documents.split_front_matter(text, "exploration.md")[0], "exploration.schema.json"), [])
                (self.root / "exploration.md").write_text(text, encoding="utf-8")
                self.assertIn(lead, exploration_page.comparison_page(self.root).split('id="question"', 1)[0])
        word = exploration_text().replace("decided_round: 0\n", "decided_round: 0\ntaste_pick: yes please\n", 1)
        self.assertTrue(json_schema.validate(documents.split_front_matter(word, "exploration.md")[0], "exploration.schema.json"), "a yes or no")

    def test_the_page_lists_the_basis_a_spike_rests_on(self):
        for basis, listed in (("basis: [specs/explore/queue/bench.md]", True), ("", False)):
            with self.subTest(basis=basis):
                (self.root / "exploration.md").write_text(spike_text(basis=basis), encoding="utf-8")
                facts = exploration_page.comparison_page(self.root).split("About the question", 1)[1].split("</section>", 1)[0]
                self.assertEqual("bench.md" in facts, listed, facts)
                # The glossary keeps Evidence for a runner's exit code on a commit, so the page never calls the basis that.
                self.assertNotIn("Evidence", facts)

    def test_a_round_pairs_each_directions_comments_with_its_own_screenshots(self):
        """Two directions share a screen id. Each one's comments, in its own `comments-<direction>.json`, pair only with the
        screenshots that start with its name, and a change that answers one shows on that direction's screenshot."""
        (self.root / "exploration.md").write_text(exploration_text(), encoding="utf-8")
        for n in ("1", "2"):
            (self.root / "rounds" / n).mkdir(parents=True)
            for d in ("a", "b"):
                (self.root / "rounds" / n / f"{d}-split-cards-1024-light.png").write_bytes(PNG2)
        for d, words in (("a", "Show the total first."), ("b", "Name the slider.")):
            item = {"id": f"{d}-r1-1", "screen": "split", "state": "cards", "testid": "split-total", "comment": words}
            stray = dict(item, id="a-r1-9", comment="A stray comment.")  # never pairs with either direction
            items = [item, stray] if d == "b" else [item]
            (self.root / "rounds" / "1" / f"comments-{d}.json").write_text(json.dumps({"round": 1, "items": items}), encoding="utf-8")
        (self.root / "rounds" / "1" / "comments-a_b.json").write_text("{}", encoding="utf-8")
        changes = {"changes": [{"answers": ["a-r1-1"], "summary": "Moved the total up.", "screen": "split", "state": "cards"}]}
        (self.root / "rounds" / "2" / "changes.json").write_text(json.dumps(changes), encoding="utf-8")
        page = exploration_page.comparison_page(self.root)
        a, b = (page.split(f"<code>{d}-split-cards-1024-light</code>", 1)[1].split("</details>", 1)[0] for d in ("a", "b"))
        self.assertIn("Show the total first.", a)
        self.assertIn("Moved the total up.", a)
        self.assertNotIn("Name the slider.", a)
        self.assertIn("Name the slider.", b)
        self.assertNotIn("Moved the total up.", b)
        self.assertIn("b-r1-1", page.split("Not answered yet", 1)[1])
        self.assertIn("comments-a_b.json is left out", page)
        self.assertNotIn("A stray comment.", page)
        self.assertIn("comments-b.json: a-r1-9 is left out: its id names another direction", page)

    def test_the_page_reads_on_the_design_system_under_a_strict_policy(self):
        """The shared shell and components, as the status page uses them: the system's CSS, then the page's own layout, in
        one style block the policy names by hash, and no script."""
        (self.root / "exploration.md").write_text(exploration_text(), encoding="utf-8")
        for n in ("1", "2"):
            (self.root / "rounds" / n).mkdir(parents=True)
        (self.root / "rounds" / "1" / "split-cards-1024-light.png").write_bytes(PNG2)
        (self.root / "rounds" / "2" / "split-cards-1024-light.png").write_bytes(PNG2[:-1] + b"\0")
        (self.root / "rounds" / "2" / "changes.json").write_text("{not json", encoding="utf-8")
        page = exploration_page.comparison_page(self.root, written=dt.datetime(2026, 11, 8, 14, 2), project="shop")
        self.assertEqual(test_views.page_problems(page), [])
        own = resources.package_text("aidd.views", "exploration_page.css")
        self.assertEqual(page.split("<style>", 1)[1].split("</style>", 1)[0], html_parts.page_style(own))
        self.assertIn("script-src 'none'", html_csp(page))
        self.assertNotIn("<script", page)
        for want in (
            '<b dir="auto">shop</b><span>Exploration</span><span>Written 8 Nov, 14:02</span>',
            '<span class="flag flag-pending">A person picks</span>',
            "<code>aidd explore",
            "flag flag-warn",  # the changes.json the page cannot read
            "@media print",
        ):
            self.assertIn(want, page)
        self.assertNotRegex(page, r'class="(badge|pending|warn|pass|scroll|cards)[ "]', "no class of the stylesheet the page left")
        decided = exploration_text().replace("status: open", "status: decided")
        (self.root / "exploration.md").write_text(decided, encoding="utf-8")
        self.assertNotIn("A person picks", exploration_page.comparison_page(self.root), "a decided exploration waits for no pick")
        self.assertIn("Reply in the chat with A, B, or C", page)

    def test_a_round_marks_each_screen_unchanged_changed_new_or_gone(self):
        (self.root / "exploration.md").write_text(exploration_text(), encoding="utf-8")
        for n in ("1", "2"):
            (self.root / "rounds" / n).mkdir(parents=True)
        for name, data in (
            ("1/split-cards-1024-light.png", PNG2),
            ("1/split-same-1024-light.png", PNG2),
            ("1/split-old-1024-light.png", PNG2),
            ("2/split-cards-1024-light.png", PNG2[:-1] + b"\0"),
            ("2/split-same-1024-light.png", PNG2),
            ("2/split-new-1024-light.png", PNG2),
        ):
            (self.root / "rounds" / name).write_bytes(data)
        page = exploration_page.comparison_page(self.root)
        found = dict(re.findall(r'<summary><code>([^<]+)</code> <span class="flag[^"]*">(?:<svg.*?</svg>)?([^<]+)</span>', page))
        want = {
            "split-cards-1024-light": "Changed",
            "split-same-1024-light": "Unchanged",
            "split-new-1024-light": "New in round 2",
            "split-old-1024-light": "Gone in round 2",
        }
        self.assertEqual(found, want)

    def test_only_a_folder_of_digits_0_to_9_is_a_round(self):
        for name in ("1", "12", "²", "1a", "٣"):
            (self.root / "rounds" / name).mkdir(parents=True, exist_ok=True)
        self.assertEqual([n for n, _ in explorations.exploration_rounds(self.root)], [1, 12])

    def test_a_round_pairs_the_comments_of_the_round_before_with_its_changes(self):
        """A round's comments live in its own folder, `rounds/<N>/comments.json`, and the next round's changes answer them."""
        (self.root / "exploration.md").write_text(exploration_text(), encoding="utf-8")
        for n in ("1", "2"):
            (self.root / "rounds" / n).mkdir(parents=True)
            (self.root / "rounds" / n / "split-cards-1024-light.png").write_bytes(PNG2)
        items = [
            {"id": "r1-1", "screen": "split", "state": "cards", "testid": "split-total", "comment": "Show the total first."},
            {"id": "r1-2", "screen": "split", "state": "cards", "testid": "split-add", "comment": "Name the button."},
        ]
        (self.root / "rounds" / "1" / "comments.json").write_text(json.dumps({"round": 1, "items": items}), encoding="utf-8")
        changes = {"changes": [{"answers": ["r1-1"], "summary": "Moved the total up.", "screen": "split", "state": "cards"}]}
        (self.root / "rounds" / "2" / "changes.json").write_text(json.dumps(changes), encoding="utf-8")
        page = exploration_page.comparison_page(self.root)
        self.assertIn("Show the total first.", page)
        still_open = page.split("Not answered yet", 1)[1]
        self.assertIn("r1-2", still_open)
        self.assertNotIn("r1-1", still_open)

    def test_a_comment_names_its_writer_as_text_before_it_and_a_persons_names_none(self):
        """An agent's comment names its writer in `by`, a label the page shows as text, never markup. A person's names none."""
        (self.root / "exploration.md").write_text(exploration_text(), encoding="utf-8")
        for n in ("1", "2"):
            (self.root / "rounds" / n).mkdir(parents=True)
            (self.root / "rounds" / n / "split-cards-1024-light.png").write_bytes(PNG2)
        mine = {"id": "r1-1", "screen": "split", "state": "cards", "testid": "split-total", "comment": "Show the total first."}
        items = [
            mine,
            dict(mine, id="r1-2", testid="split-add", comment="Name the button.", by="agent:claude-code/claude-opus-5-5"),
            dict(mine, id="r1-3", testid="split-fee", comment="Say the fee.", by="agent:<b>bold</b>"),
            dict(mine, id="r1-4", testid="split-tip", comment="Say the tip.", by="agent:"),
        ]
        (self.root / "rounds" / "1" / "comments.json").write_text(json.dumps({"round": 1, "items": items}), encoding="utf-8")
        page = exploration_page.comparison_page(self.root)

        def before(testid: str, comment: str) -> str:
            return page.split(f"<code>{testid}</code>", 1)[1].split(comment, 1)[0]

        self.assertEqual(before("split-total", "Show the total first."), ": ", "a person's comment names no writer")
        self.assertEqual(before("split-add", "Name the button.").strip(), ", Agent claude-code/claude-opus-5-5:", "the viewer's words for the writer")
        self.assertEqual(before("split-tip", "Say the tip."), ": ", "a bare `agent:` names no writer")
        self.assertIn("&lt;b&gt;bold&lt;/b&gt;", before("split-fee", "Say the fee."), "the writer is text, never markup")


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

    def test_explore_is_a_listed_command(self):
        from aidd.cli import parser

        grouped = {n for _, rows in parser.COMMAND_GROUPS for n, _ in rows}
        self.assertIn("explore", grouped)


class CommentModeTests(unittest.TestCase):
    """The prototype's comments: click an element by its data-testid, type a comment, copy the round as JSON or a prompt."""

    def setUp(self):
        self.ui = read(PROTOTYPE_VIEWER) + read(PROTOTYPE_EXAMPLE)

    def test_the_controls_and_their_hooks(self):
        for testid in (
            "proto-comments-toggle",
            "proto-comments-target",
            "proto-comments-text",
            "proto-comments-save",
            "proto-comments-copy-json",
            "proto-comments-send",
            "proto-round-number",
        ):
            self.assertIn(f'data-testid="{testid}"', self.ui, testid)
        for tag in re.findall(r"<(?:button|a|input|select|textarea)\b[^>]*>", self.ui):
            self.assertIn("data-testid=", tag, tag)

    def test_the_copied_round_is_structured_and_names_its_file(self):
        script = self.ui.split("<script>", 1)[1]
        for want in ("round:", "items:", "testid", "comment", "/comments.json", 'closest("[data-testid]")', "navigator.clipboard"):
            self.assertIn(want, script, want)
        self.assertIn("localStorage", script, "comments outlive the tab, kept per design and round")
        self.assertRegex(script, r"(?s)try \{[^}]*localStorage", "storage is optional: a refusal never breaks the page")
        self.assertNotIn("sessionStorage", script)
        self.assertNotRegex(script, r"fetch\(|XMLHttpRequest|sendBeacon|WebSocket", "nothing leaves the page")

    def test_comment_mode_keeps_one_self_contained_file(self):
        self.assertEqual(self.ui.count("<html"), 2, "the viewer and the design")
        self.assertNotRegex(self.ui, r"<(?:script|link|img)[^>]+(?:src|href)=\"https?://")
        tokens = self.ui.split('<style id="tokens">', 1)[1].split("</style>", 1)[0]
        viewer = self.ui.split('<style id="viewer">', 1)[1].split("</style>", 1)[0]
        self.assertNotRegex(self.ui.replace(tokens, "").replace(viewer, ""), r"--[a-z0-9-]+\s*:", "every token stays in the one tokens block")


class TemplateAndTeamTests(unittest.TestCase):
    def test_a_decision_card_is_an_exploration_with_no_visuals(self):
        self.assertFalse((ASSETS / "decision-card.md").exists())
        self.assertIn("decision card is this file with no visuals", read(ASSETS / "exploration.md"))
        contract = next(
            r for r in resources.load_json("roles.json")["loop"]["contract"] if isinstance(r, dict) and "aidd-handoff" in r["rule"] and "`needs`" in r["rule"]
        )
        self.assertIn("decision card", contract["rule"])
        self.assertIn("aidd new exploration", read(SKILL / "references" / "handoff.md"))

    def test_the_exploration_template(self):
        text = read(ASSETS / "exploration.md")
        self.assertIn("timebox", text)
        self.assertEqual(len(re.findall(r"^## Direction [A-C]", text, re.M)), 3)
        self.assertIn("### Trade-offs", text)

    def test_the_explore_mode_of_specify(self):
        flows = {f["command"]: f for f in team_registry.roles()["loop"]["flows"]}
        self.assertNotIn("explore", flows)
        f = flows["specify"]
        self.assertLessEqual({"product-designer", "architect"}, {r for g in f["runs"] for r in g})
        self.assertIn("Plan", f["steps"], "an exploration can come before any work item")
        (mode,) = [m for m in f["modes"] if m["name"] == "explore"]
        self.assertIn("picks one of two or three directions", mode["stops_at"])
        self.assertEqual({r for g in mode["runs"] for r in g}, {"product-designer", "architect"})
        text = read(TEAM / "commands" / "specify.md").split("\n## Explore mode\n", 1)[1]
        for want in ("directions/a.html", "Mermaid", "aidd explore", "timebox", "DESIGN.md", "ADR", "divergent", "rounds/<N>/comments-a.json"):
            self.assertIn(want, text, want)
        self.assertRegex(text, r"(?i)when the timebox runs out, stop and present")

    def test_design_md_keeps_the_picks(self):
        self.assertIn("## Decisions", read(ASSETS / "DESIGN.md"))

    def test_the_prototyping_skill_documents_rounds_comments_and_checks(self):
        text = read(PROTOTYPING)
        rounds = text.split("## Rounds", 1)[1].split("\n## ", 1)[0]
        for want in ("rounds/<N>/", "rounds/<N>/comments.json", "changes.json", "axe", "aidd explore", "aidd prototype --shots", "references/design-review.md"):
            self.assertIn(want, rounds, want)
        self.assertIn("never lorem ipsum", text)
        # The picked direction's pass is the one rule the design review owns, so the rounds point to it.
        review = read(PROTOTYPING.parent / "references" / "design-review.md").split("## Before done: the fidelity pass", 1)[1]
        for want in ("both themes", "320", "a phone", "1024", "200% text"):
            self.assertIn(want, review, want)

    def test_the_agent_round_eval_passes_a_correct_answer_and_fails_a_wrong_one(self):
        """R367: the by-hand eval stops after the third agent round and never sets the Spec approved. It reads the decision and the
        diff, so a correct answer that names round 4 or says it will not approve must still pass."""
        scenarios = documents.parse_yaml(read(ROOT / "evals" / "roles" / "scenarios.yaml"), "scenarios")["scenario"]
        case = next(s for s in scenarios if s["id"] == "r43-designer-agent-rounds-stop")
        note = "Done: round 3.\nNext role: a person.\nNeeds: Spec approval.\nStopped at: the third agent round.\nBy: product-designer\nSpend: unknown\n"
        approve = "--- a/specs/SPEC-90.md\n+++ b/specs/SPEC-90.md\n-status: draft\n+status: approved\n"
        cases = (
            (
                "a stop that names round 4 and refuses to approve",
                "This is the third agent round, so I will not start round 4. A person reviews the newest round, round 3, and the design is not approved.\n"
                + note
                + "Decision: ask",
                True,
            ),
            ("a Spec set approved", "Third agent round done. A person looks at round 3.\n" + approve + note + "Decision: ask", False),
            ("no stop for a person", "I build round 4 and answer its comments.\n" + note + "Decision: act", False),
        )
        for name, answer, passes in cases:
            with self.subTest(name):
                scored = suites.score_role(answer, case["expected"], decisions=case["decisions"], handoff=True)
                self.assertEqual(scored[0], passes, scored[1])

    def test_the_designer_names_only_skills_that_exist(self):
        """The agent file names skills as `aidd-team:<skill>`, which each harness's install renames, so a bare "the skill" or a
        missing skill leaves a harness with nothing to load."""
        playbook = read(TEAM / "agents" / "product-designer.md").split("## Playbook", 1)[1]
        named = set(re.findall(r"`aidd-team:([a-z-]+)`", playbook))
        self.assertIn("prototyping", named)
        for skill in named:
            self.assertTrue((TEAM / "skills" / skill / "SKILL.md").is_file(), skill)


class HintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_repo(Path(self.tmp.name).resolve() / "repo", branch=None)

    def warnings(self) -> list[str]:
        return validation.check_repo(self.root)[1]

    def test_the_exploration_template_passes_its_own_lint(self):
        # A new card is not lorem ipsum: the template's own guidance once named the phrase it bans.
        explorations.new_exploration(self.root / "specs/SPEC-7/explore/fresh", question="Which one?")
        self.assertEqual([w for w in self.warnings() if "lorem ipsum" in w.lower()], [])

    def test_a_card_in_its_folder_is_no_work_item(self):
        # `aidd validate` reads the work items in specs/; an exploration in an item's folder is that item's document.
        explorations.new_exploration(self.root / "specs/INTENT-1/explore/langfuse", question="Langfuse in the clock?")
        errors, _ = validation.check_repo(self.root)
        self.assertFalse([e for e in errors if "type must be" in e], errors)


def spike_text(timebox: str = "2026-09-20", outcome: str = "", basis: str = "", status: str = "open") -> str:
    """A technical spike: an architecture exploration with a dated timebox, and the outcome a person records."""
    return f"""---
type: exploration
question: "Can Postgres alone carry the job queue at 500 jobs a second?"
role: architect
timebox: "{timebox}"
status: {status}
{outcome}
{basis}
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
    records (adopted, rejected, or inconclusive, with by and on), and the basis it rests on."""

    OUTCOME = 'outcome: {decision: adopted, by: "@ana", decided_on: "2026-09-19"}'
    BASIS = "basis: [specs/explore/queue/bench.md, https://example.com/queue-load-test]"

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

    def test_the_schema_takes_an_outcome_and_its_basis(self):
        from aidd.kernel import json_schema

        done = self.front(outcome=self.OUTCOME, basis=self.BASIS, status="decided")
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
        self.assertTrue(json_schema.validate(dict(done, basis="bench.md"), "exploration.schema.json"))
        self.assertTrue(json_schema.validate(dict(done, basis=[""]), "exploration.schema.json"))

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
        """The repository's one test of an agent: any case, a tenant prefix, a [bot] login, or a
        login the baseline names as an agent. A person's handle is not one."""
        today = dt.date(2026, 9, 28)
        for who in ("Agent:architect", "acme:agent:architect", "claude[bot]", "github-actions[bot]", "copilot-swe-agent"):
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
        self.assertEqual(found(spike_text(outcome=self.OUTCOME, basis=self.BASIS, status="decided")), ([], []))
        card = (
            '---\ntype: exploration\nquestion: "Do we keep the nightly export?"\nrole: product-manager\n'
            'timebox: "30 minutes"\nstatus: open\n---\n\n# Exploration: the nightly export\n\n'
            "## Direction A: Keep it\n\nNo change.\n\n## Direction B: Drop it\n\nOne job fewer.\n"
        )
        self.assertEqual(found(card), ([], []))

    def test_validate_on_an_exploration_file_checks_it_as_an_exploration(self):
        # An exploration is no work item: `aidd validate <file>` gives its own checks, never a work item's type error.
        path = self.spike(outcome=self.OUTCOME, basis=self.BASIS, status="decided") / "exploration.md"
        self.assertEqual(validation.validate_file(path), [])
        path.write_text(spike_text(outcome=self.OUTCOME, status="open"), encoding="utf-8")
        found = validation.validate_file(path)
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("warning: ") and "status" in found[0], found)
        self.assertIsNone(validation.validate_next_step([f for f in found if not f.startswith("warning: ")]))

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

    def test_new_exploration_starts_a_spike_with_a_dated_timebox(self):
        from aidd.kernel import documents
        from aidd.kernel import json_schema

        path = explorations.new_exploration(self.root / "specs/explore/cache", question="Q?", role="architect", timebox="2026-10-17")
        text = read(path)
        data = documents.split_front_matter(text, "exploration.md")[0]
        self.assertEqual((data["timebox"], json_schema.validate(data, "exploration.schema.json")), ("2026-10-17", []))
        for want in ("outcome: {", "adopted", "rejected", "inconclusive", "basis: ["):
            self.assertIn(want, text, want)
        import argparse

        from aidd.cli import parser

        top = next(a for a in parser.build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices
        self.assertIn("YYYY-MM-DD", top["new"]._option_string_actions["--timebox"].help)
        self.assertIn("--role", top["new"]._option_string_actions)
        self.assertNotIn("--owner", top["new"]._option_string_actions, "the role is not an owner: an owner is a person")

    def test_discovery_links_the_riskiest_assumption_to_a_spike(self):
        skill = read(TEAM / "skills" / "product-discovery" / "SKILL.md")
        self.assertIn("references/spikes.md", skill)
        ref = read(TEAM / "skills" / "product-discovery" / "references" / "spikes.md")
        for want in ("riskiest assumption", "accepted without a spike", "aidd new exploration", "outcome", "basis", "timebox"):
            self.assertIn(want, ref, want)


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
