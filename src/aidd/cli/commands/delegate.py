"""`aidd delegate`: a standing delegation's commands. `check` says whether a delegated ask may go to the delegate,
`packet` prints what the delegate reads, `hook` is Claude Code's hook, and `stop` turns the delegation off here. The
delegate's answer has no command: only its MCP tool writes one."""

from __future__ import annotations

import json
import os
import sys

from aidd import delegation


def _request(args) -> delegation.Request:
    if not args.action:
        raise ValueError('name the ask: `aidd delegate check --action <id> --command "<the exact command>" --head <sha>`')
    return delegation.Request(
        action=args.action, command=args.command_line or "", head=args.head or "", spec=args.spec, cwd=args.cwd or ".", env=dict(os.environ)
    )


def cmd_delegate(args) -> int:
    """`aidd delegate check` exits 0 eligible or 1 defer; `packet` prints the delegate's packet; `hook` answers Claude
    Code's hook on stdin; `stop` writes the stop file. A usage error exits 2."""
    if args.delegate_command == "hook":
        out = delegation.hook_main(sys.stdin.read())
        if out:
            print(out)
        return 0
    if args.delegate_command == "stop":
        path = delegation.stop(args.cwd or ".")
        print(f"The delegation is off in this clone ({path}): every delegated ask now goes to you. Delete that file to turn it back on.")
        return 0
    if args.delegate_command == "packet":
        print(json.dumps(delegation.packet(_request(args)), indent=2))
        return 0
    result = delegation.run_check(_request(args))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['outcome']}: {result['action']} on {result['covers'].get('head', '')[:12]}")
        for reason in result["reasons"]:
            print(f"  {reason['code']}{' (reserved)' if reason['reserved'] else ''}: {reason['detail']}")
        if result["covers"].get("command"):
            print(f"command: {result['covers']['command']}")
        print(f"Next: {result['next']}")
    return 0 if result["outcome"] == "eligible" else 1
