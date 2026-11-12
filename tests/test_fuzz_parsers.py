"""Fuzzing, with the standard library only: seeded random inputs for the parsers an agent or a repository can feed, so
every run is the same run (deterministic) and a failure names the seed that reproduces it.

The property is fail-safe behavior, not output: a parser that raises an error nobody planned for gives a command no
risk level at all. So the shell check never raises, the shell parser raises only ValueError (a command it cannot
parse), and a document raises only DocumentError.
`FUZZ_RUNS` raises the number of cases for a longer run by hand (read before `helpers` makes the environment hermetic).
"""

import os
import random
import tempfile
import unittest
from pathlib import Path

RUNS = int(os.environ.get("FUZZ_RUNS") or "1500")

from helpers import git  # noqa: E402  (puts src on the path)

from aidd import risk  # noqa: E402
from aidd.kernel import documents  # noqa: E402
from aidd.risk import rules, shell  # noqa: E402

SEED = 20261028
# The shell check reads the rules and, for a line that names git, the folder's refs, so it takes about a millisecond a
# line: a third of RUNS keeps the file within its budget, and FUZZ_RUNS still raises it.
SHELL_RUNS = max(1, RUNS // 3)
# The longest line, in pieces: long enough to nest a wrapper in a substitution in a loop, short enough to stay fast.
SHELL_LONGEST = 24

# The pieces a shell line is built from: words the risk rules look for, every kind of quoting and expansion, and the
# punctuation that splits commands.
SHELL_PIECES = (
    "git", "push", "--force", "origin", "main", "gh", "pr", "merge", "3", "glab", "mr", "approve", "aidd", "land", "--confirmed",
    "approve-spec", "/aidd", "echo", "bash", "-c", "sh", "eval", "env", "HOME=/x", "A[x]=1", "B+=y", "tmux", "send-keys",
    "xdotool", "type", "claude", "-p", "--settings", "npx", "orca", "terminal", "send", "find", "-exec", "xargs", "sudo",
    "'", '"', "\\", "$(", ")", "`", "${", "}", "$'\\x41'", "<<", "EOF", "<<<", "|", "||", "&&", ";", "&", ">", ">>", "<", "2>&1",
    "(", ")", "{", "}", "!", "#", "*", "?", "[", "]", "~", "\n", "\t", " ", "  ", "if", "then", "fi", "for", "in", "do", "done",
    "\x00", "‮", "é", "😀",
)  # fmt: skip
YAML_PIECES = (
    "id", ": ", "SPEC-1", "\n", "  ", "- ", "[", "]", "{", "}", ",", '"', "'", "\\u", "\\", "#", "tests", "files", "true", "null",
    "~", "&a", "*a", "!!str", "|", ">", "---", "...", "\t", "é", " ", "0x1F", "1e9", "?", "%", "@", "`",
)  # fmt: skip


def random_text(rng: random.Random, pieces: tuple[str, ...], longest: int = 24) -> str:
    return "".join(rng.choice(pieces) + (" " if rng.random() < 0.5 else "") for _ in range(rng.randint(0, longest)))


class ShellFuzzTests(unittest.TestCase):
    """`aidd risk --command` reads any line an agent sends, so no line may leave it without a level."""

    def test_the_shell_check_never_raises(self):
        """The two calls `aidd risk --command` makes, `command_level` and `command_notes`, answer every line with a level:
        in no folder (another repository), in a folder with no git, on a named branch, and in a git repository with a commit."""
        rs = risk.rule_set(None)
        rng = random.Random(SEED)
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder) / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "-c", "user.name=fuzz", "-c", "user.email=fuzz@example.com", "commit", "-q", "--allow-empty", "-m", "one commit")
            contexts = ((None, None), (folder, None), (folder, "main"), (str(repo), git(repo, "branch", "--show-current")))
            for i in range(SHELL_RUNS):
                line = random_text(rng, SHELL_PIECES, longest=SHELL_LONGEST)
                cwd, branch = contexts[i % len(contexts)]
                try:
                    answer = risk.command_level(rs, line, branch=branch, cwd=cwd)
                    risk.command_notes(rs, answer)
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"case {i} (seed {SEED}) raised {type(exc).__name__}: {exc!r} on {line!r}")
                self.assertIn(answer["level"], rules.LEVELS, f"case {i} (seed {SEED}) on {line!r}")

    def test_the_shell_parser_raises_only_value_error(self):
        """A line the parser cannot read is a ValueError, which the check reads as more, never another error."""
        rng = random.Random(SEED + 1)
        parsers = (shell.split, shell.tokens, shell.wrapped, shell.shell_words, shell.without_redirections)
        for i in range(RUNS):
            line = random_text(rng, SHELL_PIECES, longest=SHELL_LONGEST)
            for parse in parsers:
                try:
                    parse(line)
                except ValueError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    self.fail(f"case {i} (seed {SEED + 1}) {parse.__name__} raised {type(exc).__name__}: {exc!r} on {line!r}")


class DocumentFuzzTests(unittest.TestCase):
    def test_front_matter_raises_only_document_error(self):
        """A Spec's front matter is read by `aidd validate` and `aidd status`; anything outside aidd's YAML subset is a
        DocumentError, never another error."""
        rng = random.Random(SEED + 2)
        for i in range(RUNS):
            text = "---\n" + random_text(rng, YAML_PIECES, longest=40) + "\n---\nbody\n"
            try:
                documents.split_front_matter(text, "fuzz.md")
            except documents.DocumentError:
                pass
            except Exception as exc:  # noqa: BLE001
                self.fail(f"case {i} (seed {SEED + 2}) raised {type(exc).__name__}: {exc!r} on {text!r}")


if __name__ == "__main__":
    unittest.main()
