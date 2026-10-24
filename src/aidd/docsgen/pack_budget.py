"""The knowledge templates, enforced: `aidd eval packs`.

A domain pack is generated from `schemas/packs.json` in one template (docs.PACK_SECTIONS); a practice skill is written
by hand in another (PRACTICE_SECTIONS), with its Standards table generated from its registry ids. Both load into an
agent's context, so both have a size cap, and a test name two of them share would make a Spec that loads both
unmergeable (the gate fails on a repeated `tests.commands` name). `problems()` lists every break of the templates:

- a pack standard no checklist row or test cites, or a row that cites a standard the pack does not list;
- more standards, tests, references, or rows per loop step than the template allows, or a Scope over 60 words;
- a test name used twice across the packs and practice skills, or a pointer to a test its owner does not have;
- a section out of order, a required section missing, or a heading the template does not have;
- a business pack (`kind: business`) with no Terms or no Invariants and missed cases;
- a SKILL.md or a reference over its estimated-token cap;
- a skill's or command's description over DESCRIPTION_CHARS, or one that repeats the config path the aidd skill names.

Tokens are estimated at four characters a token (`estimate_tokens`): a stable, dependency-free measure for a cap,
not any tokenizer's exact count.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from aidd import knowledge
from aidd.docsgen import pack_render, token_caps
from aidd.kernel import documents, resources

PACK_REFERENCES = 2
PRACTICE_REFERENCES = 3
# 10 since 1.0.0 (from 8): a pack holds its domain's engineering too (rendering, real time, sustainability), not only its rules.
PACK_STANDARDS = 10
PACK_TESTS = 8
SCOPE_WORDS = 60
# Every session lists every skill's description, so each says only when to load it. The aidd-team router lists every
# role and command by name as its triggers, so it has its own cap. The aidd skill names `.aidd/config.yaml` once; a team
# skill's "aidd repository" scopes it without repeating the path.
DESCRIPTION_CHARS = 250
ROUTER_DESCRIPTION_CHARS = 460
REPEATED_SCOPE = "(.aidd/config.yaml)"
ROWS_PER_STEP = (1, 4)

# The practice template, in order: the loop steps it works in, between its Standards and its Test commands.
PRACTICE_SECTIONS = ("Standards", "Plan", "Specify", "Implement", "Verify", "Review", "Roll out", "Learn", "Test commands", "Stop if", "Hand off")
PRACTICE_REQUIRED = ("Standards", "Test commands", "Stop if", "Hand off")
PACK_REQUIRED = ("Scope", "Standards", "Checklist by loop step", "Test commands", "Keep it current")

H2 = re.compile(r"^## (.+)$", re.M)


def skills_dir() -> Path:
    return resources.data_dir("team") / "skills"


def headings(text: str) -> list[str]:
    """The H2 headings of a Markdown file, outside fenced code."""
    return H2.findall(re.sub(r"```.*?```", "", text, flags=re.S))


def table_names(body: str) -> list[str]:
    """The first cell of each data row of the first Markdown table in `body`, emerging marks dropped."""
    rows = [ln for ln in body.splitlines() if ln.startswith("|")]
    return [re.sub(r" \(emerging\)$", "", r.strip("|").split("|")[0].strip()) for r in rows[2:]]


def _order(where: str, found: list[str], allowed: tuple[str, ...], required: tuple[str, ...]) -> list[dict]:
    out = [{"where": where, "problem": f"a heading the template does not have: {h!r}"} for h in found if h not in allowed]
    known = [h for h in found if h in allowed]
    if known != sorted(known, key=allowed.index) or len(known) != len(set(known)):
        out.append({"where": where, "problem": f"sections out of the template's order: {', '.join(known)}"})
    out += [{"where": where, "problem": f"no {h!r} section"} for h in required if h not in found]
    return out


def _references(where: str, folder: Path, most: int) -> tuple[list[dict], dict[str, int]]:
    refs = sorted((folder / "references").glob("*.md")) if (folder / "references").is_dir() else []
    sizes = {r.name: token_caps.estimate_tokens(r.read_text(encoding="utf-8")) for r in refs}
    out = [{"where": where, "problem": f"{len(refs)} references; the template allows {most}"}] if len(refs) > most else []
    out += [
        {"where": where, "problem": f"references/{n} is about {t} tokens; the cap is {token_caps.REFERENCE_TOKENS}"}
        for n, t in sizes.items()
        if t > token_caps.REFERENCE_TOKENS
    ]
    return out, sizes


def practice_tests(text: str) -> list[str]:
    """A practice skill's own test names: the first column of the table in its Test commands section."""
    return table_names(documents.raw_section(text, "Test commands"))


