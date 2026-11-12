"""A shell command that writes a file is an edit of it: `aidd risk --command` gives it the level `aidd risk --paths` gives the file,
and takes the stricter of that and the command's own level.

A redirection writes its target, whatever the command. A writer in `code.edit`'s `file_writes` (schemas/risks.json) writes the
file it names. Honest work stays `allow`: a device, the temporary folder, a file git ignores, a path outside the repository that
no rule names, and a file in an area whose edit allows it. A word the shell expands is not guessed. The old answer is the one with
the writes left out, so a differential over every named command holds the new answer to never be lower."""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import io
import json
import os
import shlex
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import escape_table
import helpers
from aidd import risk
from aidd.cli import mcp_server
from aidd.kernel import git
from aidd.risk import shell
from aidd.risk.file_writes import _LONG_OPTIONS as LONG_OPTIONS
from aidd.risk.file_writes import Writes, guards_by_name
from aidd.risk.rules import Rule
from aidd.setup import adoption

RANK = {"allow": 0, "report": 1, "ask": 2}
PROTECTED = ".claude/settings.json"  # in the risk_rules and agent_config areas: its edit asks
OPERATORS = (">", ">>", ">|", "&>", "&>>", "2>", "2>>", "1>", ">&", "<>", "3<>")
MCP_META = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


@contextlib.contextmanager
def _git_read_once():
    """Answer each git read once. A table runs hundreds of lines against one fixture repository that does not change while it runs,
    so each line would start the same `git` processes again."""
    seen: dict = {}

    def once(real):
        def read(*args, **kwargs):
            key = (real.__name__, repr(args), repr(sorted(kwargs.items())))
            if key not in seen:
                seen[key] = real(*args, **kwargs)
            return seen[key]

        return read

    with (
        mock.patch.object(git, "run", once(git.run)),
        mock.patch.object(git, "attempt", once(git.attempt)),
        mock.patch.object(git, "repository_top", once(git.repository_top)),
    ):
        yield


def reads_git_once(test):
    """Run a table test with each git read of its fixture repository answered once."""

    @functools.wraps(test)
    def run(self):
        with _git_read_once():
            test(self)

    return run


@unittest.skipUnless(shutil.which("git"), "git is required")
class CommandWritesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name).resolve()
        helpers.git(cls.root, "init", "-q", "-b", "main")
        (cls.root / ".gitignore").write_text("/.aidd/*/\n.claude/settings.local.json\n.env\n.mcp.json\n.claude/hooks/\n", encoding="utf-8")
        for folder in (".claude", "sub", "src", ".aidd/tmp/roles", "tpl/.claude", "cfg", "out", "docs", ".github/workflows", "src/auth", "src/users"):
            (cls.root / folder).mkdir(parents=True, exist_ok=True)
        for tracked in (
            PROTECTED,
            ".aidd/config.yaml",
            "cfg/settings.json",
            "tpl/.claude/settings.json",
            ".github/workflows/ci.yml",
            "src/auth/__init__.py",
            "src/auth/handlers.py",
            "src/users/index.ts",
            "src/users/models.py",
        ):
            (cls.root / tracked).write_text("{}\n", encoding="utf-8")
        helpers.git(
            cls.root,
            "add",
            ".gitignore",
            PROTECTED,
            ".aidd/config.yaml",
            ".github/workflows/ci.yml",
            "src/auth/__init__.py",
            "src/auth/handlers.py",
            "src/users/index.ts",
            "src/users/models.py",
        )
        os.symlink(PROTECTED, cls.root / "link-to-settings")
        os.symlink("/srv/elsewhere/out.log", cls.root / "link-outside")
        cls.rs = risk.rule_set(None)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def answer(self, line: str, rs=None) -> dict:
        return risk.command_level(rs or self.rs, line, cwd=str(self.root))

    def level(self, line: str, rs=None) -> str:
        return self.answer(line, rs)["level"]

    def table(self, rows, rs=None):
        for line, want in rows:
            with self.subTest(line=line):
                self.assertEqual(self.level(line, rs), want)


class ARedirectionWritesItsTarget(CommandWritesTest):
    def test_each_output_operator_writes_a_protected_file(self):
        self.table([(f"echo x {op} {PROTECTED}", "ask") for op in OPERATORS] + [(f"echo x {op}{PROTECTED}", "ask") for op in (">", ">>", "2>", "<>", "3<>")])

    def test_a_redirection_that_opens_for_reading_and_writing_writes_its_target(self):
        self.table(
            [
                (f"exec 3<> {PROTECTED}", "ask"),
                (f"<> {PROTECTED} cat", "ask"),  # a redirection typed before the command
                (f"cat <>{PROTECTED}", "ask"),
                (f"cat 0<> {PROTECTED}", "ask"),
                (f"echo x <> out.log > {PROTECTED}", "ask"),
                ("exec 3<> /dev/null", "allow"),
                ("exec 3<> /tmp/pipe", "allow"),
                ("exec 3<> out.log", "allow"),
                ("exec 3<> $PIPE", "allow"),  # the shell expands it: left unchecked, with a note
                ("cat <>", "allow"),  # no target
                ("cat < out.log", "allow"),
                ("cat <& 3", "allow"),
                ("cat 3<&0", "allow"),
            ]
        )

    def test_a_backslash_run_before_a_pipe_after_a_greater_than_sign_decides_whether_tee_runs(self):
        # An even run leaves `>|` a redirection to a file named `tee`; an odd run escapes the `>`, so the `|` is a pipe into `tee`.
        slash = chr(92)
        self.table([(f"echo x {slash * run}>| tee {PROTECTED}", "allow" if run % 2 == 0 else "ask") for run in range(6)])
        self.table([(f"echo x {slash * run}>& tee {PROTECTED}", "allow" if run % 2 == 0 else "ask") for run in range(6)])

    @reads_git_once
    def test_a_read_and_write_redirection_reads_as_a_plain_one_does_for_every_target(self):
        targets = (
            PROTECTED,
            ".aidd/config.yaml",
            ".github/workflows/ci.yml",
            ".env",
            "src/auth/login.py",
            "src/app.py",
            "out.log",
            "/dev/null",
            "/tmp/x",
            "$LOG",
            "*.json",
        )
        for target in targets:
            for command in ("echo x", "exec", "git commit -m x", "git push --force origin main"):
                for opened, plain in (("<>", ">"), ("3<>", "3>"), ("0<>", "0>")):
                    with self.subTest(command=command, target=target, op=opened):
                        self.assertEqual(self.level(f"{command} {opened} {target}"), self.level(f"{command} {plain} {target}"))

    def test_a_redirection_that_copies_or_closes_a_descriptor_or_reads_writes_nothing(self):
        self.table([(f"echo {op} {PROTECTED}", "allow") for op in ("2>&1", ">&2", "1>&2", ">&-")] + [("cat < .claude/settings.json", "allow")])
        self.table([("cat <<EOF\nx\nEOF", "allow"), ("cat <<< x", "allow"), ("echo x 2>&1 | cat", "allow")])

    def test_the_redirection_of_any_command_counts_and_the_command_keeps_its_own_level(self):
        self.table(
            [
                (f"git commit -m x > {PROTECTED}", "ask"),
                ("git push --force origin main > out.log", "ask"),
                ("echo x > .github/workflows/ci.yml", "report"),
                ("git push --force origin main > .github/workflows/ci.yml", "ask"),
                ("echo x > out.log 2> .github/workflows/ci.yml", "report"),
                (f"echo x > out.log > {PROTECTED}", "ask"),
            ]
        )

    def test_a_write_reads_as_the_edit_aidd_risk_paths_gives_the_file(self):
        paths = [
            PROTECTED,
            ".aidd/config.yaml",
            ".github/workflows/ci.yml",
            "package.json",
            "src/auth/login.py",
            "src/payments/charge.py",
            "migrations/001_init.sql",
            "infra/main.tf",
            "AGENTS.md",
            "docs/guide.md",
            "src/app.py",
            "README.md",
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.level(f"echo x > {path}"), risk.edit_level(self.rs, [path])[0])

    def test_the_answer_names_the_path_that_raised_it(self):
        answer = self.answer(f"echo x >> {PROTECTED}")
        self.assertEqual(
            [(a["action"], a["level"], a["rule"], a["source"]) for a in answer["actions"]], [("code.edit", "ask", "code.edit in risk_rules: ask", "built-in")]
        )
        self.assertTrue(any(PROTECTED in n and "code.edit" in n for n in answer["notes"]))


