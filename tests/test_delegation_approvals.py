"""`aidd delegate check` and a person's approval of an Intent, and the product scope's files. A delegated push, merge, or Spec
approval never lands a change to what an Intent's `intent.approve` covers, or to a file of the product scope, and a delegated Spec
approval waits for the Spec's parent Intent to stand approved on the default branch's tip. Each deferral has its table: what defers,
and the honest work beside it that still passes."""

from __future__ import annotations

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import SAMPLE_SPEC, git
from test_delegation_check import Repo
from test_delegation_spec import SpecCase

from aidd.workitems import intents
from aidd.delegation import diff_signals, intent_approvals, policy
from aidd.kernel import documents, resources

PERSON = "Maya Lee <maya@users.noreply.github.com>"
AT = "2026-11-10T09:12:00Z"
# The Intents' folder under the default `product_dir`: where an Intent lives, and the folder an approval is read from.
INTENTS = "product/intents"
FORMER = "specs"  # a folder outside the Intents' folder, where an Intent is misplaced
INTENT = f"{INTENTS}/INTENT-1.md"
SHA = "a" * 40
# The two lines a person's approval holds by, in the last paragraph of the commit that changes only the Intent's `approval`.
APPROVED_BY = f"Approved-by: {PERSON}"
YES = f"{APPROVED_BY}\nApproves: INTENT-1"
OUTCOME = "Shoppers pay by card by 2027-01-01"
OTHER = "Shoppers pay by card or by invoice by 2027-01-01"


def criteria_line(result: str = "", approval: str = "", extra: str = "") -> str:
    """The `success_criteria` line of an Intent with one criterion S1, with a drafted `result` when `result` is given, that result's
    `approval`, and `extra` keys on the criterion."""
    kept = f", result: {{{result}{', approval: {' + approval + '}' if approval else ''}}}" if result else ""
    return f"success_criteria: [{{id: S1, metric: {{name: Paid, source: ledger, baseline: 1, target: 2}}, measure_after_days: 30{extra}{kept}}}]"


CHECK = criteria_line()
DRAFT = "measured_on: '2027-03-01', actual: \"40%\", source: ledger, decision: continue"
RED = "import unittest\n\nclass T(unittest.TestCase):\n    def test_discount(self):\n        self.assertTrue(__import__('os').path.exists('src/checkout/discount.py'))\n"


def intent(
    outcome: str = OUTCOME,
    *,
    approved: bool = True,
    at: str = AT,
    specs: tuple[str, ...] = ("SPEC-220",),
    planned_spec_extra: str = "",
    top: str = "",
    type_: str = "intent",
    ident: str = "INTENT-1",
    body: str = "## Problem\n",
    phase_name: str = "First",
    phase_extra: str = "",
) -> str:
    """An Intent file: its approval (when `approved`), `top` for more top-level lines, and a planned Spec line for each id in `specs`."""
    lines = ["---", f"type: {type_}", f"id: {ident}", 'title: "Card payments"', f'outcome: "{outcome}"']
    lines += [f'approval: {{by: "{PERSON}", at: "{at}"}}'] if approved else []
    lines += [top.rstrip("\n")] if top else []
    lines += ["phases:", "  - id: P1", f"    name: {phase_name}", *([f"    {phase_extra}"] if phase_extra else []), "    specs:"]
    pad = "      "
    lines += [f"{pad}- {{id: {sid}, title: Slice {sid}{planned_spec_extra}}}" for sid in specs]
    return "\n".join([*lines, "---", "", body]) + "\n"


def without_approval(text: str) -> str:
    """The Intent `text` as it stood before the person approved it: the same file with no `approval` line."""
    return re.sub(r"^approval: .*\n", "", text, flags=re.M)


def spec_text(parent: str | None) -> str:
    return SAMPLE_SPEC.replace("route: normal", "status: ready\n" + (f"parent: {parent}\n" if parent else "") + "route: normal")


