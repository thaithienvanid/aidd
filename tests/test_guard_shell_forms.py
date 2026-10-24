"""Shell forms that reach a protected outcome once bash reads them, from the security review of 8fee7418..16b63746:
words the shell joins, splits, or runs later (a line continuation, a comment, a substitution, a here-string, `trap`,
`env -S`), branch names in another case or only the shell resolves, config keys that name a program, a clustered `gh pr review -a`, writes through a
folder or a link, replace refs and history rewriters, and a looser `agents.delegate`. Each one is denied for the main
session and for a role, and the plain forms around it stay allowed."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from helpers import git, make_repo

from aidd.guard import command_check, decision_files, git_commands, ref_writes, shell_parser, shell_words, write_targets

MAIN = {"tool_name": "Bash"}
ROLE = {"tool_name": "Bash", "agent_type": "aidd-team:developer"}

DENIED = {
    "a comment ends at its line, and `#` inside a word starts none": (
        "true # x\ngh pr merge 3",
        "echo a#b; gh pr merge 3",
        "echo a#b; aidd land",
        "echo a#b; git branch -f main HEAD~1",
        "echo a#b; echo x > .aidd/config.yaml",
    ),
    "a brace or a glob may name the base branch or an explore branch": (
        "git branch -f {main,HEAD~1}",
        "git branch -f ma[i]n HEAD~1",
        "git branch {-f,main} HEAD~1",
        "git branch -[f] main HEAD~1",
        "git checkout -b {explore/x,feat}",
        "git switch -c explor[e]/x",
    ),
    "a branch name in another case is the same branch on a case-insensitive disk": (
        "git branch -f MAIN HEAD~1",
        "git branch -D Main",
        "git update-ref refs/heads/MAIN HEAD~1",
        "git switch MAIN && git reset --hard HEAD~1",
        "git push --force origin MAIN",
        "git push origin --delete MAIN",
        "git switch EXPLORE/x",
    ),
    "a line continuation joins the words bash runs": (
        "gh pr mer\\\nge 3",
        "aidd la\\\nnd",
        "git branch -f ma\\\nin HEAD~1",
        "git switch expl\\\nore/x",
        "echo x > .gi\\\nt/HEAD",
    ),
    "a substitution anywhere runs its command": (
        "echo `gh pr merge 3`",
        'echo "$(gh pr merge 3)"',
        'git commit -m "`aidd land`"',
        'echo "$(echo "$(gh pr merge 3)")"',
        "cat > notes.txt <<EOF\n`gh pr merge 3`\nEOF",
    ),
    "code a shell runs later, or env splits from one word": (
        "bash <<< 'gh pr merge 3'",
        "trap 'gh pr merge 3' EXIT",
        "trap -- 'aidd land' INT",
        "env -S 'gh pr merge 3'",
        "env -iS 'gh pr merge 3'",
        "env -S'gh pr merge 3'",
        "env --split-string='aidd land'",
        "env --split='aidd land'",
        "env -S 'gh\\_pr\\_merge\\_3'",
    ),
    "a clustered short option may approve": ("gh pr review 3 -ab LGTM", "gh pr review 3 -aF body.txt", "gh pr review 3 -ca"),
    "a write through a folder or a link the reader must follow": (
        "D=.aidd; cd $D && echo x > config.yaml",
        'cd "$(echo .aidd)" && echo x > config.yaml',
        "echo x 1<>.aidd/config.yaml",
        "echo 'ref: refs/heads/explore/x' > g/HEAD",
        "ln -s .git g2 && echo 'ref: refs/heads/explore/x' > g2/HEAD",
        "ln -s .aidd a && echo x > a/config.yaml",
        'ln -s "$X" q && echo x > q/HEAD',
        "cd \"$(echo .git)\" && echo 'ref: refs/heads/explore/x' > HEAD",
    ),
    "replace refs, history rewriters, and the hooks folder": (
        "git replace HEAD HEAD~1",
        "git update-ref refs/replace/0123abcd HEAD",
        "git push . HEAD:refs/replace/0123abcd",
        "git filter-branch -f -- main",
        "git filter-branch -f --msg-filter cat main",
        "git filter-repo --force",
        "git filter-repo --refs main --force",
        "git config core.hooksPath .hooks",
    ),
    "a config key that names a program git runs when a person runs git": (
        "git config core.fsmonitor ./x.sh",
        "git config core.editor ./x.sh",
        "git config core.pager ./x.sh",
        "git config filter.lfs.clean ./x.sh",
        "git config merge.ours.driver ./x.sh",
        "git config diff.external ./x.sh",
        "git config credential.helper ./x.sh",
        "git config alias.p '!gh pr merge 3'",
        "git config --rename-section feat filter.x",
        "git config --rename-sec feat filter.x",
        "git config --frob x y",
        "git config hook.x.command ./x.sh",
        "git config protocol.ext.allow always",
        "git config submodule.s.update '!./x.sh'",
        "git config core.alternateRefsCommand ./x.sh",
        "git config url.ext::x.insteadOf https://",
        "git config trailer.x.command ./x.sh",
        "git config imap.tunnel ./x.sh",
    ),
    "a glob that starts a word, a symbolic copy, and a merge option before a branch": (
        "git branch * main",
        "git branch ?x main",
        "git branch --sort -l * main",
        "git branch -u -l * main",
        "git branch -vu -l * main",
        "ln -S -s .git/config c && echo x > c",
        "cp -S -l .git/config c && echo x > c",
        "cp -s .git/HEAD h && echo x > h",
        "cp --sym .git/HEAD h && echo x > h",
        "cp --li .git/config c && echo x > c",
        "git switch -m $B",
    ),
    "env's and trap's options, read as they read them": (
        "env -iu X -S 'gh pr merge 3'",
        "env -iu X gh pr merge 3",
        "env --un X -S 'gh pr merge 3'",
        "env -C . -S 'aidd land'",
        "env --frob gh pr merge 3",
        "trap -- '-x; gh pr merge 3' EXIT",
        "trap -p -- 'aidd land' INT",
    ),
    "code from a pipe or a stream, a clustered reset, and a git file the shell builds": (
        "printf '%s\\n' 'gh pr merge 3' | bash",
        "echo gh pr merge 3 | sh",
        "printf 'gh pr merge %s\\n' 3 | bash",
        "source /dev/stdin <<< 'gh pr merge 3'",
        "source /dev/stdin",
        ". <(echo hi)",
        "git checkout -qB main HEAD~1",
        "git switch -qC main HEAD~1",
        'echo x > "$(echo .git)/HEAD"',
        "echo x > $'.git/HEAD'",
        'echo x > "$f.git/HEAD"',
        'echo x > "$D/refs/heads/main"',
        "printf 'gh pr mer\\x67e 3\\n' | bash",
        "echo -e 'gh pr mer\\x67e 3' | bash",
        "printf '%b\\n' 'gh pr merge 3' | bash",
        "echo 'gh pr merge 3' | cat | bash",
        "echo 'gh pr merge 3' 2>/dev/null | bash",
        "printf '%.15s\\n' 'gh pr merge 3 xx' | bash",
        "printf '%c%s\\n' g 'h pr merge 3' | bash",
        "printf -- 'gh pr merge 3\\n' | bash",
        "printf 'gh pr merge %%s\\n' 3 | bash",
        "bash <(echo gh pr merge 3)",
        "bash /dev/stdin <<< 'gh pr merge 3'",
        "sh /dev/fd/0",
        "bash /dev/fd/3 <<< 'gh pr merge 3'",
        "bash - <<< 'gh pr merge 3'",
        "echo 'gh pr merge 3' | bash -",
        "gh alias set m 'pr merge'",
        "gh extension install owner/gh-x",
        "glab alias set m 'mr merge'",
        "echo '[core]' >> ~/.gitconfig",
        "echo x >> $HOME/.config/git/config",
        "echo x > ~/.config/gh/config.yml",
        "echo x > ~/.config/glab-cli/aliases.yml",
        "echo x > ~/.local/share/gh/extensions/gh-x/gh-x",
        "echo x > ~/.config/git/attributes",
        "git switch --force-create main HEAD~1",
        "git switch --force-cr main HEAD~1",
        'echo x > "$D/REFS/heads/main"',
        'echo x > "$D/HEA?"',
    ),
    "a plain value the line set, then changed, and a loop the guard does not write out": (
        'f=x; read -r f < list; echo y > "$f"',
        'f=x; f+=.aidd/config.yaml; echo y > "$f"',
        'f=a; f=$(printf .aidd/config.yaml); echo y > "$f"',
        "T=$(mktemp); read T < list; echo y > $T",
        "T=$(mktemp); T=.aidd/config.yaml; echo y > $T",
        'T=$(mktemp); printf -v T %s .aidd/config.yaml; echo y > "$T"',
        'for f in a .aidd/config.yaml; do echo y > "$f"; done',
        'for f in a; do f=.aidd/config.yaml; echo y > "$f"; done',
        'for f in a; do echo y > "${f:-.aidd/config.yaml}"; done',
        "for f in a; do echo y > $f; done",
        'for f in config.yaml; do cd .aidd && echo y > "$f"; done',
        "find . -name '*.yaml' -delete",
        "find . -name $'*.pyc' -delete",
        "gh pr review 3 -b -- --approve",
        "gh pr review 3 -bR --approve",
        'gh pr review 3 -c"$X"',
        'git restore --staged "$f" .aidd/config.yaml',
    ),
    "a gh or glab verb that changes an alias, an extension, or the config, read as an allowlist": (
        "gh alias delete co",
        "gh -R o/r alias set m 'pr merge'",
        "gh alias import aliases.yml",
        "gh extension remove gh-x",
        "gh ext upgrade --all",
        "gh extensions create gh-y",
        "gh config set editor ./x.sh",
        "gh config set -h github.com git_protocol ssh",
        "gh config clear-cache",
        "glab config set editor ./x.sh",
        "glab config edit",
        "glab alias delete m",
        "gh alias $V m 'pr merge'",
        "gh --host h config set editor ./x.sh",
        "gh --hostname h alias set m 'pr merge'",
        "gh -R o/r config set editor ./x.sh",
        "gh --repo=o/r alias set m 'pr merge'",
        "gh config --host h set editor ./x.sh",
        "gh -s x ext install owner/gh-x",
        "GH_EDITOR=./x.sh gh issue edit 3",
        "GH_PAGER='sh -c x' gh pr view 3",
        "env GH_BROWSER=./x.sh gh pr view 3 --web",
        "BROWSER=./x.sh glab mr view 3 --web",
        "EDITOR=./x.sh glab issue update 3",
        "VISUAL=$X gh issue edit 3",
        "export GH_EDITOR=./x.sh; gh issue edit 3",
        "declare -x GH_PAGER=./x.sh && gh pr view 3",
        "typeset -x GLAB_EDITOR=./x.sh; glab issue update 3",
        "set -a; EDITOR=./x.sh; gh issue edit 3",
        "GH_PAGER=./x.sh; gh pr view 3",
        "read GH_EDITOR < f; export GH_EDITOR; gh issue edit 3",
        "printf -v GH_EDITOR ./x.sh; gh issue edit 3",
        ': "${GH_EDITOR:=./x.sh}"; gh issue edit 3',
        "GIT_EDITOR=./x.sh gh pr checkout 3",
        "GIT_PAGER=./x.sh gh pr view 3",
        "GLAB_BROWSER=./x.sh glab mr view 3 --web",
        "LESSOPEN='|./x.sh %s' gh pr view 3",
        "LESSCLOSE=./x.sh gh pr view 3",
        "GH_PAGER=less LESS='+!./x.sh' gh pr view 3",
        "GH_EDITOR=vim gh issue edit 3",
        "GH_EDITOR='vim -c !./x.sh' gh issue edit 3",
        "GH_PAGER='less -R' gh pr view 3",
        "GH_PAGER=less gh pr diff 3",
        "GH_PAGER= gh pr view 3",
        "export GH_PAGER=cat && gh pr view 3",
        "X=1 gh pr view 3",
        "A[0]+=x; gh pr view 3",
        "GH_REPO=$R gh pr view 3",
        "declare -n r=GH_EDITOR; r=./x.sh; gh issue edit 3",
        "local X=1; gh pr view 3",
        "readonly X=1; gh pr view 3",
        "mapfile -t GH_EDITOR < f; gh issue edit 3",
        "GIT_SSH_COMMAND=./x.sh gh repo clone o/r",
        "GIT_ASKPASS=./x.sh gh pr checkout 3",
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.pager GIT_CONFIG_VALUE_0=./x.sh gh pr checkout 3",
        "GIT_EXEC_PATH=/tmp/x gh pr checkout 3",
        "eval true; gh pr view 3",
        "source x.sh; gh pr view 3",
        ". ./x.sh && gh pr view 3",
        "bash -c 'GH_EDITOR=./x.sh gh issue edit 3'",
        "sudo GH_EDITOR=./x.sh gh issue edit 3",
        "printf '3\\n' | GH_EDITOR=./x.sh xargs gh issue edit",
        "for GH_EDITOR in ./x.sh; do gh issue edit 3; done",
        "for e in ./x.sh; do gh issue edit 3; done",
        "select GH_EDITOR in ./x.sh; do gh issue edit 3; break; done",
        "while read -r GH_EDITOR; do gh issue edit 3; done < f",
        "until false; do gh pr view 3; break; done",
        "coproc gh pr view 3",
        "unset GH_PAGER; gh pr view 3",
        "readarray -t GH_EDITOR < f; gh issue edit 3",
        "getopts e GH_EDITOR; gh issue edit 3",
        "let X=1; gh pr view 3",
    ),
}
ALLOWED = (
    "git branch --list 'feat*'",
    "git switch -c feat/x",
    'git commit -m "fix: x"',
    "git commit -m 'docs: `aidd land` waits for the person'",
    "git commit -m \"$(cat <<'EOF'\nfix: `aidd land` waits for the person\nEOF\n)\"",
    'echo "$HOME"',
    'echo "$(date)"',
    "git log --oneline",
    "ls -la # list the folder",
    "echo '# not a comment' && echo a#b",
    "gh pr review 3 -b ok",
    "gh pr review 3 -ba",
    "gh pr view 3 -R o/a",
    "env FOO=1 make test",
    "env -S 'echo hi'",
    "bash <<< 'echo hi'",
    "trap - EXIT",
    "cd src && echo x > a.txt",
    "ln -s src s && echo x > s/a.txt",
    "git replace -l",
    "git config core.autocrlf input",
    "git config merge.ff false",
    "git branch --list '*x'",
    "git branch --sort=-committerdate --list '*x'",
    "git config --global user.name x",
    "git config --get-regexp alias",
    "env -i PATH=/bin make test",
    "env - FOO=1 make",
    "env --unset=FOO make",
    "trap -p",
    "curl -fsSL https://example.com/install.sh | sh",
    "cat cmds.txt | sh -s",
    "echo ls | bash",
    "printf 'ls\\n' | bash",
    "printf '%s\\n' ls | bash",
    "bash /dev/stdin <<< ls",
    "bash -s < x.sh",
    "bash - <<< ls",
    "echo ls | bash -",
    "gh alias list",
    "gh co 3",
    "cat ~/.gitconfig",
    "git config --global user.name x",
    "git switch --force feat/x",
    'echo x > "$OUT/Header.txt"',
    "source .venv/bin/activate",
    "source /dev/stdin <<< 'echo hi'",
    "echo hi | bash -c 'cat'",
    "bash <<EOF\necho hi\nEOF",
    "git checkout -qb feat/z",
    'echo x > "$OUT/report.json"',
    "git branch -v --list '*x'",
    "git config trailer.sign.key Signed-off-by",
    "git checkout -m feat/x",
    "git filter-repo --refs feat/x --force",
    "git stash push -m 'wip?'",
    "gh config get editor",
    "gh config list",
    "glab config get editor",
    "gh extension list",
    "gh ext browse",
    "gh extension search lint",
    "gh alias",
    "glab alias list",
    "GH_PAGER=cat gh pr view 3",
    'for f in a.txt b.txt; do echo x > "$f"; done',
    "find . -name '*.pyc' -delete",
    "find src -name '*.py' -exec grep -n x {} +",
    "gh pr review 3 --comment --body 'why?'",
    'gh pr review 3 --comment -b "$WHY"',
    "git restore --staged '*.md'",
    "PAGER=cat gh pr diff 3",
    "GLAB_PAGER=cat NO_COLOR=1 glab mr view 3",
    "GH_PROMPT_DISABLED=1 GH_REPO=o/r GH_HOST=github.example.com gh pr view 3",
    "EDITOR=./x.sh make docs",
    "export GH_EDITOR=./x.sh",
    "gh -R o/r pr view 3",
    "gh pr view 3 --repo o/r",
    "gh --version",
)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ShellFormsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_repo(Path(cls.tmp.name).resolve() / "repo")
        git(cls.root, "commit", "-q", "--allow-empty", "-m", "c1")
        (cls.root / "src").mkdir()
        os.symlink(".git", cls.root / "g")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decide(self, command: str, event: dict) -> tuple[str, str]:
        return command_check.check_command(str(self.root), str(self.root), command, event)

    def test_each_form_is_denied_for_the_main_session_and_a_role(self):
        for what, commands in DENIED.items():
            for command in commands:
                for event in (MAIN, ROLE):
                    with self.subTest(what, command=command, role=bool(event.get("agent_type"))):
                        decision, why = self.decide(command, event)
                        self.assertEqual(decision, "deny", why)

    def test_the_plain_forms_around_them_stay_allowed(self):
        for command in ALLOWED:
            with self.subTest(command=command):
                decision, why = self.decide(command, MAIN)
                self.assertEqual(decision, "allow", why)

    def test_a_denial_names_why_and_what_to_do(self):
        for command, words in (
            ("git replace HEAD HEAD~1", ("replace ref", "Leave the objects")),
            ("git config core.hooksPath .hooks", ("core.hooksPath", "a person's settings", "run the program you need yourself")),
            ("D=.aidd; cd $D && echo x > config.yaml", (".aidd/config.yaml", "name the files literally")),
            ('cd "$(echo .git)" && echo x > HEAD', ("git directory", "run the git or aidd command")),
            ("ln -s .git g2 && echo x > g2/HEAD", ("inside the git directory", "Run the git or aidd command")),
        ):
            with self.subTest(command=command):
                _, why = self.decide(command, MAIN)
                for word in words:
                    self.assertIn(word, why)


@unittest.skipUnless(shutil.which("git"), "git is required")
class HereDocumentFolderTests(unittest.TestCase):
    def test_a_cd_in_a_here_documents_text_never_moves_where_git_runs(self):
        """A body is a file's text: its `cd` line leaves git where it is, on the base branch."""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", branch=None)
            git(root, "commit", "-q", "--allow-empty", "-m", "c1")
            other = make_repo(Path(tmp).resolve() / "other")
            command = f"cat > notes.md <<'EOF'\ncd {other}\nEOF\ngit reset --hard HEAD~1"
            decision, why = command_check.check_command(str(root), str(root), command, MAIN)
            self.assertEqual(decision, "deny", why)


