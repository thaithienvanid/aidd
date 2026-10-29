"""Orca's command line as the guard reads it, checked against Orca 1.4.237's parser (`out/cli/args.js`).

Orca reads every word that does not start with `--` as part of its command path, wherever it stands, so
`orca --json agent launch` and `orca agent --prompt x launch` both run `agent launch`. A `--flag` takes the next word
as its value unless that word starts with `--`, so a value the guard can't read may turn out to be an option, such as
`--prompt=approve SPEC-1`, or a command word. The guard matches a command's words in order among all such words,
values too, so an option never hides a command. It runs every reading that may apply, and it fails closed on a word
that may change the command or the prompt.
"""

from __future__ import annotations

import re
import unicodedata

from aidd import workitems
from aidd.guard import shell_parser, shell_words

# The commands that type into a terminal or an app, start a program in a terminal, or hand text to another agent. An
# empty set means the group alone is the command.
TYPES_TEXT = {
    "terminal": {"send", "create", "split"},
    "orchestration": {"send", "ask", "reply", "dispatch"},
    "computer": {"type-text", "paste-text", "press-key", "hotkey", "set-value"},
    "emulator": {"type"},
    "automations": {"create", "edit"},
    "type": set(),
}
# `emulator exec` hands its words raw to the emulator's helper, which may type them into an app.
PASSES_RAW = {"emulator": {"exec"}}
# The commands that start an agent whose first prompt carries `--prompt` or a Task's `--spec`, which its prompt hook
# reads as the person's typed words. A Task an orchestration worker starts on (`worker-start`, or `dispatch` after
# `task-create`) holds its spec as the brief. None reads a prompt from a file or stdin, or has a positional one. Orca
# 1.4.237 puts its own preamble before a worker's brief, so the prompt hook never reads a whole brief as a decision:
# the guard judges `--spec` anyway, in case a later Orca sends the brief alone.
STARTS_AGENT = {"agent": {"launch"}, "worktree": {"create"}, "orchestration": {"task-create", "worker-start"}}
_PROMPT_FLAGS = ("--prompt", "--spec")
_PROMPT_ASSIGNED = tuple(flag + "=" for flag in _PROMPT_FLAGS)
# The commands that hand their words, as they stand, to another program (`out/cli/index.js`): `claude-teams` starts
# Claude Code with them, and `agent-teams-tmux` is a tmux stand-in that types into Orca's panes. Orca checks the first
# word only.
PASSES_THROUGH = {"claude-teams": "claude", "agent-teams-tmux": "tmux"}
_NAMES = frozenset(
    {*TYPES_TEXT, *STARTS_AGENT, *PASSES_THROUGH, *PASSES_RAW}
    | {sub for table in (TYPES_TEXT, STARTS_AGENT, PASSES_RAW) for subs in table.values() for sub in subs}
)
_NO_VALUE = frozenset({"--json", "--help"})  # global flags that never take the next word
# The device commands `emulator exec --command` may run, an allowlist. On Android Orca hands the value to the device's
# shell (`adb shell`); on iOS it splits it into serve-sim's words. Each command's first word is a verb that exists
# there and types no text, and every word is plain, with no `--` option but keyevent's. serve-sim's taps, buttons,
# rotation, and debug toggles; `input` taps, swipes, drags, or presses a key that types no text and picks none on a
# soft keyboard; `am` only starts a component or an action, or force-stops a package; `pm` only lists; and Android's
# reads: `logcat -d`, `dumpsys <service>`, `wm size|density`, `settings get`, and `cat` of a file, each of which, like
# ps, ls, and getprop, may pipe into `grep` with one pattern. The commands split at `;`, `&&`, `||`,
# `|`, and `&`; any other shell operator, a word that is not plain, or a run of words a person's decision reads as
# denies, and so does a newline or a backtick on the line (approval_commands).
_RAW_VERBS = frozenset({"tap", "button", "rotate", "ca-debug", "fold", "memory-warning", "event-log", "screencap", "getprop", "ps", "ls"})
_RAW_SEPARATORS = frozenset({";", "&&", "||", "|", "&"})
_PLAIN_WORD = re.compile(r"[A-Za-z0-9_./:=,@+-]+")
_INPUT_SOURCES = frozenset({"touchscreen", "touchpad", "mouse", "stylus", "keyboard", "dpad", "gamepad", "joystick", "trackball"})
_INPUT_MOTIONS = frozenset({"tap", "swipe", "draganddrop"})
_KEY_FLAGS = frozenset({"--longpress", "--doubletap"})
_READS = frozenset({"ps", "ls", "getprop", "logcat", "dumpsys", "wm", "settings", "cat", "pm", "grep"})
_GREP_FLAGS = frozenset({"-i", "-v", "-w", "-E", "-F", "-c", "-n"})
# Where `cat` may read: files on storage and the system, and a few of /proc's text files by name. Never a device node,
# a file descriptor, or a /proc/<pid>/ entry, whose root and cwd links reach any file.
_READABLE = ("/sdcard/", "/storage/", "/data/local/tmp/", "/system/", "/vendor/")
_PROC_TEXT = frozenset({"/proc/meminfo", "/proc/cpuinfo", "/proc/version", "/proc/uptime", "/proc/loadavg", "/proc/stat"})
_PLAIN_KEYS = frozenset({"3", "4", "24", "25", "26", "66", "82", "187"}) | {
    "KEYCODE_" + key for key in ("HOME", "BACK", "VOLUME_UP", "VOLUME_DOWN", "POWER", "ENTER", "MENU", "APP_SWITCH")
}


