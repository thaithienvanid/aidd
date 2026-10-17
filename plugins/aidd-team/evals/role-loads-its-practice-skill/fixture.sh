#!/usr/bin/env bash
set -euo pipefail
# The module the prompt names, with the pluralization bug in it.
cat > stays.py <<'PY'
from datetime import date


def nights(check_in: date, check_out: date) -> int:
    return (check_out - check_in).days


def nights_label(check_in: date, check_out: date) -> str:
    n = nights(check_in, check_out)
    return f"{n} night" + ("s" if n > 2 else "")
PY
