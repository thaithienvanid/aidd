"""One table over the shapes a workflow's `on:` can take: the delegate check, `aidd doctor`, and `aidd init` read it
through one reader, so each shape gets one answer from all three. A shape the reader cannot read counts as running on every
branch and tag (unread). It never reads as "does not deploy"."""

import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import delegation, risk
from aidd.delegation import diff_signals, workflow_triggers

JOB = "jobs:\n  ship:\n    environment: {name}\n    steps:\n      - run: echo ship\n"
READ_MAIN = (("main",), ())
UNREAD = "unread"
NOTHING = "nothing"

# name: (the `on:` part, whether a push to main runs the workflow, what init makes of it: the (branches, tags) of the environment it
# reads, unread, or nothing)
SHAPES = {
    "on: push": ("on: push\n", True, UNREAD),
    "on: [push]": ("on: [push]\n", True, UNREAD),
    "a list under on": ("on:\n- push\n", True, UNREAD),
    "a list under on, indented": ("on:\n  - push\n  - pull_request\n", True, UNREAD),
    "a branch list": ("on:\n  push:\n    branches: [main]\n", True, READ_MAIN),
    "another branch": ("on:\n  push:\n    branches: [develop]\n", False, (("develop",), ())),
    "branches-ignore": ("on:\n  push:\n    branches-ignore: [develop]\n", True, UNREAD),
    "tags alone": ("on:\n  push:\n    tags: ['v*']\n", False, ((), ("v*",))),
    "workflow_run beside a branch": ("on:\n  workflow_run:\n    workflows: [test]\n  push:\n    branches: [develop]\n", True, UNREAD),
    "a schedule beside a branch": ("on:\n  schedule:\n    - cron: '0 0 * * *'\n  push:\n    branches: [develop]\n", True, UNREAD),
    "only a review": ("on:\n  pull_request_review:\n    types: [submitted]\n", False, NOTHING),
    # A pull request or the merge queue can deploy: on a merge (`closed`), or a push to the pull request's branch.
    "a pull request": ("on:\n  pull_request:\n    branches: [main]\n", True, UNREAD),
    "a pull request closed": ("on:\n  pull_request:\n    types: [closed]\n", True, UNREAD),
    "a pull request with no types": ("on: pull_request\n", True, UNREAD),
    "a pull request target": ("on:\n  pull_request_target:\n    types: [closed]\n", True, UNREAD),
    "a merge group": ("on:\n  merge_group:\n  push:\n    branches: [develop]\n", True, UNREAD),
    # GitHub's filter is not aidd's glob: `?`, `+`, `[...]`, and `\\` mean more there, so a pattern with one reaches every ref.
    "a branch class": ("on:\n  push:\n    branches: ['[m]ain']\n", True, UNREAD),
    "a branch with a question mark": ("on:\n  push:\n    branches: ['mainn?']\n", True, UNREAD),
    "a branch with a plus": ("on:\n  push:\n    branches: ['ma+in']\n", True, UNREAD),
    "a branch with a backslash": ("on:\n  push:\n    branches: ['ma\\in']\n", True, UNREAD),
    "a tag with a plus": ("on:\n  push:\n    tags: ['v[0-9]+']\n", True, UNREAD),
    "a quoted value": ("on:\n  push:\n    branches: ['main']\n", True, READ_MAIN),
    "a double-quoted value": ('on:\n  push:\n    branches:\n      - "main"\n', True, READ_MAIN),
    # The shapes that read wrongly line by line (the review's finding 1).
    "a comment line at column 0 in on": ("on:\n# note\n  push:\n    branches: [develop]\n", False, (("develop",), ())),
    "a comment line before the push": ("on:\n  # note\n  push:\n    branches: [main]\n", True, READ_MAIN),
    "a comment line in a list": ("on:\n  push:\n    branches:\n      # the default\n      - main\n", True, READ_MAIN),
    "a comment line at column 0 in a list": ("on:\n  push:\n    branches:\n# the default\n      - develop\n", False, (("develop",), ())),
    "a trailing comment on an item": ("on:\n  push:\n    branches:\n      - main # production\n", True, READ_MAIN),
    "a trailing comment on a list": ("on:\n  push:\n    branches: [main] # production\n", True, READ_MAIN),
    "a comment holding a quote": ("on:\n  push:\n    branches:\n      - main # it's the 'default'\n", True, READ_MAIN),
    "a quoted key": ('on:\n  "push":\n    "branches": [main]\n', True, READ_MAIN),
    "a quoted on": ('"on":\n  push:\n    branches: [main]\n', True, READ_MAIN),
    "a flow map on its own line": ("on:\n  {push: {branches: [main]}}\n", True, READ_MAIN),
    "a flow map over lines": ("on: {\n  push: {\n    branches: [main]\n  }\n}\n", True, READ_MAIN),
    "a flow map on one line": ("on: {push: {branches: [develop]}}\n", False, (("develop",), ())),
    "a flow list on the next line": ("on:\n  push:\n    branches:\n      [main]\n", True, READ_MAIN),
    "a flow list over lines": ("on:\n  push:\n    branches: [develop,\n      main]\n", True, (("develop", "main"), ())),
    "a list that never closes": ("on:\n  push:\n    branches: [develop\n", True, UNREAD),
    "a key with nothing under it": ("on:\n  push:\n    branches:\n  pull_request:\n", True, UNREAD),
    "a key with lines that are no items": ("on:\n  push:\n    branches:\n      main: yes\n", True, UNREAD),
    "an empty list": ("on:\n  push:\n    branches: []\n", True, UNREAD),
    "a negated glob": ("on:\n  push:\n    branches: [develop, '!main']\n", True, UNREAD),
    "an alias": ("on:\n  push: &p\n    branches: [develop]\n", True, UNREAD),
    "a tab": ("on:\n  push:\n\tbranches: [develop]\n", True, UNREAD),
    "a key twice": ("on:\n  push:\n    branches: [develop]\n    branches: [main]\n", True, UNREAD),
    "no on at all": ("", True, UNREAD),
    # A value that goes on past its first line, or is a block scalar, must never read as a narrower list.
    "a block scalar for branches": ("on:\n  push:\n    branches: |\n      develop\n", True, UNREAD),
    "a folded block scalar for branches": ("on:\n  push:\n    branches: >-\n      develop\n", True, UNREAD),
    "a block scalar for a list item": ("on:\n  push:\n    branches:\n      - |\n        develop\n", True, UNREAD),
    "a quoted item over two lines": ('on:\n  push:\n    branches:\n      - "develop\n        main"\n', True, UNREAD),
    "a quoted name over two lines in a flow list": ('on:\n  push:\n    branches: ["develop,\n      main"]\n', True, UNREAD),
    "a plain item that continues": ("on:\n  push:\n    branches:\n      - develop\n        main\n", True, UNREAD),
    "a plain scalar that continues": ("on:\n  push:\n    branches: develop\n      main\n", True, UNREAD),
    "a flow list with text after it on the next line": ("on:\n  push:\n    branches: [develop]\n      main\n", True, UNREAD),
    "a tag on the list": ("on:\n  push:\n    branches: !!seq [develop]\n", True, UNREAD),
    "an alias for the list": ("on:\n  push:\n    branches: *b\n", True, UNREAD),
    # A name that tries to be more than a name.
    "a name with an escape": ('on:\n  push:\n    branches: ["develop\\nmain"]\n', True, UNREAD),
    "a name with a control character": ("on:\n  push:\n    branches: ['dev\x1b[0mn']\n", True, UNREAD),
    "a name that opens a flow map": ("on:\n  push:\n    branches: [develop, {a: main}]\n", True, UNREAD),
    # The whole document, not only `on:` (a second review finding): a part of the file before or around `on:` that makes a reader find a
    # different key, or none. These write `{JOB}` where the jobs go, and the rest is the file.
    "an apostrophe in a plain name before on": ("name: Don't ship\nenv: {A: 1}\non:\n  push:\n    branches: [main]\n{JOB}", True, READ_MAIN),
    "a quote left open before on": ('name: "x\non:\n  push:\n    branches: [develop]\n"\n{JOB}', True, UNREAD),
    "a flow list left open before on": ("name: [x,\non:\n  push:\n    branches: [develop]\n  ]\n{JOB}", True, UNREAD),
    "a flow map on the first line": ("{name: w}\non:\n  push:\n    branches: [develop]\n{JOB}", True, UNREAD),
    "a complex key": ("? name\n: w\non:\n  push:\n    branches: [develop]\n{JOB}", True, UNREAD),
    "an anchor on a key": ("&a name: w\non:\n  push:\n    branches: [develop]\n{JOB}", True, UNREAD),
    "a tag on the first line": ("!!map\nname: w\non:\n  push:\n    branches: [develop]\n{JOB}", True, UNREAD),
    "a merge key": ("<<: *base\non:\n  push:\n    branches: [develop]\n{JOB}", True, UNREAD),
    "a column-0 line that starts with a comma": ("name: [a\n, b]\non:\n  push:\n    branches: [develop]\n{JOB}", True, UNREAD),
    "a column-0 line that starts with a quote": ('name: w\n"o\\x6En":\n  push:\n    branches: [develop]\n{JOB}', True, UNREAD),
    "a plain on and a quoted one": ('on: pull_request\n"on":\n  push:\n    branches: [develop]\n{JOB}', True, UNREAD),
    "an On beside an on": ("On:\n  push:\n    branches: [develop]\non: pull_request\n{JOB}", True, UNREAD),
    "an on at another indent": ("name: w\n  on:\n    push:\n      branches: [develop]\n{JOB}", True, UNREAD),
    "a document that starts indented": ("  name: w\n  on:\n    push:\n      branches: [develop]\n{JOB}", True, UNREAD),
    "a second document": ("on:\n  push:\n    branches: [develop]\n---\nname: x\n{JOB}", True, UNREAD),
    "a form feed in the file": ("on:\n  push:\n    branches: [develop]\x0c\n{JOB}", True, UNREAD),
}


