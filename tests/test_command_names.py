"""A command aidd prints holds no text a shell would expand. The invariant: no command aidd suggests carries text from a file
name or a file (a path, a Spec's id, the config's Specs folder) unless it is a plain name, quoted, and a path comes after `--`;
any other name is described in words, and no command holds it. `kernel.command_names` is the one rule, and each place below
that prints a command with such a name uses it. A hostile repository may name a file `a$(touch X)`, so a person or an agent
who pastes the line would run the substitution."""

from __future__ import annotations

import contextlib
import json
import re
import shlex
import tempfile
import unittest
from pathlib import Path

from helpers import git, make_repo, run_cli

from aidd.kernel import command_names

NAMES = {
    "a plain name": "docs",
    "a command substitution": "a$(touch PWNED)",
    "backticks": "a`touch PWNED`",
    "a semicolon": "a;touch PWNED",
    "a space": "a b",
    "a line break": "a\nb",
    "a quote": "a'b",
    "a leading dash": "-x",
}
PLAIN = ("docs", "SPEC-12", "src/a_b.py", "v1.2/x-y")


def commands(text: str) -> list[list[str]]:
    """Each command a text suggests, as a shell splits it: the words in a backtick span that starts with `aidd` or `git`."""
    return [shlex.split(span) for span in re.findall(r"`([^`\n]+)`", text) if span.split()[0] in ("aidd", "git")]


class TheRule(unittest.TestCase):
    def test_a_plain_name_is_quoted_and_any_other_gets_no_command(self):
        for label, name in NAMES.items():
            with self.subTest(name=label):
                word = command_names.quoted(name)
                if name == "docs":
                    self.assertEqual(word, name)
                else:
                    self.assertIsNone(word)
        for name in PLAIN:
            with self.subTest(name=name):
                self.assertEqual(shlex.split(command_names.quoted(name) or ""), [name])
        self.assertIsNone(command_names.quoted(""), "no name is no command word")


def arrives_after_a_double_dash(case: unittest.TestCase, text: str, program: str, path: str, name: str) -> None:
    """Every `program` command in `text` holds `path` as one word after `--`, or the text has no such command and no part of
    the hostile name appears inside a backtick span."""
    spans = [c for c in commands(text) if c[0] == program]
    for words in spans:
        case.assertEqual(words[-2:], ["--", path], f"the path is one word after `--` in {words}")
    if command_names.quoted(path) is None:
        case.assertEqual(spans, [], "no command holds a name outside the plain set")
    for words in commands(text):
        case.assertNotIn("touch", " ".join(words), "no part of the hostile name is inside a command")


@contextlib.contextmanager
def in_folder(root: Path):
    with contextlib.chdir(root):
        yield


class InitDryRun(unittest.TestCase):
    def test_a_tracked_env_file_gets_its_command_by_the_rule(self):
        for label, name in NAMES.items():
            with self.subTest(name=label), tempfile.TemporaryDirectory() as d:
                root = Path(d).resolve()
                git(root, "init", "-q", "-b", "main")
                (root / name).mkdir()
                (root / name / ".env").write_text("A=1\n", encoding="utf-8")
                git(root, "add", "-A")
                git(root, "commit", "-qm", "e")
                with in_folder(root):
                    code, out = run_cli("init", "--dry-run", "--harness", "claude-code", "--ci", "none")
                self.assertEqual(code, 0, out)
                [line] = [x for x in out.splitlines() if "is tracked by git" in x]
                shown = re.sub(r"\s", " ", f"{name}/.env")
                arrives_after_a_double_dash(self, line, "git", shown, name)
                self.assertEqual(len([c for c in commands(line) if c[0] == "git"]), 1 if command_names.quoted(shown) else 0)


