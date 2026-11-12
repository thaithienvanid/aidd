"""Where a push deploys, at `aidd init`: the flags that state it (`--environment NAME=REF`, `--environment none`,
`--own-environment NAME=REF`), the environments init reads from the deploying workflows when no flag answers, and what
`--dry-run` and `--force` do with them. An environment init read is written only when it names the default branch,
because a list without it would say that nothing deploys there, which only a person can say."""

import tempfile
import unittest
from pathlib import Path

from helpers import aidd_here, aidd_subprocess, git, hermetic_environ

from aidd import config
from aidd.cli import arguments

BRANCH_AND_TAG = (
    "name: deploy\non:\n  push:\n    branches: [main]\n    tags: ['v*']\njobs:\n  ship:\n    environment: Production\n    steps:\n      - run: echo ship\n"
)
TAG_ONLY = "name: release\non:\n  push:\n    tags: ['v*']\njobs:\n  ship:\n    environment: release\n    steps:\n      - run: echo ship\n"
EVERY_PUSH = "name: deploy\non: push\njobs:\n  ship:\n    environment: production\n    steps:\n      - run: echo ship\n"
GITLAB = "deploy:\n  environment:\n    name: production\n  script: [echo]\n  rules:\n    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH\n"
INIT = ("init", ".", "--profile", "solo", "--ci", "none", "--harness", "claude-code")


class FlagTests(unittest.TestCase):
    def test_what_the_flags_say(self):
        cases = {
            "a branch": (["production=main"], None, [{"name": "production", "branches": ["main"]}]),
            "git's own spelling of a branch": (["production=refs/heads/main"], None, [{"name": "production", "branches": ["main"]}]),
            "a tag glob": (["production=refs/tags/v*"], None, [{"name": "production", "tags": ["v*"]}]),
            "one name, a branch and a tag": (
                ["production=main", "production=refs/tags/v*"],
                None,
                [{"name": "production", "branches": ["main"], "tags": ["v*"]}],
            ),
            "one name twice": (["production=main", "production=main"], None, [{"name": "production", "branches": ["main"]}]),
            "your own": (None, ["dev=dev"], [{"name": "dev", "branches": ["dev"], "shared": False}]),
            "a shared one and your own": (
                ["production=main"],
                ["dev=refs/tags/dev-1"],
                [{"name": "production", "branches": ["main"]}, {"name": "dev", "tags": ["dev-1"], "shared": False}],
            ),
            "none deploys": (["none"], None, []),
            "no flag": (None, None, None),
        }
        for name, (shared, own, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(arguments.environments(shared, own), want)

    def test_what_the_flags_refuse(self):
        cases = {
            "none beside a name": (["none", "production=main"], None, "give it alone"),
            "none beside your own": (["none"], ["dev=dev"], "give it alone"),
            "none as a name": (["none=main"], None, "reserved"),
            "none as your own name": (None, ["none=main"], "reserved"),
            "no ref": (["production"], None, "NAME=REF"),
            "an empty ref": (["production="], None, "NAME=REF"),
            "an empty tag": (["production=refs/tags/"], None, "NAME=REF"),
            "a capital in the name": (["Production=main"], None, "NAME=REF"),
            "a space in the ref": (["production=a b"], None, "NAME=REF"),
            "a colon in the ref": (["production=a:b"], None, "NAME=REF"),
            "a wildcard in your own branch": (None, ["dev=dev/*"], "wildcard"),
            "a wildcard in your own tag": (None, ["dev=refs/tags/dev-?"], "wildcard"),
            "one name shared and your own": (["dev=main"], ["dev=dev"], "both"),
        }
        for name, (shared, own, why) in cases.items():
            with self.subTest(name), self.assertRaises(ValueError) as caught:
                arguments.environments(shared, own)
            self.assertIn(why, str(caught.exception), name)

    def test_a_shared_wildcard_is_fine(self):
        self.assertEqual(arguments.environments(["staging=release/*"], None), [{"name": "staging", "branches": ["release/*"]}])


class InitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "repo"
        (self.root / ".github/workflows").mkdir(parents=True)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Maya Lee")
        git(self.root, "config", "user.email", "maya@users.noreply.github.com")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "start")

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, path: str, text: str) -> None:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text, encoding="utf-8")

    def aidd(self, *args: str):
        return aidd_here(*args, cwd=self.root)

    def environments(self):
        return config.load_file(config.CONFIG_PATH, str(self.root)).get("environments")


