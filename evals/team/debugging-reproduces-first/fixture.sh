#!/usr/bin/env bash
set -euo pipefail
# The workspace the prompt describes: the buggy pricing module, so the agent can reproduce the bug before fixing it,
# in a repository that uses aidd. Without the minimal config the aidd skill asks whether to apply aidd, and no practice skill
# loads. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > pricing.py <<'PY'
BULK_THRESHOLD = 10
BULK_RATE = 0.10


def order_total(quantity: int, unit_price: float) -> float:
    subtotal = quantity * unit_price
    if quantity > BULK_THRESHOLD:
        subtotal -= subtotal * BULK_RATE
    return round(subtotal, 2)
PY