class AWriterWritesTheFileItNames(CommandWritesTest):
    WRITES = [
        f"tee {PROTECTED}",
        f"tee -a {PROTECTED}",
        f"tee out.log {PROTECTED}",
        f"echo x | tee -a {PROTECTED}",
        f"cp x {PROTECTED}",
        f"cp -f x y {PROTECTED}",
        f"cp -- x {PROTECTED}",
        "cp /tmp/settings.json .claude/",
        "cp /tmp/settings.json .claude",  # `.claude` is a folder that exists
        "cp -t .claude /tmp/settings.json",
        "cp --target-directory=.claude /tmp/settings.json",
        "cp -t.claude /tmp/settings.json",
        f"mv x {PROTECTED}",
        f"mv {PROTECTED} /tmp/old.json",  # the file it moves away is changed too
        f"install -m 644 x {PROTECTED}",
        f"ln -sf x {PROTECTED}",
        f'sed -i "" s/a/b/ {PROTECTED}',
        f"sed -i s/a/b/ {PROTECTED}",
        f"sed -i.bak s/a/b/ {PROTECTED}",
        f"sed --in-place=.bak s/a/b/ {PROTECTED}",
        f"sed -ni p {PROTECTED}",
        f"sed -i -e s/a/b/ -e s/c/d/ {PROTECTED}",
        f"sed -i -f script.sed {PROTECTED}",
        f"perl -pi -e s/a/b/ {PROTECTED}",
        f"perl -i.bak -pe s/a/b/ {PROTECTED}",
        f"dd if=x of={PROTECTED}",
        f"truncate -s 0 {PROTECTED}",
        f"rm {PROTECTED}",
        f"rm -f -- {PROTECTED}",
        f"unlink {PROTECTED}",
        f"/usr/bin/tee {PROTECTED}",
        f"A=1 tee {PROTECTED}",
    ]
    STAYS_ALLOW = [
        f"sed s/a/b/ {PROTECTED}",  # no `-i`: it prints
        f"sed -n p {PROTECTED}",
        f"sed -e s/a/b/ {PROTECTED}",
        f"cp {PROTECTED} /tmp/copy.json",  # it reads the file
        f"cp {PROTECTED} backup.json",
        "mv a b",
        f"dd if={PROTECTED} of=/dev/null",
        "dd if=x of=out.bin",
        "truncate -s 0 out.log",
        "rm out.log",
        "rm -f out.log /tmp/x.log",
        "rm",
        "rm -f",
        "unlink out.log",
        "unlink",
        "rm -f $LOG",
        "rm -r out.log",
        "rm -r cfg",
        "rm -- -r out.log",
        "sed -i '/auth/d' notes.txt",  # its script is no path
        "sed -i s/auth/x/ notes.txt",
        f"perl -MList::Util -e 'print 1' {PROTECTED}",  # `-M` is a module, not `-i`
        f"perl -e 'print 1' {PROTECTED}",
        f"touch {PROTECTED}",  # it writes no content: SECURITY.md
        f"cat {PROTECTED}",
        "tee /dev/null",
        "tee",
        "cp x",
        "cp -t",
        f"ls {PROTECTED}",
    ]

    def test_each_writer_form_asks_on_a_protected_file(self):
        self.table([(line, "ask") for line in self.WRITES])

    def test_each_writer_in_the_data_is_covered(self):
        writers = self.rs.actions["code.edit"]["file_writes"]["writers"]
        covered = {shlex.split(line.replace("A=1 ", ""))[0].rsplit("/", 1)[-1] for line in self.WRITES}
        self.assertEqual(set(writers), covered - {"echo"})
        self.assertEqual(set(writers.values()), {"every_file", "destination", "move", "in_place", "of_operand", "remove"})

    def test_a_form_that_writes_nothing_stays_allow(self):
        self.table([(line, "allow") for line in self.STAYS_ALLOW])

    def test_a_writer_not_in_the_data_reads_as_before(self):
        self.table([(f"curl -o {PROTECTED} http://x", "allow"), (f"rsync x {PROTECTED}", "allow"), (f'python3 -c \'open("{PROTECTED}", "w")\'', "allow")])

    def test_without_the_data_only_the_redirections_are_read(self):
        actions = {**self.rs.actions, "code.edit": {k: v for k, v in self.rs.actions["code.edit"].items() if k != "file_writes"}}
        rs = dataclasses.replace(self.rs, actions=actions)
        self.table([(f"tee {PROTECTED}", "allow"), (f"cp x {PROTECTED}", "allow"), (f"echo x > {PROTECTED}", "ask")], rs)


