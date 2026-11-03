"""Timestamps: now in UTC to the second, and an ISO 8601 date or time parsed leniently."""

from __future__ import annotations

import datetime as dt

# The sort key for a missing timestamp: sorts first, never raises.
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


def utc_stamp() -> str:
    """Now, in UTC, to the second: `2026-09-28T10:00:00Z`."""
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        t = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


def parse_date(value: object) -> dt.date | None:
    """The day `value` names: a date (`2026-10-12`), or the day of a timestamp (`2026-10-12T09:30:00Z`, a datetime);
    None for anything else. The one date reader: the waivers, upkeep, the rollups, and the derived status all use it."""
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
