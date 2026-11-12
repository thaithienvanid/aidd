"""What each agent eval case proves, and which claims have no case.

Every case in the four suites names a `claim` (a behavior or a rule it proves), a `tier` (when to run it), and a one-line
`proves`. A claim is `kind:name`, and the kind is one of KINDS. `evals/claims.json` is the closed registry of the claims
(claim_registry.py says who owns each kind): a case that names a claim it does not list fails, every claim it lists is
required, and it holds the claims a case does not cover yet, each with its reason. Nothing here runs an agent.

A routing or roles case holds `claim`, `tier`, and `proves` as keys. A plugin or team case is a folder, and its
`prompt.md` front matter holds `claim:<claim>` and `tier:<tier>` as `tags`, because `claude plugin eval` reads only
the keys it knows. Its `description` is its `proves`.
"""

from __future__ import annotations

import json
from pathlib import Path

from aidd.evals import claim_registry, suites, trigger_cases
from aidd.kernel import resources

KINDS = ("action", "control", "duty", "gate", "principle", "route", "stop", "trigger")
TIERS = ("smoke", "full", "held-out", "description-change", "by-hand")
SUITES = {"routing": "evals/routing", "roles": "evals/roles", "plugin": "evals/plugin", "team": "evals/team"}
# The claims that are not a case's own: an action is in risks.json, and a trigger claim names a practice skill.
CLAIMS_FILE = "evals/claims.json"


def _listed(value: object) -> list[str]:
    return [value] if isinstance(value, str) else [str(x) for x in value] if isinstance(value, list) else []


def _front(text: str) -> tuple[str, list[str]]:
    """A case prompt's `description` and `tags`. `claude plugin eval` reads this front matter as YAML, and the tests hold it to a
    strict block subset (tests/test_plugin_evals.py), so a line-by-line read gives the same two fields."""
    head = text.split("\n---\n", 1)[0]
    description, tags, in_tags = "", [], False
    for line in head.splitlines():
        if in_tags and line.startswith("  - "):
            tags.append(line[4:].strip().strip("'\""))
            continue
        in_tags = line == "tags:"
        if line.startswith("description: "):
            description = line.removeprefix("description: ").strip().strip("'\"").replace("''", "'")
    return description, tags


def _folder_case(name: str, prompt: str, suite: str) -> dict:
    """A plugin or team case, from its `prompt.md`: its `claim:` and `tier:` tags, and its description as the line it proves."""
    description, tags = _front(prompt)
    tiers = [t.removeprefix("tier:") for t in tags if t.startswith("tier:")]
    return {
        "suite": suite,
        "id": name,
        "claims": [t.removeprefix("claim:") for t in tags if t.startswith("claim:")],
        "tier": tiers[0] if len(tiers) == 1 else None,
        "proves": description,
        "tags": tags,
    }


def suite_cases(root: Path) -> list[dict]:
    """Every case of the four suites as `{suite, id, claims, tier, proves, tags}`. `claims` is empty and `tier` is None for a
    case that names none, or more than one tier, so `case_problems` can say so. `tags` is a plugin or team case's front
    matter `tags` (a routing or roles case's own `tags`, if any), so no caller reads the front matter again."""
    rows: list[dict] = []
    for suite in ("routing", "roles"):
        for sc in suites.load_scenarios(root / SUITES[suite]):
            row = {"suite": suite, "id": str(sc["id"]), "claims": _listed(sc.get("claim")), "tier": sc.get("tier"), "proves": str(sc.get("proves", ""))}
            rows.append(row | {"tags": _listed(sc.get("tags"))})
    for suite in ("plugin", "team"):
        folder = root / SUITES[suite]
        prompts = {p.name: (p / "prompt.md").read_text(encoding="utf-8") for p in folder.iterdir() if p.is_dir() and (p / "prompt.md").is_file()}
        if suite == "team":  # the trigger cases come from triggers.json, whether or not a run has written their folders
            prompts = {name: text for name, text in prompts.items() if not name.startswith(trigger_cases.PREFIXES)}
            files = trigger_cases.case_files(trigger_cases.load_triggers(root))
            prompts |= {rel.split("/", 1)[0]: text for rel, text in files.items() if rel.endswith("/prompt.md")}
        rows += [_folder_case(name, prompts[name], suite) for name in sorted(prompts)]
    return rows