class FindingTests(unittest.TestCase):
    def test_each_new_code_is_a_reserved_defer_with_its_next_step(self):
        for code in ("intent_approval_changed", "intent_not_approved"):
            with self.subTest(code):
                row = policy.reasons()[code]
                self.assertTrue(row["reserved"], "only a person approves an Intent")
                self.assertIn("ask the person", row["next"]["what"].lower())
                self.assertIn("aidd approve", row["next"]["what"])
                self.assertIn("in the chat", row["next"]["what"], "a yes in the chat works where no terminal does")

    def test_the_next_steps_hold_for_a_person_who_just_approved_and_for_a_deleted_intent(self):
        """The step never says to approve again as the only way: the person merges the change themselves, and approves first only when
        it changes what they approved. The reserved path names the product scope."""
        step = policy.reasons()["intent_approval_changed"]["next"]["what"]
        self.assertIn("merge this change themselves", step)
        self.assertIn("If it changes what they approved", step)
        self.assertIn("product scope", policy.reasons()["reserved_path"]["why"])

    def test_trace_id_says_the_same_in_its_description_and_its_pattern(self):
        """Each description's example is a value the pattern takes, and the shape the tests write passes."""
        import re

        common = resources.load_json("common.schema.json")["$defs"]
        pattern = re.compile(common["trace_id"]["pattern"])
        texts = [
            resources.load_json("intent.schema.json")["properties"]["trace_id"]["description"],
            common["planned_spec"]["properties"]["repo"]["description"],
        ]
        for text in texts:
            example = re.search(r"`trace_id: ([^`]+)`", text)
            self.assertTrue(example, text)
            self.assertTrue(pattern.fullmatch(example.group(1).replace("<home>", "acme").replace("<Intent id>", "INTENT-1")), example.group(1))

    def test_what_an_agent_keeps_is_a_property_of_the_schema_and_nothing_else_is_named(self):
        """A field an agent keeps that the schema renames or drops fails here, so the list never names what no longer exists. Every
        other key is covered by being absent from the list, so a key added to the schema is covered until a person lists it."""
        schema = resources.load_json("intent.schema.json")
        planned_spec_properties = resources.load_json("common.schema.json")["$defs"]["planned_spec"]["properties"]
        self.assertEqual([f for f in intents.AGENT_KEPT if f not in schema["properties"]], [])
        self.assertEqual([f for f in intents.PLANNED_SPEC_KEPT if f not in planned_spec_properties], [])
        covered = [f for f in schema["properties"] if f not in intents.AGENT_KEPT]
        self.assertTrue({"approval", "outcome", "serves", "success_criteria", "reaches", "status", "go_no_go", "decisions", "phases"} <= set(covered))


class ApprovalCase(SpecCase):
    """main holds Intent INTENT-1 as a person approved it: in a commit that changes only its `approval`, with their `Approved-by` and
    `Approves` lines; feature starts there."""

    def fresh(self) -> None:
        """A new folder for the next row of a table, so each row starts from its own repository."""
        self.root = Path(tempfile.mkdtemp(dir=self.root.parent, prefix="row.")).resolve()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def commit_approval(self, repo: Repo, text: str, *, message: tuple[str, ...] = (YES,), path: str = INTENT) -> str:
        """The Intent `text` at `path`, committed as a person approves it: an Intent that holds an `approval` goes in as the file without
        it first, then in a commit that changes nothing else, whose last paragraph is the `message` lines. A draft goes in as one commit."""
        bare = without_approval(text)
        if bare != text:
            repo.write(path, bare)
            repo.commit("Draft the Intent")
        repo.write(path, text)
        return repo.commit("Approve the Intent", *(("-m", "\n".join(message)) if message else ()))

    def approved(self, text: str | None = None, *, message: tuple[str, ...] = (YES,), path: str = INTENT, **cfg) -> Repo:
        repo = self.repo(**cfg)
        git(self.root, "checkout", "-q", "main")
        self.commit_approval(repo, text or intent(), message=message, path=path)
        git(self.root, "checkout", "-q", "-B", "feature", "main")
        return repo

    def bases(self, repo: Repo, texts: set[str | None]) -> dict[str | None, str]:
        """A commit for each Intent text, off the repository's first commit, each the approved version in a commit that holds the approval."""
        git(self.root, "checkout", "-q", "main")
        start = git(self.root, "rev-parse", "HEAD")
        out = {}
        for text in texts:
            git(self.root, "checkout", "-q", "--detach", start)
            out[text] = self.commit_approval(repo, text or intent())
        return out

    def moved_by(self, repo: Repo, base: str, edits: dict[str, str | None]) -> list[str]:
        """What the change from the commit `base` does to an approval, once `edits` (path to text, None to delete) are committed."""
        git(self.root, "checkout", "-q", "-B", "work", base)
        for path, text in edits.items():
            if text is None:
                git(self.root, "rm", "-q", path)
            else:
                repo.write(path, text)
        head = repo.commit("The change")
        return intent_approvals.changes(base, head, str(self.root), diff_signals.changed(base, head, str(self.root)))


