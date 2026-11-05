"""Intent agreement, the gate before Specify: its risk rule asks, every harness that can hold its command asks at it,
`aidd validate` fails closed on an agreement no commit records, and a later change to the slices or the goal warns. And
plan drift once a Spec merged: a merge that changed files its plan never names warns."""

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import config
from aidd.config import profile_data
from aidd.kernel import documents
from aidd.risk import commands, harness_rules, rules, suggestions
from aidd.workitems import intent_checks, living_work

# One pattern holds each form a commit records an agreement in: a message or `--trailer "Agreed-by: ..."`, and git's `key=value` form.
AGREED = ("git commit *Agreed-by*",)


def intent(extra: str = "", slices: str = "[{id: SPEC-1, title: one}]") -> str:
    return f'---\naidd_version: "1.0.0"\ntype: intent\nid: INTENT-1\ntitle: "Plan"\ngoal: "g by 2027-01-01"\n{extra}slices: {slices}\n---\n\n## Problem\n'


class AgreementRuleTests(unittest.TestCase):
    def test_intent_agree_asks_in_every_profile_and_is_never_suggested_lower(self):
        for profile in profile_data.profiles()["profiles"]:
            with self.subTest(profile=profile):
                rs = rules.rule_set(config.load_text(f'aidd_version: "1.0.0"\nprofile: {profile}\n'))
                self.assertEqual(rules.level_of(rs, "intent.agree")[0], "ask")
        self.assertIn(("intent.agree", None, None), suggestions.DECISION_POINTS)

    def test_the_commit_that_records_an_agreement_asks(self):
        rs = rules.rule_set(None)
        cases = [
            ('git commit -m "plan" --trailer "Agreed-by: J <j@example.com>"', "ask"),
            ('git commit -m "Agreed-by: J <j@example.com>"', "ask"),
            ('git commit -m "plan" --trailer "Agreed-by=J <j@example.com>"', "ask"),
            ('git commit -m "plan"', "allow"),
        ]
        for line, level in cases:
            with self.subTest(line=line):
                self.assertEqual(commands.command_level(rs, line, cwd=None)["level"], level)

    def test_each_harness_asks_at_it_or_names_it_left_to_the_skill(self):
        patterns = harness_rules.harness_patterns(rules.rule_set(None), "main")
        for pattern in AGREED:
            self.assertIn(pattern, patterns)
        for fmt, form in harness_rules.FORMATS.items():
            with self.subTest(format=fmt):
                if form.match == "words":
                    # A leading-words format cannot hold a trailer, and asking before every commit would slow every change.
                    self.assertEqual(harness_rules.unwritten(fmt, list(AGREED)), list(AGREED))
                    self.assertEqual(harness_rules.widened(fmt, list(AGREED)), {})
                else:
                    self.assertEqual(harness_rules.unwritten(fmt, list(AGREED)), [])
                    self.assertEqual(sum("Agreed-by" in e for e in harness_rules._entries(fmt, list(AGREED))), 1)


@unittest.skipUnless(shutil.which("git"), "git is required")
class DoctorSaysWhereNoPromptAsksTests(unittest.TestCase):
    def test_doctor_names_the_harnesses_with_no_prompt_for_an_agreement(self):
        from aidd.setup import adoption, doctor_checks

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git(root, "init", "-q", "-b", "main")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["codex", "claude-code"]))
            lines = {key: [m for _, m in doctor_checks.harness_checks(root, [key]) if "`intent.agree`" in m] for key in ("codex", "claude-code")}
        self.assertEqual(len(lines["codex"]), 1, lines)
        self.assertIn("no prompt for `intent.agree`, so the skill asks", lines["codex"][0])
        self.assertEqual(len(lines["claude-code"]), 1, lines)
        self.assertIn("heredoc", lines["claude-code"][0], "its prompt matches the command text, which a heredoc message hides")
        self.assertIn("`Agreed-by` trailer", lines["claude-code"][0])
        self.assertNotIn("no prompt", lines["claude-code"][0], "it has a prompt, and the note says what the prompt misses")


