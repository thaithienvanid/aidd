"""Coverage floors for the whole package and the risk rules, after a coverage run.

CI runs it after `tests/run.py --coverage`, which combines the data into `.coverage` (`.github/workflows/ci.yml`). Each floor sits just under what the suite reaches,
and only rises: raise one when the suite reaches more, and never lower one to make a change pass. Add a test instead.
A floor holds for lines and branches together, as `coverage report` counts them. The summary also gives line coverage
and branch coverage on their own, so a drop in one cannot hide behind a rise in the other.

    python3 tests/coverage_floors.py    # exit 1 names each area under its floor
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# (what it covers, the files, the floor in percent of branches and lines together, as `coverage report` counts them)
FLOORS = (
    ("the risk rules", "src/aidd/risk/*", 94),
    ("everything", "src/aidd/*", 90),
    ("aidd-team's prototype tool", "plugins/aidd-team/tools/*", 86),
)


def percent(covered: int, total: int) -> str:
    return f"{100 * covered / total:.1f}%" if total else "n/a"


def line_and_branch(totals: dict) -> tuple[str, str]:
    """Line coverage and branch coverage on their own, from the `totals` of `coverage json`."""
    return percent(totals.get("covered_lines", 0), totals.get("num_statements", 0)), percent(totals.get("covered_branches", 0), totals.get("num_branches", 0))


def separately(include: str) -> tuple[str, str]:
    """(lines, branches) as percents for the files `include` names, or ("?", "?") when coverage cannot say."""
    done = subprocess.run([sys.executable, "-m", "coverage", "json", f"--include={include}", "-o", "-"], capture_output=True, text=True, check=False)
    try:
        return line_and_branch(json.loads(done.stdout)["totals"])
    except (ValueError, KeyError):
        return "?", "?"


def main() -> int:
    under = []
    rows = []
    for what, include, floor in FLOORS:
        done = subprocess.run(
            [sys.executable, "-m", "coverage", "report", f"--include={include}", f"--fail-under={floor}", "--format=total"],
            capture_output=True,
            text=True,
            check=False,
        )
        total = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else "?"
        lines, branches = separately(include)
        print(f"{what}: {total}% (floor {floor}%); lines {lines}, branches {branches}")
        rows.append(f"| {what} | {total}% | {floor}% | {lines} | {branches} |")
        if done.returncode != 0:
            under.append(f"{what} is at {total}%, under its floor of {floor}%: add tests for what the change left uncovered")
    for line in under:
        print(f"error: {line}", file=sys.stderr)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        header = "| Area | Lines and branches | Floor | Lines | Branches |\n| --- | --- | --- | --- | --- |\n"
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n" + header + "\n".join(rows) + "\n")
    return 1 if under else 0


if __name__ == "__main__":
    sys.exit(main())
