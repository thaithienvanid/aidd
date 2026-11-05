"""Generate the Markdown blocks that restate schemas and the CLI, so docs and their sources never drift: one block by
name (`render`), and every block, pack, and agent file in the repository (`gen_docs`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from aidd import config, evals, knowledge, risk, views
from aidd.docsgen import ask_holds, cli_reference, counts, diagrams, pack_render, product, schema_tables, team_reference
from aidd.docsgen import blocks as docsgen_blocks
from aidd.kernel import json_schema, resources
from aidd.kernel import text as kernel_text


def inline_list(name: str) -> str:
    """A list inside a sentence: `list:team-commands` names every flow's command, the first one in full;
    `list:ask-rule-harnesses` names the agents `aidd init` writes the ask rules for; `list:harnesses` names every agent
    `aidd init` wires, in alphabetical order; `list:leading-word-harnesses` those among them whose ask rules match only a
    command's leading words; `list:reasoning-roles` the roles on
    the reasoning tier, with their number first; `list:risk-rule-fields` a risk rule's fields from its schema, a `?` after
    each optional one; `list:lane-words` how a person reads each lane; `list:repository-documents` the types `aidd new` writes
    once for the repository, or once for each service or topic, from schemas/item-types.json."""
    if name == "risk-rule-fields":
        rule = resources.load_json("risks.schema.json")["$defs"]["rule"]
        required = set(rule.get("required", []))
        return "`{" + ", ".join(k if k in required else f"{k}?" for k in rule["properties"]) + "}`"
    if name == "ask-rule-harnesses":
        labels = [h.label for h in config.ask_rule_harnesses()]
        return kernel_text.series(labels, "and")
    if name == "leading-word-harnesses":
        return kernel_text.series(ask_holds.leading_word_labels(), "and")
    if name == "harnesses":
        # Every harness `aidd init` wires, in alphabetical order, so README and CHANGELOG name the same set as the code.
        return kernel_text.series(sorted(h.label for h in config.HARNESSES.values()), "and")
    if name == "reasoning-roles":
        data = knowledge.roles()
        names = [f"the {k.replace('-', ' ')}" for k in data["order"] if data["roles"][k].get("tier") == "reasoning"]
        number = ("Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine")[len(names) - 2] if 2 <= len(names) <= 9 else str(len(names))
        return f"{number} roles use the strongest model your harness offers (the `reasoning` tier): " + kernel_text.series(names, "and")
    if name == "repository-documents":  # a type of the repository group or the stand-alone group that starts from a template
        rows = config.item_type_rows()
        return ", ".join(t for g in ("repository", "standalone") for t in config.types_in(g) if "templates" in rows[t] or "files" in rows[t])
    if name == "lane-words":  # how a person reads each lane, from common.schema.json's `lane`
        words = config.lane_words()
        return kernel_text.series([f'`{lane}` reads "{w}"' for lane, w in words.items()], "and")
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
    prefix, _, arg = name.partition(":")
    if prefix in PREFIXED:
        return PREFIXED[prefix](arg)
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
        "retired:names": schema_tables.retired_names_table,
        "status:groups": schema_tables.groups_table,
        "devices:frames": device_frames_table,
        "risks:areas": lambda: risk_areas_table(),
        "risks:areas:short": lambda: risk_areas_table(paths=False),
        "risks:areas:levels": lambda: risk_area_levels_table(),
        "harnesses:ask-rules": ask_holds.ask_rules_table,
        "risks:rules": lambda: risk_rules_table(),
        "risks:actions": lambda: risk_actions_table(),
        "risks:holds": ask_holds.ask_holds_table,
        "roles:capabilities": team_reference.capabilities_table,
        "roles:commands": commands_line,
        "roles:loop": team_reference.loop_tables,
        "roles:stages": team_reference.stages_table,
        "roles:stages:outline": team_reference.stages_outline,
        "roles:lead": team_reference.lead_block,
        "roles:merge-approval": team_reference.merge_approval_block,
        "roles:contract": team_reference.contract_block,
        "roles:by-role": team_reference.role_sections,
        "roles:preloaded": pack_render.preloaded_sections,
        "roles:review-report": team_reference.review_report_table,
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


def commands_line() -> str:
    """`roles:commands`: the team's commands, one per flow in the registry."""
    return (
        "- **Commands:** "
        + ", ".join(f"`/aidd-team:{f['command']}`" for f in knowledge.roles()["loop"]["flows"])
        + "; one per flow in the registry, each running its roles in order and stopping where a person decides. "
        + "`/aidd-team:autopilot` runs those flows one after another, picking each step from `aidd status`, and stops at each ask."
    )


