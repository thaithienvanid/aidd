"""Environments by branch or tag (`environments` in the config): a push to an environment's branch or tag is
`deploy.run` to that environment, a rule with `environment` sets its level, and the harness ask rules name the
branches and tags of each environment that asks. A config without `environments` behaves as before."""

from __future__ import annotations

import dataclasses
import json
import re
import tempfile
import unittest

import helpers  # noqa: F401  # the hermetic environment
from aidd import config, risk
from aidd.config import loading
from aidd.kernel import globs, json_schema
from aidd.risk import commands, harness_rules

ENVIRONMENTS = (
    "environments:\n"
    '  - {name: production, branches: [prod], tags: ["v*"]}\n'
    '  - {name: staging, branches: ["release/*"], tags: ["*-rc*"]}\n'
    "  - {name: dev, branches: [dev]}\n"
)
LOWER_DEV = "risks:\n  rules:\n    - {action: deploy.run, environment: dev, level: report}\n"


# Pushes aidd asks before, as `git push <words>`: to an environment's branch or tag, by name, by ref, with a flag
# after the branch or the remote, and to the default branch, with force, and as a deletion.
PUSHES = (
    "origin prod",
    "origin prod --no-verify",
    "origin HEAD:prod",
    "origin HEAD:prod --no-verify",
    "origin refs/heads/prod",
    "origin release/2.0",
    "origin release/2.0 --no-verify",
    "origin feat prod",
    "origin v1",
    "origin refs/tags/v1",
    "origin HEAD:refs/tags/v2",
    "origin 2.0-rc1",
    "origin stable",
    "origin stable --no-verify",
    "origin refs/tags/stable",
    "origin refs/tags/stable --no-verify",
    "--tags origin",
    "origin --tags",
    "--follow-tags origin",
    "origin --follow-tags",
    "--follow-tags",
    "--all origin",
    "--mirror origin",
    "origin main",
    "origin main --no-verify",
    "origin HEAD:main",
    "origin refs/heads/main",
    "--force origin feat",
    "origin feat --force",
    "-f origin feat",
    "--delete origin feat",
    "origin --delete feat",
)


def harness_matches(fmt: str, pattern: str, line: str) -> bool:
    """Whether the rule a harness holds for `pattern` asks before `line`, by that harness's own matcher: a glob as it
    reads one, a regular expression, or leading words."""
    match = risk.FORMATS[fmt].match
    if match == "regex":
        return re.fullmatch(harness_rules.glob_regex(pattern), line) is not None
    if match == "words":
        words = harness_rules.codex_words(pattern, list(harness_rules.COMMON_REMOTES)) or harness_rules.leading_words(pattern) or []
        said = line.split()
        return any(said[: len(prefix.split())] == prefix.split() for prefix in harness_rules._expanded(words))
    form = harness_rules.claude_code_form(pattern) if fmt in ("claude-code", "grok") else pattern
    return form is not None and globs.match_text(form, line)


def cfg(text: str = "") -> config.Config:
    return config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + text)


