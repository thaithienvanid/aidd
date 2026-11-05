"""The risk rules: which rule wins, what a command line is, the route for planned paths, how a config changes the
rules, and the harness ask rules `aidd init` writes. Table-driven: each case is one row of what a person would ask."""

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from aidd import config, risk


def cfg(text: str = "") -> config.Config:
    return config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + text)


class WhichRuleWins(unittest.TestCase):
    def test_built_in_levels(self):
        rs = risk.rule_set(None)
        cases = [
            ("code.edit", {}, "allow"),
            ("code.edit", {"area": "payments"}, "ask"),
            ("code.edit", {"area": "ci"}, "report"),
            ("git.push", {"branch": "own"}, "allow"),
            ("git.push", {"branch": "default"}, "ask"),
            ("git.push.force", {}, "ask"),
            ("pr.open", {}, "report"),
            ("pr.merge", {}, "ask"),
            ("deploy.run", {}, "ask"),
            ("migration.run", {}, "ask"),
            ("migration.run.local", {}, "report"),
            ("migration.rollback", {}, "ask"),
            ("no.such.action", {}, "allow"),
        ]
        for action, narrow, want in cases:
            with self.subTest(action=action, **narrow):
                self.assertEqual(risk.level_of(rs, action, **narrow)[0], want)

    def test_most_specific_wins_then_higher(self):
        rs = risk.rule_set(
            cfg(
                "risks:\n  rules:\n"
                "    - {action: 'git.*', level: ask}\n"
                "    - {action: git.commit, level: allow}\n"
                "    - {action: 'pr.*', level: report}\n"
                "    - {action: pr.open, area: payments, level: ask}\n"
            )
        )
        self.assertEqual(risk.level_of(rs, "git.commit")[0], "allow")  # exact over a prefix
        self.assertEqual(risk.level_of(rs, "git.tag.create")[0], "ask")  # the built-in exact rule
        self.assertEqual(risk.level_of(rs, "pr.open")[0], "report")  # the built-in exact rule says report too
        self.assertEqual(risk.level_of(rs, "pr.open", area="payments")[0], "ask")  # an exact action narrowed by an area

    def test_a_config_lowers_and_raises_a_built_in(self):
        rs = risk.rule_set(cfg("risks:\n  rules:\n    - {action: pr.open, level: allow}\n    - {action: code.edit, area: dependencies, level: ask}\n"))
        self.assertEqual(risk.level_of(rs, "pr.open")[0], "allow")
        self.assertEqual(risk.level_of(rs, "code.edit", area="dependencies")[0], "ask")
        self.assertEqual(risk.level_of(rs, "pr.open")[1].source, "config")

    def test_a_locked_parent_rule_keeps_its_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "preset.yaml").write_text(
                'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: git.push.force, level: ask, locked: true}\n'
            )
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(
                'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: preset.yaml}]\nrisks:\n  rules:\n    - {action: git.push.force, level: allow}\n'
            )
            c = config.load_file(config.CONFIG_PATH, tmp)
        rs = risk.rule_set(c)
        self.assertEqual(risk.level_of(rs, "git.push.force")[0], "ask")
        self.assertTrue(any("locked" in w for w in c.warnings))

    def test_no_child_gets_past_a_locked_rule(self):
        """A narrower rule, a middle preset that restates the rule, and a redefined area all leave the lock in force."""
        preset = (
            'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n'
            "    - {action: git.push.force, level: ask, locked: true}\n    - {action: code.edit, area: payments, level: ask, locked: true}\n"
        )
        middle = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: preset.yaml}]\nrisks:\n  rules:\n    - {action: git.push.force, level: ask}\n'
        child = (
            'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: middle.yaml}]\nrisks:\n'
            "  areas:\n    payments: {paths: [nothing/**], route: minor}\n"
            "  rules:\n    - {action: git.push.force, level: allow}\n    - {action: git.push.force, branch: own, level: allow}\n"
            "    - {action: code.edit, area: payments, role: developer, level: allow}\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "preset.yaml").write_text(preset)
            (root / "middle.yaml").write_text(middle)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(child)
            c = config.load_file(config.CONFIG_PATH, tmp)
        rs = risk.rule_set(c)
        self.assertEqual(risk.level_of(rs, "git.push.force")[0], "ask")  # restated by the middle preset: still locked
        self.assertEqual(risk.level_of(rs, "git.push.force", branch="own")[0], "ask")  # a narrower child rule loses
        self.assertEqual(risk.level_of(rs, "code.edit", area="payments", role="developer")[0], "ask")
        self.assertEqual(risk.edit_level(rs, ["src/payments/charge.py"])[0], "ask")  # the area keeps its paths
        self.assertTrue(any("risks.areas payments" in w for w in c.warnings), c.warnings)

    def test_each_rule_names_the_preset_it_came_from(self):
        """A rule says where a person changes it: the preset that set it, the one that locked it, or the repository."""
        preset = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: git.push.force, level: ask, locked: true}\n'
        middle = (
            'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: preset.yaml}]\nrisks:\n  rules:\n'
            "    - {action: git.push.force, level: ask}\n    - {action: pr.open, level: report}\n"
        )
        child = 'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: middle.yaml}]\nrisks:\n  rules:\n    - {action: pr.merge, level: ask}\n'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "preset.yaml").write_text(preset)
            (root / "middle.yaml").write_text(middle)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(child)
            c = config.load_file(config.CONFIG_PATH, tmp)
        rs = risk.rule_set(c)
        for action, source in (("git.push.force", "preset preset.yaml"), ("pr.open", "preset middle.yaml"), ("pr.merge", "config")):
            with self.subTest(action=action):
                self.assertEqual(risk.level_of(rs, action)[1].source, source)
        self.assertNotIn("_source", str(c.raw))
        actions = {a["action"]: a for a in risk.command_level(rs, "git push --force origin x")["actions"]}
        self.assertEqual(actions["git.push.force"]["source"], "preset preset.yaml")

    def test_a_presets_name_is_shown_safely(self):
        """A preset's URL loses its user, password, and query, which may hold a token, and nothing reaches the terminal
        as a control character; a repository file named `org preset` is no org preset."""
        preset = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: pr.open, level: report}\n'
        url = "https://ada:pw@example.com/presets/aidd.yaml?private_token=abc#x"
        pin = hashlib.sha256(preset.encode()).hexdigest()
        child = f'aidd_version: "1.0.0"\nprofile: team\nextends: [{{url: "{url}", sha256: "{pin}"}}, {{path: "org preset"}}]\n'
        c = config.load_text(child, prefetched={url: preset, "org preset": preset.replace("pr.open", "pr.merge")})
        rs = risk.rule_set(c)
        self.assertEqual(risk.level_of(rs, "pr.open")[1].source, "preset https://example.com/presets/aidd.yaml")
        self.assertEqual(risk.level_of(rs, "pr.merge")[1].source, "preset org preset")

    def test_a_childs_own_lock_never_outranks_a_parents(self):
        preset = 'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {action: git.push.force, level: ask, locked: true}\n'
        child = (
            'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: preset.yaml}]\nrisks:\n  rules:\n'
            "    - {action: git.push.force, branch: own, level: allow, locked: true}\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "preset.yaml").write_text(preset)
            (root / ".aidd").mkdir()
            (root / ".aidd" / "config.yaml").write_text(child)
            c = config.load_file(config.CONFIG_PATH, tmp)
        self.assertEqual(risk.level_of(risk.rule_set(c), "git.push.force", branch="own")[0], "ask")
        self.assertTrue(any("cannot lock" in w for w in c.warnings), c.warnings)

    def test_a_parents_lock_on_a_prefix_covers_each_action_it_matches(self):
        for pattern in ("git.*", "*"):
            with self.subTest(pattern=pattern), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "preset.yaml").write_text(
                    f'aidd_version: "1.0.0"\nprofile: team\nrisks:\n  rules:\n    - {{action: "{pattern}", level: ask, locked: true}}\n'
                )
                (root / ".aidd").mkdir()
                (root / ".aidd" / "config.yaml").write_text(
                    'aidd_version: "1.0.0"\nprofile: team\nextends: [{path: preset.yaml}]\nrisks:\n'
                    '  actions:\n    git.push.force: {description: x, commands: ["git push --nothing-matches-this"]}\n'
                    "  rules:\n    - {action: git.push, level: allow, locked: true}\n"
                )
                c = config.load_file(config.CONFIG_PATH, tmp)
                rs = risk.rule_set(c)
                self.assertEqual(risk.level_of(rs, "git.push", branch="default")[0], "ask")
                self.assertIn("git push --force*", rs.actions["git.push.force"]["commands"])  # the redefinition is ignored
                self.assertTrue(any("cannot lock" in w for w in c.warnings), c.warnings)

    def test_a_config_adds_an_area_and_an_action(self):
        rs = risk.rule_set(
            cfg(
                "risks:\n  areas:\n    billing: {paths: ['src/billing/**'], route: major}\n"
                "  actions:\n    cloud.resource.create: {commands: ['terraform apply*']}\n"
                "  rules:\n    - {action: code.edit, area: billing, level: ask}\n    - {action: cloud.resource.create, level: ask}\n"
            )
        )
        self.assertEqual(risk.edit_level(rs, ["src/billing/charge.py"])[0], "ask")
        self.assertEqual(risk.command_level(rs, "terraform apply -auto-approve")["level"], "ask")