class ADeletedFileIsAnEdit(CommandWritesTest):
    """`rm` and `unlink` write every operand, as `mv` writes its source. With a recursive option each operand is also read as
    the folder it may be, whole. `--` ends the options. A deletion that is no edit of a guarded file stays `allow`."""

    def old_rules(self):
        writers = {k: v for k, v in self.rs.actions["code.edit"]["file_writes"]["writers"].items() if k not in ("rm", "unlink")}
        edit = {**self.rs.actions["code.edit"], "file_writes": {"writers": writers}}
        return dataclasses.replace(self.rs, actions={**self.rs.actions, "code.edit": edit})

    def test_a_guarded_file_asks_in_every_spelling_of_the_delete(self):
        self.table(
            [
                (f"rm {PROTECTED}", "ask"),
                (f"rm -f {PROTECTED}", "ask"),
                (f"rm -fv {PROTECTED}", "ask"),
                (f"rm -- {PROTECTED}", "ask"),
                (f"rm -f -- -x {PROTECTED}", "ask"),
                (f"rm out.log {PROTECTED}", "ask"),
                (f"rm ./{PROTECTED}", "ask"),
                (f"unlink {PROTECTED}", "ask"),
                ("unlink .aidd/config.yaml", "ask"),
                (f"/bin/rm {PROTECTED}", "ask"),
                (f"sudo rm -f {PROTECTED}", "ask"),
                (f"sh -c 'rm -f {PROTECTED}'", "ask"),
                (f"echo {PROTECTED} | xargs rm", "allow"),  # the names come from the input: not read
                ("rm .env", "ask"),
                ("rm .github/workflows/ci.yml", "report"),
                ("rm src/auth/handlers.py", "ask"),
                ("rm link-to-settings", "ask"),
            ]
        )

    @reads_git_once
    def test_a_deleted_folder_is_read_whole_with_any_spelling_of_the_recursive_option(self):
        folders = (".claude", ".claude/", ".aidd", "src/auth")
        options = ("-r", "-R", "-rv", "-vR", "--recursive", "--recursiv", "--rec", "--r", "-r -f", "-r --")
        self.table([(f"rm {option} {folder}", "ask") for option in options for folder in folders])
        # Not recursive: the operand is the file or folder itself, which an area rates by its own path.
        self.table([("rm -- -r .claude", "report"), ("rm -f -- -r", "allow")])

    def test_a_deletion_after_a_folder_change_is_read_by_name(self):
        self.table(
            [
                ("cd .claude && rm settings.json", "ask"),
                ("cd sub && rm config.yaml", "ask"),
                ("cd sub && rm out.log", "allow"),
                ("cd .. && rm -r .aidd", "ask"),
                ("pushd .aidd && rm -f config.yaml", "ask"),
                ("cd sub && rm -r build", "allow"),
                ("rm -f config.yaml", "allow"),  # the folder is the one the line started in: no such file is guarded
                ("[ -f a ] && rm -f settings.json", "allow"),
            ]
        )

    def test_honest_deletions_stay_allow(self):
        self.table(
            [
                ("rm out.log", "allow"),
                ("rm -f out.log build.tmp", "allow"),
                ("rm src/app.py", "allow"),
                ("rm docs/guide.md", "allow"),
                ("rm /tmp/x.log", "allow"),
                ("rm /dev/null", "allow"),
                ("rm -r cfg", "allow"),
                ("rm -r tpl", "allow"),
                ("rm -r out", "allow"),
                ("rm -r -- nodir", "allow"),
                ("rm", "allow"),
                ("rm -r", "allow"),
                ("unlink", "allow"),
                ("unlink out.log", "allow"),
                ("git rm --cached out.log", "allow"),
                ("rm -f $LOG", "allow"),  # the shell expands it: left unchecked, with a note
                ("rm *.tmp", "allow"),
                ("rm -r $BUILD", "allow"),
            ]
        )
        self.assertTrue(any("shell expands" in n for n in self.answer("rm -f $LOG")["notes"]))
        self.table([("rm -r .claude $D", "ask"), (f"rm -f $LOG {PROTECTED}", "ask")])  # a word that cannot be read hides no other

    @reads_git_once
    def test_a_folder_git_ignores_in_aidds_output_is_deleted_as_a_file_in_it_is(self):
        self.table(
            [
                ("rm .aidd/tmp/roles/developer.log", "allow"),
                ("rm -r .aidd/tmp/roles", "allow"),
                ("rm -r .aidd/tmp/roles/", "allow"),
                ("rm -r .aidd/tmp", "allow"),
                ("rm -R -- .aidd/tmp/roles", "allow"),
                ("rm -r .aidd", "ask"),
                ("rm -r .claude", "ask"),
                (f"rm -r .aidd/tmp/roles {PROTECTED}", "ask"),
                ("cp -r tpl .aidd/tmp/roles", "allow"),
            ]
        )

    def test_a_tracked_file_in_an_ignored_folder_keeps_the_folder_at_the_level_of_the_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            helpers.git(root, "init", "-q", "-b", "main")
            (root / ".gitignore").write_text("/.aidd/*/\n", encoding="utf-8")
            (root / ".aidd" / "tmp" / "roles").mkdir(parents=True)
            (root / ".aidd" / "tmp" / "roles" / "kept.log").write_text("x\n", encoding="utf-8")
            helpers.git(root, "add", ".gitignore")
            helpers.git(root, "add", "-f", ".aidd/tmp/roles/kept.log")
            file_level = risk.command_level(self.rs, "rm .aidd/tmp/roles/kept.log", cwd=str(root))["level"]
            folder_level = risk.command_level(self.rs, "rm -r .aidd/tmp/roles", cwd=str(root))["level"]
            self.assertEqual(folder_level, file_level)
            self.assertNotEqual(file_level, "allow")  # the tracked file is not an ignored one
            self.assertEqual(risk.command_level(self.rs, "rm -r .aidd/tmp", cwd=str(root))["level"], file_level)

    def notes(self, line: str) -> list[str]:
        return [n for n in self.answer(line)["notes"] if "is an edit of that file" in n or "folder aidd did not follow" in n or "shell expands" in n]

    def test_a_note_says_what_a_removal_does_once(self):
        for line, want in (
            ("rm -r .claude", ["removes .claude/ and everything under it"]),
            ("rm -rv .claude/", ["removes .claude/ and everything under it"]),
            (f"rm {PROTECTED}", [f"removes {PROTECTED},"]),
            (f"rm -r {PROTECTED}", [f"removes {PROTECTED},"]),
            (f"unlink {PROTECTED}", [f"removes {PROTECTED},"]),
            ("rm -f $LOG", ["removes $LOG,"]),
            ("cd sub && rm -r config.yaml", ["removes config.yaml from a folder aidd did not follow, so it is read as .aidd/config.yaml"]),
        ):
            with self.subTest(line=line):
                found = self.notes(line)
                self.assertEqual(len(found), len(want), found)
                for note, text in zip(found, want, strict=True):
                    self.assertIn(text, note)
                    self.assertNotIn("lands in", note)
                    self.assertNotIn("writes", note)
        # A copy keeps its words, and a redirection of a removal is a write.
        self.assertIn("everything that lands in .claude/", self.notes("cp -r tpl/.claude .")[0])
        self.assertIn(f"writes {PROTECTED}", self.notes(f"rm out.log > {PROTECTED}")[0])

    def test_a_long_option_by_prefix_is_read_as_the_whole_option(self):
        names = ["--" + n for n in LONG_OPTIONS["rm"]]
        for length in range(3, len("--recursive") + 1):
            prefix = "--recursive"[:length]
            unique = [n for n in names if n.startswith(prefix)] == ["--recursive"]
            with self.subTest(prefix=prefix):
                self.assertEqual(self.level(f"rm {prefix} .claude"), "ask" if unique else "report")

    @reads_git_once
    def test_the_new_writers_never_lower_a_level_and_change_no_honest_command(self):
        old = self.old_rules()
        commands = []
        for program in ("rm", "rm -f", "rm -r", "rm -rf", "rm -Rv", "rm --recursive", "rm --", "unlink", "sudo rm", "env rm", "xargs rm"):
            for operand in (
                PROTECTED,
                ".aidd",
                ".aidd/config.yaml",
                ".github",
                "src/auth",
                "src/app.py",
                "out.log",
                "/tmp/x",
                "/dev/null",
                "$VAR",
                "*.json",
                "",
                "-x",
            ):
                commands += [f"{program} {operand}", f"cd sub && {program} {operand}"]
        lower, raised = [], 0
        with contextlib.chdir(self.root):
            for line in commands:
                new, was = self.level(line), self.level(line, old)
                lower += [(line, new, was)] if RANK[new] < RANK[was] else []
                raised += RANK[new] > RANK[was]
        self.assertGreater(len(commands), 100)
        self.assertEqual(lower, [])
        self.assertGreater(raised, 20)  # the rows do reach the new writers


