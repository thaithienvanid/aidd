"""Intent approval, the gate before Specify: its risk rule asks, every harness that can hold its command asks at it,
`aidd validate` fails closed on an approval no commit holds, and a later change to the slices or the goal warns. And
plan drift once a Spec merged: a merge that changed files its plan never names warns."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import AGENT_APPROVERS, git

from aidd import config
from aidd.config import profile_data
from aidd.kernel import documents
from aidd.risk import commands, harness_rules, rules, suggestions
from aidd.workitems import intent_checks, intents, living_work

# The patterns that hold each form a commit or a command records an approval in: a message or `--trailer "Approves: ..."`, git's
# `key=value` form, a commit after git's own options, and `aidd approve` run as the command, as the packed program, or after other words.
APPROVAL = ("git commit *Approves*", "git * commit *Approves*", "*aidd approve*", "*aidd.pyz approve*", "aidd approve*")
WHO = "J <j@example.com>"
AT = "2026-11-10T09:12:00Z"
APPROVES = "Approves: INTENT-1"
# The last paragraph of the commit that holds a yes: the person's `Approved-by` line and the Intent's id.
HELD = (f"Approved-by: {WHO}", APPROVES)


def intent(extra: str = "", specs: str = "[{id: SPEC-1, title: one}]") -> str:
    return (
        f'---\ntype: intent\nid: INTENT-1\ntitle: "Plan"\noutcome: "g by 2027-01-01"\n{extra}phases: [{{id: P1, name: p, specs: {specs}}}]\n---\n\n## Problem\n'
    )


def approval(who: str = WHO, at: str = AT) -> str:
    """The front matter line of a person's yes."""
    return f"approval: {{by: {json.dumps(who)}, at: {json.dumps(at)}}}\n"


def commit(root: Path, message: str, *trailers: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message, *[a for t in trailers for a in ("--trailer", t)])


def hold(root: Path, path: Path, before: str, after: str, lines: tuple[str, ...] | None = None) -> None:
    """The two commits of a yes: `before` as it stood, then `after` alone, which differs by the `approval` and carries `lines` in its last
    paragraph (the person's `Approved-by` and the Intent's `Approves`, unless a case gives others)."""
    path.write_text(before, encoding="utf-8")
    commit(root, "plan")
    path.write_text(after, encoding="utf-8")
    commit(root, "approve", *(HELD if lines is None else lines))


class ApprovalRuleTests(unittest.TestCase):
    def test_intent_approve_asks_in_every_profile_and_is_never_suggested_lower(self):
        for profile in profile_data.profiles()["profiles"]:
            with self.subTest(profile=profile):
                rs = rules.rule_set(config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\n'))
                self.assertEqual(rules.level_of(rs, "intent.approve")[0], "ask")
        self.assertIn(("intent.approve", None, None), suggestions.DECISION_POINTS)

    def test_the_commit_and_the_command_that_record_an_approval_ask(self):
        rs = rules.rule_set(None)
        cases = [
            ('git commit -m "plan" --trailer "Approves: INTENT-1"', "ask"),
            ('git commit -m "plan" --trailer "Approved-by: J <j@example.com>" --trailer "Approves: INTENT-1"', "ask"),
            ('git commit -m "plan\\n\\nApproved-by: J <j@example.com>\\nApproves: INTENT-1"', "ask"),
            ('git commit -m "plan" --trailer "Approves=INTENT-1"', "ask"),
            ("aidd approve INTENT-1", "ask"),
            ("PYTHONPATH=src python3 -m aidd approve INTENT-1", "ask"),
            ("aidd.pyz approve INTENT-1", "ask"),
            ('git commit -m "plan"', "allow"),
        ]
        for line, level in cases:
            with self.subTest(line=line):
                # On the agent's own branch: a commit onto a default branch with no remote is a merge, and asks.
                self.assertEqual(commands.command_level(rs, line, cwd=None, branch="own")["level"], level)

    def test_each_harness_asks_at_it_or_names_it_left_to_the_skill(self):
        patterns = harness_rules.harness_patterns(rules.rule_set(None), "main")
        for pattern in APPROVAL:
            self.assertIn(pattern, patterns)
        for fmt, form in harness_rules.FORMATS.items():
            with self.subTest(format=fmt):
                if form.match == "words":
                    # A leading-words format cannot hold a trailer, nor a command behind other words, and asking before every commit
                    # would slow every change; it holds the one that starts with `aidd`.
                    self.assertEqual(harness_rules.unwritten(fmt, list(APPROVAL)), list(APPROVAL[:-1]))
                    self.assertEqual(harness_rules.widened(fmt, list(APPROVAL)), {})
                else:
                    self.assertEqual(harness_rules.unwritten(fmt, list(APPROVAL)), [])
                    entries = harness_rules._entries(fmt, list(APPROVAL))
                    # `aidd approve*` is held by `*aidd approve*`, so a glob or regular-expression format writes it once
                    self.assertEqual(len(entries), len(APPROVAL) - 1)
                    self.assertEqual(sum("Approves" in e for e in entries), 2)


@unittest.skipUnless(shutil.which("git"), "git is required")
class DoctorSaysWhereNoPromptAsksTests(unittest.TestCase):
    def test_doctor_names_the_harnesses_with_no_prompt_for_an_approval(self):
        from aidd.setup import adoption, doctor_harnesses

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["codex", "claude-code"]))
            lines = {
                key: [m for _, m in doctor_harnesses.harness_checks(root, [key]) if "`intent.approve`" in m and ("no prompt for" in m or "its prompt for" in m)]
                for key in ("codex", "claude-code")
            }
        self.assertEqual(len(lines["codex"]), 1, lines)
        self.assertIn("no prompt for `intent.approve`, so the skill asks", lines["codex"][0])
        self.assertEqual(len(lines["claude-code"]), 1, lines)
        self.assertIn("heredoc", lines["claude-code"][0], "its prompt matches the command text, which a heredoc message hides")
        self.assertIn("`Approves` line", lines["claude-code"][0])
        self.assertNotIn("no prompt", lines["claude-code"][0], "it has a prompt, and the note says what the prompt misses")


