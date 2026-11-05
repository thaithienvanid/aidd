"""The risk rules: which rule wins, what a command line is, the route for planned paths, how a config changes the
rules, and the harness ask rules `aidd init` writes. Table-driven: each case is one row of what a person would ask."""

from __future__ import annotations

import contextlib
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
            ("intent.agree", {}, "ask"),
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
            # A commit that records a person's agreement to an Intent is that agreement, so it asks.
            ('git commit -m "plan: agree INTENT-1" -m "Agreed-by: Dana <dana@example.com>"', "ask"),
            ('git commit -m "plan: write INTENT-1"', "allow"),
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


class TheAuthAreaNamesSignInFiles(unittest.TestCase):
    """The `auth` area catches a sign-in file by its name, outside an `auth/` folder, and keeps docs and vendored code out."""

    def route_and_areas(self, path: str):
        found = risk.route_for(risk.rule_set(None), [path])
        return found.route, list(found.areas)

    def test_each_sign_in_name_glob_routes_major_in_auth(self):
        paths = [
            "src/login.py",  # **/login*.*
            "web/login_form.tsx",
            "src/logout.go",  # **/logout*.*
            "web/signin.tsx",  # **/signin*.*
            "src/sign-in.tsx",  # **/sign-in*.*
            "app/sign_in.rb",  # **/sign_in*.*
            "app/signup.vue",  # **/signup*.*
            "src/sign-up.vue",  # **/sign-up*.*
            "src/sign_up.rb",  # **/sign_up*.*
            "app/session_store.ts",  # **/session*.*
            "src/sessions.py",
            "app/password_reset.py",  # **/*password*.*
            "app/forgot_password.py",  # the password word after a prefix
            "web/reset-password.tsx",
            "lib/passkey.go",  # **/passkey*.*
            "lib/webauthn.ts",  # **/webauthn*.*
            "src/mfa.py",  # **/mfa*.*
            "src/otp.py",  # **/otp*.*
            "src/totp.js",  # **/totp*.*
            "src/2fa.py",  # **/*2fa*.*
            "src/enable_2fa.py",
            "src/two_factor.py",  # **/two*factor*.*
            "src/two-factor-setup.ts",
            "src/twofactor.py",
            "login.py",  # at the repository root
            "login.test.ts",  # a test of sign-in code stays major on purpose: it changes what the code is held to
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.route_and_areas(path), ("major", ["auth"]))

    def test_each_sign_in_folder_glob_routes_major_in_auth(self):
        """The folder forms that Next.js and SvelteKit route by: the folder is the page's name."""
        paths = [
            "app/login/page.tsx",  # **/login/**
            "src/routes/signin/+page.svelte",  # **/signin/**
            "app/sign-in/page.tsx",  # **/sign-in/**
            "app/signup/page.tsx",  # **/signup/**
            "app/sign-up/page.tsx",  # **/sign-up/**
            "web/mfa/setup.ts",  # **/mfa/**
            "lib/password/hash.py",  # **/password/**
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.route_and_areas(path), ("major", ["auth"]))

    def test_each_new_exclude_keeps_an_asset_named_like_sign_in_out(self):
        paths = [
            "src/login.css",  # **/*.css
            "static/login.svg",  # **/*.svg
            "static/signin.png",  # **/*.png
            "assets/sign-in.jpg",  # **/*.jpg
            "assets/login.jpeg",  # **/*.jpeg
            "assets/signup.gif",  # **/*.gif
            "assets/session.ico",  # **/*.ico
            "src/auth/logo.svg",  # an image cannot hold policy, so it may leave an auth folder
            "src/auth/login.css",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.route_and_areas(path), ("minor", []))

    def test_policy_in_csv_stays_in_auth(self):
        """Casbin and similar engines keep authorization policy in CSV, so no exclude may drop a CSV file."""
        paths = [
            "src/rbac/policy.csv",
            "app/permissions/roles.csv",
            "src/auth/policy.csv",
            "data/passwords.csv",  # matches **/*password*.*, and no exclude drops it
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.route_and_areas(path), ("major", ["auth"]))

    def test_docs_vendored_code_and_other_names_stay_out(self):
        paths = [
            "docs/sessions.md",  # the docs exclude
            "docs/login.md",  # a new glob matches the name, so only the docs and *.md excludes keep it out
            "docs/login.html",  # the docs exclude, whatever the extension
            "web/login.mdx",  # the *.mdx exclude
            "node_modules/pkg/login.js",  # the node_modules exclude
            "vendor/pkg/session.go",  # the vendor exclude
            "src/login_notes",  # no extension: the name globs need a dot, and it is no folder
            "tests/test_login.py",  # the name starts with test_, not login
            "src/register.py",  # not a sign-in word on the owner's list
            "src/log_in.py",  # likewise
            "src/credentials.py",  # likewise
            "src/app.py",
            "src/user_profile.py",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.route_and_areas(path), ("minor", []))

    def test_a_name_that_only_starts_like_a_sign_in_word_still_belongs_in_auth(self):
        """A glob matches the start of a name, so these match by accident or by design. Each stays in `auth` on purpose:
        a false major costs one Spec, and a missed sign-in file costs a change nobody asked a person about."""
        paths = [
            "src/otp_display_name.py",  # a one-time-password helper's label code: the same module family
            "src/mfa_banner.tsx",  # the prompt a person sees when MFA is required
            "blog/login-tips.html",  # an HTML page outside docs/ can be a real sign-in page, and a glob cannot tell
            "src/sessionize.py",  # an accidental prefix match, accepted: the owner's list has no word boundary
            "src/loginfo.py",  # an accidental prefix match, accepted for the same reason
            "db/session.py",  # a database session is not a sign-in session, but a glob cannot tell, so it stays in
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.route_and_areas(path), ("major", ["auth"]))


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
        native = json.loads((self.root / "opencode.json").read_text())["permissions"]
        self.assertIn({"action": "shell", "resource": "git push --force*", "effect": "ask"}, native)
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

    def after(self, bash) -> dict:
        self.file.write_text(json.dumps({"permission": {"bash": bash}}))
        risk.apply_harness_rules(self.root, "opencode", ["rm -rf*", "git tag*"])
        return json.loads(self.file.read_text())

    def test_a_persons_v1_entries_stay_theirs(self):
        data = self.after({"rm -rf*": "deny", "*": "allow"})
        self.assertEqual(data["permission"], {"bash": {"rm -rf*": "deny", "*": "allow"}})  # their entries and order, in v1
        # Their `*` comes after their deny and outranks it, so aidd asks for both patterns, after every v1 entry.
        self.assertEqual([r["resource"] for r in data["permissions"]], ["rm -rf*", "git tag*"])
        risk.remove_harness_rules(self.root)
        self.assertEqual(json.loads(self.file.read_text()), {"permission": {"bash": {"rm -rf*": "deny", "*": "allow"}}})

    def test_a_pattern_of_every_command_is_never_written(self):
        self.file.write_text(json.dumps({"permission": {"bash": {"*": "allow"}}}))
        risk.apply_harness_rules(self.root, "opencode", ["*"])
        self.assertEqual(json.loads(self.file.read_text()), {"permission": {"bash": {"*": "allow"}}})

    def test_a_default_that_denies_gets_nothing(self):
        self.assertEqual(self.after("deny"), {"permission": {"bash": "deny"}})
        self.assertEqual(self.after({"*": "deny"}), {"permission": {"bash": {"*": "deny"}}})

    def test_a_permission_that_is_not_an_object_is_refused(self):
        self.file.write_text(json.dumps({"permission": ["allow"]}))
        with self.assertRaisesRegex(ValueError, "not an object"):
            risk.apply_harness_rules(self.root, "opencode", ["git tag*"])


