"""The commands that approve or merge: the platform CLIs and APIs, `aidd approve` and `aidd land` through any
wrapper, and an approval typed into another terminal (`forbidden_action`).
"""

from __future__ import annotations

import re
import shlex
import urllib.parse

from aidd import config, workitems
from aidd.guard import approval_text, git_commands, indirect_runs, orca_commands, ref_writes, repo_config, shell_parser, shell_words, tmux_commands, verdicts
from aidd.guard.publish_commands import GH_VALUE_FLAGS, RAW_PUBLISH, api_write, leaves_this_machine
from aidd.kernel import git

_GRAPHQL_WRITES = re.compile(
    r"\b(?:mergePullRequest|addPullRequestReview|submitPullRequestReview|enablePullRequestAutoMerge|approvePullRequest|"
    r"mergeBranch|mergeMergeRequest|mergeRequestAccept|mergeRequestApprove)\b"
)


def _api_write(args: list[str], merge: re.Pattern, review: re.Pattern) -> bool:
    """`gh api` or `glab api` with an endpoint that merges or approves, called with a writing method. A GET of the merge
    endpoint only asks whether the PR merged; a review listing only reads approvals."""
    return api_write(args, merge, _GRAPHQL_WRITES) or api_write(args, review, _GRAPHQL_WRITES)


_GH_MERGE = re.compile(r"/pulls/[^/]+/merge\b|/merges\b|/pulls/[^/]+/update-branch\b")
_GH_REVIEW = re.compile(r"/pulls/[^/]+/reviews\b")
_GL_MERGE = re.compile(r"/merge_requests/[^/]+/merge\b")
_GL_REVIEW = re.compile(r"/merge_requests/[^/]+/(?:approve|unapprove)\b")


def _person_said(what: str, argv: list[str], root: str | None) -> bool:
    """Whether the person already said yes to this `aidd approve`, `aidd land`, or `aidd publish`, so the agent may run
    it: their standing approval is live (`aidd approve all`), or, for a land or a Merge approval, their "land it" or
    "merge it" covers this head (workitems.land_decision; aidd checks it again and records the approval citing it). A
    publish needs agents to publish here (`publish: agents`), or the person's "publish" for this head, or their `approve
    all and publish` (workitems.publish_said_for): `approve all` alone never covers it. Never
    `--confirmed`, which claims a person confirmed elsewhere, and never `aidd approve all`, which only the person starts;
    `aidd approve stop` only takes a standing approval back, so anyone may run it. aidd itself checks the route and the
    head again, and asks for the person when the standing approval does not cover the change."""
    words = next((shell_parser.positional_words(rest, set()) for rest in shell_parser.aidd_runs(argv)), [])
    # A word only the shell or the input fills in may be `--confirmed` too.
    if not root or any(names_confirmed(a) or _EXPANSION.search(a) for a in argv):
        return False
    if words[:2] == ["approve", "stop"]:
        return True
    if words[:2] not in (["approve", "spec"], ["approve", "merge"]) and words[:1] not in (["land"], ["publish"]):
        return False
    cfg = repo_config.load_config(root)
    if words[:1] == ["publish"]:
        from aidd import gate

        head = git.run(["rev-parse", "HEAD"], root, check=False).strip()
        return gate.agents_publish(root) or (bool(head) and workitems.publish_said_for(cfg, root, head))
    if workitems.live_standing_for(cfg, root) is not None:
        return True
    head = git.run(["rev-parse", "HEAD"], root, check=False).strip()
    merge = what == "land" or words[:2] == ["approve", "merge"]
    return merge and bool(head) and workitems.land_said_for(cfg, root, head)


def names_confirmed(word: str) -> bool:
    """Whether `word` may be `--confirmed`: the option, with or without its `=value`, or any prefix of it from `--co` on,
    which argparse reads as the option wherever a parser lets a long option be abbreviated. aidd's parsers never do
    (cli/parser.py), and the guard reads every prefix as the option anyway, failing closed."""
    option = word.split("=", 1)[0]
    return option.startswith("--confirmed") or (len(option) >= len("--co") and "--confirmed".startswith(option))


def _aidd_decision(argv: list[str]) -> str | None:
    """`approve`, `land`, `publish`, or a proposal's `decide` and `sign-off` when a simple command runs aidd with it
    (`shell_parser.aidd_runs`), as its first positional words, unless it only reads: `--help`, or `--show` (a preview)
    without `--confirmed`."""
    for rest in shell_parser.aidd_runs(argv):
        first = shell_parser.positional_words(rest, set())[:1]
        # `hook` too: the harness runs aidd's hooks, and the prompt hook records what the person typed, so an agent that
        # fed it a prompt of its own would record a decision as theirs. `mcp` the same way: the server's dialogs record a
        # person's decision, and an agent that ran it with a scripted answer on stdin would answer for them.
        what = first[0] if first in (["approve"], ["land"], ["publish"], ["hook"], ["mcp"]) else None
        if first and _EXPANSION.search(first[0]):
            what = first[0]  # a command only the shell, or the input of xargs or find (indirect_runs), names: fail closed
        # `aidd worktrees clean` removes folders: a person's; `--dry-run` only says what it would remove.
        if first == ["worktrees"] and shell_parser.positional_words(rest, set())[1:2] == ["clean"] and "--dry-run" not in rest:
            what = "worktrees clean"
        if first == ["proposal"]:
            # argparse takes `--by X` and `--reason X` before the action too, so any word may be it: fail closed.
            what = next((f"proposal {a}" for a in rest if a in ("decide", "sign-off")), None)
        if what:
            if any(_EXPANSION.search(a) for a in rest):
                return what  # a word only the shell or the input fills in may be `--confirmed`: no reading only
            if any(a in ("-h", "--help") for a in rest):
                continue
            if "--show" in rest and not any(names_confirmed(a) for a in rest):
                continue
            return what
    return None


