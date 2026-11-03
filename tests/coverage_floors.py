"""Branch-coverage floors for the whole package and the risk rules, after a coverage run.

CI runs it after `coverage combine` (`.github/workflows/ci.yml`). Each floor sits just under what the suite reaches,
and only rises: raise one when the suite reaches more, and never lower one to make a change pass. Add a test instead.

    python3 tests/coverage_floors.py    # exit 1 names each area under its floor
"""

from __future__ import annotations

import subprocess
import sys

# (what it covers, the files, the floor in percent of branches and lines together, as `coverage report` counts them)
FLOORS = (
    ("the risk rules", "src/aidd/risk/*", 94),
    ("everything", "src/aidd/*", 90),
    ("aidd-team's prototype tool", "plugins/aidd-team/tools/*", 86),
)


def main() -> int:
    under = []
    for what, include, floor in FLOORS:
        done = subprocess.run(
            [sys.executable, "-m", "coverage", "report", f"--include={include}", f"--fail-under={floor}", "--format=total"],
            capture_output=True,
            text=True,
            check=False,
        )
        total = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else "?"
        print(f"{what}: {total}% (floor {floor}%)")
        if done.returncode != 0:
            under.append(f"{what} is at {total}%, under its floor of {floor}%: add tests for what the change left uncovered")
    for line in under:
        print(f"error: {line}", file=sys.stderr)
    return 1 if under else 0


if __name__ == "__main__":
    sys.exit(main())
