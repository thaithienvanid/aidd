"""Control bands: deterministic detection that closes the loop after release.

A metric with a stable baseline (a CI failure rate, a post-deploy 5xx rate, PR cycle time) is judged
against the mean and standard deviation of its recent history, with the Western Electric rules for
spikes and slow drift. No model is involved: the tier decides what an agent may do next, and a
breach becomes a draft Spec that a person triages (fix now, schedule, or dismiss).

Tiers, the playbook's 1-2-3 sigma ladder:
- ok: within one standard deviation, no drift rule;
- log: beyond 1 sigma; record it, act on nothing;
- diagnose: beyond `diagnose_sigma` (2), or a drift rule; an agent may investigate read-only;
- propose: beyond `propose_sigma` (3); an agent may open a pull request or run a pre-approved runbook,
  which still passes the gate like any change.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path

MIN_BASELINE = 8


@dataclass(frozen=True)
class Band:
    metric: str
    window: int = 30
    diagnose_sigma: float = 2.0
    propose_sigma: float = 3.0


@dataclass
class Reading:
    metric: str
    tier: str
    latest: float | None = None
    mean: float | None = None
    std: float | None = None
    sigma: float | None = None
    rules: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def load_series(path: Path) -> list[float]:
    """Values, oldest first, from JSON lines (`{"ts", "value"}`), CSV (`ts,value` or `value`), or one number per line."""
    values: list[float] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            values.append(float(json.loads(line)["value"]))
            continue
        cell = line.split(",")[-1].strip()
        try:
            values.append(float(cell))
        except ValueError:
            continue  # a CSV header
    return values


def _z(value: float, mean: float, std: float) -> float:
    if std == 0:
        return 0.0 if value == mean else float("inf") if value > mean else float("-inf")
    return (value - mean) / std


def western_electric(recent: list[float], mean: float, std: float) -> list[str]:
    """The rules the newest points break, judged against the baseline (the newest point is last)."""
    z = [_z(v, mean, std) for v in recent]
    rules = []
    if z and abs(z[-1]) >= 3:
        rules.append("1: one point beyond 3 sigma")
    for side in (1, -1):
        if len(z) >= 3 and sum(1 for x in z[-3:] if side * x >= 2) >= 2 and side * z[-1] >= 2:
            rules.append("2: two of three points beyond 2 sigma on one side")
        if len(z) >= 5 and sum(1 for x in z[-5:] if side * x >= 1) >= 4 and side * z[-1] >= 1:
            rules.append("3: four of five points beyond 1 sigma on one side")
        if len(z) >= 8 and all(side * x > 0 for x in z[-8:]):
            rules.append("4: eight points in a row on one side of the mean")
    return rules


def assess(values: list[float], band: Band) -> Reading:
    """The tier of the newest value against the `window` values before it."""
    if len(values) < MIN_BASELINE + 1:
        return Reading(band.metric, "ok", note=f"not enough history: {len(values)} value(s), need {MIN_BASELINE + 1}")
    history, latest = values[:-1][-band.window :], values[-1]
    mean, std = statistics.fmean(history), statistics.pstdev(history)
    # The drift rules look at the newest points against the baseline taken before them.
    recent = values[-8:]
    sigma = _z(latest, mean, std)
    rules = western_electric(recent, mean, std)
    if abs(sigma) >= band.propose_sigma:
        tier = "propose"
    elif abs(sigma) >= band.diagnose_sigma or any(not r.startswith("1:") for r in rules):
        tier = "diagnose"
    elif abs(sigma) >= 1:
        tier = "log"
    else:
        tier = "ok"
    return Reading(band.metric, tier, latest, round(mean, 6), round(std, 6), round(sigma, 3) if abs(sigma) != float("inf") else sigma, rules)


def band_from_config(cfg, metric: str) -> Band:
    """The configured band for `metric` (config `[[observe.bands]]`), or the defaults."""
    for entry in cfg.get("observe", "bands", default=[]) if cfg else []:
        if entry.get("metric") == metric:
            return Band(metric, entry.get("window", 30), entry.get("diagnose_sigma", 2.0), entry.get("propose_sigma", 3.0))
    return Band(metric)


def intent_text(r: Reading, source: str, goal: str | None = None) -> str:
    """The body section a breach writes into its draft Spec: the evidence, in words a triager can act on."""
    rules = "\n".join(f"- rule {x}" for x in r.rules) or "- none; the value alone crossed the band"
    return (
        "## Observed anomaly\n\n"
        f"`{r.metric}` is {r.latest} against a baseline mean of {r.mean} (standard deviation {r.std}): "
        f"{r.sigma} sigma, tier `{r.tier}`. Detected by `aidd watch` from `{source}`; no model was involved.\n\n"
        f"Control rules broken:\n{rules}\n\n"
        "Triage: the service owner decides to fix now, schedule, or dismiss. A dismissal is a reason to tune the band, not to "
        "delete this file silently. A fix goes through the loop like any change, and the incident class gets a regression test.\n"
        + (f"\nThe team's goal, to weigh the priority against: {goal}\n" if goal else "")
    )