# The words aidd records as the person's own decision when they type them (cli/commands/typed_decisions.py, and
# aidd-mods): typed into another terminal or program by an agent, they would pass for the person's keyboard. Matched
# anywhere, failing closed: a terminal edits what it receives (a backspace, a cleared line), so no reading of the text
# can say what the prompt finally holds. An agent that sends a message there words it without them.
_TYPED_DECISION = re.compile(r"approve|land|merge|publish|push|ship|automate|explore", re.I)


# The same text as the program receives it, after the quoting and escaping a raw match misses: the words may run
# together (`"aid""d approve"`, `aidd Space approve`), so no word boundary is required before `aidd`; the word after
# `approve`, `land`, or `publish` must end there, as it must for a shell to run it.
_APPROVAL_RECEIVED = re.compile(
    r"aidd(?:\.cli|\.__main__)?\s+(?:approve|land|publish)(?![A-Za-z0-9_-])"
    r"|aidd(?:\.cli|\.__main__)?\s+proposal(?![A-Za-z0-9_-])[^\n;&|]*?(?:decide|sign-off)(?![A-Za-z0-9_-])"
    r"|/aidd\s+approve|refs/aidd/(?:decisions|approvals)|Aidd-Merge-Approval",
    re.I,
)
_TTY_DEVICES = ("/dev/tty", "/dev/pts/", "/dev/console")
_KEY_SENDERS = {"xdotool": {"type", "key", "keydown", "keyup"}, "ydotool": {"type", "key"}}


# The key names tmux (and `orca computer press-key`) turns into the characters they type.
_KEY_NAMES = {"Space": " ", "Enter": "\n", "KPEnter": "\n", "Return": "\n", "C-m": "\n", "C-j": "\n", "Tab": "\t"}
# Terminal emulators and multiplexers that run the command they are given in a new terminal.
_TERMINALS = {
    "gnome-terminal", "xterm", "konsole", "alacritty", "x-terminal-emulator", "xfce4-terminal", "terminator", "tilix",
    "ghostty", "foot", "urxvt", "rxvt", "st", "wt", "kitty", "kitten", "wezterm", "screen", "osascript", "wtype", "expect",
}  # fmt: skip


# The coding agents' own programs (each harness's `bins`, an editor's or a terminal's aside): an agent that starts one
# hands it a prompt, which that session's prompt hook would read as the person's typed words (`claude -p "approve
# SPEC-1"`). Each is a sender of a whole message, held to the prompt hook's own parser.
_NOT_AGENTS = frozenset({"cursor", "zed", "warp"})
AGENT_PROGRAMS = frozenset(b for h in config.HARNESSES.values() for b in h.bins) - _NOT_AGENTS
# Programs that fetch and run a package (`npx @anthropic-ai/claude-code`), with the subcommand that does, if any.
_PACKAGE_RUNNERS: dict[str, frozenset[str] | None] = {
    "npx": None, "bunx": None, "pnpx": None, "uvx": None, "pipx": frozenset({"run"}), "pnpm": frozenset({"dlx", "exec", "x"}),
    "yarn": frozenset({"dlx", "exec"}), "npm": frozenset({"exec", "x"}), "bun": frozenset({"x"}), "deno": frozenset({"run", "x"}),
}  # fmt: skip
# Programs that run a script the guard does not read (`node .../cli.js`), which may be an agent's own program.
_SCRIPT_RUNNERS = frozenset({"node", "nodejs", "deno", "tsx", "ts-node", "bun"})
# A local OpenCode server's message API (`curl -d ... http://127.0.0.1:4096/session/<id>/message`): what it posts
# reaches a session as the person's prompt.
_HTTP_CLIENTS = frozenset({"curl", "wget", "http", "https", "xh"})
# Assignments on the command that move where an HTTP client reads its config file from.
_CLIENT_CONFIG_HOMES = frozenset({"CURL_HOME", "XDG_CONFIG_HOME", "HOME", "WGETRC", "SYSTEM_WGETRC"})
_AGENT_SERVER_MESSAGE = re.compile(r"/session/[^/\s]+/(?:message|prompt_async|command|shell)\b|/tui/(?:append-prompt|submit-prompt|execute-command)\b")


