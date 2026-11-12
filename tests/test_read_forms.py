"""A command reads `allow` under the read forms only when it provably writes nothing. Each listed read or preview form
reads `allow`. Adding a writing word, a second command, a redirection, an expansion, a setting, or a wrapper to one keeps
the level the leading words give, and so does a form the data does not list. Both directions are tables, and a generated
one crosses each form's words with a vocabulary and holds the reader to an oracle written from the tools' documentation."""

from __future__ import annotations

import itertools
import re
import unittest

import helpers  # noqa: F401  # the hermetic environment
from aidd import risk
from aidd.risk import read_forms

RS = risk.rule_set(None)


def level(line: str) -> str:
    # The default branch, so a push or a merge reads as the strict level it would have without the forms.
    return risk.command_level(RS, line, branch="default")["level"]


# Hand-written: each form the data lists, as a person types it. Every one of these asked before.
READS = [
    "git tag",
    "git tag -l",
    "git tag --list",
    "git tag -l 'v1.*'",
    'git tag --list "v1.*" -n3',
    "git tag -n",
    "git tag -n5 -l",
    "git tag -i",
    "git tag --contains HEAD",
    "git tag --no-contains v1.0.0",
    "git tag --points-at HEAD",
    "git tag --merged main",
    "git tag --no-merged main",
    "git tag --sort=-version:refname",
    "git tag '--format=%(refname:short)' -l",
    "git tag --column",
    "git tag -l --contains HEAD 'v2.*'",
    "kubectl apply -f deploy.yaml --dry-run=client",
    "kubectl apply --dry-run=client -f deploy.yaml -n shop -o yaml",
    "kubectl apply --dry-run=client --filename=deploy.yaml",
    "kubectl delete -f deploy.yaml --dry-run=client",
    "kubectl delete pod web --dry-run=client",
    "aws s3 rm s3://bucket/key --dryrun",
    "aws s3 rm s3://bucket --recursive --dryrun --exclude '*.jpg'",
    "git push -h",
    "git tag -h",
    "kubectl apply -h",
    "kubectl apply --help",
    "kubectl delete --help",
    "aws s3 rm --help",
]

# Words that write, send, or run something else, appended to a read line: every one keeps the strict level.
SECOND_COMMANDS = ["; git tag v1", "&& git push origin main", "|| rm -rf build", "| xargs rm -rf", "& rm -rf build", "\n git tag v1"]
REDIRECTIONS = ["> out.txt", ">> out.txt", "2> err.txt", "&> all.txt", ">| out.txt"]
EXPANSIONS = ["$(rm -rf build)", "`rm -rf build`", '"$WORD"', "$WORD", "*", "'x' #", "# -l", "v*", "{a,b}", "~", "\\-d"]
WRITING_WORDS = {
    "git tag": ["-d v1", "--delete v1", "-f", "-a", "-m x", "-s", "-u key", "--create-reflog", "-l -d v1", "--", "-lx", "--cont HEAD"],
    "kubectl": ["--dry-run=none", "--dry-run=server", "--dry-run", "--force", "--all", "-k dir", "--server https://x", "--kubeconfig=cfg", "--dry-run=client"],
    "aws": ["--endpoint-url https://x", "--profile p", "--dryrun=false", "--no-dryrun"],
    "git": ["origin main", "--help", "--dry-run", "-hh"],
}
PREFIXES = [
    "sudo ",
    "env X=1 ",
    "X=1 ",
    "time ",
    "nice -n 5 ",
    "xargs ",
    "command ",
    "exec ",
    "nohup ",
    "timeout 5 ",
    "/usr/bin/",
    "./",
    "(",
    "{ ",
    "if ",
    "! ",
]
SHELLS = ["sh -c '{}'", 'bash -c "{}"', "eval {}", "echo $({})", "echo `{}`", "(cd . && {})", "xargs -I{{}} {}"]


