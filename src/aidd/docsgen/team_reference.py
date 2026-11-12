"""The team's reference: the roles, domains, extensions, flows, and handoffs from schemas/roles.json, each role's block
in its agent file, the lead's rules, the loop contract, the model tiers, and the work items.
"""

from __future__ import annotations

import re

from aidd import config, knowledge
from aidd.docsgen import blocks, diagrams, pack_render

# How the roles reference names each type of extension (`extensions[].type` in the team registry).
_EXTENSION_TYPES = {"harness": "Harnesses", "tool": "Tools", "mcp": "MCP servers", "plugin": "Plugins", "skill": "Skills"}


def role_reads(role: dict) -> str:
    """The artifacts a role acts on, by their short names: a nested bullet list, one artifact a line, so a long list
    never runs into one long sentence."""
    arts = knowledge.roles()["loop"]["artifacts"]
    return "\n".join(f"  - {arts[a]['name']}" for a in role["reads"])


def standard_note(standard: dict, edition: str = "edition") -> str:
    """A registry entry's edition, with `emerging` when the registry marks it so, or "" when it has neither; `edition`
    names the field to print (`release` is the bare edition, without the publication date and notes)."""
    return "; ".join(x for x in (standard.get(edition), "emerging" if standard.get("maturity") == "emerging" else None) if x)


def standard_text(standard: dict, edition: str = "edition") -> str:
    """`name (edition)` for a registry entry, as `standard_note` gives the edition, or the name alone without one."""
    note = standard_note(standard, edition)
    return f"{standard['name']} ({note})" if note else standard["name"]


def standard_cells(standard: dict) -> tuple[str, str, str]:
    """The name, the bare edition (or a dash), and `checked <date>` for an overview row, never the notes."""
    return standard["name"], standard.get("release") or "—", f"checked {standard['checked']}"


def access_text(extension: dict) -> str:
    """What an extension can touch, in words: `network, runs commands`, or `read-only` when it touches nothing."""
    words = [c.replace("_", " ") for c in extension["access"]]
    if "telemetry" in extension["access"]:
        words[extension["access"].index("telemetry")] = "telemetry (" + ("can be turned off" if extension["telemetry_opt_out"] else "always on") + ")"
    return ", ".join(words) or "read-only"


def role_standards_cells(stds: list[dict], full: bool = True) -> list[tuple[str, str]]:
    """A role's standards as (wording, edition) pairs, each document's edition printed once: a second use of one
    document has an empty edition.

    `full` prints the whole edition note (publication date and notes), as the reference tables do; an agent file
    carries the bare edition, and its note lives once, in docs/TEAM-REFERENCE.md.
    """
    seen: set[str] = set()
    out = []
    for s in stds:
        out.append((s["name"], "" if s["id"] in seen else standard_note(s, "edition" if full else "release")))
        seen.add(s["id"])
    return out


def role_standards_text(stds: list[dict], full: bool = True) -> list[str]:
    """A role's standards as `wording (edition)`, from `role_standards_cells`."""
    return [f"{name} ({note})" if note else name for name, note in role_standards_cells(stds, full)]


def loop_points(loop: dict, steps: list[str], gates: bool = False) -> list[str]:
    """`steps` in loop order, with `Implement` shown as `Implement ⟲ Verify` when both are there, and, with `gates`,
    each human approval placed after the step it follows."""
    out: list[str] = []
    for step in loop["steps"]:
        if step == "Verify" and "Verify" in steps and "Implement" in steps:
            out[-1] += " ⟲ Verify"
        elif step in steps:
            out.append(step)
        if gates and step in diagrams.gates():
            out.append(diagrams.gates()[step][1])
    return out


