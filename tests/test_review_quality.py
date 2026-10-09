"""Review and test quality: what a finding must carry, the dismissed findings a later review leaves out, the challenge
of each security finding, and the cards that say why a test exists and when it may go."""

import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, make_repo

from aidd import config, globs, guard, packs, resources, rules

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
            for must in ("A person", "fingerprint", "path", "kind", "SHA-256", "line before it", "line number", "who", "why"):
                self.assertIn(must, dismissed, f"{path}: {must}")
            self.assertIn("`<file> | <kind> | <hash>`", dismissed, path)
            self.assertIn("`git show <base>:REVIEW.md`", dismissed, path)
            self.assertIn("never from the head", dismissed, path)
            self.assertIn("`- <file> | <kind> | <hash> | <who> | <date> | <why>`", dismissed, path)
            self.assertIn("16 lowercase hex characters", dismissed, path)
            self.assertIn("under the first line that reads exactly `## Dismissed findings`", dismissed, path)
            self.assertIn("a malformed dismissal line", dismissed, path)
            self.assertIn("anywhere in the file", dismissed, path)
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
            self.assertIn("`security` pool (`[owners.specialists]`", dismissed, path)
        merge = step(command("review"), 5)
        self.assertIn("Leave out a `security/` finding only when", merge)
        self.assertIn("`security` pool", merge)

    def test_no_schema_change(self):
        # The list lives in the policy file a person owns; the Spec's `decisions` field stays ADR paths.
        spec = json.loads(text(ROOT / "schemas" / "spec.schema.json"))
        self.assertEqual(spec["properties"]["decisions"]["items"], {"type": "string"})


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