def _reads_request_file(name: str, arg: str) -> bool:
    """Whether an HTTP client's argument reads its URLs or options from a file the guard does not read: curl's `-K`
    (alone, in a cluster, or glued to its value), `--config`, or a `--url=@<file>`; wget's `-i`, `-e`, `--input-file`,
    `--execute`, or `--config`, each also abbreviated as wget's option parser takes them."""
    letters = "K" if name == "curl" else "ie" if name == "wget" else ""
    longs = ("--config",) + (("--input-file", "--execute") if name == "wget" else ())
    if arg.startswith("--"):
        opt = arg.split("=", 1)[0]
        abbreviated = name == "wget" and len(opt) >= 4 and any(full.startswith(opt) for full in longs)
        return opt in longs or abbreviated or arg.startswith("--url=@")
    return arg.startswith("-") and any(c in arg[1:] for c in letters)


def _names_agent(word: str) -> bool:
    """Whether a program or package name is a coding agent's: `claude`, `claude-code`, `@anthropic-ai/claude-code@1`,
    `opencode-ai`."""
    base = word.rsplit("/", 1)[-1].split("@", 1)[0].casefold()
    return any(base == b or base.startswith(f"{b}-") for b in AGENT_PROGRAMS)


def _starts_agent(argv: list[str]) -> bool:
    """Whether a command starts a coding agent: its own program, one a package runner fetches, or a script a runtime
    runs, which the guard cannot read (failing closed)."""
    if not argv:
        return False
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if _names_agent(name):
        return True
    if name in _PACKAGE_RUNNERS:
        subs = _PACKAGE_RUNNERS[name]
        words = [a for a in args if not a.startswith("-")]
        if subs is not None and words[:1] and words[0] not in subs:
            return False
        # Every word and option value counts (`--package=@anthropic-ai/claude-code`, `-p opencode-ai`): a misread
        # one can only add a match, never hide one.
        return any(_names_agent(a.split("=", 1)[-1]) for a in args)
    return False


_RUNTIME_SUBCOMMANDS = frozenset({"run", "x", "exec", "test"})


def _script_arguments(argv: list[str]) -> list[str]:
    """The arguments a runtime hands its script: the words after the runtime's subcommand (`run`) and the script."""
    words = argv[1:]
    while words and words[0].startswith("-") and words[0] not in ("-", "--"):  # the runtime's own options
        words = words[1:]
    if words and words[0] in _RUNTIME_SUBCOMMANDS:
        words = words[1:]
    # One word names the script; `-` (the script from stdin) and `--` name none, so every word after them counts.
    # Dropping too few can only add a match, never hide one.
    return words[1:] if words and words[0] not in ("-", "--") else words[1:] if words else []


def _runs_unread_script(argv: list[str]) -> bool:
    """Whether a runtime runs a script the guard does not read (`node .../cli.js`), which may be an agent's own
    program: held to the prompt hook's own reading of a decision, never to every word (`bun run ship` is a build)."""
    return bool(argv) and shell_parser.program_name(argv[0]) in _SCRIPT_RUNNERS and any(not a.startswith("-") for a in argv[1:])


def _sends_input(sc: shell_parser.SimpleCommand) -> bool:
    """Whether a simple command sends text into another terminal or program, or starts a program in another terminal,
    where it would run as if a person typed it (the module docstring lists the senders)."""
    argv = shell_parser.program_argv(sc.argv)
    if any(t.startswith((*_TTY_DEVICES, "/dev/tcp/", "/dev/udp/")) for t in sc.out):
        return True  # a terminal, or bash's raw socket to a local server
    if not argv:
        return False
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if _starts_agent(argv):
        return True
    if name in _HTTP_CLIENTS and (
        any(_AGENT_SERVER_MESSAGE.search(urllib.parse.unquote(a)) or _reads_request_file(name, a) for a in args)
        or any(a == "--url" and nxt.startswith("@") for a, nxt in zip(args, args[1:], strict=False))
        or any(w.split("=", 1)[0] in _CLIENT_CONFIG_HOMES for w in sc.argv[: len(sc.argv) - len(argv)])
    ):
        return True
    if name == "xargs":  # `... | xargs tmux send-keys -t 0`: the command xargs runs
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in ("-I", "-n", "-L", "-P", "-d", "-E", "-s", "-a") else 1
        return _sends_input(shell_parser.SimpleCommand(args[i:]))
    if name == "tee":
        return any(a.startswith(_TTY_DEVICES) for a in args)
    if name == "orca":  # guard/orca_commands.py: a command that types text, starts an agent, or the guard can't read
        return any(f(args) for f in (orca_commands.types_text, orca_commands.passes_raw, orca_commands.starts_agent, orca_commands.unreadable))
    if name == "tmux":  # anything but its read-only commands (guard/tmux_commands.py)
        found, unreadable = tmux_commands.commands(args)
        return unreadable or not found <= tmux_commands.READ_ONLY
    if name == "zellij":
        return bool({"run", "action", "edit"} & set(args))
    if name == "open":
        return any(a in ("-a", "-b", "--args") or (a[:2] in ("-a", "-b") and not a.startswith("--")) for a in args)
    if name in _TERMINALS:
        return True
    if name in _KEY_SENDERS:
        return bool(_KEY_SENDERS[name] & set(args))
    return False