class EachFormReadsAllow(unittest.TestCase):
    def test_each_listed_read_or_preview_form_is_allow(self):
        for line in READS:
            with self.subTest(line=line):
                self.assertEqual(level(line), "allow")

    def test_the_data_holds_what_the_table_lists(self):
        data = risk.builtin()
        listed = {(f["program"], *f["words"]) for f in data["read_forms"]} | {(f["program"], *c) for f in data["help_forms"] for c in f["commands"]}
        for form in sorted(listed):
            with self.subTest(form=" ".join(form)):
                self.assertTrue(any(line.split()[: len(form)] == list(form) for line in READS), "every listed form has a row above")
        for form in [*data["read_forms"], *data["help_forms"]]:
            for action in form["clears"]:
                with self.subTest(action=action):
                    self.assertIn(action, data["actions"])
                    self.assertEqual(risk.level_of(RS, action, branch="default")[0], "ask", "a form clears only an asking action")

    def test_each_form_the_data_lists_reads_with_each_option_it_lists(self):
        """Built from the data, one line per option: the form's words, its required options, and the option with a value."""
        for form in risk.builtin()["read_forms"]:
            base = [form["program"], *form["words"], *form.get("required", [])]
            lines = [" ".join(base)]
            lines += [" ".join([*base, f]) for f in form.get("flags", []) if f not in form.get("required", [])]
            lines += [" ".join([*base, v, "x"]) for v in form.get("values", [])]
            lines += [" ".join([*base, a + "x"]) for a in form.get("attached", [])]
            lines += [" ".join([*base, n + "5"]) for n in form.get("numbered", [])]
            names = form.get("positionals", "none")
            lines += [" ".join([*base, "name"])] if names == "any" else []
            lines += [" ".join([*base, names[0], "name"])] if isinstance(names, list) else []
            for line in lines:
                with self.subTest(line=line):
                    self.assertEqual(level(line), "allow")


class AWritingWordASecondCommandOrAWrapperKeepsTheStrictLevel(unittest.TestCase):
    def test_the_same_forms_with_a_writing_word_keep_the_strict_level(self):
        for line in READS:
            program = "git tag" if line.startswith("git tag") else line.split()[0]
            for word in WRITING_WORDS[program]:
                text = f"{line} {word}"
                if text in READS:
                    continue
                with self.subTest(line=text):
                    self.assertEqual(level(text), "ask")

    def test_a_second_command_a_redirection_or_an_expansion_keeps_the_strict_level(self):
        for line in READS:
            for tail in [*SECOND_COMMANDS, *REDIRECTIONS, *EXPANSIONS]:
                text = f"{line} {tail}"
                with self.subTest(line=text):
                    self.assertEqual(level(text), "ask")

    def test_a_setting_a_program_path_or_a_wrapper_before_it_keeps_the_strict_level(self):
        for line in READS:
            for prefix in PREFIXES:
                text = prefix + line
                with self.subTest(line=text):
                    self.assertEqual(level(text), "ask")
            for shell in SHELLS:
                text = shell.format(line)
                with self.subTest(line=text):
                    self.assertEqual(level(text), "ask")

    def test_the_reader_itself_clears_nothing_for_a_path_a_group_or_a_setting(self):
        """`commands.call_actions` hands it the command as typed, but it holds the line on its own too."""
        for line in ("/usr/bin/git tag -l", "./git tag -l", "(git tag -l)", "{ git tag -l; }", "X=1 git tag -l", "git tag -l > f", "git tag -l $x"):
            with self.subTest(line=line):
                self.assertEqual(read_forms.cleared_actions(line), frozenset())
        self.assertEqual(read_forms.cleared_actions("git tag -l"), frozenset({"git.tag.create"}))

    def test_git_options_before_the_command_keep_the_strict_level(self):
        """`-c core.pager=...` and `--exec-path` start a program, and `-C` names another repository."""
        for option in ("-c core.pager=x", "-c alias.tag=x", "-C ..", "--git-dir=x", "--exec-path=x", "--no-pager", "-p"):
            for line in ("tag -l", "tag", "push -h", "tag -h"):
                with self.subTest(line=f"git {option} {line}"):
                    self.assertEqual(level(f"git {option} {line}"), "ask")

    def test_a_preview_that_still_runs_project_code_or_sends_stays_strict(self):
        """Each tool's own documentation, or a run, shows these write or send: a hook, a lifecycle script, a request."""
        for line in (
            "git push --dry-run origin main",
            "git push -n origin main",
            "npm publish --dry-run",
            "pnpm publish --dry-run",
            "cargo publish --dry-run",
            "wrangler deploy --dry-run",
            "helm upgrade app chart --dry-run",
            "helm install app chart --dry-run=client",
            "kubectl apply -f x.yaml --dry-run=server",
            "terraform apply -help",
            "terraform destroy -help",
            "gh pr merge --help",
            "npm publish -h",
            "git push --help",
            "git tag --help",
            "git push origin -h",
            "docker push --help",
        ):
            with self.subTest(line=line):
                self.assertEqual(level(line), "ask")