def opencode_wildcard(text: str, pattern: str) -> bool:
    """OpenCode's `Wildcard.match`, ported line by line (anomalyco/opencode v2.2.6, packages/core/src/util/wildcard.ts:3-14)."""
    import re as _re

    escaped = _re.sub(r"[.+^${}()|\[\]\\]", lambda m: "\\" + m.group(0), pattern.replace("\\", "/")).replace("*", ".*").replace("?", ".")
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + "( .*)?"
    return _re.fullmatch(escaped, text.replace("\\", "/"), _re.S) is not None


def opencode_shell_effect(data: dict, command: str) -> str:
    """What OpenCode v2 does with `command`, read from one `opencode.json` as v2.2.6 reads it: `tools`, then v1's
    `permission` (its `bash` key as the `shell` action), then the native `permissions`, in one list
    (packages/core/src/config/normalize.ts:179-182, packages/core/src/v1/config/migrate.ts:27-31), and the last rule that
    matches wins, `ask` when none does (packages/core/src/permission.ts:94-104)."""
    rename = {"bash": "shell", "task": "subagent", "write": "edit", "patch": "edit", "apply_patch": "edit"}
    rules = [(rename.get(k, k), "*", "allow" if v else "deny") for k, v in (data.get("tools") or {}).items()]
    perm = data.get("permission")
    if isinstance(perm, str):
        rules.append(("*", "*", perm))
    for key, raw in (perm or {}).items() if isinstance(perm, dict) else []:
        rules += [(rename.get(key, key), "*", raw)] if isinstance(raw, str) else [(rename.get(key, key), r, e) for r, e in raw.items()]
    rules += [(r["action"], r["resource"], r["effect"]) for r in data.get("permissions") or []]
    hits = [e for a, r, e in rules if opencode_wildcard("shell", a) and opencode_wildcard(command, r)]
    return hits[-1] if hits else "ask"


