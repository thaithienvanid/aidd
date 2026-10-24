"""The team's reference: the roles, domains, extensions, flows, and handoffs from schemas/roles.json, each role's block
in its agent file, the lead's rules, the loop contract, the model tiers, and the work items.
"""

from __future__ import annotations

from aidd import config, knowledge
from aidd.docsgen import blocks, diagrams, pack_render


def role_reads(r: dict) -> str:
    """The artifacts a role acts on, by their short names: a nested bullet list, one artifact a line, so a long list
    never runs into one long sentence."""
    arts = knowledge.roles()["loop"]["artifacts"]
    return "\n".join(f"  - {arts[a]['name']}" for a in r["reads"])


def standard_note(s: dict, edition: str = "edition") -> str:
    """A registry entry's edition, with `emerging` when the registry marks it so, or "" when it has neither; `edition`
    names the field to print (`release` is the bare edition, without the publication date and notes)."""
    return "; ".join(x for x in (s.get(edition), "emerging" if s.get("maturity") == "emerging" else None) if x)


def standard_text(s: dict, edition: str = "edition") -> str:
    """`name (edition)` for a registry entry, as `standard_note` gives the edition, or the name alone without one."""
    note = standard_note(s, edition)
    return f"{s['name']} ({note})" if note else s["name"]


def standard_cells(s: dict) -> tuple[str, str, str]:
    """The name, the bare edition (or a dash), and `checked <date>` (or `reviewed <date>`) for an overview row, never
    the notes."""
    date = f"checked {s['checked']}" if s.get("checked") else f"reviewed {s['reviewed']}"
    return s["name"], s.get("release") or "—", date


def capabilities_text(x: dict) -> str:
    """What an extension can touch, in words: `network, runs commands`, or `read-only` when it touches nothing."""
    words = [c.replace("_", " ") for c in x["capabilities"]]
    if "telemetry" in x["capabilities"]:
        words[x["capabilities"].index("telemetry")] = "telemetry (" + ("can be turned off" if x["telemetry_opt_out"] else "always on") + ")"
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
        if gates and step in diagrams.GATES:
            out.append(diagrams.GATES[step][1])
    return out


# The work items in one picture (METHOD §4): the deal, the goal, one change, and where a person's pick
# from an exploration is recorded (schemas/exploration.schema.json names the places), with a caption and the sentences
# that keep a proposal and an exploration apart. The containment arrows follow each schema's `parent`.
WORK_ITEMS = (
    "flowchart LR",
    '  Proposal["Proposal<br/><i>the deal</i>"]',
    '  Initiative["Initiative<br/><i>the goal</i>"]',
    '  Epic["Epic"]',
    '  Spec["Spec<br/><i>one change</i>"]',
    '  Task["Task"]',
    '  Exploration["Exploration<br/><i>the design</i>"]',
    '  Pick{{"a person picks"}}',
    '  ADR["ADR or DESIGN.md<br/><i>records why</i>"]',
    '  Proposal -->|"accepted"| Initiative --> Epic --> Spec --> Task',
    "  Exploration --> Pick",
    '  Pick -->|"Design section"| Spec',
    "  Pick --> ADR",
)
WORK_ITEMS_CAPTION = (
    "Proposal, Initiative, and Epic are optional. A team may start with a Spec (§4.7). "
    "The diagram shows only the planning items; this section lists all the object kinds."
)
WORK_ITEMS_TEXT = (
    "A proposal is about the deal: should we take this work, for how much, and by when? "
    "Skip it when nobody outside the team must say yes. "
    "An exploration is about the design: which way to build one part. Skip it when the answer is obvious."
)


def work_items() -> str:
    return diagrams._mermaid([*WORK_ITEMS, diagrams.HUMAN_CLASS, "  class Pick human"]) + "\n\n" + WORK_ITEMS_CAPTION + "\n\n" + WORK_ITEMS_TEXT