def _received_forms(argv: list[str]) -> list[str]:
    """The text a sender's words make once the receiving program has them: joined with spaces and run together,
    with tmux key names as their characters, and each word parsed again as the shell that runs it would parse it.
    Whitespace runs collapse to one space."""
    keys = [_KEY_NAMES.get(a, a) for a in argv]
    forms = [" ".join(keys), "".join(keys)]
    for a in argv:
        try:
            toks = shell_parser.shell_tokens(a)
        except ValueError:
            continue
        forms += [" ".join(toks), "".join(toks)]
    return [re.sub(r"\s+", " ", f) for f in forms]


def _types_approval(sc: shell_parser.SimpleCommand) -> bool:
    """A simple command that sends input, whose text carries an approval once quoting and escaping are undone, or the
    words the person types as a decision (`approve SPEC-1`, `land it`, `publish`) as one of its arguments."""
    argv = shell_parser.program_argv(sc.argv)
    if not _sends_input(sc):
        # A runtime's first words name what it runs (`bun run ship`, `node cli.js`); the words after them are what the
        # script gets, and may be a prompt: read joined and one by one, as the prompt hook reads one.
        return _runs_unread_script(argv) and (
            any(_APPROVAL_RECEIVED.search(f) for f in _received_forms(argv)) or _reads_as_decision(["", *_script_arguments(argv)])
        )
    if argv and shell_parser.program_name(argv[0]) in _HTTP_CLIENTS:
        return True  # a message posted to an agent's server reaches it as the person's prompt; its body may be a file
    if any(_APPROVAL_RECEIVED.search(f) for f in _received_forms(argv)):
        return True
    if _orca(argv) and _orca_decides(argv[1:]):
        return True
    if _orca(argv) and not orca_commands.types_text(argv[1:]):
        return False  # it types no text: `_orca_decides` read its prompt, its spec, and its words
    if _hands_a_message(argv):
        # A message arrives whole: it passes for the person's decision when the whole of it reads as one, by the prompt
        # hook's own parser.
        return _reads_as_decision(argv)
    return any(_TYPED_DECISION.search(f) for f in _received_forms(argv))


_CONFIG_FOLDERS = ("HOME", "GH_CONFIG_DIR", "GLAB_CONFIG_DIR", "XDG_CONFIG_HOME")
_GIT_CONFIG_READS = frozenset({"--get", "--get-all", "--get-regexp", "-l", "--list", "get", "list", "--show-origin"})


def runs_elsewhere(simple: list[shell_parser.SimpleCommand]) -> bool:
    """Whether a command line may run git, `gh`, or `glab` against something other than what the guard reads before it
    runs: it changes folder (`cd`, `pushd`, `popd`), sets a config folder or a `GIT_` value for the commands after it,
    or writes git's config, a remote, or a `gh`/`glab` alias first (`git config alias.p push && git p`)."""
    for sc in simple:
        argv = shell_parser.program_argv(sc.argv) or sc.argv
        if not argv:
            continue
        name = shell_parser.program_name(argv[0])
        if name in ("cd", "pushd", "popd"):
            return True
        if name in ("export", "declare", "typeset", "local", "readonly") or all("=" in w and not w.startswith("-") for w in sc.argv):
            if any(w.split("=", 1)[0] in _CONFIG_FOLDERS or w.startswith("GIT_") for w in sc.argv):
                return True
        sub = git_commands.sub_index(argv) if name == "git" else None
        if sub is not None and argv[sub] == "config" and argv[sub + 1 : sub + 2] != [] and argv[sub + 1] not in _GIT_CONFIG_READS:
            return True
        if sub is not None and argv[sub] == "remote" and set(argv[sub + 1 : sub + 2]) & {"add", "set-url", "rename", "remove", "rm"}:
            return True
        if name in ("gh", "glab") and "alias" in argv[1:2] and set(argv[2:3]) & {"set", "import"}:
            return True
    return False


def _reads_as_decision(argv: list[str]) -> bool:
    """Whether a program's arguments, from any one on, read as a person's typed decision by the prompt hook's parser."""
    words = [a.split("=", 1)[1] if a.startswith("--") and "=" in a else a for a in argv[1:]]  # `--text=approve SPEC-1`
    if any(map(orca_commands.hides_text, words)):
        return True  # a character that edits the text, or that another parser reads as a space: fails closed
    return any(workitems.grants(" ".join(words[i:])) or workitems.grants(words[i]) for i in range(len(words)))


def _orca_decides(args: list[str]) -> bool:
    """Whether an orca command may pass for the person's decision, by every reading that may apply, so none returns past
    another: a prompt or a Task's spec, which arrives whole as an agent's first prompt and passes when the prompt hook's
    own parser reads it as one, and any run of its words outside the flag values, read as a typed decision would be.
    A word that hides text fails closed. `emulator exec` is held to its allowlist on its own (forbidden_action)."""
    words = orca_commands.non_value_words(args)
    return (
        any(workitems.grants(p) for p in orca_commands.prompts(args))
        or any(map(orca_commands.hides_text, args))
        or any(workitems.grants(" ".join(words[i:])) for i in range(len(words)))
    )


def _runs_raw(sc: shell_parser.SimpleCommand) -> bool:
    """Whether a simple command may be an `orca emulator exec`, which hands its `--command` to a device shell."""
    argv = shell_parser.program_argv(sc.argv)
    return _orca(argv) and orca_commands.passes_raw(argv[1:])