@unittest.skipUnless(shutil.which("git"), "git is required")
class ApprovalCheckTests(unittest.TestCase):
    def setUp(self):
        self.fresh_repo()

    def fresh_repo(self) -> None:
        """A new repository in a new folder, for the next row of a table."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "T")
        self.path = self.root / "product" / "intents" / "INTENT-1.md"
        self.path.parent.mkdir(parents=True)

    def warnings(self, text: str) -> list[str]:
        self.path.write_text(text, encoding="utf-8")
        from aidd.kernel import documents

        data, _ = documents.split_front_matter(text, "INTENT-1")
        return intent_checks.approval_warnings(self.path, data, self.root)

    def test_an_approval_no_commit_holds_fails_closed(self):
        approved = approval()
        self.assertEqual(self.warnings(intent()), [])  # not approved yet: `aidd status` asks for it
        self.assertEqual(len(self.warnings(intent(approved))), 1)  # written, never committed
        self.assertEqual(len(intent_checks.approval_warnings(self.path, {"type": "intent", "approval": {"at": AT}}, None)), 1)
        hold(self.root, self.path, intent(), intent(approved))
        cases = [
            ("as approved", intent(approved), 0),
            ("a slice renamed", intent(approved, "[{id: SPEC-1, title: renamed}]"), 1),  # a slice's title is what the person approved it would do
            ("a slice added", intent(approved, "[{id: SPEC-1, title: one}, {id: SPEC-2, title: two}]"), 1),
            ("a slice removed", intent(approved, "[{id: SPEC-2, title: two}]"), 1),
            ("the goal changed", intent(approved).replace("g by 2027", "h by 2027"), 1),
            # The body is read through the same owner as the delegate reads it, whole: a Learn section written at the end is a change too.
            ("the body rewritten", intent(approved).replace("## Problem\n", "## Problem\n\nMore.\n"), 1),
            ("a Learn section written", intent(approved) + "\n## Learn\n\nThe outcome held.\n", 1),
            (
                "a Learn section written and the Problem rewritten",
                intent(approved).replace("## Problem\n", "## Problem\n\nMore.\n") + "\n## Learn\n\nIt held.\n",
                1,
            ),
        ]
        for name, text, n in cases:
            with self.subTest(name):
                self.assertEqual(len(self.warnings(text)), n)

    def test_the_commit_of_a_yes_changes_nothing_in_the_file_but_the_approval(self):
        """Changed on purpose: a commit that created the file with its approval held, and so did one that edited a field or the body
        beside it. Now each holds nothing, and the file reads as draft with an error."""
        approved = approval()
        two = "[{id: SPEC-1, title: one}, {id: SPEC-2, title: two}]"
        cases = [
            ("the approval alone", [intent(), intent(approved)], 0),
            ("the commit creates the file with its approval", [intent(approved)], 1),
            ("a slice added beside it", [intent(), intent(approved, two)], 1),
            ("the goal changed beside it", [intent(), intent(approved).replace("g by 2027", "h by 2027")], 1),
            ("the body changed beside it", [intent(), intent(approved) + "\nMore.\n"], 1),
        ]
        for name, versions, n in cases:
            with self.subTest(name):
                self.fresh_repo()
                for i, text in enumerate(versions):
                    self.path.write_text(text, encoding="utf-8")
                    commit(self.root, "the plan", *(HELD if i == len(versions) - 1 else ()))
                self.assertEqual(len(self.warnings(versions[-1])), n)
        # An amend of the commit that held it changes more than the approval, so it holds nothing.
        self.fresh_repo()
        hold(self.root, self.path, intent(), intent(approved))
        self.assertEqual(len(self.warnings(intent(approved))), 0)
        self.path.write_text(intent(approved, two), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "--amend", "--no-edit")
        self.assertEqual(len(self.warnings(intent(approved, two))), 1)

    def test_a_body_with_the_other_line_endings_reads_as_changed_only_when_its_text_changed(self):
        """A working tree that converts line endings is no edit, and an edit in a body written with CRLF is one."""
        approved = approval()
        hold(self.root, self.path, intent(), intent(approved))
        base = intent(approved)
        for name, text, n in (
            ("converted", base.replace("## Problem\n", "## Problem\r\n"), 0),
            ("converted and edited", base.replace("## Problem\n", "## Problem\r\n\r\nMore.\r\n"), 1),
        ):
            with self.subTest(name):
                self.path.write_text(text, encoding="utf-8", newline="")
                from aidd.kernel import documents as docs

                data, _ = docs.split_front_matter(text, "INTENT-1")
                self.assertEqual(len(intent_checks.approval_warnings(self.path, data, self.root)), n)

    def test_the_approved_version_every_view_reads_carries_the_body_mark_and_only_for_a_body_change(self):
        """`aidd status` and the work list take the approved version from `approved_version`, so the mark it sets is how they read the body."""
        from aidd import workitems

        approved = approval()
        hold(self.root, self.path, intent(), intent(approved))
        for text, marked in ((intent(approved), False), (intent(approved) + "\n## Learn\n\nIt held.\n", True), (intent(approved) + "\nMore.\n", True)):
            self.path.write_text(text, encoding="utf-8")
            data, _ = documents.split_front_matter(text, "INTENT-1")
            then = intent_checks.approved_version(self.root, "product/intents/INTENT-1.md", data)
            self.assertEqual(bool(then and then.get(intents.BODY_CHANGED)), marked, text)
            self.assertEqual(bool(workitems.approved_changes(then or {}, data)), marked)

    def test_the_approval_commit_is_found_by_the_parsed_value_in_any_yaml_spelling(self):
        """A single-quoted value, a block mapping, and a trailing comment are the same `approval.at`, so the right lines hold in each."""
        spellings = {
            "single quotes": f"approval: {{by: 'J <j@example.com>', at: '{AT}'}}\n",
            "a trailing comment": f'approval: {{by: "J <j@example.com>", at: "{AT}"}}  # said in the chat\n',
            "single quotes and a comment": f"approval: {{by: 'J <j@example.com>', at: '{AT}'}} # said in the chat\n",
            "a block mapping and a comment": f'approval:\n  by: "J <j@example.com>"\n  at: "{AT}"  # said in the chat\n',
        }
        for name, line in spellings.items():
            with self.subTest(name):
                self.fresh_repo()
                hold(self.root, self.path, intent(), intent(line))
                data, _ = documents.split_front_matter(self.path.read_text(encoding="utf-8"), "INTENT-1")
                self.assertEqual(intent_checks.approval_warnings(self.path, data, self.root), [])
                # A slice added after the approval still warns in the same spelling.
                self.path.write_text(intent(line, "[{id: SPEC-1, title: one}, {id: SPEC-2, title: two}]"), encoding="utf-8")
                commit(self.root, "a slice")
                data, _ = documents.split_front_matter(self.path.read_text(encoding="utf-8"), "INTENT-1")
                self.assertEqual(len(intent_checks.approval_warnings(self.path, data, self.root)), 1)

    def test_a_person_put_in_the_file_after_an_agent_was_committed_with_that_persons_lines_is_no_approval(self):
        """The commit that first holds `approval.at` must hold the same `approval.by` as the file: the lines alone are not the approval."""
        agent, person = approval("agent:claude-code/x"), approval()
        hold(self.root, self.path, intent(), intent(agent))
        self.assertEqual(len(self.warnings(intent(person))), 1)
        commit(self.root, "name the person", *HELD)
        self.assertEqual(len(self.warnings(intent(person))), 1, "the later commit does not make the first one a person's")

    def test_a_commit_with_no_lines_that_first_wrote_the_value_in_a_comment_spelling_is_no_approval(self):
        line = f"approval: {{by: \"J <j@example.com>\", at: '{AT}'}}  # said in the chat\n"
        hold(self.root, self.path, intent(), intent(line), lines=())
        data, _ = documents.split_front_matter(self.path.read_text(encoding="utf-8"), "INTENT-1")
        self.assertEqual(len(intent_checks.approval_warnings(self.path, data, self.root)), 1)

    def test_status_waits_for_an_approval_a_person_made_and_a_commit_holds(self):
        from helpers import open_work

        from aidd.workitems import validation

        person = approval()
        agent = approval("agent:claude-code/x")
        bot = approval("Bot <noreply@anthropic.com>")
        free = approval("the person")
        two = "[{id: SPEC-1, title: one}, {id: SPEC-2, title: two}]"
        by = f"Approved-by: {WHO}"
        yes = [by, APPROVES]
        delegated = [*yes, "Decided-by: agent:claude-code/delegate", "Delegation: " + "a" * 40]
        plain = (intent(), [])
        context = f'context: "see {AT}"\n'

        def run(*steps: tuple[str, list[str] | None]) -> dict:
            """Commit each (text, trailers) in turn in a new repository, or only write it when the trailers are None;
            the last text is the file on disk. Returns the Intent's next step."""
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                git(root, "init", "-q", "-b", "main")
                git(root, "config", "user.email", "t@example.com")
                git(root, "config", "user.name", "T")
                (root / "product" / "intents").mkdir(parents=True)
                for text, trailers in steps:
                    (root / "product" / "intents" / "INTENT-1.md").write_text(text, encoding="utf-8")
                    if trailers is not None:
                        commit(root, "the plan", *trailers)
                return next(i for i in open_work(root) if i["id"] == "INTENT-1")["next"]

        cases = [
            ("not approved", [plain], "intent.approve"),
            ("approved, not committed", [plain, (intent(person), None)], "intent.approve"),
            ("approved and committed with the lines", [plain, (intent(person), yes)], "intent.slice"),
            ("approved, committed with no lines", [plain, (intent(person), [])], "intent.approve"),
            ("approved, `Approved-by` alone", [plain, (intent(person), [by])], "intent.approve"),
            ("approved, `Approves` alone", [plain, (intent(person), [APPROVES])], "intent.approve"),
            ("approved, the retired `Agreed-by` line", [plain, (intent(person), [f"Agreed-by: {WHO}", APPROVES])], "intent.approve"),
            ("approved, lines for someone else", [plain, (intent(person), ["Approved-by: K <k@example.com>", APPROVES])], "intent.approve"),
            ("approved, the lines in another case", [plain, (intent(person), ["approved-by: J <j@example.com>", "approves: INTENT-1"])], "intent.approve"),
            ("approved, another Intent's id", [plain, (intent(person), [by, "Approves: INTENT-2"])], "intent.approve"),
            ("approved, a longer id", [plain, (intent(person), [by, "Approves: INTENT-10"])], "intent.approve"),
            ("approved, one of its results", [plain, (intent(person), [by, "Approves: INTENT-1#S1"])], "intent.approve"),
            ("approved, the id in another case", [plain, (intent(person), [by, "Approves: intent-1"])], "intent.approve"),
            ("approved, its id among others", [plain, (intent(person), [by, "Approves: INTENT-2, INTENT-1"])], "intent.slice"),
            ("approved through a delegate's lines", [plain, (intent(person), delegated)], "intent.approve"),
            ("an agent's, committed", [plain, (intent(agent), ["Approved-by: agent:claude-code/x", APPROVES])], "intent.approve"),
            (
                "an agent's, then a person's in the file only",
                [plain, (intent(agent), ["Approved-by: agent:claude-code/x", APPROVES]), (intent(person), None)],
                "intent.approve",
            ),
            ("a bot's address in Name <email>", [plain, (intent(bot), ["Approved-by: Bot <noreply@anthropic.com>", APPROVES])], "intent.approve"),
            ("free text for the person", [plain, (intent(free), ["Approved-by: the person", APPROVES])], "intent.approve"),
            ("approval.at only in other text of an earlier commit", [(intent(context), []), (intent(person + context), None)], "intent.approve"),
            ("approval.at that is no RFC 3339 time", [plain, (intent(approval(at="yes")), yes)], "intent.approve"),
            ("a slice added after the approval", [plain, (intent(person), yes), (intent(person, two), [])], "intent.approve"),
            ("a slice added in the file only", [plain, (intent(person), yes), (intent(person, two), None)], "intent.approve"),
            ("a goal changed after the approval", [plain, (intent(person), yes), (intent(person).replace("g by", "h by"), [])], "intent.approve"),
            (
                "a slice added in a commit that repeats the time",
                [plain, (intent(person), yes), (intent(person + f'context: "{AT}"\n', two), [])],
                "intent.approve",
            ),
            # Changed on purpose: each of these held while the yes shared its commit with the file's creation or with an edit.
            ("the file created with its approval", [(intent(person), yes)], "intent.approve"),
            ("a slice added in the approval's commit", [plain, (intent(person, two), yes)], "intent.approve"),
            ("the body edited in the approval's commit", [plain, (intent(person) + "\nMore.\n", yes)], "intent.approve"),
        ]
        for name, steps, code in cases:
            with self.subTest(name):
                self.assertEqual(run(*steps)["code"], code)
        # A slice added after the approval is held, the approved one may still start, and the step says so.
        held = run(plain, (intent(person), yes), (intent(person, two), []))["what"]
        self.assertIn("SPEC-2", held)
        self.assertIn("SPEC-1", held)
        # The one-file check fails an agent's approval, as the repository-wide one does.
        self.path.write_text(intent(agent), encoding="utf-8")
        self.assertTrue(any("approval.by" in e and not e.startswith("warning") for e in validation.validate_file(self.path)))

    def test_status_and_validate_agree_on_who_approved_for_every_form(self):
        """An Intent whose `approval.by` names an agent, with an `Approved-by` line in the commit that says so, is not an
        approval to `aidd status` either; a person with an accent in the name is one to both."""
        from helpers import PEOPLE_APPROVERS, open_work

        from aidd.workitems import validation

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "t@example.com")
            git(root, "config", "user.name", "T")
            (root / "product" / "intents").mkdir(parents=True)
            path = root / "product" / "intents" / "INTENT-1.md"
            path.write_text(intent(), encoding="utf-8")
            commit(root, "plan")
            # One of each kind keeps the file inside its time budget; the table in test_spec_quality runs every form through the same rule.
            kinds = [
                v
                for v in AGENT_APPROVERS
                if v.startswith(("agent:developer <", "acme:agent:x", "@devin", "<noreply", "Bob <noreply@а", "agent́:dev <", "Clɑude"))
            ]
            people = [v for v in PEOPLE_APPROVERS if v.startswith(("José", "Adé", "Devin", "Olúm", "Əli", "@maya"))]
            self.assertEqual((len(kinds), len(people)), (7, 6))
            for n, (is_agent, who) in enumerate([(True, v) for v in kinds] + [(False, v) for v in people]):
                # Each commit changes only the `approval` of the file the one before left, so a person's holds.
                path.write_text(intent(approval(who, f"2026-11-10T09:{n:02d}:00Z")), encoding="utf-8")
                commit(root, "approve", f"Approved-by: {who}", APPROVES)
                code = next(i for i in open_work(root) if i["id"] == "INTENT-1")["next"]["code"]
                errors = [e for e in validation.validate_file(path) if "approval.by" in e and not e.startswith("warning")]
                with self.subTest(who=who):
                    self.assertEqual((code == "intent.approve", bool(errors)), (is_agent, is_agent), f"status {code}, validate {errors}")

    def test_an_agent_cannot_approve(self):
        cases = [
            ("agent:claude-code/x", 1, 0),
            ("Assistant <noreply@anthropic.com>", 1, 0),
            ("Bot <41898282+github-actions[bot]@users.noreply.github.com>", 1, 0),
            ("Qwen-Coder <qwen-coder@alibabacloud.com>", 1, 0),
            ("J <j@example.com>", 0, 0),
            ("jay", 0, 1),
        ]
        for who, errors, warnings in cases:
            with self.subTest(who=who):
                found = intent_checks.approval_problems("product/intents/INTENT-1.md", {"type": "intent", "approval": {"by": who, "at": AT}})
                self.assertEqual(
                    (len([f for f in found if not f.startswith("warning")]), len([f for f in found if f.startswith("warning")])), (errors, warnings)
                )

    def test_every_form_an_earlier_check_refused_still_cannot_approve(self):
        for who in AGENT_APPROVERS:
            with self.subTest(who=who):
                found = intent_checks.approval_problems("product/intents/INTENT-1.md", {"type": "intent", "approval": {"by": who, "at": AT}})
                self.assertEqual(len([f for f in found if not f.startswith("warning")]), 1, found)