# The work items in one picture (METHOD.md#43-work-items): the deal, the goal, one change, and where a person's pick
# from an exploration is recorded (schemas/exploration.schema.json names the places), with a caption and the sentences
# that keep a proposal and an exploration apart. The containment arrows follow each schema's `parent`. The tuple is the
# diagram's lines, in drawing order.
WORK_ITEMS = (
    "flowchart TD",
    "  accTitle: The planning work items",
    "  accDescr: An accepted proposal leads to an Intent, and an agreed Intent's slice starts a Spec, which holds Tasks."
    " A person picks an exploration's direction, recorded in the Spec's Design section and in an ADR or DESIGN.md.",
    '  Proposal["Proposal<br/><i>the deal</i>"]',
    '  Intent["Intent<br/><i>the goal,<br/>its phases</i>"]',
    '  Slice["slice<br/><i>a line in a phase</i>"]',
    '  Spec["Spec<br/><i>one change</i>"]',
    '  Task["Task"]',
    '  Exploration["Exploration<br/><i>the design</i>"]',
    '  Pick{{"a person picks"}}',
    '  ADR["ADR or DESIGN.md<br/><i>records why</i>"]',
    '  Proposal -->|"accepted"| Intent -->|"agreed"| Slice -->|"its work starts"| Spec --> Task',
    "  Exploration --> Pick",
    '  Pick -->|"Design section"| Spec',
    "  Pick --> ADR",
)
WORK_ITEMS_CAPTION = "Legend: the dark hexagon is where a person picks. Proposal and Intent are optional. A team may start with a Spec. The diagram shows only the planning items; this section lists all the object types."
WORK_ITEMS_TEXT = (
    "A proposal is about the deal: should we take this work, for how much, and by when? "
    "Skip it when nobody outside the team must say yes. "
    "An exploration is about the design: which way to build one part. Skip it when the answer is obvious."
)


def work_items() -> str:
    return (
        diagrams.mermaid([*WORK_ITEMS, diagrams.DEFAULT_CLASS, diagrams.HUMAN_CLASS, "  class Pick human"])
        + "\n\n"
        + WORK_ITEMS_CAPTION
        + "\n\n"
        + WORK_ITEMS_TEXT
    )


def role_block(key: str) -> str:
    """One role's facts in its agent file (`role:<key>`): who it is, when it starts and stops, what it may write, and
    the loop-contract rules that bind it (the whole contract is rendered once, in the team skill's roles reference).
    Its standards, practice skills, and extensions are needed for some Tasks only, so they sit in its section of the
    roles reference (`roles:by-role`), and the agent file carries a one-line pointer to it."""
    r = knowledge.roles()["roles"][key]
    contract = "".join(f"\n  {i}. {x}" for i, x in enumerate(knowledge.contract_carried_for(key), 1))
    # The hard rules in short, for every role: a role that does not preload the aidd skill still keeps them, and one that does reads
    # the ones its `in_core_skill` proof names in that skill.
    shared = "".join(f"\n  {i}. {x}" for i, x in enumerate(knowledge.shared_rules_carried_for(key), 1))
    rulebook = (
        "The aidd skill, preloaded, is the rulebook."
        if pack_render.preloads_core(key)
        else "The aidd skill (`aidd:aidd`; load it with `Skill` for a rule not here) is the rulebook."
    )
    tools = "Prefer the `aidd` MCP tools."
    if r.get("mcp_tools"):  # a role with only its own tools cannot load a skill or call another tool
        tools = " and ".join(f"`{t}`" for t in r["mcp_tools"])
        rulebook, tools = "The hard rules and the contract below are the aidd skill's rules that bind you.", f"Your only tools are {tools}."
    checked = "".join(f"\n  {i}. {rule}\n     *You apply it so:* {how}" for i, (rule, how) in enumerate(knowledge.reviewed_rules_for(key), 1))
    checked = f"- **Rules the authors keep, which you check:**{checked}\n" if checked else ""
    return (
        f"You are the **{key}** of an aidd delivery team. {rulebook} {tools}\n\n"
        f"- **Hard rules (in short):**{shared}\n"
        f"- **Loop steps:** {knowledge.role_loop(r)}\n- **Starts when:** {r['starts_when']}\n- **Done when:** {r['done_when']}\n"
        f"- **Does:** {r['does']}\n"
        f"- **Reads:**\n{role_reads(r)}\n"
        f"- **May write:** {knowledge.role_area(r)}\n- **Hands off:** {r['hands_off']}\n"
        f"- **Model tier:** `{r['tier']}`\n"
        + "".join(
            f"- **Covers for:** the `{other}` where it is not installed: you also do its work, as its section of {knowledge.ROLE_REFERENCE} says\n"
            for other in knowledge.roles()["order"]
            if knowledge.roles()["roles"][other].get("fallback") == key
        )
        + f"- **Loop contract:**{contract}"
        + ("\n" + checked.rstrip("\n") if checked else "")
        + (
            "" if r.get("mcp_tools") else f"\n- **Standards and skills:** {knowledge.ROLE_REFERENCE}, section `{key}`."
        )  # a role that cannot load a skill is not sent to one
    )


