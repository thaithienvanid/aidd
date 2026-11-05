"""`aidd eval compare A.jsonl B.jsonl`: two recorded variants of one suite, the difference in mean pass@1 with a 95% interval, and a plain verdict.

The interval is a paired bootstrap over the cases both runs scored, with a fixed seed, so the same two files give the
same answer. The case is the sampling unit. A run with a small K (trials per case) also carries run-to-run noise that a
resample of cases cannot see, so the verdict never calls a difference firm until both runs have K of MIN_REPEAT or more.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from aidd.evals import records

MIN_COMPARE_CASES = 10  # fewer shared cases than this and the interval says too little to read
MIN_REPEAT = 3  # fewer trials per case than this and a difference is only a lead
MAX_SIGN_P = 0.05  # a firm difference also needs an exact two-sided sign test below this
RESAMPLES = 10_000
SEED = "aidd-eval-compare-1"


def paired_interval(differences: list[float]) -> tuple[float, float]:
    """The 95% percentile-bootstrap interval of the mean of `differences`, resampling the cases with a fixed seed."""
    rng = random.Random(SEED)
    n = len(differences)
    means = sorted(sum(differences[int(rng.random() * n)] for _ in range(n)) / n for _ in range(RESAMPLES))
    return means[int(RESAMPLES * 0.025)], means[int(RESAMPLES * 0.975) - 1]


def sign_test_p(better: int, worse: int) -> float:
    """The exact two-sided sign test on the cases that differ: how often a fair coin splits `better` and `worse` this unevenly or more."""
    n = better + worse
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(better, worse) + 1)) / 2**n) if n else 1.0


def verdict(cases: int, low: float, high: float, repeat: int, signs: tuple[int, int]) -> str:
    """What the interval allows one to say, in plain words. `repeat` is the smaller K of the two runs, and `signs` counts
    the cases B did better on and the cases B did worse on."""
    if cases < MIN_COMPARE_CASES:
        return f"Too few shared cases to say anything: {cases}, and this needs at least {MIN_COMPARE_CASES}. Run both variants on more cases."
    if low > 0 or high < 0:
        better = "B is better than A" if low > 0 else "B is worse than A"
        if repeat < MIN_REPEAT:
            return f"The interval leaves 0, which hints that {better}. K is only {repeat}, so run noise is not counted. Treat it as a lead, and rerun both with --repeat {MIN_REPEAT} or more."
        p = sign_test_p(*signs)
        if p >= MAX_SIGN_P:
            return (
                f"The interval leaves 0, but B did better on {signs[0]} cases and worse on {signs[1]}, and an exact sign test gives p={p:.2f}, "
                "which luck can explain. No firm difference yet: add cases."
            )
        return f"{better}: the interval stays on one side of 0, and the sign test agrees (p={p:.3f})."
    return "No difference the data can show: the interval holds 0. A small difference would need more cases or repeats to appear."


def _latest(path: Path) -> dict:
    runs = records.load_records([path])
    if not runs:
        raise ValueError(f"{path} holds no recorded run: write one with --record")
    return runs[-1]


def _label(name: str, run: dict) -> str:
    return f"{name}: {run['suite']}, model {run.get('model') or '(not given)'}, {run['date']}, K={run.get('repeat', 1)}, {len(run.get('scenarios', []))} cases"


def compare_runs(path_a: Path, path_b: Path) -> str:
    """The comparison of the latest run in each file, as the text `aidd eval compare` prints."""
    if path_a.resolve() == path_b.resolve():
        raise ValueError(f"{path_a} is named twice, which compares a run with itself: record each variant to its own file with --record, then name both")
    a, b = _latest(path_a), _latest(path_b)
    if a["suite"] != b["suite"]:
        raise ValueError(f"compare takes two runs of one suite: {path_a} is {a['suite']}, {path_b} is {b['suite']}")
    score_a = {s["id"]: s["pass_at_1"] for s in a.get("scenarios", [])}
    score_b = {s["id"]: s["pass_at_1"] for s in b.get("scenarios", [])}
    shared = sorted(score_a.keys() & score_b.keys())
    if not shared:
        raise ValueError("the two runs share no case id, so there is nothing to pair: compare runs of the same cases")
    differences = [score_b[i] - score_a[i] for i in shared]
    mean_a, mean_b = (sum(s[i] for i in shared) / len(shared) for s in (score_a, score_b))
    low, high = paired_interval(differences)
    signs = (sum(d > 0 for d in differences), sum(d < 0 for d in differences))
    lines = [_label("A", a), _label("B", b)]
    if len(shared) != len(score_a) or len(shared) != len(score_b):
        lines.append(f"Only {len(shared)} case ids are in both runs; the comparison uses those.")
    lines += [
        f"mean pass@1 on the shared cases: A {mean_a:.1%}, B {mean_b:.1%}",
        f"difference B - A: {(mean_b - mean_a) * 100:+.1f} points (95% interval {low * 100:+.1f} to {high * 100:+.1f}), paired over {len(shared)} cases",
        "verdict: " + verdict(len(shared), low, high, min(a.get("repeat", 1), b.get("repeat", 1)), signs),
    ]
    return "\n".join(lines)
