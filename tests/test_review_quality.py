"""Review and test quality: what a finding must carry, the dismissed findings a later review leaves out, the challenge
of each security finding, and the cards that say why a test exists and when it may go."""

import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, says

from aidd.docsgen import token_caps
from aidd.kernel import resources
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
TEMPLATE = resources.data_dir("templates") / "REVIEW.md"
POLICIES = (TEMPLATE, ROOT / "REVIEW.md")


def text(path) -> str:
    return path.read_text(encoding="utf-8")


def command(name: str) -> str:
    return text(TEAM / "commands" / f"{name}.md")


def section(page: str, heading: str) -> str:
    return page.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]


def step(page: str, number: int) -> str:
    """The text of a numbered step of a command's own steps (after the lead rules), up to the next step."""
    body = page.split("$ARGUMENTS", 1)[1].split(f"\n{number}. ", 1)[1]
    return body.split(f"\n{number + 1}. ", 1)[0]


class ConfidenceAndQuoteTests(unittest.TestCase):
    """Every finding carries a confidence and a quote of its code; an unquoted one goes to an appendix, capped at 4."""

    def test_the_review_policy_states_the_rule(self):
        for path in POLICIES:
            rule = section(text(path), "Confidence and quotes")
            for must in ("confidence from 1 to 10", "`file:line`", "at most 4", "appendix", "never in the main list"):
                self.assertIn(must, rule, f"{path}: {must}")

    def test_the_review_command_merges_by_it(self):
        merge = step(command("review"), 5)
        for must in ("confidence (1 to 10)", "`file:line` quote", "appendix", "at most 4"):
            self.assertIn(must, merge, must)

    def test_the_fix_command_cuts_the_reviewer_report_by_it(self):
        reviewer_step = next(ln for ln in command("fix").splitlines() if "`aidd-team:reviewer`" in ln)
        for must in ("confidence (1 to 10)", "`file:line` quote", "appendix", "at most 4"):
            self.assertIn(must, reviewer_step, must)


class DismissedFindingTests(unittest.TestCase):
    """A person's dismissal is recorded by fingerprint, read from the base branch, and left out of the next review."""

    def test_the_review_policy_has_the_list_and_its_fingerprint(self):
        for path in POLICIES:
            dismissed = section(text(path), "Dismissing a finding")
            for must in ("A person", "fingerprint", "path", "type", "SHA-256", "line before it", "line number", "who", "why"):
                self.assertIn(must, dismissed, f"{path}: {must}")
            self.assertIn("`<file> | <type> | <hash>`", dismissed, path)
            self.assertIn("`git show <base>:REVIEW.md`", dismissed, path)
            self.assertIn("never from the head", dismissed, path)
            self.assertIn("`- <file> | <type> | <hash> | <who> | <date> | <why>`", dismissed, path)
            self.assertIn("16 lowercase hex characters", dismissed, path)
            self.assertTrue(says(dismissed, "first line", "exactly", "`## Dismissed findings`"), path)
            self.assertIn("a malformed dismissal line", dismissed, path)
            self.assertIn("ignores every other line", dismissed, path)
            # The list itself holds no explanation, so every other line in it is a malformed dismissal line.
            listed = [ln for ln in section(text(path), "Dismissed findings").splitlines() if ln.strip()]
            self.assertEqual(len(listed), 1, path)
            self.assertRegex(listed[0], r"^<!--.*-->$", path)

    def test_the_review_command_reads_the_base_branch_copy(self):
        read = step(command("review"), 2)
        self.assertIn("Dismissed findings", read)
        self.assertIn("`git show <base>:REVIEW.md`", read)
        self.assertIn("never from the head", read)
        merge = step(command("review"), 5)
        self.assertIn("in the exact form REVIEW.md gives", merge)
        self.assertIn("under the first `## Dismissed findings` heading of the base branch's REVIEW.md", merge)
        self.assertIn("a malformed dismissal line", merge)

    def test_the_review_command_leaves_out_matches_and_lists_them(self):
        page = command("review")
        merge = step(page, 5)
        for must in ("fingerprint", "Leave out", "List the fingerprints you left out", "how many"):
            self.assertIn(must, merge, must)
        self.assertIn("never add one yourself", merge, "only a person dismisses a finding")

    def test_the_review_flags_a_change_to_the_list(self):
        merge = step(command("review"), 5)
        self.assertIn("When the diff changes `## Dismissed findings`, put that first in the report", merge)

    def test_the_fix_command_does_the_same(self):
        reviewer_step = next(ln for ln in command("fix").splitlines() if "`aidd-team:reviewer`" in ln)
        for must in (
            "Dismissed findings",
            "`git show <base>:REVIEW.md`",
            "never the head",
            "under the first `## Dismissed findings` heading",
            "exact form",
            "a malformed dismissal line",
            "List the fingerprints you left out",
            "Flag a diff that changes that section",
            "never add one yourself",
            "`security/`",
        ):
            self.assertIn(must, reviewer_step, must)

    def test_a_security_dismissal_needs_the_security_pool(self):
        for path in POLICIES:
            dismissed = section(text(path), "Dismissing a finding")
            self.assertIn("starts with `security/`", dismissed, path)
            self.assertIn("`security` pool (`owners.specialists`", dismissed, path)
        merge = step(command("review"), 5)
        self.assertIn("Leave out a `security/` finding only when", merge)
        self.assertIn("a person who reviews security", merge)

    def test_no_schema_change(self):
        # The list lives in the policy file a person owns; the Spec's `decisions` field stays ADR paths.
        spec = json.loads(text(ROOT / "schemas" / "spec.schema.json"))
        self.assertEqual(spec["properties"]["adrs"]["items"], {"type": "string"})


