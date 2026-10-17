"""`aidd mcp` is a dual-era MCP server (https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning):
a request whose `_meta` names the 2026-07-28 revision is served on its own, an `initialize` selects a legacy revision
(2025-11-25 or 2025-06-18) for the process, a request that names neither era is refused with -32602, and a revision it
does not speak is refused the way each era says."""

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd.cli import mcp_protocol, mcp_server
from aidd.setup import adoption

MODERN = "2026-07-28"


def meta(version: str = MODERN, **extra) -> dict:
    return {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientInfo": {"name": "test-client", "version": "1.0.0"},
        "io.modelcontextprotocol/clientCapabilities": {},
        **extra,
    }


@unittest.skipUnless(shutil.which("git"), "git is required")
class DualEraServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=[]))

    def serve(self, *messages) -> dict:
        """The replies of one stdio process, by request id."""
        out = io.StringIO()
        mcp_server.serve(io.StringIO("".join(json.dumps(m) + "\n" for m in messages)), out, root=str(self.root))
        return {r["id"]: r for r in map(json.loads, out.getvalue().splitlines())}

    def test_a_modern_client_discovers_lists_and_calls_with_meta(self):
        replies = self.serve(
            {"jsonrpc": "2.0", "id": "d", "method": "server/discover", "params": {"_meta": meta()}},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta()}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "check_edit", "arguments": {"path": ".aidd/config.yaml"}, "_meta": meta()}},
        )
        discover = replies["d"]["result"]
        self.assertEqual(discover["resultType"], "complete")
        self.assertIn(MODERN, discover["supportedVersions"])
        self.assertEqual(discover["supportedVersions"][0], MODERN)
        self.assertIn("tools", discover["capabilities"])
        self.assertEqual(discover["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "aidd")
        self.assertIsInstance(discover["ttlMs"], int)
        self.assertIn(discover["cacheScope"], ("public", "private"))
        listed = replies[1]["result"]
        self.assertEqual(listed["resultType"], "complete")
        self.assertIn("check_edit", [t["name"] for t in listed["tools"]])
        self.assertIsInstance(listed["ttlMs"], int)
        self.assertIn(listed["cacheScope"], ("public", "private"))
        self.assertEqual(listed["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "aidd")
        called = replies[2]["result"]
        self.assertEqual(called["resultType"], "complete")
        self.assertFalse(called["isError"])
        self.assertTrue(called["content"][0]["text"].startswith("deny"))
        # The order is the same each time, so a client can cache the list.
        again = self.serve({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta()}})
        self.assertEqual([t["name"] for t in again[1]["result"]["tools"]], [t["name"] for t in listed["tools"]])

    def test_an_unknown_modern_version_gets_32022_with_the_supported_ones(self):
        replies = self.serve({"jsonrpc": "2.0", "id": 7, "method": "tools/list", "params": {"_meta": meta("1900-01-01")}})
        error = replies[7]["error"]
        self.assertEqual(error["code"], -32022)
        self.assertEqual(error["data"]["requested"], "1900-01-01")
        self.assertEqual(error["data"]["supported"], list(mcp_protocol.SUPPORTED))
        self.assertIn(MODERN, error["data"]["supported"])

    def test_a_modern_request_without_its_capabilities_is_malformed(self):
        broken = {"io.modelcontextprotocol/protocolVersion": MODERN}
        replies = self.serve(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": broken}},
            {"jsonrpc": "2.0", "id": 2, "method": "server/discover", "params": {}},
        )
        self.assertEqual(replies[1]["error"]["code"], -32602)
        self.assertEqual(replies[2]["error"]["code"], -32602)

    def test_methods_the_modern_revision_removed_are_not_found(self):
        replies = self.serve({"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"_meta": meta()}})
        self.assertEqual(replies[1]["error"]["code"], -32601)

    def legacy_flow(self, version: str) -> dict:
        return self.serve(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "c", "version": "1"}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "check_edit", "arguments": {"path": ".aidd/config.yaml"}}},
        )

    def test_a_legacy_2025_11_25_client_initializes_and_works(self):
        replies = self.legacy_flow("2025-11-25")
        self.assertEqual(sorted(replies), [1, 2, 3, 4])  # the notification gets no answer
        self.assertEqual(replies[1]["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(replies[1]["result"]["serverInfo"]["name"], "aidd")
        self.assertIn("tools", replies[1]["result"]["capabilities"])
        self.assertEqual(replies[2]["result"], {})
        self.assertIn("check_edit", [t["name"] for t in replies[3]["result"]["tools"]])
        self.assertNotIn("resultType", replies[3]["result"])  # a legacy result carries no 2026-07-28 field
        self.assertTrue(replies[4]["result"]["content"][0]["text"].startswith("deny"))

    def test_a_legacy_2025_06_18_client_initializes_and_works(self):
        replies = self.legacy_flow("2025-06-18")
        self.assertEqual(replies[1]["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("check_edit", [t["name"] for t in replies[3]["result"]["tools"]])
        self.assertFalse(replies[4]["result"]["isError"])

    def test_a_2024_11_05_initialize_is_not_accepted_as_that_version(self):
        """The legacy lifecycle: the server answers with another revision it supports, the latest, and a client
        that cannot speak it disconnects."""
        for old in ("2024-11-05", "2025-03-26"):
            with self.subTest(old):
                replies = self.serve({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": old, "capabilities": {}}})
                self.assertEqual(replies[1]["result"]["protocolVersion"], "2025-11-25")
                self.assertNotIn(old, mcp_protocol.SUPPORTED)

    def test_one_process_serves_both_eras(self):
        replies = self.serve(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": meta()}},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        )
        self.assertEqual(replies[2]["result"]["resultType"], "complete")
        self.assertNotIn("resultType", replies[3]["result"])

    def test_a_meta_that_is_not_an_object_is_invalid_params(self):
        """`_meta` is an object in both eras; any other value is malformed, never read as `{}`."""
        bad = ([], "2026-07-28", 1, None)
        messages = [
            {"jsonrpc": "2.0", "id": f"{method}-{i}", "method": method, "params": {"_meta": value}}
            for method in ("tools/list", "server/discover", "initialize")
            for i, value in enumerate(bad)
        ]
        replies = self.serve(*messages)
        self.assertEqual(sorted(replies), sorted(m["id"] for m in messages))
        for message in messages:
            with self.subTest(message["id"]):
                self.assertNotIn("result", replies[message["id"]])
                self.assertEqual(replies[message["id"]]["error"]["code"], -32602)
                self.assertIn("_meta", replies[message["id"]]["error"]["message"])

    def test_a_request_that_names_no_era_is_refused_until_a_legacy_initialize(self):
        """A request with no modern `_meta` is legacy only after an `initialize` in this process. Before one, it gets
        -32602, which says how to name an era, so a modern client that forgot its `_meta` fails deterministically
        instead of being served legacy semantics by accident
        (https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio#backward-compatibility)."""
        call = {"name": "check_edit", "arguments": {"path": ".aidd/config.yaml"}}
        bare = [
            {"jsonrpc": "2.0", "id": "ping", "method": "ping"},
            {"jsonrpc": "2.0", "id": "list", "method": "tools/list"},
            {"jsonrpc": "2.0", "id": "call", "method": "tools/call", "params": call},
            {
                "jsonrpc": "2.0",
                "id": "meta-no-version",
                "method": "tools/list",
                "params": {"_meta": {"traceparent": "00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01"}},
            },
            {"jsonrpc": "2.0", "id": "legacy-in-meta", "method": "tools/list", "params": {"_meta": meta("2025-11-25")}},
        ]
        before = self.serve({"jsonrpc": "2.0", "method": "notifications/initialized"}, *bare)
        self.assertEqual(sorted(before), sorted(m["id"] for m in bare))
        for message in bare:
            with self.subTest(before=message["id"]):
                error = before[message["id"]]["error"]
                self.assertEqual(error["code"], -32602)
                self.assertIn("`initialize`", error["message"])
                self.assertIn(MODERN, error["message"])
                self.assertIn(mcp_protocol.VERSION_KEY, error["message"])
        initialize = {"jsonrpc": "2.0", "id": "init", "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}}}
        after = self.serve(initialize, *bare)
        for message in bare:
            with self.subTest(after=message["id"]):
                self.assertNotIn("resultType", after[message["id"]]["result"])
        self.assertTrue(after["call"]["result"]["content"][0]["text"].startswith("deny"))

    def test_the_session_remembers_only_a_legacy_initialize(self):
        session = mcp_server.Session()
        listed = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        self.assertEqual(mcp_server.handle_message(listed, str(self.root), session)["error"]["code"], -32602)
        self.assertIsNone(session.legacy)
        modern = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": meta()}}
        self.assertEqual(mcp_server.handle_message(modern, str(self.root), session)["result"]["resultType"], "complete")
        self.assertIsNone(session.legacy)  # a modern request opens no session
        initialize = {"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
        mcp_server.handle_message(initialize, str(self.root), session)
        self.assertEqual(session.legacy, "2025-06-18")
        self.assertIn("tools", mcp_server.handle_message(listed, str(self.root), session)["result"])
        # Without the process's session, each message stands alone: a bare request is refused.
        self.assertEqual(mcp_server.handle_message(listed, str(self.root))["error"]["code"], -32602)

    def test_a_response_sent_to_the_server_gets_no_reply(self):
        """The server sends no request, so a response it receives answers nothing: it is dropped, never -32600."""
        replies = self.serve(
            {"jsonrpc": "2.0", "id": 5, "result": {}},
            {"jsonrpc": "2.0", "id": 6, "error": {"code": -32601, "message": "method not found"}},
            {"jsonrpc": "2.0", "id": 7},
            {"jsonrpc": "2.0", "id": 8, "method": "tools/list", "params": {"_meta": meta()}},
        )
        self.assertEqual(sorted(replies), [8])
        self.assertEqual(replies[8]["result"]["resultType"], "complete")

    def test_the_versions(self):
        self.assertEqual(mcp_protocol.MODERN, (MODERN,))
        self.assertEqual(mcp_protocol.LEGACY, ("2025-11-25", "2025-06-18"))
        self.assertEqual(mcp_protocol.PROTOCOL, MODERN)


if __name__ == "__main__":
    unittest.main()
