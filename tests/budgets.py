"""The size budgets the agent-facing text keeps (AGENTS.md, Rules: a feature pays for its own bytes). A budget holds
with HEADROOM over its cap, so a fix a few bytes over never stops a change; past it, the change makes room by tightening
other words, and a cap rises only with a reason."""

HEADROOM = 1.03


def within(size: float, cap: float) -> bool:
    """Whether `size` keeps to `cap`, with HEADROOM."""
    return size <= cap * HEADROOM
