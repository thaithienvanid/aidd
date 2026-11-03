"""Generate the Markdown blocks that restate schemas and the CLI, so docs and their sources never drift: one block by
name (`render`), and every block, pack, and agent file in the repository (`gen_docs`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from aidd import config, knowledge, risk
from aidd.docsgen import blocks as docsgen_blocks
from aidd.docsgen import cli_reference, counts, diagrams, pack_render, schema_tables, team_reference
from aidd.kernel import json_schema
from aidd.kernel import text as kernel_text


def inline_list(name: str) -> str:
    """A list inside a sentence: `list:team-commands` names every flow's command, the first one in full;
    `list:ask-rule-harnesses` names the agents `aidd init` writes the ask rules for; `list:reasoning-roles` the roles on
    the reasoning tier, with their number first."""
    if name == "ask-rule-harnesses":
        labels = [h.label for h in config.ask_rule_harnesses()]
        return ", ".join(labels[:-1]) + f", and {labels[-1]}" if len(labels) > 2 else " and ".join(labels)
    if name == "reasoning-roles":
        data = knowledge.roles()
        names = [f"the {k.replace('-', ' ')}" for k in data["order"] if data["roles"][k].get("tier") == "reasoning"]
        number = ("Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine")[len(names) - 2] if 2 <= len(names) <= 9 else str(len(names))
        return f"{number} roles use the strongest model your harness offers (the `reasoning` tier): " + ", ".join(names[:-1]) + f", and {names[-1]}"
    if name != "team-commands":
        raise KeyError(name)
    commands = team_reference.team_commands()
    return ", ".join([f"`/aidd-team:{commands[0]}`", *(f"`{c}`" for c in commands[1:])])


def _needs_cli(name: str, cli: cli_reference.CliFacts | None) -> cli_reference.CliFacts:
    if cli is None:
        raise ValueError(f"generated block {name!r} reads the command line: pass cli=cli.cli_facts()")
    return cli


def render(name: str, cli: cli_reference.CliFacts | None = None) -> str:
    """One generated block. The blocks that restate the command line or the MCP server (`cli:*`, `mcp:*`) need `cli`."""
    kind, _, arg = name.partition(":")
    prefixed = {
        "fields": schema_tables.fields_table,
        "count": lambda x: str(counts.count(x)),
        "list": inline_list,
        "vocab": schema_tables.vocab_table,
        "role": team_reference.role_block,
        "practice": pack_render.practice_standards,
    }
    if kind in prefixed:
        return prefixed[kind](arg)
    blocks = {
        "mcp:revisions": lambda: kernel_text.series(list(_needs_cli(name, cli).mcp_supported), "and"),
        "mcp:latest": lambda: _needs_cli(name, cli).mcp_protocol,
        "mcp:tools": lambda: kernel_text.series([f"`{t}`" for t in _needs_cli(name, cli).mcp_tools], "and"),
        "cli:commands": lambda: cli_reference.cli_table(_needs_cli(name, cli)),
        "cli:when": lambda: cli_reference.when_table(_needs_cli(name, cli)),
        "cli:everyday": lambda: cli_reference.everyday_table(_needs_cli(name, cli)),
        "cli:exit": lambda: cli_reference.exit_table(_needs_cli(name, cli)),
        "steps": team_reference.step_codes_table,
        "workitems": team_reference.work_items,
        "cli:env": counts.env_table,
        "profiles": schema_tables.profiles_table,
        "status:groups": schema_tables.groups_table,
        "risks:areas": lambda: risk_areas_table(),
        "harnesses:ask-rules": lambda: ask_rules_table(),
        "risks:rules": lambda: risk_rules_table(),
        "risks:actions": lambda: risk_actions_table(),
        "roles:capabilities": team_reference.capabilities_table,
        "roles:commands": lambda: (
            "- **Commands:** "
            + ", ".join(f"`/aidd-team:{f['command']}`" for f in knowledge.roles()["loop"]["flows"])
            + "; one per flow in the registry, each running its roles in order and stopping where a person decides. "
            + "`/aidd-team:autopilot` runs those flows one after another, picking each step from `aidd status`, and stops at each ask."
        ),
        "roles:loop": team_reference.loop_tables,
        "roles:lead": team_reference.lead_block,
        "roles:contract": team_reference.contract_block,
        "roles:by-role": team_reference.role_sections,
        "roles:preloaded": pack_render.preloaded_sections,
        "roles:tiers": team_reference.tiers_table,
        "roles:documents": team_reference.documents_table,
        "roles:loops": team_reference.loops_text,
        "roles:decisions": team_reference.decision_rights_text,
        "roles:loop:diagram": diagrams.loop_diagram,
        "roles:flows:diagram": diagrams.flows_diagram,
        "roles:handoffs:diagram": diagrams.handoffs_diagram,
        "harnesses": config.harnesses_table,
        "standards:open-choices": lambda: knowledge.catalog_choices(),
        "standards:library": lambda: knowledge.catalog_library(),
        "standards:stacks": lambda: knowledge.catalog_stacks(),
        "harnesses:summary": counts.harnesses_summary,
    }
    if name in blocks:
        return blocks[name]()
    return team_reference.roles_table(name)


def ask_rules_table() -> str:
    """Each harness `aidd init` writes the ask rules for: the file, what it writes there, and how that harness matches a
    command (`risk.FORMATS`)."""
    rows = []
    for h in config.ask_rule_harnesses():
        f = risk.FORMATS[str(h.ask_rules)]
        rows.append([h.label, f"`{f.path}`", f.shape, risk.MATCHES[f.match]])
    return docsgen_blocks.markdown_table("Harness | File | What aidd writes | How it matches a command", rows)


def risk_areas_table() -> str:
    """The built-in risk areas (schemas/risks.json): each with the route it raises a change to, its dimensions, and a
    few of its paths."""
    rs = risk.rule_set(None)
    rows = []
    for name, area in rs.areas.items():
        sample = ", ".join(f"`{p}`" for p in area["paths"][:3]) + (f", and {len(area['paths']) - 3} more" if len(area["paths"]) > 3 else "")
        level = risk.edit_level(rs, [], role=None)[0]
        for r in rs.rules:
            if r.action == "code.edit" and r.area == name:
                level = r.level
        rows.append([f"`{name}`", area.get("description", ""), area.get("route", "minor"), ", ".join(area.get("dimensions", [])) or "none", level, sample])
    return docsgen_blocks.markdown_table("Area | What it holds | Raises the route to | Dimensions | Editing it | Paths, such as", rows)


def risk_rules_table() -> str:
    """The built-in risk rules (schemas/risks.json), in the order the file lists them."""
    rows = [[f"`{r.action}`", r.area or "any", r.branch or "any", f"**{r.level}**"] for r in risk.rule_set(None).rules]
    return docsgen_blocks.markdown_table("Action | Area | Branch | Level", rows)


def risk_actions_table() -> str:
    """The built-in actions (schemas/risks.json): what each is, and a command it matches."""
    rows = []
    for name, spec in risk.builtin()["actions"].items():
        example = f"`{spec['commands'][0]}`" if spec.get("commands") else (spec.get("examples") or [""])[0]
        rows.append([f"`{name}`", spec.get("description", ""), example])
    return docsgen_blocks.markdown_table("Action | What it is | Such as", rows)


def targets(root: Path) -> list[Path]:
    found = []
    for pattern in ("*.md", "docs/**/*.md", ".agents/skills/**/*.md", "plugins/**/*.md"):
        found += [p for p in root.glob(pattern) if p.is_file() and not p.is_symlink()]
    return sorted(set(found))


def empty_tables(text: str) -> int:
    """How many Markdown tables in `text` have a header and no rows."""
    empty, run = 0, 0
    for line in [*text.splitlines(), ""]:
        if line.startswith("|"):
            run += 1
            continue
        empty += run in (1, 2)
        run = 0
    return empty


def _render_checked(name: str, cli: cli_reference.CliFacts | None = None) -> str:
    out = render(name, cli)
    if empty_tables(out):
        raise ValueError(f"generated block {name!r} rendered a table with no rows; its source is empty or a $ref did not resolve")
    return out


TOC = "toc"


def _slug(heading: str) -> str:
    """A heading's anchor as GitHub writes it: lower case, punctuation dropped, spaces as hyphens."""
    # Code spans keep their text (`<ID>` stays `ID`); outside them, a tag drops and a link keeps its words.
    tag_or_link = re.compile(r"<[^>]+>|\[([^\]]*)\]\([^)]*\)")
    parts = heading.split("`")
    plain = "".join(p if i % 2 else tag_or_link.sub(lambda m: m.group(1) or "", p) for i, p in enumerate(parts)).strip().lower()
    return re.sub(r"[^\w\- ]", "", plain).replace(" ", "-")