def _orca(argv: list[str]) -> bool:
    return bool(argv) and shell_parser.program_name(argv[0]) == "orca"


def _starts_orca_agent(argv: list[str]) -> bool:
    """Whether an orca command may start an agent with a first prompt, and types no other text anywhere."""
    return _orca(argv) and not orca_commands.types_text(argv[1:]) and not orca_commands.passes_raw(argv[1:])


def _hands_a_message(argv: list[str]) -> bool:
    """Whether a sender hands another agent a whole message (`orca orchestration send|ask|reply|dispatch`, or a coding
    agent's own program started with a prompt), not keys."""
    if _starts_agent(argv):
        return True
    if not argv or shell_parser.program_name(argv[0]) != "orca":
        return False
    words = shell_parser.positional_words(argv[1:], set())
    return words[:1] == ["orchestration"] and bool({"send", "ask", "reply", "dispatch"} & set(words[1:2]))


# What tmux reads as a key name, not text: modified keys (`C-u`, `M-b`, `S-Left`, `^U`), function keys, the keypad, and
# the named keys. Of them only `_KEY_NAMES` (Enter, Space, Tab) may be sent: any other edits or moves within the line
# a terminal receives, so no reading of the sent text says what the prompt finally holds (`xapprove`, Home, Delete).
_TMUX_KEY = re.compile(
    r"(?:[CMS]-)+.+|\^.|F(?:[1-9]|1[0-2])|KP\w+|BSpace|BTab|DC|Delete|End|Escape|Home|IC|Insert|NPage|PageDown|PgDn|PPage|PageUp|PgUp"
    r"|Up|Down|Left|Right|Any|MouseDown\w*|MouseUp\w*|MouseDrag\w*|WheelUp\w*|WheelDown\w*",
    re.I,  # tmux reads key names in any case: `bspace`, `home`, `up`
)
_SENDABLE_KEYS = frozenset(k.lower() for k in ("Enter", "KPEnter", "Return", "C-m", "C-j", "Space", "Tab"))


# A shell expansion in a word: the guard sees `$(cat f)` or `$WORDS`, never the text the receiver gets. Globs and
# braces (`appro*`, `{a,b}`) turn into file names the same way.
_EXPANSION = re.compile(r"\$[({A-Za-z_0-9@*#?!-]|`|[*?\[{]")
# The only options xdotool's and ydotool's `type` may carry: none of them reads text from anywhere.
_TYPE_OPTIONS = frozenset({"--delay", "--clearmodifiers", "--window", "--key-delay", "-d"})


# The options a plain `tmux send-keys` call may carry: the global ones with a value (-L, -S, -T), the target and the
# repeat count (-t, -N), and the literal and reset flags (-l, -R). Any other (-H, -X, -K, -M, ...) is not plain text.
_SEND_KEYS_VALUES = frozenset({"-L", "-S", "-T", "-t", "-N"})
_SEND_KEYS_FLAGS = frozenset("lR")


def _plain_send_keys_options(args: list[str]) -> bool:
    """Whether every option of a tmux call is one a plain `send-keys` of text may carry."""
    skip = False
    for a in args:
        if skip:
            skip = False
        elif a in _SEND_KEYS_VALUES:
            skip = True
        elif a.startswith("-") and len(a) > 1 and not (a[1] != "-" and set(a[1:]) <= _SEND_KEYS_FLAGS):
            return False
    return True


def _hidden_keys(sc: shell_parser.SimpleCommand) -> bool:
    """A sender whose text the guard cannot read for what the receiver ends up with, so it fails closed:
    - text from somewhere else: an expansion (`$(cat f)`, `$WORDS`, a backtick), a file or stdin (`xdotool type
      --file`, a redirect, a pipe, `xargs`), or a tmux buffer (`load-buffer`, `paste-buffer`);
    - codes and edits: `tmux send-keys -H` (hex), a key name other than Enter, Space, and Tab, xdotool's and
      ydotool's key sequences, or a control character in typed text.
    An agent types plain text, which the guard reads, never codes, edits, or text it fetches."""
    argv = shell_parser.program_argv(sc.argv)
    if not argv or not _sends_input(sc):
        return False
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if sc.inp or sc.after == "|" or any(c in a for a in args for c in "\x08\x15\x17\x7f\x1b"):
        return True
    if _orca(argv) and orca_commands.unreadable(args):
        return True  # any orca command: a prompt that hides text, or a word that may change the command or the prompt
    if _starts_orca_agent(argv):  # its prompt and the words that pick its command were read: the words that run it
        return any(_EXPANSION.search(a) for a in sc.argv[: len(sc.argv) - len(argv)])
    if any(_EXPANSION.search(a) for a in sc.argv[1:]) or name == "xargs":
        return True
    if name in _KEY_SENDERS and "type" in args and any(a.startswith("-") and a.split("=", 1)[0] not in _TYPE_OPTIONS for a in args):
        return True  # an option the guard does not know may read the text from a file (`--file`, `-f`, `--fi`)
    if name == "tmux":
        # An allowlist: read-only commands, and `send-keys` with plain text; any other command runs, pastes, binds, or
        # prompts with text the guard cannot read where it lands.
        found, unreadable = tmux_commands.commands(args)
        if unreadable or found - tmux_commands.READ_ONLY - {tmux_commands.SEND_KEYS} - tmux_commands.RUNS_A_COMMAND:
            return True
        if tmux_commands.SEND_KEYS in found and not _plain_send_keys_options(args):
            return True  # -H (hex), -X (copy-mode commands), -K (key tables), -M (mouse): not plain text
        return any(_TMUX_KEY.fullmatch(a) and a.lower() not in _SENDABLE_KEYS for a in args)
    return name in _KEY_SENDERS and bool({"key", "keydown", "keyup"} & set(args))


