"""Per-role models: `agents.models` maps a tier (`reasoning`, `execution`) or a role name to a `provider/model`
string, or to `inherit` (the session's model), and `aidd init --aidd-team` and `aidd upgrade` write it into each harness's
own agent model field. A role takes its own entry, else its tier's.

The field and its value format, per harness (each harness's docs, checked 2026-09-28):

- Claude Code, `.claude/agents/<name>.md`: `model:` takes an alias, `inherit`, or a full Claude model ID
  (code.claude.com/docs/en/sub-agents), so only an `anthropic/` model can go there.
- Codex, `.codex/agents/<name>.toml`: `model = "<name>"`, a bare OpenAI model name
  (learn.chatgpt.com/docs/agent-configuration/subagents), so only an `openai/` model can go there.
- OpenCode, `.opencode/agents/<name>.md`: `model: provider/model-id` (opencode.ai/docs/agents), any provider.
- Kiro, `.kiro/agents/<name>.json`: `"model": "<id>"` from Kiro's model service; with an unavailable one the first
  prompt can fail instead of falling back to the default (kiro.dev/docs/custom-agents/configuration-reference).
- GitHub Copilot, `.github/agents/<name>.agent.md`: `model:` a model name, honored by the cloud agent and the CLI
  (docs.github.com/en/copilot/reference/custom-agents-configuration).
- Google Antigravity, `.agents/agents/<name>.md`: `model:` takes a tier, `inherit`, `flash`, or `pro`, never a model
  name (antigravity.google/docs/cli/headless; unset, the agent inherits the session's model), so a `google/` value is
  the tier, such as `google/pro`.
- Grok Build, `.grok/agents/<name>.md`: `model:` a bare model id, so only an `xai/` model goes there.

Where a harness cannot run the configured model, the generated file says so. Claude Code keeps the tier's alias, and
the other harnesses run their own default.
"""

from __future__ import annotations

import re

from aidd.knowledge import team_registry

MODEL = re.compile(r"^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._:\[\]-]*$")
# The provider a harness can run in its own agent model field; None means any provider it can reach.
HARNESS_PROVIDER = {
    "claude-code": "anthropic",
    "codex": "openai",
    "copilot": None,
    "antigravity": "google",
    "kiro": None,
    "opencode": None,
    "grok-build": "xai",
}
# The session's model: Claude Code's `model: inherit`, and an opt-in `agents.models` value for any tier or role.
INHERIT_MODEL = "inherit"


def split(model: str) -> tuple[str, str]:
    """(`anthropic`, `claude-opus-5-5`) from `anthropic/claude-opus-5-5`."""
    if not MODEL.match(model):
        raise ValueError(f"agents.models value {model!r} is not provider/model, such as anthropic/claude-opus-5-5")
    provider, name = model.split("/", 1)
    return provider, name


def unknown_key_warnings(models: dict[str, str], setting: str = "models") -> list[str]:
    """A key of `agents.models` (or `agents.<setting>`, such as `effort`) that names no tier and no role selects nothing.
    Say so: a stale or misspelt key must not pass in silence."""
    tiers = sorted(team_registry.TIER_MEANING)
    known = set(tiers) | set(team_registry.roles()["order"])
    return [f"agents.{setting} key {key!r} names no tier ({', '.join(tiers)}) and no role, so it selects nothing" for key in sorted(models) if key not in known]


def resolve_agent_effort(efforts: dict[str, str], role: str) -> str:
    """The reasoning effort for `role`: its own `agents.effort` entry, else its tier's, else the tier's default
    (team_registry.EFFORT_BY_TIER)."""
    tier = team_registry.roles()["roles"][role]["tier"]
    return efforts.get(role) or efforts.get(tier) or team_registry.EFFORT_BY_TIER[tier]


def resolve_agent_turns(turns: dict[str, int], role: str) -> int | None:
    """The turn limit `agents.max_turns` sets for `role`: its own entry, else its tier's, else None (the role keeps the number
    schemas/roles.json gives it, which stays the default's one owner)."""
    tier = team_registry.roles()["roles"][role]["tier"]
    return turns.get(role) or turns.get(tier)


def resolve_agent_model(models: dict[str, str], role: str) -> str | None:
    """The `provider/model` (or `inherit`) for `role`: its own entry, else its tier's, else None (the tier's default per
    harness)."""
    if role in models:
        return models[role]
    return models.get(team_registry.roles()["roles"][role]["tier"])


def harness_model(harness: str, model: str) -> str | None:
    """The value `harness` takes in its agent model field for `model`, or None when it cannot run that provider.
    `inherit` is Claude Code's own value for the session's model; any other harness then writes no model field, which
    runs its default, the session's."""
    if model == INHERIT_MODEL:
        return INHERIT_MODEL if harness == "claude-code" else None
    provider, name = split(model)
    wanted = HARNESS_PROVIDER[harness]
    if wanted and provider != wanted:
        return None
    return model if harness == "opencode" else name


def unsupported_note(model: str, kept: str | None = None) -> str:
    """One line for a generated file whose harness cannot run the configured model: the `kept` value (the tier's alias in
    Claude Code) runs the role, else the harness's own default does."""
    runs = f"this role runs `{kept}`, the tier's default" if kept else "the harness's default model runs this role"
    return f"agents.models names {model}, which this harness's agent model field cannot select; {runs}."