class FingerprintRecipeTests(unittest.TestCase):
    """The one command REVIEW.md gives a person for the hash: run as written, on real files."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        recipes = {re.search(r"```sh\n(.*?)\n```", section(text(p), "Dismissing a finding"), re.S).group(1) for p in POLICIES}
        self.assertEqual(len(recipes), 1, "the template and aidd's own REVIEW.md give one recipe")
        self.recipe = recipes.pop()
        self.assertTrue(self.recipe.endswith(" <file> <n>"), self.recipe)

    def hash_of(self, lines: list[str], n: int) -> str:
        f = self.dir / f"f{len(list(self.dir.iterdir()))}.py"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cmd = shlex.split(self.recipe.removesuffix(" <file> <n>")) + [str(f), str(n)]
        out = subprocess.run([sys.executable if c == "python3" else c for c in cmd], capture_output=True, text=True, check=True).stdout.strip()
        self.assertRegex(out, r"^[0-9a-f]{16}$")
        return out

    def run_recipe(self, lines: list[str], n: str) -> subprocess.CompletedProcess:
        f = self.dir / "g.py"
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cmd = shlex.split(self.recipe.removesuffix(" <file> <n>")) + [str(f), n]
        return subprocess.run([sys.executable if c == "python3" else c for c in cmd], capture_output=True, text=True)

    def test_a_line_number_below_1_is_refused(self):
        for n in ("0", "-1"):
            done = self.run_recipe(["a = 1", "b = 2"], n)
            self.assertNotEqual(done.returncode, 0, n)
            self.assertEqual(done.stdout, "", n)
            self.assertIn("line number", done.stderr, n)
            self.assertIn("1 or more", done.stderr, n)
            self.assertNotIn("Traceback", done.stderr, n)

    def test_the_same_line_in_its_context_matches(self):
        base = self.hash_of(["def f(x):", "    return eval(x)"], 2)
        # Moved down, and re-indented: no line number, and spaces are normalized.
        self.assertEqual(self.hash_of(["import os", "", "def f(x):", "  return   eval(x)  "], 4), base)
        self.assertRegex(self.hash_of(["first = 1"], 1), r"^[0-9a-f]{16}$")

    def test_the_same_80_character_prefix_does_not_match(self):
        prefix = "query = 'SELECT * FROM users WHERE id = ' + request.args['id'] + ' AND tenant = '"
        self.assertGreaterEqual(len(prefix), 80)
        a = self.hash_of(["def f(request):", prefix + "tenant_id"], 2)
        b = self.hash_of(["def f(request):", prefix + "request.args['t']"], 2)
        self.assertNotEqual(a, b)

    def test_an_identical_line_in_another_context_does_not_match(self):
        a = self.hash_of(["def public(x):", "    return eval(x)"], 2)
        b = self.hash_of(["def admin_only(x):", "    return eval(x)"], 2)
        self.assertNotEqual(a, b)


class SecurityChallengeTests(unittest.TestCase):
    """Before the human security pool sees them, a second read-only pass tries to refute each security finding, on the
    one path a security review takes: the review command's security engineer."""

    def test_the_review_command_challenges_each_security_finding(self):
        page = command("review")
        challenge = step(page, 4).split("**Challenge", 1)[1]  # inside step 4, so before the report step 5 builds
        for must in (
            "read-only",
            "fresh `aidd-team:security-engineer` subagent",
            "writes no file",
            "refute",
            "evidence",
            "`file:line`",
            "stays",
            "Refuted",
            "Needs validation",
            "the reason",
            "never drop",
            "original severity",
        ):
            self.assertIn(must, challenge, must)
        self.assertNotIn("`aidd-team:reviewer`", challenge, "the second pass is the security engineer again, never the reviewer")
        # A refutation demotes a finding only once the lead confirms it on the reviewed head, with the tree untouched.
        for must in (
            "`git status --porcelain --ignored`",
            "noted SHA",
            "the same output as you recorded",
            "git show <sha>:<path>",
            "git worktree add --detach <tmp> <sha>",
            "unconfirmed refutation",
        ):
            self.assertIn(must, challenge, must)
        # Ignored files such as caches make the output rarely empty, so it is recorded with the SHA and compared, never expected empty.
        self.assertNotIn("is empty", challenge)
        self.assertIn("`git status --porcelain --ignored`", step(page, 1))
        # The person who reviews security decides, after the challenge.
        self.assertIn("The person who reviews security decides", challenge)

    def test_the_report_carries_all_three_outcomes(self):
        report = step(command("review"), 5)
        kept, refuted, needs = (report.index(w) for w in ("kept findings", '"Refuted"', '"Needs validation"'))
        self.assertLess(kept, refuted)
        self.assertLess(refuted, needs)
        self.assertIn("original severity", report)
        # The Merge approval question names both counts, so a person sees what the challenge moved aside.
        self.assertIn("how many findings are under Refuted and how many under Needs validation", report)

    def test_a_person_can_ask_for_the_security_review(self):
        readers = step(command("review"), 3)
        security = readers.split("`aidd-team:security-engineer`", 1)[1].split("\n   - the ", 1)[0]
        for must in ("`risk_rules`", "a person asks", "references/security-findings.md", "six parts", "what it covered"):
            self.assertIn(must, security, must)
        role = team_registry.roles()["roles"]["security-engineer"]
        starts = role["starts_when"]
        self.assertIn("`risk_rules`", starts)
        self.assertIn("a person asks", starts)
        # A person's request works with no Spec too, and only the request starts it there, never a path or an AI change.
        self.assertIn("minor", role["routes"])
        # "No Spec" is the minor route only: the emergency route also has no Spec, and its area triggers still hold.
        self.assertIn("On the minor route (no Spec), only a person's request starts it", starts)
        self.assertIn("On the minor route (no Spec), start it only when a person asks", security)
        for text_ in (starts, security):
            self.assertIn("still hold on the emergency route", text_)
        # A library bump that adds no package skips the review by choice; dependency scanning covers a compromised release.
        self.assertIn("dependency scanning", security)
        # One dependency rule in both: a version bump that adds no package and changes no other integrity skips it.
        self.assertNotIn("`dependencies` area", starts)
        self.assertIn("lockfile integrity", starts)
        self.assertIn("lockfile's integrity", security)

    def test_every_threat_model_command_names_its_spec(self):
        # `aidd new threat-model <component>` exits 2 without `--spec`, so no text gives the form that fails.
        for path in (ROOT / ".agents/skills/aidd/references/spec-returns.md", ROOT / "schemas/roles.json", TEAM / "agents/security-engineer.md"):
            for m in re.finditer(r"aidd new threat-model <component>[^`]*`", text(path)):
                self.assertIn("--spec <ID>", m.group(0), path.name)

    def test_the_security_engineer_knows_its_challenge_pass(self):
        playbook = text(TEAM / "agents" / "security-engineer.md").split("## Playbook", 1)[1].lower()
        for must in ("challenge", "refute", "writes no file", "never drop", "needs validation"):
            self.assertIn(must, playbook, must)

    def test_no_second_command_runs_a_security_review(self):
        self.assertFalse((TEAM / "commands" / "secure.md").exists())


