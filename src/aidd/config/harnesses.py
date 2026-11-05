"""The coding agents `aidd init` recognizes, as data: how each one is detected and how it reaches the skill.

An agent that reads `AGENTS.md` needs nothing else. One that reads its own instruction file gets a pointer file carrying
the same marked section. A harness with a documented, committed permission prompt also gets the harness ask rules:
each `ask` risk rule's commands as that prompt (`risk.harness_rules`).
"""

from __future__ import annotations

import dataclasses

AGENTS_MD = "AGENTS.md"


@dataclasses.dataclass(frozen=True)
class Trust:
    """What a harness holds back in a folder until a person trusts it, as its vendor's documentation says."""

    holds: str  # what it holds back until then
    holds_ask_rules: bool  # its project ask rules are among what it holds back
    how: str  # what the person does to trust the folder, with the words to type
    check: str  # how the person sees whether they trust it: aidd reads nothing outside the repository, so it cannot
    when: str = ""  # the condition the trust step holds under, when it does not always


@dataclasses.dataclass(frozen=True)
class Harness:
    key: str
    label: str
    wiring: str  # what `aidd init` writes for it, for the docs
    repo: tuple[str, ...] = ()  # signals in the repository: a folder or file the agent keeps there
    home: tuple[str, ...] = ()  # signals in the home directory
    bins: tuple[str, ...] = ()  # binaries on PATH
    pointer: str | None = None  # an instruction file that carries the marked section, when the agent does not read AGENTS.md
    header: str = ""  # the first lines of a pointer file init creates
    only_if_present: bool = False  # append to the pointer only when the file already exists; never create it
    you: str = "nothing"  # what the person still does, for the docs
    agent_dirs: tuple[str, ...] = ()  # folders of native agent files `aidd init --team` writes for this harness
    ask_rules: str | None = None  # the format `aidd init` writes the ask risk rules in, as the agent's own permission prompt
    reads_agents_skills: bool = False  # it loads skills from the project's `.agents/skills/`, so the team's flows reach it there
    trust: Trust | None = None  # what it holds back until a person trusts the folder; None when it has no trust step


AGENTS = f"`{AGENTS_MD}`"
SKILL_TOO = f"`{AGENTS_MD}`, and the vendored skill in `.agents/skills/aidd/`, which the agent loads by itself"

