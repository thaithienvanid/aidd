"""What xargs, parallel, and find -exec run: a literal reader lets a writer the guard holds run the line, and every other
command they run is read with the words they fill in as names the guard cannot read.

tests/test_guard_oracle.py runs these forms under real bash for the write rules, and tests/test_guard_ref_oracle.py
under real git for the decision records, the base branch, and explore branches. This file pins the reading itself.
"""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd.guard import indirect_runs, shell_parser

READS = (
    "xargs wc -l",
    "xargs -0 grep -n x",
    "xargs -r -n 1 head -n 5",
    "xargs -0rn1 tail -n 2",
    "xargs --null --max-args=2 cat",
    "xargs --max-args 2 cat",
    "xargs -I{} basename {}",
    "xargs -i dirname {}",
    "xargs --replace=F ls -l F",
    "xargs -- stat",
    "xargs sort --",
    "xargs sort -r -k 2 --",
    "xargs file -b --",
    "/usr/bin/xargs cat",
    "find src -name app.py -exec grep -n x {} +",
    "find src -name app.py -exec grep -l x {} \\;",
    "find . -type f -execdir wc -l {} +",
    "find src -exec cat {} \\; -exec head -n1 {} \\;",
    "find src -type f -exec sort -r -- {} +",
    "find src -type f -exec file -b -- {} +",
    "xargs grep -n x *.py",  # a glob in a reader's words gives it only more files to read
    "xargs sort -- *.txt",
    "find . -path ./src/app.py -iname APP.PY -exec wc -l {} +",
)
OPAQUE = (
    # Not a reader, or a reader the input or find can make write or run a program.
    "xargs rm",
    "xargs sh -c 'echo y > x'",
    "xargs uniq",  # its second operand is a file it writes
    "xargs sort",  # the input could give `-o file` or `--compress-program=prog`
    "xargs sort -o out --",
    "xargs sort --out=x --",
    "xargs sort --compress-program=x --",
    "xargs sort -T . --",
    "xargs -I{} sort -- {}",  # under -I the input lands anywhere
    "xargs file -C --",
    "xargs file",
    "xargs git log",
    "xargs xargs cat",
    "xargs",  # echo
    # The name xargs runs is not exactly a reader's, or the input fills it in.
    "xargs ./cat",
    "xargs /bin/cat",
    "xargs CAT",
    "xargs -I ca cat x",
    "xargs -I '' cat",
    "xargs --replace=at cat",
    # Options, wrappers, and words the guard does not read.
    "xargs --process-slot-var=LD_PRELOAD cat",
    "xargs -Q cat",
    "xargs --arg cat",
    "xargs -n",
    "X=1 xargs cat",
    "env xargs cat",
    "command xargs cat",
    "./xargs cat",
    "xargs cat > out.txt",
    "xargs cat $HOME",
    "xargs cat `x`",
    "parallel cat ::: a b",
    # find: an action that writes or asks, a clause that is not a reader's, no end, or a name only find fills in.
    "find . -exec rm {} \\;",
    "find . -exec cat {} \\; -exec rm {} \\;",
    "find . -delete -exec cat {} +",
    "find . -fprint out -exec cat {} +",
    "find . -ok cat {} \\;",
    "find . -exec cat {}",
    "find . -exec \\;",
    "find . -exec {} \\;",
    "find . -exec sort {} \\;",
    "find . -exec sort {} -- \\;",
    "find . -exec sort -o {} -- {} \\;",
    "find -f -oops -exec sort -- {} +",
    "find . -files0-from list -exec sort -- {} +",
    "find . -execdir file -C -m x -- {} \\;",
    "find . -exec git update-ref refs/aidd/decisions HEAD \\;",
    "find $D -exec cat {} +",
    # A glob or a brace the shell may expand into an option or another program, since quotes are gone by now.
    "xargs -I * cat *",
    "xargs -n{1,2} cat",
    "xargs sort * --",
    "xargs sort {-ofoo,x} --",
    "find * -exec cat {} +",
    "find . -newer * -exec cat {} +",
    # The kin of xargs and find, and programs that run commands no reader exception covers.
    "busybox xargs cat",
    "gfind . -exec rm {} \\;",
    "bfs . -exec rm {} \\;",
    "gxargs rm",
    "fd -x cat",
    "sem cat x",
    "rush cat",
    "find . -name {a,-delete} -exec cat {} +",
)


