"""tmux as the guard reads it: an allowlist. An agent may run tmux's read-only commands, and `send-keys` with plain
text (guard/approval_commands.py holds that text to its rules); every other tmux command runs, pastes, binds, or
prompts with text the guard cannot read where it lands, so it is denied. Commands are found where tmux finds them
(the first word after the global options, and the word after each `;`), each resolved by tmux's own rule: the command
or its alias exactly, else the one command it is a unique prefix of.
"""

from __future__ import annotations

# Every tmux command (tmux 3.5, `tmux list-commands`), each with its alias.
_COMMANDS = {
    "attach-session": "attach", "bind-key": "bind", "break-pane": "breakp", "capture-pane": "capturep",
    "choose-buffer": None, "choose-client": None, "choose-tree": None, "clear-history": "clearhist",
    "clear-prompt-history": "clearphist", "clock-mode": None, "command-prompt": None, "confirm-before": "confirm",
    "copy-mode": None, "customize-mode": None, "delete-buffer": "deleteb", "detach-client": "detach",
    "display-menu": "menu", "display-message": "display", "display-panes": "displayp", "display-popup": "popup",
    "find-window": "findw", "has-session": "has", "if-shell": "if", "join-pane": "joinp", "kill-pane": "killp",
    "kill-server": None, "kill-session": None, "kill-window": "killw", "last-pane": "lastp", "last-window": "last",
    "link-window": "linkw", "list-buffers": "lsb", "list-clients": "lsc", "list-commands": "lscm", "list-keys": "lsk",
    "list-panes": "lsp", "list-sessions": "ls", "list-windows": "lsw", "load-buffer": "loadb", "lock-client": "lockc",
    "lock-server": "lock", "lock-session": "locks", "move-pane": "movep", "move-window": "movew",
    "new-session": "new", "new-window": "neww", "next-layout": "nextl", "next-window": "next", "paste-buffer": "pasteb",
    "pipe-pane": "pipep", "previous-layout": "prevl", "previous-window": "prev", "refresh-client": "refresh",
    "rename-session": "rename", "rename-window": "renamew", "resize-pane": "resizep", "resize-window": "resizew",
    "respawn-pane": "respawnp", "respawn-window": "respawnw", "rotate-window": "rotatew", "run-shell": "run",
    "save-buffer": "saveb", "select-layout": "selectl", "select-pane": "selectp", "select-window": "selectw",
    "send-keys": "send", "send-prefix": None, "server-access": None, "set-buffer": "setb",
    "set-environment": "setenv", "set-hook": None, "set-option": "set", "set-window-option": "setw",
    "show-buffer": "showb", "show-environment": "showenv", "show-hooks": None, "show-messages": "showmsgs",
    "show-options": "show", "show-prompt-history": "showphist", "show-window-options": "showw",
    "source-file": "source", "split-window": "splitw", "start-server": "start", "suspend-client": "suspendc",
    "swap-pane": "swapp", "swap-window": "swapw", "switch-client": "switchc", "unbind-key": "unbind",
    "unlink-window": "unlinkw", "wait-for": "wait",
}  # fmt: skip
# What an agent may run with no question: they read, or they only check that a session exists.
READ_ONLY = frozenset(
    {
        "has-session", "list-buffers", "list-clients", "list-commands", "list-keys", "list-panes", "list-sessions",
        "list-windows", "show-buffer", "show-environment", "show-hooks", "show-messages", "show-options",
        "show-prompt-history", "show-window-options", "capture-pane",
    }
)  # fmt: skip
SEND_KEYS = "send-keys"
# The ones that run a shell command the call itself holds: the guard reads that command with its own rules
# (approval_commands.forbidden_action), as it reads one an agent runs directly.
RUNS_A_COMMAND = frozenset({"new-window", "new-session", "split-window", "respawn-pane", "respawn-window", "run-shell", "display-popup"})
# Global options that take a value; `-f` (a config file of commands) and `-c` (a shell command) are not among them:
# with either, tmux runs text the guard cannot read, so they make the call unreadable.
_GLOBAL_VALUES = frozenset({"-L", "-S", "-T"})
UNREADABLE_GLOBALS = frozenset({"-f", "-c"})
_UNKNOWN = "?"  # a word that names no tmux command, or more than one: never allowed


def resolve(word: str) -> set[str]:
    """The commands a command word names: exactly a command or an alias, else every command it is a prefix of (one, or
    several when ambiguous, which tmux refuses and the guard fails closed on), else _UNKNOWN."""
    for name, alias in _COMMANDS.items():
        if word in (name, alias):
            return {name}
    found = {name for name in _COMMANDS if name.startswith(word)}
    return found if len(found) == 1 else {_UNKNOWN} if not found else found | {_UNKNOWN}


def commands(args: list[str]) -> tuple[set[str], bool]:
    """The commands a tmux call runs, and whether it sets a global option that runs unreadable text (`-f`, `-c`)."""
    i, unreadable = 0, False
    while i < len(args) and args[i].startswith("-"):
        # `-f`, `-c`, or either inside a cluster (`-2uf conf`): unreadable, whatever follows.
        here = not args[i].startswith("--") and bool(set(args[i][1:]) & {"f", "c"})
        unreadable |= here
        i += 2 if (args[i] in _GLOBAL_VALUES or here) else 1
    found: set[str] = set()
    expect = True
    for a in args[i:]:
        if expect:
            found |= resolve(a)
            expect = False
        if a in (";", "\\;") or a.endswith(("\\;", ";")):
            expect = True
    return found, unreadable
