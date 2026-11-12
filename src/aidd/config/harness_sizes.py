"""The sizes a coding agent's vendor documents for the text aidd writes, as data: each with its number, what the page says
happens past it, the page, and the date aidd read it. A limit that cuts, skips, drops, or refuses text is a hard limit, and
the tests hold aidd's text under it. A vendor's advice is guidance: the text still loads, so no test fails on it. A number
no page states is not here, and a page that gives a number and not the effect says `not stated`.

`LISTING_FACTS` holds what the vendor's pages say about how a skill gets into that listing, which decides how aidd puts a skill there.

Only a limit a coding agent really imposes belongs here. A cap aidd sets for its own reasons lives in tests/budgets.py, with
the cost it tracks beside it.
"""

from __future__ import annotations

import dataclasses

SPECIFICATION = "agent-skills"  # the open format Claude Code, Codex, Kiro, Mistral Vibe, and others read; a key of no harness


@dataclasses.dataclass(frozen=True)
class Size:
    """One documented size. `harness` is a key of `HARNESSES`, or `SPECIFICATION`. `past` is what the page says happens to
    text past `number`: `cut`, `skipped`, `dropped`, `guidance` (the text still loads), or `not stated`
    (the page gives the number and not the effect)."""

    harness: str
    what: str
    number: int
    unit: str  # characters, bytes, lines, or tokens
    past: str
    source: str  # the documentation page
    read: str  # the date aidd read it
    note: str = ""


@dataclasses.dataclass(frozen=True)
class Fact:
    """One documented behavior of a harness's skill listing: what the page says, the page, and the date aidd read it."""

    harness: str
    what: str
    says: str
    source: str
    read: str


_READ = "2026-11-11"
_SKILLS = "https://code.claude.com/docs/en/skills"
_MEMORY = "https://code.claude.com/docs/en/memory"
_AGENT_SKILLS = "https://agentskills.io/specification"

# Listed by harness, in the order of the harness table, with the open specification first. Within one, a skill's name and
# description come first, then the listing, then an instruction file.
SIZES: tuple[Size, ...] = (
    Size(
        SPECIFICATION, "a skill's name", 64, "characters", "not stated", _AGENT_SKILLS, _READ, "`Max 64 characters`, which the specification's validator checks"
    ),
    Size(
        SPECIFICATION,
        "a skill's description",
        1024,
        "characters",
        "not stated",
        _AGENT_SKILLS,
        _READ,
        "`Max 1024 characters`, which the specification's validator checks",
    ),
    Size(
        SPECIFICATION,
        "a skill's body",
        500,
        "lines",
        "guidance",
        _AGENT_SKILLS,
        _READ,
        "`Keep your main SKILL.md under 500 lines`; the page recommends under 5,000 tokens",
    ),
    Size(
        "claude-code",
        "a skill's or command's description, with its `when_to_use`, in the skill listing",
        1536,
        "characters",
        "cut",
        _SKILLS,
        _READ,
        "`skillListingMaxDescChars` changes it",
    ),
    Size(
        "claude-code",
        "the descriptions of all skills in the skill listing, at a 200,000-token context window",
        8000,
        "characters",
        "dropped",
        _SKILLS,
        _READ,
        "1% of the window (`skillListingBudgetFraction`), so five times that at 1 million tokens; past it Claude Code keeps every name and drops "
        "the descriptions of the least-used skills first. 8,000 is the vendor's fallback when the window is unknown "
        "(https://code.claude.com/docs/en/env-vars, `SLASH_COMMAND_TOOL_CHAR_BUDGET`). The other plugins and skills a person has share it",
    ),
    Size("claude-code", "a skill's body", 500, "lines", "guidance", _SKILLS, _READ, "`Keep SKILL.md under 500 lines`"),
    Size(
        "claude-code",
        "an MCP server's instructions",
        4096,
        "characters",
        "cut",
        "https://code.claude.com/docs/en/mcp",
        _READ,
        "2,048 characters before Claude Code v2.1.296; `CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` changes it",
    ),
    Size(
        "claude-code",
        "a CLAUDE.md file",
        200,
        "lines",
        "guidance",
        _MEMORY,
        _READ,
        "`target under 200 lines per CLAUDE.md file`: longer files cost context and adherence",
    ),
    Size("claude-code", "a CLAUDE.md file", 4 * 1024 * 1024, "bytes", "skipped", _MEMORY, _READ, "`Claude Code skips a file over 4 MiB and loads none of it`"),
    Size(
        "codex",
        "all the AGENTS.md files together",
        32 * 1024,
        "bytes",
        "skipped",
        "https://learn.chatgpt.com/docs/agent-configuration/agents-md",
        _READ,
        "`project_doc_max_bytes`, 32 KiB by default: Codex `stops adding files once the combined size reaches` it, so the cap is on the "
        "chain of files, not on one",
    ),
    Size(
        "codex",
        "the descriptions of all skills in the skill list",
        8000,
        "characters",
        "dropped",
        "https://learn.chatgpt.com/docs/build-skills",
        _READ,
        "at most 2% of the model's context window, or 8,000 characters when the window is unknown; Codex shortens descriptions first and may omit some skills",
    ),
    Size(
        "copilot",
        "a custom agent's prompt",
        30000,
        "characters",
        "not stated",
        "https://docs.github.com/en/copilot/reference/custom-agents-configuration",
        _READ,
        "`The prompt can be a maximum of 30,000 characters`; the page does not say what happens past it",
    ),
    Size("cursor", "a rule", 500, "lines", "guidance", "https://cursor.com/docs/context/rules", _READ, "`Keep rules under 500 lines`"),
    Size(
        "antigravity",
        "one rule file, such as AGENTS.md",
        24000,
        "bytes",
        "cut",
        "https://antigravity.google/docs/rules",
        _READ,
        "`truncates any single rule file that exceeds 24,000 bytes`, after includes are expanded; past an aggregate of 20,000 tokens it "
        "demotes the largest rule files to pointers",
    ),
    Size(
        "kiro",
        "a skill's name",
        64,
        "characters",
        "not stated",
        "https://kiro.dev/docs/skills",
        _READ,
        "`max 64 chars`; the page does not say what happens past it",
    ),
    Size(
        "kiro",
        "a skill's description",
        1024,
        "characters",
        "not stated",
        "https://kiro.dev/docs/skills",
        _READ,
        "`max 1024 chars`; the page does not say what happens past it",
    ),
    Size(
        "vibe",
        "a skill's description",
        1024,
        "characters",
        "not stated",
        "https://docs.mistral.ai/vibe/code/cli/skills",
        _READ,
        "`Up to 1,024 characters`; the page does not say what happens past it",
    ),
)