# Verified against each vendor's documentation or source on 2026-09-25. A detection signal is never a file aidd writes
# (`AGENTS.md`, `.agents/skills/`), and a pointer is added only to a file the agent reads instead of, or before, AGENTS.md.
# The order is the docs' order for the harnesses. A table keyed by harness follows it unless its own order is behavior.
_TABLE = (
    Harness(
        "claude-code",
        "Claude Code",
        "links the skill into `.claude/skills/`, writes the ask risk rules as `permissions.ask` in `.claude/settings.json` and "
        "the `aidd` MCP server in `.mcp.json`; `--team` adds the roles, commands, packs, and practice skills as project agents "
        "and skills; a `CLAUDE.md` gets the pointer when it exists (Claude Code reads `AGENTS.md` only without one)",
        repo=(".claude", "CLAUDE.md", ".mcp.json"),
        home=(".claude",),
        bins=("claude",),
        pointer="CLAUDE.md",
        only_if_present=True,
        you="nothing (or use the plugins instead: see the note below the table)",
        ask_rules="claude-code",
        # Its `ask` and `deny` rules hold in a folder nobody trusted; `allow` rules, `extraKnownMarketplaces`, and the
        # `.mcp.json` servers wait. code.claude.com/docs/en/permissions, "Project allow rules and workspace trust", read 2026-11-07.
        # A `claude -p` run never shows the dialog, and connects the `.mcp.json` servers without asking.
        trust=Trust(
            holds="the plugin marketplace, `permissions.allow`, and the `aidd` MCP server in `.mcp.json`, which it asks "
            "about before it connects (a `claude -p` run connects it without asking)",
            holds_ask_rules=False,
            how="start `claude` in the repository and accept its trust dialog",
            check="start `claude` in the repository, which shows the trust dialog until you accept it",
        ),
    ),
    Harness(
        "codex",
        "Codex",
        SKILL_TOO + "; writes the ask risk rules in `.codex/rules/aidd.rules` and the `aidd` MCP server in `.codex/config.toml` "
        "(outside Windows), keeping everything else; `--team` adds the roles as `.codex/agents/aidd-<role>.toml` and the "
        "team commands as skills in `.agents/skills/aidd-<flow>/`, which you run as `$aidd-<flow>`",
        repo=(".codex", "AGENTS.override.md"),
        home=(".codex",),
        bins=("codex",),
        agent_dirs=(".codex/agents",),
        ask_rules="codex",
        # It loads a project's `.codex/` layer, its rules and config.toml, only once the project is trusted, and an
        # unset project is untrusted. learn.chatgpt.com/docs/config-file/config-reference and codex-rs/config/src/loader, read 2026-11-07.
        trust=Trust(
            holds="everything in `.codex/`, its ask rules in `.codex/rules/` and the `aidd` MCP server in `.codex/config.toml` too",
            holds_ask_rules=True,
            how='start `codex` in the repository and choose "Trust and continue"',
            check='start `codex` in the repository, which asks until you trust it; an "Open restricted" answer leaves it untrusted',
        ),
    ),
    Harness(
        "copilot",
        "GitHub Copilot",
        f"`{AGENTS_MD}` for the cloud agent, the CLI, and VS Code; in VS Code, the pointer is also appended to "
        "`.github/copilot-instructions.md` when that file exists; the ask risk rules as `chat.tools.terminal.autoApprove` "
        "entries set to `false` in `.vscode/settings.json`, which VS Code's agent asks on; `--team` adds the roles as "
        "`.github/agents/aidd-<role>.agent.md`",
        repo=(".github/copilot-instructions.md", ".github/instructions", ".github/skills", ".github/hooks"),
        home=(".copilot",),
        bins=("copilot",),
        pointer=".github/copilot-instructions.md",
        only_if_present=True,
        agent_dirs=(".github/agents",),
        ask_rules="vscode",
        # VS Code's agent does not run until the folder is trusted (Restricted Mode turns agents off), so it never runs
        # there without the ask rules. code.visualstudio.com/docs/editing/workspaces/workspace-trust, read 2026-11-07.
        trust=Trust(
            holds="its agent, which does not run in Restricted Mode",
            holds_ask_rules=False,
            how="trust the authors when VS Code asks, or run `Workspaces: Manage Workspace Trust` from the Command Palette",
            check="VS Code shows a Restricted Mode banner until you trust it",
        ),
    ),
    Harness("cursor", "Cursor", SKILL_TOO, repo=(".cursor", ".cursorrules"), home=(".cursor",), bins=("cursor", "cursor-agent")),
    Harness(
        "antigravity",
        "Google Antigravity",
        f"`{AGENTS_MD}` (and `GEMINI.md` when present) plus `.agents/skills/aidd/`, which the Antigravity app and the Antigravity CLI (`agy`) load by themselves; "
        "`--team` adds the roles as `.agents/agents/aidd-<role>.md`, the team commands as skills (`/aidd-<flow>`) in `.agents/skills/aidd-<flow>/`, "
        "and `.agents/skills.json`, which names the domain packs in `.claude/skills/`",
        repo=(".agents/rules", ".agents/workflows", ".agents/hooks.json", ".agents/plugins/aidd", ".agents/mcp_config.json", ".agent/rules"),
        home=(".gemini/antigravity", ".gemini/antigravity-cli", ".gemini/config"),
        bins=("agy",),
        agent_dirs=(".agents/agents", ".agents/skills.json"),
    ),
    Harness(
        "kiro",
        "Kiro",
        f"`{AGENTS_MD}`, read alongside `.kiro/steering/`; `--team` adds the roles as `.kiro/agents/aidd-<role>.json`",
        repo=(".kiro",),
        home=(".kiro",),
        bins=("kiro-cli",),
        agent_dirs=(".kiro/agents",),
    ),
    Harness(
        "opencode",
        "OpenCode v2",
        SKILL_TOO + "; writes the ask risk rules in the `permissions` list of `opencode.json`, which needs OpenCode v2 or later; "
        "`--team` adds the roles as `.opencode/agents/aidd-<role>.md` and the team commands as `.opencode/commands/aidd-<flow>.md`",
        repo=("opencode.json", "opencode.jsonc", ".opencode"),
        home=(".config/opencode",),
        bins=("opencode",),
        agent_dirs=(".opencode/agents",),
        you="nothing (aidd's MCP tools are optional: add an `aidd` server that runs `aidd mcp` in `opencode.json`'s `mcp` section, as OpenCode's MCP servers docs show)",
        ask_rules="opencode",
    ),
    Harness("junie", "JetBrains Junie", AGENTS, repo=(".junie",), home=(".junie",), bins=("junie",)),
    Harness(
        "qwen-code",
        "Qwen Code",
        f"`{AGENTS_MD}`, read next to `QWEN.md`; the ask risk rules as `permissions.ask` `Bash(...)` entries in `.qwen/settings.json`",
        repo=("QWEN.md", ".qwen"),
        home=(".qwen",),
        bins=("qwen",),
        ask_rules="qwen",
        # With folder trust on (`security.folderTrust.enabled`, off by default), it loads no `.qwen/settings.json` in a
        # folder nobody trusted, and turns tool auto-approval off, so it asks before every tool there.
        # qwenlm.github.io/qwen-code-docs/en/users/configuration/trusted-folders/, read 2026-11-07.
        trust=Trust(
            when="only when folder trust is on, which is off by default",
            holds="all of `.qwen/settings.json`, its ask rules too, and asks before every tool instead",
            holds_ask_rules=True,
            how='choose "Trust folder" when Qwen Code asks',
            check="`~/.qwen/trustedFolders.json` lists the folders you trust",
        ),
    ),
    Harness("trae", "TraeCode", AGENTS, repo=(".trae",), home=(".trae",)),
    # DeepSeek Harness (`dsh`, deepseek-ai/deepseek-harness) keeps its config in `.dsh/` and `$DSH_HOME` (else `~/.dsh`)
    # and loads skills from `.dsh/skills/` and `.agents/skills/`. Its approvals are ask-or-never with one-shot grants:
    # no committed per-command rule, so the skill alone carries the asks (read 2026-11-06).
    Harness("deepseek-harness", "DeepSeek Harness", SKILL_TOO, repo=(".dsh",), home=(".dsh",), bins=("dsh",)),
    # Muse Code (`muse`, Meta, dev.meta.ai/docs/muse-code) reads AGENTS.md, keeps project hooks in `.muse/` and settings in
    # `~/.config/muse/`, and loads skills from `.agents/skills/`. Its saved allow rules live in the person's own settings,
    # with no committed per-project ask rule, so the skill alone carries the asks (read 2026-11-06). It passes
    # `MUSE_SESSION_ID` to stdio MCP servers only, not to the shell it runs commands in, so `SESSION_ENV` has no entry for it.
    Harness("muse-code", "Muse Code", SKILL_TOO, repo=(".muse",), home=(".config/muse",), bins=("muse",)),
    # Grok Build (`grok`, xai-org/grok-build) reads project rules from AGENTS.md and keeps its config in `.grok/` and
    # `~/.grok/`. It loads skills from `.grok/skills/` and `.agents/skills/`, so the vendored skill serves it as it is.
    Harness(
        "grok-build",
        "Grok Build",
        SKILL_TOO + "; the ask risk rules as `[permission] ask` in `.grok/config.toml`; `--team` adds the roles as "
        "`.grok/agents/aidd-<role>.md` and the team commands as skills in `.grok/skills/aidd-<flow>/`",
        repo=(".grok",),
        home=(".grok",),
        bins=("grok",),
        you="nothing (aidd's MCP tools are optional: add `aidd mcp` as a server for them)",
        agent_dirs=(".grok/agents",),
        ask_rules="grok",
        # Folder trust gates a project's permission rules in `.grok/config.toml`, its instructions, skills, MCP servers,
        # and hooks. xai-org/grok-build user guide (22-permissions-and-safety.md, 10-hooks.md), read 2026-11-07.
        trust=Trust(
            holds="its ask rules in `.grok/config.toml`, the project's instructions and skills, its MCP servers, and its hooks",
            holds_ask_rules=True,
            how="start `grok` in the repository and type `/hooks-trust`",
            check="`~/.grok/trusted_folders.toml` lists the folders you trust",
        ),
    ),
    Harness("vibe", "Mistral Vibe", SKILL_TOO, repo=(".vibe",), home=(".vibe",), bins=("vibe",)),
)
# The harnesses that load skills from the project's `.agents/skills/` (each vendor's docs, read 2026-11-03), so the
# team's flows written there reach them.
AGENTS_SKILLS_READERS = frozenset(
    (
        "codex",
        "copilot",
        "cursor",
        "antigravity",
        "junie",
        "qwen-code",
        "trae",
        "deepseek-harness",
        "muse-code",
        "vibe",
    )
)
HARNESSES: dict[str, Harness] = {h.key: dataclasses.replace(h, reads_agents_skills=h.key in AGENTS_SKILLS_READERS) for h in _TABLE}