class WhatACommandIs(unittest.TestCase):
    def test_commands(self):
        rs = risk.rule_set(None)
        cases = [
            ("git status", "allow"),
            ("git commit -m x", "allow"),
            ("git push --force origin feat", "ask"),
            ("git -C repo -c a=b push -f", "ask"),
            ("make test && git push origin +feat", "ask"),
            ("FOO=1 git push --force-with-lease", "ask"),
            ("gh pr create --fill", "report"),
            ("gh pr merge 12 --squash", "ask"),
            # A listener every device on the network reaches reports; one on 127.0.0.1 alone is no action.
            ("aidd prototype --serve --lan", "report"),
            ("aidd prototype docs/design/x.html --lan --serve --port 9000", "report"),
            ("python3 plugins/aidd-team/tools/prototype/prototype.py serve --lan", "report"),
            ('python3 "$TOOL" serve specs/SPEC-12/design/prototype.html --lan', "report"),  # the tool's README form
            ("aidd prototype --serve", "allow"),
            # A workflow run by hand reports; one that releases or deploys asks, since it attests or ships a build.
            ("gh workflow run ci.yml --ref feat", "report"),
            ("gh workflow run release.yml --ref main", "ask"),
            ("gh workflow run deploy-prod.yml", "ask"),
            ("gh api repos/o/r/actions/workflows/release.yml/dispatches -f ref=main", "ask"),
            # By its display name too, in any of the three common cases, and by a repository dispatch.
            ("gh workflow run Release", "ask"),
            ('gh workflow run "Publish to PyPI"', "ask"),
            ("gh workflow run DEPLOY.yml", "ask"),
            ("gh api repos/o/r/dispatches -f event_type=release", "ask"),
            ("gh run rerun 123", "report"),
            # Creating a check run asks too; reading one never does.
            ("gh api repos/o/r/check-runs -f name=tests -f head_sha=abc", "ask"),
            ("gh api repos/o/r/commits/abc/check-runs", "allow"),
            ("gh api -f name=tests repos/o/r/check-runs", "ask"),  # a field before the path is a write too
            ("gh api -XPOST repos/o/r/check-runs", "ask"),
            ("gh api graphql -F query=@q.graphql", "ask"),  # a query from a file may hold a mutation
            ('gh api graphql -f query="mutation { x }"', "ask"),
            ('gh api graphql -f query="query { viewer { login } }"', "allow"),
            ('gh api -f query="mutation { x }" graphql', "ask"),  # the endpoint after the fields
            ("gh api --input q.json graphql", "ask"),
            # Posting a commit status asks, since a check's result is CI's to report; reading the statuses does not.
            ("gh api repos/o/r/statuses/ab12cd -f state=success -f context=tests", "ask"),
            ('gh api -X POST "repos/{owner}/{repo}/statuses/$SHA" -f state=success', "ask"),
            ("gh api repos/o/r/commits/ab12cd/statuses", "allow"),
            ("gh api repos/o/r/commits/ab12cd/status", "allow"),
            ("glab ci trigger", "report"),
            ("rm -rf build", "ask"),
            ("echo 'git push --force'", "allow"),
            ("terraform plan", "allow"),
            ("terraform apply", "ask"),
            ("git push -d origin old", "ask"),
            ("git push --delete origin old", "ask"),
            ("git push origin -d old", "ask"),
            # A forward migration on the agent's own database reports; one that rewinds, drops, or is forced asks.
            ("php artisan migrate", "report"),
            ("alembic upgrade head", "report"),
            ("php artisan migrate --step --force", "ask"),
            ("php artisan migrate:refresh", "ask"),
            ("php artisan migrate:fresh --seed", "ask"),
            ("flyway clean", "ask"),
            # Any runner and any option order, and a production setting typed before the command.
            ("RAILS_ENV=production bin/rails db:migrate", "ask"),
            ("bundle exec rails db:drop", "ask"),
            ("uv run alembic -c alembic.ini downgrade base", "ask"),
            ("flyway -cleanDisabled=false clean", "ask"),
            ("npx wrangler d1 migrations apply DB --remote", "ask"),
            ("RAILS_ENV=production bin/rails assets:precompile", "allow"),
            # Work git cannot get back, and a push of every tag; a local rebase or amend needs a force push to publish.
            ("git clean -fdx", "ask"),
            ("git clean -n", "allow"),
            ("git stash drop", "ask"),
            ("git restore .", "ask"),
            ("git push origin --tags", "ask"),
            ("git rebase main", "allow"),
            ("git commit --amend --no-edit", "allow"),
            # Every tag command asks, since a harness cannot tell a listing from a release; so does each way of
            # pushing tags, abbreviated, set by `-c`, or through gh's built-in alias.
            ("git tag 1.2.0", "ask"),
            ("git tag -l", "ask"),
            ("git push origin --tag", "ask"),
            ("git push --fol", "ask"),
            ("git -c push.followTags=true push", "ask"),
            ("git -c user.name=x -c Push.FOLLOWTAGS=true push", "ask"),
            ("git -c remote.origin.push=refs/*:refs/* push", "ask"),
            ("git -c remote.origin.mirror=true push", "ask"),
            ("git --attr-source HEAD push --tags", "ask"),
            ("gh release new v1", "ask"),
            # A read or a message that names a risky word is not the command.
            ('git commit -m "fix the db:drop task"', "allow"),
            ("rg -n migrate:fresh docs", "allow"),
            ("git log --grep=db:rollback", "allow"),
            ("php artisan migrate:status", "allow"),
            # A migrate that names a target may reverse migrations.
            ("rails db:migrate VERSION=0", "ask"),
            ("python manage.py migrate shop 0003", "ask"),
            ("uv run python manage.py migrate --noinput", "report"),
            ("alembic downgrade -1", "ask"),
            ("npx prisma migrate deploy", "ask"),
            ("python manage.py migrate shop zero", "ask"),
            ("wrangler d1 migrations apply db --remote", "ask"),
        ]
        for line, want in cases:
            with self.subTest(line=line):
                self.assertEqual(risk.command_level(rs, line, branch="own")["level"], want)

    def test_a_push_to_the_default_branch_asks(self):
        rs = risk.rule_set(None)
        self.assertEqual(risk.command_level(rs, "git push origin main", branch="default")["level"], "ask")
        self.assertEqual(risk.command_level(rs, "git push origin feat", branch="own")["level"], "allow")

    def test_a_line_splits_only_outside_quotes(self):
        from aidd.risk import commands

        cases = [
            ("a && b || c ; d | e\nf", ["a", "b", "c", "d", "e", "f"]),
            ("echo 'a && b' && c", ["echo 'a && b'", "c"]),
            ('echo "a \\" ; b" ; c', ['echo "a \\" ; b"', "c"]),
            ("echo a\\;b ; c", ["echo a\\;b", "c"]),
            ("  ;; a ;  ", ["a"]),
        ]
        for line, want in cases:
            with self.subTest(line=line):
                self.assertEqual(commands.split(line), want)

    def test_a_command_reads_as_git_sees_it(self):
        from aidd.risk import commands

        cases = [
            ("git --no-pager --git-dir=.git -C repo push -f", "git push -f"),
            ("/usr/bin/git -c user.name=x push", "git push"),
            ("A=1 B=2 git push", "git push"),
            ("git push 'unbalanced", "git push 'unbalanced"),  # shlex refuses it: the words as typed
            ("make   test", "make test"),
        ]
        for line, want in cases:
            with self.subTest(line=line):
                self.assertEqual(commands.normalize(line), want)

    def test_the_branch_a_push_reaches(self):
        from aidd.risk import commands

        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(commands.push_branch("git push", d))  # not a repository: git cannot tell
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "commit", "-q", "--allow-empty", "-m", "base")
            cases = [
                ("git status", None),
                ("git push", "default"),  # HEAD on the default branch
                ("git push origin HEAD:main", "default"),
                ("git push origin +main", "default"),
                ("git push origin refs/heads/main", "default"),
                ("git push origin feat", "shared"),  # not the branch checked out: whose it is, aidd cannot tell
                ("git push --all origin", "default"),
                ("git push --mirror origin", "default"),
            ]
            for line, want in cases:
                with self.subTest(line=line):
                    self.assertEqual(commands.push_branch(line, d), want)
            helpers.git(d, "switch", "-qc", "feat")
            self.assertEqual(commands.push_branch("git push", d), "own")
            self.assertEqual(commands.push_branch("git push origin HEAD", d), "own")
            self.assertEqual(commands.push_branch("git push origin feat", d), "own")
            self.assertEqual(commands.push_branch("git push origin feat other", d), "shared")
            # A tag lands under refs/tags/ whatever name it is pushed as, never on the agent's branch.
            helpers.git(d, "tag", "v1")
            for line in (
                "git push origin v1",
                "git push origin v1:HEAD",
                "git push origin v1:feat",
                "git push origin refs/tags/v1:feat",
                "git push origin tags/v1:feat",
            ):
                with self.subTest(line=line):
                    self.assertEqual(commands.push_branch(line, d), "shared")