def _git_tag(args: list[str]) -> bool:
    """git-tag(1): a listing, as the manual and `git tag -h` describe it, written without the data."""
    flags = {"-l", "--list", "-i", "--ignore-case", "--column", "--no-column"}
    takes = {"--contains", "--no-contains", "--points-at", "--merged", "--no-merged", "--sort", "--format"}
    joined = ("--sort=", "--format=", "--contains=", "--no-contains=", "--points-at=", "--merged=", "--no-merged=", "--column=")
    seen, names, i = set(), 0, 0
    while i < len(args):
        a = args[i]
        if a in flags:
            seen.add(a)
        elif re.fullmatch(r"-n\d*", a) or any(a.startswith(p) and len(a) > len(p) for p in joined):
            pass
        elif a in takes:
            if i + 1 >= len(args) or (args[i + 1].startswith("-") and args[i + 1] != "-"):
                return False
            i += 1
        elif a.startswith("-"):
            return False
        else:
            names += 1
        i += 1
    return names == 0 or bool(seen & {"-l", "--list"})


def _kubectl(args: list[str]) -> bool:
    """kubectl apply and delete: only `--dry-run=client`, once, with the options that name or show what it reads."""
    takes = {"-f", "--filename", "-n", "--namespace", "-o", "--output"}
    previews, i = 0, 0
    while i < len(args):
        a = args[i]
        if a == "--dry-run=client":
            previews += 1
        elif a in takes:
            if i + 1 >= len(args) or (args[i + 1].startswith("-") and args[i + 1] != "-"):
                return False
            i += 1
        elif any(a.startswith(p) and len(a) > len(p) for p in ("--filename=", "--namespace=", "--output=")):
            pass
        elif a.startswith("-"):
            return False
        i += 1
    return previews == 1


def _aws_rm(args: list[str]) -> bool:
    """aws s3 rm: `--dryrun` once, with the options that only narrow what it lists."""
    dry, i = 0, 0
    while i < len(args):
        a = args[i]
        if a == "--dryrun":
            dry += 1
        elif a in {"--recursive", "--quiet", "--only-show-errors"}:
            pass
        elif a in {"--include", "--exclude"}:
            if i + 1 >= len(args) or (args[i + 1].startswith("-") and args[i + 1] != "-"):
                return False
            i += 1
        elif a.startswith("-"):
            return False
        i += 1
    return dry == 1


def _oracle(words: list[str]) -> frozenset[str]:
    """The actions `words` provably are not, from the tools' documentation, for the three programs the data lists."""
    cleared: set[str] = set()
    if words[:2] == ["git", "tag"] and _git_tag(words[2:]):
        cleared.add("git.tag.create")
    if words[:2] == ["kubectl", "apply"] and _kubectl(words[2:]):
        cleared.add("deploy.run")
    if words[:2] == ["kubectl", "delete"] and _kubectl(words[2:]):
        cleared.add("infra.apply")
    if words[:3] == ["aws", "s3", "rm"] and _aws_rm(words[3:]):
        cleared.add("data.delete")
    helps = {
        ("git", "push"): ({"-h"}, {"git.push"}),
        ("git", "tag"): ({"-h"}, {"git.tag.create"}),
        ("kubectl", "apply"): ({"-h", "--help"}, {"deploy.run"}),
        ("kubectl", "delete"): ({"-h", "--help"}, {"infra.apply"}),
        ("aws", "s3", "rm"): ({"--help"}, {"data.delete"}),
    }
    for command, (flags, actions) in helps.items():
        if len(words) == len(command) + 1 and tuple(words[:-1]) == command and words[-1] in flags:
            cleared |= actions
    return frozenset(cleared)


