"""The generated skills and agent files: each domain pack, a practice skill's Standards table, the open choices and
where they go, and each agent file's tools and preloaded skills.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from aidd import knowledge
from aidd.docsgen import blocks, token_caps
from aidd.kernel import resources
from aidd.kernel import text as kernel_text

PACKS_DIR = "plugins/aidd-team/skills"
AGENTS_DIR = "plugins/aidd-team/agents"

# Claude Code names a plugin's MCP tool `mcp__plugin_<plugin>_<server>__<tool>`, and a project server from
# `.mcp.json` `mcp__<server>__<tool>`. The aidd plugin's server is `aidd`, and `aidd init` wires the same server
# into `.mcp.json` as `aidd` for a team installed as project files, so a role's `tools:` allowlist names both.
# Without them a subagent's allowlist hides the aidd tools its prompt tells it to use. A `tools:` entry
# `mcp__<server>__*` grants every tool of that server (code.claude.com/docs/en/sub-agents, "Available tools",
# checked 2026-09-28); every aidd MCP tool reads, computes, or checks, and none writes or approves.
MCP_TOOL_PREFIXES = ("mcp__plugin_aidd_aidd__", "mcp__aidd__")


# Built-in helper types a role may hand read-only work to, next to helpers of its own type (loop contract: "helpers
# of your own `aidd-team:<role>` type or read-only ones"). Explore is Claude Code's read-only search agent.
READ_ONLY_HELPERS = ("Explore",)

# Tools every role gets on top of its hand-chosen harness tools, in this order: `Skill` loads a practice skill or a
# domain pack by name, `Agent(...)` delegates to helpers, and `WebFetch`/`WebSearch` serve the research-first rule.
# The docs name the delegation tool `Agent` (it was `Task` before v2.1.63). Claude Code honors the type list in
# `Agent(a, b)` only for an agent run as the main thread (`claude --agent`); in a subagent it ignores the list
# (code.claude.com/docs/en/sub-agents, checked 2026-09-28, and a probe run on Claude Code 2.1.283 spawned an unlisted
# type). So the list states the rule, the guard hook denies writes from any helper that is not a role, and a
# read-only role (no write area) gets no `Agent` at all, as the docs advise for a reviewer that must stay read-only.
GENERATED_TOOLS = ("Skill", "Agent", "WebFetch", "WebSearch")


def split_tools(line: str) -> list[str]:
    """A `tools:` value as its entries: commas split them, except inside `Agent(a, b)`."""
    return [t.strip() for t in re.split(r",(?![^()]*\))", line) if t.strip()]


def role_tools(key: str, base: list[str]) -> list[str]:
    """A role's whole `tools:` list: its hand-chosen harness tools, the generated ones, and one server-level pattern per
    aidd MCP server. Only a role with a write area delegates (`Agent(aidd-team:<key>, Explore)`): the Reviewer and the
    Verifier work alone, so no helper they spawn can write on their behalf."""
    own = [t for t in base if not t.startswith("mcp__") and t.split("(", 1)[0] not in GENERATED_TOOLS]
    agent = f"Agent({', '.join((f'aidd-team:{key}', *READ_ONLY_HELPERS))})"
    delegates = bool(knowledge.roles()["roles"][key]["writes"])
    generated = [agent if t == "Agent" else t for t in GENERATED_TOOLS if t != "Agent" or delegates]
    return own + generated + [prefix + "*" for prefix in MCP_TOOL_PREFIXES]


def agent_with_tools(text: str, key: str | None = None) -> str:
    """An agent file whose front matter carries the generated `tools:` and `skills:` for its role.

    `tools:` keeps the file's hand-chosen harness tools (Read, Write, Bash, ...) and adds the generated ones; `skills:`
    is a YAML list, the form the subagent docs give for preloading. `key` defaults to the front matter's `name`.
    """
    end = text.index("\n---", 4)
    front = text[:end]
    m = re.search(r"^tools: (.*)$", front, re.M)
    if not m:
        raise ValueError("an aidd-team agent file needs a `tools:` line in its front matter")
    name = re.search(r"^name: (.*)$", front, re.M)
    key = key or (name.group(1).strip() if name else "")
    if key not in knowledge.roles()["roles"]:
        raise ValueError(f"an aidd-team agent file must be named for a role, not {key!r}")
    role = knowledge.roles()["roles"][key]
    front = front[: m.start()] + "tools: " + ", ".join(role_tools(key, split_tools(m.group(1)))) + front[m.end() :]
    front = re.sub(r"^(?:model|maxTurns): .*\n?", "", front + "\n", flags=re.M)
    front = re.sub(r"^skills:\n(?:  - .*\n?)*", "", front, flags=re.M).rstrip("\n")
    # The model follows the tier (team_registry.MODELS_BY_HARNESS), and `maxTurns` caps one run (Claude Code: a positive
    # integer, "maximum number of agentic turns (API round-trips) before stopping", read from 2.1.284's agent schema).
    front += f"\nmodel: {knowledge.tier_model(role['tier'])}\nmaxTurns: {role['max_turns']}"
    # The skills a role preloads: the aidd skill for a role that writes a Spec or tests, then the practice skills and
    # domain packs it uses on most runs. Every other role loads the aidd skill by name when it needs a rule.
    skills = [*([knowledge.CORE_SKILL] if preloads_core(key) else []), *(f"aidd-team:{x}" for x in role.get("preload", []))]
    if skills:
        front += "\nskills:\n" + "".join(f"  - {s}\n" for s in skills).rstrip("\n")
    return front + text[end:]


def preloads_core(key: str) -> bool:
    """Whether role `key` preloads the aidd skill (11 KB into every run): only a role that writes a Spec, a Spec stub,
    or tests, where the Spec format and the frozen-test rules are the work itself."""
    r = knowledge.roles()["roles"][key]
    return bool({"{spec}", "{specs_dir}", "{tests}"} & set(r["writes"])) or "{tests}" in r.get("writes_unfrozen", [])


# A pack's checklist item for before the first edit, when `aidd gate --paths` gives the route and the lane.
ENTRY_LABEL = "Before the first edit (`aidd gate --paths`)"


# A pack's description: scoped to aidd repositories first, so it never fires elsewhere, then the nouns a change names.
PACK_TRIGGER = "In an aidd repository, use when code touches "

# The pack template, in order; `aidd eval packs` fails on a pack or a file that breaks it. A section in brackets
# appears only when the registry has something for it.
PACK_SECTIONS = (
    "Scope",
    "Terms",
    "Standards",
    "Dated obligations",
    "Invariants and missed cases",
    "Checklist by loop step",
    "Test commands",
    "Owned elsewhere",
    "References",
    "Keep it current",
)

# The one line every pack ends with: what the registry's dates mean, and where a missing standard goes.
KEEP_CURRENT = (
    "Each entry is due after its `review_every_days` (else emerging 90 days, established 365) or by its `review_due`. An emerging one "
    "applies only when the change needs it, said in the Spec. One `aidd eval standards` lists as due is looked up in Specify, and a "
    "missing one is proposed to aidd's `schemas/roles.json`."
)


def standard_row(s: dict) -> list[str]:
    """A standard's cells in a pack or practice skill: the name (marked emerging), the bare edition, the date, and the
    source. The edition's history stays in the registry's `notes`, which no skill renders."""
    name = s["name"] + (" (emerging)" if s.get("maturity") == "emerging" else "")
    date = s["checked"] if s.get("checked") else f"{s['reviewed']} (reviewed)"
    return [name, s.get("release") or "—", date, f"<{s['source']}>" if s.get("source") else "—"]


def _labels(d: dict) -> dict[str, str]:
    """Each pack standard's short label, `S1` to `S10`, in the order the pack lists them."""
    return {s["id"]: f"S{i}" for i, s in enumerate(d["standards"], 1)}