class StatusUnreadable(unittest.TestCase):
    def repository(self, d: str, name: str) -> Path:
        root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
        (root / "specs" / name).mkdir(parents=True)
        (root / "specs" / name / "SPEC-9.md").write_text("---\ntype: spec\nid: SPEC-9\ntitle: [unclosed\n---\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "a Spec whose front matter does not parse")
        return root

    def test_the_fix_for_an_unreadable_spec_gets_its_command_by_the_rule(self):
        for label, name in NAMES.items():
            if label == "a leading dash":
                continue  # a folder under specs/ never starts the path with a dash
            for args in ((), ("README.md",)):  # `aidd status`, then `aidd status <path>`
                with self.subTest(name=label, args=args), tempfile.TemporaryDirectory() as d:
                    root = self.repository(d, name)
                    with in_folder(root):
                        code, out = run_cli("status", *args)
                    self.assertEqual(code, 0, out)
                    [line] = [x for x in out.splitlines() if x.startswith("unreadable:") and "SPEC-9" in x]
                    arrives_after_a_double_dash(self, line, "aidd", f"specs/{re.sub(chr(10), ' ', name)}/SPEC-9.md", name)
                    self.assertIn("fix its front matter", line)


class NewSpec(unittest.TestCase):
    def test_the_next_step_of_aidd_new_takes_a_specs_folder_from_the_config_by_the_rule(self):
        for label, name in NAMES.items():
            with self.subTest(name=label), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
                config = root / ".aidd" / "config.yaml"
                config.write_text(config.read_text(encoding="utf-8") + f"specs_dir: {json.dumps(name)}\n", encoding="utf-8")
                with in_folder(root):
                    code, out = run_cli("new", "spec", "SPEC-1", "--title", "t")
                self.assertEqual(code, 0, out)
                [line] = [x for x in out.splitlines() if x.startswith("next:")]
                arrives_after_a_double_dash(self, line, "aidd", re.sub(r"\s", " ", f"{name}/SPEC-1.md"), name)


class TrackedEvidenceFolder(unittest.TestCase):
    def test_the_step_that_untracks_the_evidence_folder_takes_its_name_from_the_config_by_the_rule(self):
        from aidd.testing import last_run

        for label, name in NAMES.items():
            if label in ("a leading dash", "a line break"):
                continue  # git reads neither as a folder to add here; the rule's own table covers them
            with self.subTest(name=label), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
                (root / name).mkdir(parents=True)
                (root / name / "evidence.json").write_text("{}", encoding="utf-8")
                git(root, "add", "-f", "--", f"{name}/evidence.json")
                found, note = last_run.last_run_summary(str(root), name)
                self.assertIsNone(found)
                self.assertIn("git tracks", note)
                spans = [c for c in commands(note) if c[0] == "git"]
                if command_names.quoted(name):
                    self.assertEqual([c[-2:] for c in spans], [["--", f":(icase){name}"]])
                else:
                    self.assertEqual(spans, [], note)
                    self.assertIn(command_names.NO_COMMAND, note)


class MisplacedExploration(unittest.TestCase):
    def test_the_command_for_the_right_folder_holds_the_title_as_one_word_and_the_specs_folder_by_the_rule(self):
        title = "what if $(touch PWNED); it's x"  # no backtick: the helper reads a command as a backtick span
        for label, name in NAMES.items():
            with self.subTest(name=label), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d).resolve() / "repo", "team", branch=None)
                config = root / ".aidd" / "config.yaml"
                config.write_text(config.read_text(encoding="utf-8") + f"specs_dir: {json.dumps(name)}\n", encoding="utf-8")
                with in_folder(root):
                    code, out = run_cli("new", "exploration", "elsewhere/idea", "--title", title)
                    typed_code, typed = run_cli("new", "exploration", f"elsewhere/{name}", "--title", title)
                self.assertNotEqual(code, 0, out)
                spans = [c for c in commands(out) if c[:3] == ["aidd", "new", "exploration"]]
                if command_names.quoted(name):
                    self.assertEqual([c[-2:] for c in spans], [["--title", title]], out)
                else:
                    self.assertEqual(spans, [], out)
                    self.assertIn(command_names.NO_COMMAND, out)
                # the folder the person typed joins the command by the same rule: an agent may have typed it from a file's text
                self.assertNotEqual(typed_code, 0, typed)
                with in_folder(root):
                    _, hidden = run_cli("new", "exploration", "elsewhere/a<slug>b", "--title", title)
                self.assertEqual([c for c in commands(hidden) if c[:3] == ["aidd", "new", "exploration"]], [], "a marker inside a typed name is no marker")
                if not command_names.quoted(name):
                    self.assertEqual([c for c in commands(typed) if c[:3] == ["aidd", "new", "exploration"]], [], typed)


class NamesTheCodeOwns(unittest.TestCase):
    """A printed command may hold a name from a closed set the code owns with no quoting, because each name in the set is a
    SAFE_NAME. `test_printed_commands.ACCEPTED` names these tests as the ones that hold such a site: a new name that a
    shell could misread fails here, never at a person's paste."""

    def plain(self, names, what: str) -> None:
        for name in names:
            with self.subTest(what=what, name=name):
                self.assertIsNotNone(command_names.quoted(name), f"{name!r} is no plain name, yet a command prints it")

    def test_every_subcommand_and_the_words_of_a_command_aidd_names_are_plain_names(self):
        import argparse

        from aidd.cli import parser as cli_parser

        def walk(parser) -> list[str]:
            names = []
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for name, sub in action.choices.items():
                        names += [name, *walk(sub)]
            return names

        found = walk(cli_parser.build_parser())
        self.assertIn("status", found)
        self.plain(found, "a subcommand")
        self.plain("delegate check".split(), "the words of a command a message names by literal")

    def test_every_harness_id_and_plugin_name_is_a_plain_name(self):
        from aidd import config

        self.plain(config.HARNESSES, "a harness id")
        self.plain([config.MARKETPLACE, config.PACKS_PLUGIN, "aidd", "aidd-team"], "a plugin or marketplace name, which `name@marketplace` joins with `@`")

    def test_every_work_item_type_and_document_type_is_a_plain_name(self):
        from aidd import config, workitems

        self.plain(config.item_type_rows(), "a work item type")
        self.plain([*workitems.DOC_TEMPLATES, *workitems.REPO_DOCS], "a document type")

    def test_the_paths_a_next_step_shows_are_plain_names_or_a_placeholder(self):
        from aidd import risk

        for label, name in NAMES.items():
            with self.subTest(name=label):
                shown = risk.shown_paths([name, "src/a.py"])
                self.assertEqual(shlex.split(shown)[-1], "src/a.py")
                self.assertEqual(shlex.split(shown)[0], name if command_names.quoted(name) else "<path>")


if __name__ == "__main__":
    unittest.main()
