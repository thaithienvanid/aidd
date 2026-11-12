"""aidd: the command line, and the MCP server that serves it to agents.

`aidd.cli:main` is a permanent entry point: the console script, the managed settings
template, and every launcher `aidd init` wrote into an adopter's settings start it. The children: app (main),
parser (the help groups, the grouped help, `build_parser`, and `cli_facts`), grammar (each command's arguments and flags), commands (each help group's handlers, loaded only when one runs), arguments (what commands share), and
mcp_server.

This module is the package's door (aidd.kernel.doors): other packages use only the names below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["main"]

if TYPE_CHECKING:
    from aidd.cli.app import main as main
else:
    from aidd.kernel import doors

    __getattr__, __dir__ = doors.exports(__name__, {"main": "app"})
