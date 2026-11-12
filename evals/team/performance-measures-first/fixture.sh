#!/usr/bin/env bash
set -euo pipefail
# The orders page from the prompt over a small in-memory stand-in for the ORM that counts its queries, so the agent
# can measure a baseline (queries per page as orders grow) before it changes anything. Rendering the page writes
# baseline.log only while orders.py is as first committed, so the file proves a baseline run came before any edit.
cat > db.py <<'PY'
"""An in-memory stand-in for the ORM: every attribute that would hit the database counts one query."""

import subprocess
from pathlib import Path

QUERIES = {"count": 0}


def query() -> None:
    QUERIES["count"] += 1


class Items:
    def __init__(self, n: int):
        self._n = n

    def count(self) -> int:
        query()
        return self._n


class Customer:
    def __init__(self, name: str):
        self.name = name


class Order:
    def __init__(self, oid: int, account: str):
        self.id, self.account, self.total, self.created_at = oid, account, 10.0 * oid, oid
        self._customer = Customer(f"customer {oid}")
        self._items = Items(oid % 5 + 1)

    @property
    def customer(self) -> Customer:
        query()
        return self._customer

    @property
    def items(self) -> Items:
        return self._items


class Manager:
    rows: list = []

    def filter(self, account: str) -> "Query":
        return Query([o for o in self.rows if o.account == account])


class Query(list):
    def order_by(self, key: str) -> "Query":
        query()
        return Query(sorted(self, key=lambda o: o.created_at, reverse=key.startswith("-")))


Order.objects = Manager()


def seed(account: str, n: int) -> None:
    Order.objects.rows = [Order(i, account) for i in range(1, n + 1)]


def log_baseline() -> None:
    """Write baseline.log while orders.py is as first committed: proof that a run measured the page before any edit to it."""
    here = Path(__file__).parent
    git = lambda *args: subprocess.run(["git", *args], cwd=here, capture_output=True, text=True)  # noqa: E731
    root = git("rev-list", "--max-parents=0", "HEAD").stdout.split()
    if root and git("diff", "--quiet", root[0], "--", "orders.py").returncode == 0:
        with open(here / "baseline.log", "a", encoding="utf-8") as log:
            log.write(f"queries={QUERIES['count']}\n")


def render(request, template: str, context: dict) -> dict:
    log_baseline()
    return context
PY
cat > orders.py <<'PY'
from db import Order, render


def orders_page(request):
    orders = Order.objects.filter(account=request.account).order_by("-created_at")
    rows = []
    for order in orders:
        rows.append({
            "id": order.id,
            "customer": order.customer.name,
            "items": order.items.count(),
            "total": order.total,
        })
    return render(request, "orders.html", {"rows": rows})
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "feat: the orders page"
