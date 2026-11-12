"""What the delegate check reads about where a push deploys: the workflows that deploy, and the one answer to "does a push
to this branch deploy?" that a delegated push and a delegated merge share (`delegation/deploys.py`). What a change touches
is in test_delegation_diff."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import git
from test_delegation_check import Case, FakeGitHub, Repo, codes

from aidd.delegation import policy
from aidd.kernel import git as kernel_git
from aidd.kernel import strict_yaml


PRODUCTION = {"name": "production", "branches": ["main"]}
OWN = {"name": "dev", "branches": ["main"], "shared": False}
OTHER = {"name": "staging", "branches": ["release"]}
DEPLOY_WORKFLOW = "name: deploy\non:\n  push:\n    branches: [main]\njobs:\n  ship:\n    environment: production\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ship\n"


GITLAB = "deploy:\n  environment: production\n  script: [echo]\n  rules:\n    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH\n"
GITLAB_OTHER_BRANCH = GITLAB.replace("$CI_DEFAULT_BRANCH", '"release"')
GITLAB_UNREAD_RULE = GITLAB.replace("$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH", "$CI_PIPELINE_SOURCE == 'push'")

EXTENDS = "extends:\n  - path: presets/org.yaml\n"
PRESET = "presets/org.yaml"


def preset(environments: list[dict] | None = None, extra: str = "") -> str:
    """A parent config with its own `environments` (None: it sets none) and any more top-level lines."""
    listed = strict_yaml.dump({"environments": environments}) if environments is not None else ""
    return 'aidd_version: "1.0.0"\nprofile: solo\n' + listed + extra


LOCKED_PRODUCTION = "risks:\n  rules:\n    - {action: deploy.run, level: ask, environment: production, locked: true}\n"


class DeployCheckTests(Case):
    """One question, whether a push to the default branch deploys, decides a merge into it. Each case is the config's
    `environments` (None: unset), the files the default branch tracks, and the reasons the merge defers for."""

    def merge_result(self, environments, tracked: dict[str, str], top: str = "") -> dict:
        with tempfile.TemporaryDirectory() as d:
            repo = Repo(Path(d).resolve(), environments=environments, top=top)
            git(repo.root, "checkout", "-q", "main")
            for path, text in tracked.items():
                repo.write(path, text)
            repo.commit("track files")
            git(repo.root, "checkout", "-q", "-B", "feature")
            return repo.check(repo.change())

    def merge_codes(self, environments, tracked: dict[str, str], top: str = "") -> list[str]:
        return codes(self.merge_result(environments, tracked, top))

    def test_the_stop_for_an_unset_answer_asks_the_one_question_and_names_the_edit(self):
        (reason,) = self.merge_result(None, {})["reasons"]
        self.assertEqual(reason["code"], "environments_unset")
        self.assertIn("sets no `environments` of its own", reason["detail"])
        self.assertNotIn("Ask the person", reason["detail"], "the question is said once, in the step")
        step = policy.reasons()["environments_unset"]["next"]["what"]
        for words in ("Ask the person once", "Git integration", "`environments`", "`environments: []`"):
            self.assertIn(words, step)
        self.assertIn("Editing the config is an ask", step)

    def test_a_merge_defers_unless_environments_says_a_push_deploys_nowhere(self):
        cases = {
            # name: (environments, tracked files, the reasons)
            "unset: aidd cannot tell": (None, {}, ["environments_unset"]),
            "none deploys from a push": ((), {}, []),
            "an environment lists another branch": ([OTHER], {}, []),
            "a shared environment lists the default branch": ([PRODUCTION], {}, ["merge_deploys"]),
            "your own environment lists it too": ([OWN], {}, ["merge_deploys"]),
            "a glob that matches it": ([{"name": "prod", "branches": ["ma*"]}], {}, ["merge_deploys"]),
            "a deploy workflow": ((), {".github/workflows/deploy.yml": DEPLOY_WORKFLOW}, ["merge_deploys"]),
            "a GitLab job on the default branch, in a GitHub repository": ((), {".gitlab-ci.yml": GITLAB}, ["merge_deploys"]),
            "a GitLab job on another branch": ((), {".gitlab-ci.yml": GITLAB_OTHER_BRANCH}, []),
            "a GitLab job with a rule it cannot read": ((), {".gitlab-ci.yml": GITLAB_UNREAD_RULE}, ["merge_deploys"]),
            "a host's deploy file and no environment": ((), {"web/vercel.json": "{}\n"}, ["merge_deploys"]),
            "a host's deploy file in other letters": ((), {"web/Vercel.JSON": "{}\n"}, ["merge_deploys"]),
            "a host's deploy file, with the environment that lists the branch": ([PRODUCTION], {"vercel.json": "{}\n"}, ["merge_deploys"]),
            "unset, and a host's deploy file": (None, {"vercel.json": "{}\n"}, ["environments_unset", "merge_deploys"]),
        }
        for name, (environments, tracked, reasons) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.merge_codes(environments, tracked), reasons)

    def test_one_merge_deploys_names_every_cause_it_found(self):
        """`merge_deploys` replaced two codes, so its detail names each kind of evidence: the environment and the workflow."""
        (reason,) = self.merge_result([PRODUCTION], {".github/workflows/deploy.yml": DEPLOY_WORKFLOW})["reasons"]
        self.assertEqual(reason["code"], "merge_deploys")
        self.assertIn("environment production", reason["detail"])
        self.assertIn(".github/workflows/deploy.yml", reason["detail"])

    def test_a_gitlab_file_that_is_a_link_is_one_that_may_deploy(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Repo(Path(d).resolve(), environments=())
            git(repo.root, "checkout", "-q", "main")
            repo.write("ci/gitlab.yml", GITLAB)
            (repo.root / ".gitlab-ci.yml").symlink_to("ci/gitlab.yml")
            repo.commit("link the CI file")
            git(repo.root, "checkout", "-q", "-B", "feature")
            self.assertEqual(codes(repo.check(repo.change())), ["merge_deploys"])

    def test_an_environment_any_layer_lists_counts_and_only_this_repository_or_a_lock_says_nowhere(self):
        locks = "locks: [environments]\n"
        cases = {
            # name: (this config's environments, the parent, the reasons)
            "a parent lists the default branch and the child says none": ((), preset([PRODUCTION]), ["merge_deploys"]),
            "a parent lists it and the child lists only its own": ([{"name": "preview", "branches": ["preview"]}], preset([PRODUCTION]), ["merge_deploys"]),
            "a parent lists it and a locked rule keeps it over the child's none": ((), preset([PRODUCTION], LOCKED_PRODUCTION), ["merge_deploys"]),
            "a parent says none and the child says nothing": (None, preset([]), ["environments_unset"]),
            "a parent lists another branch and the child says none": ((), preset([OTHER]), []),
            "a parent locks the list as none and the child says nothing": (None, preset([], locks), []),
        }
        for name, (environments, parent, reasons) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.merge_codes(environments, {PRESET: parent}, EXTENDS), reasons)
        # This repository's own lock is the person's own file, so it says the same as a parent's: it loosens nothing against them.
        self.assertEqual(self.merge_codes(None, {PRESET: preset([])}, EXTENDS + locks), [])

    def test_an_unreadable_workflow_is_one_that_may_deploy(self):
        shown = kernel_git.show

        def show(ref, path, cwd="."):
            return None if path.startswith(".github/workflows/") else shown(ref, path, cwd)

        with mock.patch.object(kernel_git, "show", show):
            self.assertEqual(self.merge_codes((), {".github/workflows/ci.yml": "name: ci\non: [pull_request]\n"}), ["merge_deploys"])

    def test_a_change_to_a_parent_config_is_a_reserved_path(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Repo(Path(d).resolve(), top=EXTENDS)
            git(repo.root, "checkout", "-q", "main")
            repo.write(PRESET, preset([]))
            repo.commit("a parent")
            git(repo.root, "checkout", "-q", "-B", "feature")
            self.assertIn("reserved_path", codes(repo.check(repo.change(PRESET, preset([OTHER])))))

    def push_codes(self, environments, tracked: dict[str, str], branch: str = "feature") -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            repo = Repo(Path(d).resolve(), environments=environments)
            git(repo.root, "checkout", "-q", "main")
            for path, text in tracked.items():
                repo.write(path, text)
            repo.commit("track files")
            git(repo.root, "checkout", "-q", "-B", branch)
            head = repo.change()
            tip = git(repo.root, "rev-parse", "main")
            git(repo.root, "remote", "add", "origin", "https://github.com/acme/shop.git")
            pull = {"base": "main", "head_sha": head, "state": "open"}
            result = repo.check(head, f"git push origin {head}:refs/heads/{branch}", action="git.push", github=FakeGitHub(tip, open_pull_for=pull))
            return codes(result)

    def test_a_push_to_a_branch_that_deploys_defers_and_the_default_branch_rules_stay_out_of_it(self):
        ON_FEATURE = DEPLOY_WORKFLOW.replace("[main]", "[feature]")
        host = {"vercel.json": "{}\n"}
        cases = {
            # name: (environments, tracked files, the branch pushed, the reasons)
            "an environment lists the branch": ([{"name": "preview", "branches": ["feature"]}], host, "feature", ["branch_deploys"]),
            "none lists it": ([PRODUCTION], host, "feature", []),
            "unset": (None, host, "feature", []),
            "a workflow deploys on the branch": ((), {".github/workflows/deploy.yml": ON_FEATURE}, "feature", ["branch_deploys"]),
            "a workflow deploys on another branch": ((), {".github/workflows/deploy.yml": DEPLOY_WORKFLOW}, "feature", []),
            "a name with no wildcard lists only itself": ([{"name": "staging", "branches": ["release"]}], {}, "release/hotfix", []),
        }
        for name, (environments, tracked, branch, reasons) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.push_codes(environments, tracked, branch), reasons)


if __name__ == "__main__":
    unittest.main()
