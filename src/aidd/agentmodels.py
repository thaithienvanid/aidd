"""Per-role models: `[agents.models]` maps a tier (`reasoning`, `execution`) or a role name to a `provider/model`
string, or to `inherit` (the session's model), and `aidd init --team` and `aidd upgrade` write it into each harness's
own agent model field. A role takes its own entry, else its tier's.

The field and its value format, per harness (each harness's docs, checked 2026-09-28):

- Claude Code, `.claude/agents/<name>.md`: `model:` takes an alias, `inherit`, or a full Claude model ID
  (code.claude.com/docs/en/sub-agents), so only an `anthropic/` model can go there.
- Codex, `.codex/agents/<name>.toml`: `model = "<name>"`, a bare OpenAI model name
  (learn.chatgpt.com/docs/agent-configuration/subagents), so only an `openai/` model can go there.
- OpenCode, `.opencode/agents/<name>.md`: `model: provider/model-id` (opencode.ai/docs/agents), any provider.
- Kiro, `.kiro/agents/<name>.json`: `"model": "<id>"` from Kiro's model service; an unavailable one falls back to the
  default with a warning (kiro.dev/docs/custom-agents/configuration-reference).
- GitHub Copilot, `.github/agents/<name>.agent.md`: `model:` a model name, honored by the cloud agent and the CLI
  (docs.github.com/en/copilot/reference/custom-agents-configuration).

Where a harness cannot run the configured model, the generated file says so and keeps the harness's default.
"""

from __future__ import annotations

import re

from . import resources

MODEL = re.compile(r"^[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._:\[\]-]*$")
# The provider a harness can run in its own agent model field; None means any provider it can reach.
HARNESS_PROVIDER = {"claude-code": "anthropic", "codex": "openai", "opencode": None, "kiro": None, "copilot": None}
# The two roles whose independence from the builder the config can require, and the builder they check.
INDEPENDENT = ("reviewer", "verifier")
BUILDER = "developer"
# The session's model: Claude Code's `model: inherit`, and an opt-in `[agents.models]` value for any tier or role.
INHERIT = "inherit"


def split(model: str) -> tuple[str, str]:
    """(`anthropic`, `claude-opus-5-5`) from `anthropic/claude-opus-5-5`."""
    if not MODEL.match(model):
        raise ValueError(f"[agents.models] value {model!r} is not provider/model, such as anthropic/claude-opus-5-5")
    provider, name = model.split("/", 1)
    return provider, name


def unknown_key_warnings(models: dict[str, str]) -> list[str]:
    """A `[agents.models]` key that names no tier and no role selects nothing. Say so: a stale or misspelt key must
    not pass in silence."""
    tiers = sorted(resources.TIER_MEANING)
    known = set(tiers) | set(resources.roles()["order"])
    return [f"[agents.models] key {key!r} names no tier ({', '.join(tiers)}) and no role, so it selects nothing" for key in sorted(models) if key not in known]


def resolve(models: dict[str, str], role: str) -> str | None:
    """The `provider/model` (or `inherit`) for `role`: its own entry, else its tier's, else None (the tier's default per
    harness)."""
    if role in models:
        return models[role]
    return models.get(resources.roles()["roles"][role]["tier"])


def family(model: str) -> str:
    """The model family: the provider and the model name's first word, so `acme/model-large-2` and
    `acme/model-small-1` are one family and `other/model-large-2` another."""
    provider, name = split(model)
    return f"{provider}/{re.split(r'[-_.:]', name, maxsplit=1)[0]}"


def harness_model(harness: str, model: str) -> str | None:
    """The value `harness` takes in its agent model field for `model`, or None when it cannot run that provider.
    `inherit` is Claude Code's own value for the session's model; any other harness then writes no model field, which
    runs its default, the session's."""
    if model == INHERIT:
        return INHERIT if harness == "claude-code" else None
    provider, name = split(model)
    wanted = HARNESS_PROVIDER[harness]
    if wanted and provider != wanted:
        return None
    return model if harness == "opencode" else name


def unsupported_note(model: str) -> str:
    """One line for a generated file whose harness cannot run the configured model."""
    return f"[agents.models] names {model}, which this harness's agent model field cannot select; the harness's default model runs this role."


def independent_review_warnings(models: dict[str, str], independent_review: bool) -> list[str]:
    """With `[agents] independent_review = true`, a warning for each of the Reviewer and the Verifier roles whose model is in
    the developer's family: a second reader on the same model tends to repeat the builder's blind spots. A role with no
    configured model cannot be compared, which is a warning too: the setting then promises something nothing checks."""
    if not independent_review:
        return []
    known = lambda m: m if m and m != INHERIT else None  # noqa: E731 - the session's model cannot be compared
    builder = known(resolve(models, BUILDER))
    out = []
    for role in INDEPENDENT:
        mine = known(resolve(models, role))
        if not builder or not mine:
            out.append(
                f"[agents] independent_review is on, but [agents.models] sets no model for the {role if not mine else BUILDER}. "
                f"Name one per role or tier, so aidd can check the {role} against the {BUILDER}"
            )
        elif family(mine) == family(builder):
            out.append(
                f"[agents] independent_review is on, but the {role} ({mine}) and the {BUILDER} ({builder}) are one model family "
                f"({family(mine)}); give the {role} a model from another family"
            )
    return out