@unittest.skipUnless(shutil.which("git"), "git is required")
class DismissalGuardTests(unittest.TestCase):
    """An agent never adds or changes a dismissal, in any shape, nor moves one under the heading the review reads."""

    EXACT = "- src/app.py | missing-test | 0123456789abcdef | @me | 2026-10-07 | covered by the e2e suite"
    VARIANTS = {
        "the exact form": EXACT,
        "a star": "* src/a.py | missing-test | 0123456789abcdef | @me | 2026-10-07 | why",
        "a plus": "+ src/a.py | missing-test | 0123456789abcdef | @me | 2026-10-07 | why",
        "no marker": "src/a.py | missing-test | 0123456789abcdef | @me | 2026-10-07 | why",
        "a number": "1. src/a.py | missing-test | 0123456789abcdef | @me | 2026-10-07 | why",
        "a number and a parenthesis": "2) src/a.py | missing-test | 0123456789abcdef",
        "tabs": "-\tsrc/a.py\t|\tmissing-test\t|\t0123456789abcdef\t|\t@me",
        "no spaces": "-src/a.py|missing-test|0123456789abcdef|@me",
        "fullwidth bars": "- src/a.py ｜ missing-test ｜ 0123456789abcdef ｜ @me",
        "12 hex": "- src/a.py | missing-test | 0123456789ab | @me",
        "64 hex": "- src/a.py | missing-test | " + "a" * 64 + " | @me",
        "upper case": "- src/a.py | missing-test | 0123456789ABCDEF | @me",
        "a backticked hash": "- `src/a.py` | missing-test | `0123456789abcdef` | @me",
        "a table row": "| src/a.py | missing-test | 0123456789abcdef |",
        "a table row with the hash first": "| 0123456789abcdef | src/a.py | missing-test |",
        "indented": "    - src/a.py | missing-test | 0123456789abcdef | @me",
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", branch=None)
        self.policy = self.root / "REVIEW.md"
        self.assertTrue(self.policy.is_file(), "aidd init wrote the review policy")
        self.base = self.policy.read_text(encoding="utf-8")

    def hook(self, tool: str, tool_input: dict, agent: str | None = "aidd-team:developer"):
        event = {"tool_name": tool, "tool_input": {"file_path": str(self.policy), **tool_input}}
        if agent:
            event["agent_type"] = agent
        return guard.check_agent_edit(str(self.root), "REVIEW.md", event)

    def write(self, content: str, agent: str | None = "aidd-team:developer"):
        return self.hook("Write", {"content": content}, agent)

    def listed(self, *lines: str, text: str | None = None) -> str:
        """The policy with `lines` in the list under `## Dismissed findings`."""
        t = self.base if text is None else text
        return t.replace("\n## Repository notes\n", "\n" + "".join(ln + "\n" for ln in lines) + "\n## Repository notes\n", 1)

    def denied(self, verdict, what):
        self.assertEqual(verdict[0], "deny", what)
        self.assertIn("only a person adds a dismissal", verdict[1], what)

    def not_this_rule(self, verdict, what):
        self.assertNotIn("only a person adds a dismissal", verdict[1], what)

    def test_the_exact_form(self):
        self.assertTrue(guard.DISMISSAL_EXACT.match(self.EXACT))
        for name, line in self.VARIANTS.items():
            if name != "the exact form":
                self.assertFalse(guard.DISMISSAL_EXACT.match(line), name)
        for bad in (self.EXACT.replace(" | ", "  | ", 1), self.EXACT + " ", self.EXACT.replace("2026-10-07", "7 Oct"), self.EXACT.replace("@me", "")):
            self.assertFalse(guard.DISMISSAL_EXACT.match(bad), bad)

    def test_every_variant_is_denied_anywhere(self):
        for name, line in self.VARIANTS.items():
            for where, content in (("in the list", self.listed(line)), ("at the end", self.base + "\n" + line + "\n"), ("at the top", line + "\n" + self.base)):
                self.denied(self.write(content), f"{name}, {where}")
        add = {"old_string": "\n## Repository notes\n", "new_string": "\n" + self.EXACT + "\n\n## Repository notes\n"}
        self.denied(self.hook("Edit", add), "an Edit")
        self.assertEqual(guard.reason_code(self.write(self.listed(self.EXACT))[1]), "review_dismissal")

    def test_unicode_line_breaks_do_not_split_a_line(self):
        # Git and a reader split only on a newline, so a U+2028, U+2029, or U+0085 inside a line must not hide it.
        digest = re.search(r"\b[0-9a-f]{16}\b", self.EXACT).group(0)
        for sep in (" ", " ", "\x85", "\x0b", "\x0c"):
            line = self.EXACT.replace(digest, sep + digest + sep, 1)  # no piece alone has both the bars and the hash
            self.denied(self.write(self.listed(line)), f"break {sep!r}")

    def test_heading_tricks_are_denied(self):
        t = self.base
        tricks = {
            "a second heading": t + "\n## Dismissed findings\n\n" + self.EXACT + "\n",
            "a renamed heading": self.listed(self.EXACT, text=t.replace("## Dismissed findings\n", "## Skipped findings\n", 1)),
            "a top-level heading inside the list": self.listed("# x", "", self.EXACT),
        }
        for name, content in tricks.items():
            self.denied(self.write(content), name)

    def test_changing_a_dismissal_is_denied(self):
        self.policy.write_text(self.listed(self.EXACT), encoding="utf-8")
        for old, new in (("@me", "@someone"), ("2026-10-07", "2026-10-08"), ("covered by the e2e suite", "not a bug"), ("missing-test", "security/xss")):
            self.denied(self.hook("Edit", {"old_string": self.EXACT, "new_string": self.EXACT.replace(old, new)}), f"{old} -> {new}")

    def test_moving_a_line_under_the_heading_is_denied(self):
        # A line that looks like a dismissal outside the list, which a person wrote, counts for nothing there.
        # Moving it under the heading, or taking away the heading between, makes the review honour it.
        outside = self.base + "\n" + self.EXACT + "\n"
        self.policy.write_text(outside, encoding="utf-8")
        self.denied(self.write(self.listed(self.EXACT)), "moved under the heading")
        self.denied(self.write(outside.replace("\n## Repository notes\n", "\n", 1)), "the heading between taken away")
        self.denied(
            self.write(outside.replace("## Dismissed findings\n", "## Notes\n", 1).replace("## Repository notes\n", "## Dismissed findings\n", 1)),
            "the heading moved",
        )
        # Under the list, a malformed line becomes exact: a change to what the review honours.
        malformed = self.EXACT.replace("- ", "* ", 1)
        self.policy.write_text(self.listed(malformed), encoding="utf-8")
        self.denied(self.hook("Edit", {"old_string": malformed, "new_string": self.EXACT}), "made exact")

    def test_other_edits_are_not_this_rule(self):
        second = "- src/b.py | missing-test | fedcba9876543210 | @me | 2026-10-07 | why"
        self.policy.write_text(self.listed(self.EXACT, second), encoding="utf-8")
        current = self.policy.read_text(encoding="utf-8")
        for name, verdict in (
            ("a removal", self.hook("Edit", {"old_string": self.EXACT + "\n", "new_string": ""})),
            ("a reorder inside the list", self.write(self.listed(second, self.EXACT))),
            (
                "a word in the explanation",
                self.hook("Edit", {"old_string": "so that the review of a later head", "new_string": "so the review of a later head"}),
            ),
            ("a nit limit", self.hook("Edit", {"old_string": "## Nits\n", "new_string": "## Nits\n\nAt most three nits.\n"})),
            ("a table row without a hash", self.write(current + "\n| module | reader |\n| --- | --- |\n| src/billing | @alice |\n")),
            ("a hash in prose", self.write(current + "\nThe flaky check started at commit 0123456789abcdef.\n")),
        ):
            self.not_this_rule(verdict, name)
        self.assertEqual(self.hook("Edit", {"old_string": "so that the review of a later head", "new_string": "so the review of a later head"})[0], "allow")
        self.not_this_rule(self.hook("Edit", {"old_string": "so that the review", "new_string": "so the review"}, "aidd-team:tech-writer"), "the tech writer")
        # The person's own session (no subagent) records it, as for an exploration's outcome.
        self.assertEqual(self.write(self.listed(self.EXACT, text=self.base), agent=None)[0], "allow")

    def test_a_write_the_guard_cannot_read_is_denied(self):
        """A shell write to REVIEW.md, or a tool that gives no new text, could add a dismissal the guard never sees: for
        a role it is denied, so the change goes through Edit or Write, where it can be checked."""
        import io
        import json

        bash = {"tool_name": "Bash", "tool_input": {"command": "echo x >> REVIEW.md"}, "agent_type": "aidd-team:developer", "cwd": str(self.root)}
        for rel in ("REVIEW.md", "review.md"):
            decision, reason = guard.check_agent_edit(str(self.root), rel, bash)
            self.assertEqual(decision, "deny", rel)
            self.assertIn("only a person adds a dismissal", reason)
            self.assertIn("use the Edit or Write tool so the change can be checked", reason)
            self.assertEqual(guard.reason_code(reason), "review_dismissal")
        notebook = {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": str(self.policy)}, "agent_type": "aidd-team:developer"}
        self.assertEqual(guard.check_agent_edit(str(self.root), "REVIEW.md", notebook)[0], "deny")
        for command in ("echo '- src/a.py | missing-test | 0123456789abcdef | @me' >> REVIEW.md", "sed -i.bak 's/x/y/' REVIEW.md", "cp /dev/null REVIEW.md"):
            out = io.StringIO()
            event = bash | {"tool_input": {"command": command}, "session_id": "s1", "hook_event_name": "PreToolUse"}
            guard.pre_tool_hook(io.StringIO(json.dumps(event)), out)
            answer = json.loads(out.getvalue())["hookSpecificOutput"]
            self.assertEqual(answer["permissionDecision"], "deny", command)
            self.assertIn("use the Edit or Write tool", answer["permissionDecisionReason"], command)
        # Other files are untouched by this rule, and the person's own session writes REVIEW.md as before.
        self.not_this_rule(guard.check_agent_edit(str(self.root), "docs/notes.md", bash), "another file")
        self.assertEqual(guard.check_agent_edit(str(self.root), "REVIEW.md", {k: v for k, v in bash.items() if k != "agent_type"})[0], "allow")
        # Through Edit or Write, the content rule still judges it: a harmless edit passes.
        self.assertEqual(self.hook("Edit", {"old_string": "so that the review of a later head", "new_string": "so the review of a later head"})[0], "allow")

    def test_review_md_is_held_in_a_sibling_worktree_too(self):
        """The REVIEW.md rules resolve the target with guard.locate, as every edit rule does: a role in this worktree
        that writes a sibling worktree's REVIEW.md meets the same rules there, by shell or by Edit."""
        import io
        import json

        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "policy", "--allow-empty"], cwd=self.root, check=True)
        sibling = self.root.parent / "sibling"
        subprocess.run(["git", "worktree", "add", "-q", str(sibling), "-b", "sibling"], cwd=self.root, check=True)
        target = sibling / "REVIEW.md"
        self.assertEqual(guard.locate(target).top, str(sibling))
        base = {"agent_type": "aidd-team:developer", "cwd": str(self.root), "session_id": "s1", "hook_event_name": "PreToolUse"}
        for event, why in (
            ({"tool_name": "Bash", "tool_input": {"command": f"echo x >> {shlex.quote(str(target))}"}}, "use the Edit or Write tool"),
            (
                {
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": str(target),
                        "old_string": "\n## Repository notes\n",
                        "new_string": "\n" + self.EXACT + "\n\n## Repository notes\n",
                    },
                },
                "only a person adds a dismissal",
            ),
        ):
            out = io.StringIO()
            guard.pre_tool_hook(io.StringIO(json.dumps(base | event)), out)
            answer = json.loads(out.getvalue())["hookSpecificOutput"]
            self.assertEqual(answer["permissionDecision"], "deny", event["tool_name"])
            self.assertIn(why, answer["permissionDecisionReason"], event["tool_name"])

    def test_review_md_is_not_a_protected_path(self):
        cfg = config.load_file(config.CONFIG_PATH, str(self.root))
        self.assertIsNone(globs.first_match(rules.protected_paths(cfg), "REVIEW.md", fold_case=True))