class AGeneratedTableOfEveryCombinationOfWords(unittest.TestCase):
    """The reader against the oracle over every combination of a vocabulary's words, up to three, behind each program and
    command the data lists. A difference is either a form the reader misses or one it reads that the manual does not say."""

    VOCAB = {
        "git tag": [
            "-l",
            "--list",
            "-d",
            "-f",
            "-a",
            "-m",
            "v1",
            "--contains",
            "HEAD",
            "-n",
            "-n5",
            "--sort=x",
            "--sort",
            "-i",
            "--delete",
            "--",
            "-lx",
            "--points-at",
            "--merged",
            "-h",
            "-",
        ],
        "kubectl apply": [
            "--dry-run=client",
            "--dry-run=server",
            "--dry-run",
            "client",
            "-f",
            "x.yaml",
            "-n",
            "ns",
            "-o",
            "yaml",
            "--force",
            "-k",
            "--filename=x",
            "--dry-run=none",
            "-h",
            "--help",
        ],
        "kubectl delete": ["--dry-run=client", "--dry-run", "pod", "web", "-f", "x.yaml", "--all", "--force", "-n", "ns", "--output=json", "-h", "--help", "-"],
        "aws s3 rm": ["--dryrun", "--recursive", "s3://b", "--exclude", "x", "--include", "--profile", "p", "--quiet", "--dryrun=false", "--help", "-h"],
        "git push": ["-h", "--help", "origin", "main", "--dry-run", "-n"],
    }

    def lines(self):
        for head, vocab in self.VOCAB.items():
            for n in range(4):
                for args in itertools.product(vocab, repeat=n):
                    yield [*head.split(), *args]

    def test_the_reader_clears_exactly_what_the_oracle_does(self):
        checked = 0
        for words in self.lines():
            checked += 1
            got, want = read_forms.cleared_actions(" ".join(words)), _oracle(words)
            if got != want:
                self.fail(f"{' '.join(words)!r}: the reader clears {sorted(got)}, the documentation says {sorted(want)}")
        self.assertGreater(checked, 15_000)

    def test_a_cleared_action_is_the_only_level_change_on_a_sample_through_command_level(self):
        """Through the whole reader, a line is `allow` exactly when the oracle clears its one asking action."""
        # A push has other ways to read allow on a branch of your own, so only a help line is checked there.
        every = [w for w in self.lines() if w[:2] != ["git", "push"] or _oracle(w)]
        sample = [w for i, w in enumerate(every) if i % 53 == 0 or _oracle(w)]
        self.assertGreater(len(sample), 300)
        for words in sample:
            line = " ".join(words)
            want = "allow" if _oracle(words) else "ask"
            with self.subTest(line=line):
                self.assertEqual(level(line), want)


class TheDataIsOwnedByTheSchema(unittest.TestCase):
    def test_the_forms_validate_and_each_names_why_it_writes_nothing(self):
        from aidd.kernel import json_schema

        self.assertEqual(json_schema.validate(risk.builtin(), "risks.schema.json"), [])
        for form in [*risk.builtin()["read_forms"], *risk.builtin()["help_forms"]]:
            self.assertGreater(len(form["reason"]), 20, form)

    def test_a_config_cannot_add_or_widen_a_form(self):
        from aidd import config

        for key in ("read_forms", "help_forms"):
            with self.subTest(key=key), self.assertRaises(config.ConfigError) as caught:
                config.load_text(f'aidd_version: "1.0.0"\nprofile: solo\nrisks:\n  {key}: []\n')
            self.assertIn(key, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