def role_sections() -> str:
    """Each role's standards, practice skills, and extensions (`roles:by-role`), one section per role: an agent file
    points here instead of carrying lists it needs for some Tasks only. The standards are a table, one row each with
    its edition, because a wording and its edition note together run far past one readable sentence."""
    data = knowledge.roles()
    out = []
    for key in data["order"]:
        r = data["roles"][key]
        standards = blocks.markdown_table("Standards applied | Edition", ([name, note or "—"] for name, note in role_standards_cells(r.get("standards", []))))
        # Names only: the harness lists every skill with its description.
        practices = ", ".join(f"`aidd-team:{x}`" for x in r["practices"]) or "none listed; this role works from its standards and the domain packs"
        lines = [
            f"### {key}",
            "",
            standards,
            "",
            f"- **Practice skills (`Skill`: at most two from the Task, plus the ones for its files):** {practices}.",
        ]
        listed = [x for x in dict.fromkeys([*r["practices"], *pack_render.preloaded_by(r)]) if pack_render.open_choices_placement(x) == "reference"]
        if listed:
            where = ", ".join(f"`{knowledge.skill_ref(x)}` (its `references/open-choices.md`)" for x in listed)
            lines.append(f"- **Open choices:** {where}. Use aidd's default until a `standards` entry fills one.")
        if r.get("extensions"):
            # One short sentence per type, so a long list stays readable and within the plain-language rule.
            by_type: dict[str, list[str]] = {}
            for x in r["extensions"]:
                by_type.setdefault(x["type"], []).append(x["name"])
            names = " ".join(f"{_EXTENSION_TYPES[type_name]}: {', '.join(found)}." for type_name, found in by_type.items())
            lines.append(f"- **Extensions:** {names} Use one only when the project already has it connected, verified, and pinned.")
        out.append("\n".join(lines))
    # A pack no role lists, whose open choices sit in a reference: the pack's own References section links it too.
    listed_by_roles = {x for r in data["roles"].values() for x in [*r["practices"], *pack_render.preloaded_by(r)]}
    packs_ = [d["slug"] for d in data["domains"] if d["slug"] not in listed_by_roles and pack_render.open_choices_placement(d["slug"]) == "reference"]
    if packs_:
        where = ", ".join(f"`{knowledge.skill_ref(x)}` (its `references/open-choices.md`)" for x in packs_)
        out.append(f"### Domain packs\n\n- **Open choices:** {where}. Use aidd's default until a `standards` entry fills one.")
    return "\n\n".join(out)


def lead_block() -> str:
    """The lead's rules (`roles:lead`), in every command."""
    rules = "\n".join(f"{i}. {x}" for i, x in enumerate(knowledge.roles()["loop"]["lead"], 1))
    return f"**You are the lead.** You run this command and the roles do its work:\n\n{rules}"


def merge_approval_block() -> str:
    """The cases of Merge approval (`roles:merge-approval`), one bullet each, in the loop, autopilot, and the fix flow."""
    return "\n".join(f"- {x}" for x in knowledge.roles()["loop"]["merge_approval"])


