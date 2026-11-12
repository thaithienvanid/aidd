"""`aidd status` shows each running role and its last status line, from `.aidd/tmp/roles/<role name>.log`, and nothing when
there is no such file. The invariant: a role is shown exactly when its file is a regular file whose last line does not start
with `DONE`; its line is a role's text, so it is shown on one line and cut to a length; nothing else is read or started."""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from helpers import make_repo, run_cli

from aidd.cli import mcp_server
from aidd.kernel import json_schema
from aidd.workitems import role_status


def roles_dir(root: Path) -> Path:
    path = root / ".aidd" / "tmp" / "roles"
    path.mkdir(parents=True, exist_ok=True)
    return path


class RunningRoles(unittest.TestCase):
    def test_a_role_shows_while_its_last_line_is_not_done(self):
        cases = {  # file name -> (text, shown)
            "developer.log": ("10:01 Implement: aidd test --changed\n", True),
            "verifier.log": ("10:01 Verify: start\n10:30 Verify: the suite\n", True),
            "reviewer.log": ("10:01 Review: start\nDONE 3f2c1a9\n", False),
            "sre.log": ("10:01 start\nDONE none\n\n", False),  # a blank line after DONE changes nothing
            "empty.log": ("", False),
            "notes.txt": ("10:01 not a status file\n", False),
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = roles_dir(root)
            for name, (text, _) in cases.items():
                (folder / name).write_text(text, encoding="utf-8")
            (folder / "a-folder.log").mkdir()
            os.symlink(folder / "developer.log", folder / "a-link.log")
            now = time.time()
            os.utime(folder / "verifier.log", (now - 17 * 60, now - 17 * 60))
            shown = {r["name"]: r for r in role_status.running_roles(root, now=now)}
        self.assertEqual(sorted(shown), ["developer", "verifier"])
        self.assertEqual(shown["verifier"]["last_line"], "10:30 Verify: the suite")
        self.assertEqual(shown["verifier"]["quiet_minutes"], 17)

    def test_no_folder_no_file_or_a_link_in_its_place_shows_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            root.mkdir()
            self.assertEqual(role_status.running_roles(root), [])
            self.assertEqual(role_status.running_roles_text([]), "")
            (Path(d) / "elsewhere").mkdir()
            (Path(d) / "elsewhere" / "developer.log").write_text("10:01 x\n", encoding="utf-8")
            (root / ".aidd" / "tmp").mkdir(parents=True)
            os.symlink(Path(d) / "elsewhere", root / ".aidd" / "tmp" / "roles")
            self.assertEqual(role_status.running_roles(root), [])

    def test_a_line_is_data_shown_on_one_line_and_cut(self):
        hostile = "10:01 Implement: \x1b[2J‮reversed\rcarriage " + "x" * 2000
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (roles_dir(root) / "developer.log").write_text(hostile + "\n", encoding="utf-8")
            (shown,) = role_status.running_roles(root)
        text = role_status.running_roles_text([shown])
        self.assertEqual(text.count("\n"), 2, "a heading and one line")
        self.assertNotIn("\x1b", text)
        self.assertNotIn("‮", text)
        self.assertNotIn("\r", text)
        self.assertLess(len(shown["last_line"]), 400)

    def test_aidd_status_shows_them_in_text_and_json_and_nothing_without_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d) / "repo", "solo", branch=None)
            here = os.getcwd()
            os.chdir(root)
            try:
                _, before = run_cli("status")
                data = json.loads(run_cli("status", "--json")[1])
                self.assertNotIn("running_roles", data)
                (roles_dir(root) / "developer.log").write_text("10:01 Implement: aidd test --changed\n", encoding="utf-8")
                _, after = run_cli("status")
                data = json.loads(run_cli("status", "--json")[1])
            finally:
                os.chdir(here)
        self.assertNotIn("running roles", before)
        self.assertIn("developer: 10:01 Implement: aidd test --changed", after)
        self.assertEqual(json_schema.validate(data, "status.schema.json"), [])
        self.assertEqual([r["name"] for r in data["running_roles"]], ["developer"])


# Secret-shaped values are joined here, so no literal of one sits in the repository.
TOKEN = "ghp_" + "a1b2c3d4e5" * 3 + "a1b2c3"
CANARY = "hunter" + "2pass"
PUSH_URL = "https://u:" + CANARY + "@example.com/r.git"
MODERN = {
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}
LINES = {  # a status line -> the values no output may hold
    "a token after a name": (f"10:00 implement: pushing with GITHUB_TOKEN={TOKEN} now", [TOKEN]),
    "a token alone": (f"10:00 implement: {TOKEN}", [TOKEN]),
    "a canary in a URL": (f"10:00 implement: git push {PUSH_URL}", [CANARY]),
    "both": (f"10:00 implement: pushing with {TOKEN} and {PUSH_URL}", [TOKEN, CANARY]),
    "a token the 300-character cut would split": ("10:00 " + "x" * 280 + f" {TOKEN}", [TOKEN, TOKEN[:20]]),
    "a token after an escape sequence": (f"10:00 \x1b[2J\u202e{TOKEN}", [TOKEN, "\x1b", "\u202e"]),
}


class SecretsInAStatusLine(unittest.TestCase):
    """A role writes its status file, so its line is data that may hold a secret. The invariant: the line passes the secret
    scrub and the one-line rule where it is read, so `aidd status`, `aidd status --json`, and the MCP `status` tool all show it
    hidden."""

    def mcp_status(self, root: Path) -> str:
        out = io.StringIO()
        call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "status", "arguments": {}, "_meta": MODERN}}
        mcp_server.serve(io.StringIO(json.dumps(call) + "\n"), out, root=str(root))
        return out.getvalue()

    def test_no_output_shows_a_secret_a_role_wrote(self):
        for label, (line, hidden) in LINES.items():
            with self.subTest(line=label), tempfile.TemporaryDirectory() as d:
                root = make_repo(Path(d) / "repo", "solo", branch=None)
                (roles_dir(root) / "developer.log").write_text(line + "\n", encoding="utf-8")
                here = os.getcwd()
                os.chdir(root)
                try:
                    outputs = {
                        "the status text": run_cli("status")[1],
                        "the status json": run_cli("status", "--json")[1],
                        "the MCP status tool": self.mcp_status(root),
                    }
                finally:
                    os.chdir(here)
                shown = role_status.running_roles(root)
                self.assertEqual(len(shown), 1)
                outputs["the role's last_line"] = shown[0]["last_line"]
                for where, text in outputs.items():
                    for value in hidden:
                        self.assertNotIn(value, text, f"{where} shows {value[:6]}...")
                self.assertIn("<redacted>", shown[0]["last_line"])
                self.assertLessEqual(len(shown[0]["last_line"]), 300)

    def test_a_line_with_no_secret_shows_as_it_was(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (roles_dir(root) / "developer.log").write_text("10:01 Implement: aidd test --changed\n", encoding="utf-8")
            (shown,) = role_status.running_roles(root)
        self.assertEqual(shown["last_line"], "10:01 Implement: aidd test --changed")


if __name__ == "__main__":
    unittest.main()