@unittest.skipUnless(shutil.which("git"), "git is required")
class AgreementCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "t@example.com")
        git(self.root, "config", "user.name", "T")
        self.path = self.root / "specs" / "INTENT-1.md"
        self.path.parent.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def warnings(self, text: str) -> list[str]:
        self.path.write_text(text, encoding="utf-8")
        from aidd.kernel import documents

        data, _ = documents.split_front_matter(text, "INTENT-1")
        return intent_checks.agreement_warnings(self.path, data, self.root)

    def test_an_agreement_no_commit_records_fails_closed(self):
        agreed = 'agreed_by: "J <j@example.com>"\nagreed_at: "2026-11-10T09:12:00Z"\n'
        self.assertEqual(self.warnings(intent()), [])  # not agreed yet: `aidd status` asks for it
        self.assertEqual(len(self.warnings(intent(agreed))), 1)  # written, never committed
        self.assertEqual(len(intent_checks.agreement_warnings(self.path, {"type": "intent", "agreed_at": "2026-11-10T09:12:00Z"}, None)), 1)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "agree", "--trailer", "Agreed-by: J <j@example.com>")
        cases = [
            ("as agreed", intent(agreed), 0),
            ("a slice renamed", intent(agreed, "[{id: SPEC-1, title: renamed}]"), 0),
            ("a slice added", intent(agreed, "[{id: SPEC-1, title: one}, {id: SPEC-2, title: two}]"), 1),
            ("a slice removed", intent(agreed, "[{id: SPEC-2, title: two}]"), 1),
            ("the goal changed", intent(agreed).replace("g by 2027", "h by 2027"), 1),
        ]
        for name, text, n in cases:
            with self.subTest(name):
                self.assertEqual(len(self.warnings(text)), n)

    def test_the_agreement_commit_is_found_by_the_parsed_value_in_any_yaml_spelling(self):
        """A single-quoted value and a trailing comment are the same `agreed_at`, so the right trailer agrees in each."""
        at = "2026-11-10T09:12:00Z"
        who = 'agreed_by: "J <j@example.com>"\n'
        spellings = {
            "single quotes": f"agreed_at: '{at}'\n",
            "a trailing comment": f'agreed_at: "{at}"  # said in the chat\n',
            "single quotes and a comment": f"agreed_at: '{at}' # said in the chat\n",
        }
        for name, line in spellings.items():
            with self.subTest(name):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                root = Path(tmp.name)
                git(root, "init", "-q", "-b", "main")
                git(root, "config", "user.email", "t@example.com")
                git(root, "config", "user.name", "T")
                (root / "specs").mkdir()
                path = root / "specs" / "INTENT-1.md"
                path.write_text(intent(who + line), encoding="utf-8")
                git(root, "add", "-A")
                git(root, "commit", "-qm", "agree", "--trailer", "Agreed-by: J <j@example.com>")
                data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), "INTENT-1")
                self.assertEqual(intent_checks.agreement_warnings(path, data, root), [])
                # A slice added after the agreement still warns in the same spelling.
                path.write_text(intent(who + line, "[{id: SPEC-1, title: one}, {id: SPEC-2, title: two}]"), encoding="utf-8")
                git(root, "add", "-A")
                git(root, "commit", "-qm", "a slice")
                data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), "INTENT-1")
                self.assertEqual(len(intent_checks.agreement_warnings(path, data, root)), 1)

    def test_a_person_put_in_the_file_after_an_agent_was_committed_with_that_persons_trailer_is_no_agreement(self):
        """The commit that first holds `agreed_at` must hold the same `agreed_by` as the file: a trailer alone is not the agreement."""
        at = "2026-11-10T09:12:00Z"
        agent = f'agreed_by: "agent:claude-code/x"\nagreed_at: "{at}"\n'
        person = f'agreed_by: "J <j@example.com>"\nagreed_at: "{at}"\n'
        self.path.write_text(intent(agent), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "agree", "--trailer", "Agreed-by: J <j@example.com>")
        self.assertEqual(len(self.warnings(intent(person))), 1)
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "name the person", "--trailer", "Agreed-by: J <j@example.com>")
        self.assertEqual(len(self.warnings(intent(person))), 1, "the later commit does not make the first one a person's")

    def test_a_commit_with_no_trailer_that_first_wrote_the_value_in_a_comment_spelling_is_no_agreement(self):
        at = "2026-11-10T09:12:00Z"
        who = 'agreed_by: "J <j@example.com>"\n'
        line = f"agreed_at: '{at}'  # said in the chat\n"
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.email", "t@example.com")
        git(root, "config", "user.name", "T")
        (root / "specs").mkdir()
        path = root / "specs" / "INTENT-1.md"
        path.write_text(intent(who + line), encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "agree")
        data, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), "INTENT-1")
        self.assertEqual(len(intent_checks.agreement_warnings(path, data, root)), 1)

    def test_status_waits_for_an_agreement_a_person_made_and_a_commit_holds(self):
        from helpers import open_work

        from aidd.workitems import validation

        at = "2026-11-10T09:12:00Z"
        person = f'agreed_by: "J <j@example.com>"\nagreed_at: "{at}"\n'
        agent = f'agreed_by: "agent:claude-code/x"\nagreed_at: "{at}"\n'
        bot = f'agreed_by: "Bot <noreply@anthropic.com>"\nagreed_at: "{at}"\n'
        free = f'agreed_by: "the person"\nagreed_at: "{at}"\n'
        two = "[{id: SPEC-1, title: one}, {id: SPEC-2, title: two}]"
        by = "Agreed-by: J <j@example.com>"
        delegated = [by, "Decided-by: agent:claude-code/delegate", "Delegation: " + "a" * 40]

        def run(*steps: tuple[str, list[str] | None]) -> dict:
            """Commit each (text, trailers) in turn in a new repository, or only write it when the trailers are None;
            the last text is the file on disk. Returns the Intent's next step."""
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                git(root, "init", "-q", "-b", "main")
                git(root, "config", "user.email", "t@example.com")
                git(root, "config", "user.name", "T")
                (root / "specs").mkdir()
                for text, trailers in steps:
                    (root / "specs" / "INTENT-1.md").write_text(text, encoding="utf-8")
                    if trailers is not None:
                        git(root, "add", "-A")
                        git(root, "commit", "-qm", "the plan", *[a for t in trailers for a in ("--trailer", t)])
                return next(i for i in open_work(root) if i["id"] == "INTENT-1")["next"]

        cases = [
            ("not agreed", [(intent(), [])], "intent.agree"),
            ("agreed, not committed", [(intent(), []), (intent(person), None)], "intent.agree"),
            ("agreed and committed with the trailer", [(intent(person), [by])], "intent.slice"),
            ("agreed, committed with no trailer", [(intent(person), [])], "intent.agree"),
            ("agreed, a trailer for someone else", [(intent(person), ["Agreed-by: K <k@example.com>"])], "intent.agree"),
            ("agreed, the trailer in another case", [(intent(person), ["agreed-by: J <j@example.com>"])], "intent.agree"),
            ("agreed through a delegate's trailers", [(intent(person), delegated)], "intent.agree"),
            ("an agent's, committed", [(intent(agent), ["Agreed-by: agent:claude-code/x"])], "intent.agree"),
            ("an agent's, then a person's in the file only", [(intent(agent), ["Agreed-by: agent:claude-code/x"]), (intent(person), None)], "intent.agree"),
            ("a bot's address in Name <email>", [(intent(bot), ["Agreed-by: Bot <noreply@anthropic.com>"])], "intent.agree"),
            ("free text for the person", [(intent(free), ["Agreed-by: the person"])], "intent.agree"),
            (
                "agreed_at only in other text of an earlier commit",
                [(intent(f'context: "see {at}"\n'), []), (intent(person + f'context: "see {at}"\n'), None)],
                "intent.agree",
            ),
            ("agreed_at that is no RFC 3339 time", [(intent('agreed_by: "J <j@example.com>"\nagreed_at: "yes"\n'), [by])], "intent.agree"),
            ("a slice added after the agreement", [(intent(person), [by]), (intent(person, two), [])], "intent.agree"),
            ("a slice added in the file only", [(intent(person), [by]), (intent(person, two), None)], "intent.agree"),
            ("a goal changed after the agreement", [(intent(person), [by]), (intent(person).replace("g by", "h by"), [])], "intent.agree"),
            ("a slice added in a commit that repeats the time", [(intent(person), [by]), (intent(person + f'context: "{at}"\n', two), [])], "intent.agree"),
        ]
        for name, steps, code in cases:
            with self.subTest(name):
                self.assertEqual(run(*steps)["code"], code)
        # A slice added after the agreement is held, the agreed one may still start, and the step says so.
        held = run((intent(person), [by]), (intent(person, two), []))["what"]
        self.assertIn("SPEC-2", held)
        self.assertIn("SPEC-1", held)
        # The one-file check fails an agent's agreement, as the repository-wide one does.
        self.path.write_text(intent(agent), encoding="utf-8")
        self.assertTrue(any("agreed_by" in e and not e.startswith("warning") for e in validation.validate_file(self.path)))

    def test_an_agent_cannot_agree(self):
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
                found = intent_checks.agreement_problems("specs/INTENT-1.md", {"type": "intent", "agreed_by": who, "agreed_at": "2026-11-10T09:12:00Z"})
                self.assertEqual(
                    (len([f for f in found if not f.startswith("warning")]), len([f for f in found if f.startswith("warning")])), (errors, warnings)
                )


@unittest.skipUnless(shutil.which("git"), "git is required")
class MergedDriftTests(unittest.TestCase):
    def spec(self, extra: str = "") -> str:
        return (
            '---\naidd_version: "1.0.0"\ntype: spec\nid: SPEC-1\ntitle: t\nowner_team: core\nchange_type: feat\nroute: normal\n'
            f"status: done\n{extra}tasks:\n  - id: SPEC-1-T1\n    title: t\n    scope: [src/app/**]\n---\n"
        )

    def merged(self, files: list[str], extra: str = "", learn: str = "") -> list[str]:
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