def contract_block() -> str:
    """The whole loop contract once (`roles:contract`), each rule with the roles it binds; an agent file carries only its own."""
    data = knowledge.roles()
    loop, order = data["loop"], data["order"]
    lines = []
    for i, (x, scope) in enumerate(zip(loop["contract"], loop["contract_applies_to"], strict=True), 1):
        who = "every role" if scope is None else _roles_text([k for k in order if x in knowledge.contract_for(k)], order, code=True)
        lines.append(f"{i}. {x} *(binds: {who})*")
    return "\n".join(lines)


def tiers_table() -> str:
    """Each model tier (`roles:tiers`): what it is for and its model per harness. Which role sits in which tier is the
    reference's `roles:models` table."""
    harness_names = [config.HARNESSES[h].label if h in config.HARNESSES else h for h in knowledge.MODELS_BY_HARNESS]
    rows = [[f"`{tier}`", meaning, *(f"`{m[tier]}`" for m in knowledge.MODELS_BY_HARNESS.values())] for tier, meaning in knowledge.TIER_MEANING.items()]
    return blocks.markdown_table("Tier | For | " + " | ".join(harness_names), rows)


def review_report_table() -> str:
    """The fields of a review report's finding (`roles:review-report`): each closed value, with what it says."""
    report = knowledge.roles()["loop"]["review_report"]
    rows = [[f"`{field}`", f"`{value}`", meaning] for field, values in report["fields"].items() for value, meaning in values.items()]
    return blocks.markdown_table("Field | Value | It says", rows)


def documents_table() -> str:
    """Each document type `aidd new` makes (`roles:documents`): the one role that writes it, frozen or living, whether it is
    the product's or one change's, the product-level type it feeds, the roles it is handed to, the command that opens it,
    and its home."""
    docs = knowledge.roles()["loop"]["documents"]
    rows = (
        [
            f"`{type_name}`",
            f"`{d['written_by']}`",
            d["lifecycle"] + (", changed in a Task" if d.get("changed_only_in_a_task") else ""),
            d["belongs_to"],
            f"`{d['feeds']}`" if d.get("feeds") else "",
            ", ".join(f"`{r}`" for r in d.get("read_by", [])),
            f"`{d['opened_by']}`" if d.get("opened_by") else "",
            d["home"],
        ]
        for type_name, d in docs.items()
    )
    return blocks.markdown_table("Type | Written by | Frozen or living | Product or change | Feeds | Read by | Opened by | Home", rows)


def capabilities_table() -> str:
    caps = knowledge.roles()["loop"]["capabilities"]
    counts = {k: sum(1 for c in caps["processes"] if c["coverage"] == k) for k in ("agents", "agents_person_decides", "humans")}
    summary = (
        f"All {len(caps['processes'])} processes of {caps['standard']}:\n\n- {counts['agents']} run by agents\n"
        f"- {counts['agents_person_decides']} run by agents with a person deciding\n- {counts['humans']} kept by humans"
    )
    rows = ([c["group"], c["process"], ", ".join(f"`{b}`" for b in c["by"]) or "humans", f"`{c['coverage']}`", c["how"]] for c in caps["processes"])
    return summary + "\n\n" + blocks.markdown_table("Group | Process | Covered by | Who acts | How", rows)


def _roles_text(names: list[str], order: list[str], code: bool = False) -> str:
    """Role keys (or steps) as a list, or, when they are most of the roles, as `every role but ...`: a long list of role
    keys reads like a hand-kept roster that drifts, and says less than the few it leaves out."""
    fmt = (lambda k: f"`{k}`") if code else (lambda k: k)  # noqa: E731
    if set(names) <= set(order) and len(names) > len(order) / 2:
        return "every role but " + ", ".join(fmt(k) for k in order if k not in names)
    return ", ".join(fmt(k) for k in names)