def pack_scope(d: dict) -> str:
    """The Scope section's text: applies when, not when, and the neighbours."""
    near = ", ".join(f"`aidd-team:{x}`" for x in d["scope"]["neighbours"])
    return f"Applies when the change touches {d['signal']}. Not when {d['scope']['not_when']}. Neighbours: {near}."


def defaults_row(d: dict) -> str:
    """The one checklist row that points to the product defaults a pack's domain builds."""
    keys = ", ".join(f"`{k}`" for k in d["defaults"])
    return f"Product defaults ({keys}): build each one `project.defaults.disabled` does not name, as `aidd-team:product-defaults` says."


def render_pack(d: dict, choices: bool = True) -> str:
    """One domain pack: a skill generated from schemas/roles.json, in the pack template's order (PACK_SECTIONS)."""
    label = _labels(d)

    def cited(ids: list[str]) -> str:
        return ", ".join(label.get(x, x) for x in ids)

    preloaded = d["slug"] in preloaded_skills()
    stds = _standards_table(d, label, preloaded)
    rows = [[ENTRY_LABEL if c["step"] == "Entry" else c["step"], c["item"], cited(c["cites"])] for c in d["checklist"]]
    if d.get("defaults"):
        at = max((i for i, c in enumerate(d["checklist"]) if c["step"] == "Entry"), default=-1) + 1
        rows.insert(at, [ENTRY_LABEL, defaults_row(d), "—"])
    # A harness picks a skill by its description: scoped to aidd repositories, then the nouns a change names. Every
    # session and every subagent lists every description, so it stays under 200 characters.
    description = f"{PACK_TRIGGER}{kernel_text.series(d['triggers'], 'or')}."
    parts = [
        f"---\nname: {d['slug']}\ndescription: {json.dumps(description)}\n---\n",
        "<!-- generated by `aidd gen-docs` from schemas/roles.json; edit the registry, not this file -->\n",
        f"# {d['name']}\n",
        f"## Scope\n\n{pack_scope(d)}\n",
    ]
    if d.get("terms"):
        parts.append("## Terms\n\n" + "\n".join(f"- **{t['term']}**: {t['meaning']}" for t in d["terms"]) + "\n")
    parts.append(f"## Standards\n\n{stds}\n")
    if choices and open_choices_placement(d["slug"]) == "skill":
        parts[-1] += f"\n{open_choices_section(d['slug'])}\n"
    if d.get("obligations"):
        parts.append(
            f"## Dated obligations\n\n{blocks.markdown_table('From | Obligation | Standard', ([o['date'], o['what'], cited(o['cites'])] for o in d['obligations']))}\n"
        )
    if d.get("invariants"):
        rows_inv = ([i["holds"], i["missed"]] for i in d["invariants"])
        parts.append(f"## Invariants and missed cases\n\n{blocks.markdown_table('Always true | The case a plan misses', rows_inv)}\n")
    parts.append(f"## Checklist by loop step\n\n{blocks.markdown_table('Step | Item | Standard', rows)}\n")
    parts.append(_tests_section(d, cited))
    if d.get("owned_elsewhere"):
        parts.append("## Owned elsewhere\n\n" + "\n".join(f"- {x['what']}: `aidd-team:{x['owner']}`." for x in d["owned_elsewhere"]) + "\n")
    refs = [f"- [{r['path']}]({r['path']}): {r['holds']}." for r in d.get("references", [])]
    # A pack no role preloads, whose choices would pass its cap, points to them itself; a preloaded one adds no bytes.
    if choices and d["slug"] not in preloaded_skills() and open_choices_placement(d["slug"]) == "reference":
        refs.append(f"- [references/{OPEN_CHOICES_REF}](references/{OPEN_CHOICES_REF}): its open choices, with aidd's defaults.")
    if refs:
        parts.append("## References\n\n" + "\n".join(refs) + "\n")
    parts.append(f"## Keep it current\n\n{preloaded_pointer(d['slug']) if preloaded else KEEP_CURRENT}\n")
    return "\n".join(parts)