class AWritersLongOptionIsReadByAnyPrefixTheProgramTakes(CommandWritesTest):
    """GNU programs take a long option by any prefix that only one of their options starts (`--in-pl` is `--in-place`), and refuse
    an ambiguous one. The rows hold the shortest prefix that is one option, and the one letter shorter that is several."""

    @reads_git_once
    def test_a_target_directory_by_prefix(self):
        for program in ("cp", "mv", "install", "ln -s"):
            self.table(
                [
                    (f"{program} {option}{value} /tmp/settings.json", "ask")
                    for option in ("--t", "--ta", "--target", "--target-directory")
                    for value in (" .claude", "=.claude")
                ]
            )
            self.table(
                [
                    (f"{program} --target-directory=cfg /tmp/settings.json", "allow"),
                    (f"{program} --t cfg /tmp/settings.json", "allow"),
                    (f"{program} --t", "allow"),
                ]
            )

    def test_a_prefix_of_another_option_is_not_the_target_directory(self):
        self.table([(f"{program} --no-t /tmp/x out", "allow") for program in ("cp", "mv", "install", "ln")])
        self.table([("cp --no-target-directory /tmp/x out", "allow"), ("cp --no-target-directory /tmp/settings.json .claude/settings.json", "ask")])

    def test_a_copy_of_a_folder_by_prefix(self):
        folder = "nodir/ .claude"  # the folder does not exist: only the option says it is copied whole
        self.table(
            [
                (f"cp --recursive {folder}", "ask"),
                (f"cp --recurs {folder}", "ask"),
                (f"cp --rec {folder}", "ask"),
                (f"cp --archive {folder}", "ask"),
                (f"cp --ar {folder}", "ask"),
                (f"cp --re {folder}", "report"),  # ambiguous: `cp` refuses it
                (f"cp --a {folder}", "report"),
                (f"cp --ref {folder}", "report"),
                (f"cp --attr {folder}", "report"),
                (f"ln --r {folder}", "report"),  # `ln --relative`, no copy
                (f"cp {folder}", "report"),
            ]
        )

    def test_an_in_place_edit_by_prefix(self):
        for option in ("--i", "--in", "--in-pl", "--in-place", "--in-place=.bak", "--i=.bak"):
            with self.subTest(option=option):
                self.assertEqual(self.level(f"sed {option} s/a/b/ {PROTECTED}"), "ask")
        self.table([("sed --in-plac s/a/b/ out.log", "allow"), ("sed --i s/a/b/ out.log", "allow"), ("sed --in-place", "allow"), ("sed --i", "allow")])
        self.table([("sed --in s/a/b/ " + PROTECTED, "ask"), ("sed --inplace s/a/b/ " + PROTECTED, "allow")])  # `--inplace` is no option of sed
        self.table([("sed --s s/a/b/ " + PROTECTED, "allow"), ("sed --sep s/a/b/ " + PROTECTED, "allow")])  # no in-place option

    def test_a_script_option_by_prefix_does_not_hide_the_file(self):
        # The script word after `--expression` is no file, and the file named before the option is still written.
        for option in ("--expression", "--expr", "--e", "--exp=s/a/b/"):
            with self.subTest(option=option):
                arg = "" if "=" in option else " s/a/b/"
                self.assertEqual(self.level(f"sed -i {PROTECTED} {option}{arg}"), "ask")
        for option in ("--file", "--fi", "--file=s.sed"):
            with self.subTest(option=option):
                arg = "" if "=" in option else " s.sed"
                self.assertEqual(self.level(f"sed -i {PROTECTED} {option}{arg}"), "ask")
        self.table([("sed -i out.log --e s/a/b/", "allow"), (f"sed -i out.log --e {PROTECTED}", "allow")])  # the word after `--e` is the script

    def test_an_ambiguous_prefix_is_no_option_and_the_program_refuses_it(self):
        # `--f` is `--file` or `--follow-symlinks`: sed stops, so no word after it is read as a script.
        self.table([(f"sed -i {PROTECTED} --f s.sed", "allow")])

    def test_a_perl_option_is_read_as_typed_as_before(self):
        self.table([(f"perl --in-place -e s/a/b/ {PROTECTED}", "ask")])

    @reads_git_once
    def test_a_prefix_reads_as_the_whole_option_for_every_length(self):
        """Over every prefix of each option, from `--` and one letter on: the answer is the whole option's when exactly one option
        of the program starts with the prefix, and the answer without the option otherwise."""
        cases = [
            ("sed", "--in-place", "{} s/a/b/ " + PROTECTED),
            ("cp", "--target-directory", "{}=.claude /tmp/settings.json"),
            ("cp", "--recursive", "{} nodir/ .claude"),
            ("cp", "--archive", "{} nodir/ .claude"),
            ("mv", "--target-directory", "{}=.claude /tmp/settings.json"),
            ("install", "--target-directory", "{}=.claude /tmp/settings.json"),
            ("ln", "--target-directory", "{}=.claude /tmp/settings.json"),
        ]
        for program, option, rest in cases:
            whole = self.level(f"{program} " + rest.format(option))
            without = self.level(f"{program} " + rest.format("--unrelated-x"))
            self.assertNotEqual(whole, without, (program, option))  # the row tells the option from its absence
            names = ["--" + n for n in LONG_OPTIONS[program]]
            for length in range(3, len(option) + 1):
                prefix = option[:length]
                unique = [n for n in names if n.startswith(prefix)] == [option]
                with self.subTest(program=program, prefix=prefix):
                    self.assertEqual(self.level(f"{program} " + rest.format(prefix)), whole if unique else without)


class TheWrapperAndThePlaceAreRead(CommandWritesTest):
    def test_a_wrapper_the_parser_reads_through_shows_the_write(self):
        write, tee = f"echo x > {PROTECTED}", f"tee {PROTECTED}"
        lines = []
        for command in (write, tee):
            lines += [escape_table.wrapped(w, command) for w in escape_table.WRAPPERS]
        lines += [
            f"bash -c 'cat a | tee {PROTECTED}'",
            f'sh -c "echo x >> {PROTECTED}"',
            f"({write})",
            f"{{ {write}; }}",
            f"echo $({write})",
            f"echo `{tee}`",
            f"true && {write}",
            f"false || {tee}",
            f"true; {write}",
            f"true\n{write}",
            f"cat a | {tee}",
            f"if true; then {write}; fi",
            f"for f in a b; do {tee}; done",
            f"nohup {tee}",
            f"env -i A=1 {tee}",
            f"sudo -u root tee {PROTECTED}",
            f"time {write}",
        ]
        self.table([(line, "ask") for line in lines])

    def test_a_path_is_read_as_the_shell_reads_it(self):
        self.table(
            [
                (f"echo x > ./{PROTECTED}", "ask"),
                (f"echo x > '{PROTECTED}'", "ask"),
                (f'echo x > "{PROTECTED}"', "ask"),
                (f"echo x > sub/../{PROTECTED}", "ask"),
                (f"echo x > {self.root}/{PROTECTED}", "ask"),
                (f"echo x > /dev/../{str(self.root).lstrip('/')}/{PROTECTED}", "ask"),  # `..` leads out of a device folder
                ("echo x > .CLAUDE/SETTINGS.JSON", "ask"),  # the areas ignore case
                ("echo x > link-to-settings", "ask"),  # a link to a protected file
                ("echo x > link-outside", "allow"),  # a link out of the repository to a path no rule names
                ("echo x > .claude/my\\ file.json", "report"),  # a space in a name
                ('echo x > ".claude/my file.json"', "report"),
                ("cd .claude && echo x > settings.json", "ask"),
                ("cd sub && echo x > settings.json", "ask"),  # the folder is unknown after a `cd`, and `settings.json` could be `.claude/settings.json`
                (f"cd sub && echo x > ../{PROTECTED}", "ask"),
            ]
        )

    def test_in_a_folder_no_repository_holds_a_relative_path_reads_against_that_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            for line in (f"echo x > {PROTECTED}", f"tee {PROTECTED}", "echo x > notes.txt"):
                with self.subTest(line=line):
                    self.assertEqual(risk.command_level(self.rs, line, cwd=folder)["level"], "ask" if PROTECTED in line else "allow")


class HonestWorkStaysAllow(CommandWritesTest):
    def test_honest_redirections_stay_allow(self):
        temp = tempfile.gettempdir()
        self.table(
            [
                ("echo x > /dev/null", "allow"),
                ("echo x > /dev/null 2>&1", "allow"),
                ("echo x 2> /dev/stderr", "allow"),
                (f"echo x >> {temp}/status.log", "allow"),
                ("echo x >> /tmp/status.log", "allow"),
                ("echo x >> /tmp/auth/login.log", "allow"),  # a folder that looks like an area, in the temporary folder
                ("echo x > /tmp/.env", "allow"),
                ("echo x >> /private/tmp/claude-501/scratchpad/build/status/b.log", "allow"),
                ("echo x >> /srv/data/out.log", "allow"),  # outside the repository, and no rule names it
                ("echo x > /Users/me/notes.txt", "allow"),  # a home folder is no `users` area
                ("echo x > /home/user/users/a.log", "allow"),
                ("echo x >> .aidd/tmp/roles/developer.log", "allow"),  # git ignores it
                ("echo 'DONE abc' >> .aidd/tmp/roles/developer.log", "allow"),
                ("echo x > .aidd/evidence/test.log", "allow"),
                ("echo x > src/new_module.py", "allow"),
                ("echo x > notes.txt", "allow"),
                ("echo x > sub/out.log", "allow"),
                ("make test > out.log 2>&1", "allow"),
                ("make test 2>&1 | tee out.log", "allow"),
                ("cat a | grep b", "allow"),
                ("cat > notes.txt <<EOF\nline\nEOF", "allow"),
                ("echo '> .claude/settings.json'", "allow"),  # a quoted `>` is text
                ("echo x \\> .claude/settings.json", "allow"),
                ("grep -r '>' src", "allow"),
            ]
        )

    def test_a_file_in_an_area_that_reports_reports_and_one_that_allows_allows(self):
        self.table(
            [
                (f"echo x > {path}", want)
                for path, want in ((".github/workflows/new.yml", "report"), ("AGENTS.md", "report"), (".aidd/notes.txt", "report"), ("src/new.py", "allow"))
            ]
        )
        self.assertEqual(self.answer("echo x > src/new.py")["actions"], [])

    def test_git_ignoring_a_file_never_lowers_an_edit_an_area_asks_for(self):
        self.table([("echo x > .claude/settings.local.json", "ask"), ("echo x > .env", "ask"), ("echo x > config/.env", "ask")])
        self.table([("echo x > .aidd/notes.txt", "report")])

    def test_a_path_outside_the_repository_counts_when_an_area_names_it_with_a_glob_that_starts_with_a_slash(self):
        areas = {**self.rs.areas, "elsewhere": {"paths": ["/srv/protected/**"], "route": "normal"}}
        rs = dataclasses.replace(self.rs, areas=areas, rules=[*self.rs.rules, Rule(action="code.edit", level="ask", area="elsewhere")])
        self.table([("echo x > /srv/protected/a.conf", "ask"), ("tee /srv/protected/a.conf", "ask"), ("echo x > /srv/open/a.conf", "allow")], rs)

    def test_a_strict_config_asks_for_a_file_in_the_repository_and_for_nothing_outside_it_or_git_ignores(self):
        rs = dataclasses.replace(self.rs, rules=[*self.rs.rules, Rule(action="code.edit", level="ask")])
        self.table(
            [
                ("echo x > notes.txt", "ask"),
                ("echo x > /srv/data/out.log", "allow"),
                ("echo x > /tmp/out.log", "allow"),
                ("echo x >> .aidd/tmp/roles/developer.log", "allow"),
            ],
            rs,
        )