def contents(text: str) -> str:
    """The page's own contents list: each `##` heading outside code, linked to its anchor (a repeated one numbered as
    GitHub numbers it)."""
    seen: dict[str, int] = {}
    lines = []
    for heading in re.findall(r"^## +(.+?) *#*$", re.sub(r"^(```|~~~).*?^\1", "", text, flags=re.S | re.M), re.M):
        slug = _slug(heading)
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        lines.append(f"- [{heading}](#{slug if n == 0 else f'{slug}-{n}'})")
    return "\n".join(lines) if lines else "- (no sections)"


def regenerate(text: str, cli: cli_reference.CliFacts | None = None) -> str:
    def fill(block: re.Match[str]) -> str:
        return block.group(0) if block.group(2) == TOC else f"{block.group(1)}{_render_checked(block.group(2), cli)}\n{block.group(4)}"

    text = docsgen_blocks.BLOCK.sub(fill, text)
    text = docsgen_blocks.INLINE.sub(lambda m: f"{m.group(1)}{render(m.group(2), cli)}{m.group(4)}", text)
    # The contents list last, from the headings the page now has.
    return docsgen_blocks.BLOCK.sub(lambda m: f"{m.group(1)}{contents(text)}\n{m.group(4)}" if m.group(2) == TOC else m.group(0), text)