def _standards_table(d: dict, label: dict[str, str], preloaded: bool) -> str:
    """A pack's Standards table. A preloaded pack, as a preloaded practice skill does, leaves the dates and sources to
    the roles reference."""
    if preloaded:
        return blocks.markdown_table("# | Standard | Edition", ([label[s["id"]], *standard_row(s)[:2]] for s in d["standards"]))
    return blocks.markdown_table("# | Standard | Edition | Checked | Source", ([label[s["id"]], *standard_row(s)] for s in d["standards"]))


def _tests_section(d: dict, cited) -> str:
    """A pack's Test commands: its own commands, then the ones it points to in other skills."""
    tests = []
    if d["tests"]:
        rows = (
            [t["name"] + (" (emerging)" if t.get("maturity") == "emerging" else ""), t["proves"], t["how"], cited(t.get("cites", [])) or "—"]
            for t in d["tests"]
        )
        tests.append(blocks.markdown_table("Command | Proves | How | Standard", rows))
    if d.get("tests_elsewhere"):
        tests.append("\n".join(f"- From `aidd-team:{x['owner']}`: {', '.join(x['tests'])}." for x in d["tests_elsewhere"]))
    return "## Test commands\n\n" + "\n\n".join(tests) + "\n"


OPEN_CHOICES_REF = "open-choices.md"


def preloaded_skills() -> set[str]:
    """The packs and practice skills some role preloads: their SKILL.md loads into every run of that role."""
    return {x for r in knowledge.roles()["roles"].values() for x in r.get("preload", [])}


