"""`aidd doctor --autopilot`: the settings an autopilot run needs, as far as aidd can see them.

aidd reads the repository's own files and this process's environment. It checks the hooks level, that the edit-time
guard is wired in a coding agent (Claude Code, Codex, Grok Build, Antigravity, or OpenCode), that the deploy tooling
it finds has held commands, that no variable named like a credential reaches the agent (by name only), and that
Claude Code's permissions allow what the run runs (aidd itself and aidd's read-only MCP tools) and never skip every
check. Where Codex is wired, it checks that Codex's sandbox lets the run write the git directory, and for each wired
harness that the autopilot flow is there to run. It reads no
credential's value, with one exception: the first four characters of GH_TOKEN and GITHUB_TOKEN, to tell a long-lived
classic token (`ghp_`, `gho_`) from one that expires. It never prints or keeps them. It warns when a
run would hold all three legs of Meta's Agents Rule of Two at once: untrusted input, a credential, and egress no
allowlist limits. The sandbox, permission, and trust lines read Claude Code's settings only; the Rule of Two also reads
the MCP servers of Codex and OpenCode where aidd wired them, and a note names each wired harness whose own settings it
did not read. What lives in the harness or the machine, such as managed settings and the permission mode, it cannot
see, so it lists them for a person to check. It also says whether Claude Code's advisor is configured (`advisorModel`
in the settings files aidd can read), as information only: the advisor is optional and experimental, and never a
warning when it is absent.
"""

from __future__ import annotations

import contextvars
import json
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path

from aidd import config
from aidd.kernel import git
from aidd.kernel.processes import CREDENTIAL_NAME
from aidd.setup import antigravity_wiring, codex_wiring, detection, grok_wiring, hook_wiring, opencode_wiring
from aidd.setup.harness_configs import codex_git_check, codex_home, config_bytes, opencode_home, read_json, read_toml

AUTOPILOT_CHECKLIST_TITLE = "What aidd cannot see; check these yourself before an autopilot run:"
AUTOPILOT_CHECKLIST: tuple[str, ...] = (
    "the sandbox is on wherever aidd cannot read the settings, such as managed settings",
    "the permission mode asks or denies what the settings do not allow (`dontAsk` for a run with nobody at the keyboard)",
    "the network reaches only what the work needs, from an allowlist",
    "for a team, managed settings hold these, so a project file cannot turn them off",
)
MAX_NAMES = 10
ADVISOR_KEY = "advisorModel"
ADVISOR_OFF_ENV = "CLAUDE_CODE_DISABLE_ADVISOR_TOOL"
ADVISOR_LIMITS = "optional and experimental, on the Anthropic API only"


def wired_harnesses(root: Path) -> list[str]:
    """Each coding agent whose guard aidd wired here, by its key in `config.HARNESSES`: Claude Code's hook or the aidd
    plugin, the PreToolUse hook in the hook files of Codex, Grok Build, and Antigravity, and OpenCode's guard plugin."""
    out = ["claude-code"] if _claude_code_guard_wired(root) else []
    for key, wiring in (("codex", codex_wiring.wired), ("grok-build", grok_wiring.wired), ("antigravity", antigravity_wiring.wired)):
        if wiring(root).get("PreToolUse"):
            out.append(key)
    if opencode_wiring.state(root) != "missing":  # aidd's plugin, current or from an older aidd: either runs the guard
        out.append("opencode")
    return out


def _labels(keys: list[str]) -> str:
    """The harnesses' names inside a sentence: `Codex`, `Codex and OpenCode V2`, `Codex, Grok Build, and OpenCode V2`."""
    names = [config.HARNESSES[k].label for k in keys]
    return ", ".join(names[:-1]) + f", and {names[-1]}" if len(names) > 2 else " and ".join(names)


