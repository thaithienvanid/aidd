"""`AIDD_HOOK_CAPTURE`: each hook appends the raw event it got, then decides as it always does.

The copy is what a live check compares the dialect against, so it must be the event exactly as the harness sent it,
and it must never change the decision. The file can hold a prompt, so it is the person's: 0600, never through a link,
and capped.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, make_repo

from aidd.guard import hook_capture


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name).resolve()
        self.file = self.dir / "events.jsonl"

    def capture(self, raw: str, target: str | None = None) -> None:
        with mock.patch.dict(os.environ, {hook_capture.ENV: target if target is not None else str(self.file)}):
            hook_capture.keep("pre-tool", raw)

    def test_unset_writes_nothing(self):
        with mock.patch.dict(os.environ, {hook_capture.ENV: ""}):
            hook_capture.keep("pre-tool", '{"a": 1}')
        self.assertFalse(self.file.exists())

    def test_the_event_is_kept_as_it_came(self):
        raw = '{"tool_name": "Write", "tool_input": {"file_path": "x"}}'
        self.capture(raw)
        self.capture("not json")
        lines = [json.loads(ln) for ln in self.file.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([ln["event"] for ln in lines], [json.loads(raw), "not json"])
        self.assertEqual({ln["hook"] for ln in lines}, {"pre-tool"})
        self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o600)

    def test_a_loose_file_is_made_private(self):
        self.file.write_text("", encoding="utf-8")
        self.file.chmod(0o644)
        self.capture("{}")
        self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o600)

    def test_a_link_a_pipe_a_relative_path_and_a_full_file_take_no_copy(self):
        elsewhere = self.dir / "elsewhere.txt"
        elsewhere.write_text("", encoding="utf-8")
        link = self.dir / "link.jsonl"
        link.symlink_to(elsewhere)
        self.capture("{}", str(link))
        self.assertEqual(elsewhere.read_text(encoding="utf-8"), "")
        if hasattr(os, "mkfifo"):
            pipe = self.dir / "pipe"
            os.mkfifo(pipe)
            self.capture("{}", str(pipe))  # returns at once: a pipe with no reader never holds the hook
        self.capture("{}", "events.jsonl")
        self.assertFalse(Path("events.jsonl").exists())
        self.file.write_bytes(b"x" * hook_capture.MAX_BYTES)
        self.capture("{}")
        self.assertEqual(self.file.stat().st_size, hook_capture.MAX_BYTES)

    def test_the_hook_decides_as_it_does_without_it(self):
        """Through `aidd hook pre-tool`: the same answer with and without the copy, and the copy holds the event."""
        root = make_repo(self.dir / "repo", "team")
        event = json.dumps(
            {"session_id": "s-cap", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "Write",
             "tool_input": {"file_path": str(root / ".git" / "config"), "content": "x"}}
        )  # fmt: skip
        plain = aidd_subprocess("hook", "pre-tool", cwd=root, input=event, env={k: v for k, v in os.environ.items() if k != hook_capture.ENV})
        captured = aidd_subprocess("hook", "pre-tool", cwd=root, input=event, env={**os.environ, hook_capture.ENV: str(self.file)})
        self.assertIn('"deny"', plain.stdout)
        self.assertEqual(captured.stdout, plain.stdout)
        self.assertEqual(json.loads(self.file.read_text(encoding="utf-8"))["event"], json.loads(event))


if __name__ == "__main__":
    unittest.main()