def one(command: str) -> shell_parser.SimpleCommand:
    """The command's first simple command: a substitution in it (`` `x` ``) adds the commands it runs after it."""
    return shell_parser.simple_commands(command)[0]


class ReadersTests(unittest.TestCase):
    def test_literal_readers_are_read(self):
        self.assertEqual([c for c in READS if not indirect_runs.runs_only_readers(one(c))], [])

    def test_everything_else_stays_opaque(self):
        self.assertEqual([c for c in OPAQUE if indirect_runs.runs_only_readers(one(c))], [])
        for command in OPAQUE[-8:-1]:
            self.assertTrue(indirect_runs.runs_a_command(one(command)), command)

    def test_a_find_pattern_the_shell_expands_into_an_action_stays_opaque(self):
        """`find . -name * -exec cat {} +` with files named `*` and `-delete` in the folder is `-name '*' -delete`. An
        earlier command on the line can make those files (`touch -- -delete`), so the files on disk never decide. The
        reader keeps no quotes, so a quoted pattern counts too: the documented cost of failing closed."""
        for command in (
            "find . -name * -exec cat {} +",
            "find . -name {a,-delete} -exec cat {} +",
            "find . -name $P -exec cat {} +",
            "find . -name '*' -exec cat {} +",
            'find . -name "*.py" -exec cat {} +',
        ):
            sc = one(command)
            self.assertFalse(indirect_runs.runs_only_readers(sc), command)
            self.assertTrue(indirect_runs.find_glob_injects(sc.argv[1:]), command)
        self.assertTrue(indirect_runs.runs_only_readers(one("find . -name app.py -exec cat {} +")))
        (sc,) = [c for c in shell_parser.simple_commands("touch -- -delete; find . -name * -exec cat {} +") if c.argv[0] == "find"]
        self.assertFalse(indirect_runs.runs_only_readers(sc))