@unittest.skipUnless(shutil.which("git"), "git is required")
class OddRepositoryPathTests(unittest.TestCase):
    """A repository whose own path holds a shell character (iCloud's `com~apple~CloudDocs`, a `[`) is no folder only the
    shell names: a plain write there is judged as written."""

    def test_a_plain_write_stays_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "com~apple~Docs [x]" / "repo")
            for command in ("echo x > config", "echo x > settings.json", "cd src && echo x > HEAD"):
                with self.subTest(command=command):
                    (root / "src").mkdir(exist_ok=True)
                    decision, why = command_check.check_command(str(root), str(root), command, MAIN)
                    self.assertEqual(decision, "allow", why)


class ShellReadingTests(unittest.TestCase):
    """The reader joins, splits, and keeps what bash does."""

    def argvs(self, command: str) -> list[list[str]]:
        return [sc.argv for sc in shell_parser.simple_commands(command)]

    def test_continuations_and_comments_read_as_bash_reads_them(self):
        for command, expected in (
            ("gh pr mer\\\nge 3", [["gh", "pr", "merge", "3"]]),
            ('echo "a\\\nb"', [["echo", "ab"]]),
            ("echo a\\\n#b; gh x", [["echo", "a#b"], ["gh", "x"]]),
            ("echo \\\n#b; gh x", [["echo"]]),
            ("echo ${#x} $# # a comment", [["echo", "${#x}", "$#"]]),
            ("echo $'it\\'s' # x\ngh y", [["echo", "it's"], ["gh", "y"]]),
        ):
            with self.subTest(command=command):
                self.assertEqual(self.argvs(command), expected)

    def test_a_single_quote_keeps_a_continuation_and_a_substitution_as_text(self):
        self.assertEqual(self.argvs("echo 'a`gh`$(gh)'"), [["echo", "a`gh`$(gh)"]])

    def test_a_read_write_redirect_writes_and_a_here_string_is_kept(self):
        (sc,) = shell_parser.simple_commands("cat 1<>f.txt")
        self.assertEqual((sc.out, sc.inp), (["f.txt"], ["f.txt"]))
        first = shell_parser.simple_commands("bash <<< 'gh pr merge 3'")[0]
        self.assertEqual(first.strings, ["gh pr merge 3"])

    def test_a_substitution_runs_in_a_folder_the_guard_does_not_know(self):
        found = self.argvs('echo "$(gh pr merge 3)"')
        self.assertEqual(found[1:], [["cd", "$(...)"], ["gh", "pr", "merge", "3"]])

    def test_a_substitution_with_no_end_cannot_be_read(self):
        broken: list[str] = []
        shell_parser.simple_commands('echo "`gh pr merge 3"', broken=broken)
        self.assertTrue(broken)

    def test_a_here_document_with_no_delimiter_stays_commands(self):
        stripped, _ = shell_parser.split_heredocs("cat <<'EOF'\ngh pr merge 3")
        self.assertIn("gh pr merge 3", stripped)


