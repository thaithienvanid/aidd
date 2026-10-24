"""What a run's journal says, read for the decision: the lines of one run, what it spent, the circuit breaker, the
stall breaker, and how many times a Spec went back to a step. Pure: these read lines `lease.read_journal` gave."""

from __future__ import annotations


def spent(journal: list[dict], lease: dict) -> tuple[int, dict[str, float]]:
    """The tokens and the cost by currency the lease's run recorded (self-reported by the autopilot command)."""
    tokens, cost = 0, dict[str, float]()
    for e in run_of(journal, lease):
        tokens += int(e.get("tokens") or 0)
        if isinstance(e.get("cost"), dict):
            c = e["cost"]
            cost[c["currency"]] = cost.get(c["currency"], 0.0) + float(c["amount"])
    return tokens, cost


def run_of(journal: list[dict], lease: dict) -> list[dict]:
    """The journal lines of this lease's run."""
    return [e for e in journal if e.get("session_id") == lease["session_id"] and str(e.get("at")) >= str(lease["started_at"])]


def of(journal: list[dict], spec: str, codes: frozenset[str] | set[str] | tuple[str, ...]) -> list[dict]:
    return [e for e in journal if e.get("spec") == spec and e.get("code") in codes]


def same_head(entry: dict, head: str | None) -> bool:
    return head is None or entry.get("head") == head


def tripped(run: list[dict], spec: str | None, code: str, head: str | None = None, *, progress: bool = False) -> bool:
    """The circuit breaker: the last two times this run noted `code` for `spec`, neither moved the work on. A try that
    failed never does; with `progress`, an `ok` on the same head (the derived state unchanged) does not either. Both
    tries must be on the current head, when it is known."""
    tries = [e for e in run if e.get("code") == code and e.get("spec") == spec]

    def stuck(e: dict) -> bool:
        if head is not None and e.get("head") != head:
            return False  # a new head is progress: the breaker never trips across heads
        return e.get("result") == "fail" or (progress and e.get("result") == "ok" and head is not None)

    return len(tries) >= 2 and all(stuck(e) for e in tries[-2:])


# How many times one run sends a Spec back to the same step (`ROUNDS`) before it sets the Spec aside for a person, as
# a Task's three implementation retries do: a loop no head breaks, such as a Review that fails on every new head, or a
# Spec that stays unready however often it is specified. Specify gets one more: its first run is no return.
MAX_ROUNDS = 3
ROUNDS = {"spec.rework": "Implement", "spec.draft": "Specify"}


def rounds(run: list[dict], spec: str, code: str) -> int:
    """How many times this run noted `code` for `spec`."""
    return sum(1 for e in run if e.get("spec") == spec and e.get("code") == code)


def last_reports(run: list[dict], spec: str, count: int = 2) -> str:
    """The codes of the run's last `count` failed notes for `spec`, never their words: those are an agent's report, which
    a person reads in the handoff note, never as aidd's own words."""
    failed = [e for e in run if e.get("spec") == spec and e.get("result") == "fail"][-count:]
    return ", ".join(f"{e.get('code')} fail" for e in failed) or "none noted"


# The stall breaker, across the whole run: this many steps in a row with no progress stop it (the circuit breaker
# sets one step aside after two; this catches a run that goes round between steps or between Specs).
STALL_TURNS = 6


def stalled(run: list[dict]) -> bool:
    """Whether the run's last STALL_TURNS notes moved nothing on: each failed, or was an `ok` for a step (its code, Spec,
    and head) the run had already done. A merge, a first `ok` of a step on a head, or a plan is progress."""
    if len(run) < STALL_TURNS:
        return False
    done = {(e.get("code"), e.get("spec"), e.get("head")) for e in run[:-STALL_TURNS] if e.get("result") == "ok"}
    for e in run[-STALL_TURNS:]:
        key = (e.get("code"), e.get("spec"), e.get("head"))
        if e.get("merged") or (e.get("result") == "ok" and key not in done):
            return False
        if e.get("result") == "ok":
            done.add(key)
    return True
