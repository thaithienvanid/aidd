"""The team suite's trigger cases (`loads-*`, `skips-*`, `held-out-loads-*`), built from `evals/team/triggers.json`, so their
prompts and descriptions have one owner and git tracks none of the 72 folders.

    PYTHONPATH=src python3 -m aidd.evals.trigger_cases    # write them into evals/team/ before `claude plugin eval`

A trigger case is a folder with a prompt, a grader, a seed, and a `case.yaml`. Only the prompt text, the description, and the
sibling skills that also count (`also`) differ between cases, so `triggers.json` holds those, and this module writes the rest.
git ignores the written folders (`.gitignore`), so edit `triggers.json`, never a written case. The same input always gives the
same files. `claims.suite_cases` reads the cases from here, not from the folders, so a checkout with or without them gives
the same claim table.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from aidd.kernel import regular_files

SUITE = "evals/team"
TRIGGERS_FILE = f"{SUITE}/triggers.json"
# A written case's folder starts with one of these; no hand-written case may.
PREFIXES = ("loads-", "skips-", "held-out-")

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
# The plugins load relative to the case folder, evals/team/<case>/: the team plugin, and the aidd plugin at the root.
PROMPT = """---
description: {description}
plugins:
  - "../../../plugins/aidd-team"
  - "../../.."
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


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def read_json(root: Path, rel: str) -> dict:
    """The JSON object in the regular file at `rel` in the checkout `root`, read as every repository file is
    (`regular_files.named_text`): never through a link. Raises OSError when there is no such file to read."""
    text, why = regular_files.named_text(root, rel)
    if text is None:
        raise OSError(f"cannot read {rel} under {root}: {why}")
    return json.loads(text)


def load_triggers(root: Path) -> dict:
    """`evals/team/triggers.json` in the checkout at `root`."""
    return read_json(root, TRIGGERS_FILE)


def case_files(data: dict) -> dict[str, str]:
    """Every trigger case's files, as `<case>/<file>` and its text, in a fixed order."""
    out: dict[str, str] = {}
    for skill, entry in data["skills"].items():
        for case in entry["cases"]:
            name = case["name"]
            kind = "held-out" if name.startswith("held-out-") else name.split("-", 1)[0]
            tier = "held-out" if kind == "held-out" else "description-change"
            held = "  - held-out\n" if kind == "held-out" else ""
            prompt = PROMPT.format(description=_quote(entry["description"][kind]), held=held, skill=skill, tier=tier, prompt=case["prompt"])
            names = "(?:" + "|".join([skill, *case["also"]]) + ")" if case.get("also") else skill
            out[f"{name}/prompt.md"] = prompt
            out[f"{name}/case.yaml"] = CASE_YAML.format(name=name)
            out[f"{name}/fixture.sh"] = FIXTURE
            out[f"{name}/graders/{'skill-not-loaded' if kind == 'skips' else 'skill-loaded'}.md"] = (SKIPS if kind == "skips" else LOADS).format(names=names)
    return out


def write_cases(folder: Path, data: dict) -> list[str]:
    """Write every trigger case into `folder`, and remove a written case that `data` no longer names, so a run never scores
    a stale one. Returns what changed, one line each."""
    wanted = case_files(data)
    names = {rel.split("/", 1)[0] for rel in wanted}
    changed: list[str] = []
    for old in sorted(p for p in folder.iterdir() if p.is_dir() and p.name.startswith(PREFIXES) and p.name not in names):
        shutil.rmtree(old)
        changed.append(f"removed: {old.name} (not in triggers.json)")
    for rel, text in wanted.items():
        if regular_files.repository_text(folder, rel) != text:
            regular_files.write_text_safely(folder, rel, text)
            changed.append(f"wrote: {rel}")
    return changed


def main(argv: list[str] | None = None) -> int:
    """Write the cases into `evals/team/` of the checkout this aidd runs from, or of the folder given."""
    args = sys.argv[1:] if argv is None else argv
    root = Path(args[0]) if args else Path(__file__).resolve().parents[3]
    if not (root / TRIGGERS_FILE).is_file():
        print(f"no {TRIGGERS_FILE} under {root}: run this from aidd's source checkout, or name it", file=sys.stderr)
        return 2
    changed = write_cases(root / SUITE, load_triggers(root))
    print("\n".join(changed) if changed else "the trigger cases are up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