def loop_tables() -> str:
    data = knowledge.roles()
    loop, order, roles = data["loop"], data["order"], data["roles"]
    marks = ([step, *("●" if step in roles[k]["steps"] else "" for k in order)] for step in loop["steps"])
    steps = blocks.markdown_table("Step | " + " | ".join(f"`{k}`" for k in order), marks)
    when = blocks.markdown_table("Role | Starts when | Done when", ([f"`{k}`", roles[k]["starts_when"], roles[k]["done_when"]] for k in order))
    contract = [
        f"{i}. {x}" + ("" if s is None else f" *(applies to: {_roles_text(s, order)})*")
        for i, (x, s) in enumerate(zip(loop["contract"], loop["contract_applies_to"], strict=True), 1)
    ]
    return "\n\n".join([steps, when, "Every role keeps the loop contract; a rule that names roles or steps binds only those:", "\n".join(contract)])


def stages_table() -> str:
    """`roles:stages`: each stage, in order, with the loop steps it groups and the gates in it, each before its step,
    from `loop.stages` and `loop.gates` in schemas/roles.json."""
    loop = knowledge.roles()["loop"]
    rows = (
        [
            stage["name"],
            ", ".join(stage["steps"]),
            "; ".join(f"{g['name']} (`{'` or `'.join(g['actions'])}`), before {g['before']}" for g in loop["gates"] if g["stage"] == stage["name"]) or "—",
        ]
        for stage in loop["stages"]
    )
    return blocks.markdown_table("Stage | Its steps | Gate", rows)


def route_steps_table() -> str:
    """`roles:routes`: the steps each route runs and the gates its steps name, from `loop.routes` and `loop.gates` in
    schemas/roles.json. Routes with the same steps share a row, and a route reads as the word `x-words` gives it."""
    loop = knowledge.roles()["loop"]
    words = config.route_words()
    by_steps: dict[str, list[str]] = {}
    for route, steps in loop["routes"].items():
        by_steps.setdefault(steps, []).append(route)
    rows = (
        [
            f"**{words[routes[0]]}**",
            ", ".join(routes),
            steps,
            ", ".join(f"`{'` or `'.join(g['actions'])}`" for g in loop["gates"] if g["name"] in steps) or "—",
        ]
        for steps, routes in by_steps.items()
    )
    return blocks.markdown_table("As a person reads it | Routes | Steps | Asks", rows)


def stages_outline() -> str:
    """`roles:stages:outline`: the loop as a text block, one line for each stage: its steps, with each gate where a person
    decides, from `loop.stages` and `loop.gates` in schemas/roles.json. A gate stands before the step it names, and at the
    end of its stage when that step opens the next stage."""
    loop = knowledge.roles()["loop"]
    width = max(len(stage["name"]) for stage in loop["stages"]) + 2
    lines = []
    for stage in loop["stages"]:
        steps = list(stage["steps"])
        gates = [g for g in loop["gates"] if g["stage"] == stage["name"]]
        if len(gates) > 1:
            raise ValueError(f"stage {stage['name']} has {len(gates)} gates; the outline draws one gate a stage")
        gate = gates[0] if gates else None
        if gate is None:
            lines.append(f"{stage['name']:<{width}}{', '.join(steps)}")
            continue
        cut = steps.index(gate["before"]) if gate["before"] in steps else len(steps)
        mark = f"[gate: {gate['name']}, {' or '.join(gate['actions'])}]"
        parts = [", ".join(steps[:cut]), mark, ", ".join(steps[cut:])]
        lines.append(f"{stage['name']:<{width}}" + " → ".join(p for p in parts if p))
    return "```text\n" + "\n".join(lines) + "\n```"