class QuotingTests(unittest.TestCase):
    """The reader keeps each word's quoting (shell_words), and reads the same words shlex does."""

    def words(self, command: str) -> list[str]:
        return [w for sc in shell_parser.simple_commands(command, quoting=True) for w in sc.argv]

    def test_quoting_says_what_bash_may_split_and_what_it_passes_as_written(self):
        for command, splits, literal in (
            ("x '*.py'", False, True),
            ('x "*.py"', False, True),
            ("x \\*.py", False, True),
            ("x *.py", True, False),
            ("x '*'.py*", True, False),
            ('x "$f"', False, False),
            ("x $f", True, False),
            ("x $'*'", True, False),
            ('x "a b"', False, True),
            ("x ~/a", True, False),
            ("x '{a,b}'", False, True),
        ):
            with self.subTest(command=command):
                word = self.words(command)[1]
                self.assertEqual((shell_words.may_split(word), shell_words.literal(word)), (splits, literal))

    def test_a_word_with_no_quoting_known_fails_closed(self):
        for word in ("*.py", "$f", "a{b,c}"):
            self.assertEqual((shell_words.may_split(word), shell_words.literal(word)), (True, False))
        inner = shell_parser.simple_commands("bash -c \"find . -name '*.py' -delete\"", quoting=True)[-1]
        self.assertTrue(shell_words.may_split(inner.argv[3]), "a child shell's words keep no quoting")

    def test_the_quoted_reading_matches_shlex_on_random_lines(self):
        import random
        import shlex

        rng = random.Random(66)
        alphabet = "ab *?$`'\"\\;|&()<>{}~-=\n\t"
        for _ in range(3000):
            text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 24)))
            lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()<>")
            lex.whitespace_split, lex.commenters = True, ""
            try:
                expected = list(lex)
            except ValueError:
                expected = None
            found = shell_words.quoted_tokens(text)
            self.assertEqual(None if found is None else [t for t, _ in found], expected, repr(text))

    def test_a_loop_over_literal_words_is_written_out_once_for_each(self):
        argvs = [sc.argv for sc in shell_parser.simple_commands('for f in a "b c"; do git add "$f"; done', quoting=True)]
        self.assertEqual(argvs, [["git", "add", "a"], ["git", "add", "b c"]])
        for command in (
            'for f in a; do f=b; git add "$f"; done',
            'for f in $X; do git add "$f"; done',
            "for f in a; do git add $f; done",
            'for F in a; do git add "$F"; done',
            'for _ in a; do git add "$_"; done',
            'for _f in a; do git add "$_f"; done',
            'for IFS in a; do git add "$IFS"; done',
            'for path in a; do git add "$path"; done',
            'for f in a; do git add "$f$g"; done',
            '(for f in a; do git add "$f"; done)',
            'for f in a; do git add "$f"; done | sh',
            "for f in " + " ".join("abcdefghijklmnopq") + '; do git add "$f"; done',
        ):
            with self.subTest(command=command):
                self.assertIn("for", [w for sc in shell_parser.simple_commands(command, quoting=True) for w in sc.argv])