def eval_block(name: str) -> str:
    """`evals:role-coverage`: the role eval cases per role operation. `evals:claim-coverage`: the cases per claim, over the four
    suites. `evals:shape-coverage`: the cases and fixtures per project shape. All read the source repository's evals."""
    root = resources.repo_root()
    if name not in ("role-coverage", "claim-coverage", "shape-coverage") or root is None:
        raise ValueError(f"generated block 'evals:{name}' reads the source repository's evals: run `aidd gen-docs` from a source checkout")
    if name == "claim-coverage":
        file = evals.claims_file(root)
        if problems := evals.case_problems(rows := evals.suite_cases(root), file):
            raise ValueError("an eval case lacks its claim, tier, or proves line: " + "; ".join(problems))
        return evals.claim_coverage_table(rows, file)
    if name == "shape-coverage":
        file = evals.shapes_file(root)
        if problems := evals.shape_problems(rows := evals.case_shapes(root), file) + evals.fixture_problems(root, file):
            raise ValueError("an eval case or a fixture names no project shape: " + "; ".join(problems))
        return evals.shape_coverage_table(rows, file)
    cases = evals.load_scenarios(root / "evals" / "roles")
    if problems := evals.role_case_problems(cases):
        raise ValueError("a role eval case would count toward no operation; give it a `step` its role works in: " + "; ".join(problems))
    return evals.role_coverage_table(cases)


# The blocks named `prefix:argument`, by prefix; the others are named in full, in `render`.
PREFIXED: dict[str, Callable[[str], str]] = {
    "fields": schema_tables.fields_table,
    "findings": schema_tables.findings_table,
    "count": lambda x: str(counts.count(x)),
    "list": inline_list,
    "vocab": schema_tables.vocab_table,
    "transitions": schema_tables.transitions_table,
    "role": team_reference.role_block,
    "areas": lambda role: knowledge.areas_phrase(knowledge.roles()["roles"][role]["starts_on_areas"]),
    "practice": pack_render.practice_standards,
    "evals": eval_block,
    "product": product.text,
}


def _area_edit_level(rs, name: str) -> str:
    """The level of `code.edit` inside the area `name`: its own rule's, else the default."""
    level = risk.edit_level(rs, [], role=None)[0]
    for r in rs.rules:
        if r.action == "code.edit" and r.area == name:
            level = r.level
    return level


def device_frames_table() -> str:
    """`devices:frames`: the design system's device frames (design/tokens.json), each with its size, the devices that have it,
    and the source and day it was read."""
    rows = []
    for key, frame in json.loads(views.devices_json())["frames"].items():
        source = f"[{urlsplit(frame['citation']['url']).netloc}]({frame['citation']['url']}), {frame['checked']}"
        rows.append([f"`{key}`", f"{frame['name']}, {frame['platform']}", f"{frame['width']} by {frame['height']}", ", ".join(frame["devices"]), source])
    return docsgen_blocks.markdown_table("Frame | Name and platform | CSS px | Devices with this size | Source, read on", rows)


def risk_areas_table(paths: bool = True) -> str:
    """The built-in risk areas (schemas/risks.json): each with the route it raises a change to, its dimensions, and its edit
    level. With `paths`, also a few of its paths; `risks:areas:short` leaves them out, for the route reference."""
    rs = risk.rule_set(None)
    rows = []
    for name, area in rs.areas.items():
        sample = ", ".join(f"`{p}`" for p in area["paths"][:3]) + (f", and {len(area['paths']) - 3} more" if len(area["paths"]) > 3 else "")
        row = [
            f"`{name}`",
            area.get("description", ""),
            area.get("route", "minor"),
            ", ".join(area.get("dimensions", [])) or "none",
            _area_edit_level(rs, name),
        ]
        rows.append([*row, sample] if paths else row)
    head = "Area | What it holds | Raises the route to | Dimensions | Editing it"
    return docsgen_blocks.markdown_table(head + (" | Paths, such as" if paths else ""), rows)


def risk_area_levels_table() -> str:
    """`risks:areas:levels`: the built-in areas grouped by edit level and route, in the order schemas/risks.json lists them."""
    rs = risk.rule_set(None)
    groups: dict[tuple[str, str], list[str]] = {}
    for name, area in rs.areas.items():
        groups.setdefault((_area_edit_level(rs, name), area.get("route", "minor")), []).append(f"`{name}`")
    return docsgen_blocks.markdown_table("Area | Edit level | Route", [[", ".join(names), level, route] for (level, route), names in groups.items()])


