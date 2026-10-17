"""The commands that approve or merge: the platform CLIs and APIs, `aidd approve` and `aidd ship` through any
wrapper, and an approval typed into another terminal (`forbidden_action`).
"""

from __future__ import annotations

import re
import shlex

from aidd import workitems
from aidd.guard import git_commands, ref_writes, repo_config, shell_parser, tmux_commands, verdicts
from aidd.kernel import git

_GRAPHQL_WRITES = re.compile(
    r"\b(?:mergePullRequest|addPullRequestReview|submitPullRequestReview|enablePullRequestAutoMerge|approvePullRequest|"
    r"mergeBranch|mergeMergeRequest|mergeRequestAccept|mergeRequestApprove)\b"
)
_AIDD_APPROVE = re.compile(r"/aidd\s+approve", re.I)
# What reads as an approval, not a mention of one: the command, then a work item id and a hash or commit.
_APPROVAL_LINE = re.compile(r"/aidd\s+approve(?:-spec|-merge)?\s+[A-Za-z][\w-]*-\d+\s+\S+", re.I)
_APPROVAL_RECORD = re.compile(r"refs/aidd/approvals|Aidd-Merge-Approval", re.I)
_MERGE_TRAILER_TEXT = re.compile(r"Aidd-Merge-Approval", re.I)


_GH_VALUE_FLAGS = {"-R", "--repo", "-b", "--body", "-F", "--body-file", "-t", "--subject", "--author-email", "-H", "--header", "-X", "--method"}
_GH_API_VALUE_FLAGS = {
    "-X", "--method", "-H", "--header", "-f", "--raw-field", "-F", "--field", "--input", "-q", "--jq", "-t", "--template",
    "--hostname", "-p", "--preview", "--cache",
}  # fmt: skip


def _api_write(args: list[str], merge: re.Pattern, review: re.Pattern) -> bool:
    """`gh api` or `glab api` with an endpoint that merges or approves, called with a writing method."""
    words = shell_parser.positional_words(args, _GH_API_VALUE_FLAGS)
    endpoint = words[0] if words else ""
    method = (shell_parser.flag_value(args, "-X", "--method") or "").upper()
    has_fields = any(a in ("-f", "-F", "--field", "--raw-field", "--input") or a.startswith(("--field=", "--raw-field=", "--input=")) for a in args)
    writes = method in ("POST", "PUT", "PATCH") or (not method and has_fields)
    if endpoint.strip("/") == "graphql":
        return bool(_GRAPHQL_WRITES.search(" ".join(args)))
    # A GET of the merge endpoint only asks whether the PR merged; a review listing only reads approvals.
    return bool(merge.search(endpoint) or review.search(endpoint)) and writes


_GH_MERGE = re.compile(r"/pulls/[^/]+/merge\b|/merges\b|/pulls/[^/]+/update-branch\b")
_GH_REVIEW = re.compile(r"/pulls/[^/]+/reviews\b")
_GL_MERGE = re.compile(r"/merge_requests/[^/]+/merge\b")
_GL_REVIEW = re.compile(r"/merge_requests/[^/]+/(?:approve|unapprove)\b")


def _only_reads(argv: list[str]) -> bool:
    """A search or a view, which may name `/aidd approve` without posting it: `grep -rn '/aidd approve' docs/`."""
    if not argv:
        return True
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if name == "sed":
        return not any(a == "-i" or a.startswith(("-i", "--in-place")) for a in args)
    if name == "git":
        return shell_parser.positional_words(args, {"-C", "-c"})[:1] in [[w] for w in _GIT_READS]
    return name in shell_parser.SEARCHERS


# git commands that only read, refs and objects included: `git for-each-ref refs/aidd/approvals` lists, never records.
_GIT_READS = ("grep", "log", "show", "diff", "blame", "for-each-ref", "show-ref", "rev-parse", "rev-list", "cat-file", "shortlog")


def _describes_only(argv: list[str]) -> bool:
    """A command whose text goes where the gate never reads an approval: a commit message, or a pull or merge request's
    title and description (the gate reads approval lines from comments alone). It may mention `/aidd approve`."""
    if not argv:
        return True
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    words = shell_parser.positional_words(args, {"-C", "-c", *_GH_VALUE_FLAGS, "-m", "--message", "-t", "--title", "-d", "--description"})
    if name == "git":
        return words[:1] == ["commit"]
    if name == "gh":
        return words[:2] in (["pr", "create"], ["pr", "edit"])
    if name == "glab":
        return words[:2] in (["mr", "create"], ["mr", "update"])
    return False


