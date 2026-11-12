"""`aidd validate` warns when a filled project guide (AGENTS.md) names a command or a path the repository no longer has, and says
nothing when it cannot tell. The invariant: a warning names something that is missing for certain, so honest work never gets
one. A tool on the PATH, a shell builtin, a glob, a placeholder, an example, a build output git ignores, a URL, and aidd's own
sections are never named; a repository with no Makefile or no package.json says nothing about `make` or a script."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd.workitems import guide_checks

PATH, COMMAND = guide_checks.PATH_MISSING, guide_checks.COMMAND_MISSING
MAKEFILE = "test:\n\tpytest\n\nlint build: deps\n\truff check .\n\n.PHONY: test lint\n"
PACKAGE = '{"scripts": {"build": "tsc", "test": "vitest"}}'
TREE = {"src/app.py": "", "docs/architecture/README.md": "", "scripts/dev.sh": "", "gradlew": ""}

# (name, guide text, the files that exist beside it, the codes expected in order)
CASES = [
    ("a path that exists", "Code is in `src/app.py`.", {}, []),
    ("a path that moved", "Code is in `src/old/mod.py`.", {}, [PATH]),
    ("a folder that exists", "Docs are in `docs/`.", {}, []),
    ("a path with a line number", "See `src/app.py:42:7`.", {}, []),
    ("a glob", "Tests match `src/**/*.py`.", {}, []),
    ("a placeholder", "Put it in `src/<name>/mod.py`.", {}, []),
    ("a path that starts nowhere the repository is", "Never edit `dist/bundle.js`.", {}, []),
    ("a path under a folder that is there, which git ignores", "Never edit `src/generated/`.", {".gitignore": "src/generated/\n"}, []),
    ("a path under a folder that is there, which nothing ignores", "Never edit `src/generated/`.", {}, [PATH]),
    ("a MIME type", "Send `application/json`.", {}, []),
    ("a URL in a span", "See `https://example.com/src/app.py`.", {}, []),
    ("an absolute path", "Reads `/etc/hosts`.", {}, []),
    ("an owner and a repository", "Clone `acme/widgets`.", {}, []),
    ("a path in a comment", "<!-- see `src/old/mod.py` -->\nDone.", {}, []),
    ("a path in aidd's section", "<!-- aidd -->\n## Change control\n\nSee `src/old/mod.py`.\n<!-- /aidd -->", {}, []),
    ("a path in aidd's team section", "<!-- aidd-team -->\n## Team\n\nSee `src/old/team.py`.\n<!-- /aidd-team -->", {}, []),
    ("a path after aidd's section", "<!-- aidd -->\n## A\n\nx\n<!-- /aidd -->\n\nSee `src/old/mod.py`.", {}, [PATH]),
    ("a link that leads somewhere", "See [the design](docs/architecture/README.md#module-map).", {}, []),
    ("a link that leads nowhere", "See [the design](docs/gone.md).", {}, [PATH]),
    ("a link to a URL, an anchor, and a mail address", "[a](https://x.dev/a) [b](#top) [c](mailto:a@b.dev) [d](/abs/path)", {}, []),
    ("make with the target", "Run `make test`.", {"Makefile": MAKEFILE}, []),
    ("make with a target in a rule that has two names", "Run `make build`, then `make lint`.", {"Makefile": MAKEFILE}, []),
    ("make with a target no Makefile has", "Run `make deploy`.", {"Makefile": MAKEFILE}, [COMMAND]),
    ("make with no Makefile", "Run `make deploy`.", {}, []),
    ("make with an include it cannot read", "Run `make deploy`.", {"Makefile": "include rules.mk\ntest:\n\ttrue\n"}, []),
    ("make with a target built from a variable", "Run `make deploy`.", {"Makefile": "$(NAME):\n\ttrue\n"}, []),
    ("make with no target", "Run `make`.", {"Makefile": MAKEFILE}, []),
    ("make with an option and its value", "Run `make -C web -j 4 test`.", {"Makefile": MAKEFILE}, []),
    ("make with a variable", "Run `make test CI=1`.", {"Makefile": MAKEFILE}, []),
    ("a script that exists", "Run `npm run build`.", {"package.json": PACKAGE}, []),
    ("a script that is missing", "Run `npm run deploy`.", {"package.json": PACKAGE}, [COMMAND]),
    ("npm test with the script", "Run `npm test`.", {"package.json": PACKAGE}, []),
    ("npm test without it", "Run `npm test`.", {"package.json": '{"scripts": {}}'}, [COMMAND]),
    ("pnpm with a filter", "Run `pnpm --filter web run build`.", {"package.json": PACKAGE}, []),
    ("yarn run a missing script", "Run `yarn run deploy`.", {"package.json": PACKAGE}, [COMMAND]),
    ("bun test is bun's own runner", "Run `bun test`.", {"package.json": '{"scripts": {}}'}, []),
    ("npm with no package.json", "Run `npm run build`.", {}, []),
    ("npm with a package.json that does not parse", "Run `npm run build`.", {"package.json": "{"}, []),
    ("a script in a package below the top", "Run `npm run build`.", {"web/package.json": PACKAGE}, []),
    ("a tool on the PATH", "Run `git status`, `pytest -q`, `ruff check .`, `python3 -m unittest`, and `aidd test`.", {}, []),
    ("a shell builtin", "Run `cd web`, then `source .venv/bin/activate`, then `export A=1`.", {}, []),
    ("a program given by a path that exists", "Run `./scripts/dev.sh --watch`.", {}, []),
    ("a program given by a path that is missing", "Run `./scripts/serve.sh`.", {}, [PATH]),
    ("a wrapper at the top that exists", "Run `./gradlew test`.", {}, []),
    ("a wrapper at the top that is missing", "Run `./mvnw test`.", {}, [PATH]),
    ("a build output git ignores", "Run `./target/release/app`.", {".gitignore": "target/\n"}, []),
    ("a command after cd", "Run `cd web && npm run deploy`.", {"package.json": PACKAGE}, [COMMAND]),
    ("a command after an environment variable", "Run `CI=1 npm test`.", {"package.json": '{"scripts": {}}'}, [COMMAND]),
    ("a command with a quote that never closes", 'Run `echo "oops`.', {}, []),
    ("a code block", "```sh\n$ make deploy\nnpm run build\n# make nothing\n```", {"Makefile": MAKEFILE, "package.json": PACKAGE}, [COMMAND]),
    ("a path in a code block is not a claim", "```\nsrc/old/mod.py\n```", {}, [PATH]),
    ("a line still waiting to be written", "TODO: the layout, such as `docs/architecture/README.md` and `make deploy`.", {"Makefile": MAKEFILE}, []),
    ("nothing to name", "A short guide with no code.", {}, []),
]


def build(root: Path, files: dict[str, str]) -> None:
    git(root, "init", "-q")
    for rel, text in {**TREE, **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


class WhatTheGuideNames(unittest.TestCase):
    def test_a_warning_names_something_missing_and_honest_work_gets_none(self):
        for name, guide, files, codes in CASES:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                build(root, {"AGENTS.md": guide, **files})
                found = guide_checks.guide_findings(root)
                self.assertEqual([code for code, _ in found], codes, found)
                for _, message in found:
                    self.assertRegex(message, r"^warning: AGENTS\.md:\d+: .+; fix it, or delete the line$")

    def test_a_finding_names_its_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, {"AGENTS.md": "# Guide\n\nok `src/app.py`\n<!-- a\ncomment -->\n\n- bad `src/old/mod.py`\n"})
            ((_, message),) = guide_checks.guide_findings(root)
            self.assertIn("AGENTS.md:7:", message)

    def test_a_nested_guide_resolves_from_its_own_folder_and_the_top_guide_does_not_see_into_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(
                root,
                {
                    "AGENTS.md": "See `docs/architecture/README.md`.",
                    "packages/api/AGENTS.md": "Run `make test`. Code is in `src/handlers.py` and `docs/architecture/README.md`.\n",
                    "packages/api/Makefile": MAKEFILE,
                    "packages/api/src/handlers.py": "",
                },
            )
            git(root, "add", "-A")
            found = guide_checks.guide_findings(root)
            self.assertEqual([m.split(":")[1] for _, m in found], [], found)
            (root / "packages/api/AGENTS.md").write_text("Code is in `src/gone.py`.\n", encoding="utf-8")
            self.assertEqual([m.split(": ")[1] for _, m in guide_checks.guide_findings(root)], ["packages/api/AGENTS.md:1"])

    def test_a_repository_with_no_guide_says_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root, {})
            self.assertEqual(guide_checks.guide_findings(root), [])

    def test_a_folder_that_is_no_repository_names_no_path_it_cannot_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "AGENTS.md").write_text("Never edit `src/generated/`, and run `make test`.", encoding="utf-8")
            self.assertEqual(guide_checks.guide_findings(root), [], "without git it cannot tell a build output from a moved path")

    def test_validate_prints_them_as_warnings_and_they_never_fail_it(self):
        from aidd.workitems import validation

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(
                root,
                {
                    "AGENTS.md": "Run `make deploy`. Code is in `src/old/mod.py`.",
                    "Makefile": MAKEFILE,
                    ".aidd/config.yaml": 'aidd_version: "1.0.0"\nprofile: solo\n',
                },
            )
            errors, warnings = validation.check_repo(root)
            self.assertEqual(errors, [])
            self.assertEqual(sum("AGENTS.md:1:" in w for w in warnings), 2, warnings)


if __name__ == "__main__":
    unittest.main()
