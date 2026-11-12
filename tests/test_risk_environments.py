"""Environments by branch or tag (`environments` in the config): a push to an environment's branch or tag is
`deploy.run` to that environment, a rule with `environment` sets its level, and the harness ask rules name the
branches and tags of each environment that asks. A config without `environments` behaves as before."""

from __future__ import annotations

import dataclasses
import json
import re
import tempfile
import unittest

import helpers
import shared_reads
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
# The developer's own environment (`shared: false`), beside one marked shared and one unmarked.
OWN_ENVIRONMENTS = (
    "environments:\n"
    '  - {name: production, branches: [prod], tags: ["v*"]}\n'
    '  - {name: staging, branches: ["release/*"], shared: true}\n'
    '  - {name: preview, branches: ["preview/*"]}\n'
    "  - {name: dev, branches: [dev], shared: false}\n"
)


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


class APushToAnEnvironment(shared_reads.ReadOnlyRepoCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = cls.tmp.name
        helpers.git(cls.root, "init", "-q", "-b", "main")
        helpers.git(cls.root, "commit", "-q", "--allow-empty", "-m", "base")
        helpers.git(cls.root, "tag", "v1")
        helpers.git(cls.root, "tag", "2.0-rc1")
        helpers.git(cls.root, "switch", "-qc", "feat")
        cls.share_reads()

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

    def test_an_empty_list_of_environments_reads_as_none_for_a_push_and_the_delegate_check_tells_them_apart(self):
        """`environments: []` says nothing deploys from a push. The rules treat it as none, so a push still asks as
        `git.push`; only a delegated merge reads the difference from an unset list (tests/test_delegation_check.py)."""
        empty, unset = cfg("environments: []\n"), cfg()
        self.assertEqual(empty.get("environments"), [])
        self.assertIsNone(unset.get("environments"))
        self.assertEqual(risk.rule_set(empty).environments, risk.rule_set(unset).environments)
        for line in ("git push origin prod", "git push origin main"):
            self.assertEqual(
                commands.push_reach(line, self.root, risk.rule_set(empty).environments), commands.push_reach(line, self.root, risk.rule_set(unset).environments)
            )
            self.assertEqual(
                risk.command_level(risk.rule_set(empty), line, cwd=self.root)["level"], risk.command_level(risk.rule_set(unset), line, cwd=self.root)["level"]
            )

    def test_the_level_of_a_push_to_an_environment(self):
        lowered = risk.rule_set(cfg(ENVIRONMENTS + LOWER_DEV))
        plain = risk.rule_set(cfg())
        # A rule for every deploy, naming no environment, never lowers a push: only a rule that names the environment does.
        generic = risk.rule_set(cfg(ENVIRONMENTS + "risks:\n  rules:\n    - {action: deploy.run, level: report}\n"))
        # A parent config's locked `git.push` rule still decides a push to a lowered environment.
        locked = risk.rule_set(cfg(ENVIRONMENTS + LOWER_DEV))
        locked.rules = [
            dataclasses.replace(r, locked=True) if r.selector == ("git.push", None, "shared") + (None,) * (len(config.SELECTOR) - 3) else r
            for r in locked.rules
        ]
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
        line through every pattern it holds that matches it. The second and third rule sets lower the actions whose
        patterns also catch an environment's push, so only the environment's own patterns can match. The third marks dev
        as the developer's own, and the last two keep a push there asking, by a lock or by a rule for every deploy."""
        envs = ENVIRONMENTS + "  - {name: canary, tags: [stable]}\n"
        alone = LOWER_DEV + "    - {action: release.publish, level: report}\n    - {action: git.push, branch: shared, level: report}\n"
        lines = [f"git push {where}" for where in PUSHES]
        own = OWN_ENVIRONMENTS + "  - {name: canary, tags: [stable]}\n" + alone.replace(LOWER_DEV, "risks:\n  rules:\n")
        every_ref = OWN_ENVIRONMENTS + "  - {name: canary, tags: [stable, '*-rc*']}\n"
        locked = risk.rule_set(cfg(every_ref))
        locked.rules = [dataclasses.replace(r, locked=r.selector[:3] == ("git.push", None, "shared")) for r in locked.rules]
        rule_sets = {
            "lowered": risk.rule_set(cfg(envs + LOWER_DEV)),
            "alone": risk.rule_set(cfg(envs + alone)),
            "own": risk.rule_set(cfg(own)),
            "locked": locked,
            "generic": risk.rule_set(cfg(every_ref + "risks:\n  rules:\n    - {action: deploy.run, level: report}\n")),
        }
        mine = ["git push origin preview/login", "git push origin dev prod", "git push origin dev", "git push origin feat dev"]
        for name, rs in rule_sets.items():
            patterns, asked = risk.harness_patterns(rs, "main"), 0
            for line in lines + (mine if name in ("own", "locked", "generic") else []):
                if risk.command_level(rs, line, cwd=self.root)["level"] != "ask":
                    continue
                asked += 1
                matched = [p for p in patterns if globs.match_text(p, line)]
                with self.subTest(line=line, config=name):
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


class ADeployToYourOwnEnvironment(shared_reads.ReadOnlyRepoCase):
    """An environment the config marks `shared: false` is the developer's own, so a deploy there reports. Every other
    environment, staging and production included, and a deploy whose environment aidd cannot name, still asks."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = cls.tmp.name
        helpers.git(cls.root, "init", "-q", "-b", "main")
        helpers.git(cls.root, "commit", "-q", "--allow-empty", "-m", "base")
        helpers.git(cls.root, "tag", "v1")
        helpers.git(cls.root, "switch", "-qc", "feat")
        cls.share_reads()

    def test_the_level_of_a_deploy_by_environment(self):
        own = risk.rule_set(cfg(OWN_ENVIRONMENTS))
        raised = risk.rule_set(cfg(OWN_ENVIRONMENTS + "risks:\n  rules:\n    - {action: deploy.run, environment: dev, level: ask}\n"))
        raised_all = risk.rule_set(cfg(OWN_ENVIRONMENTS + "risks:\n  rules:\n    - {action: deploy.run, environment_shared: false, level: ask}\n"))
        # A shared environment that names the same branch keeps the push asking.
        overlap = risk.rule_set(cfg(OWN_ENVIRONMENTS + "  - {name: qa, branches: [dev]}\n"))
        # A parent config's locked rule still decides: `git.push` to a shared branch, or every deploy.
        locked_push = risk.rule_set(cfg(OWN_ENVIRONMENTS))
        locked_push.rules = [dataclasses.replace(r, locked=r.selector[:3] == ("git.push", None, "shared")) for r in locked_push.rules]
        locked_deploy = risk.rule_set(cfg(OWN_ENVIRONMENTS))
        locked_deploy.rules = [dataclasses.replace(r, locked=r.selector == ("deploy.run",) + (None,) * (len(config.SELECTOR) - 1)) for r in locked_deploy.rules]
        # A rule for every deploy names no environment, so it never lowers a push, whatever the push names first.
        generic = risk.rule_set(cfg(OWN_ENVIRONMENTS + "risks:\n  rules:\n    - {action: deploy.run, level: report}\n"))
        # A wildcard glob can match other people's branches, so only the branch checked out gives way to it.
        wide = risk.rule_set(cfg("environments:\n  - {name: preview, branches: ['*'], tags: ['dev-*'], shared: false}\n"))
        shared_ask = ("git.push", "shared", None, "ask")
        cases = [
            # (rule set, command line, level, the actions it reads as)
            (own, "git push origin dev", "report", [("deploy.run", None, "dev", "report")]),
            (own, "git push origin feat dev", "report", [("git.push", "own", None, "allow"), ("deploy.run", None, "dev", "report")]),
            (own, "git push origin release/2.0", "ask", [shared_ask, ("deploy.run", None, "staging", "ask")]),
            (own, "git push origin preview/login", "ask", [shared_ask, ("deploy.run", None, "preview", "ask")]),
            (own, "git push origin prod", "ask", [shared_ask, ("deploy.run", None, "production", "ask")]),
            (own, "git push origin v1", "ask", [shared_ask, ("deploy.run", None, "production", "ask")]),
            (own, "git push origin dev prod", "ask", [shared_ask, ("deploy.run", None, "dev", "report"), ("deploy.run", None, "production", "ask")]),
            (own, "git push -f origin dev", "ask", [("deploy.run", None, "dev", "report"), ("git.push.force", "shared", None, "ask")]),
            (own, "git push origin :dev", "ask", [shared_ask, ("git.branch.delete", None, None, "ask")]),
            (own, "kubectl apply -f deploy.yaml", "ask", [("deploy.run", None, None, "ask")]),
            (own, "vercel deploy --prod", "ask", [("deploy.run", None, None, "ask")]),
            (raised, "git push origin dev", "ask", [("deploy.run", None, "dev", "ask")]),
            (raised_all, "git push origin dev", "ask", [("deploy.run", None, "dev", "ask")]),
            (overlap, "git push origin dev", "ask", [shared_ask, ("deploy.run", None, "dev", "report"), ("deploy.run", None, "qa", "ask")]),
            (locked_push, "git push origin dev", "ask", [shared_ask, ("deploy.run", None, "dev", "report")]),
            (locked_deploy, "git push origin dev", "ask", [shared_ask, ("deploy.run", None, "dev", "ask")]),
            # Abuse cases: a push with several refspecs never steps past a lock, or past an environment no rule names.
            (locked_push, "git push origin feat dev", "ask", [shared_ask, ("deploy.run", None, "dev", "report")]),
            (locked_push, "git push origin HEAD dev", "ask", [shared_ask, ("deploy.run", None, "dev", "report")]),
            (generic, "git push origin feat prod", "ask", [shared_ask, ("deploy.run", None, "production", "report")]),
            (wide, "git push origin teammate", "ask", [shared_ask, ("deploy.run", None, "preview", "report")]),
            (wide, "git push origin HEAD:refs/tags/dev-1", "ask", [shared_ask, ("deploy.run", None, "preview", "report")]),
            (wide, "git push origin feat", "report", [("deploy.run", None, "preview", "report")]),
            (wide, "git push origin HEAD", "report", [("deploy.run", None, "preview", "report")]),
            (wide, "git push", "report", [("deploy.run", None, "preview", "report")]),
        ]
        for rs, line, level, actions in cases:
            with self.subTest(line=line):
                answer = risk.command_level(rs, line, cwd=self.root)
                self.assertEqual(answer["level"], level)
                self.assertEqual([(a["action"], a["branch"], a["environment"], a["level"]) for a in answer["actions"]], actions)

    def test_a_force_push_that_also_names_your_branch_reads_as_shared(self):
        """Abuse cases: a force push to your own environment reads as one to a shared branch, and naming the branch
        checked out beside it changes nothing, with the parent's lock (b2) or without it (b1)."""
        own_force = OWN_ENVIRONMENTS + "risks:\n  rules:\n    - {action: git.push.force, branch: own, level: allow}\n"
        unlocked = risk.rule_set(cfg(own_force))
        locked = risk.rule_set(cfg(own_force + "    - {action: git.push.force, branch: shared, level: ask}\n"))
        locked.rules = [dataclasses.replace(r, locked=r.selector[:3] == ("git.push.force", None, "shared")) for r in locked.rules]
        for name, rs in (("b1", unlocked), ("b2", locked)):
            for line in ("git push -f origin dev", "git push -f origin feat dev", "git push -f origin HEAD dev"):
                with self.subTest(case=name, line=line):
                    answer = risk.command_level(rs, line, cwd=self.root)
                    self.assertEqual(answer["level"], "ask")
                    self.assertEqual([a["branch"] for a in answer["actions"] if a["action"] == "git.push.force"], ["shared"])

    def test_only_an_environment_marked_your_own_reports(self):
        own, plain = risk.rule_set(cfg(OWN_ENVIRONMENTS)), risk.rule_set(None)
        # A name the config holds twice, once shared, reads as shared.
        twice = risk.rule_set(cfg(OWN_ENVIRONMENTS + "  - {name: dev, tags: [nightly]}\n"))
        cases = [
            (own, "dev", "report"),
            (own, "staging", "ask"),
            (own, "preview", "ask"),
            (own, "production", "ask"),
            (own, None, "ask"),
            (own, "no-such-environment", "ask"),
            (plain, "dev", "ask"),
            (twice, "dev", "ask"),
        ]
        for rs, env, want in cases:
            with self.subTest(environment=env, config=bool(rs.environments)):
                self.assertEqual(risk.level_of(rs, "deploy.run", environment=env)[0], want)
        rule = risk.level_of(own, "deploy.run", environment="dev")[1]
        self.assertEqual(rule.label() if rule else None, "deploy.run to your own environment: report")

    def test_the_harness_asks_at_every_environment_but_your_own(self):
        patterns = risk.harness_patterns(risk.rule_set(cfg(OWN_ENVIRONMENTS)), "main")
        for p in ("git push * prod", "git push * release/*", "git push * preview/*", "git push * v*"):
            with self.subTest(pattern=p):
                self.assertIn(p, patterns)
        self.assertIn("kubectl apply*", patterns)
        # Every harness reads the same patterns, so none holds one that asks before a deploy to your own environment.
        for fmt in risk.FORMATS:
            held = [p for p in patterns if p not in risk.unwritten(fmt, [p])]
            with self.subTest(harness=fmt):
                self.assertFalse([p for p in held if harness_matches(fmt, p, "git push origin dev")], "your own environment writes no ask rule")


class AParentsLockedEnvironment(shared_reads.ReadOnlyRepoCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = cls.tmp.name
        helpers.git(cls.root, "init", "-q", "-b", "main")
        helpers.git(cls.root, "commit", "-q", "--allow-empty", "-m", "base")
        helpers.git(cls.root, "switch", "-qc", "feat")
        cls.share_reads()

    def test_a_child_cannot_lower_a_push_its_parent_locked(self):
        """Abuse cases: the parent locks every deploy to a shared environment, or one environment it lists twice. A child
        that marks that environment its own, or replaces the list with its own environment on the same branch, keeps the
        parent's entries, so the push still asks."""
        head = 'aidd_version: "1.0.0"\nprofile: solo\n'
        release, tags = {"name": "production", "branches": ["release"]}, {"name": "production", "tags": ["v*"]}
        preview = {"name": "preview", "branches": ["release"], "shared": False}
        shared_lock = "risks:\n  rules:\n    - {action: deploy.run, environment_shared: true, level: ask, locked: true}\n"
        named_lock = "risks:\n  rules:\n    - {action: deploy.run, environment: production, level: ask, locked: true}\n"
        one, twice = "environments:\n  - {name: production, branches: [release]}\n", "  - {name: production, tags: ['v*']}\n"
        flip = "environments:\n  - {name: production, branches: [release], shared: false}\n"
        replace = "environments:\n  - {name: preview, branches: [release], shared: false}\n"
        cases = [
            # (parent, child, the environments in force, whether the child is warned)
            (one + shared_lock, flip, [release], True),
            (one + shared_lock, replace, [release, preview], False),
            (one + twice + named_lock, replace, [release, tags, preview], False),
            (one + twice + named_lock, flip, [release, tags], True),
        ]
        for parent, child, envs, warned in cases:
            with self.subTest(parent=parent, child=child):
                loaded = config.load_text(head + "extends: [{path: parent.yaml}]\n" + child, read={"parent.yaml": head + parent}.get)
                rs = risk.rule_set(loaded)
                self.assertEqual(rs.environments, envs)
                self.assertEqual(any("environments production" in w for w in loaded.warnings), warned)
                self.assertEqual(risk.command_level(rs, "git push origin release", cwd=self.root)["level"], "ask")

    def test_a_lock_that_holds_no_environment_is_warned(self):
        """Abuse cases: a parent locks a rule for an environment it never defines (e1), or for whether one is shared while
        it defines none (e2). A child would then decide what the lock covers, so the load warns."""
        head = 'aidd_version: "1.0.0"\nprofile: solo\n'
        named = "risks:\n  rules:\n    - {action: deploy.run, environment: production, level: ask, locked: true}\n"
        shared = "risks:\n  rules:\n    - {action: deploy.run, environment_shared: true, level: ask, locked: true}\n"
        defined = "environments:\n  - {name: production, branches: [release]}\n"
        child = "environments:\n  - {name: production, branches: [release], shared: false}\n"
        cases = [
            # (case, parent, whether the load warns)
            ("e1", named, True),
            ("e2", shared, True),
            ("e1 defined", defined + named, False),
            ("e2 defined", defined + shared, False),
        ]
        for case, parent, warned in cases:
            with self.subTest(case):
                loaded = config.load_text(head + "extends: [{path: parent.yaml}]\n" + child, read={"parent.yaml": head + parent}.get)
                self.assertEqual(any("no parent config defines" in w for w in loaded.warnings), warned, loaded.warnings)

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
        self.assertIn("environments production is covered by a rule a parent config locked", warnings[0])
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
    def test_your_own_environment_with_a_wildcard_glob_is_warned(self):
        cases = [
            # (an environment, the globs the config check names)
            ("{name: dev, branches: [dev], tags: [dev-1], shared: false}", []),
            ("{name: preview, branches: ['*'], shared: true}", []),
            ("{name: preview, branches: ['preview/*']}", []),
            ("{name: dev, branches: [dev, 'dev/*'], tags: ['dev-*'], shared: false}", ["dev/*", "dev-*"]),
        ]
        for env, named in cases:
            with self.subTest(env=env):
                warnings = [w for w in cfg(f"environments:\n  - {env}\n").warnings if "shared: false" in w]
                self.assertEqual(len(warnings), len(named))
                for glob, warning in zip(named, warnings, strict=True):
                    self.assertIn(repr(glob), warning)
                    # A tag is never checked out, so its warning says only that it never gives way.
                    self.assertEqual("checked out" in warning, "/" in glob)

    def test_the_wildcard_warning_names_the_file_that_defines_the_environment(self):
        head = 'aidd_version: "1.0.0"\nprofile: solo\n'
        parent = head + "environments:\n  - {name: dev, branches: ['dev/*'], shared: false}\n"
        loaded = config.load_text(head + "extends: [{path: parent.yaml}]\n", read={"parent.yaml": parent}.get)
        warnings = [w for w in loaded.warnings if "shared: false" in w]
        self.assertEqual(len(warnings), 1)
        self.assertIn("in parent.yaml", warnings[0])

    def test_an_environment_needs_a_name_and_a_branch_or_a_tag(self):
        cases = [
            ("environments:\n  - {name: production, branches: [prod]}\n", True),
            ("environments:\n  - {name: production, tags: ['v*']}\n", True),
            ("environments:\n  - {name: production}\n", False),
            ("environments:\n  - {branches: [prod]}\n", False),
            ("environments:\n  - {name: Production, branches: [prod]}\n", False),
            ("environments:\n  - {name: production, branches: []}\n", False),
            ("environments:\n  - {name: production, branches: ['a:b']}\n", False),
            ("environments:\n  - {name: dev, branches: [dev], shared: false}\n", True),
            ("environments:\n  - {name: dev, branches: [dev], shared: true}\n", True),
            # A value or a key written by mistake stops the config, so it never lowers a deploy.
            ("environments:\n  - {name: dev, branches: [dev], shared: 'false'}\n", False),
            ("environments:\n  - {name: dev, branches: [dev], own: true}\n", False),
            ("risks:\n  rules:\n    - {action: deploy.run, environment_shared: false, level: ask}\n", True),
            ("risks:\n  rules:\n    - {action: deploy.run, environment_shared: 'no', level: ask}\n", False),
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