def risk_rules_table() -> str:
    """The built-in risk rules (schemas/risks.json), in the order the file lists them."""
    shared = {None: "any", True: "shared", False: "your own"}
    rows = [
        [f"`{r.action}`", r.area or "any", r.branch or "any", shared[r.environment_shared], f"**{r.level}**"]
        for r in risk.rule_set(None).rules
        if r.source == "built-in"
    ]
    return docsgen_blocks.markdown_table("Action | Area | Branch | Environment | Level", rows)


def risk_actions_table() -> str:
    """The built-in actions (schemas/risks.json): what each is, and a command it matches."""
    rows = []
    for name, spec in risk.builtin()["actions"].items():
        example = f"`{spec['commands'][0]}`" if spec.get("commands") else (spec.get("examples") or [""])[0]
        rows.append([f"`{name}`", spec.get("description", ""), example])
    return docsgen_blocks.markdown_table("Action | What it is | Such as", rows)


def targets(root: Path) -> list[Path]:
    found = [p for p in [root / "llms.txt"] if p.is_file() and not p.is_symlink()]  # the index an agent reads first
    for pattern in ("*.md", "docs/**/*.md", ".agents/skills/**/*.md", "plugins/**/*.md", "evals/**/*.md"):
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


DESIGN_DOC = Path("docs/design/DESIGN.md")
SYSTEM_CSS = Path("plugins/aidd-team/tools/prototype/system.css")
DEVICES_JSON = Path("plugins/aidd-team/tools/prototype/devices.json")


def _fill_domain_pack_enum(root: Path, update: Callable[[Path, str], None]) -> None:
    """`agents.domain_packs` takes the packs of schemas/packs.json and nothing else, so `aidd validate` refuses a typo."""
    schema_path, packs_path = root / "schemas" / "config.schema.json", root / "schemas" / "packs.json"
    if schema_path.is_file() and packs_path.is_file():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        slugs = sorted(p["slug"] for p in json.loads(packs_path.read_text(encoding="utf-8")))
        schema["properties"]["agents"]["properties"]["domain_packs"]["items"]["enum"] = slugs
        update(schema_path, json.dumps(schema, indent=2, ensure_ascii=False) + "\n")


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

    # First, because the config reference and the editor's schema below read the config schema it fills.
    _fill_domain_pack_enum(root, update)
    product.sync(root, update)  # the description and keywords, which no Markdown block can hold
    for path in targets(root):
        text = path.read_text(encoding="utf-8")
        is_agent = path.parent == root / pack_render.AGENTS_DIR
        if "<!-- aidd:gen " in text or is_agent:
            new = regenerate(text, cli)
            update(path, pack_render.agent_with_tools(new, path.stem) if is_agent else new)
    # The config schema as one file an editor reads (the modeline `aidd init` writes names it).
    if (root / "schemas" / "config.schema.json").is_file():
        update(root / config.EDITOR_SCHEMA, json.dumps(json_schema.bundled("config.schema.json"), indent=2, ensure_ascii=False) + "\n")
    # The design system of aidd's own pages: its CSS beside the prototype tool, and DESIGN.md's token front matter.
    if (root / DESIGN_DOC).is_file():
        update(root / DESIGN_DOC, views.with_design_front_matter((root / DESIGN_DOC).read_text(encoding="utf-8")))
    if (root / SYSTEM_CSS).parent.is_dir():
        update(root / SYSTEM_CSS, views.system_css())
        update(root / DEVICES_JSON, views.devices_json())
    for d in knowledge.roles()["domains"]:
        update(pack_render.pack_path(root, d), pack_render.render_pack(d))
    # A preloaded skill, or one near its cap, carries its open choices in a generated reference instead.
    owners = {c["owner"] for c in knowledge.open_choices().values()}
    for owner in sorted(owners):
        if pack_render.open_choices_placement(owner) == "reference":
            update(pack_render.skill_folder(root, owner) / "references" / pack_render.OPEN_CHOICES_REF, pack_render.open_choices_reference(owner))
    written = sorted(
        p for skills in (pack_render.PACKS_DIR, pack_render.PRACTICES_DIR) for p in (root / skills).glob(f"*/references/{pack_render.OPEN_CHOICES_REF}")
    )
    for path in written:
        if pack_render.open_choices_placement(path.parent.parent.name) != "reference":
            stale.append(path)
            if not check:
                path.unlink()
    return stale
