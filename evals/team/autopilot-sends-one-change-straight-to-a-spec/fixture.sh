#!/usr/bin/env bash
set -euo pipefail
# A small shop that uses aidd, with product code, so autopilot's path is not the MVP. The chat request holds one change.
# The config makes the shop's code an area that routes normal, so `aidd risk --paths` on the change gives normal, and
# autopilot writes its Spec with no Intent, and saves no request file. The role subagents write the files inside the workspace, which the case lets them do. The files are ours and are written
# only inside the case's workspace.
mkdir -p .aidd shop tests
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]

risks:
  areas:
    shop: {paths: ["shop/**"], route: normal}
YAML
cat > shop/orders.py <<'PY'
"""The shop's orders: what a customer bought, and its total."""


def total(lines: list[tuple[str, int, int]]) -> int:
    """The order's total in cents, from (item, quantity, unit price in cents) lines."""
    return sum(quantity * price for _, quantity, price in lines)
PY
cat > tests/test_orders.py <<'PY'
import unittest

from shop.orders import total


class TotalTests(unittest.TestCase):
    def test_the_total_sums_each_line(self):
        self.assertEqual(total([("tea", 2, 450), ("cup", 1, 1200)]), 2100)


if __name__ == "__main__":
    unittest.main()
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "feat: the order total"