def case_problems(rows: list[dict], file: dict | None = None) -> list[str]:
    """Each case that names no claim, a claim that is not `kind:name` of a known kind, an `action:` that risks.json lacks, no
    tier or a tier outside TIERS, or no line it proves (a routing or roles case). With the registry `file`, also a claim it does not list."""
    actions = set(resources.load_json("risks.json")["actions"])
    problems: list[str] = []
    for row in rows:
        where = f"{row['suite']}/{row['id']}"
        if not row["claims"]:
            problems.append(f"{where}: name its `claim`")
        for claim in row["claims"]:
            kind, _, name = claim.partition(":")
            if kind not in KINDS or not name:
                problems.append(f"{where}: claim {claim!r} is not `kind:name` with a kind from {', '.join(KINDS)}")
            elif kind == "action" and name not in actions:
                problems.append(f"{where}: claim {claim!r} names no action in schemas/risks.json")
            elif file is not None and not claim_registry.is_registered(claim, file):
                problems.append(f"{where}: claim {claim!r} is not in the registry: list it in evals/claims.json, or use a claim that is")
        if row["tier"] not in TIERS:
            problems.append(f"{where}: `tier` is {row['tier']!r}, one of {', '.join(TIERS)}")
        if not row["proves"].strip():
            problems.append(f"{where}: say in one line what it `proves`")
    return problems


def claims_file(root: Path) -> dict:
    """evals/claims.json: the registry (`gates`, `stops`, `routes`, `duties`, `controls`, `principles`, `triggers`) and `known_gaps`
    (a claim with no case yet, and why)."""
    return json.loads((root / CLAIMS_FILE).read_text(encoding="utf-8"))


def required_claims(file: dict) -> list[str]:
    """Every claim a case must cover: each action in risks.json, a `route:` claim for each of its areas, every claim the registry
    lists, and a `stop_code:` claim for each stop code that no stop claim reaches."""
    risks = resources.load_json("risks.json")
    codes = [f"stop_code:{c}" for c in claim_registry.uncovered_stop_codes(file)]
    return [f"action:{a}" for a in risks["actions"]] + [f"route:{a}" for a in risks["areas"]] + claim_registry.registry_claims(file) + codes


def claim_gaps(rows: list[dict], file: dict) -> tuple[list[str], list[str]]:
    """(the required claims with no case that are not a known gap, the known gaps that a case now covers or that nothing requires).
    The first is a new gap: write a case. The second is a closed gap: remove it from `known_gaps`."""
    covered = {c for row in rows for c in row["claims"]}
    required, known = required_claims(file), set(file.get("known_gaps", {}))
    return (
        sorted(c for c in required if c not in covered and c not in known),
        sorted(c for c in known if c in covered or c not in required),
    )


def claim_cases(rows: list[dict]) -> dict[str, list[dict]]:
    """The cases of each claim, claims in sorted order."""
    out: dict[str, list[dict]] = {}
    for row in rows:
        for claim in row["claims"]:
            out.setdefault(claim, []).append(row)
    return dict(sorted(out.items()))


def claim_coverage_table(rows: list[dict], file: dict) -> str:
    """The claims as a Markdown table: each claim, its case count, the cases per tier, and for a known gap (`0` cases) its reason. A
    required claim with no case and no reason comes last, so the gap shows."""
    tiers = ("smoke", "full", "held-out", "description-change")
    lines = ["| Claim | Cases | " + " | ".join(tiers) + " | Known gap |", "| --- | --- | " + " | ".join("---" for _ in tiers) + " | --- |"]
    for claim, cases in claim_cases(rows).items():
        lines.append(f"| `{claim}` | {len(cases)} | " + " | ".join(str(sum(c["tier"] == t for c in cases)) for t in tiers) + " |  |")
    for claim, reason in sorted(file.get("known_gaps", {}).items()):
        lines.append(f"| `{claim}` | 0 | " + " | ".join("0" for _ in tiers) + f" | {reason} |")
    for claim in claim_gaps(rows, file)[0]:  # a required claim no case proves and no known gap names
        lines.append(f"| `{claim}` | 0 | " + " | ".join("0" for _ in tiers) + " | no case yet: write one |")
    return "\n".join(lines)