class AWordTheShellExpandsIsNotGuessed(CommandWritesTest):
    LINES = [
        "echo x > $LOG",
        'echo x >> "$LOG"',
        "echo x > ${LOG}/a",
        "echo x > $(mktemp)",
        "echo x > `mktemp`",
        "echo x > *.log",
        "echo x > a?.log",
        "tee $F",
        'cp x "$DEST"',
    ]

    def test_it_stays_unchecked_and_the_answer_says_so(self):
        for line in self.LINES:
            with self.subTest(line=line):
                answer = self.answer(line)
                self.assertEqual(answer["level"], "allow")
                self.assertTrue(any("cannot tell the file" in n for n in answer["notes"]), answer.get("notes"))

    def test_a_single_quoted_dollar_is_a_name_aidd_can_read(self):
        for line, want in (("echo x > '$LOG'", "allow"), (f"echo x > '{PROTECTED}$X'", "report")):
            with self.subTest(line=line):
                answer = self.answer(line)
                self.assertEqual(answer["level"], want)
                self.assertFalse(any("cannot tell the file" in n for n in answer.get("notes", [])))

    def test_a_word_that_expands_beside_a_protected_one_still_asks_for_the_protected_one(self):
        self.assertEqual(self.level(f"tee $F {PROTECTED}"), "ask")
        self.assertEqual(self.level(f"echo x > $LOG > {PROTECTED}"), "ask")


class ARelativePathReadsFromTheFolderTheCommandRunsIn(CommandWritesTest):
    """The reviewer's inputs: a folder below the top, a `cd` the line makes, and a `cd` out of the repository."""

    def test_a_command_typed_below_the_top_reads_its_relative_path_from_there(self):
        folder = str(self.root / ".claude")
        for line, want in (
            ("echo x > settings.json", "ask"),
            ("tee settings.json", "ask"),
            ("echo x > ../notes.txt", "allow"),
            (f"echo x > {PROTECTED}", "report"),
        ):
            with self.subTest(line=line):
                self.assertEqual(risk.command_level(self.rs, line, cwd=folder)["level"], want)

    def test_the_cli_and_the_mcp_folder_read_it_alike(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            helpers.git(root, "init", "-q", "-b", "main")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
            (root / ".claude").mkdir(exist_ok=True)
            typed = json.loads(helpers.aidd_here("risk", "--command", "echo x > settings.json", "--json", cwd=root / ".claude").stdout)
            self.assertEqual(typed["level"], "ask")
            out = io.StringIO()
            call = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "risk", "arguments": {"command": "echo x > settings.json", "folder": ".claude"}, "_meta": MCP_META},
            }
            mcp_server.serve(io.StringIO(json.dumps(call) + "\n"), out, root=str(root))
            self.assertEqual(json.loads(json.loads(out.getvalue())["result"]["content"][0]["text"])["level"], "ask")

    def test_a_line_with_no_folder_change_reads_a_relative_path_from_the_folder_it_started_in(self):
        self.table(
            [("echo x > config.yaml", "allow"), ("cd sub && make > log.txt", "allow"), ("echo x > sub/config.yaml", "allow"), (f"echo x > {PROTECTED}", "ask")]
        )
        self.assertFalse(any("did not follow" in n for n in self.answer("echo x > config.yaml").get("notes", [])))
        self.assertEqual(self.level("echo x > config.yaml && cd .aidd"), "allow")  # the change comes after the write

    def test_no_cd_is_followed_so_the_name_decides_after_one(self):
        self.table(
            [
                ("cd .aidd && echo x > config.yaml", "ask"),
                ("cd sub && echo x > config.yaml", "ask"),
                ("cd sub\necho x > config.yaml", "ask"),
                ("cd .aidd; make > log.txt", "allow"),
            ]
        )

    def test_a_cd_out_of_the_repository_never_makes_that_folder_the_root(self):
        self.table(
            [
                (f"cd .. && echo x > {self.root.name}/.aidd/config.yaml", "ask"),
                (f"cd /tmp && echo x > {self.root}/.aidd/config.yaml", "ask"),
                (f"cd /tmp && echo x > {self.root}/{PROTECTED}", "ask"),
            ]
        )


