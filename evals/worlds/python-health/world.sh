#!/usr/bin/env bash
set -euo pipefail
# A small clinic booking module in Python, in a repository that uses aidd under the solo profile. It lists the free slots of
# a day, and its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd clinic tests
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
: > clinic/__init__.py
cat > clinic/slots.py <<'PY'
def free_slots(day_slots, booked):
    """The slots of a day that nobody booked, in their order."""
    return [slot for slot in day_slots if slot not in booked]
PY
cat > tests/test_slots.py <<'PY'
from clinic.slots import free_slots


def test_a_booked_slot_is_not_free():
    assert free_slots(["09:00", "09:30"], {"09:00"}) == ["09:30"]
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: free slots"
