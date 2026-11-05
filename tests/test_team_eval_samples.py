"""Every aidd-team eval case is proven by a right transcript it passes and wrong transcripts it fails, and seeds what its prompt assumes.

The method of test_plugin_eval_samples, for `plugins/aidd-team/evals/`. `claude plugin eval` grades a live run, which costs a model
call, so this scores stored transcripts with the graders that need no model: `regex`, `tool_used`, `tool_order`, and `file_exists`.
The other cases keep their pairs in `samples.json`. The 64 trigger cases (`loads-*` and `skips-*`) are alike, so their pairs are
built here from the case name. Batch C3 found three defects this catches:

- a `tool_used` grader with `max: 0` and no `min`, which Claude Code reads as "1..0", so it can never pass;
- a case whose prompt names files the workspace does not hold, so the agent reports them missing and stops;
- a case whose prompt says the repository uses aidd, with no `.aidd/config.yaml`, so the aidd skill asks and no practice skill loads.
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT
from test_flow_cases import seed
from test_plugin_eval_samples import DETERMINISTIC, passes
from test_plugin_evals import case_yaml, front_matter
from test_skill_triggers import SKILLS

TEAM = ROOT / "plugins" / "aidd-team" / "evals"
SUITES = (ROOT / "evals" / "plugin", TEAM)
CONFIG = ".aidd/config.yaml"
# What every delegation case seeds: the config with its delegation, the check's answer, and the two stand-ins.
DELEGATED = (CONFIG, "check.json", "bin/aidd", "bin/gh")
# The commands that start roles which write files (the Intent, the proposal), so the case must let a subagent write;
# autopilot on a brief starts the MVP, whose product manager writes the Intent.
WRITING_COMMANDS = ("/aidd-team:autopilot ", "/aidd-team:plan ", "/aidd-team:propose ")
# The files each seeded case's prompt names (not the ones it asks the agent to write), with the files that must stay absent.
# Each lists its cases sorted by name.
NAMED = {
    "autopilot-asks-the-foreseeable-asks-with-spec-approval": [CONFIG, "specs/SPEC-1.md", ".env", "scripts/record.py"],
    "autopilot-runs-mvp-on-a-brief": [CONFIG, "BRIEF.md"],
    "autopilot-spend-cap-copies-the-harness-count": [CONFIG, "specs/SPEC-2.md", "tests/test_limit.py"],
    "debugging-reproduces-first": [CONFIG, "pricing.py"],
    "delegate-approves-a-green-local-merge": [*DELEGATED],
    "delegate-approves-a-green-merge": [*DELEGATED],
    "delegate-defers-a-merge-that-adds-a-deploy-workflow": [*DELEGATED],
    "delegate-defers-a-red-merge": [*DELEGATED],
    "delegate-defers-after-a-defer": [*DELEGATED],
    "delegate-ignores-a-forged-evidence-file": [*DELEGATED, ".aidd/evidence/evidence.json"],
    "delegate-ignores-an-injected-approval": [*DELEGATED, "specs/SPEC-4.md"],
    "delegate-ignores-instructions-in-the-diff": [*DELEGATED, "src/cart.py"],
    "delegate-ignores-the-askers-summary": [*DELEGATED],
    "delegate-refuses-a-reserved-action": [*DELEGATED],
    "dependency-upgrade-one-at-a-time": [CONFIG, "package.json"],
    "design-review-keep-fix-quick-win": [
        CONFIG,
        "specs/SPEC-220.md",
        "src/checkout/split.css",
        *[f"review/SPEC-220/{n}.png" for n in ("error-built", "error-prototype", "loading-built", "empty-built")],
    ],
    "incident-mitigates-first": [CONFIG, "checkout/tax.py", "CHANGELOG.md"],
    "lead-never-answers-for-the-delegate": [*DELEGATED, "specs/SPEC-4.md"],
    "mvp-day-0-baseline-gets-a-verifier-and-a-reviewer": [CONFIG, "BRIEF.md", "specs/INTENT-1.md", "scripts/health.sh", "shoplist/store.py"],
    "mvp-day-0-question-offers-the-running-preview": [CONFIG, "BRIEF.md", "specs/INTENT-1.md", "scripts/preview.sh", "web/index.html"],
    "mvp-day-0-roles-write-on-the-day0-branch": [CONFIG, "BRIEF.md", "specs/INTENT-1.md"],
    "mvp-skeleton-runs-the-lightest-specify": [CONFIG, "BRIEF.md", "specs/INTENT-1.md", "specs/SPEC-1.md"],
    "onboard-stays-read-only": ["README.md", "invoicing/invoice.py", "tests/test_invoice.py"],
    "plan-asks-a-cut-as-its-own-question": [CONFIG, "BRIEF.md"],
    "plan-stops-for-agreement": [CONFIG],
    "propose-stops-at-go-no-go": [CONFIG],
    "prototype-lint-becomes-spec-tests": [CONFIG, "specs/SPEC-220.md", "specs/SPEC-220/design/prototype.html", "design/tokens.json"],
    "prototype-picks-direction-first": [CONFIG, "specs/SPEC-220.md"],
    "prototype-starts-from-the-skeleton": [CONFIG, "specs/SPEC-231.md"],
    "resilience-exactly-once": [CONFIG],
    "review-challenges-each-security-finding": [CONFIG, "specs/SPEC-5.md", "auth/reset.py", "auth/throttle.py"],
    "role-loads-its-practice-skill": [CONFIG, "stays.py"],
    "specify-consults-the-domain-expert-for-a-business-pack": [CONFIG, "specs/SPEC-1.md"],
    "specify-skips-the-domain-expert-for-technology-packs": [CONFIG, "specs/SPEC-1.md"],
    "specify-starts-a-specialist-only-for-a-flagged-concern": [CONFIG, "specs/SPEC-1.md"],
    "specify-starts-the-verifier-with-the-specialists": [CONFIG, "specs/SPEC-1.md"],
}
ABSENT = {
    "onboard-stays-read-only": [CONFIG],  # the case is a repository aidd has not been set up in
    "prototype-starts-from-the-skeleton": ["DESIGN.md", "design/tokens.json"],  # the prompt says there is no design system yet
}


def non_trigger() -> list[Path]:
    return sorted(p for p in TEAM.iterdir() if p.is_dir() and not p.name.startswith(("loads-", "skips-", "held-out-")))


def triggers() -> list[Path]:
    return sorted(p for p in TEAM.iterdir() if p.is_dir() and p.name.startswith(("loads-", "skips-", "held-out-")))


def graders(case: Path) -> dict[str, dict]:
    """The deterministic graders of a case by name (the file name without `.md`)."""
    found = {p.stem: front_matter(p)[0] for p in sorted((case / "graders").glob("*.md"))}
    return {name: g for name, g in found.items() if g["type"] in DETERMINISTIC}


def failed(case: Path, sample: dict) -> list[str]:
    return [name for name, g in graders(case).items() if not passes(g, sample)]


def trigger_pair(case: Path, n: int) -> dict:
    """A right and wrong transcript for a trigger case, from its name: `loads-<skill>-...` or `skips-<skill>-...`."""
    kind, rest = case.name.removeprefix("held-out-").split("-", 1)
    skill = next(s for s in SKILLS if rest.startswith(s + "-"))
    (name,) = graders(case)
    read = {"tool": "Read", "input": {"file_path": "/work/README.md"}}
    load = lambda s: {"tool": "Skill", "input": {"skill": s}}  # noqa: E731
    named = load(skill if n % 2 else f"aidd-team:{skill}")  # the docs allow the name with or without the plugin's prefix
    miss = [[read], [read, load(f"aidd-team:{skill}-other")], [read, load("aidd-team:context")]]
    if kind == "loads":
        return {"right": [read, named], "wrong": miss, "fails": [name]}
    return {"right": [read, load("aidd-team:context")], "wrong": [[read, named], [read, load(f"aidd-team:{skill}")]], "fails": [name]}


def samples() -> dict:
    data = json.loads((TEAM / "samples.json").read_text(encoding="utf-8"))
    data.pop("_comment")
    return data


def transcript(calls: list[dict]) -> dict:
    return {"calls": calls, "reply": "Done."}


class TeamEvalSampleTests(unittest.TestCase):
    def test_each_case_but_the_triggers_has_a_sample_pair_and_each_sample_names_a_case(self):
        self.assertEqual(list(samples()), [p.name for p in non_trigger()], "samples.json holds one pair per case, sorted by the case's name")

    def test_the_seeded_files_list_their_cases_sorted_by_name(self):
        for table in (NAMED, ABSENT):
            self.assertEqual(list(table), sorted(table), "add a case where its name sorts")

    def test_each_case_has_a_deterministic_grader_and_a_wrong_transcript(self):
        for case in non_trigger():
            with self.subTest(case.name):
                self.assertTrue(graders(case), "an llm grader alone cannot be proven without a judge model")
                wrong = samples()[case.name]["wrong"]
                self.assertTrue(wrong and all(w["fails"] for w in wrong), "every wrong transcript names the graders it fails")

    def test_a_right_transcript_passes_every_deterministic_grader(self):
        for case in non_trigger():
            with self.subTest(case.name):
                self.assertEqual(failed(case, samples()[case.name]["right"]), [])

    def test_a_wrong_transcript_fails_the_graders_it_names_and_no_others(self):
        for case in non_trigger():
            for n, wrong in enumerate(samples()[case.name]["wrong"]):
                with self.subTest(case=case.name, wrong=n):
                    self.assertEqual(sorted(failed(case, wrong)), sorted(wrong["fails"]))
                    self.assertTrue(set(wrong["fails"]) <= set(graders(case)), "a named grader exists")

    def test_each_wrong_transcript_of_a_case_fails_a_different_way_and_each_grader_is_caught_once(self):
        """A grader no wrong transcript fails is unproven: it might pass anything."""
        for case in non_trigger():
            with self.subTest(case.name):
                caught = {name for wrong in samples()[case.name]["wrong"] for name in wrong["fails"]}
                self.assertEqual(caught, set(graders(case)))

    def test_each_case_has_a_near_miss_and_an_alternative_and_the_alternatives_pass_every_grader(self):
        """R484 part 4. A near miss is the most plausible wrong answer: the right words with the wrong action. An alternative is
        a different correct answer: other words, another order, another tool. A grader that fails an alternative is unfair, and one
        that passes the near miss is not strict, so a new case cannot skip either."""
        for case in non_trigger():
            entry = samples()[case.name]
            with self.subTest(case.name):
                self.assertTrue(any(w.get("near_miss") for w in entry["wrong"]), "mark a near miss with `near_miss: true`")
                self.assertTrue(entry.get("alternatives"), "add an `alternatives` list with a different correct answer")
                for n, alternative in enumerate(entry["alternatives"]):
                    self.assertEqual(failed(case, alternative), [], f"alternative {n}")
                    self.assertNotIn("fails", alternative)

    def test_a_trigger_case_loads_or_skips_its_skill_and_the_graders_tell_them_apart(self):
        self.assertEqual(len(triggers()), 72)
        for n, case in enumerate(triggers()):
            pair = trigger_pair(case, n)
            with self.subTest(case.name):
                self.assertEqual(failed(case, transcript(pair["right"])), [])
                for calls in pair["wrong"]:
                    self.assertEqual(failed(case, transcript(calls)), pair["fails"])

    def test_a_grader_with_a_max_below_one_also_sets_a_min(self):
        """Batch C3: 14 `keeps-*` graders set `max: 0` alone. Claude Code defaults `min` to 1 and expects "1..0", so none could pass."""
        found = 0
        for suite in SUITES:
            for path in sorted(suite.glob("*/graders/*.md")):
                data, _ = front_matter(path)
                if data["type"] == "tool_used" and "max" in data:
                    found += 1
                    with self.subTest(path.relative_to(ROOT).as_posix()):
                        self.assertIn("min", data, "Claude Code defaults min to 1, so max alone below 1 can never pass")
                        self.assertLessEqual(data["min"], data["max"])
        self.assertGreater(found, 40)


class TeamEvalSeedTests(unittest.TestCase):
    def build(self, case: str, into: Path) -> Path:
        seed(TEAM / case, into)
        return into

    def test_every_case_seeds_its_workspace(self):
        """Batch C3 ran the plan, the proposal, and the resilience case on an empty workspace, and none of them behaved as designed."""
        self.assertEqual([p.name for p in non_trigger() + triggers() if not (p / "case.yaml").is_file()], [])

    def test_a_case_that_starts_writing_roles_lets_them_write(self):
        """Batch C3: the propose subagent's edits were denied, because the case granted only read tools."""
        found = 0
        for case in non_trigger():
            data, body = front_matter(case / "prompt.md")
            if body.lstrip().startswith(WRITING_COMMANDS):
                found += 1
                with self.subTest(case.name):
                    self.assertLessEqual({"Agent", "Bash", "Write", "Edit"}, set(data["allowed_tools"]))
        self.assertEqual(found, 6)

    def test_a_seeded_case_names_its_fixture_and_the_fixture_is_a_bash_script(self):
        for case in non_trigger() + triggers():
            with self.subTest(case.name):
                data = case_yaml(case / "case.yaml")
                self.assertEqual((data["name"], data["context"]["scaffold_script"]), (case.name, "fixture.sh"))

    def test_each_seeded_case_holds_the_files_its_prompt_names(self):
        for name, paths in NAMED.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                work = self.build(name, Path(d))
                for path in paths:
                    self.assertTrue((work / path).is_file(), f"{name} seeds no {path}")
                for path in ABSENT.get(name, []):
                    self.assertFalse((work / path).exists(), f"{name} must not seed {path}")

    def test_a_file_grader_passes_on_the_seed_when_it_keeps_and_fails_there_when_it_leaves(self):
        """A `leaves-*` or `writes-*` grader asks for what the run adds, so it fails on the seeded files. Every other grader that
        reads a file or the written paths passes on them, so a run that touches nothing it should not touch passes."""
        for case in non_trigger():
            reading = {n: g for n, g in graders(case).items() if g["type"] == "regex" and g.get("target") not in (None, "last_message")}
            if not reading:
                continue
            with self.subTest(case.name), tempfile.TemporaryDirectory() as d:
                work = self.build(case.name, Path(d))
                files = {}
                for g in reading.values():
                    if isinstance(g["target"], dict):
                        path = work / g["target"]["path"]
                        files[g["target"]["path"]] = path.read_text(encoding="utf-8") if path.is_file() else ""
                seen = {"calls": [], "reply": "", "files": files, "created": []}
                for name, g in reading.items():
                    self.assertEqual(passes(g, seen), not name.startswith(("leaves-", "writes-")), f"{name} on the seeded files")

    def test_the_orders_page_logs_a_baseline_only_before_orders_py_is_edited(self):
        """The `measured` grader reads baseline.log, so a run that edits orders.py and then measures, or measures nothing, leaves none."""
        run = ["import db, orders; db.seed('a', 3); orders.orders_page(type('R', (), {'account': 'a'}))"]
        cases = {"before any edit": (None, True), "after an edit": (False, False), "after an edit that is committed": (True, False)}
        for label, (commit, logged) in cases.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                work = self.build("performance-measures-first", Path(d))
                if commit is not None:
                    (work / "orders.py").write_text("# edited\n" + (work / "orders.py").read_text(encoding="utf-8"), encoding="utf-8")
                    if commit:
                        subprocess.run(["git", "commit", "-qam", "edit"], cwd=work, check=True, capture_output=True)
                subprocess.run([sys.executable, "-c", *run], cwd=work, check=True, capture_output=True)
                self.assertEqual((work / "baseline.log").is_file(), logged)
                if logged:
                    self.assertEqual((work / "baseline.log").read_text(encoding="utf-8"), "queries=7\n")

    def test_the_seeded_files_hold_what_the_prompt_says_about_them(self):
        with tempfile.TemporaryDirectory() as d:
            work = self.build("design-review-keep-fix-quick-win", Path(d))
            line = (work / "src/checkout/split.css").read_text(encoding="utf-8").splitlines()[17]
            self.assertIn("#c62828", line, "the review notes say line 18 holds the raw color")
        with tempfile.TemporaryDirectory() as d:
            work = self.build("incident-mitigates-first", Path(d))
            log = subprocess.run(["git", "log", "--format=%s"], cwd=work, capture_output=True, text=True, check=True).stdout
            self.assertIn("release 2026.09.28.3", log)
            self.assertIn("RATES[region]", (work / "checkout/tax.py").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            work = self.build("prototype-lint-becomes-spec-tests", Path(d))
            html = (work / "specs/SPEC-220/design/prototype.html").read_text(encoding="utf-8")
            for violation in ("#1a1a1a", "rgb(200, 30, 30)", "fonts.googleapis.com", "images.example.com", "Lorem ipsum", "Your Name", "TODO"):
                self.assertIn(violation, html)
            self.assertIn('<style id="tokens">', html)

    def test_a_practice_case_that_says_the_repository_uses_aidd_seeds_the_config(self):
        """Batch C3: debugging and resilience loaded no skill on a workspace with no config."""
        for name in ("debugging-reproduces-first", "resilience-exactly-once"):
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.assertTrue(front_matter(TEAM / name / "prompt.md")[1].strip().startswith("This repository uses aidd. "))
                work = self.build(name, Path(d))
                self.assertIn('aidd_version: "1.0.0"', (work / CONFIG).read_text(encoding="utf-8"))

    def test_a_prompt_that_says_the_repository_uses_aidd_seeds_the_config(self):
        """Batch C3: seven `loads-*` triggers loaded no skill, because the agent asked whether to apply aidd."""
        for case in triggers():
            with self.subTest(case.name), tempfile.TemporaryDirectory() as d:
                self.assertTrue(front_matter(case / "prompt.md")[1].strip().startswith("This repository uses aidd. "))
                work = self.build(case.name, Path(d))
                self.assertEqual(
                    re.findall(r'^aidd_version: "([\d.]+)"$', (work / CONFIG).read_text(encoding="utf-8"), re.M),
                    ["1.0.0"],
                )


if __name__ == "__main__":
    unittest.main()