class APushToAnEnvironment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = cls.tmp.name
        helpers.git(cls.root, "init", "-q", "-b", "main")
        helpers.git(cls.root, "commit", "-q", "--allow-empty", "-m", "base")
        helpers.git(cls.root, "tag", "v1")
        helpers.git(cls.root, "tag", "2.0-rc1")
        helpers.git(cls.root, "switch", "-qc", "feat")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_which_branch_and_environments_a_push_reaches(self):
        envs = cfg(ENVIRONMENTS).get("environments")
        cases = [
            ("git push origin prod", None, ["production"]),
            ("git push origin HEAD:prod", None, ["production"]),
            ("git push origin +refs/heads/prod", None, ["production"]),
            ("git push origin release/2.0", None, ["staging"]),
            ("git push origin release/2.0/hotfix", "shared", []),  # `*` stays inside one segment
            ("git push origin dev", None, ["dev"]),
            ("git push origin dev/login", "shared", []),  # a name with no wildcard is that ref only
            ("git push origin prod-old", "shared", []),
            ("git push origin v1", None, ["production"]),
            ("git push origin refs/tags/v1", None, ["production"]),
            ("git push origin 2.0-rc1", None, ["staging"]),
            ("git push origin HEAD:refs/tags/v2", None, ["production"]),
            ("git push origin HEAD:refs/tags/nightly", "shared", []),
            ("git push origin feat prod", "own", ["production"]),
            ("git push origin prod main", "default", ["production"]),
            ("git push origin feat", "own", []),
            ("git push", "own", []),
            ("git push --tags origin", "own", ["production", "staging"]),
            ("git push --all origin", "default", ["production", "staging", "dev"]),
            ("git push --follow-tags origin", "own", ["production", "staging"]),
            ("git push --mirror origin", "default", ["production", "staging", "dev"]),
            # A deletion deploys nothing: it stays a push to a shared branch.
            ("git push origin :dev", "shared", []),
            ("git push --delete origin dev", "shared", []),
            ("git push -d origin prod", "shared", []),
            ("git status", None, []),
        ]
        for line, branch, deployed in cases:
            with self.subTest(line=line):
                self.assertEqual(commands.push_reach(line, self.root, envs), (branch, deployed))

    def test_without_environments_a_push_reads_as_before(self):
        for line, want in (("git push origin prod", "shared"), ("git push origin v1", "shared"), ("git push origin feat", "own")):
            with self.subTest(line=line):
                self.assertEqual(commands.push_reach(line, self.root), (want, []))
                self.assertEqual(commands.push_branch(line, self.root), want)

    def test_the_level_of_a_push_to_an_environment(self):
        lowered = risk.rule_set(cfg(ENVIRONMENTS + LOWER_DEV))
        plain = risk.rule_set(cfg())
        # A rule for every deploy, naming no environment, never lowers a push: only a rule that names the environment does.
        generic = risk.rule_set(cfg(ENVIRONMENTS + "risks:\n  rules:\n    - {action: deploy.run, level: report}\n"))
        # A parent config's locked `git.push` rule still decides a push to a lowered environment.
        locked = risk.rule_set(cfg(ENVIRONMENTS + LOWER_DEV))
        locked.rules = [dataclasses.replace(r, locked=True) if r.selector == ("git.push", None, "shared", None, None) else r for r in locked.rules]
        shared_ask = ("git.push", "shared", None, "ask")
        cases = [
            # (rule set, command line, level, the actions it reads as)
            (lowered, "git push origin prod", "ask", [shared_ask, ("deploy.run", None, "production", "ask")]),
            (lowered, "git push origin dev", "report", [("deploy.run", None, "dev", "report")]),
            (lowered, "git push origin v1", "ask", [shared_ask, ("deploy.run", None, "production", "ask")]),
            (lowered, "git push origin dev/login", "ask", [shared_ask]),
            (lowered, "git push origin feat", "allow", [("git.push", "own", None, "allow")]),
            (lowered, "git push origin feat dev", "report", [("git.push", "own", None, "allow"), ("deploy.run", None, "dev", "report")]),
            (lowered, "git push -f origin dev", "ask", [("deploy.run", None, "dev", "report"), ("git.push.force", "shared", None, "ask")]),
            (lowered, "git push origin :dev", "ask", [shared_ask, ("git.branch.delete", None, None, "ask")]),
            (generic, "git push origin prod", "ask", [shared_ask, ("deploy.run", None, "production", "report")]),
            (locked, "git push origin dev", "ask", [shared_ask, ("deploy.run", None, "dev", "report")]),
            (plain, "git push origin dev", "ask", [shared_ask]),
            (plain, "git push origin prod", "ask", [shared_ask]),
        ]
        for rs, line, level, actions in cases:
            with self.subTest(line=line, environments=bool(rs.environments)):
                answer = risk.command_level(rs, line, cwd=self.root)
                self.assertEqual(answer["level"], level)
                self.assertEqual([(a["action"], a["branch"], a["environment"], a["level"]) for a in answer["actions"]], actions)

    def test_the_harness_asks_wherever_aidd_asks_before_a_push(self):
        """A control's property, not a list: each push `aidd risk` asks before matches a harness pattern, so dropping a
        form, such as a flag after the branch or the remote, fails here. Each harness's own matcher must then catch the
        line through every pattern it holds that matches it. The second rule set lowers the actions whose patterns also
        catch an environment's push, so only the environment's own patterns can match."""
        envs = ENVIRONMENTS + "  - {name: canary, tags: [stable]}\n"
        alone = LOWER_DEV + "    - {action: release.publish, level: report}\n    - {action: git.push, branch: shared, level: report}\n"
        lines = [f"git push {where}" for where in PUSHES]
        for rules in (LOWER_DEV, alone):
            rs = risk.rule_set(cfg(envs + rules))
            patterns, asked = risk.harness_patterns(rs, "main"), 0
            for line in lines:
                if risk.command_level(rs, line, cwd=self.root)["level"] != "ask":
                    continue
                asked += 1
                matched = [p for p in patterns if globs.match_text(p, line)]
                with self.subTest(line=line, rules=rules):
                    self.assertTrue(matched, f"aidd asks before {line!r}, and no harness pattern matches it")
                    for fmt in risk.FORMATS:
                        held = [p for p in matched if p not in risk.unwritten(fmt, [p])]
                        self.assertEqual([p for p in held if not harness_matches(fmt, p, line)], [], f"{fmt} holds these and misses {line!r}")
            self.assertGreaterEqual(asked, 24, "the table must reach the pushes that ask")

    def test_the_rule_names_the_environment(self):
        answer = risk.command_level(risk.rule_set(cfg(ENVIRONMENTS + LOWER_DEV)), "git push origin dev", cwd=self.root)
        self.assertEqual(answer["actions"][0]["rule"], "deploy.run to dev: report")
        self.assertEqual(json_schema.validate({"schema_version": "1"} | answer, "risk.schema.json"), [])

    def test_an_environment_rule_decides_only_its_own_environment(self):
        rs = risk.rule_set(cfg(ENVIRONMENTS + LOWER_DEV))
        cases = [({"environment": "dev"}, "report"), ({"environment": "production"}, "ask"), ({}, "ask")]
        for narrow, want in cases:
            with self.subTest(**narrow):
                self.assertEqual(risk.level_of(rs, "deploy.run", **narrow)[0], want)


