"""The commands that start a coding agent: its own program, one a package runner fetches, and the Claude Code launches
that may switch off aidd's hooks (`drops_hooks`, `moves_config`).
"""

from __future__ import annotations

from aidd import config
from aidd.guard import shell_parser

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


# The variables that move a tool's config folder: `gh`'s, `glab`'s, and Claude Code's, which then loads none of the
# person's plugins or aidd's hooks.
CONFIG_FOLDERS = ("HOME", "GH_CONFIG_DIR", "GLAB_CONFIG_DIR", "XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR")


def names_agent(word: str) -> bool:
    """Whether a program or package name is a coding agent's: `claude`, `claude-code`, `@anthropic-ai/claude-code@1`,
    `opencode-ai`."""
    base = word.rsplit("/", 1)[-1].split("@", 1)[0].casefold()
    return any(base == b or base.startswith(f"{b}-") for b in AGENT_PROGRAMS)


def starts_agent(argv: list[str]) -> bool:
    """Whether a command starts a coding agent: its own program, one a package runner fetches, or a script a runtime
    runs, which the guard cannot read (failing closed)."""
    if not argv:
        return False
    name, args = shell_parser.program_name(argv[0]), argv[1:]
    if names_agent(name):
        return True
    if name in _PACKAGE_RUNNERS:
        subs = _PACKAGE_RUNNERS[name]
        words = [a for a in args if not a.startswith("-")]
        if subs is not None and words[:1] and words[0] not in subs:
            return False
        # Every word and option value counts (`--package=@anthropic-ai/claude-code`, `-p opencode-ai`): a misread
        # one can only add a match, never hide one.
        return any(names_agent(a.split("=", 1)[-1]) for a in args)
    return False


# Claude Code's options that load other settings or none: each may switch off the hooks that run the guard.
HOOK_DROPPING = ("--settings", "--setting-sources", "--bare")


def is_claude(sc: shell_parser.SimpleCommand) -> bool:
    """Whether the command starts Claude Code, as `claude` or through a package runner (`npx @anthropic-ai/claude-code`)."""
    argv = shell_parser.program_argv(sc.argv)
    words = [a.split("=", 1)[-1] for a in argv]
    return bool(argv) and starts_agent(argv) and (shell_parser.program_name(argv[0]) == "claude" or any(w == "claude" or "claude-code" in w for w in words[1:]))


def drops_hooks(sc: shell_parser.SimpleCommand) -> bool:
    """Whether the command starts Claude Code with an option or a variable that may load settings without aidd's hooks."""
    if not is_claude(sc):
        return False
    argv = shell_parser.program_argv(sc.argv)
    before = sc.argv[: len(sc.argv) - len(argv)]  # the assignments and wrappers (`env`) in front of the program
    return any(a == o or a.startswith(o + "=") for a in argv[1:] for o in HOOK_DROPPING) or any(assigns_config(w) for w in before)


def moves_config(simple: list[shell_parser.SimpleCommand]) -> bool:
    """Whether a command on the line sets a config-folder variable (inline, or by `export`, `declare`, `typeset`, or
    `readonly`) and the line also starts Claude Code, which would then load no aidd hooks."""
    return any(is_claude(sc) for sc in simple) and any(assigns_config(w) for sc in simple for w in sc.argv)


def assigns_config(word: str) -> bool:
    """Whether a word sets a config-folder variable, in any spelling of an assignment (shell_parser.assignment)."""
    found = shell_parser.assignment(word)
    return bool(found) and found[0] in CONFIG_FOLDERS  # type: ignore[index]