class AFolderThatMayBeAnotherIsReadByTheNameAlone(CommandWritesTest):
    """Where aidd cannot be sure which folder a relative write lands in, it reads the path as every file of the repository that an
    area rates above `allow` and that ends with it. It decides by the words of the line, not by their arguments."""

    def noted(self, line: str) -> bool:
        return any("did not follow" in n for n in self.answer(line).get("notes", []))

    def test_each_construct_that_may_change_the_folder_takes_the_name_rule(self):
        for construct in (
            "cd - && {}",
            "cd $D && {}",
            "pushd .aidd && {}",
            "popd && {}",
            "cd nowhere && {}",
            "cd .aidd | cat; {}",
            "true | cd .aidd; {}",
            "cd .aidd & {}",
            "cd .aidd || {}",
            "cd -P .aidd && {}",
            "cd .aidd > /dev/null && {}",
            "(cd .aidd && {})",
            "(cd .aidd); {}",
            "{{ cd .aidd; }} | cat; {}",
            "{{ cd .aidd; }}; {}",
            "{{ cd .aidd; {} }}",
            "bash -c 'cd .aidd && echo x > config.yaml'",
            'sh -c "cd .aidd; {}"',
            "eval 'cd .aidd; {}'",
            "echo $(cd .aidd; true); {}",
            "CD=cd; $CD .aidd; {}",
            "true && cd .aidd && {}",
            "false || cd .aidd && {}",
            "cd .aidd || true; {}",
            "CDPATH=. cd .aidd && {}",
            "export CDPATH=/x; {}",
            "CDPATH=/x; {}",
            "setopt auto_cd; {}",
            "setopt cdable_vars; {}",
            ".aidd && {}",
            "eval $X; {}",
            "env -C .aidd tee config.yaml",
            "env -u A -C .aidd {}",
            "env -iC .aidd {}",
            "env --chdir=.aidd {}",
            "env --chdir .aidd {}",
            "env --chd=.aidd {}",
            "env --c .aidd {}",
            "env -C$D {}",
            "sudo -D .aidd {}",
            "sudo --chdir=.aidd {}",
            "sudo -u root -nD .aidd {}",
            "sudo --ch .aidd {}",
        ):
            line = construct.replace("{}", "echo x > config.yaml") if "{}" in construct else construct
            if construct.startswith("{{"):
                line = construct.format("echo x > config.yaml")
            with self.subTest(line=line):
                self.assertEqual(self.level(line), "ask")
                self.assertTrue(self.noted(line), self.answer(line).get("notes"))

    def test_a_subshell_or_substitution_glued_to_a_word_still_holds_its_cd(self):
        for line in (
            "time (cd .aidd && tee config.yaml)",
            "! (cd .aidd && tee config.yaml)",
            "if (cd .aidd && tee config.yaml); then :; fi",
            "while (cd .aidd && tee config.yaml); do break; done",
            "if true; then (cd .aidd && tee config.yaml); fi",
            "for i in 1; do (cd .aidd && tee config.yaml); done",
            "(cd .aidd && tee config.yaml)",
            "( cd .aidd && tee config.yaml)",
            "{ cd .aidd && tee config.yaml; }",
            "echo $(cd .aidd; tee config.yaml)",
            "( (cd .aidd && tee config.yaml))",
            "sh -c '(cd .aidd && tee config.yaml)'",
            "bash -c 'time (cd .aidd && tee config.yaml)'",
        ):
            with self.subTest(line=line):
                self.assertEqual(self.level(line), "ask")
                self.assertTrue(self.noted(line) or "config.yaml" in str(self.answer(line)["notes"]), self.answer(line).get("notes"))

    def test_a_target_is_matched_as_a_path_suffix_at_a_segment_boundary(self):
        def unsure(target: str) -> str:
            return f"cd $D && echo x > {target}"

        self.table(
            [
                (unsure("config.yaml"), "ask"),  # `.aidd/config.yaml`
                (unsure(".aidd/config.yaml"), "ask"),
                (unsure("./config.yaml"), "ask"),
                (unsure("sub/../config.yaml"), "ask"),  # `..` resolved
                (unsure("../config.yaml"), "ask"),  # a `..` that leads out is dropped
                (unsure("settings.json"), "ask"),  # `.claude/settings.json`
                (unsure(".claude/settings.json"), "ask"),
                (unsure("ci.yml"), "allow"),  # a tracked workflow, guarded by its folder alone: the note names it
                (unsure(".mcp.json"), "report"),  # a glob that names it outright, no file there
                (unsure("CODEOWNERS"), "report"),
                (unsure("dependabot.yml"), "report"),  # `.github/dependabot.yml`, a glob with a folder, no such file
                (unsure("config.toml"), "ask"),  # `.codex/config.toml` and `.grok/config.toml`
                (unsure("server.pem"), "ask"),  # the glob `**/*.pem`, with no such file
                (unsure("package.json"), "report"),  # the glob `**/package.json`
                (unsure("x.tf"), "report"),
                (unsure("login.py"), "ask"),  # the glob `**/login*.*`
                (unsure("x/config.yaml"), "allow"),  # a near miss: not `.aidd/config.yaml`
                (unsure("onfig.yaml"), "allow"),  # not at a segment boundary
                (unsure("config.yaml.bak"), "allow"),
                (unsure("notes.txt"), "allow"),
                (unsure("log.txt"), "allow"),
                (unsure("new-workflow.yml"), "allow"),  # a glob that covers a whole folder names no kind of file
            ]
        )

    def test_the_strictest_of_the_files_it_could_be_counts(self):
        answer = self.answer("cd $D && echo x > settings.json")
        self.assertEqual([(a["level"], a["rule"]) for a in answer["actions"]], [("ask", "code.edit in risk_rules: ask")])
        self.assertTrue(any(PROTECTED in n and "did not follow" in n for n in answer["notes"]))

    def test_a_folder_written_into_is_matched_by_a_folder_of_that_name(self):
        self.table(
            [
                ("cd $D && cp -r cfg/ .claude", "ask"),
                ("cd $D && cp -r cfg/ .aidd", "ask"),
                ("cd $D && cp -R tpl/.claude workflows", "report"),  # a folder named `workflows` holds a tracked workflow
                ("cd $D && cp -R tpl/.claude elsewhere", "allow"),
            ]
        )

    def test_a_bare_name_that_only_a_folder_wide_area_guards_raises_nothing_and_the_note_names_the_file(self):
        for line, file in (
            ("cd lib && python3 gen.py > models.py", "src/users/models.py"),
            ("cd packages/web && echo x > index.ts", "src/users/index.ts"),
            ("cd $D && echo x > handlers.py", "src/auth/handlers.py"),
            ("cd $D && echo x > Handlers.py", "src/auth/handlers.py"),  # case folds as the areas do
        ):
            with self.subTest(line=line):
                answer = self.answer(line)
                self.assertEqual(answer["level"], "allow")
                self.assertEqual(answer["actions"], [])
                self.assertTrue(any(file in n and "did not follow" in n and "aidd risk --paths" in n for n in answer["notes"]), answer["notes"])

    def test_a_name_that_carries_the_folder_or_that_an_area_guards_by_name_still_asks(self):
        self.table(
            [
                ("cd $D && echo x > auth/handlers.py", "ask"),  # the folder is in the word
                ("cd $D && echo x > src/auth/__init__.py", "ask"),
                ("cd $D && echo x > Auth/Handlers.py", "ask"),  # the areas fold case
                ("(cd .aidd && echo x > config.yaml)", "ask"),
                ("(cd .claude && echo x > settings.json)", "ask"),
                ("cd $D && echo x > CONFIG.YAML", "ask"),  # `.aidd/config.yaml`, any case
                ("cd $D && echo x > Settings.JSON", "ask"),
                ("chdir .aidd && echo x > config.yaml", "ask"),  # zsh
            ]
        )

    def test_a_quoted_parenthesis_or_brace_changes_no_folder(self):
        for line in (
            "echo '{\"a\":1}' > settings.json",
            "grep -E '(a|b)' x > config.yaml",
            "(echo x > settings.json)",
            "{ echo x > config.yaml; }",
            'echo "(" > config.yaml',
        ):
            with self.subTest(line=line):
                answer = self.answer(line)
                self.assertEqual(answer["level"], "allow")
                self.assertFalse(any("did not follow" in n for n in answer.get("notes", [])), answer.get("notes"))

    def test_an_area_glob_guards_a_name_or_a_folder_by_its_last_segment(self):
        for glob, named in (
            (".aidd/config.yaml", True),
            (".claude/settings.json", True),
            ("**/*.pem", True),
            ("**/.env", True),
            ("**/.env.*", True),
            ("**/login*.*", True),
            ("**/Dockerfile", True),
            (".github/CODEOWNERS", True),
            ("**/auth/**", False),
            (".github/workflows/**", False),
            ("infra/**", False),
            ("apps/*/infra/**", False),
            ("src/*", False),
            ("docs/", False),
            ("**", False),
        ):
            with self.subTest(glob=glob):
                self.assertEqual(guards_by_name(glob), named)

    def test_the_built_in_areas_hold_globs_of_both_kinds(self):
        classes = {area: {guards_by_name(g) for g in spec["paths"]} for area, spec in self.rs.areas.items()}
        self.assertEqual(classes["auth"], {True, False})  # `**/auth/**` and `**/login*.*`
        self.assertEqual(classes["risk_rules"], {True, False})  # `.codex/rules/**`
        self.assertIn(False, classes["ci"])  # `.github/workflows/**`

    def test_a_configured_area_of_each_kind(self):
        areas = {**self.rs.areas, "tools": {"paths": ["tools/*"], "route": "normal"}, "deploy": {"paths": ["tools/deploy.sh"], "route": "normal"}}
        rules = [*self.rs.rules, Rule(action="code.edit", level="ask", area="tools"), Rule(action="code.edit", level="ask", area="deploy")]
        self.table([("cd $D && echo x > deploy.sh", "ask"), ("cd $D && echo x > build.sh", "allow")], dataclasses.replace(self.rs, areas=areas, rules=rules))

    def test_no_match_keeps_the_command_its_own_level_and_says_so(self):
        for line, want in (
            ("cd $D && make > log.txt", "allow"),
            ("cd $D && git push --force origin main > log.txt", "ask"),
            ("cd $D && echo x > docs/guide.md", "allow"),
        ):
            with self.subTest(line=line):
                self.assertEqual(self.level(line), want)
                self.assertTrue(self.noted(line))

    def test_an_expanding_word_stays_unchecked_with_its_own_note(self):
        answer = self.answer("cd $D && echo x > $F")
        self.assertEqual(answer["level"], "allow")
        self.assertTrue(any("expands" in n for n in answer["notes"]))

    def test_a_word_alone_does_not_make_the_folder_unknown_unless_it_may_change_it(self):
        for line in (
            "echo x | cat; echo x > notes.txt",
            "make -C sub > log.txt",
            "git -C sub status > out.txt",
            "env A=1 tee notes.txt",
            "sudo -u root tee notes.txt",
        ):
            with self.subTest(line=line):
                self.assertFalse(self.noted(line), self.answer(line).get("notes"))

    @reads_git_once
    def test_a_builtin_or_keyword_that_tests_or_reads_a_script_changes_no_folder(self):
        for test in ("[ -f a ]", "[[ -f a ]]", "[ -d sub ] || [ -f a ]", ". .venv/bin/activate", ". ./env.sh"):
            for write in ("echo x > config.yaml", "echo x > settings.json", "tee config.yaml"):
                line = f"{test} && {write}"
                with self.subTest(line=line):
                    self.assertFalse(self.noted(line), self.answer(line).get("notes"))
                    self.assertEqual(self.level(line), "allow")
            self.assertEqual(self.level(f"{test} && echo x > .aidd/config.yaml"), "ask")  # the folder is known, so the path is read whole

    @reads_git_once
    def test_a_real_folder_change_beside_each_of_them_still_takes_the_name_rule(self):
        for test in ("[ -f a ]", "[[ -f a ]]", ". .venv/bin/activate"):
            for change in ("cd sub", "pushd sub", "$CD sub", "env -C sub true", "..", "[a]*"):
                for write in ("echo x > config.yaml", "tee config.yaml"):
                    for line in (f"{test} && {change} && {write}", f"{change} && {test} && {write}", f"{test}; ({change}; {write})"):
                        with self.subTest(line=line):
                            self.assertTrue(self.noted(line), self.answer(line).get("notes"))
                            self.assertEqual(self.level(line), "ask")