def gen_docs(root: Path, check: bool = False, cli: cli_reference.CliFacts | None = None) -> list[Path]:
    """Return the files that are (or were) stale. `cli` is the command line's facts, for the `cli:*` and `mcp:*`
    blocks (`cli.cli_facts()`); without it, a target that holds one fails."""
    stale: list[Path] = []

    def update(path: Path, new: str) -> None:
        if not path.is_file() or path.read_text(encoding="utf-8") != new:
            stale.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(new, encoding="utf-8")

    for path in targets(root):
        text = path.read_text(encoding="utf-8")
        is_agent = path.parent == root / pack_render.AGENTS_DIR
        if "<!-- aidd:gen " in text or is_agent:
            new = regenerate(text, cli)
            update(path, pack_render.agent_with_tools(new, path.stem) if is_agent else new)
    # The config schema as one file an editor reads (the modeline `aidd init` writes names it).
    if (root / "schemas" / "config.schema.json").is_file():
        update(root / config.EDITOR_SCHEMA, json.dumps(json_schema.bundled("config.schema.json"), indent=2, ensure_ascii=False) + "\n")
    for d in knowledge.roles()["domains"]:
        update(pack_render.pack_path(root, d), pack_render.render_pack(d))
    # A preloaded skill, or one near its cap, carries its open choices in a generated reference instead.
    owners = {c["owner"] for c in knowledge.open_choices().values()}
    for owner in sorted(owners):
        if pack_render.open_choices_placement(owner) == "reference":
            update(root / pack_render.PACKS_DIR / owner / "references" / pack_render.OPEN_CHOICES_REF, pack_render.open_choices_reference(owner))
    for path in sorted((root / pack_render.PACKS_DIR).glob(f"*/references/{pack_render.OPEN_CHOICES_REF}")):
        if pack_render.open_choices_placement(path.parent.parent.name) != "reference":
            stale.append(path)
            if not check:
                path.unlink()
    return stale