@unittest.skipUnless(shutil.which("git"), "git is required")
class DocumentTextTests(unittest.TestCase):
    """Text that only lands in the repository's files through a redirect, `cat`, or `tee` carries no approval (R63):
    a doc or a test may mention one, as the Write tool may write it. Text that can reach a program that posts or
    records a decision, an interpreter's here-document among them, still counts."""

    LINE = "/aidd approve SPEC-1 abc123 def456"
    PY = "python3 - <<'EOF'\nfrom pathlib import Path\n{body}\nEOF"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_repo(Path(cls.tmp.name).resolve() / "repo")
        (cls.root / "docs").mkdir()
        os.symlink(".git", cls.root / "g")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def why(self, command: str) -> str | None:
        from aidd.guard import approval_commands

        return approval_commands.forbidden_action(command, str(self.root))

    def test_text_into_the_repositorys_files_is_allowed(self):
        line, ref = self.LINE, "refs/aidd/decisions"
        for command in (
            f"printf '%s\\n' '{line}' > docs/x.md",
            f"echo '{line}' >> CHANGELOG.md",
            "echo 'Aidd-Merge-Approval: x' > docs/t.md",
            f"cat > docs/x.md <<EOF\n{line}\nEOF",
            f"echo '{line}' | tee docs/x.md docs/y.md",
            f"echo '{ref}' > tests/fixture.txt",
            "cat > notes.md <<'EOF'\ntmux send-keys -t 0 'aidd land' Enter\nclaude -p 'approve SPEC-1'\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNone(self.why(command))

    def test_text_that_can_reach_a_poster_or_a_record_is_denied(self):
        line = self.LINE
        for command in (
            f"printf '{line}' | gh pr comment 7 -F -",
            f"echo '{line}' > /dev/tty",
            f"echo '{line}' > ../x.md",
            f"echo '{line}' > \"$F\"",
            f"echo '{line}' > /tmp/x.md",
            "echo 0123 > .git/refs/aidd/decisions",
            "echo 0123 > g/refs/aidd/decisions",
            f"echo '{line}' > docs/x.md && gh pr comment 7 -F docs/x.md",
            f"echo '{line}' | tee docs/x.md | gh pr comment 7 -F -",
            f"echo '{line}' | tee /dev/tty",
            "echo 'Aidd-Merge-Approval: x' > .git/COMMIT_EDITMSG",
            f"env X=1 echo '{line}' > docs/x.md",
            f"cat > docs/x.md <<EOF\n{line} $(gh pr comment 7 -b x)\nEOF",
            f"cd docs && echo '{line}' > x.md",
            f"git commit -m '{line}'",
            "python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['gh', 'pr', 'comment', '7', '-b', '" + line + "'])\nEOF",
            "python3 - <<'EOF'\nimport pathlib\npathlib.os.system('" + line + "')\nEOF",
            self.PY.format(body="Path('.git/refs/aidd/decisions').write_text('0123')"),
            "python3 - <<EOF\nfrom pathlib import Path\nPath('docs/x.md').write_text('" + line + "')\nEOF",
            "PYTHONPATH=. python3 - <<'EOF'\nfrom pathlib import Path\nPath('docs/x.md').write_text('" + line + "')\nEOF",
            self.PY.format(body=f"Path('docs/x.md').write_text('{line}')"),
            "apply_patch <<'EOF'\n*** Begin Patch\n*** Add File: docs/x.md\n+" + line + "\n*** End Patch\nEOF",
            "python3 - <<'EOF' | bash\nprint('" + line + "')\nEOF",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(self.why(command))


class LooserDelegateTests(unittest.TestCase):
    """`agents.delegate` only tightens: never < auto < always, as the config package orders it."""

    def loosens(self, old: str, new: str) -> str | None:
        return decision_files.config_loosening(".aidd/config.yaml", old, new)

    def test_a_looser_delegate_is_denied(self):
        for was, now in (("always", "never"), ("always", "auto"), ("auto", "never")):
            with self.subTest(was=was, now=now):
                why = self.loosens(f"profile: team\nagents:\n  delegate: {was}\n", f"profile: team\nagents:\n  delegate: {now}\n")
                self.assertIn("agents.delegate", why or "")

    def test_dropping_the_key_is_judged_by_the_profile_default(self):
        self.assertIsNotNone(self.loosens("profile: team\nagents:\n  delegate: always\n", "profile: team\n"))
        self.assertIsNone(self.loosens("profile: audited\nagents:\n  delegate: always\n", "profile: audited\n"))

    def test_a_stricter_delegate_is_allowed(self):
        self.assertIsNone(self.loosens("profile: team\nagents:\n  delegate: never\n", "profile: team\nagents:\n  delegate: always\n"))


class LinearReadingTests(unittest.TestCase):
    def test_a_long_unclosed_brace_reads_in_one_pass_and_counts(self):
        word = "{" + "," * 50_000
        start = time.perf_counter()
        self.assertTrue(git_commands._SHELL_WORD.search(word) and git_commands._BRACES.search(word) and write_targets._BRACES.search(word))
        self.assertLess(time.perf_counter() - start, 0.2)


class HooksPathTests(unittest.TestCase):
    def test_setting_or_removing_the_hooks_folder_is_denied(self):
        for rest in (["core.hooksPath", "x"], ["--unset", "core.hooksPath"], ["--global", "core.hookspath", "x"], ["--remove-section", "core"]):
            with self.subTest(rest=rest):
                self.assertIn("names a program git runs", ref_writes.signing_config_denial(rest) or "")

    def test_reading_it_or_another_core_key_stays_allowed(self):
        for rest in (["--get", "core.hooksPath"], ["core.autocrlf", "input"], ["--remove-section", "diff.x"]):
            with self.subTest(rest=rest):
                self.assertIsNone(ref_writes.signing_config_denial(rest))


if __name__ == "__main__":
    unittest.main()