class SecurityChallengeTests(unittest.TestCase):
    """Before the human security pool sees them, a second read-only pass tries to refute each finding."""

    def test_the_secure_command_challenges_each_finding(self):
        page = command("secure")
        challenge = page.split("**Challenge", 1)[1]
        for must in (
            "read-only",
            "fresh `aidd-team:security-engineer` subagent",
            "writes no file",
            "refute",
            "evidence",
            "`file:line`",
            "Refuted",
            "the reason",
            "never drop",
        ):
            self.assertIn(must, challenge, must)
        # The challenge comes before the person, and the person still decides.
        self.assertLess(page.index("**Challenge"), page.index("The human reviewer from the security pool decides"))
        # The second pass is a role the flow already runs (test_team: a command names only its flow's roles).
        self.assertNotIn("`aidd-team:reviewer`", page)


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
        self.assertLessEqual(packs.estimate_tokens(text(self.REF)), packs.REFERENCE_TOKENS)

    def test_the_review_command_points_to_it(self):
        # The skill body is preloaded and at its budget, so the on-demand pointer lives in the review command.
        self.assertIn("references/test-value.md", step(command("review"), 4))

    def test_the_specify_command_points_the_tester_to_it(self):
        # The tester's preloaded skill cannot take the link, so the command that runs the tester carries it.
        tester = step(command("specify"), 7)
        self.assertIn("`aidd-team:tester`", tester)
        self.assertIn("value card", tester)
        self.assertIn("`references/test-value.md`", tester)


class OneQuoteFormTests(unittest.TestCase):
    """One form for a quote's place, `file:line`, in the policy and the commands."""

    def test_no_path_line(self):
        for page in (*POLICIES, *(TEAM / "commands" / f"{c}.md" for c in ("review", "fix", "secure"))):
            self.assertNotIn("path:line", text(page), page)


if __name__ == "__main__":
    unittest.main()
