"""Who may stand in for a person at their terminal: where a `--confirmed` answer counts, and whether the person at this
machine can approve here at all. `aidd approve` and `aidd ship` read both."""

from __future__ import annotations

import re

from aidd import config, gate
from aidd.cli import arguments
from aidd.kernel import git

# Where `--confirmed` says the person confirmed (`--confirmed-in`): the aidd-mods plugin in Claude Code, from a prompt
# the person typed or its dialog; an MCP client's elicitation dialog (`mcp:<client>`); or a prompt the person typed,
# which aidd's own prompt hook records (`prompt`). The record carries it.
CONFIRMED_IN = "claude-code"
CONFIRMED_WHERE = re.compile(r"claude-code|prompt|mcp:[A-Za-z0-9.:_-]{1,48}")


def confirmation_problem(confirmed_in: str) -> str | None:
    """Why a `--confirmed` answer cannot stand in for a person at their terminal, or None. `--confirmed` skips the check
    that an agent started this shell, so something else must keep an agent from typing it: aidd's MCP server in its own
    process (`mcp:`), aidd's prompt hook in its own process (`prompt`), or, for aidd-mods (`claude-code`), the guard,
    which always denies an agent's `--confirmed`."""
    if not CONFIRMED_WHERE.fullmatch(confirmed_in):
        return f"--confirmed-in {confirmed_in!r} must be claude-code, prompt, or mcp:<client>"
    if confirmed_in.startswith("mcp:"):
        if not arguments.in_mcp_dialog():
            return "an MCP client's confirmation counts only from aidd's MCP server, which asks the person itself. Type `/aidd approve` instead"
        return None
    if confirmed_in == "prompt":
        return None if arguments.in_prompt_hook() else "a typed prompt counts only from aidd's own prompt hook, which reads what the person typed"
    return None


def standing_identity() -> tuple[str | None, str | None]:
    """Who a standing approval recorded here counts as: (the person's platform login to record with it, or None, and
    why it would never count, or None). Locally the email decides (local_identity_problem). Where a platform's gate
    decides and the Approvers are logins, the person's own token names them: of the accounts `gh` holds, the one that
    is an Approver, whichever is active. A record that matches no Approver is refused up front, never recorded to
    count for nothing."""
    from aidd import platforms

    if gate.platform_of(".") != "preflight":
        return None, None
    cfg = arguments.config_or_none()
    if cfg is None:
        return None, None
    pool = {config.normalize_identity(str(a)) for a in cfg.approvers}
    email = git.config_value("user.email")
    login, why = platforms.person_login(list(cfg.approvers))
    if login and config.normalize_identity(login) in pool:
        return login, None
    if email and config.normalize_identity(f"email:{email}") in pool:
        return None, None
    who = platforms.not_an_approver_problem(login, list(cfg.approvers)) if login else f"aidd cannot name you on GitHub ({why})"
    return None, f'it would never count here: {who}. Or add "email:{email or "you@example.com"}" to owners.approvers'


def local_identity_problem() -> str | None:
    """Locally, an approval counts as `email:<git user.email>`: why the person at this terminal could never approve here,
    or None. Only where the local gate is the gate: a preflight's approvals come from the platform."""
    if gate.platform_of(".") != "local":
        return None
    cfg = arguments.config_or_none()
    if cfg is None:
        return None
    email = git.config_value("user.email")
    who = f"email:{email}" if email else ""
    if who and config.normalize_identity(who) in {config.normalize_identity(a) for a in cfg.approvers}:
        return _signing_problem(cfg)
    emails = [str(a).removeprefix("email:") for a in cfg.approvers if str(a).startswith("email:")]
    quick = (
        f"If {' or '.join(emails)} is yours, set it for this repository: `git config user.email {emails[0] if len(emails) == 1 else '<yours>'}`, "
        "then decide again. Otherwise add "
        if emails
        else "Add "
    )
    return (
        f"the local gate counts an approval from this machine as {who or 'nobody: git user.email is not set'}, and owners.approvers lists "
        f'{", ".join(cfg.approvers) or "nobody"}, so it would never count. {quick}"{who or "email:you@example.com"}" to owners.approvers in '
        f"{config.CONFIG_PATH} with a commit of your own on the base branch (never an agent's)"
    )


def _signing_problem(cfg) -> str | None:
    """Where approvals must be signed (`gates.local_approvals: signed`), why one from this machine would never count:
    git signs nothing here. None when it signs, or when nothing asks for a signature."""
    from aidd import workitems

    if cfg.gates.get("local_approvals") != "signed" or workitems.is_signing_configured("."):
        return None
    return (
        'approvals here must be signed (gates.local_approvals: "signed"), and git on this machine signs nothing, so it would never '
        "count. Point git at your SSH key, the one listed in the signers file on the base branch: `git config gpg.format ssh` and "
        "`git config user.signingkey ~/.ssh/id_ed25519.pub`. Then decide again"
    )