class TestValueCardTests(unittest.TestCase):
    """An on-demand reference in test-design with a value card and a retirement card."""

    REF = TEAM / "skills" / "test-design" / "references" / "test-value.md"

    def test_the_cards(self):
        page = text(self.REF)
        value = section(page, "Test value card").lower()
        for must in ("failure it prevents", "how it fails today", "cost"):
            self.assertIn(must, value, must)
        retire = section(page, "Retirement card").lower()
        for must in ("evidence", "passing test", "decides", "a person"):
            self.assertIn(must, retire, must)

    def test_it_fits_the_reference_cap(self):
        self.assertLessEqual(token_caps.estimate_tokens(text(self.REF)), token_caps.REFERENCE_TOKENS)

    def test_the_review_command_points_to_it(self):
        # The skill body is preloaded and at its budget, so the on-demand pointer lives in the review command.
        self.assertIn("references/test-value.md", step(command("review"), 4))

    def test_the_specify_command_points_the_tester_to_it(self):
        # The verifier's preloaded skill cannot take the link, so the command that runs the verifier carries it.
        verifier = step(command("specify"), 7)
        self.assertIn("`aidd-team:verifier`", verifier)
        self.assertIn("value card", verifier)
        self.assertIn("`references/test-value.md`", verifier)


class OneQuoteFormTests(unittest.TestCase):
    """One form for a quote's place, `file:line`, in the policy and the commands."""

    def test_no_path_line(self):
        for page in (*POLICIES, *(TEAM / "commands" / f"{c}.md" for c in ("review", "fix"))):
            self.assertNotIn("path:line", text(page), page)


if __name__ == "__main__":
    unittest.main()