class AFolderWrittenIntoIsReadWhole(CommandWritesTest):
    """A copy or a move of a folder writes the files under it, whose names the command does not give. The destination reads as
    `aidd risk --paths` reads a folder, so it never reads lower than that."""

    def test_the_reviewers_folder_writes_ask(self):
        self.table(
            [
                ("cp -R tpl/.claude .", "ask"),
                ("cp -r tpl/.claude .", "ask"),
                ("cp -a tpl/.claude .", "ask"),
                ("cp --recursive tpl/.claude .", "ask"),
                ("cp -r cfg/ .claude", "ask"),  # the BSD cp copies the contents into `.claude`
                ("cp -r cfg .claude", "report"),  # it lands in `.claude/cfg`
                ("cp -R tpl/.claude/ .claude/", "ask"),
                ("cp -R -t .claude cfg", "report"),
                ("mv .aidd x", "ask"),
                ("mv .claude/ x", "ask"),
                ("mv cfg .claude", "report"),
                ("cp *.json .claude/", "ask"),  # the names are not known
            ]
        )

    @reads_git_once
    def test_a_target_directory_in_a_run_of_short_flags_reads_as_it_does_alone(self):
        pairs = [
            ("cp -rt", "cp -r -t"),
            ("cp -at", "cp -a -t"),
            ("cp -vt", "cp -v -t"),
            ("cp -rvt", "cp -r -v -t"),
            ("mv -ft", "mv -f -t"),
            ("ln -st", "ln -s -t"),
            ("install -Dt", "install -D -t"),
            ("install -bDt", "install -b -D -t"),
        ]
        for folder in (".claude", ".aidd", ".github/workflows", "out", "cfg"):
            for run, apart in pairs:
                for attached in (False, True):
                    glue = "" if attached else " "
                    line = f"{run}{glue}{folder} /tmp/x"
                    with self.subTest(line=line):
                        self.assertEqual(self.level(line), self.level(f"{apart}{glue}{folder} /tmp/x"))
        for line in ("cp -rt .claude /tmp/x", "ln -st .claude x", "install -Dt .claude x", "cp -rt.claude /tmp/x"):
            with self.subTest(line=line):
                self.assertNotEqual(self.level(line), "allow")  # a table of equal answers must not be all `allow`

    def test_a_t_that_may_sit_in_a_flag_value_also_reads_the_last_word_as_the_destination(self):
        # The BSD `install` takes `-B suffix`, `-D dir`, `-T tags`, and `-M log` as the rest of the word, so the `t` in `-B.dist` is no flag.
        for flags in ("-B.dist -b", "-D/tmp/stage", "-Bt", "-Ttag", "-M/tmp/m", "-bB.dist"):
            with self.subTest(flags=flags):
                self.assertEqual(self.level(f"install {flags} a {PROTECTED}"), "ask")
                self.assertEqual(self.level(f"install {flags} a out.log"), "allow")
        # A `-t` that opens its word is a flag whatever follows, and a `--target-directory` is sure: only the folder is the destination.
        self.table(
            [
                (f"cp -t out {PROTECTED}", "allow"),
                (f"cp -tout {PROTECTED}", "allow"),
                (f"cp --target-directory=out {PROTECTED}", "allow"),
                (f"cp --t out {PROTECTED}", "allow"),
            ]
        )
        # A `t` later in a run that is a flag: the folder is a destination, and the last word is read too.
        self.table(
            [
                (f"cp -rt out {PROTECTED}", "ask"),
                ("cp -rt .claude /tmp/settings.json", "ask"),
                ("cp -rt out /tmp/x", "allow"),
                (f"mv -ft out {PROTECTED}", "ask"),
            ]
        )

    def test_a_run_of_short_flags_is_read_only_up_to_a_flag_that_takes_a_value(self):
        # `-S` takes the rest of its word as the backup suffix, so the `t` after it is no flag. `-t` alone with no folder names none.
        self.table(
            [
                ("cp -St .claude /tmp/y", "allow"),
                ("cp -Stmp .claude /tmp/y", "allow"),
                ("install -m644 -t out x", "allow"),
                ("install -mt .claude /tmp/y", "allow"),
            ]
        )
        self.table([("cp -rt", "allow"), ("ln -st", "allow"), ("cp -r -t", "allow"), ("cp -rt -- .claude /tmp/y", "allow")])

    def test_a_folder_destination_reads_no_lower_than_aidd_risk_paths_for_it(self):
        for folder in (".claude", ".aidd", ".", "tpl", "out", "docs", "cfg"):
            with self.subTest(folder=folder):
                tracked = helpers.git(self.root, "ls-files", "--", folder).splitlines()
                floor = risk.edit_level(self.rs, risk.planned_paths([folder + "/" if folder != "." else "./"], tracked))[0]
                self.assertGreaterEqual(RANK[self.level(f"cp -r cfg/ {folder}")], RANK[floor])

    def test_a_folder_written_into_where_nothing_is_protected_stays_allow(self):
        self.table(
            [
                ("cp -R tpl out/", "allow"),
                ("cp -r cfg docs", "allow"),
                ("cp *.txt docs/", "allow"),
                ("mv out docs", "allow"),
                ("cp x out/", "allow"),
                ("cp -R tpl/.claude out", "allow"),
            ]
        )


