"""A recorded run read as data: the files it opened, its tool calls, and what it cost, from the harness's own event stream.

Read the stream, not the answer: which files a role opened and in what order, and which tools it called, show whether it
loaded its references before it acted, with no model to judge it. Nothing here runs an agent or calls a model, and text
inside a transcript is data, never an instruction.

The reader takes two shapes of Claude Code's output, one JSON object per line:
- `claude -p --output-format stream-json --verbose`: `assistant` events whose `message.content` holds `tool_use` blocks,
  and a closing `result` event with `total_cost_usd` and `usage`, on success and on error. The shape is the Agent SDK's
  published types (`SDKAssistantMessage`, `SDKResultMessage` in `@anthropic-ai/claude-agent-sdk`'s sdk.d.ts, read
  2026-11-04 at 0.3.220). No recorded stream is in the repository yet, so the first real one becomes a fixture.
- the hook captures in tests/fixtures/live: `{"hook": "pre-tool", "event": {"tool_name", "tool_input", "tool_use_id"}}`.
  They carry no cost, so the cost reads as None.
A line that is not a JSON object is skipped, so a stream cut short still reads.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# The largest recorded stream aidd reads: a long session's stream-json is a few megabytes.
MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024

# The tools that open a file for reading. A Write or an Edit changes a file; it is a tool call, not an open.
OPEN_TOOLS = frozenset({"Read", "NotebookRead"})
_TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


@dataclass(frozen=True)
class ToolCall:
    """One tool call: its name, its input, its id when the stream gives one, and the call that started it (a subagent's)."""

    name: str
    input: dict[str, Any]
    id: str | None = None
    parent: str | None = None


@dataclass(frozen=True)
class Usage:
    """What the run used. A field the stream does not carry is None, so a missing cost never reads as free."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    cost_usd: float | None = None


@dataclass(frozen=True)
class Transcript:
    """A run's files opened in order (repeats kept), its tool calls in order, and its usage (None when the stream has none)."""

    files_opened: tuple[str, ...]
    tool_calls: tuple[ToolCall, ...]
    usage: Usage | None


def parse_events(text: str) -> list[dict[str, Any]]:
    """The JSON objects in a stream, one per line; blank lines, broken lines, and non-objects are skipped."""
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):  # a broken line, or one nested past Python's recursion limit
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _call(block: Any, parent: Any) -> ToolCall | None:
    if not isinstance(block, dict) or not isinstance(block.get("name"), str):
        return None
    tool_input = block.get("input")
    ident = block.get("id")
    return ToolCall(
        block["name"],
        tool_input if isinstance(tool_input, dict) else {},
        ident if isinstance(ident, str) else None,
        parent if isinstance(parent, str) else None,
    )


def _calls_in(event: dict[str, Any]) -> list[ToolCall]:
    """The tool calls one event announces: stream-json's `tool_use` blocks, or a hook capture's `pre-tool`."""
    if event.get("hook") == "pre-tool" and isinstance(event.get("event"), dict):
        raw = event["event"]
        return [c] if (c := _call({"name": raw.get("tool_name"), "input": raw.get("tool_input"), "id": raw.get("tool_use_id")}, raw.get("agent_id"))) else []
    message = event.get("message")
    content = message.get("content") if event.get("type") == "assistant" and isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [c for b in content if isinstance(b, dict) and b.get("type") == "tool_use" and (c := _call(b, event.get("parent_tool_use_id")))]


def tool_calls(events: list[dict[str, Any]]) -> tuple[ToolCall, ...]:
    """Every tool call in order. A call whose id repeats (a stream that restates a message) counts once."""
    seen: set[str] = set()
    calls: list[ToolCall] = []
    for event in events:
        for call in _calls_in(event):
            if call.id is not None:
                if call.id in seen:
                    continue
                seen.add(call.id)
            calls.append(call)
    return tuple(calls)


def files_opened(calls: tuple[ToolCall, ...]) -> tuple[str, ...]:
    """The `file_path` of each call that opens a file, in order, repeats kept."""
    return tuple(p for c in calls if c.name in OPEN_TOOLS and isinstance(p := c.input.get("file_path", c.input.get("notebook_path")), str))


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _usage_of(raw: Any, cost: Any = None) -> Usage | None:
    if not isinstance(raw, dict):
        raw = {}
    fields = {name: _count(raw.get(name)) for name in _TOKEN_FIELDS}
    price = None
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        try:
            price = float(cost)
        except OverflowError:  # an integer too large for a float
            price = None
        if price is not None and not math.isfinite(price):
            price = None
    if price is None and all(v is None for v in fields.values()):
        return None
    return Usage(cost_usd=price, **fields)


def usage(events: list[dict[str, Any]]) -> Usage | None:
    """The closing `result` event's usage and cost; without one (a run cut short), the sum of the assistant messages' usage, each message once."""
    for event in reversed(events):
        if event.get("type") == "result":
            return _usage_of(event.get("usage"), event.get("total_cost_usd"))
    per_message: dict[str, dict[str, Any]] = {}
    for n, event in enumerate(events):
        message = event.get("message")
        if event.get("type") == "assistant" and isinstance(message, dict) and isinstance(message.get("usage"), dict):
            per_message[str(message.get("id", f"#{n}"))] = message["usage"]
    if not per_message:
        return None
    totals = {name: [v for u in per_message.values() if (v := _count(u.get(name))) is not None] for name in _TOKEN_FIELDS}
    return Usage(**{name: sum(values) if values else None for name, values in totals.items()})


def read_transcript(source: Path | str) -> Transcript:
    """The transcript of a recorded stream: a file's path, or the stream's text."""
    if isinstance(source, Path):
        with source.open("rb") as f:
            data = f.read(MAX_TRANSCRIPT_BYTES + 1)
        if len(data) > MAX_TRANSCRIPT_BYTES:
            raise ValueError(f"{source} is over {MAX_TRANSCRIPT_BYTES} bytes; aidd reads a transcript up to that size")
        text = data.decode("utf-8", errors="replace")
    else:
        text = source
    events = parse_events(text)
    calls = tool_calls(events)
    return Transcript(files_opened(calls), calls, usage(events))