def _claude_code_guard_wired(root: Path) -> bool:
    """The guard runs: a PreToolUse hook runs `aidd hook pre-tool`, or the aidd plugin is on (its hooks carry it)."""
    if config.plugin_enabled(root):
        return True
    for name in ("settings.json", "settings.local.json"):
        try:
            data = json.loads((root / ".claude" / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entries = (data.get("hooks") or {}).get("PreToolUse") or [] if isinstance(data, dict) else []
        if any(
            hook_wiring.aidd_hook(h.get("command")) == "pre-tool" for e in entries if isinstance(e, dict) for h in e.get("hooks") or [] if isinstance(h, dict)
        ):
            return True
    return False


# What an autopilot run calls on every step: under a permission mode that denies what the settings do not allow
# (`dontAsk`, as a run with nobody at the keyboard needs), each must be allowed, or the step stops on a denial. Found
# in real runs: reads and edits of the project's files (the guard still checks each edit's scope), aidd itself, aidd's
# read-only MCP tools, and the team plugin's flow files, outside the project. The decision tools (approve_*, land,
# proposal_*) are left out: they ask the person in a dialog, which no rule replaces.
READ_ONLY_TOOLS = ("gate", "check_edit", "validate", "describe")
COMMAND_RULE = "Bash(aidd *)"
PROJECT_RULES = ("Read(/**)", "Edit(/**)")
SKIPS_EVERY_CHECK = "bypassPermissions"


def _settings(root: Path) -> list[dict]:
    """Every Claude Code settings file aidd can read, in the order a later one decides."""
    out = []
    for path in config.claude_settings_paths(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def sandbox_on(root: Path) -> bool:
    """Whether the settings aidd can read turn Claude Code's sandbox on (`sandbox.enabled`, a later file deciding)."""
    on = False
    for data in _settings(root):
        box = data.get("sandbox")
        if isinstance(box, dict) and isinstance(box.get("enabled"), bool):
            on = box["enabled"]
    return on


def _permissions(root: Path) -> tuple[set[str], str | None]:
    """The `permissions.allow` rules of every Claude Code settings file aidd can read, and the `defaultMode` the last
    of them sets (a later file decides)."""
    allowed: set[str] = set()
    mode: str | None = None
    for data in _settings(root):
        perms = data.get("permissions")
        if not isinstance(perms, dict):
            continue
        allowed |= {r for r in perms.get("allow") or [] if isinstance(r, str)}
        if isinstance(perms.get("defaultMode"), str):
            mode = perms["defaultMode"]
    return allowed, mode


def _mcp_server(root: Path) -> str | None:
    """How Claude Code names aidd's MCP tools here: `mcp__plugin_aidd_aidd` for the plugin, `mcp__aidd` for a project
    `.mcp.json` server named `aidd`, or None when neither is wired."""
    if config.plugin_enabled(root):
        return "mcp__plugin_aidd_aidd"
    try:
        servers = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers") or {}
    except (OSError, ValueError, AttributeError):
        return None
    return "mcp__aidd" if isinstance(servers, dict) and "aidd" in servers else None


def needed_rules(root: Path) -> list[str]:
    """The `permissions.allow` rules an autopilot run needs and the settings do not have yet, in the order to add them."""
    allowed, _ = _permissions(root)
    out = [r for r in PROJECT_RULES if r not in allowed and r.split("(", 1)[0] not in allowed]
    out += [] if allowed & {COMMAND_RULE, "Bash(aidd:*)", "Bash(aidd*)", "Bash"} else [COMMAND_RULE]
    if f"aidd-team@{config.MARKETPLACE}" in config.plugins_enabled(root) and (rule := _plugins_rule()) not in allowed and "Read" not in allowed:
        out.append(rule)
    if server := _mcp_server(root):
        whole = {server, f"{server}__*"}
        out += [f"{server}__{name}" for name in READ_ONLY_TOOLS if not allowed & (whole | {f"{server}__{name}"})]
    return out


def _plugins_rule() -> str:
    """Reading the installed plugins' files, where the team plugin keeps the flow each autopilot step runs."""
    folder = config.claude_config_dir() / "plugins"
    home = Path.home()
    return f"Read(~/{folder.relative_to(home).as_posix()}/**)" if folder.is_relative_to(home) else f"Read(/{folder.as_posix()}/**)"


# Within one `autopilot_checks` run, `.claude.json` (which can be large) is read once, by its path. Outside a run, as in
# the MCP server between calls, nothing is kept, so a later call reads the file as it is then.
_USER_RECORDS: contextvars.ContextVar[dict[Path, dict | None] | None] = contextvars.ContextVar("aidd_user_records", default=None)


def _user_record() -> dict | None:
    """Claude Code's own record of this user, `.claude.json` in CLAUDE_CONFIG_DIR or the home folder, or None when aidd
    cannot read it."""
    home = Path(os.environ["CLAUDE_CONFIG_DIR"]).expanduser() if os.environ.get("CLAUDE_CONFIG_DIR") else Path.home()
    path, read = home / ".claude.json", _USER_RECORDS.get()
    if read is not None and path in read:
        return read[path]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    record = data if isinstance(data, dict) else None
    if read is not None:
        read[path] = record
    return record


def folder_trusted(root: Path) -> bool | None:
    """Whether Claude Code trusts the folder (`projects.<path>.hasTrustDialogAccepted` in its own `.claude.json`), read
    only: until it does, it ignores the project's `permissions.allow`. None when aidd cannot read the record."""
    record = _user_record()
    projects = (record.get("projects") or {}) if record is not None else None
    if not isinstance(projects, dict):
        return None
    for key in {str(root), str(root.resolve())}:
        entry = projects.get(key)
        if isinstance(entry, dict) and isinstance(entry.get("hasTrustDialogAccepted"), bool):
            return entry["hasTrustDialogAccepted"]
    return False


def permission_checks(root: Path) -> list[tuple[str, str]]:
    """(level, message) for Claude Code's permissions: never a mode that skips every check, and an allow rule for each
    thing an autopilot run calls (needed_rules), printed for a person to add: aidd never writes the settings."""
    _, mode = _permissions(root)
    out: list[tuple[str, str]] = []
    if sandbox_on(root):
        out.append(("ok", "Claude Code's sandbox is on (`sandbox.enabled`): the agents' shell commands run inside it, with no one asked"))
    else:
        out.append(
            (
                "warn",
                "Claude Code's sandbox is off in the settings aidd can read: set `sandbox.enabled: true`. Without it, a run with nobody to "
                "ask (`dontAsk`) is denied every shell command its allow rules do not match, such as a test piped to `tail`",
            )
        )
    if mode == SKIPS_EVERY_CHECK:
        out.append(("fail", f"`permissions.defaultMode` is `{SKIPS_EVERY_CHECK}`, which skips every check: use `dontAsk` or `default`"))
    missing = needed_rules(root)
    if missing:
        rules = ", ".join(json.dumps(r) for r in missing)
        out.append(
            (
                "warn",
                f"Claude Code's permissions do not allow what an autopilot run calls on every step, so a run with nobody to ask "
                f"(`dontAsk`) stops on a denial. Add to `permissions.allow` in .claude/settings.json: [{rules}]. Claude Code "
                "applies a project's allow rules once you trust the folder: run Claude Code there once and accept",
            )
        )
    else:
        out.append(("ok", "Claude Code's permissions allow what an autopilot run calls on every step: the project's files, aidd, and its read-only tools"))
    trusted = folder_trusted(root)
    if trusted is False:
        out.append(
            (
                "warn",
                "Claude Code does not trust this folder yet, so it ignores the project's `permissions.allow`: run Claude Code here "
                "once and accept the trust dialog",
            )
        )
    elif trusted:
        out.append(("ok", "Claude Code trusts this folder, so it applies the project's permission rules"))
    return out


def credential_names(env: dict[str, str] | None = None) -> list[str]:
    """The names of the variables that look like credentials (processes.CREDENTIAL_NAME). Never their values."""
    return sorted(k for k in (os.environ if env is None else env) if CREDENTIAL_NAME.search(k))


# A classic personal access token (`ghp_`) or an OAuth app token (`gho_`) can live until someone revokes it. The
# variables are the two aidd itself reads a GitHub token from.
GITHUB_TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN")
LONG_LIVED_PREFIXES = {"ghp_": "a classic personal access token", "gho_": "an OAuth app token"}
PREFIX_LENGTH = 4
CREDENTIALS_DOC = "docs/AUTOPILOT.md, Credentials for a run"


def long_lived_github_tokens(env: Mapping[str, str] | None = None) -> list[tuple[str, str]]:
    """(variable, kind) for each of GH_TOKEN and GITHUB_TOKEN whose value starts with a long-lived token's prefix. It
    reads the first PREFIX_LENGTH characters only, and never returns, prints, or keeps any part of the value."""
    environ: Mapping[str, str] = os.environ if env is None else env
    out = []
    for name in GITHUB_TOKEN_VARS:
        kind = LONG_LIVED_PREFIXES.get(str(environ.get(name) or "")[:PREFIX_LENGTH])
        if kind:
            out.append((name, kind))
    return out


def token_checks(env: Mapping[str, str] | None = None) -> list[tuple[str, str]]:
    """A warning for each long-lived GitHub token the run would hold; nothing when there is none."""
    return [
        (
            "warn",
            f"`{name}` holds {kind}, which can live until someone revokes it (aidd read only its prefix). Give the run a "
            f"fine-grained token with an expiry, or a GitHub App user token, which expires in 8 hours ({CREDENTIALS_DOC})",
        )
        for name, kind in long_lived_github_tokens(env)
    ]


# Meta's Agents Rule of Two (ai.meta.com/blog/practical-ai-agent-security, 2025-10-31): a run with nobody to ask should
# hold at most two of untrusted input, sensitive data or credentials, and a way to change state or talk to the outside.
# aidd sees the legs only in the files it reads, so the check is a warning, never a failure.
RULE_OF_TWO = "Meta's Agents Rule of Two (2025-10-31)"
WEB_TOOLS = ("WebFetch", "WebSearch")
# A web-fetch rule that names no host lets the tool reach any host, and the tool runs outside the sandbox.
OPEN_FETCH_RULES = ("WebFetch", "WebFetch(*)", "WebFetch(domain:*)")
# An MCP server or plugin that, by a whole word of its name, command, arguments, or URL, reads text anyone can write:
# issues and tickets, chat and mail, shared pages, error reports, a browser, or the web.
UNTRUSTED_SOURCE = frozenset(
    {
        *("github", "gitlab", "bitbucket", "jira", "linear", "atlassian", "confluence", "issue", "issues", "sentry", "zendesk"),
        *("intercom", "slack", "discord", "teams", "gmail", "mail", "email", "outlook", "imap", "notion"),
        *("browser", "playwright", "puppeteer", "chrome", "chromium", "selenium", "fetch", "web", "search", "brave"),
        *("tavily", "exa", "perplexity", "firecrawl", "crawl", "crawler", "scrape", "scraper", "scraping"),
    }
)
# A shell command an allow rule may run that reads text from the outside: a web page, an issue, or a pull request.
UNTRUSTED_COMMANDS = frozenset({"curl", "wget", "gh issue", "gh pr view", "gh api"})


def _words(text: str) -> set[str]:
    """The whole words of a name, command, or URL, split on anything but a letter or a digit, lower case; a camelCase
    word gives its parts as well (`mcpWebSearch` gives web and search)."""
    out: set[str] = set()
    for run in re.findall(r"[A-Za-z0-9]+", text):
        out.add(run.lower())
        out |= {w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|[0-9]+", run)}
    return out


def _untrusted_words(text: str) -> bool:
    return bool(_words(text) & UNTRUSTED_SOURCE)


def _shell_reads_untrusted(rule: str) -> bool:
    """Whether a `Bash(...)` allow rule lets a command read the outside (UNTRUSTED_COMMANDS): bare `Bash`, a rule a
    prefix of one of them matches (`Bash(gh:*)`), or one that starts with one (`Bash(curl -s https://x:*)`)."""
    if rule == "Bash":
        return True
    if not (rule.startswith("Bash(") and rule.endswith(")")):
        return False
    inner = rule[5:-1].strip()
    wild = inner.endswith("*")
    # `Bash(cu*)` matches inside a word; `Bash(gh *)` and `Bash(gh:*)` match whole words only.
    glued = wild and not inner.rstrip("*").endswith((" ", ":"))
    words = tuple(inner.rstrip("*").rstrip(":").split())
    if not words:
        return wild

    def covers(command: tuple[str, ...]) -> bool:
        if words[: len(command)] == command:
            return True
        if not wild or len(words) > len(command) or command[: len(words) - 1] != words[:-1]:
            return False
        nxt = command[len(words) - 1]
        return nxt == words[-1] or (glued and nxt.startswith(words[-1]))

    return any(covers(tuple(c.split())) for c in UNTRUSTED_COMMANDS)


# aidd's dev container writes its egress allowlist here, root-owned, when its image is built (templates/devcontainer),
# whether or not its firewall ever starts. The firewall writes the marker, root-owned, only once its own check passed.
DEVCONTAINER_EGRESS_LIST = Path("/etc/aidd-egress/allowed-hosts")
DEVCONTAINER_FIREWALL_ACTIVE = Path("/run/aidd-egress/active")
FIREWALL_SCRIPT = "/usr/local/sbin/aidd-init-firewall"


def _root_owned(path: Path, *, folder: bool) -> bool:
    """Whether `path` is root's own regular file (or folder), not a link, that no one else may write."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    kind = stat.S_ISDIR(st.st_mode) if folder else stat.S_ISREG(st.st_mode)
    return kind and st.st_uid == 0 and not st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def current_start() -> str | None:
    """This container's start as the firewall's marker names it: the boot id and PID 1's start time (field 22 of
    /proc/1/stat). None where /proc cannot say, so a marker is never trusted there."""
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        fields = Path("/proc/1/stat").read_text(encoding="ascii").rsplit(") ", 1)[-1].split()
    except (OSError, ValueError):
        return None
    return f"aidd-start {boot} {fields[19]}" if boot and len(fields) > 19 else None


def devcontainer_firewall_up() -> bool:
    """Whether aidd's dev container firewall started and passed its own check on this start: its marker is root's, in
    root's folder, and its first line names the container's current start, so one an earlier start left counts for
    nothing (iptables rules end with the container, a file under /run may not)."""
    marker = DEVCONTAINER_FIREWALL_ACTIVE
    if not (_root_owned(marker.parent, folder=True) and _root_owned(marker, folder=False)):
        return False
    try:
        with marker.open(encoding="ascii", errors="replace") as f:
            first = f.readline(200).strip()
    except OSError:
        return False
    start = current_start()
    return start is not None and first == start


def devcontainer_firewall_down() -> bool:
    """Inside aidd's dev container (its allowlist is there) with no sign that its firewall is up."""
    return DEVCONTAINER_EGRESS_LIST.is_file() and not devcontainer_firewall_up()


def _mcp_servers(root: Path) -> dict[str, object]:
    """Every MCP server aidd can read that Claude Code would start here: the project's `.mcp.json`, and the user's and
    this folder's servers in `.claude.json`."""
    try:
        project = json.loads((root / ".mcp.json").read_text(encoding="utf-8")).get("mcpServers")
    except (OSError, ValueError, AttributeError):
        project = None
    record = _user_record() or {}
    projects = record.get("projects")
    local = [projects.get(k) for k in {str(root), str(root.resolve())}] if isinstance(projects, dict) else []
    found: dict[str, object] = {}
    for servers in (project, record.get("mcpServers"), *(e.get("mcpServers") for e in local if isinstance(e, dict))):
        if isinstance(servers, dict):
            found.update({str(k): v for k, v in servers.items()})
    return found


def _reads_untrusted(name: str, server: object) -> bool:
    """Whether an MCP server reads text anyone can write (UNTRUSTED_SOURCE), by a whole word of its name, command,
    arguments, or URL; never by its environment, which may hold a secret."""
    parts = [name]
    if isinstance(server, dict):
        parts += [str(server.get(k) or "") for k in ("command", "url")]
        args = server.get("args")
        parts += [str(a) for a in args] if isinstance(args, list) else []
    return _untrusted_words(" ".join(parts))


def _shown(name: str) -> str:
    """A name from a settings file, safe to print: no control character reaches the terminal, and no name runs long."""
    return "".join(c if c.isprintable() and c != "`" else "?" for c in name[:60])


def harness_mcp_servers(root: Path, key: str) -> dict[str, object] | None:
    """The MCP servers harness `key` would start here, from the files the standard library reads: Codex's
    `mcp_servers` in `.codex/config.toml` and the user's `config.toml`, and OpenCode's `mcp` in `opencode.json` (or
    `.jsonc`), the project's and the user's. None where aidd cannot read them: another harness keeps them elsewhere, a
    file does not parse (an `opencode.jsonc` with comments, or one nested too deep), or `config_bytes` will not read
    it, so an unread harness never counts as clear."""
    if key == "codex":
        paths, read, field = [root / ".codex" / "config.toml", codex_home() / "config.toml"], read_toml, "mcp_servers"
    elif key == "opencode":
        names = ("opencode.json", "opencode.jsonc")
        paths, read, field = [*(root / n for n in names), *(opencode_home() / n for n in names)], read_json, "mcp"
    else:
        return None
    found: dict[str, object] = {}
    for path in paths:
        if not path.exists() and not path.is_symlink():
            continue
        try:
            data = read(config_bytes(path, in_repository=path.parent in (root, root / ".codex")))
        except (OSError, ValueError, RecursionError):  # tomllib.TOMLDecodeError and UnicodeDecodeError are ValueErrors
            return None
        servers = data.get(field) if isinstance(data, dict) else None
        if servers is not None and not isinstance(servers, dict):
            return None
        found.update({str(k): v for k, v in (servers or {}).items()})
    return found


def _web_servers(root: Path) -> list[str]:
    """The MCP servers and plugins that read text anyone can write, named as a person would find them: Claude Code's,
    and those of each other harness aidd wired here whose servers it can read."""
    out = [f"the MCP server `{_shown(name)}`" for name, server in sorted(_mcp_servers(root).items()) if _reads_untrusted(name, server)]
    for key in wired_harnesses(root):
        servers = harness_mcp_servers(root, key) if key != "claude-code" else None
        label = config.HARNESSES[key].label
        out += [f"the MCP server `{_shown(n)}` ({label})" for n, s in sorted((servers or {}).items()) if _reads_untrusted(n, s)]
    plugins = sorted(p for p in config.plugins_enabled(root) if _untrusted_words(p.split("@", 1)[0]))
    return out + [f"the plugin `{_shown(p)}`" for p in plugins]


def unread_harnesses(root: Path) -> list[str]:
    """The harnesses other than Claude Code whose guard aidd wired here and whose MCP servers it cannot read."""
    return [k for k in wired_harnesses(root) if k != "claude-code" and harness_mcp_servers(root, k) is None]


def harness_scope_note(root: Path) -> tuple[str, str] | None:
    """Which harnesses' settings the checks read, when aidd wired the guard in one besides Claude Code; else None."""
    others = [k for k in wired_harnesses(root) if k != "claude-code"]
    if not others:
        return None
    unread = unread_harnesses(root)
    read = [k for k in others if k not in unread]
    said = (
        "The sandbox, permission, and trust lines read Claude Code's settings only."
        if "claude-code" in wired_harnesses(root)
        else "aidd checks the sandbox, permissions, and trust in Claude Code's settings only, and Claude Code is not wired here."
    )
    said += f" The Rule of Two line also read the MCP servers of {_labels(read)}." if read else ""
    if unread:
        said += f" aidd did not read the MCP servers of {_labels(unread)}, so it never counts them as clear."
    return ("info", f"{said} Check the sandbox and permissions of {_labels(others)} yourself before an unattended run")


def untrusted_inputs(root: Path) -> list[str]:
    """What lets a run read text anyone can write: a web tool or a shell command that reads the outside its permissions
    allow, a mode that allows every tool, or an MCP server or plugin that reads issues, chat, mail, a browser, or the web."""
    allowed, mode = _permissions(root)
    out = [f"`{_shown(r)}` allowed" for r in sorted(allowed) if r.split("(", 1)[0] in WEB_TOOLS or _shell_reads_untrusted(r)]
    out += [f"`permissions.defaultMode` is `{mode}`"] if mode == SKIPS_EVERY_CHECK else []
    return out + _web_servers(root)


def _sandbox_lists(root: Path) -> tuple[set[str], set[str], bool]:
    """From the settings files aidd can read: `sandbox.network.allowedDomains` and `sandbox.excludedCommands`, which
    Claude Code merges across files, and whether a command that fails in the sandbox may retry outside it
    (`allowUnsandboxedCommands`, true unless a later file sets it false)."""
    domains: set[str] = set()
    excluded: set[str] = set()
    retry = True
    for data in _settings(root):
        box = data.get("sandbox")
        if not isinstance(box, dict):
            continue
        net = box.get("network")
        listed = net.get("allowedDomains") if isinstance(net, dict) else None
        domains |= {d for d in listed if isinstance(d, str)} if isinstance(listed, list) else set()
        commands = box.get("excludedCommands")
        excluded |= {c for c in commands if isinstance(c, str)} if isinstance(commands, list) else set()
        if isinstance(box.get("allowUnsandboxedCommands"), bool):
            retry = box["allowUnsandboxedCommands"]
    return domains, excluded, retry


OWN_COMMAND_RULES = {COMMAND_RULE, "Bash(aidd:*)", "Bash(aidd*)"}


def egress_limit(root: Path) -> str | None:
    """How the run's outbound traffic is held to an allowlist, as far as aidd can see, or None: what aidd cannot see
    counts as open. aidd's dev container holds all of it. Claude Code's sandbox holds only the shell commands it runs,
    so it is open with a web-fetch rule for any host, a mode that allows every tool, a `*` domain, an excluded command,
    a web MCP server, or a shell allow rule beside aidd's own while a failed command may retry outside the sandbox."""
    if DEVCONTAINER_EGRESS_LIST.is_file() and devcontainer_firewall_up():
        return f"aidd's dev container firewall is up and allows only the hosts in {DEVCONTAINER_EGRESS_LIST}"
    allowed, mode = _permissions(root)
    domains, excluded, retry = _sandbox_lists(root)
    shell_rules = {r for r in allowed if r.split("(", 1)[0] == "Bash"} - OWN_COMMAND_RULES
    if not sandbox_on(root) or mode == SKIPS_EVERY_CHECK or allowed & set(OPEN_FETCH_RULES) or "*" in domains or excluded:
        return None
    if (retry and shell_rules) or _web_servers(root):
        return None
    return "the sandbox holds shell commands to `sandbox.network.allowedDomains`, and no web tool may reach any host"


def rule_of_two_check(root: Path, env: Mapping[str, str] | None = None) -> tuple[str, str]:
    """A warning when an unattended run would hold all three legs of the Rule of Two; otherwise, which leg is missing."""
    inputs = untrusted_inputs(root)
    creds = credential_names(dict(os.environ if env is None else env))
    limit = egress_limit(root)
    if inputs and creds and limit is None:
        shown = "; ".join(inputs[:3]) + (f"; and {len(inputs) - 3} more" if len(inputs) > 3 else "")
        container = (
            f"start the dev container's firewall, which did not start here ({DEVCONTAINER_FIREWALL_ACTIVE} is missing or from an earlier start): rebuild the "
            f"container, or run `sudo {FIREWALL_SCRIPT}` and read why it stops"
            if devcontainer_firewall_down()
            else "run inside the dev container `aidd init --devcontainer` writes, with its firewall"
        )
        return (
            "warn",
            f"an unattended run here would hold all three legs of {RULE_OF_TWO}: untrusted input ({shown}), credentials in "
            f"the environment ({len(creds)} named like one), and egress that no allowlist limits. Text in a page or an issue "
            f"could then send a credential out. Drop one leg: {container}; or unset the credentials for the run; or remove "
            f"the web tool or server ({CREDENTIALS_DOC})",
        )
    missing = [] if inputs else ["no web tool, and no issue, browser, or web MCP server"]
    missing += [] if creds else ["no variable named like a credential"]
    missing += [limit] if limit else []
    unread = unread_harnesses(root)
    scope = f" in what aidd read, which leaves out the MCP servers of {_labels(unread)}" if unread else ""
    return ("ok", f"{RULE_OF_TWO} holds{scope}: {'; '.join(missing)}")


def autopilot_checks(root: Path, env: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """(level, message) for each check aidd can make: ok, warn, or fail, and info for which harnesses it read. It reads
    `.claude.json` once (_USER_RECORDS)."""
    token = _USER_RECORDS.set({})
    try:
        return _autopilot_checks(root, env)
    finally:
        _USER_RECORDS.reset(token)


def _hooks_line(level: str) -> tuple[str, str]:
    """The session hooks' level: below balanced, no stop reminder runs and no snapshot outlives a compaction."""
    if level in ("off", "minimal"):
        why = "so no stop reminder runs, and no snapshot keeps the run's state across a compaction"
        return ("warn", f"the hooks level is {level}, {why}: set `hooks.level` to `balanced` or `strict`")
    return ("ok", f"the hooks level is {level}")


def _autopilot_checks(root: Path, env: dict[str, str] | None) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not (root / config.CONFIG_PATH).is_file():
        return [("fail", "aidd is not set up here: run `aidd init` first")]
    try:
        cfg = config.load_file(config.CONFIG_PATH, str(root))
    except (config.ConfigError, OSError, ValueError) as exc:
        return [("fail", f"the config does not load: {exc}")]
    out.append(_hooks_line(config.hook_level(cfg.raw)))
    if wired := wired_harnesses(root):
        out.append(("ok", f"the guard is wired in {_labels(wired)} (aidd hook pre-tool)"))
    else:
        out.append(
            (
                "fail",
                "the guard is not wired: in Claude Code, run `aidd init --claude-hooks` or turn on the aidd plugin; in another "
                "agent, run `aidd init --harness <agent>`",
            )
        )
    tracked = [p for p in git.run(["ls-files", "-z"], str(root), check=False).split("\0") if p]
    found, _ = detection.held_commands(root, tracked)
    held = cfg.get("guard", "held_commands", default=[]) or []
    if found and not held:
        names = ", ".join(e["name"] for e in found[:3])
        out.append(("warn", f"deploy tooling is here ({names}) but `guard.held_commands` holds nothing: `aidd init --dry-run` prints the entries"))
    elif found:
        out.append(("ok", f"{len(held)} held command{'s' if len(held) != 1 else ''} for the deploy tooling found"))
    else:
        out.append(("ok", "no deploy tooling found, so no held command is needed"))
    creds = credential_names(env)
    if creds:
        shown = ", ".join(creds[:MAX_NAMES]) + (f", and {len(creds) - MAX_NAMES} more" if len(creds) > MAX_NAMES else "")
        out.append(("warn", f"{len(creds)} variable{'s' if len(creds) != 1 else ''} named like a credential reach the agent: {shown}. Unset them for the run"))
    else:
        out.append(("ok", "no variable named like a credential (names only; aidd never reads a value)"))
    out += token_checks(env)
    if devcontainer_firewall_down():
        out.append(
            (
                "warn",
                f"this is aidd's dev container, and its firewall did not start ({DEVCONTAINER_FIREWALL_ACTIVE} is missing), so "
                f"outbound traffic is open: rebuild the container, or run `sudo {FIREWALL_SCRIPT}` and read why it stops",
            )
        )
    out.append(rule_of_two_check(root, env))
    wired = wired_harnesses(root)
    out += [codex_git_check(root)] if "codex" in wired else []
    out += flow_checks(root, wired)
    note = harness_scope_note(root)
    # The sandbox, permission, and trust lines read Claude Code's settings, so they speak only where it is wired.
    return out + (permission_checks(root) if "claude-code" in wired else []) + ([note] if note else [])


# A headless OpenCode run (`opencode run`) passes `/aidd-autopilot` as plain text and asks nobody (opencode 2.1).
OPENCODE_HEADLESS = (
    "for a run nobody watches, `opencode run` passes `/aidd-autopilot` as plain text, so attach the flow and allow its "
    'steps: `opencode run --auto -f .opencode/commands/aidd-autopilot.md "all"` (docs/AUTOPILOT.md, Runs nobody watches)'
)


def flow_checks(root: Path, wired: list[str]) -> list[tuple[str, str]]:
    """For each harness whose guard aidd wired, whether the autopilot flow is there for it to run: the team's command
    file (`aidd init --team`), or in Claude Code the aidd-team plugin; and how OpenCode runs it with nobody there."""
    from aidd.setup import team_install

    out: list[tuple[str, str]] = []
    for key in wired:
        path = team_install.flow_command_file(key, "autopilot")
        label = config.HARNESSES[key].label
        if path and (root / path).is_file():
            out.append(("ok", f"{label} has the autopilot flow ({path})"))
        elif key == "claude-code" and f"aidd-team@{config.MARKETPLACE}" in config.plugins_enabled(root):
            out.append(("ok", "Claude Code has the autopilot flow (the aidd-team plugin)"))
        elif path:
            plugin = " or turn on the aidd-team plugin" if key == "claude-code" else ""
            out.append(("warn", f"{label} has no autopilot flow ({path}): run `aidd init --team --harness {key}`{plugin}"))
    if "opencode" in wired:
        out.append(("info", "OpenCode: " + OPENCODE_HEADLESS))
    return out


def advisor_model(root: Path) -> str | None:
    """Claude Code's `advisorModel` from the user's, the project's, and the local settings (a later file decides), or
    None. Managed settings and the `--advisor` flag are not seen."""
    found: str | None = None
    for path in config.claude_settings_paths(root):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value = data.get(ADVISOR_KEY) if isinstance(data, dict) else None
        if isinstance(value, str) and value.strip():
            found = value.strip()
    return found


def autopilot_advisor_line(root: Path, env: Mapping[str, str] | None = None) -> str:
    """One line of information about the advisor for an autopilot run; never a warning."""
    environ: Mapping[str, str] = os.environ if env is None else env
    model = advisor_model(root)
    if model and environ.get(ADVISOR_OFF_ENV):
        return f"{ADVISOR_KEY} = {model} is set, but {ADVISOR_OFF_ENV} turns it off for this environment"
    if model:
        return (
            f"an advisor is configured ({ADVISOR_KEY} = {model}), {ADVISOR_LIMITS}: a second opinion inside one session, never a "
            "substitute for the verifier, the reviewer, or independent review. Count its tokens in `aidd autopilot note --tokens`"
        )
    return f"no advisor is configured ({ADVISOR_KEY}): {ADVISOR_LIMITS}; AUTOPILOT.md's harness settings for a run recommend one"