class OpenCodeV2Rules(unittest.TestCase):
    """OpenCode v2 puts a file's native `permissions` after its v1 `permission`, and the last match wins, so aidd's asks
    go in that list, after the person's default. Each case reads the file back as OpenCode does (`opencode_shell_effect`)."""

    ALLOW_ALL = {"action": "shell", "resource": "*", "effect": "allow"}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.file = self.root / "opencode.json"
        self.patterns = risk.harness_patterns(risk.rule_set(None), "main")

    def apply(self) -> dict:
        risk.apply_harness_rules(self.root, "opencode", self.patterns)
        return json.loads(self.file.read_text())

    def assert_asks_as_the_rules_do(self, data: dict) -> None:
        cases = EveryHarnessAsksTheSame
        for command in cases.ASK + cases.GLOB_ONLY + cases.ALLOW:
            with self.subTest(command=command):
                self.assertEqual(opencode_shell_effect(data, command), "allow" if command in cases.ALLOW else "ask")

    def test_a_native_allow_never_outranks_aidds_asks(self):
        self.file.write_text(json.dumps({"permission": {"edit": "allow"}, "permissions": [self.ALLOW_ALL]}))
        data = self.apply()
        self.assertEqual(data["permissions"][0], self.ALLOW_ALL)  # the person's default stays first, as they wrote it
        self.assertEqual(data["permission"], {"edit": "allow"})
        self.assert_asks_as_the_rules_do(data)
        self.assertEqual(risk.apply_harness_rules(self.root, "opencode", self.patterns), [])  # a second run changes nothing

    def test_no_ask_is_lost_in_any_file(self):
        """Every file aidd may meet keeps each ask, or a stricter deny, and its v1 `permission` holds only the person's
        entries. A case marked `earlier` holds what an earlier aidd wrote: v1 asks, listed in `.aidd/harness-rules.json`."""
        old = {p: "ask" for p in self.patterns}
        deny_all = {"action": "shell", "resource": "*", "effect": "deny"}
        mixed = {"edit": "allow", "bash": {"*": "allow", **old, "ls*": "allow"}}
        own_ask = {self.patterns[0]: "ask", "*": "allow"}
        cases = [
            # (the file before, the effect each asked command gets, the v1 `permission` after, an earlier aidd's record)
            (None, "ask", None, False),  # no file
            ({"model": "x"}, "ask", None, False),  # no list
            ({"permissions": []}, "ask", None, False),  # an empty list
            ({"permission": {"bash": {"*": "allow"}}}, "ask", {"bash": {"*": "allow"}}, False),  # a v1 catch-all allow
            ({"permission": "allow"}, "ask", "allow", False),  # a v1 allow for every tool
            ({"permissions": [self.ALLOW_ALL]}, "ask", None, False),  # a native catch-all allow
            ({"permission": {"bash": {"*": "deny"}}}, "deny", {"bash": {"*": "deny"}}, False),  # a v1 catch-all deny
            ({"permissions": [deny_all]}, "deny", None, False),  # a native catch-all deny
            ({"permission": {"bash": old}}, "ask", None, True),  # an earlier aidd's v1 asks alone
            ({"permission": mixed}, "ask", {"edit": "allow", "bash": {"*": "allow", "ls*": "allow"}}, True),  # among the person's
            ({"permission": {"bash": old}, "permissions": [self.ALLOW_ALL]}, "ask", None, True),  # under a native allow
            ({"permission": {"bash": own_ask}}, "ask", {"bash": own_ask}, False),  # the person's own v1 ask, kept on every run
        ]
        asked = EveryHarnessAsksTheSame.ASK + EveryHarnessAsksTheSame.GLOB_ONLY
        record = self.root / config.HARNESS_RULES_FILE
        for before, effect, v1, earlier in cases:
            with self.subTest(before=before, earlier=earlier):
                self.file.unlink(missing_ok=True)
                record.unlink(missing_ok=True)
                if before is not None:
                    self.file.write_text(json.dumps(before))
                if earlier:
                    record.parent.mkdir(exist_ok=True)
                    record.write_text(json.dumps({"opencode": self.patterns}))
                data = self.apply()
                self.assertEqual(data.get("permission"), v1)
                for command in asked:
                    self.assertEqual(opencode_shell_effect(data, command), effect, command)
                again = risk.apply_harness_rules(self.root, "opencode", self.patterns)
                self.assertEqual([d for d in again if not d.startswith("kept")], [])  # a second run changes nothing
                self.assertEqual(json.loads(self.file.read_text()).get("permission"), v1)
                risk.remove_harness_rules(self.root)  # uninstall leaves the person's v1 entries as they are
                self.assertEqual(json.loads(self.file.read_text()).get("permission") if self.file.is_file() else None, v1)

    def test_upgrade_says_once_when_a_persons_v1_allow_stops_deciding(self):
        """The old v1 asks sat right after the person's `*`, so their later v1 allow decided; in the list it no longer does."""
        push_all = {"git push *": "allow"}
        self.file.write_text(json.dumps({"permission": {"bash": {"*": "ask", **{p: "ask" for p in self.patterns}, **push_all}}}))
        (self.root / config.HARNESS_RULES_FILE).parent.mkdir(exist_ok=True)
        (self.root / config.HARNESS_RULES_FILE).write_text(json.dumps({"opencode": self.patterns}))
        said = [d for d in risk.apply_harness_rules(self.root, "opencode", self.patterns) if d.startswith("note")]
        self.assertEqual(len(said), 1, said)
        self.assertIn('`"git push *": "allow"` in `permission.bash`', said[0])
        self.assertEqual(json.loads(self.file.read_text())["permission"], {"bash": {"*": "ask", **push_all}})
        self.assertEqual([d for d in risk.apply_harness_rules(self.root, "opencode", self.patterns) if d.startswith("note")], [])

    def test_every_ask_holds_under_a_persons_own_rules(self):
        """The person's rules before their default, or in v1, never stop an ask, whatever their default spells."""
        tag_allow = {"action": "shell", "resource": "git tag*", "effect": "allow"}
        cases = [
            {"permissions": [tag_allow, self.ALLOW_ALL]},  # their rule before their default decides nothing
            {"permission": {"bash": {"git push --force*": "ask"}}, "permissions": [self.ALLOW_ALL]},  # a v1 ask under a v2 allow
            {"permission": {"bash": {"*": "allow", "git push*": "allow"}}, "permissions": []},  # v1 comes before every v2 rule
            {"permissions": [{"action": "shell", "resource": "**", "effect": "allow"}]},  # a default spelled `**`
            {"permissions": [{"action": "*", "resource": "*", "effect": "allow"}]},
        ]
        for case in cases:
            with self.subTest(case=case):
                self.file.write_text(json.dumps(case))
                data = self.apply()
                self.assert_asks_as_the_rules_do(data)
                self.assertEqual(risk.opencode_shadow_warnings(self.root, self.patterns), [])

    def test_a_persons_rule_after_their_default_stays_theirs_and_doctor_names_it(self):
        deny = {"action": "*", "resource": "*", "effect": "deny"}
        self.file.write_text(json.dumps({"permissions": [deny]}))
        self.assertEqual(self.apply()["permissions"], [deny])  # a default that denies is stricter: nothing is written
        own = {"action": "shell", "resource": "git tag*", "effect": "allow"}
        later = {"action": "shell", "resource": "git push*", "effect": "allow"}
        self.file.write_text(json.dumps({"permissions": [self.ALLOW_ALL, own, later]}))
        data = self.apply()
        self.assertEqual(data["permissions"][0], self.ALLOW_ALL)
        self.assertEqual(data["permissions"][-2:], [own, later])  # rules after the default stay after aidd's asks, and win
        self.assertNotIn({"action": "shell", "resource": "git tag*", "effect": "ask"}, data["permissions"])  # never their pattern
        self.assertEqual(opencode_shell_effect(data, "git push --force"), "allow")
        from aidd.setup import doctor_checks

        warned = [m for level, m in doctor_checks.harness_checks(self.root, ["opencode"]) if level == "warn"]
        self.assertEqual(len(warned), 2, warned)  # doctor names each rule that lets an asked command run with no prompt
        self.assertTrue(json.dumps(own) in warned[0] + warned[1] and json.dumps(later) in warned[0] + warned[1])
        # A v1 default that denies, and a v2 allow after it: aidd writes nothing, and doctor names the allow.
        self.file.write_text(json.dumps({"permission": {"bash": {"*": "deny"}}, "permissions": [later]}))
        self.assertEqual(self.apply()["permissions"], [later])
        self.assertEqual(len(risk.opencode_shadow_warnings(self.root, self.patterns)), 1)

    def test_a_mis_cased_deny_never_stops_an_ask(self):
        """Off Windows, OpenCode ignores a rule whose case differs (wildcard.ts:13), so such a deny is no default there:
        aidd still writes its asks, and doctor names an allow that wins on either platform."""
        deny_all = {"action": "SHELL", "resource": "*", "effect": "deny"}
        self.file.write_text(json.dumps({"permissions": [self.ALLOW_ALL, deny_all]}))
        data = self.apply()
        self.assert_asks_as_the_rules_do({**data, "permissions": [r for r in data["permissions"] if r != deny_all]})
        self.assertGreater(len(data["permissions"]), 2)
        git_allow = {"action": "shell", "resource": "git *", "effect": "allow"}
        git_deny = {"action": "SHELL", "resource": "git *", "effect": "deny"}
        self.file.write_text(json.dumps({"permissions": [self.ALLOW_ALL, git_allow, git_deny]}))
        data = self.apply()
        self.assertEqual(opencode_shell_effect(data, "git push --force"), "allow")  # off Windows, their `git *` allow wins
        warned = risk.opencode_shadow_warnings(self.root, self.patterns)
        self.assertTrue(any(json.dumps(git_allow) in w for w in warned), warned)

    def test_a_default_however_spelled_comes_before_aidds_asks(self):
        for default in ({**self.ALLOW_ALL, "resource": "* *"}, {**self.ALLOW_ALL, "resource": "?*"}, {**self.ALLOW_ALL, "action": "SHELL"}):
            with self.subTest(default=default):
                self.file.write_text(json.dumps({"permissions": [default]}))
                data = self.apply()
                self.assertEqual(data["permissions"][0], default)  # OpenCode reads it as every command (on Windows, any case)
                if default["action"] == "shell":  # the reader here is OpenCode off Windows, where `SHELL` matches nothing
                    self.assert_asks_as_the_rules_do(data)

    def test_doctor_names_each_allow_that_outranks_an_ask(self):
        """An agent's rules come after the file's in OpenCode v2, and a narrow allow after aidd's asks still wins."""
        push_main = {"action": "shell", "resource": "git push origin main", "effect": "allow"}
        cases = [
            # (the file before aidd writes, what the person adds after, the agent a warning names)
            ({"agent": {"build": {"permission": {"bash": "allow"}}}}, None, "build"),
            ({"permissions": [], "agents": {"plan": {"permissions": [self.ALLOW_ALL]}}}, None, "plan"),
            ({"permissions": [self.ALLOW_ALL]}, lambda d: d["permissions"].append(push_main), None),
            ({"permission": {"bash": {"*": "allow"}}}, lambda d: d["permissions"].append(push_main), None),
        ]
        for before, add, agent in cases:
            with self.subTest(before=before):
                self.file.write_text(json.dumps(before))
                data = self.apply()
                if add:
                    add(data)
                    self.file.write_text(json.dumps(data))
                warned = risk.opencode_shadow_warnings(self.root, self.patterns)
                self.assertEqual(len(warned), 1, warned)
                if agent:
                    self.assertIn(f"`{agent}`", warned[0])

    def test_uninstall_takes_aidds_rules_out_of_both_forms(self):
        self.file.write_text(json.dumps({"model": "x", "permissions": [self.ALLOW_ALL]}))
        self.apply()
        risk.remove_harness_rules(self.root)
        self.assertEqual(json.loads(self.file.read_text()), {"model": "x", "permissions": [self.ALLOW_ALL]})
        self.file.write_text(json.dumps({"model": "x", "permissions": []}))
        self.apply()
        risk.remove_harness_rules(self.root)
        self.assertEqual(json.loads(self.file.read_text()), {"model": "x"}, "an emptied list goes")

    def test_a_list_that_is_no_list_is_refused(self):
        self.file.write_text(json.dumps({"permissions": {"shell": "allow"}}))
        with self.assertRaisesRegex(ValueError, "not a list"):
            self.apply()

    def test_doctor_says_when_the_installed_opencode_is_below_v2(self):
        """OpenCode v1 refuses the `permissions` list, so `aidd doctor` names an installed v1 and the step that fixes it."""
        import subprocess
        from unittest import mock

        from aidd.setup import doctor_checks, doctor_probes

        self.file.write_text(json.dumps({"permissions": []}))
        outside = str(Path(tempfile.gettempdir()).resolve().parent / "bin" / "opencode")
        cases = [
            # (what `opencode --version` says, where `shutil.which` finds it, whether doctor warns)
            ("1.18.0\n", outside, True),
            ("opencode v2.1.4\n", outside, False),
            ("opencode v0.0.0-beta-19507\n", outside, False),  # a v2 beta: unknown, so no warning
            ("0.0.0-dev-986\n", outside, False),
            ("", outside, False),
            ("1.18.0\n", None, False),  # no OpenCode on this machine
            ("1.18.0\n", str(self.root / "bin" / "opencode"), False),  # one inside the repository never runs
        ]
        for answer, found, warned in cases:
            with self.subTest(answer=answer, found=found):
                done = subprocess.CompletedProcess(["opencode"], 0, answer, "")
                with (
                    mock.patch.object(doctor_probes.shutil, "which", return_value=found),
                    mock.patch.object(doctor_probes.subprocess, "run", return_value=done) as run,
                ):
                    said = doctor_probes.opencode_version_problem(self.root)
                self.assertEqual(said is not None, warned, said)
                self.assertTrue(not warned or "OpenCode 1.18.0" in said and "@opencode/cli" in said and "brew install opencode" in said, said)
                self.assertEqual([c.args[0][0] for c in run.call_args_list], [found] if found == outside else [])  # the program `which` found
        v1 = subprocess.CompletedProcess(["opencode"], 0, "1.18.0\n", "")
        with mock.patch.object(doctor_probes.shutil, "which", return_value=outside), mock.patch.object(doctor_probes, "_run_probe", return_value=v1):
            self.assertEqual(len([m for _, m in doctor_checks.doctor(self.root, execute=True) if "@opencode/cli" in m]), 1)


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


