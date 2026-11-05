"""Fuzzing, with the standard library only: seeded random inputs for the parsers an agent or a repository can feed, so
every run is the same run (deterministic) and a failure names the seed that reproduces it.

The property is fail-safe behavior, not output: a parser that raises an error nobody planned for gives a command no
risk level at all. So the shell check never raises, the shell parser raises only ValueError (a command it cannot
parse), and a document raises only DocumentError.
`FUZZ_RUNS` raises the number of cases for a longer run by hand (read before `helpers` makes the environment hermetic).
"""

import os
import random
import unittest

RUNS = int(os.environ.get("FUZZ_RUNS") or "1500")

from helpers import ROOT  # noqa: E402, F401  (puts src on the path)

from aidd.kernel import documents  # noqa: E402

SEED = 20261028

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