# Checks on the raw text of a command the shell check cannot parse: each is a denial the parsed checks would make.
_RAW_MERGE = re.compile(r"\b(?:gh|glab)(?:\.exe)?\s+(?:(?:-R|--repo)[\s=]+\S+\s+)?(?:pr|mr)\s+(?:merge|review|approve|accept)\b", re.I)
_RAW_API = re.compile(
    r"\b(?:gh|glab)(?:\.exe)?\s+api\b[^\n;&|]*(?:/pulls/[^/\s]+/(?:merge|reviews|update-branch)\b|/merges\b|/merge_requests/[^/\s]+/(?:merge|approve|unapprove)\b)",
    re.I,
)
_RAW_FORCE_PUSH = re.compile(r"\bgit(?:\.exe)?\b[^\n;&|]*\spush\b[^\n;&|]*\s(?:--force\b|--force-with-lease|--mirror\b|--delete\b|-[A-Za-z]*[fd]\b|\+\S)", re.I)
FAIL_CLOSED_ENV = repo_config.FAIL_CLOSED_ENV


def _raw_denial(command: str) -> str | None:
    """Why a command the shell check cannot parse is denied anyway, by its text alone, or None. The text is read as
    written and with each backslash-newline gone, as bash joins it (`gh pr mer\\<newline>ge`)."""
    command = command + "\n" + command.replace("\\\n", "")
    if approval_text.APPROVAL_TEXT.search(command):
        return f"the shell check cannot parse the command, and its text carries an approval (`aidd approve`, `aidd land`, `/aidd approve`, or a decision record): agents never approve or merge; {verdicts.TELL_A_PERSON}"
    if _RAW_MERGE.search(command) or _RAW_API.search(command) or _GRAPHQL_WRITES.search(command):
        return f"the shell check cannot parse the command, and its text approves, reviews, or merges a pull or merge request: agents never approve or merge; {verdicts.TELL_A_PERSON}"
    if _RAW_FORCE_PUSH.search(command):
        return "the shell check cannot parse the command, and its text force-pushes or deletes a branch, maybe a protected branch. An agent never rewrites history on the default branch. Push a new commit instead, or ask a person"
    if RAW_PUBLISH.search(command):
        return "the shell check cannot parse the command, and its text pushes or opens a pull or merge request, which takes work off this machine. Write it so the check can read it, or ask the person to type `publish`"
    return None


def _with_indirect(simple: list[shell_parser.SimpleCommand]) -> list[shell_parser.SimpleCommand]:
    """`simple`, each followed by what it has xargs, find, or their kin run (indirect_runs), so every check below reads those too, with
    the words they fill in as names only the shell resolves; by the command each git, gh, glab, aidd, tmux, or orca
    word starts (indirect_runs.named_runs), for a program no table names that runs a command; and by the program an
    orca command hands its words to (`orca claude-teams -p ...` runs Claude Code)."""
    runs = [found for sc in simple for found in (sc, *indirect_runs.indirect_commands(sc))]
    runs = [found for sc in runs for found in (sc, *indirect_runs.named_runs(sc))]
    return [found for sc in runs for found in (sc, *_orca_passes_to(sc))]


def _orca_passes_to(sc: shell_parser.SimpleCommand) -> list[shell_parser.SimpleCommand]:
    """The command an orca command runs in its place, with the same words (orca_commands.passed_through), or none."""
    argv = shell_parser.program_argv(sc.argv)
    if not argv or shell_parser.program_name(argv[0]) != "orca":
        return []
    passed = orca_commands.passed_through(argv[1:])
    return [shell_parser.SimpleCommand(passed, inp=sc.inp, depth=sc.depth, after=sc.after)] if passed else []


# `gh pr review`'s options that take the next word as their value, and a short cluster that ends in one (`-cb`).
_REVIEW_VALUES = frozenset({"-b", "--body", "-F", "--body-file", "-R", "--repo"})
_TAKES_NEXT = re.compile(r"-[^-bFR]*[bFR]")
# The start of a word that carries its own value (`--body="$X"`, `-b"$X"`): whatever the rest expands to is that value.
_CARRIES_VALUE = re.compile(r"--(?:body|body-file|repo)=|-[^-bFRa]*[bFR]")