def _runs(args: list[str], table: dict[str, set[str]]) -> bool:
    """Whether a group in `table`, then one of its commands, appear in that order among the words Orca may read as
    its command path. That includes values, so it never misses a command an option stands between."""
    words = [a for a in args if not a.startswith("--")]
    return any(w in table and (not table[w] or bool(table[w] & set(words[i + 1 :]))) for i, w in enumerate(words))


def passed_through(args: list[str]) -> list[str] | None:
    """The command `orca <args>` runs in its place, as that program's words, or None."""
    program = PASSES_THROUGH.get(args[0]) if args else None
    return [program, *args[1:]] if program else None


def types_text(args: list[str]) -> bool:
    """Whether `orca <args>` may type text or keys somewhere, or hand a message to another agent. A worker started in a
    terminal the command names (`worker-start --terminal`) may get its brief there as typed input, in a bare shell."""
    in_terminal = any(a == "--terminal" or a.startswith("--terminal=") for a in args)
    return _runs(args, TYPES_TEXT) or (in_terminal and _runs(args, {"orchestration": {"worker-start"}}))


def passes_raw(args: list[str]) -> bool:
    """Whether Orca may run `emulator exec`, which hands its `--command` raw to a helper that may type it into an app.
    Matched among all the words, values too, failing closed: Orca's reading of a flag before the command depends on its
    command registry, and the raw reading reads only `--command`, so it never hides another."""
    return _runs(args, PASSES_RAW)


def _follows_value_flag(args: list[str], i: int) -> bool:
    """Whether the word at `i` follows a `--flag` that may take it as its value."""
    return i > 0 and args[i - 1].startswith("--") and "=" not in args[i - 1] and args[i - 1] not in _NO_VALUE


def non_value_words(args: list[str]) -> list[str]:
    """The words of `orca <args>` that are no flag's value: each that does not start with `--`, but the word after a
    `--flag` that may take one. That reads more words as values than Orca may, so each word it returns is no value."""
    return [w for i, w in enumerate(args) if not w.startswith("--") and not _follows_value_flag(args, i)]


def _device_command_allowed(words: list[str], piped_read: bool = False) -> bool:
    """Whether one device command is on the allowlist: its verb, what that verb may take, and no run of its words that
    reads as a person's decision. `grep` runs only on what a listed read pipes into it (`piped_read`)."""
    verb, rest = words[0], words[1:]
    flags = {"pm": {"--user"}, "input": _KEY_FLAGS}.get(verb, set())
    if any(w.startswith("--") and w not in flags for w in words) or any(workitems.grants(" ".join(words[i:])) for i in range(len(words))):
        return False
    options = [w for w in rest if w.startswith("-")]
    if verb == "grep":  # one pattern on what a listed read pipes in: no file, and only flags that read
        return piped_read and set(options) <= _GREP_FLAGS and len(rest) - len(options) == 1
    if verb == "pm":  # lists only, for a user a number names
        return rest[:1] == ["list"] and all(rest[i + 1 : i + 2] and rest[i + 1].isdigit() for i, w in enumerate(rest) if w == "--user")
    if verb == "am":  # force-stops a package, or starts a component or an action: no extra, data, or other argument
        if rest[:1] == ["force-stop"]:
            return len(rest) == 2 and not options
        i = 1
        while i < len(rest) and (rest[i] == "-W" or (rest[i] in ("-n", "-a") and rest[i + 1 : i + 2] and not rest[i + 1].startswith("-"))):
            i += 1 if rest[i] == "-W" else 2
        return rest[:1] == ["start"] and i == len(rest)
    if verb == "logcat":  # dumps the log and exits, with filter words
        return rest[:1] == ["-d"] and options == ["-d"]
    if verb == "wm":  # reads the size or density; with a value, it sets one
        return rest in (["size"], ["density"])
    if verb == "settings":
        return rest[:1] == ["get"] and len(rest) == 3 and not options
    if verb == "dumpsys":  # one service's dump: some services act on the words after their name
        return len(rest) == 1 and not options
    if verb == "cat":
        return bool(rest) and not options and all(p in _PROC_TEXT or (p.startswith(_READABLE) and "/fd" not in p and ".." not in p) for p in rest)
    if verb == "input":
        rest = rest[1:] if rest[:1] and rest[0] in _INPUT_SOURCES else rest
        if rest[:1] == ["keyevent"]:
            keys = [w for w in rest[1:] if w not in _KEY_FLAGS]
            return bool(keys) and set(keys) <= _PLAIN_KEYS
        return bool(rest) and rest[0] in _INPUT_MOTIONS
    return verb in _RAW_VERBS


