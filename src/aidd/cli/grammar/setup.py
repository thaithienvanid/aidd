"""The Setup commands' arguments and flags: init, upgrade, uninstall, doctor, standard, and stack."""

from __future__ import annotations

from aidd import config


def _profiles_in_mode(mode: str) -> str:
    """The profiles that start in `mode`, from schemas/profiles.json, such as "solo and team"."""
    names = [p for p in config.profiles()["order"] if config.profile_mode(p) == mode]
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names) or "no profile"


def register(cmd, flag) -> None:
    """Add the setup commands with `cmd(name, help, "group:handler")` and `flag(parser, name, help)`."""
    s = cmd("init", "adopt aidd in a repository", "setup:cmd_init")
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(s, "--dry-run", "print what init finds (stacks, tests, sensitive areas, owners, CI) and the config it proposes; write nothing")
    s.add_argument(
        "--profile",
        choices=config.profiles()["order"],
        help="gate strictness (default: the config init keeps, else asked at a person's terminal, else team)",
    )
    s.add_argument("--ci", choices=["github", "gitlab", "none"], default="github", help="CI templates to install")
    s.add_argument(
        "--ref",
        metavar="SHA_OR_TAG",
        help="pin the CI files' aidd action and workflow to this commit SHA or release tag (default: the commit this aidd runs "
        "from, when it is a git checkout)",
    )
    s.add_argument("--approvers", nargs="+", metavar="WHO", help="owners.approvers, such as @org/team")
    s.add_argument(
        "--specialist", action="append", metavar="POOL=WHO", help="a specialist Approver pool (owners.specialists), such as security=@org/security (repeatable)"
    )
    s.add_argument("--test", metavar="COMMAND", help='the repository suite, such as "npm test"')
    s.add_argument("--goal", metavar="SENTENCE", help='the goal every agent steers by, such as "make onboarding succeed on the first try"')
    flag(
        s,
        "--team",
        "also install the delivery team (optional): an agent for each role, such as product manager, architect, verifier, developer, "
        "and reviewer, each kept to its own files, with the team commands and domain packs",
    )
    hooks = s.add_mutually_exclusive_group()
    flag(
        hooks,
        "--claude-hooks",
        "wire Claude Code's guard hook (.claude/settings.json) and the aidd MCP server (.mcp.json) even when Claude Code is not detected",
    )
    flag(hooks, "--no-claude-hooks", "do not wire the hook and the MCP server even when Claude Code is detected")
    s.add_argument(
        "--harness",
        action="append",
        choices=[*config.HARNESSES, "none"],
        metavar="AGENT",
        help="the coding agents to wire instead of detecting them: " + ", ".join(config.HARNESSES) + ", or none (repeatable)",
    )
    flag(s, "--claude-plugins", "install the aidd plugins for this user through the `claude` CLI instead of repository files for Claude Code")
    flag(
        s,
        "--mods",
        "with --claude-plugins, also install the optional aidd-mods plugin: `/aidd status`, a side pane of what waits on you "
        "(Claude Code 2.1.295 or later; experimental)",
    )
    flag(
        s,
        "--enforce",
        "install the gate in enforce mode; by default it starts in the profile's mode: advisory under "
        + _profiles_in_mode("advisory")
        + ", reporting on 'aidd/gate (advisory)' without blocking, and enforce under "
        + _profiles_in_mode("enforce"),
    )
    s.add_argument("--policy", metavar="COMMAND", help='policy.command, such as "./scripts/aidd-policy" (org and audited need one)')
    flag(
        s,
        "--devcontainer",
        "also write .devcontainer/: a dev container for agents that denies outbound traffic except to an allow-list (a starting point; aidd sandboxes nothing)",
    )
    flag(s, "--orca", "also write orca.yaml for Orca: aidd doctor after setup, and a tab with aidd list --branch (never replaces an existing one)")
    s.add_argument(
        "--compliance-target",
        action="append",
        choices=["soc2", "iso27001", "gdpr", "hipaa", "pci-dss", "fedramp", "cra", "other"],
        help="a framework or law the product answers to, for `project.compliance.targets`; any target turns compliance on: the enterprise-controls defaults and the security CI (repeatable)",
    )
    flag(
        s,
        "--security-ci",
        "also write the security CI when compliance is off: on GitHub .github/workflows/aidd-security.yml (dependency scan, SAST, SBOM, "
        "secret scan), on GitLab .gitlab/aidd-security.gitlab-ci.yml (secret scan)",
    )
    s.add_argument("--link", action="append", metavar="DIR", help="extra agent skill directory to link, besides .claude/skills (repeatable)")
    flag(s, "--no-skill", "do not vendor the skill (agents load the plugin instead)")
    flag(s, "--force", "overwrite existing files and upgrade the vendored skill")

    s = cmd(
        "upgrade",
        "bring a repository's aidd files up to this aidd: the skill, the team files, the guard in each agent's own files, the CI pins, and aidd_version; a dry run unless --yes. It refuses when the config names a newer aidd, and in aidd's own source unless it runs from that checkout",
        "setup:cmd_upgrade",
    )
    s.add_argument("path", nargs="?", default=".", help="repository root")
    s.add_argument("--ref", metavar="SHA_OR_TAG", help="pin the CI files to this aidd commit or release; default: this aidd's")
    flag(s, "--yes", "make the changes")

    s = cmd(
        "self-update",
        "update the aidd CLI to the latest release of thaithienvanid/aidd, the way it was installed (uv, pipx, or the one-line "
        "installer), from the release's wheel once it matches the release's SHA256SUMS (and its build provenance, with gh); "
        "once a day after a command a person runs at a terminal, aidd says when a release is out, never in CI, an agent's "
        "shell, or a hook (AIDD_NO_UPDATE_CHECK=1 turns that off; AIDD_AUTO_UPDATE=1 installs it instead)",
        "setup:cmd_self_update",
    )
    flag(s, "--check", "say what it would update to; change nothing")
    flag(s, "--main", "update to the tip of main instead: unreleased code, with no release to verify it against")

    s = cmd("uninstall", "reverse `aidd init`: list what it would remove, or remove it with --yes", "setup:cmd_uninstall")
    s.add_argument("path", nargs="?", default=".", help="the repository (default: the current directory)")
    flag(s, "--yes", "remove the files; without it, only list them")
    s.add_argument("--link", action="append", metavar="DIR", help="extra skill link directories given to `aidd init --link` (repeatable)")

    s = cmd(
        "extensions",
        "suggest the plugins from aidd's registry that fit this repository's stacks and the roles that use them, each with its tier, "
        "what it can touch, its pin, and the line a person runs to install it; it installs nothing",
        "setup:cmd_extensions",
    )
    s.add_argument("action", choices=["suggest"])
    s.add_argument("--role", help="only this role's, such as developer")
    flag(s, "--json", "print the suggestions as JSON")

    s = cmd("doctor", "check that a repository is wired correctly", "setup:cmd_doctor")
    s.add_argument("path", nargs="?", default=".", help="repository root")
    flag(
        s,
        "--autopilot",
        "check the settings for autopilot runs that aidd can see (the hooks level, the guard, held commands, "
        "credential-like variable names, the permissions a run needs), then list what only you can check (the sandbox, the network)",
    )
    flag(s, "--json", "print each check as JSON (schemas/doctor.schema.json)")

    s = cmd(
        "standard",
        "the choices the domain packs and practice skills leave open, each with aidd's default, and aidd's library of opinionated "
        "standards that fill them; `add` copies one into docs/standards/ with its `standards` entry and its `tests`, following "
        "`standards_policy`",
        None,
    )
    actions = s.add_subparsers(dest="standard_command", required=True, metavar="ACTION")
    s = cmd(
        "list",
        "the open choices and the library standards, with the company's policy and what this repository has",
        "setup:cmd_standard",
        into=actions,
        short="the open choices and the library standards",
    )
    flag(s, "--json", "print JSON")
    s = cmd(
        "add",
        "copy library standards into this repository, all or nothing: each file into docs/standards/, a `standards` entry that records "
        "its id, aidd's version, and its hash, and its `tests` (std.<group>.<topic>.<name>)",
        "setup:cmd_standard",
        into=actions,
        short="copy library standards into this repository",
    )
    s.add_argument("ids", nargs="+", metavar="ID", help="library ids, such as python/ruff-lint-format (`aidd standard list` lists them)")

    s = cmd(
        "stack",
        "stacks: opinionated standards that go together, plus the `project.stack` entries they bring; `add` copies a stack's standards, "
        "as `aidd standard add` does, and merges its entries into `project.stack`",
        None,
    )
    actions = s.add_subparsers(dest="stack_command", required=True, metavar="ACTION")
    s = cmd("list", "the library's stacks and their standards", "setup:cmd_stack", into=actions, short="the library's stacks")
    flag(s, "--json", "print JSON")
    s = cmd(
        "add", "copy one stack's standards into this repository and merge its `project.stack` entries", "setup:cmd_stack", into=actions, short="adopt one stack"
    )
    s.add_argument("name", metavar="NAME", help="the stack, such as python-cli (`aidd stack list` lists them)")