def _reviews_unread(args: list[str]) -> bool:
    """Whether a `gh pr review` may approve, read in order as gh's flag parser reads it: `--approve` or `-a`, alone or
    in a cluster before a letter that takes a value (`-ab LGTM`, `-aF body.txt`), up to a `--` that is no option's
    value (`-b -- --approve` approves). A word the shell may split counts anywhere, a value too (`-b *` with a file
    named `--approve`), and so does a quoted expansion that is no value, which may be `--approve` itself. A quoted
    text (`-b 'why?'`) or a quoted expansion as a value (`-b "$WHY"`) is one word, the value."""
    value = False
    for a in args:
        if value:
            value = False
            if shell_words.may_split(a):
                return True
            continue
        if a == "--":
            return False
        if not shell_words.literal(a):
            if shell_words.may_split(a) or not _CARRIES_VALUE.match(shell_words.literal_prefix(a)):
                return True
            continue
        if a == "--approve" or a.startswith("--approve=") or re.match(r"-[^-bFR]*a", a):
            return True
        value = a in _REVIEW_VALUES or bool(_TAKES_NEXT.fullmatch(a))
    return False


def forbidden_action(command: str, root: str | None = None, *, powershell: bool = False, quoting: bool = True) -> str | None:
    """Why an agent may not run `command`, or None. Agents never approve, merge, or post an approval.

    `root`, the repository the command runs in, lets a push with no refspec resolve to the current branch and adds the
    repository's default branch to the protected ones. `powershell` undoes PowerShell's backtick escapes first.
    `quoting` reads each word's quoting from the text (shell_parser.simple_commands): never for text the guard built.
    A command the check cannot parse is held to its raw text, and denied outright where the guard fails closed
    (repo_config.fails_closed)."""
    as_written = command  # a backtick or a newline here reaches a device shell as one (`emulator exec`)
    if powershell:
        command = shell_parser.powershell_plain(command)
    broken: list[str] = []
    simple = _with_indirect(shell_parser.simple_commands(command, broken=broken, quoting=quoting))
    if broken:
        why = _raw_denial(command)
        if why:
            return why
        if repo_config.fails_closed(root):
            return (
                f"the shell check cannot parse the command (an unbalanced quote), and {verdicts.FAILS_CLOSED} denies what it cannot check. "
                "Rewrite it with balanced quotes, or put the text in a file"
            )
    reads = all(approval_text.only_reads(shell_parser.program_argv(sc.argv)) for sc in simple)
    # A file's text a here-document gives `cat` or `tee` is data (a handoff note, a doc): read the line without it.
    text = approval_text.without_file_text(command)
    if text != command:
        simple = _with_indirect(shell_parser.simple_commands(text, quoting=quoting))
    if any(_sends_input(sc) and shell_parser.program_name((shell_parser.program_argv(sc.argv) or [""])[0]) in _HTTP_CLIENTS for sc in simple):
        return (
            "the command posts to a local agent server's message API, or reads its request from a file, a config, or the "
            "environment the guard does not read: a message there reaches an agent as the person's prompt. Name the URL and "
            "the body on the command line, and post no message to an agent's session"
        )
    # A newline, a carriage return, or a backtick anywhere on the line counts, as written: the shell reader turns a
    # newline inside a quoted `--command` into a separator, and PowerShell's reading drops a backtick a device shell runs.
    # PowerShell's `--%` hands the rest of the line to the program unread.
    raw = [sc for sc in simple if _runs_raw(sc)]
    if raw and (
        any(c in as_written for c in "\n\r`")
        or (powershell and "--%" in as_written)
        or not all(orca_commands.raw_allowed(shell_parser.program_argv(sc.argv)[1:]) for sc in raw)
    ):
        return (
            "the command runs a device command through `orca emulator exec` that the guard does not allow there. Only taps, buttons, "
            "rotation, key presses that type no text, app starts and stops, and reads run raw, with plain words. Keep the line free "
            "of newlines and backticks, and join device commands with `&&` inside one `--command`. Type text with "
            "`orca emulator type <text>`, which the guard reads as typed text. Send a gesture with `orca emulator gesture`, "
            "or ask the person to run it in their own terminal"
        )
    if (approval_text.APPROVAL_TEXT.search(text) and any(_sends_input(sc) for sc in simple)) or any(_types_approval(sc) for sc in simple):
        return (
            "the command types an approval or a person's decision word (`approve`, `land`, `publish`, `merge`, `automate`, `explore`) into another "
            "terminal or program, where it would pass for the person's own keyboard. Word the message without them. " + verdicts.APPROVE_IN_A_DIALOG
        )
    if any(_hidden_keys(sc) for sc in simple):
        return (
            "the command sends another terminal or program text the guard cannot read: an expansion (`$(cat f)`, `$VAR`), a file, "
            "stdin, a tmux buffer, key codes, or edit keys. Send the plain text itself instead"
        )
    if not reads and (why := approval_text.approval_text_denial(text, simple, root)):
        return why
    for sc in simple:
        argv = shell_parser.program_argv(sc.argv)
        if not argv:
            continue
        name, args = shell_parser.program_name(argv[0]), argv[1:]
        if name == "tmux" and tmux_commands.commands(args)[0] & tmux_commands.RUNS_A_COMMAND:
            # The shell command tmux would run, read as the agent's own. tmux joins the words after the command into it
            # (`tmux new-window git push --force origin main`), so every run of them from each word on is read.
            for i in range(len(args)):
                for nested in {shlex.join(args[i:]), " ".join(args[i:])}:
                    if why := forbidden_action(nested, root, powershell=powershell, quoting=False):
                        return f"the command tmux would run: {why}"
        what = _aidd_decision(argv)
        if what in ("approve", "land", "publish") and _person_said(what, argv, root):
            continue
        if what == "hook":
            return "`aidd hook`: the harness runs aidd's hooks, never an agent, since the prompt hook records the person's typed decisions. Leave it to the harness"
        if what == "mcp":
            return (
                "`aidd mcp`: the harness starts aidd's MCP server from its own config, never an agent, since its dialogs record the "
                "person's decisions. Call the aidd tools the session already has, or ask the person to type the decision"
            )
        if what == "worktrees clean":
            return (
                "`aidd worktrees clean` removes worktrees, which is the person's call. Next: run `aidd worktrees clean --dry-run` "
                "and show the person what it would remove; they run `aidd worktrees clean` at their terminal"
            )
        if what:
            if what.startswith("proposal"):
                typed = "decide <proposal> go" if what.endswith("decide") else "sign off <proposal>"
                return (
                    f"`aidd {what}`: agents never decide for a person. They type `{typed}` at the prompt, and aidd records it "
                    "from their own words; in Claude Code, the aidd MCP tool asks them in a dialog instead"
                )
            if what == "publish":
                return (
                    "`aidd publish` takes work off this machine, which is the person's step: once they type `publish` for this head, "
                    "run it. In Claude Code, the aidd MCP tool `publish` asks them in a dialog instead"
                )
            return f"`aidd {what}`: an agent never runs it; the person decides. {verdicts.APPROVE_IN_A_DIALOG}"
        if name in ("gh", "glab") and any(_EXPANSION.search(w) for w in shell_parser.positional_words(args, GH_VALUE_FLAGS)[:2]):
            return (
                f"`{name}` with a command only the shell, or the input of xargs or find, names: it could approve or merge, which "
                f"agents never do. Name the {name} command plainly"
            )
        if name in ("gh", "glab") and (
            why := ref_writes.cli_settings_denial(name, args) or ref_writes.cli_environment_denial(_with_indirect(shell_parser.simple_commands(text)))
        ):
            return why
        if name == "gh":
            words = shell_parser.positional_words(args, GH_VALUE_FLAGS)
            if words[:2] == ["pr", "review"] and _reviews_unread(args):
                return "`gh pr review --approve`: an agent never approves; the person gives Spec approval and Merge approval. " + verdicts.APPROVE_IN_A_DIALOG
            if words[:2] == ["pr", "merge"]:
                return f"`gh pr merge`: agents never merge; a human merges once `aidd/gate` passes, so {verdicts.TELL_A_PERSON}"
            if words[:1] == ["api"] and _api_write(args[args.index("api") + 1 :], _GH_MERGE, _GH_REVIEW):
                return f"a `gh api` call that approves or merges: agents never approve or merge; {verdicts.TELL_A_PERSON}"
        elif name == "glab":
            words = shell_parser.positional_words(args, GH_VALUE_FLAGS)
            if words[:1] == ["mr"] and len(words) > 1 and words[1] in ("approve", "merge", "accept"):
                return f"`glab mr {words[1]}`: agents never approve or merge; a human does, once `aidd/gate` passes, so {verdicts.TELL_A_PERSON}"
            if words[:1] == ["api"] and _api_write(args[args.index("api") + 1 :], _GL_MERGE, _GL_REVIEW):
                return f"a `glab api` call that approves or merges: agents never approve or merge; {verdicts.TELL_A_PERSON}"
        elif name == "git" and (sub := git_commands.sub_index(argv)) is not None and argv[sub] == "push":
            why = git_commands.push_denial(argv[sub:], root)
            if why:
                return why
    if opaque := indirect_runs.first_opaque_program(command):
        return (
            f"the command runs a program only the shell, or the input of xargs or find, names (`{opaque}`), so the guard "
            "cannot check what it does: it could approve, merge, or switch branches. Name the program plainly"
        )
    if stream := indirect_runs.first_stream_program(command):
        return (
            f"`{stream}` runs code from a pipe or a stream the command never shows, so the guard cannot check what it does: "
            "it could approve, merge, or move a branch. Put the commands on the line itself, or in `bash -c '...'`"
        )
    if why := ref_writes.unread_ref_write_denial(simple, root):
        return why
    if not root:
        return None
    # Read without the here-document bodies too, where a body's line (`cd ../wt`) is no command that moves the folder.
    stripped = shell_parser.split_heredocs(command)[0]
    for reading in (simple, *([_with_indirect(shell_parser.simple_commands(stripped))] if stripped != command else [])):
        if why := git_commands.base_branch_denial(reading, root) or git_commands.goal_branch_denial(reading, root):
            return why
        if why := git_commands.explore_branch_denial(reading, root):
            return why
    # Last: a push or a PR/MR that takes work off this machine, after every more specific reason a push may be denied.
    moves = runs_elsewhere(simple)
    for sc in simple:
        argv = shell_parser.program_argv(sc.argv)
        if argv and (why := leaves_this_machine(shell_parser.program_name(argv[0]), argv, root, sc.argv, elsewhere=moves)):
            return why
    return None