class FillInTests(InitCase):
    def test_init_writes_the_environments_the_workflows_name(self):
        cases = {
            "a branch and a tag": (".github/workflows/deploy.yml", BRANCH_AND_TAG, [{"name": "production", "branches": ["main"], "tags": ["v*"]}], ":8"),
            "GitLab": (".gitlab-ci.yml", GITLAB, [{"name": "production", "branches": ["main"]}], ".gitlab-ci.yml:2"),
        }
        for name, (path, text, want, where) in cases.items():
            with self.subTest(name):
                self.put(path, text)
                done = self.aidd(*INIT, "--delegate")
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(self.environments(), want)
                written = (self.root / config.CONFIG_PATH).read_text(encoding="utf-8")
                self.assertIn(f"# read from {path}", written)
                self.assertIn(where, written, "the comment names the line")
                self.assertIn("config   wrote environments from your workflows: production", done.stdout)
                self.assertIn("a merge into it stays yours", done.stdout)
                self.assertNotIn("does a push to the default branch deploy anything", done.stdout, "the question is answered by what it read")
                self.assertFalse(any(e.get("shared") is False for e in self.environments()), "what it reads is shared")
                (self.root / config.CONFIG_PATH).unlink()
                (self.root / path).unlink()

    def test_init_leaves_environments_unset_when_none_it_read_names_the_default_branch(self):
        """A list without the default branch would say that nothing deploys there. A host's Git integration can, so only a person says it."""
        cases = {
            "a tag only": TAG_ONLY,
            "a workflow on every push": EVERY_PUSH,
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.put(".github/workflows/deploy.yml", text)
                done = self.aidd(*INIT, "--delegate")
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertIsNone(self.environments())
                self.assertIn("hint     your workflows deploy:", done.stdout)
                self.assertIn("only you can say that", done.stdout)
                self.assertIn("does a push to the default branch deploy anything", done.stdout)
                (self.root / config.CONFIG_PATH).unlink()

    def test_a_flag_answers_instead_of_the_workflows(self):
        self.put(".github/workflows/deploy.yml", BRANCH_AND_TAG)
        done = self.aidd(*INIT, "--environment", "live=refs/tags/v*")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.environments(), [{"name": "live", "tags": ["v*"]}])
        self.assertNotIn("read from", (self.root / config.CONFIG_PATH).read_text(encoding="utf-8"))

    def test_none_beside_a_deploying_workflow_names_the_workflow(self):
        self.put(".github/workflows/deploy.yml", BRANCH_AND_TAG)
        done = self.aidd(*INIT, "--delegate", "--environment", "none")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.environments(), [])
        self.assertIn("you said nothing deploys from a push, but your workflows deploy at .github/workflows/deploy.yml:8", done.stdout)

    def test_your_own_environment_is_written_as_not_shared(self):
        done = self.aidd(*INIT, "--own-environment", "dev=dev", "--environment", "production=main")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.environments(), [{"name": "dev", "branches": ["dev"], "shared": False}, {"name": "production", "branches": ["main"]}][::-1])

    def test_no_workflow_and_no_flag_writes_none(self):
        done = self.aidd(*INIT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIsNone(self.environments())
        self.assertNotIn("your workflows", done.stdout)

    def test_init_keeps_a_config_that_is_there_and_says_nothing_of_writing_environments(self):
        self.put(".github/workflows/deploy.yml", BRANCH_AND_TAG)
        self.aidd(*INIT, "--environment", "none")
        done = self.aidd(*INIT)
        self.assertEqual(self.environments(), [])
        self.assertNotIn("wrote environments", done.stdout)


class DryRunAndForceTests(InitCase):
    def test_the_dry_run_shows_the_environments_it_read(self):
        self.put(".github/workflows/deploy.yml", BRANCH_AND_TAG)
        done = self.aidd(*INIT, "--dry-run")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("config   would write environments from your workflows: production (main, refs/tags/v*) at .github/workflows/deploy.yml:8", done.stdout)
        self.assertIn("environments:\n  # read from .github/workflows/deploy.yml:8\n  - name: production", done.stdout)
        self.assertFalse((self.root / config.CONFIG_PATH).exists(), "a dry run writes nothing")

    def test_the_dry_run_shows_what_a_flag_would_write(self):
        done = self.aidd(*INIT, "--dry-run", "--environment", "production=main", "--own-environment", "dev=dev")
        self.assertIn("  - name: production\n    branches: [main]\n  - name: dev\n    branches: [dev]\n    shared: false", done.stdout)

    def test_force_keeps_the_environments_a_person_wrote(self):
        self.put(".github/workflows/deploy.yml", BRANCH_AND_TAG)
        self.aidd(*INIT)
        path = self.root / config.CONFIG_PATH
        mine = path.read_text(encoding="utf-8").replace("branches: [main]", "branches: [main, trunk]  # my note")
        path.write_text(mine, encoding="utf-8")
        done = self.aidd(*INIT, "--force")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), mine, "--force keeps the environments, and the comment beside them")
        self.put(".github/workflows/deploy.yml", EVERY_PUSH)
        again = self.aidd(*INIT, "--force")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertEqual(path.read_text(encoding="utf-8"), mine)

    def test_force_with_a_flag_changes_only_that_environment(self):
        self.aidd(*INIT, "--environment", "production=main", "--environment", "staging=release")
        done = self.aidd(*INIT, "--force", "--own-environment", "dev=dev")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual([e["name"] for e in self.environments()], ["production", "staging", "dev"])
        self.assertIn("config   added   environments.dev:", done.stdout)