def pack_sizes_and_problems(folder: Path | None = None) -> tuple[list[dict], list[dict]]:
    """Every pack's and practice skill's estimated size, and every break of the templates."""
    folder = folder or skills_dir()
    data = knowledge.roles()
    sizes: list[dict] = []
    problems: list[dict] = []
    owners: dict[str, set[str]] = {}
    names: dict[str, list[str]] = {}

    for d in data["domains"]:
        where = f"pack {d['slug']}"
        label = {s["id"] for s in d["standards"]}
        text = pack_render.render_pack(d)
        for row in [*d["checklist"], *d["tests"], *d.get("obligations", [])]:
            problems += [{"where": where, "problem": f"cites {x!r}, which the pack does not list"} for x in row.get("cites", []) if x not in label]
        # An obligation names a date, not a practice: only a checklist row or a test puts a standard to work.
        cited = {x for row in [*d["checklist"], *d["tests"]] for x in row.get("cites", [])}
        problems += [{"where": where, "problem": f"standard {s['id']!r} is cited by no checklist row or test"} for s in d["standards"] if s["id"] not in cited]
        if len(d["standards"]) > PACK_STANDARDS:
            problems.append({"where": where, "problem": f"{len(d['standards'])} standards; the template allows {PACK_STANDARDS}"})
        if len(d["tests"]) > PACK_TESTS:
            problems.append({"where": where, "problem": f"{len(d['tests'])} test commands; the template allows {PACK_TESTS}"})
        if d.get("kind") == "business":
            # The words and the rules a team gets wrong without an expert: what the domain expert's card checks.
            problems += [{"where": where, "problem": f"a business pack with no `{k}`"} for k in ("terms", "invariants") if not d.get(k)]
        if not d["tests"] and not d.get("tests_elsewhere"):
            problems.append({"where": where, "problem": "no test command of its own and no pointer to one"})
        steps: dict[str, int] = {}
        for c in d["checklist"]:
            steps[c["step"]] = steps.get(c["step"], 0) + 1
        if d.get("defaults"):
            steps["Entry"] = steps.get("Entry", 0) + 1
        lo, hi = ROWS_PER_STEP
        problems += [
            {"where": where, "problem": f"{n} checklist rows at {step}; the template allows {lo} to {hi}"} for step, n in steps.items() if not lo <= n <= hi
        ]
        words = len(pack_render.pack_scope(d).split())
        if words > SCOPE_WORDS:
            problems.append({"where": where, "problem": f"the Scope is {words} words; the cap is {SCOPE_WORDS}"})
        problems += _order(where, headings(text), pack_render.PACK_SECTIONS, PACK_REQUIRED)
        tokens = token_caps.estimate_tokens(text)
        if tokens > token_caps.PACK_TOKENS:
            problems.append({"where": where, "problem": f"SKILL.md is about {tokens} tokens; the cap is {token_caps.PACK_TOKENS}"})
        ref_problems, ref_sizes = _references(where, folder / d["slug"], PACK_REFERENCES)
        problems += ref_problems
        listed = {r["path"].removeprefix("references/") for r in d.get("references", [])}
        # The open choices of a preloaded pack are a generated reference (docs.open_choices_reference), not a listed one.
        if listed != set(ref_sizes) - {pack_render.OPEN_CHOICES_REF}:
            problems.append({"where": where, "problem": f"references on disk {sorted(ref_sizes)} differ from the registry's {sorted(listed)}"})
        sizes.append({"name": d["slug"], "kind": "pack", "tokens": tokens, "references": ref_sizes})
        owners[d["slug"]] = {t["name"] for t in d["tests"]}
        for t in d["tests"]:
            names.setdefault(t["name"], []).append(where)

    practices = data.get("practices", {})
    for name in knowledge.practice_names():
        where = f"practice {name}"
        path = folder / name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        if name not in practices:
            problems.append({"where": where, "problem": "no `practices` entry in schemas/roles.json, so no standard of its is checked"})
        if f"<!-- aidd:gen practice:{name} -->" not in documents.raw_section(text, "Standards"):
            problems.append({"where": where, "problem": f"its Standards section is not the generated block `practice:{name}`"})
        body = text.split("\n---", 2)[-1]
        head = body.split("\n## ", 1)[0]
        for cue in ("**Use it when**", "**Do not use when**"):
            if cue not in head:
                problems.append({"where": where, "problem": f"no {cue} before the first section"})
        problems += _order(where, headings(text), PRACTICE_SECTIONS, PRACTICE_REQUIRED)
        tokens = token_caps.estimate_tokens(text)
        if tokens > token_caps.PRACTICE_TOKENS:
            problems.append({"where": where, "problem": f"SKILL.md is about {tokens} tokens; the cap is {token_caps.PRACTICE_TOKENS}"})
        ref_problems, ref_sizes = _references(where, folder / name, PRACTICE_REFERENCES)
        problems += ref_problems
        sizes.append({"name": name, "kind": "practice", "tokens": tokens, "references": ref_sizes})
        own = practice_tests(text)
        owners[name] = set(own)
        for t in own:
            names.setdefault(t, []).append(where)

    for test, places in sorted(names.items()):
        if len(places) > 1:
            problems.append({"where": ", ".join(places), "problem": f"the test name {test!r} is used {len(places)} times; a Spec that loads both cannot merge"})
    for d in data["domains"]:
        for x in d.get("tests_elsewhere", []):
            if x["owner"] not in owners:
                problems.append({"where": f"pack {d['slug']}", "problem": f"points to tests in {x['owner']!r}, which is no pack or practice skill"})
                continue
            missing = [t for t in x["tests"] if t not in owners[x["owner"]]]
            problems += [{"where": f"pack {d['slug']}", "problem": f"points to {t!r} in {x['owner']}, which has no test by that name"} for t in missing]
        for x in d.get("owned_elsewhere", []):
            if x["owner"] not in owners:
                problems.append({"where": f"pack {d['slug']}", "problem": f"points to {x['owner']!r}, which is no pack or practice skill"})
        for x in d["scope"]["neighbours"]:
            if x not in owners:
                problems.append({"where": f"pack {d['slug']}", "problem": f"names the neighbour {x!r}, which is no pack or practice skill"})
    problems += _description_problems(folder)
    return sizes, problems


