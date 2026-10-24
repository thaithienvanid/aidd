# Your own hook next to aidd's guard

`aidd init` wires one Claude Code PreToolUse hook, the guard (`aidd hook pre-tool`), into `.claude/settings.json`. A team can add its own rules beside it without replacing or wrapping it. Claude Code runs every matching PreToolUse hook in parallel, and the most restrictive answer wins: deny, then ask, then allow ([Claude Code hooks](https://code.claude.com/docs/en/hooks), checked 2026-09-28). So your hook can only add a deny, and aidd's guard keeps denying everything it denies today.

This folder is an example, not a conformance case. [`deny-rm-rf-outside-worktree.py`](deny-rm-rf-outside-worktree.py) denies a recursive, forced `rm` whose target is outside the git worktree the session works in (or is the worktree itself, or holds a variable it cannot judge). It uses only the Python standard library, and a failure of its own lets the call through, since aidd's guard still runs.

## Add it

1. Copy the script to `.claude/hooks/deny-rm-rf-outside-worktree.py` and make it executable (`chmod +x`).
2. Add a second entry under `PreToolUse` in `.claude/settings.json`, after aidd's, leaving aidd's entry as it is:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|mcp__.*(?:[Mm]erge|MERGE|[Aa]pprov|APPROV|[Aa]ccept|ACCEPT|[Cc]omplete|COMPLETE|[Ss]tatus|STATUS|[Rr]eview|REVIEW|[Cc]omment|COMMENT|[Nn]ote|NOTE|[Dd]iscussion|DISCUSSION|[Tt]hread|THREAD|[Rr]eply|REPLY|[Ii]ssue|ISSUE|[Pp]ull|PULL|[Rr]equest|REQUEST|[Cc]ommit|COMMIT|[Pp]ush|PUSH|[Ff]ile|FILE|(?:_|-)(?:[Pp][Rr]|[Mm][Rr])s?(?:_|-|$)|(?<=[a-z])(?:Pr|PR|Mr|MR)(?:[A-Z_-]|s?$)).*",
        "hooks": [{ "type": "command", "command": "aidd hook pre-tool", "timeout": 20 }]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/deny-rm-rf-outside-worktree.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

3. Try it: `echo '{"tool_name":"Bash","cwd":"'"$PWD"'","tool_input":{"command":"rm -rf ~/old"}}' | python3 .claude/hooks/deny-rm-rf-outside-worktree.py` prints a deny; the same with `rm -rf build/` prints nothing.

`aidd init`, `aidd upgrade`, and `aidd uninstall` touch only aidd's own entries in that file, so your entry stays. Changing `.claude/**` is a protected path, so the change that adds the hook is a major change: a person reviews the rule like any other control.

## Write your own

- Read the event JSON on stdin: `tool_name`, `tool_input` (for Bash, `command`), and `cwd`.
- To deny, print `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "…"}}` and exit 0. To let the call through, print nothing. Never print `allow`: it would skip the permission prompt for that call, though another hook's deny would still win.
- Keep it fast and deterministic: no network, no model. Hooks run on every matching tool call.
- A hook is best effort, not a sandbox: a command built at run time gets past any text rule. For real limits, run the agent in a container with a default-deny network ([How do I… run agents in a sandbox](../../docs/HOW-TO.md#many-agents-at-once)).