def document(i: int, on: str) -> str:
    """The workflow file for row `i`: `on` with its jobs, or the lines after `name:` when `on` is only the trigger part."""
    job = JOB.format(name=f"env{i:02}")
    return on.replace("{JOB}", job) if "{JOB}" in on else f"name: w{i}\n{on}{job}"


class WorkflowShapeTests(unittest.TestCase):
    """The three readers on every shape: the delegate check (the tip's files), doctor (the working tree), and init's evidence."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        git(cls.root, "init", "-q", "-b", "main")
        git(cls.root, "config", "user.name", "Maya Lee")
        git(cls.root, "config", "user.email", "maya@users.noreply.github.com")
        folder = cls.root / ".github" / "workflows"
        folder.mkdir(parents=True)
        cls.files = {}
        for i, (name, (on, _reaches, _init)) in enumerate(SHAPES.items()):
            cls.files[name] = f".github/workflows/w{i:02}.yml"
            (cls.root / cls.files[name]).write_text(document(i, on), encoding="utf-8")
        git(cls.root, "add", "-A")
        git(cls.root, "commit", "-q", "-m", "workflows")
        rs = risk.rule_set(None)
        cls.check = " ".join(diff_signals.deploying_workflows(rs, "HEAD", "main", str(cls.root)))
        cls.doctor = " ".join(delegation.workflows_deploying_on(cls.root, "main", rs))
        cls.init = delegation.read_deploy_evidence(cls.root, ["main"], rs)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_delegate_check_and_doctor_say_whether_a_push_to_main_runs_it(self):
        for name, (_on, reaches, _init) in SHAPES.items():
            with self.subTest(name):
                self.assertEqual(self.files[name] + ":" in self.check, reaches, f"the delegate check: {self.check}")
                self.assertEqual(self.files[name] + ":" in self.doctor, reaches, f"doctor: {self.doctor}")

    def test_init_reads_an_environment_or_counts_the_workflow_unread_and_never_drops_it(self):
        for name, (_on, _reaches, want) in SHAPES.items():
            with self.subTest(name):
                path = self.files[name]
                read = [e for e in self.init.environments if any(w.startswith(path + ":") for w in e.where)]
                unread = [w for w in self.init.unread if w.startswith(path + ":")]
                if want == UNREAD:
                    self.assertEqual((read, len(unread)), ([], 1))
                elif want == NOTHING:
                    self.assertEqual((read, unread), ([], []))
                else:
                    self.assertEqual(([(e.branches, e.tags) for e in read], unread), ([want], []))

    def test_what_init_calls_unread_the_other_two_count_as_reaching_every_branch(self):
        for name, (_on, _reaches, want) in SHAPES.items():
            if want == UNREAD:
                with self.subTest(name):
                    for branch in ("main", "develop", "any-branch"):
                        self.assertTrue(workflow_triggers.push_reaches(f"name: x\n{SHAPES[name][0]}{JOB.format(name='env')}", branch))


class LinkedWorkflowTests(unittest.TestCase):
    def test_a_workflow_that_is_a_link_in_the_tip_may_deploy(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.name", "Maya Lee")
            git(root, "config", "user.email", "maya@users.noreply.github.com")
            (root / ".github/workflows").mkdir(parents=True)
            (root / "elsewhere.yml").write_text("name: x\non: pull_request\n", encoding="utf-8")
            (root / ".github/workflows/linked.yml").symlink_to("../../elsewhere.yml")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "link")
            self.assertEqual(diff_signals.deploying_workflows(risk.rule_set(None), "HEAD", "main", str(root)), [".github/workflows/linked.yml (unreadable)"])


if __name__ == "__main__":
    unittest.main()