class TheRouteForPlannedPaths(unittest.TestCase):
    def test_routes(self):
        cases = [
            (["README.md"], "feat", "minor"),
            (["src/app.py"], "fix", "minor"),
            (["src/billing/charge.py"], "feat", "major"),
            (["src/auth/login.py"], "feat", "major"),
            (["db/migrations/0002_add.sql"], "feat", "major"),
            (["package.json"], "deps", "normal"),
            ([".github/workflows/ci.yml"], "chore", "normal"),
            (["AGENTS.md"], "docs", "normal"),
            (["src/app.py"], "security", "major"),
            (["infra/main.tf"], "infra", "normal"),
        ]
        for paths, ctype, want in cases:
            with self.subTest(paths=paths, change_type=ctype):
                self.assertEqual(risk.advice(cfg(), paths, change_type=ctype)["route"], want)

    def test_spec_approval_follows_the_profile(self):
        solo, team = cfg(), config.load_text('aidd_version: "1.0.0"\nprofile: team\n')
        self.assertEqual(risk.spec_approval_level(solo, "normal"), "report")
        self.assertEqual(risk.spec_approval_level(solo, "major"), "ask")
        self.assertEqual(risk.spec_approval_level(team, "normal"), "ask")
        self.assertEqual(risk.spec_approval_level(team, "minor"), "allow")

    def test_a_fast_lane_change_in_an_ask_area_asks_once(self):
        a = risk.advice(
            cfg("risks:\n  areas:\n    copy: {paths: ['site/**'], route: minor}\n  rules:\n    - {action: code.edit, area: copy, level: ask}\n"),
            ["site/index.html"],
        )
        self.assertEqual((a["lane"], a["edit"]["level"]), ("fast", "ask"))
        self.assertIn("ask before the first edit", a["step"])