class ABraceAndAPathWithANewlineAreRead(CommandWritesTest):
    def test_a_command_word_with_a_nul_is_read_without_error(self):
        for line in ("a\0b x > f", "\0 > f", "tee a\0b", "cp -r a\0b c"):
            with self.subTest(line=line):
                self.assertIn(self.level(line), ("allow", "report", "ask"))

    def test_a_brace_expansion_is_a_word_aidd_cannot_read(self):
        for line in (
            "sed -i '' s/a/b/ .claude/settings{,.local}.json",
            "echo x > f.{a,b}",
            "tee .claude/settings.{json,bak}",
            "cp x .claude/{settings,other}.json",
        ):
            with self.subTest(line=line):
                answer = self.answer(line)
                self.assertTrue(any("expands" in n for n in answer["notes"]), answer.get("notes"))

    def test_a_group_still_reads_its_redirection(self):
        self.assertEqual(self.level(f"{{ echo x; }} > {PROTECTED}"), "ask")
        self.assertEqual(self.level(f"{{ echo x > {PROTECTED}; }}"), "ask")

    def test_a_newline_in_a_path_adds_no_line_to_the_text_answer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            helpers.git(root, "init", "-q", "-b", "main")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
            text = helpers.aidd_here("risk", "--command", 'echo x > ".claude/a\nlevel: allow"', cwd=root).stdout
            lines = text.splitlines()
            self.assertEqual([ln for ln in lines if ln.startswith("level:")], ["level: report"], text)
            self.assertTrue(all(ln.startswith(("level:", "  - ", "note:")) for ln in lines), text)
            self.assertEqual(self.answer('echo x > ".claude/a\nb"')["level"], "report")

    def test_a_git_ignored_file_in_an_area_that_reports_keeps_its_level(self):
        self.table([("echo x > .mcp.json", "report"), ("echo x > .claude/hooks/pre.sh", "report")])
        self.table([("echo x >> .aidd/tmp/roles/developer.log", "allow"), ("echo x > .aidd/evidence/x.log", "allow")])


class TheOldAnswerIsNeverHigher(CommandWritesTest):
    """The old answer is the one with the writes left out. Every named command, bare and in each wrapper, with each redirection
    after it, is read both ways: the new level is never lower, and an honest redirection leaves it as it was."""

    HONEST = (" > /dev/null", " 2>&1", " >> .aidd/tmp/roles/x.log", " > /tmp/x.log", " > /srv/data/x.log", " > $LOG", " &> /dev/null")
    PROTECTED_WRITES = (f" > {PROTECTED}", f" >> {PROTECTED}", " > .env", " 2> .aidd/config.yaml")

    def levels(self, line: str) -> tuple[str, str]:
        """The new level and the old one, read in the repository's folder with no git state to read (`cwd=None`)."""
        new = risk.command_level(self.rs, line, cwd=None)["level"]
        with mock.patch.object(Writes, "part", return_value=([], [])):
            return new, risk.command_level(self.rs, line, cwd=None)["level"]

    def test_no_level_goes_down_and_an_honest_redirection_changes_none(self):
        named = [c for c in escape_table.named_commands() if "\n" not in c and ">" not in c and "<" not in c][::45]
        self.assertGreater(len(named), 10)
        lower, changed, raised, read = [], [], 0, 0
        with contextlib.chdir(self.root):
            for command in named:
                for wrapper in ("{}", "sh -c {q}"):
                    for suffix in self.HONEST + self.PROTECTED_WRITES:
                        line = escape_table.wrapped(wrapper, command + suffix) if "{q}" in wrapper else command + suffix
                        new, old = self.levels(line)
                        read += 1
                        if RANK[new] < RANK[old]:
                            lower.append((line, new, old))
                        elif suffix in self.HONEST and new != old:
                            changed.append((line, new, old))
                        elif suffix in self.PROTECTED_WRITES and RANK[new] > RANK[old]:
                            raised += 1
        self.assertGreater(read, 100)
        self.assertEqual((lower, changed), ([], []))
        self.assertGreater(raised, 0)  # the table does reach the new control


class TheShellReaderMarksWhatItNeeds(unittest.TestCase):
    def test_a_pipe_after_a_greater_than_sign_is_one_redirection(self):
        self.assertEqual(shell.split("cat a >| out.log"), ["cat a >| out.log"])
        self.assertEqual(shell.split("cat a > b | cat"), ["cat a > b", "cat"])
        self.assertEqual(shell.split("echo \\>| cat"), ["echo \\>", "cat"])
        self.assertEqual(shell.split("echo '>'| cat"), ["echo '>'", "cat"])

    @reads_git_once
    def test_an_escape_before_an_operator_is_counted_as_the_word_reader_counts_it(self):
        """A backslash escapes the next character, so an even run leaves the operator real and an odd run escapes it. The line is
        one command when `shell_words` reads the operator as a redirection, and two when the `|` or `&` ends a command."""
        for operator in (">|", ">&", "<&"):
            for run in range(7):
                line = f"echo x {chr(92) * run}{operator} cat"
                real = run % 2 == 0
                with self.subTest(line=line):
                    self.assertEqual(operator in [str(w) for w, is_operator in shell.shell_words(line) if is_operator], real)
                    self.assertEqual(len(shell.split(line)), 1 if real else 2)
        self.assertEqual(shell.split("echo \\\\>| cat"), ["echo \\\\>| cat"])
        self.assertEqual(shell.split("echo \\\\\\>| cat"), ["echo \\\\\\>", "cat"])

    def test_a_pipe_after_an_even_run_of_backslashes_is_the_redirection_it_is_in_a_shell(self):
        self.assertEqual(shell.split("cat a \\\\>| out.log | wc"), ["cat a \\\\>| out.log", "wc"])
        self.assertEqual(shell.split("cat a \\\\\\>| wc"), ["cat a \\\\\\>", "wc"])
        self.assertEqual(shell.split("echo \\\\\\>& cat"), ["echo \\\\\\>", "cat"])  # the third backslash escapes the `>`
        self.assertEqual(shell.split("echo \\\\>& cat"), ["echo \\\\>& cat"])

    def test_an_escape_in_an_earlier_command_does_not_escape_a_later_operator(self):
        # The later command has the length that the earlier one had just after its escape, and a real operator at its end.
        self.assertEqual(shell.split("echo \\>;abcdef>| cat"), ["echo \\>", "abcdef>| cat"])
        self.assertEqual(shell.split("echo \\> &&abcdef>| cat"), ["echo \\>", "abcdef>| cat"])
        self.assertEqual(shell.split("echo \\>;abcdef<& 3"), ["echo \\>", "abcdef<& 3"])

    def test_a_word_says_whether_the_shell_expands_it(self):
        words = {w: w.expands for w, op in shell.shell_words("a $B \"$C\" '$D' \\$E `f` \"x\\$y\" *.g h? [i] '*' \"*\" a'$'b $(j)") if not op}
        self.assertEqual(
            [(str(w), e) for w, e in words.items()],
            [
                ("a", False),
                ("$B", True),
                ("$C", True),
                ("$D", False),
                ("$E", False),
                ("`f`", True),
                ("x$y", False),
                ("*.g", True),
                ("h?", True),
                ("[i]", True),
                ("*", False),
                ("a$b", False),
                ("$(j)", True),
            ],
        )


@unittest.skipUnless(shutil.which("git"), "git is required")
class TheCliAndTheMcpToolGiveOneAnswer(unittest.TestCase):
    def test_an_agent_that_asks_through_either_is_told_the_same(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            helpers.git(root, "init", "-q", "-b", "main")
            adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))
            for line, level in ((f"echo x >> {PROTECTED}", "ask"), ("echo x >> .aidd/tmp/roles/developer.log", "allow"), ("tee $LOG", "allow")):
                with self.subTest(line=line):
                    cli = json.loads(helpers.aidd_here("risk", "--command", line, "--json", cwd=root).stdout)
                    out = io.StringIO()
                    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "risk", "arguments": {"command": line}, "_meta": MCP_META}}
                    mcp_server.serve(io.StringIO(json.dumps(call) + "\n"), out, root=str(root))
                    result = json.loads(out.getvalue())["result"]
                    self.assertFalse(result["isError"])
                    self.assertEqual(json.loads(result["content"][0]["text"]), cli)
                    self.assertEqual(cli["level"], level)


if __name__ == "__main__":
    unittest.main()
