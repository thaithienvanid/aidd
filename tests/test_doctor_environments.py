"""`aidd doctor` on where a push deploys: `environments: []` beside a workflow that deploys on a push to the default branch,
and an environment whose branches are gone (R528, part 3). The delegate check already fails closed on both, so doctor says why."""

import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ

from aidd import config
from aidd.setup import doctor_environments

DEPLOY_ON_MAIN = "name: deploy\non:\n  push:\n    branches: [main]\njobs:\n  ship:\n    environment: production\n    steps:\n      - run: echo ship\n"
DEPLOY_ON_STAGING = DEPLOY_ON_MAIN.replace("[main]", "[staging]")
DEPLOY_ON_EVERY_PUSH = "name: deploy\non: push\njobs:\n  ship:\n    environment: production\n    steps:\n      - run: echo ship\n"
TEST_ONLY = "name: test\non:\n  push:\n    branches: [main]\njobs:\n  t:\n    steps:\n      - run: pytest\n"
GITLAB = "deploy:\n  environment: production\n  script: [echo]\n  rules:\n    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH\n"


def cfg(environments: str = "") -> config.Config:
    return config.load_text('aidd_version: "1.0.0"\nprofile: solo\n' + environments)


class DoctorEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Maya Lee")
        git(self.root, "config", "user.email", "maya@users.noreply.github.com")
        git(self.root, "commit", "-q", "--allow-empty", "-m", "start")

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, path: str, text: str) -> None:
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text, encoding="utf-8")

    def warnings(self, environments: str) -> list[str]:
        return [m for level, m in doctor_environments.environment_checks(self.root, cfg(environments)) if level == "warn"]

    def test_nothing_deploys_beside_a_workflow_that_does(self):
        cases = {
            "on the default branch": ({".github/workflows/deploy.yml": DEPLOY_ON_MAIN}, ".github/workflows/deploy.yml:7"),
            "on every push": ({".github/workflows/deploy.yml": DEPLOY_ON_EVERY_PUSH}, ".github/workflows/deploy.yml:5"),
            "in GitLab": ({".gitlab-ci.yml": GITLAB}, ".gitlab-ci.yml:2"),
        }
        for name, (files, where) in cases.items():
            with self.subTest(name):
                for path, text in files.items():
                    self.put(path, text)
                (said,) = self.warnings("environments: []\n")
                self.assertIn("environments: [] says no push deploys", said)
                self.assertIn(where, said, "it names the file and line")
                for path in files:
                    (self.root / path).unlink()

    def test_a_tag_pattern_is_not_a_deploy_on_the_default_branch_and_a_pages_job_is_one(self):
        self.put(".gitlab-ci.yml", "deploy:\n  environment: production\n  script: [echo]\n  rules:\n    - if: $CI_COMMIT_TAG =~ /^v/\n")
        self.assertEqual(self.warnings("environments: []\n"), [])
        self.put(".gitlab-ci.yml", "pages:\n  script: [make site]\n")
        (said,) = self.warnings("environments: []\n")
        self.assertIn(".gitlab-ci.yml:1", said)

    def test_no_warning_when_the_answer_and_the_files_agree(self):
        cases = {
            "nothing deploys, and no workflow does": ("environments: []\n", {".github/workflows/test.yml": TEST_ONLY}),
            "nothing deploys, and a workflow deploys another branch": ("environments: []\n", {".github/workflows/deploy.yml": DEPLOY_ON_STAGING}),
            "environments unset": ("", {".github/workflows/deploy.yml": DEPLOY_ON_MAIN}),
            "an environment names it": ("environments:\n  - {name: production, branches: [main]}\n", {".github/workflows/deploy.yml": DEPLOY_ON_MAIN}),
        }
        for name, (environments, files) in cases.items():
            with self.subTest(name):
                for path, text in files.items():
                    self.put(path, text)
                self.assertEqual(self.warnings(environments), [])
                for path in files:
                    (self.root / path).unlink()

    def test_an_environment_whose_branches_are_gone(self):
        git(self.root, "branch", "release/1.0")
        cases = {
            "a branch that does not exist": ("environments:\n  - {name: staging, branches: [staging]}\n", True),
            "a glob that no branch matches": ("environments:\n  - {name: staging, branches: ['stage/*']}\n", True),
            "none of several exists": ("environments:\n  - {name: staging, branches: [staging, stage]}\n", True),
            "the default branch": ("environments:\n  - {name: production, branches: [main]}\n", False),
            "a glob a branch matches": ("environments:\n  - {name: staging, branches: ['release/*']}\n", False),
            "one of several exists": ("environments:\n  - {name: staging, branches: [staging, main]}\n", False),
            "tags only": ("environments:\n  - {name: production, tags: ['v*']}\n", False),
        }
        for name, (environments, warned) in cases.items():
            with self.subTest(name):
                found = self.warnings(environments)
                self.assertEqual(len(found), int(warned), found)
                if warned:
                    self.assertIn("no branch like that exists", found[0])

    def test_a_branch_on_origin_counts(self):
        git(self.root, "update-ref", "refs/remotes/origin/staging", "HEAD")
        self.assertEqual(self.warnings("environments:\n  - {name: staging, branches: [staging]}\n"), [])

    def test_doctor_prints_the_warning(self):
        self.put(".github/workflows/deploy.yml", DEPLOY_ON_MAIN)
        init = aidd_subprocess(
            "init", ".", "--profile", "solo", "--ci", "none", "--harness", "none", "--environment", "none", cwd=self.root, env=hermetic_environ()
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        done = aidd_subprocess("doctor", cwd=self.root, env=hermetic_environ())
        line = next(ln for ln in done.stdout.splitlines() if "environments: [] says no push deploys" in ln)
        self.assertTrue(line.startswith("[warn]"), line)
        self.assertIn(".github/workflows/deploy.yml:7", line)


if __name__ == "__main__":
    unittest.main()