class TheBuiltInData(unittest.TestCase):
    def test_every_rule_names_a_known_action_area_and_level(self):
        data = risk.builtin()
        for r in data["rules"]:
            with self.subTest(rule=r):
                self.assertIn(r["action"], data["actions"])
                self.assertIn(r["level"], data["levels"])
                self.assertTrue(r.get("area") is None or r["area"] in data["areas"])

    def test_a_tool_that_runs_commands_in_every_worktree_is_agent_configuration(self):
        for path in ("orca.yaml", ".worktreeinclude", ".config/wt.toml"):
            with self.subTest(path=path):
                self.assertIn("agent_config", risk.route_for(risk.rule_set(None), [path]).areas)

    def test_the_agent_config_area_holds_every_harness_path(self):
        from aidd.kernel import globs

        area = risk.builtin()["areas"]["agent_config"]["paths"]
        missing = [p for p in config.harness_paths() if not globs.match_any(area, globs.literal_form(p))]
        self.assertEqual(missing, [])

    def test_the_schema_validates_the_data(self):
        from aidd.kernel import json_schema

        self.assertEqual(json_schema.validate(risk.builtin(), "risks.schema.json"), [])


class TheHarnessAskRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patterns = risk.harness_patterns(risk.rule_set(None), "main")

    def test_claude_code_keeps_a_persons_own_rules(self):
        settings = self.root / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"permissions": {"ask": ["Bash(npm publish*)"], "allow": ["Bash(ls)"]}}))
        risk.apply_harness_rules(self.root, "claude-code", self.patterns)
        data = json.loads(settings.read_text())
        self.assertIn("Bash(git push --force*)", data["permissions"]["ask"])
        self.assertIn("Bash(git push * main)", data["permissions"]["ask"])
        self.assertEqual(data["permissions"]["allow"], ["Bash(ls)"])
        self.assertEqual(risk.apply_harness_rules(self.root, "claude-code", self.patterns), [])  # a second run changes nothing
        risk.remove_harness_rules(self.root)
        self.assertEqual(json.loads(settings.read_text())["permissions"]["ask"], ["Bash(npm publish*)"])  # the person's own stays

    def test_opencode_and_codex(self):
        risk.apply_harness_rules(self.root, "opencode", self.patterns)
        risk.apply_harness_rules(self.root, "codex", self.patterns)
        bash = json.loads((self.root / "opencode.json").read_text())["permission"]["bash"]
        self.assertEqual(bash["git push --force*"], "ask")
        rules = (self.root / ".codex" / "rules" / "aidd.rules").read_text()
        self.assertIn('prefix_rule(pattern = ["git", "push", "--force"], decision = "prompt")', rules)
        self.assertNotIn("+*", rules)  # a pattern with a star inside has no prefix form
        # Uninstall: a dry run says what it would take out and writes nothing; then everything aidd wrote goes.
        before = (self.root / "opencode.json").read_text()
        said = risk.remove_harness_rules(self.root, write=False)
        self.assertTrue(any("would remove" in s for s in said), said)
        self.assertEqual((self.root / "opencode.json").read_text(), before)
        risk.remove_harness_rules(self.root)
        self.assertFalse((self.root / ".codex" / "rules" / "aidd.rules").exists())
        self.assertFalse((self.root / "opencode.json").exists())  # it held only aidd's rules, so it goes

    def test_a_lowered_rule_leaves_the_harness(self):
        risk.apply_harness_rules(self.root, "claude-code", self.patterns)
        lowered = risk.harness_patterns(risk.rule_set(cfg("risks:\n  rules:\n    - {action: git.tag.create, level: allow}\n")), "main")
        risk.apply_harness_rules(self.root, "claude-code", lowered)
        ask = json.loads((self.root / ".claude" / "settings.json").read_text())["permissions"]["ask"]
        self.assertNotIn("Bash(git tag*)", ask)
        self.assertIn("Bash(git push --force*)", ask)


