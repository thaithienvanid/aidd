"""A founder's first days with aidd, local-first and solo.

Each test names the Acceptance item it proves. The journeys run the real CLI on throwaway repositories: the person's
steps (`aidd approve`, `aidd ship`) in-process at a pretend terminal, the agent's in a child process with no terminal.
"""

import contextlib
import copy
import json
import re
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, aidd_subprocess, git, make_repo
from test_local_first import SPEC_FIELDS, at_a_terminal

from aidd.evals import examples
from aidd.guard import command_check
from aidd.guard import approval_commands
from aidd.cli import app
from aidd.cli import parser as cli_parser
from aidd.tracking import next_steps
from aidd.setup import detection
from aidd.setup import doctor_checks
from aidd.setup import adoption
from aidd.platforms import local_context
from aidd.gate import routing
from aidd import config
from aidd.workitems import approval_ledger
from aidd.config import identities
from aidd.gate import decide

EMAIL = "me@example.com"
PY = shlex.quote(sys.executable)
DISCOUNT_TEST = (
    "import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n"
    "    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n"
)
# Secret-shaped strings, built at run time so no scanner mistakes this file for a leak. The AWS id is AWS's own
# documentation example.
AWS_ID = "AKIA" + "IOSFODNN7EXAMPLE"
STRIPE_KEY = "sk_" + "live_" + "4eC39HqLyjWDarjtT1zdp7dc"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The body of a Markdown section, up to the next heading of the same or a higher level."""
    level = len(heading) - len(heading.lstrip("#"))
    start = text.index(heading + "\n")
    rest = text[start + len(heading) + 1 :]
    m = re.search(rf"(?m)^#{{1,{level}}} ", rest)
    return rest[: m.start()] if m else rest


class _Repo(unittest.TestCase):
    """A throwaway git repository per test, with helpers for the agent's and the person's commands."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(Path(self.tmp.name).resolve() / "repo")
        Path(self.root).mkdir()
        git(self.root, "init", "-q", "-b", "main")
        for k, v in (("user.email", EMAIL), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(self.root, "config", k, v)

    def write(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            Path(self.root, rel).parent.mkdir(parents=True, exist_ok=True)
            Path(self.root, rel).write_text(text, encoding="utf-8")

    def commit(self, message: str, files: dict[str, str] | None = None) -> str:
        self.write(files or {})
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", message)
        return git(self.root, "rev-parse", "HEAD")

    def aidd(self, *args, expect: int | None = 0):
        """The agent's `aidd <args>`: a child process with no terminal."""
        run = aidd_subprocess(*args, cwd=self.root)
        if expect is not None:
            self.assertEqual(run.returncode, expect, f"aidd {' '.join(args)}\n{run.stdout}\n{run.stderr}")
        return run

    def as_person(self, *argv, answer=None):
        """The person's `aidd <argv>` at their own terminal, typing back the code shown: (exit, stdout, stderr)."""
        with contextlib.chdir(self.root), at_a_terminal(answer) as (out, err, _):
            code = app.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def decision(self, **kw):
        with contextlib.chdir(self.root):
            ev = Path(self.root, ".aidd", "evidence", "evidence.json")
            ctx = local_context.build_local_context(repo=self.root, base="main", evidence=str(ev) if ev.is_file() else None, run_policy=False, **kw)
            return ctx, decide(ctx)

    def solo_shop(self, *, init_args: tuple[str, ...] = ()) -> None:
        """A tiny Python shop adopted under solo with local approvals, the setup committed on main as Day 0."""
        self.commit(
            "scaffold",
            {
                ".gitignore": "__pycache__/\n",
                "app/__init__.py": "",
                "tests/__init__.py": "",
                "app/cart.py": "def total(items):\n    return sum(items)\n",
                "tests/test_cart.py": "import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n"
                "    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n",
            },
        )
        args = init_args or ("--approvers", f"email:{EMAIL}")
        self.aidd("init", "--profile", "solo", *args, "--test", f"{PY} -m unittest", "--ci", "none", "--harness", "none")
        self.commit("chore: adopt aidd")

    def discount_spec(self) -> None:
        """On a new branch: SPEC-1 (route normal) and its failing test, committed, as the Quickstart writes them."""
        git(self.root, "switch", "-qc", "discount")
        self.aidd("new", "spec", "SPEC-1", "--title", "Apply a percentage discount", "--type", "feat")
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8")
        for old, new in SPEC_FIELDS.items():
            text = text.replace(old, new)
        spec.write_text(text, encoding="utf-8")
        self.commit("spec: SPEC-1 and its test\n\nAssisted-by: claude-code/claude-opus-5-5", {"tests/test_discount.py": DISCOUNT_TEST})

    def implement(self, body: str = "def discount(total, percent):\n    return total - total * percent // 100\n") -> None:
        self.commit("feat: add discount()\n\nAssisted-by: claude-code/claude-opus-5-5", {"app/discount.py": body})
        self.aidd("test", "--base", "main", expect=None)


# ---- A solo founder's approver is the local git identity ---------------------------------------------------------


class ApproverIdentityTests(_Repo):
    def test_solo_init_names_the_local_git_email(self):
        with mock.patch.object(identities, "operator_login", return_value="you"), mock.patch.object(identities, "operator_email", return_value=EMAIL):
            adoption.init(Path(self.root), adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, harnesses=[]))
        cfg = config.load_file(config.CONFIG_PATH, self.root)
        self.assertIn(f"email:{EMAIL}", cfg.approvers)

    def test_approve_refuses_a_handle_the_local_gate_cannot_match(self):
        self.solo_shop(init_args=("--approvers", "@you"))
        git(self.root, "switch", "-qc", "fix")
        self.commit("fix: cart", {"app/cart.py": "def total(items):\n    return sum(items) or 0\n"})
        self.aidd("describe", "--commit")
        code, _, err = self.as_person("approve", "merge")
        self.assertEqual(code, 1, err)
        self.assertIn(f"email:{EMAIL}", err)
        self.assertIn("owners.approvers", err)
        self.assertEqual(git(self.root, "for-each-ref", approval_ledger.APPROVALS_REF), "")  # nothing recorded

    def test_doctor_warns_when_the_local_git_email_is_not_an_approver(self):
        self.solo_shop(init_args=("--approvers", "@you"))
        warns = [m for level, m in doctor_checks.doctor(Path(self.root)) if level == "warn"]
        self.assertTrue(any(f"email:{EMAIL}" in m and "owners.approvers" in m for m in warns), warns)
        with open(Path(self.root, ".aidd/config.yaml"), encoding="utf-8") as fh:
            text = fh.read()
        Path(self.root, ".aidd/config.yaml").write_text(text.replace('["@you"]', f'["@you", "email:{EMAIL}"]'), encoding="utf-8")
        warns = [m for level, m in doctor_checks.doctor(Path(self.root)) if level == "warn"]
        self.assertFalse(any("owners.approvers" in m and f"email:{EMAIL}" in m for m in warns), warns)

    def test_the_readme_teaches_the_email_form_for_solo(self):
        for rel in ("README.md", "docs/ADOPTION.md"):
            text = read(rel)
            self.assertNotIn("--profile solo --approvers @you", text, rel)
        self.assertIn("aidd init --profile solo --approvers email:", read("README.md"))


# ---- The guard keeps agents off the base branch when the local gate is the gate --------------------


class BaseBranchGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = str(make_repo(Path(self.tmp.name) / "repo", "solo", approvers=[f"email:{EMAIL}"]))  # on branch feat, no remote

    def test_agents_cannot_land_work_on_the_base_branch_locally(self):
        denied = (
            "git checkout main && git merge feat",
            "git switch main; git merge --no-ff feat -m ship",
            "git push origin main",
            "git push origin feat:main",
            "git checkout main && git commit -am sneak",
            "git switch main && git reset --hard HEAD~1",
            "git checkout main && git cherry-pick abc1234",
            "git branch -f main HEAD",
            "git update-ref refs/heads/main HEAD",
        )
        for cmd in denied:
            with self.subTest(cmd=cmd):
                why = approval_commands.forbidden_action(cmd, self.root)
                self.assertIsNotNone(why, cmd)
                self.assertIn("aidd ship", why or "")
        allowed = (
            "git merge main",
            "git commit -m work",
            "git push origin feat",
            "git checkout main",
            "git checkout main -- a.txt",
            "git checkout -b other && git commit -m work",
            "git reset --hard HEAD",
            "git log main",
        )
        for cmd in allowed:
            with self.subTest(cmd=cmd):
                self.assertIsNone(approval_commands.forbidden_action(cmd, self.root), cmd)

    def test_on_the_base_branch_itself_a_commit_or_merge_is_denied(self):
        git(self.root, "switch", "-q", "main")
        for cmd in ("git commit -m x", "git merge feat", "git reset --soft HEAD~1"):
            with self.subTest(cmd=cmd):
                self.assertIsNotNone(approval_commands.forbidden_action(cmd, self.root), cmd)
        self.assertEqual(command_check.check_command(self.root, self.root, "git commit -m x")[0], "deny")

    def test_with_a_platform_gate_the_platform_protects_the_branch(self):
        git(self.root, "remote", "add", "origin", "https://example.com/shop.git")
        Path(self.root, ".github/workflows").mkdir(parents=True)
        Path(self.root, ".github/workflows/aidd-gate.yml").write_text("name: aidd-gate\n", encoding="utf-8")
        self.assertIsNone(approval_commands.forbidden_action("git push origin main", self.root))
        self.assertIsNotNone(approval_commands.forbidden_action("git push --force origin main", self.root))  # unchanged: never rewrite


# ---- A recorded Spec approval binds, even where solo makes it optional ----------------------------------------


class RecordedSpecApprovalTests(_Repo):
    def test_the_conformance_case_pins_the_codes(self):
        case = ROOT / "examples" / "17-solo-optional-spec-approval"
        ctx, expected = examples.load_example(case)
        self.assertEqual(decide(copy.deepcopy(ctx)).codes(), expected["findings"])
        mutations = {m.stem: json.loads(m.read_text(encoding="utf-8")) for m in (case / "mutations").glob("*.json")}
        got = {}
        for name, m in mutations.items():
            got[name] = decide(examples.apply_ops(copy.deepcopy(ctx), m["ops"])).codes()
            self.assertEqual(got[name], m["expected"]["findings"], name)
        self.assertIn("fail spec_approval.voided", {c for codes in got.values() for c in codes})
        self.assertIn("fail red_green.passes_on_base", {c for codes in got.values() for c in codes})
        self.assertIn("warn red_green.passes_on_base", {c for codes in got.values() for c in codes})  # no approval recorded

    def test_rewriting_the_approved_test_fails_the_gate(self):
        self.solo_shop()
        self.discount_spec()
        code, _, err = self.as_person("approve", "spec", "specs/SPEC-1.md")
        self.assertEqual(code, 0, err)
        # The agent rewrites the frozen test so it passes on base, with a no-op implementation.
        self.write(
            {
                "tests/test_discount.py": "import unittest\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertTrue(True)\n"
            }
        )
        self.implement("def discount(total, percent):\n    return total\n")
        _, d = self.decision()
        self.assertEqual(d.decision, "fail", d.codes())
        self.assertIn("fail spec_approval.voided", d.codes())
        code, out, err = self.as_person("ship")
        self.assertEqual(code, 1, out + err)
        self.assertEqual(git(self.root, "log", "-1", "--format=%s", "main"), "chore: adopt aidd")

    def test_a_weak_test_under_a_recorded_approval_fails_red_green(self):
        self.solo_shop()
        git(self.root, "switch", "-qc", "discount")
        self.discount_spec_weak()
        code, _, err = self.as_person("approve", "spec", "specs/SPEC-1.md")
        self.assertEqual(code, 0, err)
        self.implement()
        _, d = self.decision()
        self.assertIn("fail red_green.passes_on_base", d.codes())

    def discount_spec_weak(self) -> None:
        self.aidd("new", "spec", "SPEC-1", "--title", "Apply a percentage discount", "--type", "feat")
        spec = Path(self.root, "specs/SPEC-1.md")
        text = spec.read_text(encoding="utf-8")
        for old, new in SPEC_FIELDS.items():
            text = text.replace(old, new)
        spec.write_text(text.replace("tests.test_discount", "tests.test_cart").replace('"tests/test_discount.py"', '"tests/test_cart.py"'), encoding="utf-8")
        self.commit("spec: SPEC-1 with a test that already passes")


# ---- A repository with no tests gets a smoke test on Day 0 ----------------------------------------------------


class NoTestsTests(_Repo):
    MESSY = {
        ".gitignore": "__pycache__/\n",
        "requirements.txt": "flask==3.0.0\n",
        "app/__init__.py": "",
        "app/main.py": "GREETING: Helo\n",
    }

    def test_the_dry_run_says_every_change_fails_without_a_test_command(self):
        self.commit("messy", self.MESSY)
        out = self.aidd("init", "--dry-run").stdout
        self.assertIn("every change fails", out)
        self.assertIn("smoke", out)

    def test_init_binds_a_smoke_test_and_the_first_typo_fix_passes_tests(self):
        self.commit("messy", self.MESSY)
        out = self.aidd("init", "--profile", "solo", "--approvers", f"email:{EMAIL}", "--ci", "none", "--harness", "none").stdout
        self.assertIn("smoke", out)
        cfg = config.load_file(config.CONFIG_PATH, self.root)
        self.assertEqual([t["name"] for t in cfg.get("tests")], ["smoke"])
        self.commit("chore: adopt aidd")  # Day 0, on main
        git(self.root, "switch", "-qc", "typo")
        self.commit("fix(copy): correct the greeting typo", {"app/main.py": "GREETING: Hello\n"})
        self.aidd("describe", "--commit")
        self.aidd("test")
        _, d = self.decision()
        self.assertEqual(d.rules_at("fail"), [], d.codes())
        # The smoke test catches a broken file.
        self.commit("fix: break it", {"app/main.py": 'GREETING = "Hello\n'})
        self.assertNotEqual(self.aidd("test", expect=None).returncode, 0)


# ---- Secrets ----------------------------------------------------------------------------------------------------


class SecretsTests(_Repo):
    def test_the_dry_run_flags_a_tracked_env_and_secret_shaped_strings(self):
        self.commit("app", {".env": f"STRIPE_KEY={STRIPE_KEY}\n", "app/aws.py": f'KEY = "{AWS_ID}"\n', "app/main.py": "x = 1\n"})
        out = self.aidd("init", "--dry-run").stdout
        self.assertIn(".env", out)
        self.assertIn("app/aws.py", out)
        self.assertIn("AWS", out)
        self.assertNotIn(AWS_ID, out)
        self.assertNotIn(STRIPE_KEY, out)

    def test_init_ignores_env_files_but_keeps_the_example(self):
        self.commit("app", {"app/main.py": "x = 1\n"})
        self.aidd("init", "--profile", "solo", "--approvers", f"email:{EMAIL}", "--ci", "none", "--harness", "none")
        lines = Path(self.root, ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env*", lines)
        self.assertIn("!.env.example", lines)

    def test_the_local_gate_warns_on_a_secret_shaped_addition(self):
        self.solo_shop()
        git(self.root, "switch", "-qc", "keys")
        self.commit("feat: pay", {"app/pay.py": f'API_KEY = "{STRIPE_KEY}"\nAWS = "{AWS_ID}"\n'})
        self.aidd("describe", "--commit")
        _, d = self.decision()
        self.assertIn("warn secrets.added", d.codes())
        text = " ".join(f.message + f.fix for f in d.findings)
        self.assertIn("app/pay.py", text)
        self.assertNotIn(STRIPE_KEY, text)
        self.assertNotIn(AWS_ID, text)

    def test_the_rule_scans_only_added_lines_and_is_bounded(self):
        from aidd.gate.rules import safety

        self.assertEqual(safety.secret_kinds(f'x: "{AWS_ID}"'), ["an AWS access key id"])
        self.assertEqual(safety.secret_kinds("-----BEGIN RSA PRIVATE KEY-----"), ["a private key"])
        self.assertEqual(safety.secret_kinds("GITHUB_TOKEN=ghp_" + "a" * 36), ["a GitHub token"])
        self.assertEqual(safety.secret_kinds("WEBHOOK_SECRET=hunter2hunter2"), ["a *_SECRET assignment"])
        self.assertEqual(safety.secret_kinds("WEBHOOK_SECRET=${WEBHOOK_SECRET}"), [])
        self.assertEqual(safety.secret_kinds("sk_test_" + "a" * 24), [])
        self.assertEqual(safety.secret_kinds("A" * 100_000), [])


# ---- Detected sensitive areas become risk rules ---------------------------------------------------------------


class RiskRuleTests(_Repo):
    def test_init_writes_the_detected_risk_rules(self):
        self.commit("app", {"app/ledger/entries.py": "x = 1\n", "scripts/deploy.sh": "echo deploy\n", "app/main.py": "x = 1\n"})
        self.aidd("init", "--profile", "solo", "--approvers", f"email:{EMAIL}", "--ci", "none", "--harness", "none")
        cfg = config.load_file(config.CONFIG_PATH, self.root)
        names = {r["name"] for r in cfg.get("risk_rules")}
        self.assertLessEqual({"payments", "deploy"}, names)
        a = routing.assess_paths(cfg, ["scripts/deploy.sh"], ctype="fix", tracked=["scripts/deploy.sh"])
        self.assertNotEqual(a.required_route, "minor")
        self.assertIn("remove", Path(self.root, ".aidd/config.yaml").read_text(encoding="utf-8").lower())


# ---- What the forecast, list, and the gate say locally --------------------------------------------------------------


class LocalWordingTests(_Repo):
    def test_after_a_local_spec_approval_the_steps_say_it_is_recorded(self):
        self.solo_shop()
        self.discount_spec()
        code, _, err = self.as_person("approve", "spec", "specs/SPEC-1.md")
        self.assertEqual(code, 0, err)
        steps = next_steps.forecast(Path(self.root))["steps"]
        spec = next(s for s in steps if s.get("id") == "SPEC-1")
        self.assertEqual(spec["code"], "spec.ready")
        self.assertIn("Spec approval recorded", spec["what"])
        for s in steps:
            self.assertNotIn("/aidd-team:", s["how"])  # the team plugin is not installed here
            self.assertNotIn("hash", s["how"])
            self.assertNotIn("PR/MR", s["how"])
        self.aidd("test", "--base", "main", expect=None)
        _, d = self.decision()
        phase = [f for f in d.findings if f.code == "tests.spec_phase"]
        self.assertTrue(phase, d.codes())
        self.assertNotIn("get Spec approval first", phase[0].fix)
        self.assertIn("Spec approval recorded", phase[0].message + phase[0].fix)

    def test_the_fast_lane_hint_gives_the_local_order(self):
        self.solo_shop()
        git(self.root, "switch", "-qc", "fix")
        self.commit("fix: cart", {"app/cart.py": "def total(items):\n    return sum(items) or 0\n"})
        lane = next(s for s in next_steps.forecast(Path(self.root))["steps"] if s["code"] == "lane")
        how = lane["how"]
        self.assertLess(how.index("aidd describe --commit"), how.index("aidd test"))
        self.assertLess(how.index("aidd test"), how.index("aidd ship"))

    def test_a_new_feature_file_without_a_test_suggests_the_spec_lane(self):
        self.solo_shop()
        a = next_steps.forecast(Path(self.root), paths=["app/endpoint.py"], ctype="feat")
        self.assertEqual(a["route"]["route"], "minor")  # routing is unchanged
        self.assertIn("spec lane", a["steps"][0]["how"])
        with_test = next_steps.forecast(Path(self.root), paths=["app/endpoint.py", "tests/test_endpoint.py"], ctype="feat")
        self.assertNotIn("spec lane", with_test["steps"][0]["how"])
        existing = next_steps.forecast(Path(self.root), paths=["app/cart.py"], ctype="feat")
        self.assertNotIn("spec lane", existing["steps"][0]["how"])
        run = self.aidd("new", "spec", "SPEC-9", "--title", "Endpoint", "--type", "feat", "--paths", "app/endpoint.py", expect=1)  # nothing written
        self.assertIn("spec lane", run.stderr)


# ---- Who the local change's author is, and which approvals belong to this branch ------------------------------


class LocalApprovalsTests(_Repo):
    def test_the_local_git_user_is_the_change_author_in_a_preflight(self):
        git(self.root, "config", "user.name", "alice")
        self.commit(
            "scaffold",
            {
                ".gitignore": "__pycache__/\n",
                "a.txt": "a\n",
                "t/__init__.py": "",
                "t/test_a.py": "import unittest\n\n\nclass A(unittest.TestCase):\n    def test_a(self):\n        self.assertTrue(True)\n",
            },
        )
        self.aidd("init", "--profile", "team", "--approvers", "@alice", "@bob", "--test", f"{PY} -m unittest", "--ci", "none", "--harness", "none")
        self.commit("chore: adopt aidd")
        git(self.root, "switch", "-qc", "fix")
        self.commit("fix: a", {"a.txt": "b\n"})
        self.aidd("describe", "--commit")
        head = git(self.root, "rev-parse", "HEAD")
        self.aidd("test")
        verdicts = {}
        for who in ("alice", "bob"):
            f = Path(self.tmp.name, f"{who}.json")
            f.write_text(json.dumps({"comments": [], "reviews": [{"user": who, "state": "approved", "commit_sha": head}]}), encoding="utf-8")
            verdicts[who] = self.decision(approvals=str(f))[1]
        self.assertNotEqual(verdicts["alice"].decision, "pass", verdicts["alice"].codes())
        self.assertIn("pending merge_approval.missing", verdicts["alice"].codes())
        self.assertEqual(verdicts["bob"].decision, "pass", verdicts["bob"].codes())

    def test_an_approval_of_another_branch_is_not_this_branchs(self):
        self.solo_shop()
        git(self.root, "switch", "-qc", "c")
        self.commit("fix: one", {"app/cart.py": "def total(items):\n    return sum(items) or 0\n"})
        self.aidd("describe", "--commit")
        code, out, err = self.as_person("ship")
        self.assertEqual(code, 0, out + err)
        git(self.root, "switch", "-qc", "d")
        self.commit("fix: two", {"app/cart.py": "def total(items):\n    return sum(items) or 0  # two\n"})
        self.aidd("describe", "--commit")
        self.aidd("test")
        _, d = self.decision()
        self.assertNotIn("warn merge_approval.not_carried", d.codes())
        missing = next(f for f in d.findings if f.code == "merge_approval.missing")
        self.assertNotIn("older commit", missing.message)


# ---- What the person reads before typing the code, and the local cool-off --------------------------------------


class BeforeTheCodeTests(_Repo):
    def test_approve_spec_shows_what_is_approved(self):
        self.solo_shop()
        self.discount_spec()
        h = self.aidd("hash", "specs/SPEC-1.md").stdout.strip()
        code, out, err = self.as_person("approve", "spec", "specs/SPEC-1.md")
        self.assertEqual(code, 0, err)
        shown = out + err
        self.assertIn("Apply a percentage discount", shown)
        self.assertRegex(shown, r"Acceptance +A1\n")
        self.assertIn(h, shown)

    def test_ship_shows_the_diffstat_before_the_code(self):
        self.solo_shop()
        git(self.root, "switch", "-qc", "fix")
        self.commit("fix: cart", {"app/cart.py": "def total(items):\n    return sum(items) or 0\n"})
        self.aidd("describe", "--commit")
        code, out, err = self.as_person("ship")
        self.assertEqual(code, 0, out + err)
        self.assertRegex(out, r"app/cart\.py \| +\d+ [+-]+")
        self.assertRegex(out, r"1 file changed")

    def test_a_person_may_skip_the_local_cooloff_on_record(self):
        head = "a" * 40
        self.commit("day 0", {"a.txt": "a\n"})
        approval_ledger.record_local_approval(approval_ledger.approve_merge_line(head, skip_cooloff=True), self.root)
        reviews, _, _ = approval_ledger.load_local_approvals(self.root)
        self.assertTrue(reviews[0]["cooloff_skipped"])
        parser = cli_parser.build_parser()
        self.assertTrue(parser.parse_args(["ship", "--skip-cooloff"]).skip_cooloff)
        self.assertTrue(parser.parse_args(["approve", "merge", "--skip-cooloff"]).skip_cooloff)

    def test_the_conformance_case_records_the_skip_only_locally(self):
        ctx, _ = examples.load_example(ROOT / "examples" / "11-solo-major")
        m = json.loads((ROOT / "examples/11-solo-major/mutations/local-first-cooloff-skipped.json").read_text(encoding="utf-8"))
        d = decide(examples.apply_ops(copy.deepcopy(ctx), m["ops"]))
        self.assertEqual(d.decision, "pass", d.codes())
        self.assertIn("warn merge_approval.cooloff_skipped", d.codes())
        self.assertTrue(d.record.get("cooloff_skipped_by"))


# ---- Setup polish -----------------------------------------------------------------------------------------------


class SetupPolishTests(_Repo):
    def test_doctor_is_quiet_about_ci_on_a_local_first_repository(self):
        self.solo_shop()
        results = doctor_checks.doctor(Path(self.root))
        self.assertFalse([m for level, m in results if "no aidd CI found" in m], results)
        self.assertTrue([m for level, m in results if level == "ok" and "local-first" in m], results)

    def test_solo_specs_get_an_owner_team(self):
        self.solo_shop()
        self.assertEqual(config.load_file(config.CONFIG_PATH, self.root).get("owners", "default_team"), "maintainers")
        self.aidd("new", "spec", "SPEC-2", "--title", "Two")
        self.assertIn("\nowner_team: maintainers\n", Path(self.root, "specs/SPEC-2.md").read_text(encoding="utf-8"))

    def test_the_spec_template_is_platform_neutral_and_routes_tests(self):
        for name in ("spec-short.md", "spec.md"):
            self.assertNotIn("PR/MR", re.search(r"(?m)^rollback: .*$", read(f".agents/skills/aidd/assets/{name}")).group(0), name)
        self.solo_shop()
        self.aidd("new", "spec", "SPEC-3", "--title", "Three", "--paths", "app/x.py", "tests/test_x.py", "--force")
        text = Path(self.root, "specs/SPEC-3.md").read_text(encoding="utf-8")
        self.assertIn("scope: [app/x.py]", text)
        self.assertIn("files: [tests/test_x.py]", text)

    def test_init_describes_enforcement_as_the_config_does(self):
        self.commit("app", {"a.txt": "a\n"})
        out = self.aidd("init", "--profile", "solo", "--approvers", f"email:{EMAIL}", "--harness", "none").stdout
        self.assertNotIn("the aidd-gate.yml input on GitHub", out)
        self.assertIn("mode: enforce", out)
        self.assertIn("wins", out)

    def test_a_bun_project_runs_bun(self):
        self.write({"package.json": json.dumps({"name": "tiny", "scripts": {"start": "bun src/server.ts", "test": "bun test"}})})
        found = detection.detect(Path(self.root))
        self.assertEqual(found["tests"][0]["test"][0], "bun")


# ---- The pages a founder reads first ----------------------------------------------------------------------------


class DocsTests(unittest.TestCase):
    def test_the_quickstart_is_solo_and_local_first(self):
        text = read("docs/QUICKSTART.md")
        first_init = re.search(r"(?m)^aidd init .*$", text).group(0)
        self.assertIn("--profile solo", first_init)
        self.assertIn("aidd approve spec", text)
        self.assertIn("aidd ship", text)
        team = re.search(r"(?mi)^## .*team.*$", text)
        self.assertIsNotNone(team)
        self.assertGreater(text.index("approvals.json"), team.start())

    def test_install_shows_the_commit_form_first(self):
        cli_table = section(read("docs/INSTALL.md"), "## The CLI")
        uv = next(ln for ln in cli_table.splitlines() if ln.startswith("| ") and "uv tool install" in ln)
        self.assertIn("@<sha>", uv)
        self.assertIn("after the release", cli_table)

    def test_the_pr_template_defaults_to_the_fast_lane(self):
        text = read("templates/github/pull_request_template.md")
        self.assertNotIn("SPEC-XXX", text)
        block = re.search(r"```yaml aidd\n(.*?)```", text, re.S).group(1)
        self.assertIn("route: minor", block)
        self.assertNotRegex(block, r"(?m)^spec = ")

    def test_a_solo_day_fits_one_screen_and_the_readme_links_it(self):
        day = section(read("docs/ADOPTION.md"), "### A solo day")
        self.assertLess(len(day.strip().splitlines()), 40)
        self.assertIn("aidd ship", day)
        readme = read("README.md")
        self.assertIn("ADOPTION.md#a-solo-day", readme)
        self.assertNotIn("flowchart TD", readme)


if __name__ == "__main__":
    unittest.main()