class WhatAnApprovalCoversTests(ApprovalCase):
    def test_what_changes_an_approved_intent_defers_and_what_a_slice_start_writes_passes(self):
        sha = "b" * 40
        two = intent(specs=("SPEC-220", "SPEC-221"))
        checked = intent(top=CHECK)
        cases = {
            # name: (the base Intent, None for the plain one; the edits; what names the change, None when it passes)
            "a new outcome": (None, {INTENT: intent(OTHER)}, "outcome changed"),
            "a slice added": (None, {INTENT: two}, "specs changed"),
            "a slice removed": (two, {INTENT: intent()}, "specs changed"),
            "a slice swapped for another": (None, {INTENT: intent(specs=("SPEC-221",))}, "specs changed"),
            "serves set": (None, {INTENT: intent(top="serves: Outcome-1")}, "serves changed"),
            "serves moved": (intent(top="serves: Outcome-1"), {INTENT: intent(top="serves: Outcome-2")}, "serves changed"),
            "success criteria set": (None, {INTENT: checked}, "success_criteria changed"),
            "a criterion's days moved": (checked, {INTENT: intent(top=CHECK.replace("30", "31"))}, "success_criteria changed"),
            "a criterion renumbered": (checked, {INTENT: intent(top=CHECK.replace("id: S1", "id: S2"))}, "success_criteria changed"),
            "a criterion's day chosen": (checked, {INTENT: intent(top=criteria_line(extra=", measure_on: '2027-02-01'"))}, "success_criteria changed"),
            "reaches changed": (None, {INTENT: intent(top="reaches: flagged")}, "reaches changed"),
            "the approval's time rewritten": (None, {INTENT: intent(at="2026-11-12T09:12:00Z")}, "approval changed"),
            "the approval's person rewritten": (None, {INTENT: intent().replace(PERSON, "Dana <dana@example.com>")}, "approval changed"),
            "the approval erased": (None, {INTENT: intent(approved=False)}, "approval changed"),
            "the Intent deleted": (None, {INTENT: None}, "is gone"),
            "the Intent made another type": (None, {INTENT: intent(type_="spec")}, "is gone"),
            "the Intent's front matter broken": (None, {INTENT: "---\noutcome: [unclosed\n---\n"}, "is gone"),
            "moved, and the outcome edited": (None, {INTENT: None, f"{INTENTS}/moved.md": intent(OTHER)}, "outcome changed"),
            "two fields at once": (None, {INTENT: intent("Another goal by 2027-01-01", specs=("SPEC-221",))}, "outcome, specs changed"),
            "a slice start: blocked_by and development_team leave the line": (
                intent(planned_spec_extra=", blocked_by: [SPEC-1], development_team: web"),
                {INTENT: intent()},
                None,
            ),
            "a slice records drafted_in": (None, {INTENT: intent(planned_spec_extra=f", drafted_in: {sha}")}, None),
            "a slice's title rewritten": (None, {INTENT: intent().replace("Slice SPEC-220", "Delete every customer's data")}, "phases changed"),
            "a slice's repo set": (None, {INTENT: intent(planned_spec_extra=", repo: acme/other")}, "phases changed"),
            "the slices reordered": (two, {INTENT: intent(specs=("SPEC-221", "SPEC-220"))}, "phases changed"),
            "a phase's date set": (None, {INTENT: intent(phase_extra='due: "2027-02-01"')}, "phases changed"),
            "a phase's money set": (None, {INTENT: intent(phase_extra="amount: 15000\n    currency: EUR")}, "phases changed"),
            "a phase's finish recorded": (None, {INTENT: intent(phase_extra='finished_on: "2027-02-01"')}, "phases changed"),
            "a phase renamed": (None, {INTENT: intent(phase_name="Another name")}, "phases changed"),
            "status cancelled": (None, {INTENT: intent(top="status: cancelled")}, "status changed"),
            "status done": (None, {INTENT: intent(top="status: done")}, "status changed"),
            "a no-go recorded": (None, {INTENT: intent(top="go_no_go: {decision: no_go, by: '@maya', decided_on: \"2027-01-02\"}")}, "go_no_go changed"),
            "a decision entry added": (
                None,
                {INTENT: intent(top="decisions:\n  - {id: D1, decision: drop it, by: '@maya', at: \"2027-01-02T09:00:00Z\"}")},
                "decisions changed",
            ),
            "the Intent's title rewritten": (None, {INTENT: intent().replace("Card payments", "Anything else")}, "title changed"),
            "a request link changed": (None, {INTENT: intent(top="request: BRIEF.md")}, "request changed"),
            "a key no schema lists yet": (None, {INTENT: intent(top="future_field: x")}, "future_field changed"),
            "the body rewritten": (None, {INTENT: intent(body="## Problem\n\nMore about the problem.\n")}, "body changed"),
            "the out-of-scope section emptied": (intent(body="## Out of scope\n\nNo invoices.\n"), {INTENT: intent(body="## Out of scope\n")}, "body changed"),
            "the Intent waits for another (kept)": (None, {INTENT: intent(top="blocked_by: [INTENT-9]")}, None),
            "the owner named (kept)": (None, {INTENT: intent(top="owner: maya")}, None),
            "a tracker link added (kept)": (None, {INTENT: intent(top="tracker: [{type: epic, id: PORT-31}]")}, None),
            "a trace id set (kept)": (None, {INTENT: intent(top="trace_id: acme-INTENT-1")}, None),
            "a risk added (kept)": (
                None,
                {INTENT: intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}")},
                None,
            ),
            "a risk edited without being accepted (kept)": (
                intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}"),
                {INTENT: intent(top="risks:\n  - {id: R1, text: slips later, owner: '@maya', status: open, likelihood: low, impact: low}")},
                None,
            ),
            "a second risk added (kept)": (
                intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}"),
                {
                    INTENT: intent(
                        top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}\n  - {id: R2, text: late, owner: '@maya', status: open, likelihood: low, impact: low}"
                    )
                },
                None,
            ),
            "a risk moved to accepted": (
                intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}"),
                {INTENT: intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: accepted, likelihood: low, impact: low}")},
                "risks changed",
            ),
            "a risk added already accepted": (
                None,
                {INTENT: intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: accepted, likelihood: low, impact: low}")},
                "risks changed",
            ),
            "a risk removed": (
                intent(
                    top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}\n  - {id: R2, text: late, owner: '@maya', status: open, likelihood: low, impact: low}"
                ),
                {INTENT: intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}")},
                "risks changed",
            ),
            "every risk removed": (
                intent(top="risks:\n  - {id: R1, text: slips, owner: '@maya', status: open, likelihood: low, impact: low}"),
                {INTENT: intent()},
                "risks changed",
            ),
            "a first result drafted (kept)": (checked, {INTENT: intent(top=criteria_line(DRAFT))}, None),
            "a first result drafted with its approval": (
                checked,
                {INTENT: intent(top=criteria_line(DRAFT, "by: Dana, at: '2027-03-02T09:00:00Z'"))},
                "success_criteria changed",
            ),
            "a result changed": (intent(top=criteria_line(DRAFT)), {INTENT: intent(top=criteria_line(DRAFT.replace("40%", "45%")))}, "result changed"),
            "a result removed": (intent(top=criteria_line(DRAFT)), {INTENT: checked}, "result changed"),
            "a drafted result that fails its schema": (
                checked,
                {INTENT: intent(top=criteria_line(DRAFT.replace("decision: continue", "decision: maybe")))},
                "result changed",
            ),
            "a blocker added (kept)": (intent(top="blocked_by: [INTENT-9]"), {INTENT: intent(top="blocked_by: [INTENT-9, INTENT-8]")}, None),
            "a blocker removed": (intent(top="blocked_by: [INTENT-9, INTENT-8]"), {INTENT: intent(top="blocked_by: [INTENT-9]")}, "blocked_by changed"),
            "every blocker removed": (intent(top="blocked_by: [INTENT-9]"), {INTENT: intent()}, "blocked_by changed"),
            "a kept key of the wrong shape (a mapping for blocked_by)": (None, {INTENT: intent(top="blocked_by: {goal: x}")}, "blocked_by changed"),
            "a kept key of the wrong shape (a number for owner)": (None, {INTENT: intent(top="owner: 5")}, "owner changed"),
            "a kept slice key of the wrong shape (drafted_in)": (None, {INTENT: intent(planned_spec_extra=", drafted_in: nope")}, "drafted_in changed"),
            "the Learn section written": (None, {INTENT: intent(body="## Problem\n\n## Learn\n\nThe outcome held.\n")}, "body changed"),
            "the Learn section rewritten": (
                intent(body="## Problem\n\n## Learn\n\nOld.\n"),
                {INTENT: intent(body="## Problem\n\n## Learn\n\nNew.\n")},
                "body changed",
            ),
            "the Learn section written and another changed": (
                intent(body="## Problem\n\nA.\n"),
                {INTENT: intent(body="## Problem\n\nB.\n\n## Learn\n\nIt held.\n")},
                "body changed",
            ),
            "a Learn heading placed above a covered section": (
                intent(body="## Constraints\n\nNo invoices.\n"),
                {INTENT: intent(body="## Learn\n\nScope note.\n\n## Constraints\n\nNo invoices.\n")},
                "body changed",
            ),
            "text added under a Learn heading that is not the last section": (
                intent(body="## Learn\n\nOld.\n\n## Constraints\n\nNo invoices.\n"),
                {INTENT: intent(body="## Learn\n\nNew.\n\n## Constraints\n\nNo invoices.\n")},
                "body changed",
            ),
            "a section added after the Learn section": (
                intent(body="## Problem\n\n## Learn\n\nOld.\n"),
                {INTENT: intent(body="## Problem\n\n## Learn\n\nOld.\n\n## Notes\n\nNew.\n")},
                "body changed",
            ),
            "the body's line endings converted, nothing else": (
                intent(body="## Problem\n\nA.\n"),
                {INTENT: intent(body="## Problem\r\n\r\nA.\r\n")},
                None,
            ),
            "a body with CRLF line endings, edited": (
                intent(body="## Problem\r\n\r\nA.\r\n"),
                {INTENT: intent(body="## Problem\r\n\r\nB.\r\n")},
                "body changed",
            ),
            "a body with CRLF line endings, and a Learn section written": (
                intent(body="## Problem\r\n\r\nA.\r\n"),
                {INTENT: intent(body="## Problem\r\n\r\nA.\r\n\r\n## Learn\r\n\r\nIt held.\r\n")},
                "body changed",
            ),
            "the mark of an approved version supplied by a file": (None, {INTENT: intent(top="_body_changed: true")}, "_body_changed changed"),
            "a section renamed Learn to hide it": (
                intent(body="## Constraints\n\nNo invoices.\n"),
                {INTENT: intent(body="## Learn\n\nNo invoices.\n")},
                "body changed",
            ),
            "a team named (kept)": (None, {INTENT: intent(top="development_team: web")}, None),
            "reaches set to its default": (None, {INTENT: intent(top="reaches: incremental")}, None),
            "the Intent moved, nothing changed": (None, {INTENT: None, f"{INTENTS}/moved.md": intent()}, None),
            "an unrelated file": (None, {"src/app.py": "x = 1\n"}, None),
            "a file with no front matter": (None, {"README.md": "# readme\n"}, None),
            "a Spec": (None, {f"{INTENTS}/SPEC-1.md": SAMPLE_SPEC}, None),
            "a file that is no Markdown": (None, {f"{INTENTS}/INTENT-2.txt": intent(specs=("SPEC-300",))}, None),
            "an uppercase extension": (None, {f"{INTENTS}/UPPER.MD": intent(OTHER)}, "it sets or changes approval"),
            "the approval moved by git: the same Intent in the specs folder, then the Intents' folder": (
                None,
                {INTENT: None, f"{FORMER}/INTENT-1.md": intent()},
                None,
            ),
        }
        repo = self.repo()
        bases = self.bases(repo, {base for base, _, _ in cases.values()})
        for name, (base, edits, expected) in cases.items():
            with self.subTest(name):
                found = self.moved_by(repo, bases[base], edits)
                if expected is None:
                    self.assertEqual(found, [])
                else:
                    self.assertTrue(found and expected in found[0], found)
                self.one_owner(base or intent(), edits.get(INTENT), expected)

    def one_owner(self, then_text: str, now_text: str | None, expected: str | None) -> None:
        """`aidd validate` and `aidd status` read what the approval covers through the same owner as the delegate: for an edit of the
        Intent's own file they say a change exactly when the delegate defers, except for the body, which only the delegate reads."""
        try:
            then, now = (documents.split_front_matter(text)[0] for text in (then_text, now_text or ""))
        except documents.DocumentError:
            return
        if now.get("type") == "intent" and expected != "body changed":
            self.assertEqual(bool(intents.changes_since(then, now)), expected is not None, "one owner for what an approval covers")

    def test_a_draft_no_person_approved_is_free_to_change_until_the_change_sets_an_approval(self):
        def new(text: str) -> str:
            return text.replace("INTENT-1", "INTENT-2")

        cases = {
            "a draft's goal edited": ({INTENT: intent("Another goal by 2027-01-01", approved=False)}, None),
            "a draft's slices changed": ({INTENT: intent(specs=("SPEC-1", "SPEC-2"), approved=False)}, None),
            "a new draft": ({f"{INTENTS}/INTENT-2.md": new(intent(approved=False))}, None),
            "a draft approved by the change": ({INTENT: intent()}, "sets or changes approval"),
            "a draft given an approval with a time alone": ({INTENT: intent(approved=False, top=f'approval: {{at: "{AT}"}}')}, "sets or changes approval"),
            "a new Intent that holds an approval": ({f"{INTENTS}/INTENT-2.md": new(intent())}, "sets or changes approval"),
            "a copy of an approved Intent under a new path": ({f"{INTENTS}/copy.md": intent()}, "sets or changes approval"),
        }
        repo = self.repo()
        draft = intent(approved=False)
        base = self.bases(repo, {draft})[draft]
        for name, (edits, expected) in cases.items():
            with self.subTest(name):
                found = self.moved_by(repo, base, edits)
                self.assertEqual(found == [], expected is None, found)
                if expected:
                    self.assertIn(expected, found[0])

    def test_an_intent_in_a_shape_no_reader_knows_counts_when_the_base_held_it_approved(self):
        """A `slices:` list beside `phases:` is a key no reader knows: it counts as a change of what the person approved, so the
        delegate defers."""
        both = intent().replace("phases:", "slices:\n  - {id: SPEC-1, title: one}\nphases:")
        repo = self.repo()
        found = self.moved_by(repo, self.bases(repo, {None})[None], {INTENT: both})
        self.assertIn("slices changed", " ".join(found))


if __name__ == "__main__":
    unittest.main()
