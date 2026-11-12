#!/usr/bin/env bash
set -euo pipefail
# A checkout service in a repository that uses aidd, with two commits: the release before and release 2026.09.28.3,
# which changed the tax calculation. The new code fails on a region that has no rate. The files are ours and are written
# only inside the case's workspace.
mkdir -p .aidd checkout
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
touch checkout/__init__.py
cat > checkout/tax.py <<'PY'
"""The tax on an order."""

RATES = {"north": 0.05, "south": 0.07}


def tax_cents(subtotal_cents, region):
    return round(subtotal_cents * RATES.get(region, 0.0))
PY
cat > CHANGELOG.md <<'MD'
# Changelog

## 2026.09.28.2

- Show the tax line on the cart.
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "release 2026.09.28.2"
cat > checkout/tax.py <<'PY'
"""The tax on an order."""

RATES = {"north": 0.05, "south": 0.07}


def tax_cents(subtotal_cents, region):
    return round(subtotal_cents * RATES[region])
PY
cat > CHANGELOG.md <<'MD'
# Changelog

## 2026.09.28.3

- Change the tax calculation to read the rate for the region directly.

## 2026.09.28.2

- Show the tax line on the cart.
MD
git add -A
git commit -q -m "release 2026.09.28.3: change the tax calculation"
git tag release-2026.09.28.3