def raw_allowed(args: list[str]) -> bool:
    """Whether every device command an `emulator exec` hands its helper is on the allowlist, read as the device shell
    reads it, failing closed, and no word after `emulator exec` but flag values would be more of Orca's command path."""
    path = non_value_words(args)
    if path[:2] == ["emulator", "exec"] and len(path) > 2:
        return False
    values = [a.split("=", 1)[1] for a in args if a.startswith("--command=")]
    values += [nxt for a, nxt in zip(args, args[1:], strict=False) if a == "--command" and not nxt.startswith("--")]
    for value in values:
        try:
            tokens = shell_parser.shell_tokens(value)
        except ValueError:
            return False
        if not tokens:
            return False  # an empty command
        segment: list[str] = []
        piped_read = False  # the command before this one is a listed read that pipes into it
        for token in [*tokens, None]:
            if token is None and not segment:
                break  # a trailing separator
            if token is None or token in _RAW_SEPARATORS:
                if not segment or not _device_command_allowed(segment, piped_read):
                    return False  # a separator with no command before it, or a command off the list
                piped_read, segment = token == "|" and segment[0] in _READS, []
            elif _PLAIN_WORD.fullmatch(token):
                segment.append(token)
            else:
                return False  # a shell operator, a quoted space, an expansion, or a character beyond plain ASCII
    return True


def prompt_words(args: list[str]) -> list[str]:
    """Each word that hands an agent its first prompt: `--prompt=<text>` or `--spec=<text>`, or the word after either
    unless it starts with `--`. Each keeps its quoting, so the guard can tell whether the shell passes it as written."""
    found = [a for a in args if a.startswith(_PROMPT_ASSIGNED)]
    return found + [nxt for a, nxt in zip(args, args[1:], strict=False) if a in _PROMPT_FLAGS and not nxt.startswith("--")]


def prompts(args: list[str]) -> list[str]:
    """The text of each prompt the command line hands an agent."""
    return [w.split("=", 1)[1] if w.startswith(_PROMPT_ASSIGNED) else str(w) for w in prompt_words(args)]


def starts_agent(args: list[str]) -> bool:
    """Whether `orca <args>` may start an agent with a first prompt: a command in STARTS_AGENT, or any prompt flag."""
    return bool(prompt_words(args)) or _runs(args, STARTS_AGENT)


def _may_be_option(word: str) -> bool:
    """Whether the shell may make `word` into other words, or into one that starts with `-`."""
    prefix = shell_words.literal_prefix(word)
    return shell_words.may_split(word) or not prefix or prefix.startswith("-")


def _may_be_name(word: str) -> bool:
    """Whether the shell may make `word` into an option or a command word the guard matches."""
    prefix = shell_words.literal_prefix(word)
    return _may_be_option(word) or any(name.startswith(prefix) for name in _NAMES)


def hides_text(prompt: str) -> bool:
    """Whether a prompt holds a character that may edit what an agent reads, or that one parser reads as a space and
    another does not: a control character other than a newline or a tab, or a format or space character beyond ASCII."""
    return any((unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp") and c not in "\n\t") or (unicodedata.category(c) == "Zs" and c != " ") for c in prompt)


def unreadable(args: list[str]) -> bool:
    """Whether a word may change which command Orca runs, or the prompt it hands an agent, in a way the guard can't read:
    - a prompt that is not literal, such as `"$P"`, `"$(cat f)"`, or a brace or a glob, or one with a character that
      edits or hides text, such as a control key or an invisible format character;
    - on a command that may start an agent, any word not literal that may split or start with `-`;
    - on any command, a word not literal before the second word that is surely in its command path.
    """
    if any(not shell_words.literal(w) for w in prompt_words(args)) or any(map(hides_text, prompts(args))):
        return True
    agent, sure = starts_agent(args), 0
    for i, word in enumerate(args):
        if not shell_words.literal(word):
            if (sure < 2 and _may_be_name(word)) or (agent and _may_be_option(word)):
                return True
        elif not word.startswith("--") and not _follows_value_flag(args, i):
            sure += 1
    return False
