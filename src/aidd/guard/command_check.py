"""The command check: `check_command` puts the approval, git, held-command, and shell-write checks together."""

from __future__ import annotations

from aidd.guard import approval_commands, git_commands, held_commands, path_location, repo_config, shell_parser, verdicts, write_targets


def check_command(root: str | None, cwd: str, command: str, event: dict | None = None) -> verdicts.Verdict:
    """(decision, reason) for running `command` from `cwd`, for whoever `event` says is running it. `root` is the
    adopted repository the session works in, or None outside one: then only the writes are checked. Each obvious shell
    write is judged in the repository that holds its target: for an aidd-team role or a helper subagent, by the edit
    rules; for the main session, by `delegate`."""
    event = event or {}
    if "\x00" in command:  # no shell passes a NUL byte on, and a path holding one makes the path checks raise
        return "deny", "the command holds a NUL character, which no shell passes on; write it without one"
    if event.get("tool_name") == "PowerShell":
        command = shell_parser.powershell_plain(command)
    why = git_commands.autopilot_session_denial(command, event)
    if why:
        return "deny", why
    if root:
        why = approval_commands.forbidden_action(command, root, quoting=event.get("tool_name") != "PowerShell")
        if why:
            return "deny", why
        cfg = repo_config.load_config(root)  # None outside an aidd repository, or with a config that does not load
        problem = None if cfg else path_location.config_problem(root)
        try:
            if cfg:
                held = held_commands.held_command(cfg, command)
            elif problem:  # an invalid config never disables the guard: hold what `aidd init` could detect
                from aidd import setup

                held = held_commands.held_by(setup.default_held(), command)
                held = f"{problem}. Until then the guard holds the commands `aidd init` detects. {held}" if held else None
            else:
                held = None
        except Exception as exc:  # noqa: BLE001  # a held command never runs because the check broke
            kind = str(exc) if isinstance(exc, held_commands.CommandTooLong) else type(exc).__name__
            return (
                "deny",
                f"aidd could not check this command against the held commands: {kind}; ask a person to run it, or fix the config and run `aidd validate`",
            )
        if held:
            return "deny", held
    return write_targets.shell_writes(root, cwd, command, event)
