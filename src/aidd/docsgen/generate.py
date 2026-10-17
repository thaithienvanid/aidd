"""Generate the Markdown blocks that restate schemas and the CLI, so docs and their sources never drift: one block by
name (`render`), and every block, pack, and agent file in the repository (`gen_docs`).
"""

from __future__ import annotations

import re
from pathlib import Path

from aidd import config, gate, knowledge
from aidd.docsgen import blocks as docsgen_blocks
from aidd.docsgen import cli_reference, counts, diagrams, pack_render, schema_tables, team_reference
from aidd.kernel import text as kernel_text


def inline_list(name: str) -> str:
    """A list inside a sentence: `list:team-commands` names every flow's command, the first one in full;
    `list:guard-harnesses` names the agents whose own hook runs the guard."""
    if name == "guard-harnesses":
        labels = [h.label for h in config.guarded_harnesses()]
        return ", ".join(labels[:-1]) + f", and {labels[-1]}" if len(labels) > 2 else " and ".join(labels)
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
        "examples:cases": lambda: counts.examples_table(counts._examples_root()),
        "mcp:revisions": lambda: kernel_text.series(list(_needs_cli(name, cli).mcp_supported), "and"),
        "mcp:latest": lambda: _needs_cli(name, cli).mcp_protocol,
        "cli:commands": lambda: cli_reference.cli_table(_needs_cli(name, cli)),
        "cli:when": lambda: cli_reference.when_table(_needs_cli(name, cli)),
        "cli:everyday": lambda: cli_reference.everyday_table(_needs_cli(name, cli)),
        "workitems": team_reference.work_items,
        "cli:env": counts.env_table,
        "profiles": schema_tables.profiles_table,
        "profiles:carry": lambda: docsgen_blocks.markdown_table(
            "Profile | A Merge approval carries across a trivial rebase | On routes",
            (
                [p, schema_tables._cell(g["approval_carry"]), schema_tables._cell(g["approval_carry_routes"] if g["approval_carry"] != "none" else [])]
                for p, g in ((p, config.profiles()["profiles"][p]) for p in config.profiles()["order"])
            ),
        ),
        "status:groups": schema_tables.groups_table,
        "baseline": schema_tables.baseline_table,
        "baseline:summary": schema_tables.baseline_summary,
        "roles:capabilities": team_reference.capabilities_table,
        "roles:commands": lambda: (
            "- **Commands:** "
            + ", ".join(f"`/aidd-team:{f['command']}`" for f in knowledge.roles()["loop"]["flows"])
            + "; one per flow in the registry, each running its roles in order and stopping where a person decides. "
            + "`/aidd-team:autopilot` runs those flows between your decisions, one `aidd autopilot next` action at a time."
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
        "autopilot:steps": team_reference.autopilot_steps_table,
        "roles:handoffs:diagram": diagrams.handoffs_diagram,
        "harnesses": config.harnesses_table,
        "standards:open-choices": lambda: knowledge.catalog_choices(),
        "standards:library": lambda: knowledge.catalog_library(),
        "standards:stacks": lambda: knowledge.catalog_stacks(),
        "harnesses:summary": counts.harnesses_summary,
        "rules:questions": lambda: docsgen_blocks.markdown_table(
            "The gate asks | Its rules", ([q, ", ".join(f"`{n}`" for n in names)] for q, names in gate.QUESTIONS)
        ),
        "rules:method": lambda: docsgen_blocks.markdown_table("Rule | Level on miss | Holds when", ([f"`{r.name}`", r.levels, r.holds] for r in gate.RULES)),
        "rules:skill": lambda: docsgen_blocks.markdown_table("Rule | Holds when | How you satisfy it", ([f"`{r.name}`", r.holds, r.fix] for r in gate.RULES)),
        "rules:codes": lambda: docsgen_blocks.markdown_table(
            "Code | Rule | Fires when",
            ([f"`{code}`", f"`{r.name}`", meaning.replace("|", "\\|")] for r in gate.RULES for code, meaning in sorted(r.codes.items())),
        ),
    }
    if name in blocks:
        return blocks[name]()
    return team_reference.roles_table(name)


def targets(root: Path) -> list[Path]:
    found = []
    for pattern in ("*.md", "docs/**/*.md", ".agents/skills/**/*.md", "plugins/**/*.md", "examples/*.md"):
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
    baseline = root / "schemas" / "baseline.json"
    if baseline.is_file():
        update(baseline, config.baseline_json_text(baseline.read_text(encoding="utf-8")))
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
