"""Timestamps: now in UTC to the second, and an ISO 8601 date or time parsed leniently."""

from __future__ import annotations

import datetime as dt

UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_stamp(at: dt.datetime | None = None) -> str:
    """`at` (now when none), in UTC, to the second: `2026-09-28T10:00:00Z`. A datetime with no zone reads as UTC already."""
    at = dt.datetime.now(dt.UTC) if at is None else at
    return (at.astimezone(dt.UTC) if at.tzinfo else at).strftime(UTC_FORMAT)


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
    None for anything else. It reads leniently, for the waivers, upkeep, the rollups, and the derived status. A check that must
    refuse a timestamp reads `YYYY-MM-DD` strictly, with `date.fromisoformat`."""
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
