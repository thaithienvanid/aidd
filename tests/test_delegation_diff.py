"""`aidd delegate check` on what a change touches: the CI paths, dependency files, and test-run scripts it defers on, a deploy
workflow at the tip, and a test file renamed away. Split from test_delegation_deploys to keep each file inside the test budget."""

import tempfile
import unittest
from pathlib import Path

from helpers import git
from test_delegation_check import Case, Repo, codes, config_text

from aidd import risk
from aidd.delegation import diff_signals, workflow_triggers


class DiffTests(Case):
    def test_check_defers_a_ci_path_a_dependency_or_a_test_script_change(self):
        for path in (".github/workflows/release.yml", "package.json", "Makefile", "conftest.py", ".aidd/config.yaml", "vercel.json"):
            with self.subTest(path), tempfile.TemporaryDirectory() as d:
                repo = Repo(Path(d).resolve())
                text = config_text(extra="  reserved: []\n") if path == ".aidd/config.yaml" else "x = 1\n"
                result = repo.check(repo.change(path, text))
                self.assertIn("reserved_path", codes(result))
                self.assertTrue(result["reserved"])

    def test_check_defers_a_file_that_steers_a_test_run(self):
        steering = (
            "sitecustomize.py",
            "usercustomize.py",
            "pytest_plugins.py",
            "conftest.py",
            "tests/__init__.py",
            "pkg/tests/__init__.py",
            ".jest/setup.js",
            "web/.jest/env.js",
            "jest.config.ts",
            "vitest.config.mts",
            "web/vitest.config.js",
        )
        for path in steering:
            with self.subTest(path), tempfile.TemporaryDirectory() as d:
                repo = Repo(Path(d).resolve())
                result = repo.check(repo.change(path, "x = 1\n"))
                self.assertIn("reserved_path", codes(result))
                self.assertTrue(result["reserved"])

    def test_a_test_renamed_away_on_the_fast_lane_lost_its_lines(self):
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        body = "".join(f"def test_{i}():\n    assert {i} == {i}\n" for i in range(12))
        repo.write("tests/test_cart.py", body)
        repo.commit("a test")
        git(self.root, "checkout", "-q", "-B", "feature")
        git(self.root, "mv", "tests/test_cart.py", "tests/test_basket.py")
        repo.write("tests/test_basket.py", body.replace("assert 11 == 11", "pass"))
        head = repo.change()
        self.assertIn("tests/test_cart.py", diff_signals.changed_test_files("main", head, str(self.root)))
        self.assertIn("tests_changed", codes(repo.check(head)))

    def test_check_defers_a_deploy_workflow_at_the_tip(self):
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        repo.write(
            ".github/workflows/deploy.yml",
            "name: deploy\non:\n  push:\n    branches: [main]\njobs:\n  ship:\n    environment: production\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ship\n",
        )
        repo.commit("deploy on push")
        git(self.root, "checkout", "-q", "-B", "feature")
        head = repo.change()
        self.assertEqual(codes(repo.check(head)), ["merge_deploys"])

    def test_a_deploy_on_a_closed_pull_request_is_a_deploy_on_a_merge(self):
        repo = self.repo()
        git(self.root, "checkout", "-q", "main")
        repo.write(
            ".github/workflows/deploy.yml",
            "name: deploy\non:\n  pull_request:\n    types: [closed]\njobs:\n  ship:\n    environment: production\n    steps:\n      - run: echo ship\n",
        )
        repo.commit("deploy when a pull request closes")
        git(self.root, "checkout", "-q", "-B", "feature")
        head = repo.change()
        self.assertEqual(codes(repo.check(head)), ["merge_deploys"])

    def test_a_deploy_is_found_however_the_step_is_written(self):
        """R528 review: a quoted key, any block scalar header, and a job or step in a flow map are the same deploy as the plain one."""
        rs = risk.rule_set(None)
        steps = "on: push\njobs:\n  a:\n    steps:\n"
        cases = {
            "a quoted environment key": ('on: push\njobs:\n  a:\n    "environment": prod\n', 4),
            "a single-quoted environment key": ("on: push\njobs:\n  a:\n    'environment': prod\n", 4),
            "a single-quoted uses key": (steps + "      - 'uses': peaceiris/actions-gh-pages@v4\n", 5),
            "a double-quoted run key": (steps + '      - "run": terraform apply -auto-approve\n', 5),
            "a keep block": (steps + "      - run: |+\n          terraform apply -auto-approve\n", 5),
            "a strip block": (steps + "      - run: |-\n          terraform apply -auto-approve\n", 5),
            "an indent block": (steps + "      - run: |2\n          terraform apply -auto-approve\n", 5),
            "a folded keep block": (steps + "      - run: >+\n          terraform apply -auto-approve\n", 5),
            "a job in a flow map": ("on: push\njobs:\n  a: {environment: prod, steps: []}\n", 3),
            "a step in a flow map": (steps + "      - {uses: peaceiris/actions-gh-pages@v4}\n", 5),
            "a run step in a flow map": (steps + "      - {name: x, run: terraform apply -auto-approve}\n", 5),
            "a quoted key in a flow map": ("on: push\njobs:\n  a: {'environment': prod}\n", 3),
            "a step that only tests": (steps + "      - run: |+\n          pytest\n", None),
            "a step that only tests, in a flow map": (steps + "      - {run: pytest}\n", None),
            "an escaped quoted key": ('on: push\njobs:\n  a:\n    "envi\\x72onment": prod\n', 4),
            "an escaped quoted key in a flow map": ('on: push\njobs:\n  a: {"envi\\x72onment": prod}\n', 3),
            "a plain run value that goes on below": (steps + "      - run: echo hi &&\n          ./ship\n", 5),
            "a quoted run value that never closes": (steps + '      - run: "echo hi\n          ./ship"\n', 5),
            "a quoted test run that closes": (steps + '      - run: "pytest -q"\n', None),
            "a plain test run with a step after it": (steps + "      - run: pytest\n      - run: ruff check\n", None),
            "a continued value whose next line looks like a key": (steps + "      - run: echo a\n          ./ship:now\n", 5),
            "a double quote closed only by an escape": (steps + '      - run: "echo \\"\n          ./ship"\n', 5),
            "a flow map that goes on below": (steps + "      - {run: echo,\n          x: 1}\n", 5),
            "a test run with an env key beside it": (steps + "      - run: pytest\n        env:\n          X: 1\n", None),
            "a closed quote with escapes in it": (steps + '      - run: "echo \\"hi\\""\n', None),
            "a doubled single quote": (steps + "      - run: 'it''s fine'\n", None),
            "a brace inside a quoted flow value": (steps + '      - {run: "echo }", x: 1,\n          y: 2}\n', 5),
            "a quoted flow value": (steps + '      - {run: "pytest -q"}\n', 5),
            "a nested flow map": ("on: push\njobs:\n  a: {steps: [{run: pytest}]}\n", 3),
        }
        for name, (text, line) in cases.items():
            with self.subTest(name):
                self.assertEqual(diff_signals.deploy_line(text, rs), line)

    def test_a_workflow_deploys_on_a_push_only_where_its_filter_reaches(self):
        rs = risk.rule_set(None)
        cases = {
            "on: push\njobs:\n  a:\n    steps:\n      - run: vercel deploy --prod\n": ("main", True),
            "on:\n  push:\n    branches: [release/*]\njobs:\n  a:\n    environment: prod\n": ("main", False),
            "on:\n  push:\n    branches-ignore: [main]\njobs:\n  a:\n    environment: prod\n": ("main", True),
            "on:\n  push:\n    tags: ['v*']\njobs:\n  a:\n    environment: prod\n": ("main", False),
            "on:\n  pull_request:\njobs:\n  a:\n    environment: prod\n": ("main", True),
            "on:\n  pull_request_review:\njobs:\n  a:\n    environment: prod\n": ("main", False),
            "on: [push]\njobs:\n  a:\n    steps:\n      - uses: peaceiris/actions-gh-pages@v4\n": ("main", True),
            "on: [push]\njobs:\n  a:\n    steps:\n      - run: pytest\n": ("main", False),
            # A list at its key's own indent is a list, as YAML reads it: the dash lines belong to `branches:`.
            "on:\n  push:\n    branches:\n    - main\njobs:\n  a:\n    environment: prod\n": ("main", True),
            "on:\n  push:\n    branches:\n    - release\njobs:\n  a:\n    environment: prod\n": ("main", False),
            "on:\n  push:\n    tags:\n    - 'v*'\n    branches:\n    - main\njobs:\n  a:\n    environment: prod\n": ("main", True),
        }
        for text, (branch, deploys) in cases.items():
            with self.subTest(text):
                self.assertEqual(workflow_triggers.push_reaches(text, branch) and diff_signals.deploy_line(text, rs) is not None, deploys)


if __name__ == "__main__":
    unittest.main()
