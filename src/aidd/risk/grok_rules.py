"""Grok Build's ask rules in `.grok/config.toml`, written as one block aidd marks, and read back before and after: aidd leaves the
file alone when the person's part does not parse, when it sets `permission` itself (one table per file), or when the block
was changed, and says why and what to do."""

from __future__ import annotations

import json
import tomllib

TOML_BEGIN = "# >>> aidd: the ask rules aidd writes from the risk rules. `aidd upgrade` rewrites this block."
TOML_END = "# <<< aidd"


def block_text(entries: list[str]) -> str:
    return f"{TOML_BEGIN}\n[permission]\nask = {json.dumps(entries)}\n{TOML_END}\n"


def block_span(text: str) -> tuple[int, int] | None:
    start = text.find(TOML_BEGIN)
    end = text.find(TOML_END, start)
    return (start, end + len(TOML_END) + (1 if text[end + len(TOML_END) : end + len(TOML_END) + 1] == "\n" else 0)) if start >= 0 and end >= 0 else None


def conflict(outside: str, block: str | None, before: set[str]) -> str | None:
    """Why aidd must leave `.grok/config.toml` alone, or None: the person's part does not parse, it sets `permission`
    itself (one table per file), or they changed aidd's block."""
    try:
        theirs = tomllib.loads(outside)
    except tomllib.TOMLDecodeError as exc:
        return f"it does not parse ({exc})"
    if "permission" in theirs:
        return "it has a `permission` table of its own"
    if block is not None:
        try:
            ours = tomllib.loads(block)
        except tomllib.TOMLDecodeError:
            return "aidd's block in it was changed"
        ask = ours.get("permission", {}).get("ask") if isinstance(ours.get("permission"), dict) else None
        if ours != {"permission": {"ask": ask}} or not isinstance(ask, list) or not all(isinstance(a, str) for a in ask) or set(ask) != before:
            return "aidd's block in it was changed"
    return None


def whole(text: str, span: tuple[int, int] | None) -> str | None:
    """Why the whole `.grok/config.toml` stops aidd, or None: it must parse, and its `permission` table must be exactly
    aidd's block, so no line of the person's after the block reads as part of it."""
    if span is None:
        return None
    try:
        whole = tomllib.loads(text)
        block = tomllib.loads(text[span[0] : span[1]])
    except tomllib.TOMLDecodeError as exc:
        return f"it does not parse ({exc})"
    return None if whole.get("permission") == block.get("permission") else "its `permission` table holds more than aidd's block"


def merged(text: str, entries: list[str], before: set[str], rel: str) -> tuple[str, str | None]:
    """`.grok/config.toml` as it reads once aidd's block holds `entries`, and None; or its text as it is, and why aidd keeps it."""
    span = block_span(text)
    outside = text if span is None else text[: span[0]] + text[span[1] :]
    why = conflict(outside, text[span[0] : span[1]] if span else None, before) or whole(text, span)
    if why:
        return text, f"kept     {rel} ({why}; add aidd's ask rules by hand: `aidd risk --list`)"
    block = block_text(entries)
    new_text = (text[: span[0]] + block + text[span[1] :]) if span else (text.rstrip("\n") + ("\n\n" if text.strip() else "") + block)
    try:
        parsed = tomllib.loads(new_text)
        expected = tomllib.loads(outside) | {"permission": {"ask": entries}}
    except tomllib.TOMLDecodeError as exc:
        return text, f"kept     {rel} (aidd's block would not parse there: {exc})"
    if parsed != expected:
        return text, f"kept     {rel} (aidd's block would change how the rest of it reads)"
    return new_text, None


def without_block(text: str, entries: set[str]) -> tuple[str | None, str | None]:
    """`.grok/config.toml` without aidd's block, and why aidd must keep it as it is (None when it may remove the block).
    (None, None) when the file holds no block."""
    found = block_span(text)
    if found is None:
        return None, None
    rest = text[: found[0]].rstrip("\n") + ("\n" if text[: found[0]].strip() else "") + text[found[1] :]
    why = conflict("", text[found[0] : found[1]], entries) or whole(text, found)
    if not why:
        try:
            if tomllib.loads(rest) != {k: v for k, v in tomllib.loads(text).items() if k != "permission"}:
                why = "taking aidd's block out would change how the rest of it reads"
        except tomllib.TOMLDecodeError:
            why = "taking aidd's block out would leave it unparsable"
    return rest, why