def _person_said(what: str, argv: list[str], root: str | None) -> bool:
    """Whether the person already said yes to this `aidd approve` or `aidd ship`, so the agent may run it: their
    standing approval is live (`aidd approve all`), or, for a ship or a Merge approval, their "ship it" covers this
    head (workitems.ship_decision; aidd checks it again and records the approval citing it). Never
    `--confirmed`, which claims a person confirmed elsewhere, and never `aidd approve all`, which only the person starts;
    `aidd approve stop` only takes a standing approval back, so anyone may run it. aidd itself checks the route and the
    head again, and asks for the person when the standing approval does not cover the change."""
    words = next((shell_parser.positional_words(rest, set()) for rest in shell_parser.aidd_runs(argv)), [])
    # `--skip-cooloff` too: skipping the cool-off is the person's own call, on record, never one an agent makes.
    if not root or any(a.startswith(("--confirmed", "--skip-cooloff")) for a in argv):
        return False
    if words[:2] == ["approve", "stop"]:
        return True
    if words[:2] not in (["approve", "spec"], ["approve", "merge"]) and words[:1] != ["ship"]:
        return False
    cfg = repo_config.load_config(root)
    if workitems.live_standing_for(cfg, root) is not None:
        return True
    head = git.run(["rev-parse", "HEAD"], root, check=False).strip()
    merge = what == "ship" or words[:2] == ["approve", "merge"]
    return merge and bool(head) and workitems.ship_said_for(cfg, root, head)


def _aidd_decision(argv: list[str]) -> str | None:
    """`approve`, `ship`, or a proposal's `decide` and `sign-off` when a simple command runs aidd with it
    (`shell_parser.aidd_runs`), as its first positional words, unless it only reads: `--help`, or `--show` (a preview)
    without `--confirmed`."""
    for rest in shell_parser.aidd_runs(argv):
        first = shell_parser.positional_words(rest, set())[:1]
        # `hook` too: the harness runs aidd's hooks, and the prompt hook records what the person typed, so an agent that
        # fed it a prompt of its own would record a decision as theirs.
        what = first[0] if first in (["approve"], ["ship"], ["hook"]) else None
        # `aidd worktrees clean` removes folders: a person's; `--dry-run` only says what it would remove.
        if first == ["worktrees"] and shell_parser.positional_words(rest, set())[1:2] == ["clean"] and "--dry-run" not in rest:
            what = "worktrees clean"
        if first == ["proposal"]:
            # argparse takes `--by X` and `--reason X` before the action too, so any word may be it: fail closed.
            what = next((f"proposal {a}" for a in rest if a in ("decide", "sign-off")), None)
        if what:
            if any(a in ("-h", "--help") for a in rest):
                continue
            if "--show" in rest and not any(a.startswith("--confirmed") for a in rest):
                continue
            return what
    return None


# Text that approves when a person's terminal runs it: `aidd approve`, `aidd ship` (also as `python -m aidd.cli`), a
# proposal's `decide` and `sign-off`, `/aidd approve`, and the local approval records.
_APPROVAL_TEXT = re.compile(
    r"\baidd(?:\.cli|\.__main__)?\s+(?:approve|ship)\b|\baidd(?:\.cli|\.__main__)?\s+proposal\b[^\n;&|]*?\b(?:decide|sign-off)\b"
    r"|/aidd\s+approve|refs/aidd/approvals|Aidd-Merge-Approval",
    re.I,
)
# The words aidd records as the person's own decision when they type them (cli/commands/typed_decisions.py, and
# aidd-mods): typed into another terminal or program by an agent, they would pass for the person's keyboard. Matched
# anywhere, failing closed: a terminal edits what it receives (a backspace, a cleared line), so no reading of the text
# can say what the prompt finally holds. An agent that sends a message there words it without them.
_TYPED_DECISION = re.compile(r"approve|ship|automate", re.I)
# Each describing program's flags whose value is a message or a title: text the gate never reads as a record, the one
# place a command that only describes may name the approvals ref.
_MESSAGE_FLAGS = {"git": ("-m", "--message"), "gh": ("-b", "--body", "-t", "--title"), "glab": ("-d", "--description", "-t", "--title")}


