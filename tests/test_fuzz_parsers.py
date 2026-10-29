"""Fuzzing, with the standard library only: seeded random inputs for the parsers an agent or a repository can feed, so
every run is the same run (deterministic) and a failure names the seed that reproduces it.

The property is fail-safe behavior, not output: a parser that raises an error nobody planned for makes the guard's hook
answer "allow" outside a fail-closed project (pre_tool._broke). So the shell check never raises, the shell parser raises
only ValueError (the guard reads that as a command it cannot parse), and a document raises only DocumentError.
`FUZZ_RUNS` raises the number of cases for a longer run by hand (read before `helpers` makes the environment hermetic).
"""

import os
import random
import unittest

RUNS = int(os.environ.get("FUZZ_RUNS") or "1500")

from helpers import ROOT  # noqa: E402, F401  (puts src on the path)

from aidd.guard import approval_commands, command_check, dialects, shell_parser  # noqa: E402
from aidd.kernel import documents  # noqa: E402

SEED = 20261028

# The pieces a shell line is built from: words the guard looks for, every kind of quoting and expansion, and the
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
    def test_the_shell_check_never_raises(self):
        """`forbidden_action` decides every line it is given, whatever it holds, in either shell."""
        rng = random.Random(SEED)
        for i in range(RUNS):
            command = random_text(rng, SHELL_PIECES)
            for powershell in (False, True):
                try:
                    approval_commands.forbidden_action(command, powershell=powershell)
                except Exception as exc:  # noqa: BLE001  # the property: nothing escapes
                    self.fail(f"case {i} (seed {SEED}, powershell={powershell}) raised {type(exc).__name__}: {exc!r} on {command!r}")

    def test_the_guards_bash_entry_never_raises(self):
        """`check_command`, what the hook calls for a Bash tool call, outside a repository and with long, deep lines."""
        rng = random.Random(SEED + 3)
        for i in range(RUNS):
            command = random_text(rng, SHELL_PIECES, longest=24 if i % 10 else 400)
            try:
                command_check.check_command(None, "/tmp", command)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"case {i} (seed {SEED + 3}) raised {type(exc).__name__}: {exc!r} on {command!r}")

    def test_the_hook_event_readers_never_raise(self):
        """Each harness's dialect normalizes whatever event it is given."""
        rng = random.Random(SEED + 4)
        keys = ("tool_name", "tool", "tool_input", "input", "toolCall", "cwd", "harness", "agent", "agent_type", "agent_id", "sessionID")
        values = (None, "", "Bash", "task", "opencode", "invoke_subagent", "aidd-developer", 3, [], {}, {"command": "git push"}, {"subagent_type": ["x"]})
        for i in range(RUNS):
            event = {rng.choice(keys): rng.choice(values) for _ in range(rng.randint(0, 6))}
            try:
                dialects.of(event).normalize(event)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"case {i} (seed {SEED + 4}) raised {type(exc).__name__}: {exc!r} on {event!r}")

    def test_the_shell_parser_raises_only_value_error(self):
        rng = random.Random(SEED + 1)
        for i in range(RUNS):
            command = random_text(rng, SHELL_PIECES)
            try:
                shell_parser.simple_commands(command, quoting=bool(i % 2))
            except ValueError:
                pass  # a command it cannot parse, which the guard holds to its raw text
            except Exception as exc:  # noqa: BLE001
                self.fail(f"case {i} (seed {SEED + 1}) raised {type(exc).__name__}: {exc!r} on {command!r}")


class DocumentFuzzTests(unittest.TestCase):
    def test_front_matter_raises_only_document_error(self):
        """A Spec's front matter is read by the guard and the gate; anything outside aidd's YAML subset is a
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