# A preloaded skill loads whole into every run of its role, but a standard's checked date and source matter only when
# a role looks up or records an edition. So a preloaded skill carries each standard's name and edition and this
# pointer; the full rows and when an entry is due are in the roles reference, once (`roles:preloaded`).
def preloaded_pointer(name: str) -> str:
    return f"Each standard's checked date and source are in {knowledge.ROLE_REFERENCE}, section `aidd-team:{name}`."


def preloaded_sections() -> str:
    """Each preloaded pack's and practice skill's Standards rows in full (`roles:preloaded`): the edition, the checked
    date, and the source. The skill itself carries only the names and editions."""
    data = knowledge.roles()
    out = [KEEP_CURRENT]
    for name in sorted(preloaded_skills()):
        pack = next((d for d in data["domains"] if d["slug"] == name), None)
        if pack is not None:
            label = _labels(pack)
            table = blocks.markdown_table("# | Standard | Edition | Checked | Source", ([label[s["id"]], *standard_row(s)] for s in pack["standards"]))
        else:
            table = blocks.markdown_table("Standard | Edition | Checked | Source", (standard_row(s) for s in data["practices"][name]["standards"]))
        out.append(f"### aidd-team:{name}\n\n{table}")
    return "\n\n".join(out)


def open_choices_section(owner: str) -> str:
    """The open choices of a pack or practice skill, as they appear inside its SKILL.md."""
    return (
        "### Open choices\n\nThe team decides these. aidd's default holds until a `standards` entry fills one "
        f"(`aidd standard list`).\n\n{knowledge.open_choices_table(owner)}"
    )


def open_choices_reference(owner: str) -> str:
    """`references/open-choices.md` of a pack or practice skill that is preloaded or near its cap."""
    return (
        "<!-- generated by `aidd gen-docs` from schemas/roles.json; edit the registry, not this file -->\n\n"
        f"# Open choices: {owner}\n\n"
        f"`aidd-team:{owner}` leaves these decisions to the team. aidd's default holds until a `standards` entry fills one. "
        "`aidd standard list` names the library standards for each choice, and `aidd standard add` adopts one.\n\n"
        f"{knowledge.open_choices_table(owner)}\n"
    )


def open_choices_placement(owner: str) -> str | None:
    """Where a pack's or practice skill's open choices go: `skill` (its SKILL.md), `reference` (its generated
    `references/open-choices.md`, when a role preloads the skill or the section would pass its cap), or None (none)."""

    if not any(c["owner"] == owner for c in knowledge.open_choices().values()):
        return None
    if owner in preloaded_skills():
        return "reference"
    extra = token_caps.estimate_tokens(open_choices_section(owner)) + 1
    pack = next((d for d in knowledge.roles()["domains"] if d["slug"] == owner), None)
    if pack is not None:
        return "reference" if token_caps.estimate_tokens(render_pack(pack, choices=False)) + extra > token_caps.CHOICES_INLINE_TOKENS else "skill"
    path = resources.data_dir("team") / "skills" / owner / "SKILL.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    block = f"practice:{owner}"
    without = blocks.BLOCK.sub(lambda m: f"{m.group(1)}{practice_standards(owner, choices=False)}\n{m.group(4)}" if m.group(2) == block else m.group(0), text)
    return "reference" if token_caps.estimate_tokens(without) + extra > token_caps.PRACTICE_TOKENS else "skill"


def practice_standards(name: str, choices: bool = True) -> str:
    """A practice skill's Standards table (`practice:<name>`), from its registry ids, so `aidd eval standards` checks each."""
    entry = knowledge.roles().get("practices", {}).get(name)
    if entry is None:
        raise KeyError(f"practice skill {name!r} has no `practices` entry in schemas/roles.json")
    if name in preloaded_skills():
        # A preloaded skill keeps the name and edition; the dates and sources are in the roles reference.
        table = blocks.markdown_table("Standard | Edition", (standard_row(s)[:2] for s in entry["standards"]))
        return f"{table}\n\n{preloaded_pointer(name)}"
    table = blocks.markdown_table("Standard | Edition | Checked | Source", (standard_row(s) for s in entry["standards"]))
    return table + (f"\n\n{open_choices_section(name)}" if choices and open_choices_placement(name) == "skill" else "")


def pack_path(root: Path, d: dict) -> Path:
    return root / PACKS_DIR / d["slug"] / "SKILL.md"