@unittest.skipUnless(shutil.which("git"), "git is required")
class MergedDriftTests(unittest.TestCase):
    def spec(self, extra: str = "") -> str:
        return (
            "---\ntype: spec\nid: SPEC-1\ntitle: t\nchange_type: feat\nroute: normal\n"
            f"status: done\n{extra}tasks:\n  - id: SPEC-1-T1\n    title: t\n    scope: [src/app/**]\n---\n"
        )

    def merged(self, files: list[str], extra: str = "", learn: str = "", also: str = "") -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "t@example.com")
            git(root, "config", "user.name", "T")
            (root / "README.md").write_text("x\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "base")
            git(root, "checkout", "-qb", "spec/SPEC-1")
            (root / "specs").mkdir()
            (root / "specs/SPEC-1.md").write_text(self.spec(extra), encoding="utf-8")
            if also:  # a second Spec in the same merge, whose Task scope is `also`
                (root / "specs/SPEC-2.md").write_text(self.spec().replace("SPEC-1", "SPEC-2").replace("src/app/**", also), encoding="utf-8")
            for rel in files:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("y\n", encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "build")
            git(root, "checkout", "-q", "main")
            git(root, "merge", "-q", "--no-ff", "-m", "merge SPEC-1", "spec/SPEC-1")
            if learn:  # Learn, after the merge, records the drift
                (root / "specs/SPEC-1.md").write_text(self.spec(extra) + f"\n## Learn\n\n{learn}\n", encoding="utf-8")
                git(root, "commit", "-qam", "learn")
            from aidd.kernel import documents

            data, _ = documents.split_front_matter(self.spec(extra), "SPEC-1")
            return living_work.merged_drift_warnings(root / "specs/SPEC-1.md", data, root)

    def test_a_merge_outside_the_plan_warns_unless_the_plan_changed(self):
        revised = 'revisions: [{why: "scope grew", at: "2026-11-09T10:00:00Z", by: "J <j@example.com>"}]\n'
        cases = [
            ("inside the scope", ["src/app/a.py"], "", 0),
            ("outside the scope", ["src/app/a.py", "src/other/b.py"], "", 1),
            ("the changelog", ["CHANGELOG.md"], "", 0),
            ("outside, after spec.revise", ["src/other/b.py"], revised, 0),
        ]
        for name, files, extra, n in cases:
            with self.subTest(name):
                self.assertEqual(len(self.merged(files, extra)), n)

    def test_a_merge_of_several_specs_reads_each_file_against_every_plan(self):
        files = ["src/app/a.py", "src/other/b.py", "src/third/c.py"]
        cases = [
            ("no second Spec", "", ["src/other/b.py", "src/third/c.py"]),
            ("the second plan names one file", "src/other/**", ["src/third/c.py"]),
            ("the second plan names every file", "src/**", []),
            ("the second plan names none of them", "docs/**", ["src/other/b.py", "src/third/c.py"]),
        ]
        for name, also, drifted in cases:
            with self.subTest(name):
                found = self.merged(files, also=also)
                self.assertEqual([f for f in files if any(f" changed {f}," in w for w in found)], drifted)

    def test_learn_that_names_the_file_clears_the_drift(self):
        files = ["src/other/b.py", "src/third/c.py"]
        cases = [
            ("Learn names one", "`src/other/b.py` changed too, because the plan missed a caller.", 1),
            ("Learn names both", "src/other/b.py and src/third/c.py changed beside the plan.", 0),
            ("Learn names neither", "The plan held.", 2),
            ("Learn names longer paths that hold them", "`src/other/b.pyc` and `lib/src/third/c.py` changed.", 2),
            ("Learn ends a sentence with the path", "It changed src/other/b.py. And src/third/c.py, too.", 0),
        ]
        for name, learn, n in cases:
            with self.subTest(name):
                self.assertEqual(len(self.merged(files, learn=learn)), n)


if __name__ == "__main__":
    unittest.main()