def _brace_variants(text: str, limit: int = 64) -> tuple[list[str], bool]:
    """`text` as bash's brace expansion may turn it into words (`approval{s,}`): each variant, at most `limit`, and
    whether that was all of them. A quoted brace bash leaves alone is expanded here too, so the reading fails closed."""
    todo, done = [text], list[str]()
    while todo and len(done) + len(todo) <= limit:
        t = todo.pop()
        m = re.search(r"\{([^{}]*,[^{}]*)\}", t)
        if m is None:
            done.append(t)
            continue
        todo.extend(t[: m.start()] + part + t[m.end() :] for part in m.group(1).split(","))
    return done + todo, not todo


def _as_git_reads(text: str) -> str:
    """Text as git may receive it: each brace variant bash could make, with each run of slashes as one, the way git
    reads a ref name (`refs/aidd//approvals` is the approvals ref). The match on it ignores case: on a case-insensitive
    disk, an upper-case spelling names the same file. Braces with more variants than the guard reads read as the
    approvals ref itself, failing closed: the variants the guard did not read could spell any name."""
    variants, complete = _brace_variants(text)
    read = " ".join(re.sub(r"/{2,}", "/", v) for v in variants)
    return read if complete else f"{read} {workitems.APPROVALS_REF}"


def _outside_messages(sc: shell_parser.SimpleCommand) -> str:
    """A simple command's text without its message values: environment assignments, wrapper words, and every other
    argument stay, and only the described program's own message flags are skipped."""
    argv = shell_parser.program_argv(sc.argv)
    lead = sc.argv[: len(sc.argv) - len(argv)]  # assignments and wrappers before the program
    flags = _MESSAGE_FLAGS.get(shell_parser.program_name(argv[0]), ()) if argv else ()
    out, skip = list(lead) + argv[:1], False
    for a in argv[1:]:
        if skip:
            skip = False
        elif a in flags:
            skip = True
        elif not a.startswith(tuple(f"{f}=" for f in flags if f.startswith("--"))):
            out.append(a)
    return " ".join(out)


# The same text as the program receives it, after the quoting and escaping a raw match misses: the words may run
# together (`"aid""d approve"`, `aidd Space approve`), so no word boundary is required before `aidd`; the word after
# `approve` or `ship` must end there, as it must for a shell to run it.
_APPROVAL_RECEIVED = re.compile(
    r"aidd(?:\.cli|\.__main__)?\s+(?:approve|ship)(?![A-Za-z0-9_-])"
    r"|aidd(?:\.cli|\.__main__)?\s+proposal(?![A-Za-z0-9_-])[^\n;&|]*?(?:decide|sign-off)(?![A-Za-z0-9_-])"
    r"|/aidd\s+approve|refs/aidd/approvals|Aidd-Merge-Approval",
    re.I,
)
_TTY_DEVICES = ("/dev/tty", "/dev/pts/", "/dev/console")
_KEY_SENDERS = {"xdotool": {"type", "key", "keydown", "keyup"}, "ydotool": {"type", "key"}}


# The key names tmux (and `orca computer press-key`) turns into the characters they type.
_KEY_NAMES = {"Space": " ", "Enter": "\n", "KPEnter": "\n", "Return": "\n", "C-m": "\n", "C-j": "\n", "Tab": "\t"}
# orca subcommands that type into a terminal or an app, start a program in a terminal, or hand text to another agent.
_ORCA_SENDS = {
    "terminal": {"send", "create", "split"},
    "orchestration": {"send", "ask", "reply", "dispatch", "worker-start"},
    "computer": {"type-text", "paste-text", "press-key", "hotkey", "set-value"},
    "emulator": {"type"},
    "worktree": {"create"},
    "automations": {"create", "edit"},
    "type": set(),
}
# Terminal emulators and multiplexers that run the command they are given in a new terminal.
_TERMINALS = {
    "gnome-terminal", "xterm", "konsole", "alacritty", "x-terminal-emulator", "xfce4-terminal", "terminator", "tilix",
    "ghostty", "foot", "urxvt", "rxvt", "st", "wt", "kitty", "kitten", "wezterm", "screen", "osascript", "wtype", "expect",
}  # fmt: skip