class AParentsLockedEnvironment(unittest.TestCase):
    def test_a_child_cannot_move_the_branches_a_locked_rule_covers(self):
        """The parent locks `deploy.run` to production; a child that renames production's branch keeps the parent's."""
        parent = {
            "environments": [{"name": "production", "branches": ["prod"]}],
            "risks": {"rules": [{"action": "deploy.run", "environment": "production", "level": "ask", "locked": True}]},
        }
        child = {"environments": [{"name": "production", "branches": ["no-such-branch"]}, {"name": "dev", "branches": ["dev"]}]}
        warnings: list[str] = []
        merged = loading.merge(parent, child, "child", warnings)
        self.assertEqual(merged["environments"], [{"name": "production", "branches": ["prod"]}, {"name": "dev", "branches": ["dev"]}])
        self.assertIn("environments production is named by a rule a parent config locked", warnings[0])
        # Without a lock, the child's list replaces the parent's.
        parent["risks"]["rules"][0]["locked"] = False
        self.assertEqual(loading.merge(parent, child, "child", [])["environments"], child["environments"])


class TheHarnessAsksAtAnEnvironment(unittest.TestCase):
    def test_an_environment_that_asks_gets_patterns_and_a_lowered_one_none(self):
        patterns = risk.harness_patterns(risk.rule_set(cfg(ENVIRONMENTS + LOWER_DEV)), "main")
        for p in (
            "git push * prod",
            "git push * *:prod",
            "git push * release/*",
            "git push * v*",
            "git push * refs/tags/*-rc*",
            "git push * tags/v*",
            "git push --tags*",
        ):
            with self.subTest(pattern=p):
                self.assertIn(p, patterns)
        self.assertFalse([p for p in patterns if p.split()[-1] in ("dev", "*:dev")], "a lowered environment writes no ask rule")

    def test_without_environments_the_patterns_are_unchanged(self):
        self.assertEqual(risk.harness_patterns(risk.rule_set(cfg()), "main"), risk.harness_patterns(risk.rule_set(None), "main"))
        self.assertNotIn("git push * prod", risk.harness_patterns(risk.rule_set(cfg()), "main"))

    def test_claude_code_writes_them(self):
        with tempfile.TemporaryDirectory() as d:
            from pathlib import Path

            risk.apply_harness_rules(Path(d), "claude-code", risk.harness_patterns(risk.rule_set(cfg(ENVIRONMENTS)), "main"))
            ask = json.loads((Path(d) / ".claude" / "settings.json").read_text())["permissions"]["ask"]
            self.assertIn("Bash(git push * prod)", ask)
            self.assertIn("Bash(git push * dev)", ask)  # not lowered here, so it asks


class TheConfigChecksEnvironments(unittest.TestCase):
    def test_an_environment_needs_a_name_and_a_branch_or_a_tag(self):
        cases = [
            ("environments:\n  - {name: production, branches: [prod]}\n", True),
            ("environments:\n  - {name: production, tags: ['v*']}\n", True),
            ("environments:\n  - {name: production}\n", False),
            ("environments:\n  - {branches: [prod]}\n", False),
            ("environments:\n  - {name: Production, branches: [prod]}\n", False),
            ("environments:\n  - {name: production, branches: []}\n", False),
            ("environments:\n  - {name: production, branches: ['a:b']}\n", False),
            ("risks:\n  rules:\n    - {action: deploy.run, environment: dev, level: report}\n", True),
            ("risks:\n  rules:\n    - {action: deploy.run, environment: Dev, level: report}\n", False),
        ]
        for text, ok in cases:
            with self.subTest(text=text):
                if ok:
                    cfg(text)
                else:
                    with self.assertRaises(config.ConfigError):
                        cfg(text)


if __name__ == "__main__":
    unittest.main()
