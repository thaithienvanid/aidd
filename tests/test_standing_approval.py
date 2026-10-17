"""A person's own words are the decision: what they type is recorded (`approve SPEC-1`, `ship it`), and a standing
approval (`approve all`) lets the agent record each approval it covers until they stop it. Only the person starts one,
and the agent never acts on a yes it only read."""

import contextlib
import datetime as dt
import json
import os
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, git
from test_local_first import SPEC_FIELDS, at_a_terminal
from test_platform_approve import FakeGitHub

from aidd.autopilot import engine
from aidd.cli import app
from aidd.cli.commands import confirmations
from aidd.cli.commands import standing as cli_standing
from aidd.cli.commands import typed_decisions
from aidd.guard import approval_commands, decision_files, edit_check, verdicts
from aidd.kernel import documents
from aidd.platforms import github, local_ship
from aidd.workitems import approval_ledger

T0 = dt.datetime(2026, 10, 7, 9, 0, tzinfo=dt.UTC)
AGENT = {"AIDD_AGENT": "1"}  # a shell an agent started, whatever harness runs this suite
NOT_AN_AGENT = {v: "" for v in local_ship.AGENT_ENV}  # a person's own terminal
CONFIG = (
    'aidd_version: "1.0.0"\nprofile: {profile}\nowners:\n  approvers: ["email:me@example.com"]\ntests:\n  - name: unit\n    command: [python3, -m, unittest]\n'
)


class TypedTests(unittest.TestCase):
    def test_what_a_prompt_decides(self):
        cases = {
            "approve SPEC-1": ("spec", ["SPEC-1"]),
            "/aidd approve spec-1 and SPEC-4": ("spec", ["SPEC-1", "SPEC-4"]),
            "approve": ("spec", []),
            "approve the merge": ("merge", []),
            "ship it": ("ship", []),
            "/aidd ship": ("ship", []),
            "approve all": ("all", []),
            "automate": ("all", []),
            "I approve all, but major": ("all", ["but-major"]),
            "stop approving": ("stop", []),
            "/aidd approve stop": ("stop", []),
        }
        for text, decided in cases.items():
            self.assertEqual(typed_decisions.parse(text), decided, text)
        for text in ("approve the design of the button", "please approve SPEC-1", "ship the release notes", "automate the deploy", "fix the bug"):
            self.assertIsNone(typed_decisions.parse(text), text)