def loops_text() -> str:
    loop = knowledge.roles()["loop"]
    lo = loop["loops"]
    outer, inner = ", ".join(loop_points(loop, lo["outer_steps"], gates=True)), ", ".join(loop_points(loop, lo["inner_steps"]))
    who = [
        ["Outer", "a human: by approval at Spec approval and Merge approval, by recorded agreement for Plan, Merge, Roll out, and Learn", outer],
        ["Inner", "the agent: it drafts the contract in Specify, then works inside it once Spec approval freezes it", inner],
    ]
    return "\n\n".join(
        [
            f"*Loop contract version {loop['version']}: a change that adds, removes, or reorders a step, an approval, or a route bumps its major number.*",
            f"**The way in.** {loop['entry']}",
            f"**Outer loop — human strategy and governance.** {lo['outer']}",
            f"**Inner loop — autonomous agentic execution.** {lo['inner']}",
            f"**What crosses between them.** {lo['boundary']}",
            blocks.markdown_table("Loop | Who decides | Steps", who),
            "Control passes at the two approvals on machine-checkable evidence, and at Plan, Merge, Roll out, and Learn on a recorded human decision:",
            "\n".join(f"- {g}" for g in lo["approvals"]),
            "**Human feedback.** A person sends work back on these paths, drawn dashed in the loop diagram; each is a normal part of the loop, not a failure:",
            "\n".join(f"- **{f['from']} → {f['to']}** ({f['when']}): {f['note']}" for f in lo["feedback"]),
        ]
    )


def decision_rights_text() -> str:
    """`roles:decisions`: who decides what, the person's decisions first, then the team's (`loop.decision_rights`)."""
    rights = knowledge.roles()["loop"]["decision_rights"]
    person = [[r["decision"], r["decided_by"], r["basis"], r["undo"]] for r in rights if r["loop"] == "outer"]
    team = [[r["decision"], r["decided_by"], r["basis"], r["undo"], r["escalates_when"]] for r in rights if r["loop"] == "inner"]
    return "\n\n".join(
        [
            "**The person decides** (the outer loop):",
            blocks.markdown_table("Decision | Who decides | On what | How it is taken back", person),
            "**The team decides** (the inner loop), on evidence alone: never an approval, and never on another agent's word:",
            blocks.markdown_table("Decision | Who decides | On what | How it is taken back | Goes to a person when", team),
        ]
    )


