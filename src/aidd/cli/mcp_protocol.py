"""The MCP protocol revisions `aidd mcp` speaks. It is dual-era
(https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning):

- **Modern** (2026-07-28): each request names its revision in `_meta` (`VERSION_KEY`) and is served on its own, with
  no session. A revision aidd does not speak gets `UNSUPPORTED_PROTOCOL_VERSION` (-32022) with the ones it does.
- **Legacy** (2025-11-25 and 2025-06-18): an `initialize` request selects legacy semantics for the rest of the
  process. An `initialize` that asks for another revision gets the newest legacy one, as the legacy lifecycle says.
- **Neither**: a request other than `initialize` whose `_meta` names no 2026-07-28 revision is served with legacy
  semantics only after a legacy `initialize` in the same process. Before one, it gets `INVALID_PARAMS` (-32602),
  which says to send `initialize` or to name the revision in `_meta`, so a client that probes or forgets its `_meta`
  fails deterministically instead of being served by accident. A `_meta` that is not an object is -32602 in both eras.
"""

from __future__ import annotations

MODERN = ("2026-07-28",)
LEGACY = ("2025-11-25", "2025-06-18")
SUPPORTED = MODERN + LEGACY  # newest first: what server/discover and -32022 list
PROTOCOL = MODERN[0]  # the newest revision aidd speaks
LEGACY_LATEST = LEGACY[0]  # the answer to an `initialize` that asks for a revision aidd does not speak

# The per-request and per-result `_meta` keys (https://modelcontextprotocol.io/specification/2026-07-28/basic/index#meta).
VERSION_KEY = "io.modelcontextprotocol/protocolVersion"
CAPABILITIES_KEY = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_KEY = "io.modelcontextprotocol/serverInfo"

UNSUPPORTED_PROTOCOL_VERSION = -32022
INVALID_PARAMS = -32602
METHOD_NOT_FOUND = -32601