def role_block(key: str) -> str:
    """One role's facts in its agent file (`role:<key>`): who it is, when it starts and stops, what it may write, and
    the loop-contract rules that bind it (the whole contract is rendered once, in the team skill's roles reference).
    Its standards, practice skills, and extensions are needed for some Tasks only, so they sit in its section of the
    roles reference (`roles:by-role`), and the agent file carries a one-line pointer to it."""
    r = knowledge.roles()["roles"][key]
    contract = "".join(f"\n  {i}. {x}" for i, x in enumerate(knowledge.contract_for(key), 1))
    # The hard rules in brief, for every role: a role that does not preload the aidd skill still keeps them.
    shared = "".join(f"\n  {i}. {x}" for i, x in enumerate(knowledge.shared_rules_for(key), 1))
    rulebook = (
        "The aidd skill, preloaded, is the rulebook."
        if pack_render.preloads_core(key)
        else "The aidd skill (`aidd:aidd`; load it with `Skill` for a rule not here) is the rulebook."
    )
    return (
        f"You are the **{key}** of an AIDD delivery team. {rulebook} Prefer the `aidd` MCP tools.\n\n"
        f"- **Hard rules (in brief):**{shared}\n"
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
        + f"- **Loop contract:**{contract}\n"
        f"- **Standards and skills:** {knowledge.ROLE_REFERENCE}, section `{key}`."
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
            f"- **Practice skills (`Skill`, two per Task at most):** {practices}.",
        ]
        listed = [x for x in dict.fromkeys([*r["practices"], *r.get("preload", [])]) if pack_render.open_choices_placement(x) == "reference"]
        if listed:
            where = ", ".join(f"`aidd-team:{x}` (its `references/open-choices.md`)" for x in listed)
            lines.append(f"- **Open choices:** {where}. Use aidd's default until a `standards` entry fills one.")
        if r.get("extends"):
            names = ", ".join(x["name"] for x in r["extends"])
            lines.append(f"- **Extensions:** {names}. Use one only when the project already has it connected, verified, and pinned.")
        out.append("\n".join(lines))
    # A pack no role lists, whose open choices sit in a reference: the pack's own References section links it too.
    listed_by_roles = {x for r in data["roles"].values() for x in [*r["practices"], *r.get("preload", [])]}
    packs_ = [d["slug"] for d in data["domains"] if d["slug"] not in listed_by_roles and pack_render.open_choices_placement(d["slug"]) == "reference"]
    if packs_:
        where = ", ".join(f"`aidd-team:{x}` (its `references/open-choices.md`)" for x in packs_)
        out.append(f"### Domain packs\n\n- **Open choices:** {where}. Use aidd's default until a `standards` entry fills one.")
    return "\n\n".join(out)


def lead_block() -> str:
    """The lead's rules (`roles:lead`), in every command: MODELS becomes each tier's model on the plugin's harness."""
    models = knowledge.MODELS_BY_HARNESS[knowledge.PLUGIN_HARNESS]
    named = ", ".join(f"`{m}` for {t}" for t, m in models.items())
    rules = "\n".join(f"{i}. {x.replace('MODELS', named)}" for i, x in enumerate(knowledge.roles()["loop"]["lead"], 1))
    return f"**You are the lead.** You run this command and the roles do its work:\n\n{rules}"


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


def documents_table() -> str:
    """Each document kind `aidd new` makes (`roles:documents`): the one role that writes it, frozen or living, and its home."""
    docs = knowledge.roles()["loop"]["documents"]
    rows = ([f"`{kind}`", f"`{d['owner']}`", d["lifecycle"], d["home"]] for kind, d in docs.items())
    return blocks.markdown_table("Kind | Owner | Frozen or living | Home", rows)


def capabilities_table() -> str:
    caps = knowledge.roles()["loop"]["capabilities"]
    counts = {k: sum(1 for c in caps["processes"] if c["coverage"] == k) for k in ("agents", "agents, a person decides", "humans")}
    summary = (
        f"All {len(caps['processes'])} processes of {caps['standard']}:\n\n- {counts['agents']} run by agents under the gate\n"
        f"- {counts['agents, a person decides']} run by agents with a person deciding\n- {counts['humans']} kept by humans"
    )
    rows = ([c["group"], c["process"], ", ".join(f"`{b}`" for b in c["by"]) or "humans", c["coverage"], c["how"]] for c in caps["processes"])
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


def loops_text() -> str:
    loop = knowledge.roles()["loop"]
    lo = loop["loops"]
    outer, inner = ", ".join(loop_points(loop, lo["outer_steps"], gates=True)), ", ".join(loop_points(loop, lo["inner_steps"]))
    who = [
        ["Outer", "a human: by approval at Spec approval and Merge approval, by recorded agreement for Plan, Publish, Roll out, and Learn", outer],
        ["Inner", "the agent: it drafts the contract in Specify, then works inside it once Spec approval freezes it", inner],
    ]
    return "\n\n".join(
        [
            f"*Loop contract version {loop['version']}: a change that adds, removes, or reorders a step, an approval, or a lane bumps its major number.*",
            f"**The way in.** {loop['entry']}",
            f"**Outer loop — human strategy and governance.** {lo['outer']}",
            f"**Inner loop — autonomous agentic execution.** {lo['inner']}",
            f"**What crosses between them.** {lo['boundary']}",
            blocks.markdown_table("Loop | Who decides | Steps", who),
            "Control passes at the two approvals on machine-checkable evidence, and at Plan, Publish, Roll out, and Learn on a recorded human decision:",
            "\n".join(f"- {g}" for g in lo["gates"]),
            "**Human feedback.** A person sends work back on these paths, drawn dashed in the loop diagram; each is a normal part of the loop, not a failure:",
            "\n".join(f"- **{f['from']} → {f['to']}** ({f['when']}): {f['note']}" for f in lo["feedback"]),
        ]
    )