PLUGIN_NOTE = (
    "For Claude Code, we recommend the plugins over repository files: `aidd init --claude-plugins --team`, "
    "or in Claude Code `/plugin marketplace add thaithienvanid/aidd`, then `/plugin install aidd@aidd` and "
    "`/plugin install aidd-team@aidd`. Add `/plugin install aidd-cli@aidd` when no CLI is installed: it puts the `aidd` "
    "command on the agent's `PATH`. The command (`aidd-cli`) and the delivery team (`aidd-team`) are optional, and every part "
    "works without them. With the aidd plugin enabled in your own Claude Code settings, `aidd init` enables it in the project's "
    "`.claude/settings.json` (`enabledPlugins` and `extraKnownMarketplaces`) instead of copying the MCP server and the skill link "
    "into the repository, so nothing loads twice. The ask rules go into the project's settings either way.\n\n"
    "Run `aidd init` again to add an agent, such as `aidd init --harness opencode`: it reads the profile from the config it "
    "keeps, keeps every file that exists, and writes only what is new."
)


# The variable each agent sets in the shell it runs, so `aidd init` wires the agent of the session it runs in, and
# `aidd doctor` names it. Init wires every one set; for doctor, the first one set names the harness.
SESSION_ENV = {
    "CLAUDECODE": "claude-code",
    "CODEX_SANDBOX": "codex",
    "OPENCODE": "opencode",
    "ANTIGRAVITY_AGENT": "antigravity",
}