@unittest.skipUnless(shutil.which("git"), "git is required")
class LedgerAndGuardTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)
        Path(self.root, ".aidd").mkdir()
        Path(self.root, ".aidd", "config.yaml").write_text(CONFIG.format(profile="solo"), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "adopt")

    def record(self, line: str) -> None:
        approval_ledger.record_local_approval(line, self.root)

    def test_the_newest_standing_record_of_a_listed_approver_holds_until_stopped_or_past_its_date(self):
        approvers = ["email:me@example.com"]
        self.assertIsNone(approval_ledger.live_standing(self.root, approvers))
        self.record(approval_ledger.standing_line("all-but-major"))
        standing = approval_ledger.live_standing(self.root, approvers)
        self.assertEqual((standing or {}).get("scope"), "all-but-major")
        self.assertTrue(approval_ledger.standing_covers(standing, "normal"))
        self.assertFalse(approval_ledger.standing_covers(standing, "major"))
        self.assertIsNone(approval_ledger.live_standing(self.root, ["email:someone@else.com"]))  # not an Approver's
        self.record(approval_ledger.standing_line("stop"))
        self.assertIsNone(approval_ledger.live_standing(self.root, approvers))
        self.record(approval_ledger.standing_line("all", until="2026-01-01"))
        self.assertIsNone(approval_ledger.live_standing(self.root, approvers, today=dt.date(2026, 1, 2)))
        self.assertTrue(approval_ledger.standing_covers(approval_ledger.live_standing(self.root, approvers, today=dt.date(2026, 1, 1)), "major"))

    def test_only_a_listed_approvers_record_counts_signed_where_approvals_must_be_and_anyone_stops_one(self):
        approvers = ["email:me@example.com"]
        self.record(approval_ledger.standing_line("all"))
        head = git(self.root, "rev-parse", "HEAD")
        self.record(approval_ledger.ship_said_line(head))
        self.assertIsNone(approval_ledger.live_standing(self.root))  # the Approvers unknown: nobody's counts
        self.assertFalse(approval_ledger.ship_said(self.root, head))
        self.assertIsNotNone(approval_ledger.live_standing(self.root, ["@me"] + approvers))
        # Under `local_approvals: signed` with no signers file on the base branch, no unsigned record counts.
        self.assertIsNone(approval_ledger.live_standing(self.root, approvers, require_signed=True))
        self.assertFalse(approval_ledger.ship_said(self.root, head, approvers, require_signed=True))
        git(self.root, "config", "user.email", "someone@else.com")
        self.record(approval_ledger.standing_line("stop"))  # not an Approver, and still it ends it
        self.assertIsNone(approval_ledger.live_standing(self.root, approvers))
        self.record(approval_ledger.standing_line("all"))
        self.assertIsNone(approval_ledger.live_standing(self.root, approvers))  # but never starts one

    def test_where_approvers_are_logins_the_record_names_the_persons_login(self):
        logins = ["@thaithienvanid"]
        self.record(approval_ledger.standing_line("all"))
        self.assertIsNone(approval_ledger.live_standing(self.root, logins), "an email never matches a login")
        self.record(approval_ledger.with_login(approval_ledger.standing_line("all"), "thaithienvanid"))
        self.assertEqual((approval_ledger.live_standing(self.root, logins) or {}).get("scope"), "all")
        # A platform repository (a remote and the gate's workflow) whose Approvers are logins.
        Path(self.root, ".github", "workflows").mkdir(parents=True)
        Path(self.root, ".github", "workflows", "aidd-gate.yml").write_text("name: aidd\n", encoding="utf-8")
        git(self.root, "remote", "add", "origin", "https://github.com/acme/shop.git")
        cfg_path = Path(self.root, ".aidd", "config.yaml")
        cfg_path.write_text(cfg_path.read_text(encoding="utf-8").replace('["email:me@example.com"]', '["@thaithienvanid"]'), encoding="utf-8")
        with contextlib.chdir(self.root):
            with mock.patch.object(github, "_person_client", return_value=FakeGitHub("thaithienvanid", [])):
                self.assertEqual(confirmations.standing_identity(), ("thaithienvanid", None))
            with mock.patch.object(github, "_person_client", return_value=FakeGitHub("someone-else", [])):
                login, problem = confirmations.standing_identity()
                self.assertIsNone(login)
                self.assertIn("it would never count here", problem or "")
                self.assertIn("gh auth login", problem or "")

    def test_doctor_names_what_stands_behind_a_standing_approval(self):
        from aidd import config
        from aidd.setup import doctor_checks

        cfg = config.load_file(config.CONFIG_PATH, self.root)
        self.assertEqual(doctor_checks.standing_rails(Path(self.root), cfg), [])
        self.record(approval_ledger.standing_line("all"))
        found = doctor_checks.standing_rails(Path(self.root), cfg)
        self.assertEqual([level for level, _ in found], ["info", "warn"])
        self.assertIn("no risk_rules of its own", found[1][1])

    def test_the_agent_never_skips_the_cooloff_or_runs_the_hook_itself(self):
        self.record(approval_ledger.standing_line("all"))
        for command in ("aidd approve merge --skip-cooloff", "aidd ship --skip-cooloff", "aidd hook prompt-submit"):
            self.assertIsNotNone(approval_commands.forbidden_action(command, self.root), command)

    def test_the_guard_lets_the_agent_approve_only_what_the_person_already_said(self):
        for command in ("aidd approve spec SPEC-1", "aidd approve merge", "aidd ship", "aidd approve all"):
            self.assertIsNotNone(approval_commands.forbidden_action(command, self.root), command)
        self.assertIsNone(approval_commands.forbidden_action("aidd approve stop", self.root))  # it only takes back
        self.record(approval_ledger.standing_line("all"))
        for command in ("aidd approve spec SPEC-1", "aidd approve merge", "aidd ship --squash", "uvx aidd approve spec specs/SPEC-1.md"):
            self.assertIsNone(approval_commands.forbidden_action(command, self.root), command)
        # Starting one is the person's alone, and a claim that someone confirmed elsewhere is never the agent's.
        for command in ("aidd approve all", "aidd approve spec SPEC-1 --confirmed abc", "aidd ship --confirmed abc"):
            why = approval_commands.forbidden_action(command, self.root)
            self.assertIn(verdicts.APPROVE_IN_A_DIALOG, why or "", command)

    def test_a_typed_ship_lets_the_agent_ship_and_approve_exactly_that_head(self):
        """A "ship it" is a standing approval for one change: its Merge approval too (on a platform, where nothing runs
        `aidd ship`), never a Spec approval, a standing approval, or a claim that the person confirmed elsewhere."""
        head = git(self.root, "rev-parse", "HEAD")
        self.record(approval_ledger.ship_said_line(head))
        self.assertTrue(approval_ledger.ship_said(self.root, head, ["email:me@example.com"]))
        self.assertIsNone(approval_commands.forbidden_action("aidd ship", self.root))
        self.assertIsNone(approval_commands.forbidden_action("aidd approve merge", self.root))
        for still in ("aidd approve spec SPEC-1", "aidd approve all", f"aidd approve merge --confirmed {head}"):
            with self.subTest(still=still):
                self.assertIsNotNone(approval_commands.forbidden_action(still, self.root))
        git(self.root, "commit", "-q", "--allow-empty", "-m", "a new head")
        self.assertIsNotNone(approval_commands.forbidden_action("aidd ship", self.root))

    def test_an_agent_never_loosens_the_config(self):
        rel, team = ".aidd/config.yaml", CONFIG.format(profile="team")
        enforced = team.replace("profile: team", "profile: team\nmode: enforce")
        loosen = {
            "from team to 'solo'": (team, CONFIG.format(profile="solo")),
            "off `enforce`": (enforced, team.replace("profile: team", "profile: team\nmode: advisory")),
            "`gates`": (team, team + "gates:\n  approvals: {normal: 2}\n"),
            "`components`": (team, team + "components:\n  loop: false\n"),
            "does not parse": (team, team + "profile: ["),
        }
        for what, (old, new) in loosen.items():
            with self.subTest(what):
                self.assertIn(what, decision_files.config_loosening(rel, old, new) or "")
                decision, reason = edit_check.check_edit(self.root, rel, None, old, new)
                self.assertEqual(decision, "deny")
                self.assertIn("never because someone said yes in the chat", reason)
        self.assertIsNone(decision_files.config_loosening(rel, team, CONFIG.format(profile="org")))
        self.assertIsNone(decision_files.config_loosening(rel, CONFIG.format(profile="7"), team))
        self.assertIsNone(decision_files.config_loosening(rel, team, team + "risk_rules: []\n"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class LoopTests(unittest.TestCase):
    """A local-first solo repository that asks for Spec approval on normal changes: the agent's whole loop, from Spec
    to main, under the person's standing approval or their typed words."""

    @classmethod
    def setUpClass(cls):
        cls.template_dir = tempfile.TemporaryDirectory()
        cls.template = str(Path(cls.template_dir.name) / "shop")
        os.mkdir(cls.template)
        git(cls.template, "init", "-q", "-b", "main")
        for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(cls.template, "config", k, v)
        for rel, text in {
            "app/__init__.py": "",
            "tests/__init__.py": "",
            "app/cart.py": "def total(items):\n    return sum(items)\n",
            "tests/test_cart.py": "import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n",
        }.items():
            Path(cls.template, rel).parent.mkdir(parents=True, exist_ok=True)
            Path(cls.template, rel).write_text(text, encoding="utf-8")
        git(cls.template, "add", "-A")
        git(cls.template, "commit", "-qm", "scaffold")
        suite = f"{shlex.quote(sys.executable)} -m unittest"
        run = aidd_subprocess(
            "init", "--profile", "solo", "--approvers", "email:me@example.com", "--test", suite, "--ci", "none", "--harness", "none", cwd=cls.template
        )
        assert run.returncode == 0, run.stdout + run.stderr
        with open(Path(cls.template, ".aidd", "config.yaml"), "a", encoding="utf-8") as fh:
            fh.write("\ngates:\n  spec_approval_routes: [normal, major]\n")
        git(cls.template, "add", "-A")
        git(cls.template, "commit", "-qm", "chore: adopt aidd")

    @classmethod
    def tearDownClass(cls):
        cls.template_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name) / "shop")
        shutil.copytree(self.template, self.root, symlinks=True)

    def aidd(self, *args, expect=0):
        """`aidd <args>` in a shell an agent started, which has no terminal."""
        run = aidd_subprocess(*args, cwd=self.root, env={**os.environ, **AGENT})
        self.assertEqual(run.returncode, expect, f"aidd {' '.join(args)}\n{run.stdout}\n{run.stderr}")
        return run

    def as_person(self, *argv):
        """`aidd <argv>` typed by the person at their own terminal, answering yes."""
        with contextlib.chdir(self.root), mock.patch.dict(os.environ, NOT_AN_AGENT), at_a_terminal() as (out, err, _):
            code = app.main(list(argv))
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        return out.getvalue()

    def main_log(self):
        return git(self.root, "log", "--format=%s", "main").splitlines()

    def spec(self, *, route: str = "normal") -> None:
        """On a new branch: SPEC-1 and its failing test, committed."""
        git(self.root, "switch", "-qc", "discount")
        self.aidd("new", "spec", "SPEC-1", "--title", "Apply a percentage discount", "--type", "feat")
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8").replace("route: normal", f"route: {route}", 1)
        if route == "major":
            text = text.replace("\ntasks:", '\nobserve:\n  window: "24h"\n  signals: checkout totals\n  rollback_trigger: a wrong total\n\ntasks:', 1)
        for old, new in SPEC_FIELDS.items():
            text = text.replace(old, new)
        spec.write_text(text, encoding="utf-8")
        Path(self.root, "tests/test_discount.py").write_text(
            "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n",
            encoding="utf-8",
        )
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "spec: SPEC-1 and its test\n\nAssisted-by: claude-code/claude-opus-5-5")

    def build(self) -> None:
        Path(self.root, "app/discount.py").write_text("def discount(total, percent):\n    return total - total * percent // 100\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "feat: add discount()\n\nAssisted-by: claude-code/claude-opus-5-5")
        self.aidd("test", "--base", "main")

    def codes(self) -> list[str]:
        return [s["code"] for s in json.loads(self.aidd("list", "--json").stdout)["steps"] if s.get("id") == "SPEC-1"]

    def test_only_the_person_starts_a_standing_approval(self):
        refused = self.aidd("approve", "all", expect=1)
        self.assertIn("an agent started this shell", refused.stderr)
        self.assertIsNone(approval_ledger.live_standing(self.root))
        self.assertIn("Approving every Spec approval and Merge approval for you until you stop it", self.as_person("approve", "all"))

    def test_under_a_standing_approval_the_agent_takes_a_change_from_spec_to_main(self):
        self.as_person("approve", "all")
        self.spec()
        self.assertEqual(self.codes(), ["spec.approve_standing"])
        approved = self.aidd("approve", "spec", "specs/SPEC-1.md")
        self.assertIn("Approved SPEC-1 under your standing approval", approved.stdout)
        self.build()
        self.assertEqual(self.codes(), ["spec.ship_ready"])
        shipped = self.aidd("ship", "--squash")
        self.assertIn("your standing approval", shipped.stdout)
        self.assertEqual(self.main_log(), ["feat: Apply a percentage discount (SPEC-1)", "chore: adopt aidd", "scaffold"])
        self.assertIn("Aidd-Confirmed-In: standing:", git(self.root, "log", "--format=%B", approval_ledger.APPROVALS_REF))

    def test_but_major_leaves_a_major_change_to_the_person(self):
        self.as_person("approve", "all", "--but-major")
        self.spec(route="major")
        self.assertEqual(self.codes(), ["spec.spec_approval"])
        refused = self.aidd("approve", "spec", "specs/SPEC-1.md", expect=1)
        self.assertIn("an agent started this shell", refused.stderr)

    def test_but_major_covers_the_route_the_tasks_need_not_the_one_the_spec_declares(self):
        self.as_person("approve", "all", "--but-major")
        self.spec()
        spec = Path(self.root, "specs/SPEC-1.md")
        spec.write_text(spec.read_text(encoding="utf-8").replace("scope: [app/discount.py]", "scope: [app/discount.py, .aidd/config.yaml]"), encoding="utf-8")
        git(self.root, "commit", "-qam", "spec: SPEC-1 touches the config")
        self.assertIn(".aidd/config.yaml", spec.read_text(encoding="utf-8"))
        with contextlib.chdir(self.root):
            data = documents.split_front_matter(spec.read_text(encoding="utf-8"), "SPEC-1.md")[0]
            self.assertEqual((data["route"], cli_standing.spec_route(data)), ("normal", "major"))
        refused = self.aidd("approve", "spec", "specs/SPEC-1.md", expect=1)
        self.assertIn("an agent started this shell", refused.stderr)

    def test_a_typed_approve_all_through_the_prompt_hook_starts_nothing(self):
        said = typed_decisions.record("approve all", self.root)
        self.assertIn("`approve_all`", said or "")
        self.assertIsNone(approval_ledger.live_standing(self.root, ["email:me@example.com"]))

    def test_stopping_hands_every_approval_back(self):
        self.as_person("approve", "all")
        self.aidd("approve", "stop")
        self.spec()
        self.assertEqual(self.codes(), ["spec.spec_approval"])

    def test_typed_words_are_recorded_by_the_prompt_hook_and_ship_lands_that_head(self):
        self.spec()
        said = typed_decisions.record("approve SPEC-1", self.root)
        self.assertIn("Approved SPEC-1", said or "")
        self.assertEqual(self.codes(), ["spec.ready"])  # no longer waits for approval
        self.assertIn("Aidd-Confirmed-In: prompt", git(self.root, "log", "-1", "--format=%B", approval_ledger.APPROVALS_REF))
        self.build()
        self.assertIsNotNone(approval_commands.forbidden_action("aidd ship", self.root))  # nobody said ship yet
        said = typed_decisions.record("ship it", self.root)
        self.assertIn("run `aidd ship`", said or "")
        shipped = self.aidd("ship")
        self.assertIn("you said to ship", shipped.stdout)
        self.assertEqual(self.main_log()[0], "feat: Apply a percentage discount (SPEC-1)")
        self.assertIsNone(typed_decisions.record("fix the bug", self.root))


class AutopilotTests(unittest.TestCase):
    LEASE = {"session_id": "s", "work": "all", "by": "a", "timebox": "2h", "started_at": "2026-10-07T09:00:00Z", "expires_at": "2026-10-07T11:00:00Z"}

    def decide(self, step: dict, *results: tuple[str, str]) -> dict:
        journal = [
            {"session_id": "s", "at": f"2026-10-07T09:0{n}Z", "spec": "SPEC-1", "code": c, "result": r, "head": "h1"} for n, (c, r) in enumerate(results)
        ]
        i = engine.Inputs(steps=[step], lease=self.LEASE, cleared={"SPEC-1"}, journal=journal, heads={"SPEC-1": "h1"}, now=T0)
        return engine.decide(i)

    def test_it_records_the_spec_approval_then_verifies_reviews_and_ships(self):
        approve = {"code": "spec.approve_standing", "id": "SPEC-1", "who": "agent", "what": "w", "how": "h", "where": "specs/SPEC-1.md"}
        run = self.decide(approve)
        self.assertEqual((run["action"], run["command"], run["args"]), ("run", "aidd approve spec", "specs/SPEC-1.md"))
        ship = {"code": "spec.ship_ready", "id": "SPEC-1", "who": "agent", "what": "w", "how": "h", "where": "specs/SPEC-1.md"}
        self.assertEqual(self.decide(ship)["command"], "/aidd-team:verify")
        self.assertEqual(self.decide(ship, ("spec.verify", "ok"))["command"], "/aidd-team:review")
        shipping = self.decide(ship, ("spec.verify", "ok"), ("spec.review", "ok"))
        self.assertEqual((shipping["code"], shipping["command"]), ("spec.ship_ready", "aidd ship"))
        self.assertNotIn("args", shipping)


if __name__ == "__main__":
    unittest.main()
