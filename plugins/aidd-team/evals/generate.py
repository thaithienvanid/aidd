"""Generate the trigger cases (`loads-*`, `skips-*`, `held-out-loads-*`) from `triggers.json`, so their prompts and descriptions have one owner.

    python3 plugins/aidd-team/evals/generate.py          # write the cases
    python3 plugins/aidd-team/evals/generate.py --check  # exit 1 and name each file that is stale

A trigger case is a folder with a prompt, a grader, a seed, and a `case.yaml`. Only the prompt text, the description, and the sibling skills
that also count (`also`) differ between cases, so `triggers.json` holds those, and this script writes the rest. Never edit a generated case by hand: edit `triggers.json`.
It uses the standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

CASE_YAML = 'schema_version: "1.1"\nname: {name}\ncontext:\n  scaffold_script: fixture.sh\n'
FIXTURE = """#!/usr/bin/env bash
set -euo pipefail
# The prompt says this repository uses aidd, so the workspace holds the minimal aidd config. Without it the aidd skill
# asks whether to apply aidd, and no practice skill loads. The file is ours and is written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
"""
PROMPT = """---
description: {description}
plugins:
  - "../.."
  - "../../../.."
max_turns: 6
timeout_seconds: 300
allowed_tools:
  - Read
  - Glob
  - Grep
  - Skill
tags:
  - trigger
{held}  - {skill}
  - claim:trigger:{skill}
  - tier:{tier}
---

{prompt}
"""
LOADS = """---
type: tool_used
tool: Skill
input_match: '"skill"\\s*:\\s*"(?:aidd-team:)?{names}"'
min: 1
---
"""
SKIPS = """---
type: tool_used
tool: Skill
input_match: '"skill"\\s*:\\s*"(?:aidd-team:)?{names}"'
min: 0
max: 0
arm: both
---
"""


def quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def files(data: dict) -> dict[str, str]:
    """Every generated file as a path under this folder and its text."""
    out: dict[str, str] = {}
    for skill, entry in data["skills"].items():
        for case in entry["cases"]:
            name = case["name"]
            kind = "held-out" if name.startswith("held-out-") else name.split("-", 1)[0]
            description = quote(entry["description"][kind])
            tier = "held-out" if kind == "held-out" else "description-change"
            prompt = PROMPT.format(description=description, held="  - held-out\n" if kind == "held-out" else "", skill=skill, tier=tier, prompt=case["prompt"])
            names = "(?:" + "|".join([skill, *case.get("also", [])]) + ")" if case.get("also") else skill
            grader = (SKIPS if kind == "skips" else LOADS).format(names=names)
            out[f"{name}/prompt.md"] = prompt
            out[f"{name}/case.yaml"] = CASE_YAML.format(name=name)
            out[f"{name}/fixture.sh"] = FIXTURE
            out[f"{name}/graders/{'skill-not-loaded' if kind == 'skips' else 'skill-loaded'}.md"] = grader
    return out


def main(argv: list[str], folder: Path = HERE) -> int:
    data = json.loads((folder / "triggers.json").read_text(encoding="utf-8"))
    wanted = files(data)
    stale = [rel for rel, text in wanted.items() if not (folder / rel).is_file() or (folder / rel).read_text(encoding="utf-8") != text]
    names = {rel.split("/", 1)[0] for rel in wanted}
    extra = sorted(p.name for p in folder.iterdir() if p.is_dir() and p.name.startswith(("loads-", "skips-", "held-out-")) and p.name not in names)
    if "--check" in argv:
        for rel in stale:
            print(f"stale: {rel}")
        for name in extra:
            print(f"not in triggers.json: {name}")
        if stale or extra:
            print("run `python3 plugins/aidd-team/evals/generate.py` and commit the result")
        return 1 if stale or extra else 0
    for rel in stale:
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(wanted[rel], encoding="utf-8")
        print(f"wrote: {rel}")
    for name in extra:
        print(f"not in triggers.json, left alone: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