def session_harness(env: dict[str, str]) -> str | None:
    """The harness whose own variable this environment carries, or None outside a known agent's shell."""
    return next((h for var, h in SESSION_ENV.items() if env.get(var)), None)


def pointer_files() -> list[tuple[str, str]]:
    """Every instruction file init may write or append to, with the header a fresh one starts with."""
    return [(AGENTS_MD, "# Agents")] + [(h.pointer, h.header.strip()) for h in HARNESSES.values() if h.pointer]


_FILE_SIGNALS = {".cursorrules"}


def _is_file(signal: str) -> bool:
    base = signal.rsplit("/", 1)[-1]
    return "." in base[1:] or base in _FILE_SIGNALS


def _shown(signal: str, prefix: str = "") -> str:
    """A signal in the docs: files as they are, directories with a trailing slash."""
    return f"`{prefix}{signal}{'' if _is_file(signal) else '/'}`"


def harness_paths() -> list[str]:
    """Every path a supported agent reads as instructions or settings, as globs: the `agent_config` risk area holds them,
    so an edit of an agent's own instructions or permissions is reported (tests/test_risk.py keeps the two in step). A
    file is itself and a folder everything under it; a path another one already covers is left out."""
    from aidd.kernel import globs

    out: list[str] = []
    for h in HARNESSES.values():
        for signal in (*h.repo, *((h.pointer,) if h.pointer else ()), *h.agent_dirs):
            out.append(signal if _is_file(signal) else f"{signal}/**")
    out = list(dict.fromkeys(out))
    return [p for p in out if not any(q != p and globs.match(q, globs.literal_form(p)) for q in out)]


def ask_rule_harnesses() -> list[Harness]:
    """The agents `aidd init` writes the ask risk rules for: Claude Code first, as aidd's reference harness, then the rest by name."""
    rest = sorted((h for k, h in HARNESSES.items() if h.ask_rules and k != "claude-code"), key=lambda h: h.label.casefold())
    return [HARNESSES["claude-code"], *rest]


def _table(harnesses: list[Harness], anything_else: bool = False) -> str:
    rows = ["| Your agent | Detected by (in the repository) | What `aidd init` does | What you do |", "| --- | --- | --- | --- |"]
    for h in harnesses:
        signals = ", ".join(_shown(x) for x in h.repo) or f"nothing it keeps there: `--harness {h.key}`"
        rows.append(f"| {h.label} | {signals} | {h.wiring} | {what_you_do(h)} |")
    if anything_else:
        rows.append(f"| Anything else | | `{AGENTS_MD}` and `.agents/skills/aidd/` | tell the agent to read `{AGENTS_MD}` |")
    return "\n".join(rows)


def what_you_do(h: Harness) -> str:
    """What the person still does for a harness, for the docs: its own step, then the trust step it asks for."""
    if h.trust is None:
        return h.you
    when = f" ({h.trust.when})" if h.trust.when else ""
    trust = f"trust the folder{when}, because until then it holds back {h.trust.holds}. To trust it, {h.trust.how}"
    # "nothing (a note)" becomes the trust step with its note, never "nothing" followed by a step.
    return f"{trust}{h.you.removeprefix('nothing')}" if h.you.startswith("nothing") else f"{h.you}; {trust}"


def harnesses_table() -> str:
    """The per-agent tables for the docs: the agents that get ask rules, then every other agent, folded."""
    main = ask_rule_harnesses()
    others = [h for h in HARNESSES.values() if h not in main]
    return (
        _table(main)
        + "\n\n"
        + PLUGIN_NOTE
        + f"\n\n**Every other agent** reads `{AGENTS_MD}` and the vendored skill, which tells it when to ask. Its own settings decide "
        + f"what it may run without a prompt. `aidd init` wires each of these {len(others)} agents when it finds it.\n\n"
        + f"<details><summary>What <code>aidd init</code> does for each of the other {len(others)} agents</summary>\n\n"
        + _table(others, anything_else=True)
        + "\n\n</details>"
    )