class IndirectCommandsTests(unittest.TestCase):
    def argvs(self, command: str) -> list[list[str]]:
        return [sc.argv for sc in indirect_runs.indirect_commands(one(command))]

    def test_xargs_input_is_a_word_the_guard_cannot_read(self):
        i = indirect_runs.INPUT
        self.assertEqual(self.argvs("xargs git update-ref"), [["git", "update-ref", i]])
        self.assertEqual(self.argvs("xargs -I R git update-ref R HEAD"), [["git", "update-ref", i, "HEAD"]])
        self.assertEqual(self.argvs("xargs -I R git update-ref refs/aidd/approvalR HEAD"), [["git", "update-ref", f"refs/aidd/approval{i}", "HEAD"]])
        self.assertEqual(self.argvs("xargs git"), [["git", i]])
        self.assertEqual(self.argvs("xargs -n1 -- git checkout"), [["git", "checkout", i]])

    def test_options_it_cannot_read_and_parallel_give_every_command_the_line_could_run(self):
        i = indirect_runs.INPUT
        self.assertEqual(self.argvs("xargs --process-slot-var=X git update-ref"), [["git", "update-ref", i], ["update-ref", i]])
        self.assertEqual(self.argvs("parallel git checkout ::: explore/x"), [["git", "checkout", i], ["checkout", i]])
        # `{}` starts no command here: `gh` and `pr` come before it, and `pr` follows no option, so it is not a value.
        self.assertEqual(self.argvs("parallel -j2 gh pr merge {} ::: 1 2"), [["gh", "pr", "merge", i, i], ["pr", "merge", i, i], ["merge", i, i]])
        self.assertEqual(
            self.argvs("parallel -j 2 {} pr merge 3"),
            [["2", i, "pr", "merge", "3", i], [i, "pr", "merge", "3", i], ["pr", "merge", "3", i], ["merge", "3", i], ["3", i]],
        )
        self.assertEqual(self.argvs("parallel ::: 'gh pr merge 3'"), [[i]], "with no command, each input is the command")
        self.assertEqual(self.argvs("sem gh pr merge"), [["gh", "pr", "merge", i], ["pr", "merge", i], ["merge", i]])
        self.assertEqual(len(self.argvs("parallel " + "x " * 40)), 12, "the starts are bounded")
        # Past the bound, the rest is git with a subcommand the guard cannot read, which the git checks deny.
        many = self.argvs("parallel " * 30 + "x")
        self.assertLess(len(many), 60)
        self.assertEqual(many[-1], ["git", i])

    def test_find_fills_in_its_paths_and_execdir_runs_git_elsewhere(self):
        i = indirect_runs.INPUT
        self.assertEqual(self.argvs("find . -exec git rm {} \\;"), [["git", "rm", i]])
        self.assertEqual(self.argvs("find . -execdir git push origin main \\;"), [["git", "-C", i, "push", "origin", "main"]])
        self.assertEqual(self.argvs("find . -ok git switch x \\; -okdir cat {} +"), [["git", "switch", "x"], ["cat", i]])
        self.assertEqual(self.argvs("find . -exec git checkout x"), [["git", "checkout", "x"]])  # no end: the rest

    def test_a_shell_it_runs_is_followed_and_nesting_is_bounded(self):
        i = indirect_runs.INPUT
        found = self.argvs("xargs sh -c 'git update-ref refs/aidd/x HEAD'")
        self.assertIn(["git", "update-ref", "refs/aidd/x", "HEAD"], found)
        deep = self.argvs("xargs xargs xargs xargs xargs git update-ref")
        self.assertEqual(deep[-1], ["git", i])
        self.assertEqual(len(deep), 4)

    def test_the_kin_of_xargs_and_find_are_read_the_same_way(self):
        i = indirect_runs.INPUT
        self.assertEqual(self.argvs("gfind . -exec git rm {} \\;"), [["git", "rm", i]])
        self.assertEqual(self.argvs("bfs . -execdir git push \\;"), [["git", "-C", i, "push"]])
        self.assertEqual(self.argvs("busybox xargs git checkout"), [["git", "checkout", i]])
        self.assertEqual(self.argvs("gxargs -I B git switch B"), [["git", "switch", i]])
        self.assertEqual(self.argvs("fd -e py -x git rm {} \\; -X cat"), [["git", "rm", i], ["cat", i]])
        self.assertEqual(self.argvs("fdfind --exec-batch=git add"), [["git", "add", i]])

    def test_a_program_only_the_input_names_is_opaque(self):
        opaque = indirect_runs.opaque_program
        for argv in (["$X", "pr"], ["${X}"], [i := indirect_runs.INPUT, "pr"], ["$(echo gh)"], ["g?"], ["g{h,x}"], ["sh", i], ["bash", "-o", i]):
            self.assertTrue(opaque(argv), argv)
        for argv in (["$VENV/bin/python", "-m", "x"], ["[", "-f", "x", "]"], ["[["], ["sh", "script.sh", i], ["bash", "-c", "echo", i], []):
            self.assertFalse(opaque(argv), argv)
        self.assertEqual(indirect_runs.first_opaque_program("git commit -F - <<'EOF'\n`x` works\nEOF"), None, "a message is not a command")
        self.assertEqual(indirect_runs.first_opaque_program("bash <<'EOF'\n$X pr merge\nEOF"), "$X", "a shell's here-document is")

    def test_named_runs_read_the_rest_of_the_line_from_each_named_program(self):
        def named(command: str) -> list[list[str]]:
            return [sc.argv for sc in indirect_runs.named_runs(one(command))]

        self.assertEqual(named("ssh host gh pr merge 3"), [["gh", "pr", "merge", "3"]])
        self.assertEqual(named("docker exec c git checkout x"), [["git", "checkout", "x"]])
        self.assertEqual(named("grep -r 'gh pr merge' docs/"), [])
        self.assertEqual(named("echo git push"), [])
        self.assertEqual(named("brew install tmux git"), [["git"]], "tmux with a command it lacks runs nothing")
        self.assertEqual(len(named("x " + "gh " * 20)), 8, "bounded")

    def test_other_commands_run_nothing(self):
        for command in ("git ls-files", "find . -name x -print", "grep -r xargs .", "echo find -exec rm"):
            self.assertEqual(self.argvs(command), [], command)


if __name__ == "__main__":
    unittest.main()