class APersonsOwnOpenCodeRules(unittest.TestCase):
    """aidd never changes a person's OpenCode entry, and never puts an ask where it would undo their deny."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.file = self.root / "opencode.json"

    def bash_after(self, bash) -> dict:
        self.file.write_text(json.dumps({"permission": {"bash": bash}}))
        risk.apply_harness_rules(self.root, "opencode", ["rm -rf*", "git tag*"])
        return json.loads(self.file.read_text())["permission"]["bash"]

    def test_a_persons_entry_stays_theirs(self):
        bash = self.bash_after({"rm -rf*": "deny", "*": "allow"})
        self.assertEqual(bash["rm -rf*"], "deny")
        self.assertEqual(list(bash), ["rm -rf*", "*", "git tag*"])  # their order kept, aidd's asks right after their `*`
        risk.remove_harness_rules(self.root)
        self.assertEqual(json.loads(self.file.read_text())["permission"]["bash"], {"*": "allow", "rm -rf*": "deny"})

    def test_asks_go_right_after_the_persons_default(self):
        bash = self.bash_after({"git *": "allow", "*": "ask"})
        self.assertEqual(list(bash), ["git *", "*", "rm -rf*", "git tag*"])  # their `git *` cannot outrank aidd's asks after `*`
        self.file.write_text(json.dumps({"permission": {"bash": {"*": "allow"}}}))
        risk.apply_harness_rules(self.root, "opencode", ["*"])  # a pattern of `*` alone is never written
        self.assertEqual(json.loads(self.file.read_text())["permission"]["bash"], {"*": "allow"})

    def test_a_default_that_denies_gets_nothing(self):
        self.assertEqual(self.bash_after("deny"), "deny")
        self.assertEqual(self.bash_after({"*": "deny"}), {"*": "deny"})

    def test_a_permission_that_is_not_an_object_is_refused(self):
        self.file.write_text(json.dumps({"permission": "allow"}))
        with self.assertRaisesRegex(ValueError, "not an object"):
            risk.apply_harness_rules(self.root, "opencode", ["git tag*"])


class RiskNeverFallsBackSilently(unittest.TestCase):
    def test_a_config_that_does_not_load_is_an_error(self):
        import contextlib

        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_repo(Path(d) / "repo")
            (root / ".aidd" / "config.yaml").write_text("profile: [broken\n", encoding="utf-8")
            with contextlib.chdir(root):
                code, out = helpers.run_cli("risk", "--command", "gh pr create", "--json")
        self.assertEqual(code, 2, out)
        self.assertIn("config.yaml", out)


class EveryHarnessAsksTheSame(unittest.TestCase):
    """Every harness with ask rules asks for the same commands. Each format is read back from the file aidd wrote and
    matched the way its harness documents it: by glob over the whole command (Claude Code, OpenCode, Grok Build), by
    regular expression (Augment, VS Code), or by leading words (Codex and Factory Droid, a word or a list; Devin, a
    prefix of whole words; Qwen Code, the bare prefix or the prefix with ` *`)."""

    ASK = (
        "git push origin main",
        "git push upstream --force",
        "git push origin HEAD:main",
        "git push origin +main",
        "git push --force",
        "git push -f origin feat",
        "git push --force-with-lease",
        "git push -d origin old",
        "git push --all origin",
        "git push origin --mirror",
        "git push origin refs/heads/main",
        "git push origin main --no-verify",
        "git tag v1.0.0",
        "git tag 1.2.0",
        "git push --follow-tags",
        "git reset --hard HEAD~1",
        "gh pr merge 12 --squash",
        "terraform apply -auto-approve",
        "npm publish",
        "rm -rf build",
        "php artisan migrate --force",
        "php artisan migrate:fresh --seed",
        "alembic downgrade -1",
        "npx prisma migrate deploy",
        "bundle exec rails db:drop",
        "./vendor/bin/sail artisan migrate:fresh",
        "uv run alembic downgrade base",
        "gh workflow run release.yml --ref main",
    )
    # Only the leading-words formats ask here: they hold no `*` inside a command, so they ask at its first three words.
    WIDER = ("gh workflow run ci.yml", "npx wrangler d1 migrations list DB")
    ALLOW = (
        "git push origin feat",
        "git status",
        "git commit -m x",
        "terraform plan",
        "npm test",
        "rm build.log",
        "php artisan migrate",
        "alembic upgrade head",
        'git commit -m "fix the db:drop task"',
        "rg -n migrate:fresh docs",
        "cat docs/flyway-cleanup.md",
    )

    @staticmethod
    def glob_asks(patterns: list[str], command: str) -> bool:
        import fnmatch

        return any(fnmatch.fnmatchcase(command, p) for p in patterns)

    @staticmethod
    def words_ask(rules: list[list], command: str) -> bool:
        words = command.split()
        return any(len(words) >= len(rule) and all(w == r if isinstance(r, str) else w in r for w, r in zip(words, rule, strict=False)) for rule in rules)

    def written(self) -> dict:
        """What each format's file holds after `aidd init`, as the harness reads it."""
        import re as _re
        import tomllib

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            patterns = risk.harness_patterns(risk.rule_set(None), "main")
            for fmt in risk.FORMATS:
                risk.apply_harness_rules(root, fmt, patterns)

            def read(rel: str) -> dict:
                return json.loads((root / rel).read_text())

            bash = lambda e: e[len("Bash(") : -1]  # noqa: E731
            return {
                "claude-code": [bash(e) for e in read(".claude/settings.json")["permissions"]["ask"]],
                "opencode": [k for k, v in read("opencode.json")["permission"]["bash"].items() if v == "ask"],
                "grok": [bash(e) for e in tomllib.loads((root / ".grok/config.toml").read_text())["permission"]["ask"]],
                "augment": [r["shellInputRegex"] for r in read(".augment/settings.json")["toolPermissions"] if r["permission"]["type"] == "ask-user"],
                "vscode": [k[1:-1] for k, v in read(".vscode/settings.json")["chat.tools.terminal.autoApprove"].items() if v is False],
                "codex": [json.loads(m) for m in _re.findall(r"pattern = (\[.*?\]), decision", (root / ".codex/rules/aidd.rules").read_text())],
                "factory": [r["match"]["prefix"] for r in read(".factory/settings.json")["permissionRules"]["rules"] if r["decision"] == "ask"],
                "factory_ids": [r["id"] for r in read(".factory/settings.json")["permissionRules"]["rules"]],
                "devin": [e[len("Exec(") : -1].split() for e in read(".devin/config.json")["permissions"]["ask"]],
                "qwen": [bash(e) for e in read(".qwen/settings.json")["permissions"]["ask"]],
            }

    def test_the_same_commands_ask_everywhere(self):
        import re as _re

        w = self.written()
        asks = {
            "claude-code": lambda c: self.glob_asks(w["claude-code"], c),
            "opencode": lambda c: self.glob_asks(w["opencode"], c),
            "grok": lambda c: self.glob_asks(w["grok"], c),
            "augment": lambda c: any(_re.search(r, c) for r in w["augment"]),
            "vscode": lambda c: any(_re.search(r, c) for r in w["vscode"]),
            "codex": lambda c: self.words_ask(w["codex"], c),
            "factory": lambda c: self.words_ask(w["factory"], c),
            "devin": lambda c: self.words_ask(w["devin"], c),
            "qwen": lambda c: self.glob_asks(w["qwen"], c),
        }
        self.assertEqual(set(asks), set(risk.FORMATS), "every format is in this test")
        self.assertEqual(len(w["factory_ids"]), len(set(w["factory_ids"])), "Factory skips a file whose rule ids repeat")
        for command in self.ASK + self.ALLOW + self.WIDER:
            for fmt, ask in asks.items():
                with self.subTest(command=command, harness=fmt):
                    wider = command in self.WIDER and risk.FORMATS[fmt].match == "words"
                    self.assertEqual(ask(command), command in self.ASK or wider)

    def test_every_harness_with_a_format_names_one_aidd_knows(self):
        for key, h in config.HARNESSES.items():
            if h.ask_rules:
                with self.subTest(harness=key):
                    self.assertIn(h.ask_rules, risk.FORMATS)

    def test_a_persons_rules_stay_in_every_format(self):
        """A person's own entry in each JSON format survives aidd's write and its removal."""
        own = {
            ".claude/settings.json": {"permissions": {"ask": ["Bash(make deploy)"], "allow": ["Bash(ls)"]}},
            ".qwen/settings.json": {"permissions": {"deny": ["Bash(rm -rf /)"]}},
            ".devin/config.json": {"permissions": {"allow": ["Exec(git status)"]}},
            ".augment/settings.json": {"toolPermissions": [{"toolName": "bash", "shellInputRegex": "^rm ", "permission": {"type": "deny"}}]},
            ".vscode/settings.json": {"editor.tabSize": 2, "chat.tools.terminal.autoApprove": {"npm test": True}},
            ".factory/settings.json": {
                "permissionRules": {
                    "version": 1,
                    "rules": [
                        {
                            "id": "project/push",
                            "decision": "ask",
                            "match": {"prefix": ["git", "push"]},
                            "tests": {"match": ["git push"], "noMatch": ["git status"]},
                        }
                    ],
                }
            },
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, data in own.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(json.dumps(data))
            (root / ".grok").mkdir()
            (root / ".grok/config.toml").write_text('model = "x"\n')
            patterns = risk.harness_patterns(risk.rule_set(None), "main")
            for fmt in risk.FORMATS:
                risk.apply_harness_rules(root, fmt, patterns)
            augment = json.loads((root / ".augment/settings.json").read_text())["toolPermissions"]
            self.assertEqual(augment[0]["permission"]["type"], "deny")  # a person's deny stays first, so no ask undoes it
            risk.remove_harness_rules(root)
            for rel, data in own.items():
                with self.subTest(file=rel):
                    left = json.loads((root / rel).read_text())
                    for key, value in data.items():
                        self.assertEqual(left[key], value)
            self.assertEqual((root / ".grok/config.toml").read_text(), 'model = "x"\n')

    def test_augment_keeps_the_persons_order(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / ".augment" / "settings.json"
            path.parent.mkdir()
            allow_then_deny = [
                {"toolName": "bash", "shellInputRegex": "^npm test$", "permission": {"type": "allow"}},
                {"toolName": "bash", "permission": {"type": "deny"}},
            ]
            path.write_text(json.dumps({"toolPermissions": allow_then_deny}))
            done = risk.apply_harness_rules(root, "augment", ["git tag*"])
            self.assertTrue(done[0].startswith("kept"), done)  # an ask before their later deny could undo it
            self.assertEqual(json.loads(path.read_text())["toolPermissions"], allow_then_deny)
            deny_first = [
                allow_then_deny[1],
                allow_then_deny[0],
                {"toolName": "bash", "shellInputRegex": "^git tag[\\s\\S]*$", "permission": {"type": "ask-user"}},
            ]
            path.write_text(json.dumps({"toolPermissions": deny_first}))
            risk.apply_harness_rules(root, "augment", ["git tag*"])
            rules = json.loads(path.read_text())["toolPermissions"]
            self.assertEqual(rules, deny_first)  # their own identical ask stays theirs, and their order holds
            risk.remove_harness_rules(root)
            self.assertEqual(json.loads(path.read_text())["toolPermissions"], deny_first)

    def test_grok_reads_its_toml_and_never_breaks_it(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".grok").mkdir()
            path = root / ".grok" / "config.toml"
            for theirs in ('[ permission ]\ndeny = ["Bash(rm *)"]\n', 'permission.deny = ["Bash(rm *)"]\n', "[broken\n"):
                with self.subTest(theirs=theirs):
                    path.write_text(theirs)
                    done = risk.apply_harness_rules(root, "grok", ["git tag*"])
                    self.assertTrue(done[0].startswith("kept"), done)
                    self.assertEqual(path.read_text(), theirs)
            path.write_text('model = "x"\n')
            risk.apply_harness_rules(root, "grok", ["git tag*", "echo \u00e9*"])  # a non-ASCII pattern is left to the skill
            text = path.read_text()
            self.assertNotIn("echo", text)
            edited = text.replace('ask = ["Bash(git tag*)"]', 'ask = ["Bash(git tag*)"]\ndeny = ["Bash(rm *)"]')
            path.write_text(edited)
            done = risk.apply_harness_rules(root, "grok", ["git tag*", "npm publish*"])
            self.assertTrue(done[0].startswith("kept"), done)  # a person changed aidd's block: it is theirs now
            risk.remove_harness_rules(root)
            self.assertEqual(path.read_text(), edited)
        self.assertEqual(risk.unwritten("claude-code", ["echo \u00e9*", "git tag*"]), ["echo \u00e9*"])

    def test_grok_keeps_a_persons_line_after_aidds_block(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".grok").mkdir()
            path = root / ".grok" / "config.toml"
            path.write_text("[tools]\nx = 1\n")
            risk.apply_harness_rules(root, "grok", ["git tag*"])
            theirs = path.read_text() + 'deny = ["Bash(rm -rf*)"]\n'  # after aidd's block, so it reads as permission.deny
            path.write_text(theirs)
            self.assertTrue(risk.apply_harness_rules(root, "grok", ["git tag*", "npm publish*"])[0].startswith("kept"))
            self.assertTrue(risk.remove_harness_rules(root)[0].startswith("kept"))
            self.assertEqual(path.read_text(), theirs)

    def test_odd_input_is_kept_never_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            factory = root / ".factory" / "settings.json"
            factory.parent.mkdir()
            factory.write_text(json.dumps({"permissionRules": {"version": 1, "rules": [{"id": ["x"], "decision": "ask"}]}}))
            risk.apply_harness_rules(root, "factory", ["git tag*"])
            (root / ".grok").mkdir()
            grok = root / ".grok" / "config.toml"
            risk.apply_harness_rules(root, "grok", ["git tag*"])
            odd = grok.read_text().replace('ask = ["Bash(git tag*)"]', "ask = [{a = 1}]")
            grok.write_text(odd)
            self.assertTrue(risk.apply_harness_rules(root, "grok", ["git tag*"])[0].startswith("kept"))
            risk.remove_harness_rules(root)
            self.assertEqual(grok.read_text(), odd)

    def test_a_file_aidd_cannot_read_safely_is_refused_or_kept(self):
        """Each format refuses a file it cannot merge into safely, with the fix, and its removal leaves an odd file as it is."""
        refused = {
            ("vscode", ".vscode/settings.json"): '{"chat.tools.terminal.autoApprove": ["x"]}',
            ("augment", ".augment/settings.json"): '{"toolPermissions": {"x": 1}}',
            ("factory", ".factory/settings.json"): '{"permissionRules": {"version": 2, "rules": []}}',
            ("qwen", ".qwen/settings.json"): "{not json",
            ("devin", ".devin/config.json"): "[1, 2]",
        }
        for (fmt, rel), text in refused.items():
            with self.subTest(fmt=fmt), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / rel).parent.mkdir(parents=True)
                (root / rel).write_text(text)
                with self.assertRaisesRegex(ValueError, "fix it|by hand"):
                    risk.apply_harness_rules(root, fmt, ["git tag*"])
                self.assertEqual((root / rel).read_text(), text)
        with tempfile.TemporaryDirectory() as d:  # removal: aidd's record names entries, but the files changed shape
            root = Path(d)
            for fmt in ("augment", "factory", "vscode", "qwen"):
                risk.apply_harness_rules(root, fmt, ["git tag*"])
            odd = {
                ".augment/settings.json": {"toolPermissions": "x"},
                ".factory/settings.json": {"permissionRules": []},
                ".vscode/settings.json": {"a": 1},
                ".qwen/settings.json": {"permissions": "x"},
            }
            for rel, data in odd.items():
                (root / rel).write_text(json.dumps(data))
            risk.remove_harness_rules(root)
            for rel, data in odd.items():
                with self.subTest(rel=rel):
                    self.assertEqual(json.loads((root / rel).read_text()), data)

    def test_a_factory_id_clash_is_said(self):
        from aidd.risk import harness_rules

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            entry = harness_rules._entries("factory", ["git tag*"])[0]
            theirs = dict(harness_rules._factory_rule(entry), reason="mine")
            path = root / ".factory" / "settings.json"
            path.parent.mkdir()
            path.write_text(json.dumps({"permissionRules": {"version": 1, "rules": [theirs]}}))
            done = risk.apply_harness_rules(root, "factory", ["git tag*"])
            self.assertTrue(any("kept" in x and theirs["id"] in x for x in done), done)
            self.assertEqual(json.loads(path.read_text())["permissionRules"]["rules"], [theirs])

    def test_a_regex_matches_exactly_and_reads_alike_everywhere(self):
        import re as _re

        from aidd.risk import harness_rules

        regex = harness_rules.glob_regex("git push * a/b.c+")
        self.assertEqual(regex, "^git push [\\s\\S]* a\\/b\\.c\\+$")
        self.assertTrue(_re.search(regex, "git push origin\nx a/b.c+"))
        self.assertFalse(_re.search(regex, "git push origin a/bxc+"))

    def test_grok_leaves_a_persons_permission_table_alone(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".grok").mkdir()
            mine = '[permission]\nallow = ["Bash(git *)"]\n'
            (root / ".grok/config.toml").write_text(mine)
            done = risk.apply_harness_rules(root, "grok", ["git tag*"])
            self.assertTrue(done[0].startswith("kept"), done)
            self.assertEqual((root / ".grok/config.toml").read_text(), mine)

    def test_an_ask_on_one_branch_reaches_the_harness(self):
        """A harness cannot tell branches apart, so an action that asks on one branch asks there; a push to the agent's
        own branch stays allowed."""
        rs = risk.rule_set(cfg("risks:\n  rules:\n    - {action: git.push.force, level: allow}\n    - {action: git.push.force, branch: default, level: ask}\n"))
        patterns = risk.harness_patterns(rs, "main")
        self.assertIn("git push --force*", patterns)
        self.assertNotIn("git push*", patterns)

    def test_what_codex_cannot_hold_is_named(self):
        from aidd.risk import harness_rules

        cases = {
            "git push * main": ["git", "push", ["origin", "upstream"], "main"],
            "git push * *:main": ["git", "push", ["origin", "upstream"], "HEAD:main"],
            "git push * --force*": ["git", "push", ["origin", "upstream"], "--force"],
            "rm -rf*": ["rm", "-rf"],
            "php artisan migrate:fresh*": ["php", "artisan", "migrate:fresh"],
            "git clean -f*": ["git", "clean", "-f"],  # held only in part: `-fdx` is another word
            "git push * +*": None,  # Codex matches whole words, so `+<any branch>` has no form
            "git push * :*": None,
        }
        for pattern, want in cases.items():
            with self.subTest(pattern=pattern):
                self.assertEqual(harness_rules.codex_words(pattern, ["origin", "upstream"]), want)
        # A `*` between words is only `origin` and `upstream`, and `*:main` only `HEAD:main`, so doctor names those too.
        self.assertEqual(
            risk.unwritten("codex", list(cases)),
            [
                "git push * main",
                "git push * *:main",
                "git push * --force*",
                "rm -rf*",
                "php artisan migrate:fresh*",
                "git clean -f*",
                "git push * +*",
                "git push * :*",
            ],
        )
        self.assertEqual(risk.unwritten("claude-code", list(cases)), [])

    def test_a_star_inside_a_command_asks_at_three_words_of_the_tool(self):
        """A pattern with no leading-words form asks at the words before its first `*`, so those formats ask more, never
        less; but only at three or more of the tool's own words, past a setting and a runner, so no ask grows wider."""
        from aidd.risk import harness_rules

        cases = {
            "gh workflow run *release*": ["gh", "workflow", "run"],
            "dotnet ef migrations remove*--force*": ["dotnet", "ef", "migrations"],
            "npx wrangler d1 migrations apply*--remote*": ["npx", "wrangler", "d1", "migrations"],
            "gh api *dispatches*": None,  # `gh api` would ask before every API call
            "gh api */statuses/*": None,
            "git push * +*": None,
            "bundle exec rails db:*RAILS_ENV=production*": None,  # one word of rails's own, past its runner
            "RAILS_ENV=production bundle exec rails db:*": None,
            "uv run manage.py migrate*zero*": None,
            "git push --force*": None,  # it has a leading-words form of its own
        }
        for pattern, want in cases.items():
            with self.subTest(pattern=pattern):
                self.assertEqual(harness_rules.leading_words(pattern), want)
        patterns = ["gh workflow run *release*", "gh api *dispatches*", "git push --force*"]
        for fmt in ("codex", "factory", "devin", "qwen"):
            with self.subTest(fmt=fmt):
                self.assertEqual(risk.unwritten(fmt, patterns), ["gh api *dispatches*"])
                self.assertEqual(risk.widened(fmt, patterns), {"gh workflow run *release*": "gh workflow run"})
        self.assertEqual(risk.widened("claude-code", patterns), {})

    def test_the_files_aidd_writes_are_the_same_on_every_machine(self):
        """A remote a person adds lives in their own git config, so it never reaches a file aidd commits."""
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            helpers.git(d, "remote", "add", "fork", "https://example.com/x.git")
            risk.apply_harness_rules(Path(d), "codex", ["git push * main"])
            text = (Path(d) / ".codex" / "rules" / "aidd.rules").read_text()
        self.assertIn('["origin", "upstream"]', text)
        self.assertNotIn("fork", text)


class OutputSchemaTests(unittest.TestCase):
    """What `aidd risk --json` and `aidd status --json` print is what their schemas say, in every shape."""

    def test_risk_and_status_match_their_schemas(self):
        import contextlib

        from aidd.kernel import json_schema

        with tempfile.TemporaryDirectory() as d:
            root = helpers.make_repo(Path(d) / "repo", spec="specs/SPEC-220.md")
            with contextlib.chdir(root):
                for argv in (
                    ["risk", "--paths", "src/auth/login.py", "--json"],
                    ["risk", "--command", "git push --force origin main", "--json"],
                    ["risk", "--action", "pr.merge", "--json"],
                    ["risk", "--list", "--json"],
                ):
                    code, out = helpers.run_cli(*argv)
                    self.assertEqual(code, 0, out)
                    self.assertEqual(json_schema.validate(json.loads(out), "risk.schema.json"), [], argv)
                code, out = helpers.run_cli("status", "--json")
                self.assertEqual(code, 0, out)
                shown = json.loads(out)
                self.assertTrue(shown["items"], "the repository holds an open Spec")
                self.assertEqual(json_schema.validate(shown, "status.schema.json"), [])


if __name__ == "__main__":
    unittest.main()