class UnsureDefaultBranchTests(InitCase):
    """No origin HEAD, no `main`, no `master`: git cannot tell the default branch, so init guesses nothing."""

    def setUp(self):
        super().setUp()
        git(self.root, "branch", "-m", "trunk")
        git(self.root, "branch", "dev")

    def test_init_writes_no_environments_and_says_why(self):
        self.put(".github/workflows/deploy.yml", BRANCH_AND_TAG.replace("[main]", "['**']"))  # it lists every branch it could be
        done = self.aidd(*INIT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIsNone(self.environments())
        self.assertIn("git cannot tell the default branch (trunk, main, master, dev could be it), so init wrote no environments", done.stdout)
        self.assertNotIn("wrote environments", done.stdout)

    def test_a_gitlab_default_branch_does_not_become_every_branch(self):
        self.put(".gitlab-ci.yml", GITLAB)
        done = self.aidd(*INIT, "--ci", "gitlab")
        self.assertIsNone(self.environments())
        self.assertIn("git cannot tell the default branch", done.stdout)
        self.assertIn(".gitlab-ci.yml:2", done.stdout)


class FlagsNamedOnceTests(InitCase):
    def test_delegate_names_the_environment_flags_once(self):
        self.put(".github/workflows/deploy.yml", EVERY_PUSH)
        done = self.aidd(*INIT, "--delegate")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("does a push to the default branch deploy anything", done.stdout)
        self.assertEqual(done.stdout.count("--environment NAME=REF"), 1, done.stdout)


class KeptConfigTests(InitCase):
    """`init --force --delegate` on a config that stays: its lines tell the truth about the `environments` that stay, not about the
    ones init would have written."""

    def kept(self, environments: str, workflow: str | None = EVERY_PUSH) -> str:
        self.aidd(*INIT, *environments.split())  # the config that stays; the workflow comes after it
        if workflow:
            self.put(".github/workflows/deploy.yml", workflow)
        done = self.aidd(*INIT, "--force", "--delegate")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def test_kept_environments_that_name_the_branch_ask_nothing_and_claim_nothing_is_unset(self):
        out = self.kept("--environment production=main", BRANCH_AND_TAG)
        for words in ("does a push to the default branch deploy", "stays unset", "comment beside", "says nothing deploys"):
            self.assertNotIn(words, out)

    def test_kept_environments_that_say_nothing_deploys_beside_a_deploying_workflow_say_so(self):
        out = self.kept("--environment none")
        self.assertIn(".aidd/config.yaml says nothing deploys from a push, but your workflows deploy at .github/workflows/deploy.yml", out)
        self.assertIn("a merge into main stays yours", out)
        self.assertNotIn("stays unset", out)

    def test_a_kept_config_with_no_environments_is_told_so_and_not_pointed_at_a_comment(self):
        out = self.kept("", BRANCH_AND_TAG)
        self.assertIn("the config you kept leaves `environments` unset", out)
        self.assertIn("--environment NAME=REF", out)
        self.assertNotIn("comment beside", out)
        self.assertIsNone(self.environments())

    def test_delegate_needs_a_name_and_an_email_to_act_for(self):
        git(self.root, "config", "--unset", "user.name")
        env = hermetic_environ() | {"HOME": str(self.root.parent), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
        done = aidd_subprocess(*INIT, "--delegate", cwd=self.root, env=env)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("names you as the one it acts for", done.stdout + done.stderr)
        self.assertFalse((self.root / config.CONFIG_PATH).exists(), "nothing is written")


class RefusalTests(InitCase):
    def test_a_bad_answer_stops_before_init_writes_or_prints_anything_else(self):
        for flags in (
            ["--environment", "none", "--environment", "production=main"],
            ["--environment", "none=main"],
            ["--own-environment", "dev=dev/*"],
        ):
            with self.subTest(flags):
                done = self.aidd("init", ".", "--profile", "solo", "--ci", "none", *flags)
                self.assertEqual(done.returncode, 2, done.stdout)
                self.assertEqual(done.stdout, "")
                self.assertTrue(done.stderr.startswith(("error:", "aidd:")), done.stderr)
                self.assertFalse((self.root / config.CONFIG_PATH).exists())

    def test_the_old_flag_is_gone(self):
        done = self.aidd(*INIT, "--deploys-nowhere")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("unknown option --deploys-nowhere", done.stderr)


if __name__ == "__main__":
    unittest.main()