def roles_table(name: str) -> str:
    """The `roles:*` reference tables, one row per role, domain, extension, flow, or handoff; `roles:flows:when` says
    when a person picks each command, and `roles:flows:starts` which agent step code starts which."""
    data = knowledge.roles()
    order, roles, loop = data["order"], data["roles"], data["loop"]
    if name == "roles":
        return blocks.markdown_table(
            "Role | Loop steps | Industry name | May write | Hands off",
            ([f"`{k}`", knowledge.role_loop(roles[k]), roles[k]["industry"], knowledge.role_area(roles[k]), roles[k]["hands_off"]] for k in order),
        )
    if name == "roles:summary":  # TEAM.md's table: each role's first sentence of `does`, and its model tier
        first = (re.split(r"(?<=[.;])\s+(?=[A-Z`(])", roles[k]["does"], maxsplit=1)[0].rstrip(";.") + "." for k in order)
        return blocks.markdown_table("Role | What it does | Tier", ([f"`{k}`", s, f"`{roles[k]['tier']}`"] for k, s in zip(order, first, strict=True)))
    if name == "roles:models":
        models = knowledge.MODELS_BY_HARNESS
        tiers = {k: roles[k]["tier"] for k in order}
        rows = [[f"`{k}`", f"`{t}`", *(f"`{m.get(t, '—')}`" for m in models.values()), roles[k]["tier_reason"]] for k, t in tiers.items()]
        return blocks.markdown_table("Role | Tier | " + " | ".join(models) + " | Why", rows)
    if name == "roles:practices":
        rows = []
        for x in knowledge.practice_names():
            front = knowledge.practice_front(x)
            who = ", ".join(f"`{k}`" for k in order if x in roles[k]["practices"])
            rows.append([f"`aidd-team:{x}`", front["description"].removeprefix("Practice skill: "), who, front["checked"]])
        return blocks.markdown_table("Practice skill | Does | Roles that load it | Checked", rows)
    if name == "roles:standards":
        return blocks.markdown_table("Role | Standards applied", ([f"`{k}`", "; ".join(role_standards_text(roles[k].get("standards", [])))] for k in order))
    if name == "roles:domains":
        # An overview, one row per standard: the name, the bare edition, and the date. The notes, caveats, and sources
        # live in each pack. A domain's own cells fill only its first row.
        return blocks.markdown_table(
            "Domain | Pack | When the change touches | Standard | Edition | Checked",
            (
                [*((x["name"], f"`{knowledge.skill_ref(x['slug'])}`", x["signal"]) if i == 0 else ("", "", "")), *standard_cells(s)]
                for x in data["domains"]
                for i, s in enumerate(x["standards"])
            ),
        )
    if name == "roles:extensions":
        rows = []
        for k in order:
            for x in roles[k].get("extensions", []):
                type_name = x["type"] + (", emerging" if x.get("maturity") == "emerging" else "")
                source = f"<{x['source']}>" + (f" (listed in <{x['listed_in']}>)" if x.get("listed_in") else "")
                license = x.get("license", "—") + (f" ({x['license_note']})" if x.get("license_note") else "")
                rows.append([f"`{k}`", x["name"], type_name, x["publisher"], access_text(x), x["adds"], source, license, x.get("pin", "—")])
        return blocks.markdown_table("Role | Extension | Type | Publisher | Access | Adds | Source | License | Pin", rows)
    if name == "roles:flows":
        rows = []
        for f in loop["flows"]:
            for name, x in [(f["command"], f), *((f"{f['command']} {m['name']}", m) for m in f.get("modes", []))]:
                runs = " then ".join(", ".join(f"`{r}`" for r in g) for g in x["runs"])
                rows.append([f"`/aidd-team:{name}`", ", ".join(f["steps"]), ", ".join(f["routes"]), runs, x["stops_when"]])
        return blocks.markdown_table("Command | Loop steps | Routes | Runs, in order (a group runs in parallel) | Stops when", rows)
    if name == "roles:flows:when":
        rows = [
            [f"`/aidd-team:{name}`", x["when"], x["stops_when"]]
            for f in loop["flows"]
            for name, x in [(f["command"], f), *((f"{f['command']} {m['name']}", m) for m in f.get("modes", []))]
        ]
        if "autopilot" in loop:
            a = loop["autopilot"]
            rows.append([f"`/aidd-team:{a['command']}`", a["when"], a["stops_when"]])
        return blocks.markdown_table("Command | When | Stops when", rows)
    if name == "roles:flows:starts":
        from aidd import workitems

        command = {code: f["command"] for f in loop["flows"] for code in f["starts_on"]}
        return blocks.markdown_table("Step code | Run", ([f"`{code}`", f"`/aidd-team:{command[code]}`"] for code in workitems.STEP_CODES if code in command))
    if name == "roles:handoffs":
        arts = loop["artifacts"]
        party = lambda x: f"`{x}`" if x in roles else x  # noqa: E731
        rows = []
        for h in loop["handoffs"]:
            where = "; ".join(f"{arts[a]['name']}: {arts[a]['where']}" for a in h["artifact"])
            rows.append([", ".join(map(party, h["from"])), ", ".join(map(party, h["to"])), h["through"], where, h["note"]])
        return blocks.markdown_table("From | To | Through | Artifact | The note adds", rows)
    raise KeyError(f"unknown generated block {name!r}")


def team_commands() -> list[str]:
    """Every aidd-team command: one per flow, then autopilot, which runs the flows one after another."""
    loop = knowledge.roles()["loop"]
    return [f["command"] for f in loop["flows"]] + ([loop["autopilot"]["command"]] if "autopilot" in loop else [])


def step_codes_table() -> str:
    """Every step code `aidd status` gives: who takes it, and what moves it on."""
    from aidd import workitems
    from aidd.docsgen import blocks
    from aidd.kernel import text as kernel_text

    rows = ([f"`{code}`", who, kernel_text.md_cell(workitems.STEP_MEANINGS[code])] for code, who in workitems.STEP_CODES.items())
    return blocks.markdown_table("Code | Who takes it | What it means", rows)