# What decides how aidd keeps a skill loadable and out of the listing, each fact confirmed on its page. No setting keeps a skill
# loadable by a model and unlisted: `disable-model-invocation` stops the model's own load and a role's preload, and `skillOverrides`
# skips plugin skills. So a skill that is found by name but must stay loadable, a domain pack, is a skill of a plugin a person adds.
LISTING_FACTS: tuple[Fact, ...] = (
    Fact(
        "claude-code",
        "a skill or command with `disable-model-invocation: true`",
        "Description not in context, full skill loads when invoked; `Claude can't invoke the skill on its own`, and a person can",
        _SKILLS,
        _READ,
    ),
    Fact(
        "claude-code",
        "a subagent's `skills` field",
        "`You can't preload skills that set disable-model-invocation: true`; without the field a subagent can still load project, user, and plugin skills through the Skill tool",
        "https://code.claude.com/docs/en/sub-agents",
        _READ,
    ),
    Fact(
        "claude-code",
        "a plugin skill and `skillOverrides`",
        "`Plugin skills are not affected by skillOverrides`, so its `name-only` and `off` states never apply to a skill of a plugin",
        _SKILLS,
        _READ,
    ),
    Fact(
        "claude-code",
        "the skill listing past its budget",
        "`The listing always contains every skill name`, and a skill without a description is still listed by its name, so a model told its name loads it",
        _SKILLS,
        _READ,
    ),
    Fact(
        "claude-code",
        "a plugin manifest's `skills` key",
        "`Adds to the default skills/ scan`: the default folder is still scanned, so a skill leaves a plugin only by moving out of its `skills/` folder",
        "https://code.claude.com/docs/en/plugins-reference",
        _READ,
    ),
)


def listing_budget() -> Size:
    """The row of the characters Claude Code lists for all skill descriptions at a 200,000-token window, the smallest it documents."""
    return next(s for s in SIZES if s.harness == "claude-code" and s.what.startswith("the descriptions of all skills"))


def listing_note(chars: int, where: str, next_step: str = "", by_name: int = 0) -> str:
    """One line saying how `chars` characters of skill descriptions, listed by `where`, stand against Claude Code's listing
    budget, which scales with the model's context window. It is a report: no harness refuses the text, so aidd fails nothing
    on it. Past the budget the note says what Claude Code does, how many of the characters are of skills a role or the lead
    loads by name (`by_name`, which lose nothing when their description drops), and `next_step`."""
    budget = listing_budget()
    named = (
        f" {by_name:,} of the characters belong to skills a role or the lead loads by name, which lose nothing when their description drops; "
        f"the other {chars - by_name:,} belong to skills a model finds from the description."
        if by_name
        else ""
    )
    effect = (
        f"At 200,000 tokens that is {chars - budget.number:,} over, and Claude Code drops the descriptions of the least-used skills "
        f"past the budget, keeping their names.{named} {next_step}".rstrip()
        if chars > budget.number
        else "That fits at 200,000 tokens."
    )
    return (
        f"{where} {chars:,} characters of skill descriptions. Claude Code lists at most 1% of the model's context window: "
        f"{budget.number:,} characters at 200,000 tokens, and five times that at 1 million (read {budget.read}). {effect}"
    )
