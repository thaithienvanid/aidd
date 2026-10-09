"""One team of people and agents: who decides and who works (`aidd owners`), the goal everyone steers by, the
readiness checks in `aidd doctor`, and autonomy an agent earns from evidence (`aidd metrics --autonomy`)."""

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import bands, config, metrics, owners, repo

CFG = 'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@org/leads"]\n[owners.specialists]\nsecurity = ["@org/sec"]\n'


def cfg_text(extra="", profile="team"):
    """Top-level keys such as `goal` go before the first table; TOML would read them into that table otherwise."""
    lines = extra.splitlines(keepends=True)
    first_table = next((i for i, line in enumerate(lines) if line.startswith("[")), len(lines))
    top, tables = "".join(lines[:first_table]), "".join(lines[first_table:])
    return CFG.replace('profile = "team"\n', f'profile = "{profile}"\n{top}') + tables


class OwnersTests(unittest.TestCase):
    def build(self, extra=""):
        return owners.build(config.load_text(cfg_text(extra)))

    def test_humans_decide_and_agents_do_the_work(self):
        r = self.build()
        self.assertEqual(r["humans"]["approvers"], ["@org/leads"])
        self.assertEqual(r["humans"]["specialist_pools"], {"security": ["@org/sec"]})
        self.assertIn("verifier", [a["role"] for a in r["agents"]])
        text = owners.markdown(r)
        self.assertIn("Spec approval and Merge approval", text)
        self.assertIn("_not set_", text)
        self.assertIn("**Goal:** fewer failed checkouts", owners.markdown(self.build('goal = "fewer failed checkouts"\n')))
        self.assertNotIn("**Mission:**", text)
        both = self.build('mission = "shops get paid"\ngoal = "fewer failed checkouts"\n')
        self.assertEqual((both["mission"], both["goal"]), ("shops get paid", "fewer failed checkouts"))
        self.assertIn("**Mission:** shops get paid\n\n**Goal:** fewer failed checkouts", owners.markdown(both))

    def test_only_named_roles_propose_unsolicited_work(self):
        default = {a["role"] for a in self.build()["agents"] if a["proactive"]}
        self.assertEqual(default, set(owners.DEFAULT_PROACTIVE_ROLES))
        quiet = self.build("[agents]\nproactive_roles = []\n")
        self.assertFalse(any(a["proactive"] for a in quiet["agents"]))
        self.assertEqual(self.build('[agents]\nproactive_roles = ["intern"]\n')["unknown_proactive_roles"], ["intern"])

    def test_the_markdown_names_every_decision_and_its_owners(self):
        built = owners.build(
            config.load_text(
                'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@org/leads"]\ncodeowners = true\n'
                '[owners.specialists]\nsecurity = ["@org/sec"]\nprivacy = ["@dpo", "@legal"]\n'
                '[[owners.paths]]\npaths = ["src/billing/**", "db/**"]\napprovers = ["@org/billing"]\n'
                '[identities]\nbots = ["codex[bot]", "claude[bot]"]\n[agents]\nproactive_roles = ["sre", "intern"]\n'
            )
        )
        text = owners.markdown(built)
        humans = text.split("## Humans: they decide", 1)[1].split("## Agents", 1)[0]
        rows = [tuple(c.strip() for c in ln.strip("|").split("|")) for ln in humans.splitlines() if ln.startswith("| ") and "---" not in ln][1:]
        self.assertEqual(
            rows,
            [
                ("Spec approval and Merge approval", "@org/leads"),
                ("specialist Approvers: privacy", "@dpo, @legal"),  # pools sorted by name
                ("specialist Approvers: security", "@org/sec"),
                ("owners of src/billing/**, db/**", "@org/billing"),
                ("owners of CODEOWNERS areas", "the base branch's CODEOWNERS"),
            ],
        )
        # The agent accounts, sorted, on one line of the Agents section before its table.
        self.assertEqual(built["agent_accounts"], ["claude[bot]", "codex[bot]"])
        agents_section = text.split("## Agents", 1)[1]
        [accounts] = [ln for ln in agents_section.split("\n| ", 1)[0].splitlines() if "claude[bot]" in ln]
        self.assertLess(accounts.index("claude[bot]"), accounts.index("codex[bot]"))
        agents = {ln.split("|")[1].strip(" `"): ln.split("|")[-2].strip() for ln in agents_section.splitlines() if ln.startswith("| `")}
        self.assertEqual({role for role, proposes in agents.items() if proposes == "yes"}, {"sre"})
        # An unknown proactive role is named last, with the config key to fix.
        self.assertEqual(built["unknown_proactive_roles"], ["intern"])
        last = text.rstrip().splitlines()[-1]
        self.assertIn("agents.proactive_roles", last)
        self.assertIn("intern", last)
        self.assertNotIn("sre", last)
        plain = owners.markdown(self.build())
        self.assertNotIn("CODEOWNERS", plain)
        self.assertNotIn("Agent accounts", plain)
        self.assertNotIn("Unknown roles", plain)

    def test_the_command_prints_json_and_never_fails_on_readiness(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            run = subprocess.run([sys.executable, "-m", "aidd", "owners", "--json"], cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("verifier", [a["role"] for a in json.loads(run.stdout)["agents"]])


class DoctorReadinessTests(unittest.TestCase):
    """`aidd doctor` asks whether the team can work together: the goal and the review rubric, beside its wiring checks."""

    def doctor(self, extra="", review=True, profile="team", security='["@org/sec"]'):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", d], check=True)
            (root / ".aidd").mkdir()
            text = cfg_text(extra, profile).replace('security = ["@org/sec"]', f"security = {security}")
            (root / ".aidd" / "config.toml").write_text(text, encoding="utf-8")
            if review:
                (root / "REVIEW.md").write_text("# Review policy\n", encoding="utf-8")
            with contextlib.chdir(root):
                return repo.doctor(root)

    def test_a_missing_rubric_is_warned_and_a_missing_goal_is_not(self):
        found = self.doctor(review=False)
        self.assertTrue(any(level == "warn" and msg.startswith("no REVIEW.md") for level, msg in found))
        # A fresh init stays free of warnings; `aidd owners` shows the goal as not set, with how to set it.
        self.assertFalse(any("goal" in msg for _, msg in found))

    def test_a_ready_team_is_ok(self):
        found = self.doctor('goal = "fewer failed checkouts"\n')
        self.assertIn(("ok", "goal: fewer failed checkouts"), found)
        self.assertIn(("ok", "REVIEW.md: the rubric every reviewer follows"), found)

    def test_a_one_person_specialist_pool_is_warned_outside_solo(self):
        # An author never approves their own change, so a pool of one can never approve that person's major change.
        found = self.doctor(security='["@tech-lead"]')
        warned = [msg for level, msg in found if level == "warn" and "owners.specialists.security" in msg]
        self.assertEqual(len(warned), 1, found)
        self.assertIn("@tech-lead", warned[0])
        self.assertIn("at least two", warned[0])

    def test_a_pool_of_two_a_team_handle_or_solo_is_not_warned(self):
        for security, profile in (('["@tech-lead", "@engineer"]', "team"), ('["@org/sec"]', "team"), ('["@me"]', "solo")):
            with self.subTest(security=security, profile=profile):
                found = self.doctor(security=security, profile=profile)
                self.assertFalse([msg for _, msg in found if "owners.specialists.security" in msg], found)

    def test_init_writes_the_goal_and_uninstall_still_recognizes_the_config(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", d], check=True)
            goal = 'make "checkout" succeed on the first try'
            repo.init(root, profile="team", ci="none", links=[], approvers=["@org/leads"], harnesses=[], goal=goal)
            text = (root / ".aidd" / "config.toml").read_text(encoding="utf-8")
            self.assertEqual(config.load_text(text).get("goal"), goal)
            self.assertIn(f"would remove {root / '.aidd' / 'config.toml'}", repo.uninstall(root))  # unchanged since init, so removable

    def test_uninstall_recognizes_an_unchanged_config_under_every_profile(self):
        # Under solo, init also writes `owners.default_team`, so uninstall rebuilds the config with it.
        for profile in ("solo", "team", "org", "regulated"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                repo.init(root, profile=profile, ci="none", links=[], skill=False, approvers=["@org/leads"], harnesses=[])
                self.assertIn(f"would remove {root / '.aidd' / 'config.toml'}", repo.uninstall(root))
                repo.uninstall(root, yes=True)
                self.assertFalse((root / ".aidd" / "config.toml").exists())

    def test_a_breach_weighs_its_priority_against_the_goal(self):
        reading = bands.assess([1.0, 1.1, 0.9, 1.0, 1.0, 1.1, 0.9, 1.0, 9.0], bands.Band("errors"))
        self.assertIn("goal, to weigh the priority against: fewer failed checkouts", bands.intent_text(reading, "s.txt", "fewer failed checkouts"))
        self.assertNotIn("goal", bands.intent_text(reading, "s.txt"))


def ev(change, ts, decision="pass", head="h1", agent="claude-code/opus", ctype="fix", **kw):
    return {
        "repo": "o/r",
        "change": change,
        "ts": ts,
        "head_sha": head,
        "decision": decision,
        "type": ctype,
        "assisted_by": [agent],
        "pending_rules": [],
        "failed_rules": [],
        "spec_hash": "a",
    } | kw


class AutonomyTests(unittest.TestCase):
    def history(self, n, **kw):
        return [ev(str(i), f"2026-09-{1 + i % 27:02d}T10:00:00Z", **kw) for i in range(n)]

    def test_a_new_agent_starts_by_having_every_change_reviewed(self):
        self.assertEqual(metrics.autonomy(self.history(3))[0]["stage"], "review every change")

    def test_clean_history_earns_one_stage_at_a_time(self):
        self.assertEqual(metrics.autonomy(self.history(12))[0]["stage"], "review the trade-offs")
        self.assertEqual(metrics.autonomy(self.history(30))[0]["stage"], "candidate standard change")

    def test_one_failure_holds_the_agent_at_full_review(self):
        rows = metrics.autonomy(self.history(30) + [ev("x", "2026-09-28T10:00:00Z", decision="fail")])
        self.assertEqual(rows[0]["stage"], "review every change")

    def test_the_thresholds_are_the_teams_to_set(self):
        strict = {"min_changes": 20, "min_first_pass": 0.95, "standard_min_changes": 50, "standard_min_first_pass": 1.0}
        self.assertEqual(metrics.autonomy(self.history(12), **strict)[0]["stage"], "review every change")
        cfg = config.load_text(CFG + "[agents.autonomy]\nmin_changes = 5\n")
        self.assertEqual(metrics.autonomy(self.history(6), **cfg.get("agents", "autonomy"))[0]["stage"], "review the trade-offs")

    def test_autonomy_is_per_kind_of_work(self):
        rows = {r["type"]: r["stage"] for r in metrics.autonomy(self.history(12) + self.history(2, ctype="feat"))}
        self.assertEqual(rows, {"fix": "review the trade-offs", "feat": "review every change"})
        self.assertIn("candidate standard change", metrics.autonomy_markdown([]))


if __name__ == "__main__":
    unittest.main()