def decision_rights_text() -> str:
    """`roles:decisions`: who decides what, the person's decisions first, then the team's (`loop.decision_rights`)."""
    rights = knowledge.roles()["loop"]["decision_rights"]
    person = [[r["decision"], r["decided_by"], r["evidence"], r["undo"]] for r in rights if r["loop"] == "outer"]
    team = [[r["decision"], r["decided_by"], r["evidence"], r["undo"], r["escalates_when"]] for r in rights if r["loop"] == "inner"]
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
    when a person picks each command."""
    data = knowledge.roles()
    order, roles, loop = data["order"], data["roles"], data["loop"]
    if name == "roles":
        return blocks.markdown_table(
            "Role | Loop steps | Industry name | May write | Hands off",
            ([f"`{k}`", knowledge.role_loop(roles[k]), roles[k]["industry"], knowledge.role_area(roles[k]), roles[k]["hands_off"]] for k in order),
        )
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
                [*((x["name"], f"`aidd-team:{x['slug']}`", x["signal"]) if i == 0 else ("", "", "")), *standard_cells(s)]
                for x in data["domains"]
                for i, s in enumerate(x["standards"])
            ),
        )
    if name == "roles:extends":
        rows = []
        for k in order:
            for x in roles[k].get("extends", []):
                kind = x["kind"] + (", emerging" if x.get("maturity") == "emerging" else "")
                source = f"<{x['source']}>" + (f" (listed in <{x['listed_in']}>)" if x.get("listed_in") else "")
                license = x.get("license", "—") + (f" ({x['license_note']})" if x.get("license_note") else "")
                rows.append([f"`{k}`", x["name"], kind, x["tier"], capabilities_text(x), x["adds"], source, license, x.get("pin", "—")])
        return blocks.markdown_table("Role | Extension | Kind | Tier | Can | Adds | Source | License | Pin", rows)
    if name == "roles:flows":
        rows = []
        for f in loop["flows"]:
            runs = " then ".join(", ".join(f"`{r}`" for r in g) for g in f["runs"])
            rows.append([f"`/aidd-team:{f['command']}`", ", ".join(f["steps"]), ", ".join(f["lanes"]), runs, f["stops_at"]])
        return blocks.markdown_table("Command | Loop steps | Lanes | Runs, in order (a group runs in parallel) | Stops at", rows)
    if name == "roles:flows:when":
        rows = [[f"`/aidd-team:{f['command']}`", f["when"], f["stops_at"]] for f in loop["flows"]]
        if "autopilot" in loop:
            a = loop["autopilot"]
            rows.append([f"`/aidd-team:{a['command']}`", a["when"], a["stops_at"]])
        return blocks.markdown_table("Command | When | Stops at", rows)
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
    """Every aidd-team command: one per flow, then autopilot, which runs the flow `aidd autopilot next` names."""
    loop = knowledge.roles()["loop"]
    return [f["command"] for f in loop["flows"]] + ([loop["autopilot"]["command"]] if "autopilot" in loop else [])


def autopilot_steps_table() -> str:
    """The step-code contract: every code the engine can emit, who takes it, and the flow `aidd autopilot next`
    runs for it, from steps.STEP_CODES, autopilot.AUTOPILOT_CODES, and each flow's `starts_on`."""
    from aidd import autopilot

    rows = ([f"`{code}`", who, step_runs(code)] for code, who in sorted(autopilot.contract().items()))
    return blocks.markdown_table("Step code | Who takes it | The flow `aidd autopilot next` runs", rows)


def step_runs(code: str) -> str:
    """What `aidd autopilot next` runs for a step code: its flow's team command, the aidd command a standing approval
    covers, or none, for a person's step."""
    from aidd import autopilot

    flows, shell = autopilot.flow_map(), autopilot.SHELL_STEPS
    if code in flows:
        return f"`/aidd-team:{flows[code]}`"
    return f"`{shell[code]}` (under the person's standing approval)" if code in shell else "none: a person's step"
