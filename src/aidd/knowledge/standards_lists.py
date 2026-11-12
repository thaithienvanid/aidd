"""The standards library's lists: the rows of `aidd standard list --json`, and the tables docs/STANDARDS.md and the packs
hold, split from `standards` to keep each module short."""

from __future__ import annotations

from aidd.kernel.text import md_cell
from aidd.knowledge import standards

# The version of `aidd standard list --json` and `aidd standard list --stacks --json` (schemas/standard-list.schema.json,
# schemas/stack-list.schema.json): a new key keeps it, a renamed or removed one bumps it.
LIST_SCHEMA_VERSION = "1"


def standard_rows(cfg) -> dict:
    """`aidd standard list --json`: the open choices, and each library standard with its policy mark and whether it is here."""
    policy = standards.company_policy(cfg)
    present = {e["from_library"]["id"] for e in standards.standard_copies(list(cfg.standards))} if cfg else set()
    lib = standards.standards_library()
    fills: dict[str, list[str]] = {}
    for s in lib.values():
        for ref in s.meta["fills"]:
            fills.setdefault(ref, []).append(s.id)
    picks = standards.defaults(lib)
    return {
        "schema_version": LIST_SCHEMA_VERSION,
        "open_choices": [
            {
                "ref": ref,
                "pack": c["owner"],
                "question": c["question"],
                "default_answer": c["default"],
                "options": c["options"],
                "filled_by": sorted(fills.get(ref, [])),
                "default_by_ecosystem": {eco: sid for (r, eco), sid in sorted(picks.items()) if r == ref},
            }
            for ref, c in standards.open_choices().items()
        ],
        "standards": [
            {
                "id": s.id,
                "fills": s.meta["fills"],
                "tool": (s.meta.get("tool") or {}).get("name"),
                "checked_version": s.meta.get("checked_version"),
                "checked": s.meta.get("checked"),
                "status": s.meta["status"],
                "default": bool(s.meta.get("default")) and s.active,
                "policy": standards.policy_mark(s.id, policy),
                "added": s.id in present,
            }
            for s in sorted(lib.values(), key=lambda x: x.id)
        ],
    }


def stack_rows(cfg) -> dict:
    policy = standards.company_policy(cfg)
    allowed = policy.get("allow_stacks")
    known = standards.stacks()
    return {
        "schema_version": LIST_SCHEMA_VERSION,
        "stacks": [
            {
                "name": name,
                "description": data["description"],
                "extends": data.get("extends"),
                "standards": standards.stack_standards(name, known),
                "allowed": allowed is None or name in allowed,
            }
            for name, data in sorted(known.items())
        ],
    }


def open_choices_table(owner: str) -> str:
    """One pack's or skill's open choices as a table: the choice, the question, aidd's default, and the options."""
    rows_ = [c for c in standards.open_choices().values() if c["owner"] == owner]
    lines = ["| Choice | Question | aidd's default | Options |", "| --- | --- | --- | --- |"]
    lines += [f"| `{c['id']}` | {md_cell(c['question'])} | {md_cell(c['default'])} | {md_cell(', '.join(c['options']))} |" for c in rows_]
    return "\n".join(lines)


def catalog_choices() -> str:
    """docs/STANDARDS.md: every open choice, its default, and the library standards that fill it. Where an ecosystem has
    several options for a choice, aidd's default among them is marked."""
    lib = standards.standards_library()
    picks = set(standards.defaults(lib).items())
    options: dict[tuple[str, str], int] = {}
    for s in lib.values():
        for ref in s.meta["fills"]:
            options[(ref, s.ecosystem)] = options.get((ref, s.ecosystem), 0) + s.active
    fills: dict[str, list[str]] = {}
    for s in lib.values():
        for ref in s.meta["fills"]:
            mark = " (default)" if options[(ref, s.ecosystem)] > 1 and ((ref, s.ecosystem), s.id) in picks else ""
            fills.setdefault(ref, []).append(f"`{s.id}`{mark}")
    lines = ["| Choice | Question | aidd's default | Library standards |", "| --- | --- | --- | --- |"]
    for ref, c in standards.open_choices().items():
        lines.append(f"| `{ref}` | {md_cell(c['question'])} | {md_cell(c['default'])} | {', '.join(sorted(fills.get(ref, []))) or '—'} |")
    return "\n".join(lines)


def catalog_library() -> str:
    """docs/STANDARDS.md: the library by ecosystem, with each tool's checked version and date."""
    by_eco: dict[str, list[standards.Standard]] = {}
    for s in sorted(standards.standards_library().values(), key=lambda x: x.id):
        by_eco.setdefault(s.ecosystem, []).append(s)
    parts = []
    for eco, items in sorted(by_eco.items()):
        lines = [f"### {eco}", "", "| Standard | Fills | Tool | Checked version | Checked | Status |", "| --- | --- | --- | --- | --- | --- |"]
        for s in items:
            m = s.meta
            tool = (m.get("tool") or {}).get("name", "—")
            status = m["status"] + (f", replaced by `{m['replaced_by']}`" if m.get("replaced_by") else "")
            lines.append(f"| `{s.id}` | {', '.join(f'`{r}`' for r in m['fills'])} | {tool} | {m.get('checked_version', '—')} | {m['checked']} | {status} |")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


def catalog_stacks() -> str:
    known = standards.stacks()
    lines = ["| Stack | For | Extends | Standards |", "| --- | --- | --- | --- |"]
    for name, data in sorted(known.items()):
        ids = ", ".join(f"`{x}`" for x in standards.stack_standards(name, known))
        lines.append(f"| `{name}` | {md_cell(data['description'])} | {('`' + data['extends'] + '`') if data.get('extends') else '—'} | {ids} |")
    return "\n".join(lines)