class RiskOutsideARepository(unittest.TestCase):
    """In a folder that no git repository holds, `aidd risk` answers from the rules there with the branch unknown, so
    an action that turns on the branch asks, and the answer says so once. The MCP tool runs the same command."""

    def setUp(self):
        import contextlib

        from aidd.kernel import git

        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.assertEqual(git.toplevel(str(self.folder)), "", "the test folder must be in no repository")
        self.enterContext(contextlib.chdir(self.folder))

    def _answer(self, *argv: str) -> tuple[int, dict | str]:
        import contextlib

        with contextlib.chdir(self.folder):  # aidd moves to a repository's top, as each process would
            code, out = helpers.run_cli("risk", *argv, "--json")
        return code, (json.loads(out) if code == 0 else out)

    def test_every_command_answer_asks_where_the_branch_counts_and_says_what_is_unknown(self):
        cases = [
            # (command, extra flags, level): every answer out here notes that the branch and the repository's own rules are unknown
            ("git push origin feat", (), "ask"),
            ("git push", (), "ask"),
            ("git push --force origin feat", (), "ask"),
            ("git merge feat", (), "ask"),
            ("gh pr merge 3", (), "ask"),
            ("gh pr create", (), "report"),
            ("git push origin feat", ("--branch", "own"), "allow"),  # the person named the branch: still noted, since no config was read
            ("ls -la", (), "allow"),  # a command only a repository's config names reads as no action here
        ]
        for line, extra, level in cases:
            with self.subTest(line=line, extra=extra):
                code, answer = self._answer("--command", line, *extra)
                self.assertEqual(code, 0, answer)
                assert isinstance(answer, dict)
                self.assertEqual(answer["level"], level)
                self.assertEqual(len(answer["notes"]), 1, answer["notes"])

    def test_the_route_the_action_and_the_list_answer_from_the_built_in_rules(self):
        rs = risk.rule_set(None)
        import contextlib

        code, answer = self._answer("--paths", "src/payments/charge.py")
        assert isinstance(answer, dict)
        self.assertEqual((code, answer["edit"]["level"]), (0, "ask"))
        repo = self.folder / "repo"
        repo.mkdir()
        helpers.git(str(repo), "init", "-q", "-b", "main")
        with contextlib.chdir(repo):
            inside = json.loads(helpers.run_cli("risk", "--paths", "src/payments/charge.py", "--json")[1])
        assert isinstance(inside, dict)
        self.assertEqual(len(answer["hints"]), len(inside["hints"]) + 1, "one hint says the folder is in no repository")
        code, answer = self._answer("--action", "pr.merge")
        assert isinstance(answer, dict)
        self.assertEqual((code, answer["level"]), (0, risk.level_of(rs, "pr.merge")[0]))
        code, answer = self._answer("--list")
        assert isinstance(answer, dict)
        self.assertEqual((code, len(answer["rules"])), (0, len(rs.rules)))

    def test_each_built_in_rule_says_why_and_the_answers_show_it(self):
        """The built-in rules are aidd's own decisions, so each keeps its reason where `aidd risk` shows it."""
        rs = risk.rule_set(None)
        self.assertEqual([r.label() for r in rs.rules if not r.reason], [], "write a `reason` for each rule in schemas/risks.json")
        _, rule = risk.level_on_any_branch(rs, "git.push.force")
        assert rule is not None
        code, answer = self._answer("--action", "git.push.force")
        assert isinstance(answer, dict)
        self.assertEqual((code, answer["reason"]), (0, rule.reason))
        self.assertIn(f"why: {rule.reason}\n", helpers.run_cli("risk", "--action", "git.push.force")[1])
        _, listed = self._answer("--list")
        assert isinstance(listed, dict)
        self.assertEqual([r["reason"] for r in listed["rules"]], [r.reason for r in rs.rules])

    def test_a_configs_reason_never_forges_a_line_of_the_answer(self):
        """A config's or a preset's reason is text from a file: a newline refuses the config, and a control character prints
        as a space, so no reason writes a `level: allow (built-in)` line of its own."""
        import contextlib

        repo = self.folder / "repo"
        (repo / ".aidd").mkdir(parents=True)
        helpers.git(str(repo), "init", "-q", "-b", "main")
        cfg = repo / ".aidd" / "config.yaml"
        for reason, refused in (
            ('"ok\\nlevel: allow (built-in)"', True),
            ('"ok\\u001b[1A\\rlevel: allow (built-in)"', True),
            ('"ok\\u001b[1Alevel: allow"', False),
        ):
            cfg.write_text(f'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {{action: pr.merge, level: ask, reason: {reason}}}\n')
            with self.subTest(reason=reason), contextlib.chdir(repo):
                code, out = helpers.run_cli("risk", "--action", "pr.merge")
                self.assertNotIn("\nlevel: allow", out)
                self.assertNotIn("\x1b", out)
                self.assertEqual(code != 0, refused, out)
                if not refused:
                    self.assertIn("why: ok [1Alevel: allow\n", out)

    def test_suggest_names_the_next_step(self):
        code, out = self._answer("--suggest")
        self.assertEqual(code, 2)
        self.assertIn("run it inside", str(out))
        self.assertNotIn("fatal:", str(out))

    def test_the_mcp_tool_answers_the_same(self):
        from aidd.cli import mcp_server

        is_error, text = mcp_server.call("risk", {"command": "git push origin feat"}, str(self.folder))
        self.assertFalse(is_error, text)
        answer = json.loads(text)
        self.assertEqual((answer["level"], len(answer["notes"])), ("ask", 1))

    def test_a_folder_that_names_a_checkout_reads_its_config(self):
        """From outside, --folder reads that repository's config too, as the same command does from inside it."""
        repo = self.folder / "repo"
        (repo / ".aidd").mkdir(parents=True)
        helpers.git(str(repo), "init", "-q", "-b", "main")
        (repo / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {action: pr.merge, level: allow}\n')
        code, answer = self._answer("--command", "gh pr merge 3", "--folder", "repo")
        assert isinstance(answer, dict)
        self.assertEqual((code, answer["level"], answer["actions"][0]["source"], answer["notes"]), (0, "allow", "config", []))
        code, answer = self._answer("--command", "gh pr merge 3", "--folder", "no-such-folder")
        assert isinstance(answer, dict)
        self.assertEqual((answer["level"], len(answer["notes"])), ("ask", 1))  # still outside: the built-in rules, and the note
        # From inside another repository, --folder still reads the checkout it names, never the session's config.
        other = self.folder / "other"
        (other / ".aidd").mkdir(parents=True)
        helpers.git(str(other), "init", "-q", "-b", "main")
        (other / ".aidd" / "config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  rules:\n    - {action: pr.merge, level: report}\n')
        with contextlib.chdir(other):
            answer = json.loads(helpers.run_cli("risk", "--command", "gh pr merge 3", "--folder", str(repo), "--json")[1])
        self.assertEqual((answer["level"], answer["actions"][0]["source"]), ("allow", "config"))

    def test_folder_goes_with_command_only(self):
        """--folder names where a command line runs, so with --paths or --action it would read another config: refused."""
        repo = self.folder / "repo"
        repo.mkdir()
        helpers.git(str(repo), "init", "-q", "-b", "main")
        for argv in (("--paths", "src/a.py"), ("--action", "pr.merge")):
            with self.subTest(argv=argv):
                code, out = self._answer(*argv, "--folder", "repo")
                self.assertEqual(code, 2)
                self.assertIn("--command", str(out))

    def test_an_action_answer_says_what_is_unknown_too(self):
        code, answer = self._answer("--action", "pr.merge")
        assert isinstance(answer, dict)
        self.assertEqual((code, answer["level"], len(answer["notes"])), (0, "ask", 1))


class AnActionWithNoBranch(unittest.TestCase):
    """`--action` with no `--branch` takes the action's highest level on any branch, so `git.push`, whose built-in rules
    all name a branch, asks instead of reading as no rule at all."""

    def test_the_highest_level_on_any_branch(self):
        rs = risk.rule_set(None)
        cases = [
            # (action, branch, level)
            ("git.push", None, "ask"),
            ("git.push", "own", "allow"),
            ("git.push", "default", "ask"),
            ("pr.merge", None, "ask"),
            ("code.edit", None, "allow"),
        ]
        for action, branch, level in cases:
            with self.subTest(action=action, branch=branch):
                self.assertEqual(risk.level_on_any_branch(rs, action, branch=branch)[0], level)
        with tempfile.TemporaryDirectory() as d:
            helpers.git(d, "init", "-q", "-b", "main")
            with contextlib.chdir(d):
                answer = json.loads(helpers.run_cli("risk", "--action", "git.push", "--json")[1])
                self.assertEqual((answer["level"], len(answer["notes"])), ("ask", 1))  # the note names --branch
                answer = json.loads(helpers.run_cli("risk", "--action", "git.push", "--branch", "own", "--json")[1])
                self.assertEqual((answer["level"], answer.get("notes")), ("allow", None))


class EveryHarnessAsksTheSame(unittest.TestCase):
    """Every harness with ask rules asks for the same commands. Each format is read back from the file aidd wrote and
    matched the way its harness documents it: by glob over the whole command (Claude Code, OpenCode, Grok Build), by
    regular expression (VS Code), or by leading words (Codex, a word or a list; Qwen Code, the bare prefix or the prefix
    with ` *`)."""

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
        "gh repo edit o/r --visibility public",
        "gh repo archive o/r --yes",
        "gh repo unarchive o/r --yes",
        "gh repo rename new-name",
        "gh api -X DELETE repos/o/r/git/refs/heads/old",  # the leading-words formats ask at a flag-first `gh api` write
        "gh api --method PATCH repos/o/r",
        "gh api --input body.json repos/o/r/releases",
        "gh api graphql -f query=q",
    )
    # Only the leading-words formats ask here: they hold no `*` inside a command, so they ask at its first three words.
    WIDER = ("gh workflow run ci.yml", "npx wrangler d1 migrations list DB")
    # Only the glob and regular-expression formats ask here: a leading-words format holds no `db:*`, and asks at a `gh api`
    # write only when its flag comes first (`unwritten`).
    GLOB_ONLY = ("RAILS_ENV=production rails db:migrate", "gh api repos/o/r/git/refs/heads/old -X DELETE")
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
        "gh repo view o/r",
        "gh repo list o",
        "gh repo clone o/r",
    )

    @staticmethod
    def glob_asks(patterns: list[str], command: str) -> bool:
        import fnmatch

        return any(fnmatch.fnmatchcase(command, p) for p in patterns)

    @classmethod
    def claude_code_asks(cls, patterns: list[str], command: str) -> bool:
        """As Claude Code reads a rule: a trailing `:*` is its older prefix form, `ls:*` as `ls *`, which also matches
        the bare `ls`; anywhere else a colon is a literal."""
        prefix = [p[:-2] for p in patterns if p.endswith(":*")]
        return cls.glob_asks([p for p in patterns if not p.endswith(":*")] + [f"{p} *" for p in prefix], command) or command in prefix

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
                "opencode": [r["resource"] for r in read("opencode.json")["permissions"] if r["effect"] == "ask"],
                "grok": [bash(e) for e in tomllib.loads((root / ".grok/config.toml").read_text())["permission"]["ask"]],
                "vscode": [k[1:-1] for k, v in read(".vscode/settings.json")["chat.tools.terminal.autoApprove"].items() if v is False],
                "codex": [json.loads(m) for m in _re.findall(r"pattern = (\[.*?\]), decision", (root / ".codex/rules/aidd.rules").read_text())],
                "qwen": [bash(e) for e in read(".qwen/settings.json")["permissions"]["ask"]],
            }

    def test_the_same_commands_ask_everywhere(self):
        import re as _re

        w = self.written()
        asks = {
            "claude-code": lambda c: self.claude_code_asks(w["claude-code"], c),
            "opencode": lambda c: self.glob_asks(w["opencode"], c),
            "grok": lambda c: self.glob_asks(w["grok"], c),
            "vscode": lambda c: any(_re.search(r, c) for r in w["vscode"]),
            "codex": lambda c: self.words_ask(w["codex"], c),
            "qwen": lambda c: self.glob_asks(w["qwen"], c),
        }
        self.assertEqual(set(asks), set(risk.FORMATS), "every format is in this test")
        for command in self.ASK + self.ALLOW + self.WIDER + self.GLOB_ONLY:
            for fmt, ask in asks.items():
                with self.subTest(command=command, harness=fmt):
                    words = risk.FORMATS[fmt].match == "words"
                    wider = command in self.WIDER and words
                    self.assertEqual(ask(command), command in self.ASK or wider or (command in self.GLOB_ONLY and not words))

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
            ".vscode/settings.json": {"editor.tabSize": 2, "chat.tools.terminal.autoApprove": {"npm test": True}},
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
            risk.remove_harness_rules(root)
            for rel, data in own.items():
                with self.subTest(file=rel):
                    left = json.loads((root / rel).read_text())
                    for key, value in data.items():
                        self.assertEqual(left[key], value)
            self.assertEqual((root / ".grok/config.toml").read_text(), 'model = "x"\n')

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
            ("qwen", ".qwen/settings.json"): "{not json",
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
            for fmt in ("vscode", "qwen"):
                risk.apply_harness_rules(root, fmt, ["git tag*"])
            odd = {
                ".vscode/settings.json": {"a": 1},
                ".qwen/settings.json": {"permissions": "x"},
            }
            for rel, data in odd.items():
                (root / rel).write_text(json.dumps(data))
            risk.remove_harness_rules(root)
            for rel, data in odd.items():
                with self.subTest(rel=rel):
                    self.assertEqual(json.loads((root / rel).read_text()), data)

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
        # Claude Code reads a trailing `:*` that starts a word as its older prefix form, so that one is left to the skill (R413).
        self.assertEqual(risk.unwritten("claude-code", list(cases)), ["git push * :*"])

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
        for fmt in ("codex", "qwen"):
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