def _sends_input(sc: shell_parser.SimpleCommand) -> bool:
    """Whether a simple command sends text into another terminal or program, or starts a program in another terminal,
    where it would run as if a person typed it (the module docstring lists the senders)."""
    argv = shell_parser.program_argv(sc.argv)
    if any(t.startswith(_TTY_DEVICES) for t in sc.out):
        return True
    if not argv:
        return False
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if name == "xargs":  # `... | xargs tmux send-keys -t 0`: the command xargs runs
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in ("-I", "-n", "-L", "-P", "-d", "-E", "-s", "-a") else 1
        return _sends_input(shell_parser.SimpleCommand(args[i:]))
    if name == "tee":
        return any(a.startswith(_TTY_DEVICES) for a in args)
    if name == "orca":
        words = shell_parser.positional_words(args, set())
        if not words or words[0] not in _ORCA_SENDS:
            return False
        subs = _ORCA_SENDS[words[0]]
        return not subs or bool(subs & set(words[1:2]))
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
    words the person types as a decision (`approve SPEC-1`, `ship it`) as one of its arguments."""
    argv = shell_parser.program_argv(sc.argv)
    if not _sends_input(sc):
        return False
    if any(_APPROVAL_RECEIVED.search(f) for f in _received_forms(argv)):
        return True
    if _hands_a_message(argv):
        # A message arrives whole: it passes for the person's decision when the whole of it reads as one, by the prompt
        # hook's own parser.
        words = [a.split("=", 1)[1] if a.startswith("--") and "=" in a else a for a in argv[1:]]  # `--text=approve SPEC-1`
        return any(workitems.grants(" ".join(words[i:])) or workitems.grants(words[i]) for i in range(len(words)))
    return any(_TYPED_DECISION.search(f) for f in _received_forms(argv))


def _hands_a_message(argv: list[str]) -> bool:
    """Whether a sender hands another agent a whole message (`orca orchestration send|ask|reply|dispatch`), not keys."""
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
    if any(_EXPANSION.search(a) for a in sc.argv[1:]) or sc.inp or sc.after == "|" or name == "xargs":
        return True
    if any(c in a for a in args for c in "\x08\x15\x17\x7f\x1b"):
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
    """Why a command the shell check cannot parse is denied anyway, by its text alone, or None."""
    if _APPROVAL_TEXT.search(command):
        return f"the shell check cannot parse the command, and its text carries an approval (`aidd approve`, `aidd ship`, `/aidd approve`, or an approval record): agents never approve or merge; {verdicts.TELL_A_PERSON}"
    if _RAW_MERGE.search(command) or _RAW_API.search(command) or _GRAPHQL_WRITES.search(command):
        return f"the shell check cannot parse the command, and its text approves, reviews, or merges a pull or merge request: agents never approve or merge; {verdicts.TELL_A_PERSON}"
    if _RAW_FORCE_PUSH.search(command):
        return "the shell check cannot parse the command, and its text force-pushes or deletes a branch, maybe a protected branch. An agent never rewrites history on the default branch. Push a new commit instead, or ask a person"
    return None


def forbidden_action(command: str, root: str | None = None, *, powershell: bool = False) -> str | None:
    """Why an agent may not run `command`, or None. Agents never approve, merge, or post an approval.

    `root`, the repository the command runs in, lets a push with no refspec resolve to the current branch and adds the
    repository's default branch to the protected ones. `powershell` undoes PowerShell's backtick escapes first.
    A command the check cannot parse is held to its raw text, and denied outright where the guard fails closed
    (repo_config.fails_closed)."""
    if powershell:
        command = shell_parser.powershell_plain(command)
    broken: list[str] = []
    simple = shell_parser.simple_commands(command, broken=broken)
    if broken:
        why = _raw_denial(command)
        if why:
            return why
        if repo_config.fails_closed(root):
            return (
                f"the shell check cannot parse the command (an unbalanced quote), and {verdicts.FAILS_CLOSED} denies what it cannot check. "
                "Rewrite it with balanced quotes, or put the text in a file"
            )
    reads = all(_only_reads(shell_parser.program_argv(sc.argv)) for sc in simple)
    if (_APPROVAL_TEXT.search(command) and any(_sends_input(sc) for sc in simple)) or any(_types_approval(sc) for sc in simple):
        return (
            "the command types an approval or a person's decision word (`approve`, `ship`, `automate`) into another "
            "terminal or program, where it would pass for the person's own keyboard. Word the message without them. " + verdicts.APPROVE_IN_A_DIALOG
        )
    if any(_hidden_keys(sc) for sc in simple):
        return (
            "the command sends another terminal or program text the guard cannot read: an expansion (`$(cat f)`, `$VAR`), a file, "
            "stdin, a tmux buffer, key codes, or edit keys. Send the plain text itself instead"
        )
    # A commit message or a PR/MR description may mention `/aidd approve`; it may never hold a line that reads as one.
    describes = not _APPROVAL_LINE.search(command) and all(
        _only_reads(shell_parser.program_argv(sc.argv)) or _describes_only(shell_parser.program_argv(sc.argv)) for sc in simple
    )
    if _AIDD_APPROVE.search(command) and not reads and not describes:
        return "the command carries `/aidd approve`: an approval is a human's to post, never an agent's. Leave the line out, and ask the author or an Approver to post it"
    # A command that only describes (a commit message, a PR body) may name the approvals ref inside its message: that
    # writes no record. Anywhere else (an option, an editor or hook a `-c` names, an environment value) it may run one.
    # A merge approval's trailer stays denied anywhere: text that reads as a record is never an agent's.
    # Read as bash passes it on, too: quoting splits the name in the raw text (`approval"s"`), and bash joins it again.
    named_outside = any(_APPROVAL_RECORD.search(_as_git_reads(_outside_messages(sc))) for sc in simple)
    named = _APPROVAL_RECORD.search(command) or named_outside
    if named and not reads and not (describes and not named_outside and not _MERGE_TRAILER_TEXT.search(command)):
        return (
            f"the command names {workitems.APPROVALS_REF} or {workitems.MERGE_TRAILER}, where local approvals are recorded. An approval is a "
            "person's, recorded with `aidd approve` in a terminal an agent did not start. An agent only reads those approvals"
        )
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
                    if why := forbidden_action(nested, root, powershell=powershell):
                        return f"the command tmux would run: {why}"
        what = _aidd_decision(argv)
        if what in ("approve", "ship") and _person_said(what, argv, root):
            continue
        if what == "hook":
            return "`aidd hook`: the harness runs aidd's hooks, never an agent, since the prompt hook records the person's typed decisions. Leave it to the harness"
        if what == "worktrees clean":
            return (
                "`aidd worktrees clean` removes worktrees, which is the person's call. Next: run `aidd worktrees clean --dry-run` "
                "and show the person what it would remove; they run `aidd worktrees clean` at their terminal"
            )
        if what:
            if what.startswith("proposal"):
                tool = "proposal_decide" if what.endswith("decide") else "proposal_sign_off"
                return (
                    f"`aidd {what}`: agents never decide for a person. Call the aidd MCP tool `{tool}`, which asks them in their own dialog; "
                    f"or they type `/aidd {what.removeprefix('proposal ')} <proposal>` (aidd-mods), or run it in a terminal no agent started"
                )
            return f"`aidd {what}`: an agent never runs it; the person decides. {verdicts.APPROVE_IN_A_DIALOG}"
        if name == "gh":
            words = shell_parser.positional_words(args, _GH_VALUE_FLAGS)
            if words[:2] == ["pr", "review"] and any(a in ("--approve", "-a") or a.startswith("--approve=") for a in args):
                return "`gh pr review --approve`: an agent never approves; the person gives Spec approval and Merge approval. " + verdicts.APPROVE_IN_A_DIALOG
            if words[:2] == ["pr", "merge"]:
                return f"`gh pr merge`: agents never merge; a human merges once `aidd/gate` passes, so {verdicts.TELL_A_PERSON}"
            if words[:1] == ["api"] and _api_write(args[args.index("api") + 1 :], _GH_MERGE, _GH_REVIEW):
                return f"a `gh api` call that approves or merges: agents never approve or merge; {verdicts.TELL_A_PERSON}"
        elif name == "glab":
            words = shell_parser.positional_words(args, _GH_VALUE_FLAGS)
            if words[:1] == ["mr"] and len(words) > 1 and words[1] in ("approve", "merge", "accept"):
                return f"`glab mr {words[1]}`: agents never approve or merge; a human does, once `aidd/gate` passes, so {verdicts.TELL_A_PERSON}"
            if words[:1] == ["api"] and _api_write(args[args.index("api") + 1 :], _GL_MERGE, _GL_REVIEW):
                return f"a `glab api` call that approves or merges: agents never approve or merge; {verdicts.TELL_A_PERSON}"
        elif name == "git" and (sub := git_commands.sub_index(argv)) is not None and argv[sub] == "push":
            why = git_commands.push_denial(argv[sub:], root)
            if why:
                return why
    if why := ref_writes.unread_ref_write_denial(simple, root):
        return why
    if not root:
        return None
    return git_commands.base_branch_denial(simple, root) or git_commands.goal_branch_denial(simple, root) or git_commands.explore_branch_denial(simple, root)