def description(text: str) -> str:
    """The `description` of a skill's or command's front matter, unquoted; empty when it has none."""
    head = text.split("---", 2)[1] if text.startswith("---") else ""
    m = re.search(r"^description: (.+)$", head, re.M)
    raw = m.group(1).strip() if m else ""
    return str(json.loads(raw)) if raw.startswith('"') else raw


def pack_descriptions(folder: Path | None = None) -> list[dict]:
    """The description of the aidd skill, each pack, each practice skill, the aidd-team router, and each team command,
    with its length in characters."""
    folder = folder or skills_dir()
    texts = [("skill", "aidd", (resources.data_dir("skill") / "SKILL.md").read_text(encoding="utf-8"))]
    texts += [("skill", d["slug"], pack_render.render_pack(d)) for d in knowledge.roles()["domains"]]
    texts += [("skill", n, (folder / n / "SKILL.md").read_text(encoding="utf-8")) for n in knowledge.practice_names()]
    router = folder / "aidd-team" / "SKILL.md"
    texts += [("skill", "aidd-team", router.read_text(encoding="utf-8"))] if router.is_file() else []
    commands = resources.data_dir("team") / "commands"
    texts += [("command", p.stem, p.read_text(encoding="utf-8")) for p in sorted(commands.glob("*.md"))]
    return [{"name": name, "kind": kind, "chars": len(description(text))} for kind, name, text in texts]


def _description_problems(folder: Path) -> list[dict]:
    out: list[dict] = []
    for d in knowledge.roles()["domains"]:
        out += _one_description(f"pack {d['slug']}", description(pack_render.render_pack(d)), DESCRIPTION_CHARS)
    for name in knowledge.practice_names():
        out += _one_description(f"practice {name}", description((folder / name / "SKILL.md").read_text(encoding="utf-8")), DESCRIPTION_CHARS)
    router = folder / "aidd-team" / "SKILL.md"
    if router.is_file():
        out += _one_description("skill aidd-team", description(router.read_text(encoding="utf-8")), ROUTER_DESCRIPTION_CHARS)
    out += _one_description("skill aidd", description((resources.data_dir("skill") / "SKILL.md").read_text(encoding="utf-8")), DESCRIPTION_CHARS, own_path=True)
    for p in sorted((resources.data_dir("team") / "commands").glob("*.md")):
        out += _one_description(f"command {p.stem}", description(p.read_text(encoding="utf-8")), DESCRIPTION_CHARS)
    return out


def _one_description(where: str, text: str, cap: int, own_path: bool = False) -> list[dict]:
    out = [{"where": where, "problem": f"the description is {len(text)} characters; the cap is {cap}"}] if len(text) > cap else []
    if not own_path and REPEATED_SCOPE in text:
        out.append({"where": where, "problem": f'the description repeats {REPEATED_SCOPE!r}; say "in an aidd repository", since the aidd skill names the path'})
    return out


def problems(folder: Path | None = None) -> list[dict]:
    return pack_sizes_and_problems(folder)[1]
