"""What the repository's workflows say deploys on a push (`delegation/deploy_evidence.py`): the refs that start a deploy and
the environment it names, in GitHub Actions and GitLab CI, read as text. A shape the reader does not read is unread, never
a push that deploys nothing."""

import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  # puts src on the path

from aidd import delegation, risk
from aidd.delegation import deploy_evidence as evidence


def workflow(on: str, job: str = "    environment: production\n    steps:\n      - run: echo ship\n") -> str:
    return f"name: deploy\n{on}jobs:\n  ship:\n{job}"


PUSH_MAIN = "on:\n  push:\n    branches: [main]\n"


class PushRefsTests(unittest.TestCase):
    def test_which_refs_a_push_trigger_lists(self):
        cases = {
            "a branch list in brackets": ("on:\n  push:\n    branches: [main, 'release/*']\n", (["main", "release/*"], [])),
            "a branch list with dashes": ("on:\n  push:\n    branches:\n      - main\n      - dev\n", (["main", "dev"], [])),
            "a list at the key's own indent": ("on:\n  push:\n    branches:\n    - main\n", (["main"], [])),
            "tags": ("on:\n  push:\n    tags: ['v*']\n", ([], ["v*"])),
            "branches and tags": ("on:\n  push:\n    branches: [main]\n    tags:\n      - 'v*'\n", (["main"], ["v*"])),
            "other triggers beside it": ("on:\n  issues:\n  push:\n    branches: [main]\n  workflow_dispatch:\n", (["main"], [])),
            "a pull request beside it": ("on:\n  pull_request:\n  push:\n    branches: [main]\n", None),
            "a pull request target beside it": ("on:\n  push:\n    branches: [main]\n  pull_request_target:\n", None),
            "a merge group beside it": ("on:\n  push:\n    branches: [main]\n  merge_group:\n", None),
            "a push with nothing listed": ("on: push\n", None),
            "a push in a list": ("on: [push, pull_request]\n", None),
            "a push block with only paths": ("on:\n  push:\n    paths: ['src/**']\n", None),
            "branches-ignore": ("on:\n  push:\n    branches-ignore: [dev]\n", None),
            "tags-ignore beside branches": ("on:\n  push:\n    branches: [main]\n    tags-ignore: ['v*']\n", None),
            "a negated glob": ("on:\n  push:\n    branches: [main, '!release']\n", None),
            "a pattern with a class": ("on:\n  push:\n    branches: ['[m]ain']\n", None),
            "a pattern with a question mark": ("on:\n  push:\n    branches: ['mainn?']\n", None),
            "a tag pattern with a plus": ("on:\n  push:\n    tags: ['v1+']\n", None),
            "no push": ("on:\n  pull_request:\n", None),
            "no trigger": ("name: x\n", None),
        }
        for name, (on, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(evidence.push_refs(on), None if want is None else (want[0], want[1]))


class UnreadFilesTests(unittest.TestCase):
    """A workflow that is a link, or too large to read, may deploy: it is unread, never left out."""

    def tree(self, root: Path) -> None:
        (root / ".github/workflows").mkdir(parents=True)
        (root / "elsewhere.yml").write_text(workflow("on: push\n"), encoding="utf-8")
        (root / ".github/workflows/linked.yml").symlink_to("../../elsewhere.yml")
        (root / ".github/workflows/big.yaml").write_text("# " + "x" * 2_000_000 + "\n" + workflow("on: push\n"), encoding="utf-8")
        (root / ".gitlab-ci.yml").symlink_to("elsewhere.yml")

    def test_a_link_or_a_large_file_is_unread_for_init_and_for_doctor(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            self.tree(root)
            unread = delegation.read_deploy_evidence(root, ["main"]).unread
            for name in ("linked.yml", "big.yaml", ".gitlab-ci.yml"):
                self.assertTrue(any(name in u for u in unread), (name, unread))
            reached = delegation.workflows_deploying_on(root, "main", risk.rule_set(None))
            for name in ("linked.yml", "big.yaml", ".gitlab-ci.yml"):
                self.assertTrue(any(name in u and "unreadable" in u for u in reached), (name, reached))


class NameTests(unittest.TestCase):
    def test_an_environment_name_becomes_one_the_config_accepts(self):
        cases = {
            "Production": "production",
            "'Staging EU'": "staging-eu",
            "prod_1": "prod_1",
            "${{ inputs.target }}": "fallback",
            "1st": "fallback",
            "": "fallback",
        }
        for raw, want in cases.items():
            with self.subTest(raw):
                self.assertEqual(evidence.environment_name(raw, "fallback"), want)

    def test_a_job_names_its_environment_in_any_of_three_ways(self):
        cases = {
            "a scalar": "    environment: Production\n",
            "a name key": "    environment:\n      name: production\n      url: https://x.example\n",
            "a map": "    environment: {name: production, url: https://x.example}\n",
        }
        for name, job in cases.items():
            with self.subTest(name):
                self.assertEqual(evidence.github_environments(workflow(PUSH_MAIN, job + "    steps: []\n"), "stem"), [("production", 7)])

    def test_an_input_named_environment_is_not_a_job_environment(self):
        text = "on:\n  workflow_dispatch:\n    inputs:\n      environment:\n        type: choice\njobs:\n  ship:\n    steps: []\n"
        self.assertEqual(evidence.github_environments(text, "stem"), [])


class GitlabTests(unittest.TestCase):
    def test_which_refs_start_a_job(self):
        cases = {
            "the default branch": (["- if: '$CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH'"], (["main"], [])),
            "a branch by name": (['- if: $CI_COMMIT_BRANCH == "release"'], (["release"], [])),
            "the older ref name": (["- if: $CI_COMMIT_REF_NAME == 'main'"], (["main"], [])),
            "any tag": (["- if: $CI_COMMIT_TAG"], ([], ["*"])),
            "a branch and any tag": (["- if: $CI_COMMIT_BRANCH == 'main'", "- if: $CI_COMMIT_TAG"], (["main"], ["*"])),
            "a tag pattern is every tag": (["- if: $CI_COMMIT_TAG =~ /^v/"], ([], ["*"])),
            "a tag pattern with an escaped slash": ([r"- if: $CI_COMMIT_TAG =~ /^v\/x/"], ([], ["*"])),
            "a tag pattern beside a branch": (["- if: $CI_COMMIT_TAG =~ /^v/ || $CI_COMMIT_BRANCH == 'main'"], None),
            "a tag pattern then a branch pattern": (["- if: $CI_COMMIT_TAG =~ /^v/ || $CI_COMMIT_BRANCH =~ /main/"], None),
            "a branch test then a tag test": (["- if: $CI_COMMIT_BRANCH == 'dev' || $CI_COMMIT_TAG"], None),
            "a branch test then more": (['- if: $CI_COMMIT_BRANCH == "dev" && $CI_PIPELINE_SOURCE == "push"'], None),
            "a tag test and a branch test": (["- if: $CI_COMMIT_TAG && $CI_COMMIT_BRANCH == 'main'"], None),
            "a pattern body with a bare slash": (["- if: $CI_COMMIT_TAG =~ /^v/x/"], None),
            "a negated tag": (["- if: '!$CI_COMMIT_TAG'"], None),
            "a grouped tag": (["- if: ($CI_COMMIT_TAG)"], None),
            "a rule with no if beside a tag rule": (["- if: $CI_COMMIT_TAG", "- when: always"], None),
            "a rule of another kind": (["- if: $CI_PIPELINE_SOURCE == 'merge_request_event'"], None),
        }
        for name, (rules, want) in cases.items():
            with self.subTest(name):
                job = ["deploy:", "  rules:", *(f"    {r}" for r in rules)]
                self.assertEqual(evidence.gitlab_refs(job, ["main"]), want)

    def test_a_job_that_extends_a_template_has_rules_this_cannot_see(self):
        job = ["deploy:", "  extends: .release", "  rules:", "    - if: $CI_COMMIT_TAG"]
        self.assertIsNone(evidence.gitlab_refs(job, ["main"]))

    def test_a_filter_this_does_not_fully_read_leaves_the_job_unread(self):
        """A rule that goes on past its first line, or a key this does not know, must never read as a narrower set."""
        rule = "  rules:\n    - if: $CI_COMMIT_TAG =~ /^v/\n"
        cases = {
            "an if continued with ||": rule + '      || $CI_COMMIT_BRANCH == "main"\n',
            "an if continued with a plain line": rule + '      $CI_COMMIT_BRANCH == "main"\n',
            "an if as a folded block": "  rules:\n    - if: >\n        $CI_COMMIT_TAG ||\n        $CI_COMMIT_BRANCH\n",
            "an if as a literal block": "  rules:\n    - if: |\n        $CI_COMMIT_TAG\n",
            "an if as a stripped block": "  rules:\n    - if: >-\n        $CI_COMMIT_TAG\n",
            "a double-quoted if over two lines": '  rules:\n    - if: "$CI_COMMIT_TAG ||\n        $CI_COMMIT_BRANCH"\n',
            "a single-quoted if over two lines": "  rules:\n    - if: '$CI_COMMIT_TAG ||\n        $CI_COMMIT_BRANCH'\n",
            "an if with a value on the next line": "  rules:\n    - if:\n        $CI_COMMIT_TAG\n",
            "a rule key that is not if": "  rules:\n    - if: $CI_COMMIT_TAG\n      changes: [a]\n",
            "a deeper line under a rule": "  rules:\n    - if: $CI_COMMIT_TAG\n        variables: x\n",
            "an unknown when": "  rules:\n    - if: $CI_COMMIT_TAG\n      when: sometimes\n",
            "when: never": "  rules:\n    - if: $CI_COMMIT_TAG\n      when: never\n",
            "when twice": "  rules:\n    - if: $CI_COMMIT_TAG\n      when: manual\n      when: always\n",
            "a rule list in flow style": "  rules: [{if: $CI_COMMIT_TAG}]\n",
            "a rule that starts with when": "  rules:\n    - when: always\n      if: $CI_COMMIT_TAG\n",
            "a reference in a rule": "  rules:\n    - !reference [.tpl, rules]\n    - if: $CI_COMMIT_TAG\n",
            "a tag on the rules": "  rules: !reference [.tpl, rules]\n",
            "an anchor on the rules": "  rules: &r\n    - if: $CI_COMMIT_TAG\n",
            "an alias for the rules": "  rules: *r\n",
            "a merge key": "  <<: *base\n  rules:\n    - if: $CI_COMMIT_TAG\n",
            "extends": "  extends: .tpl\n" + rule,
            "extends with a quoted key": "  'extends': .tpl\n" + rule,
            "a variable that is not the branch or tag": "  rules:\n    - if: $CI_PIPELINE_SOURCE == 'push'\n",
            "rules beside only": rule + "  only: [main]\n",
            "rules beside except": rule + "  except: [dev]\n",
            "only with a kind of pipeline": "  only: [main, pushes]\n",
            "only with merge requests": "  only:\n    - main\n    - merge_requests\n",
            "only as a block scalar": "  only: |\n    main\n",
            "only over two lines": "  only: [main,\n    dev]\n",
            "only with a quoted name over two lines": "  only: ['main\n    dev']\n",
            "only with an unreadable except": "  only: [main]\n  except:\n    refs: [dev]\n",
            "an except alone": "  except: [dev]\n",
            "a key twice": "  only: [main]\n  only: [dev]\n",
            "a job with a tab": "\trules:\n\t  - if: $CI_COMMIT_TAG\n",
            "a line that is no key": "  - stray\n" + rule,
        }
        for name, body in cases.items():
            with self.subTest(name):
                self.assertIsNone(evidence.gitlab_refs(["deploy:", *body.splitlines()], ["main"]))

    def test_a_filter_that_fits_the_grammar_is_read(self):
        cases = {
            "a when after an if": ("  rules:\n    - if: $CI_COMMIT_TAG\n      when: manual\n", ([], ["*"])),
            "rules at the key's own indent": ("  rules:\n  - if: $CI_COMMIT_BRANCH == 'main'\n", (["main"], [])),
            "a trailing comment": ("  rules:\n    - if: $CI_COMMIT_TAG # releases\n", ([], ["*"])),
            "an only list at the key's indent": ("  only:\n  - main\n  - 'dev'\n", (["main", "dev"], [])),
            "an except beside only": ("  only: [main]\n  except: [dev]\n", (["main"], [])),
            "other job keys": ("  stage: build\n  script:\n    - make\n  only: [main]\n", (["main"], [])),
        }
        for name, (body, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(evidence.gitlab_refs(["deploy:", *body.splitlines()], ["main"]), want)

    def test_only_lists(self):
        self.assertEqual(evidence.gitlab_refs(["deploy:", "  only: [main, staging]"], ["main"]), (["main", "staging"], []))
        self.assertEqual(evidence.gitlab_refs(["deploy:", "  only:", "    - main"], ["main"]), (["main"], []))
        for unread in ("  only: [branches]", "  only:\n    refs:\n      - main", "  only: ['/^release-.*$/']", ""):
            with self.subTest(unread):
                self.assertIsNone(evidence.gitlab_refs(["deploy:", *unread.splitlines()], ["main"]))


class ReadTests(unittest.TestCase):
    """The working tree of a folder: what is found, what is unread, and what covers the default branch."""

    def read(self, files: dict[str, str], default: str = "main") -> evidence.Evidence:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for path, text in files.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(text, encoding="utf-8")
            return delegation.read_deploy_evidence(root, [default])

    def test_what_the_workflows_say_deploys_on_a_push(self):
        cases = {
            "a branch": (
                {".github/workflows/d.yml": workflow(PUSH_MAIN)},
                [("production", ("main",), (), (".github/workflows/d.yml:7",))],
                [],
            ),
            "a tag": (
                {".github/workflows/d.yml": workflow("on:\n  push:\n    tags: ['v*']\n")},
                [("production", (), ("v*",), (".github/workflows/d.yml:7",))],
                [],
            ),
            "no environment key: the file's name": (
                {".github/workflows/ship-it.yaml": workflow(PUSH_MAIN, "    steps:\n      - run: fly deploy\n")},
                [("ship-it", ("main",), (), (".github/workflows/ship-it.yaml:8",))],
                [],
            ),
            "two workflows, one environment": (
                {".github/workflows/a.yml": workflow(PUSH_MAIN), ".github/workflows/b.yml": workflow("on:\n  push:\n    tags: ['v*']\n")},
                [("production", ("main",), ("v*",), (".github/workflows/a.yml:7", ".github/workflows/b.yml:7"))],
                [],
            ),
            "a workflow that deploys on every push": ({".github/workflows/d.yml": workflow("on: push\n")}, [], [".github/workflows/d.yml:5"]),
            "a workflow that tests": ({".github/workflows/t.yml": workflow(PUSH_MAIN, "    steps:\n      - run: pytest\n")}, [], []),
            "a deploy on pull requests only": ({".github/workflows/d.yml": workflow("on:\n  pull_request:\n")}, [], [".github/workflows/d.yml:6"]),
            "a deploy on a closed pull request": (
                {".github/workflows/d.yml": workflow("on:\n  pull_request:\n    types: [closed]\n")},
                [],
                [".github/workflows/d.yml:7"],
            ),
            "a deploy from the merge queue": ({".github/workflows/d.yml": workflow("on:\n  merge_group:\n")}, [], [".github/workflows/d.yml:6"]),
            "a deploy on a review only": ({".github/workflows/d.yml": workflow("on:\n  issues:\n")}, [], []),
            "a GitLab job": (
                {".gitlab-ci.yml": "deploy:\n  environment: production\n  rules:\n    - if: $CI_COMMIT_BRANCH == $CI_DEFAULT_BRANCH\n"},
                [("production", ("main",), (), (".gitlab-ci.yml:2",))],
                [],
            ),
            "a GitLab job that runs on every push": ({".gitlab-ci.yml": "deploy:\n  environment: production\n  script: x\n"}, [], [".gitlab-ci.yml:2"]),
            "a GitLab job with no environment": ({".gitlab-ci.yml": "build:\n  script: make\n"}, [], []),
            "a GitLab pages job": ({".gitlab-ci.yml": "pages:\n  script: [make site]\n"}, [], [".gitlab-ci.yml:1"]),
            "a GitLab deploy stage with no environment": ({".gitlab-ci.yml": "ship:\n  stage: deploy\n  script: [x]\n"}, [], [".gitlab-ci.yml:1"]),
            "a GitLab script that deploys by its words": ({".gitlab-ci.yml": "ship:\n  script:\n    - npm run deploy\n"}, [], [".gitlab-ci.yml:1"]),
            "a GitLab job on tags by a pattern": (
                {".gitlab-ci.yml": "deploy:\n  environment: production\n  rules:\n    - if: $CI_COMMIT_TAG =~ /^v/\n"},
                [("production", (), ("*",), (".gitlab-ci.yml:2",))],
                [],
            ),
            "nothing": ({"README.md": "hi\n"}, [], []),
        }
        cases |= self.gitlab_files_this_cannot_read()
        for name, (files, found, unread) in cases.items():
            with self.subTest(name):
                got = self.read(files)
                self.assertEqual([(f.name, f.branches, f.tags, f.where) for f in got.environments], found)
                self.assertEqual(list(got.unread), unread)

    @staticmethod
    def gitlab_files_this_cannot_read() -> dict:
        """A file that brings jobs or rules from elsewhere reads as unread for each job that deploys, never as narrower."""
        job = 'deploy:\n  environment: production\n  rules:\n    - if: $CI_COMMIT_BRANCH == "dev"\n'
        cases = {
            "an include": ("include: other.yml\n" + job, 3),
            "an include list": ("include:\n  - local: other.yml\n" + job, 4),
            "a workflow with rules": ('workflow:\n  rules:\n    - if: $CI_COMMIT_BRANCH == "dev"\n' + job, 5),
            "an anchor": (".t: &t\n  script: x\n" + job, 4),
            "an alias": (job.replace("rules:", "rules: *r"), 2),
            "a merge key": (".t:\n  script: x\n" + job.replace("  rules:", "  <<: *t\n  rules:"), 4),
            "a reference": ("deploy:\n  environment: production\n  script: !reference [.t, script]\n", 2),
            "an indented file": ("  deploy:\n    environment: production\n    script: x\n", 2),
            "an indented file after a document marker": ("---\n  deploy:\n    environment: production\n", 3),
            "a top-level variable override": ("variables:\n  CI_DEFAULT_BRANCH: dev\n" + job, 4),
            "a job variable override": (job.replace("  rules:", "  variables:\n    CI_COMMIT_BRANCH: main\n  rules:"), 2),
            "a quoted variable override in a flow map": ('variables: {"CI_COMMIT_TAG": x}\n' + job, 3),
            "a job that triggers a pipeline": ("deploy:\n  trigger:\n    include: other.yml\n", 1),
            "a job that triggers a project": ("build:\n  script: make\ndeploy:\n  environment: production\n  trigger: group/project\n", 3),
            "a default that deploys": ("default:\n  before_script:\n    - npm run deploy\nbuild:\n  script: make\n", 4),
            "a top-level before_script that deploys": ("before_script:\n  - make deploy\nbuild:\n  script: make\n", 3),
            "an image line that deploys": ("image: ./deploy.sh\nbuild:\n  script: make\n", 2),
            "a job in a flow map": ("{deploy: {environment: production, only: [dev]}}\n", 1),
            "a job with its map on its own line": ("deploy: {environment: production, only: [dev]}\n", 1),
        }
        return {f"GitLab, {name}": ({".gitlab-ci.yml": text}, [], [f".gitlab-ci.yml:{line}"]) for name, (text, line) in cases.items()} | {
            "GitLab, a job that extends a template with an environment": (
                {".gitlab-ci.yml": ".tpl:\n  environment: production\nship:\n  extends: .tpl\n  script: x\n"},
                [],
                [".gitlab-ci.yml:3"],
            ),
            "GitLab, a quoted job name beside a plain one": (
                {".gitlab-ci.yml": '"deploy":\n  environment: production\nship:\n  environment: staging\n'},
                [],
                [".gitlab-ci.yml:2", ".gitlab-ci.yml:4"],
            ),
            "GitLab, a job that extends a template that deploys nothing": ({".gitlab-ci.yml": ".tpl:\n  script: x\nship:\n  extends: .tpl\n"}, [], []),
        }

    def test_covers_asks_for_every_name_the_default_branch_can_have(self):
        got = self.read({".github/workflows/d.yml": workflow(PUSH_MAIN)})
        self.assertTrue(got.covers(["main"]))
        self.assertFalse(got.covers(["main", "master"]))
        self.assertTrue(got.covers(["main", "master"], every=False))
        self.assertFalse(got.covers([]))
        tags = self.read({".github/workflows/d.yml": workflow("on:\n  push:\n    tags: ['v*']\n")})
        self.assertFalse(tags.covers(["main"]), "a tag does not name the default branch")

    def test_the_workflows_that_deploy_on_a_push_to_a_branch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".github/workflows").mkdir(parents=True)
            (root / ".github/workflows/d.yml").write_text(workflow(PUSH_MAIN), encoding="utf-8")
            (root / ".github/workflows/e.yml").write_text(workflow("on:\n  push:\n    branches: [staging]\n"), encoding="utf-8")
            rs = risk.rule_set(None)
            self.assertEqual(delegation.workflows_deploying_on(root, "main", rs), [".github/workflows/d.yml:7"])
            self.assertEqual(delegation.workflows_deploying_on(root, "staging", rs), [".github/workflows/e.yml:7"])
            self.assertEqual(delegation.workflows_deploying_on(root / "nowhere", "main", rs), [])


if __name__ == "__main__":
    unittest.main()
