"""`aidd eval hooks`: a live check of one harness's hook events against aidd's reading of them (its dialect).

AGENTS.md asks that a new harness hook be a dialect and a live run. This makes the live run one command the agent runs,
never steps a person copies. It builds a scratch repository with `aidd init --harness <name> --team`, under a scratch
HOME so the person's launcher is never rewritten. Its hooks start the aidd under test with AIDD_HOOK_CAPTURE set. It runs
the agent command the operator names, with one scripted prompt as its last argument, as `aidd eval roles` runs one: aidd
itself starts no agent. Then it judges what the dialect makes of each captured event and writes the events, with the
prompt and the home folder masked, to `tests/fixtures/live/<harness>-<version>.jsonl`, which a unit test replays; for
Antigravity, each conversation's messages go beside it in `.messages.json`, since a subagent's role is read from them.
It runs on the operator's quota, by hand, never in CI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from aidd import config
from aidd.guard import antigravity_subagents, dialects
from aidd.kernel import git, processes

PROMPT = (
    "This is a test of tool hooks in a scratch repository. Do these steps in order, then stop: "
    "1. Read README.md. "
    "2. Create notes/one.md containing the word one, with your file-writing tool. "
    "3. Edit notes/one.md so it says: one, edited. "
    "4. Start one subagent and ask it to create notes/two.md containing the word two. "
    "5. Call the aidd MCP server's validate tool once. "
    "6. Run the shell command: git status --short. "
    "Report each step as done or denied, with the exact denial text."
)
# Two more steps for a harness that counts a role's turns and a session with a browser tool. The count runs against a cap of
# 5 turns (turn_budget.CAP_ENV in the launcher), so five reads cross both lines; the browser steps are skipped, and the
# check says so, when no Playwright MCP is configured.
EXTRA_STEPS = (
    " 7. Start the aidd-developer subagent and ask it to read README.md five times, one tool call each, and say done."
    " 8. Only if you have a Playwright browser tool: navigate it to file://{repo}/README.md, then to https://example.com."
)
TURN_CAP = 5
LAUNCHERS = ('\\"$HOME\\"/.aidd/bin/aidd', '"$HOME"/.aidd/bin/aidd', "${HOME}/.aidd/bin/aidd", "~/.aidd/bin/aidd")
# OpenCode's plugin and pane build the same path in JavaScript, which the rewrite replaces with a string of its own.
JS_LAUNCHER = 'join(homedir(), ".aidd", "bin", "aidd")'
EDITS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
CAPTURE = "events.jsonl"


def scratch(dest: Path, harness: str, src: Path) -> Path:
    """A repository in `dest/repo`, adopted for `harness` with the team, whose hooks start the aidd under test (`src`)
    through `dest/aidd-under-test` with AIDD_HOOK_CAPTURE set to `dest/events.jsonl`. Init runs with HOME at
    `dest/home`, so it writes its launcher there, never in the person's home."""
    repo, home = dest / "repo", dest / "home"
    repo.mkdir(parents=True)
    home.mkdir()
    git.run(["init", "-q", "-b", "main"], str(repo))
    for key, value in (("user.name", "Scratch"), ("user.email", "scratch@example.invalid"), ("commit.gpgsign", "false")):
        git.run(["config", key, value], str(repo))
    (repo / "README.md").write_text("# Scratch\n\nA repository for a live hook check.\n", encoding="utf-8")
    env = {**os.environ, "HOME": str(home), "PYTHONPATH": str(src), "AIDD_OFFLINE": "1"}
    init = [sys.executable, "-m", "aidd", "init", "--harness", harness, "--team", "--profile", "solo", "--ci", "none", "--approvers", "@scratch"]
    done = subprocess.run(init, cwd=repo, env=env, capture_output=True, text=True)
    if done.returncode != 0:
        raise ValueError(f"aidd init --harness {harness} failed in the scratch repository: {(done.stderr or done.stdout).strip()[-400:]}")
    launcher = dest / "aidd-under-test"
    launcher.write_text(
        f'#!/bin/sh\nAIDD_HOOK_CAPTURE="{dest / CAPTURE}" AIDD_HOOK_TURN_CAP={TURN_CAP} PYTHONPATH="{src}" exec "{sys.executable}" -m aidd "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    for path in (p for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if any(old in text for old in (*LAUNCHERS, JS_LAUNCHER)):
            for old in LAUNCHERS:
                text = text.replace(old, str(launcher))
            path.write_text(text.replace(JS_LAUNCHER, json.dumps(str(launcher))), encoding="utf-8")
    git.run(["add", "-A"], str(repo))
    git.run(["commit", "-qm", "day 0"], str(repo))
    git.run(["switch", "-qc", "feature"], str(repo))
    return repo


def run_agent(command: str, repo: Path, timeout_seconds: float) -> subprocess.CompletedProcess:
    """The agent command, with the scripted prompt as its last argument, in the scratch repository."""
    argv = [*processes.split_command(command), PROMPT + EXTRA_STEPS.format(repo=repo)]
    return subprocess.run(argv, cwd=repo, capture_output=True, text=True, timeout=timeout_seconds, stdin=subprocess.DEVNULL)


def read_capture(path: Path) -> list[dict]:
    """Each captured line: {hook, at, event}."""
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a line a stopped hook or the size cap cut short
    return out


def reading(event: dict) -> dict:
    """What the dialect makes of an event, in the fields a check reads: the tool, its file or command, the role, and
    whether it names a session."""
    out = dialects.of(event).normalize(event)
    raw_input = out.get("tool_input")
    tool_input: dict = raw_input if isinstance(raw_input, dict) else {}
    found: dict = {"dialect": dialects.of(event).key, "agent_type": out.get("agent_type") or "", "has_session": bool(out.get("session_id"))}
    if "tool_name" in out:
        found["tool_name"] = out["tool_name"]
        target = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path") or tool_input.get("command")
        if isinstance(target, str):
            found["target"] = target
    return found


def _who(event: dict) -> tuple[str, str]:
    """(the session, the subagent) an event names, as its dialect reads them: Claude Code names a subagent by
    `agent_id` within the session, the others by a session of its own."""
    out = dialects.of(event).normalize(event)
    return str(out.get("session_id") or ""), str(event.get("agent_id") or out.get("agent_id") or "")


def _counted(captured: list[dict], repo: Path | None) -> tuple[str, str]:
    """(verdict, what was seen) for the turn budget: a role's tool calls reach the post-tool hook, which counts them in the
    git directory and claims its two lines (turn_budget). The files are the evidence, never what the agent says."""
    seen = [c["event"] for c in captured if c.get("hook") == "post-tool" and isinstance(c.get("event"), dict) and c["event"].get("agent_id")]
    roles = [e for e in seen if str(e.get("agent_type", "")).startswith("aidd-")]
    if not roles:
        return "unseen", f"{len(seen)} subagent tool results, none from an aidd-team role"
    folder = (repo / ".git" / "aidd" / "turns") if repo else None
    counts = {p.stem: p.stat().st_size for p in folder.glob("*.n")} if folder and folder.is_dir() else {}
    said = sorted(p.name for p in folder.glob("*.[89]*")) if folder and folder.is_dir() else []
    if not counts:
        return "fail", f"{len(roles)} role tool results, and no count was kept"
    # Name whose calls each count holds, from the events' own ids, so the evidence says it counted a role and nothing else.
    kinds = {str(e["agent_id"]): str(e.get("agent_type") or "none") for e in seen}
    counted = {agent: next((kind for ident, kind in kinds.items() if ident.startswith(agent) or agent.startswith(ident)), "unknown") for agent in counts}
    strays = sorted(kind for kind in counted.values() if not kind.startswith("aidd-"))
    named = ", ".join(f"{kind} {counts[agent]}" for agent, kind in sorted(counted.items()))
    verdict = "fail" if strays or not said else "ok"
    return verdict, f"{len(roles)} role tool results; counted {named}; lines claimed {', '.join(said) or 'none'}" + (
        f"; counted an agent that is no role: {', '.join(strays)}" if strays else ""
    )


def _browsed(captured: list[dict]) -> tuple[str, str]:
    """(verdict, what was seen) for the browser rule on the addresses a Playwright call really carried: a `file:` page the
    guard allows, and a remote one it names (browser_pages). Skipped, and said so, where no browser tool was called."""
    from aidd.guard import browser_pages

    urls = []
    for e in (c["event"] for c in captured if c.get("hook") == "pre-tool" and isinstance(c.get("event"), dict)):
        read = dialects.of(e).normalize(e)
        raw = read.get("tool_input")
        tool_input: dict = raw if isinstance(raw, dict) else {}
        if "playwright" in str(read.get("tool_name", "")).lower() and isinstance(tool_input.get("url"), str):
            urls.append(tool_input["url"])
    if not urls:
        return "unseen", "skipped: no Playwright MCP is configured in this session, or the agent made no navigation"
    wrong = [u for u in urls if (browser_pages.why_denied(u) is None) != u.startswith("file:")]
    return (
        "fail" if wrong else "ok"
    ), f"{len(urls)} navigations; the guard reads {', '.join(('allows ' if browser_pages.why_denied(u) is None else 'denies ') + u[:40] for u in urls)}"


def judge(harness: str, captured: list[dict], repo: Path | None = None) -> list[tuple[str, str, str]]:
    """(check, ok | fail | unseen | limit, what was seen) for each thing a dialect must read right in a live session. The first
    event's session is the main one; a tool call from another session, or one a subagent's id names, is a subagent's,
    and must read a role, since a subagent read as a main session writes what its role may not."""
    events = [c["event"] for c in captured if isinstance(c.get("event"), dict)]
    tools = [(e, reading(e), _who(e)) for e in (c["event"] for c in captured if c.get("hook") == "pre-tool" and isinstance(c.get("event"), dict))]
    out = [("hooks ran", "ok" if tools else "fail", f"{len(captured)} events, {len(tools)} tool calls")]
    keys = sorted({r["dialect"] for _, r, _ in tools})
    out.append(("every tool event reads as this harness", "ok" if keys == [harness] else "fail", ", ".join(keys) or "none"))
    main = next((s for s in (_who(e)[0] for e in events) if s), "")  # the first event that names a session
    in_main = [r for _, r, (session, agent) in tools if session == main and not agent]
    roled = [r for r in in_main if r["agent_type"]]
    out.append(
        ("the main session carries no role", "fail" if roled else "ok" if in_main else "unseen", f"{len(roled)} of its {len(in_main)} calls read a role")
    )
    others = [r for _, r, (session, agent) in tools if session != main or agent]
    bare = [r for r in others if not r["agent_type"]]
    roles = ", ".join(sorted({r["agent_type"] for r in others if r["agent_type"]})) or "none"
    # Every subagent the session started, from any of its events: one that only reads never reaches the pre-tool hook.
    started = ", ".join(sorted({str(e.get("agent_type")) for e in events if e.get("agent_id") and e.get("agent_type")})) or "none"
    seen = f"{len(others)} guarded calls from subagents, by {roles}; subagents seen: {started}"
    if bare and not getattr(dialects.of(events[0]), "names_subagents", True):
        # A harness whose events name no subagent: SECURITY.md's known limit, now with the events that show it.
        out.append(("a subagent carries its role", "limit", f"{seen}; its events name no subagent, a known limit (SECURITY.md)"))
    else:
        out.append(("a subagent carries its role", "fail" if bare else "ok" if others else "unseen", seen))
    writes = [r for _, r, _ in tools if r.get("tool_name") in EDITS]
    pathless = [str(r.get("tool_name")) for r in writes if not r.get("target")]
    out.append(
        (
            "each file write reads as an edit of its path",
            "fail" if pathless else "ok" if writes else "unseen",
            f"{len(writes)} writes, {len(pathless)} with no path",
        )
    )
    mcp = sorted({str(r["tool_name"]) for _, r, _ in tools if str(r.get("tool_name", "")).startswith("mcp__")})
    ours = [m for m in mcp if "aidd" in m.split("__")[1]]
    out.append(("an MCP call names aidd's server", "ok" if ours else "unseen", ", ".join(mcp) or "no MCP call"))
    if repo is not None:  # a live run; a replay of a pinned fixture has no scratch repository to look in
        if dialects.of(events[0]).counts_turns:
            out.append(("a role's tool calls are counted", *_counted(captured, repo)))
        out.append(("a browser opens a local page and names a remote one", *_browsed(captured)))
    return out


def _mask(value: object, scratch_dir: Path) -> object:
    """A value with the scratch folder and the home folder replaced by names, and each prompt dropped."""
    if isinstance(value, str):
        for spelled in dict.fromkeys((str(scratch_dir.resolve()), str(scratch_dir), str(scratch_dir.resolve()).removeprefix("/private"))):
            value = value.replace(spelled, "<scratch>")
        return value.replace(str(Path.home()), "~")
    if isinstance(value, dict):
        return {k: ("<prompt>" if k in _PROMPTS and isinstance(v, str) else _mask(v, scratch_dir)) for k, v in value.items()}
    if isinstance(value, list):
        return [_mask(v, scratch_dir) for v in value]
    return value


# The keys that hold what a person or a lead wrote: a prompt, a delegated task, a message's text.
_PROMPTS = ("lastUserInput", "prompt", "Prompt", "Message", "content")


def masked(captured: list[dict], scratch_dir: Path) -> list[dict]:
    """The captured lines for a fixture: the scratch folder and the home folder replaced by names, the prompts dropped,
    and each with what the dialect reads, which the replay test pins."""
    lines = []
    for c in captured:
        event = _mask(c.get("event"), scratch_dir)
        line: dict = {"hook": c.get("hook"), "event": event}
        if c.get("hook") == "pre-tool" and isinstance(event, dict):
            line["reads_as"] = reading(event)
        lines.append(line)
    return lines


def antigravity_messages(captured: list[dict], scratch_dir: Path) -> dict[str, list]:
    """Each captured Antigravity conversation's messages, oldest first and masked, which the replay restores under a
    scratch home, since the guard reads a subagent's role from them. Only what the guard would read: a conversation's
    own folder under the brain folder with no link, its regular files up to the guard's cap, and only the fields the
    role reading needs."""
    out: dict[str, list] = {}
    for event in (c["event"] for c in captured if isinstance(c.get("event"), dict)):
        folder, _ = antigravity_subagents.messages_folder(event)
        if folder is None or event["conversationId"] in out or not folder.is_dir():
            continue
        with os.scandir(folder) as listing:
            found = [e for e in listing if e.name.endswith(".json") and e.name != "read.json" and e.is_file(follow_symlinks=False)]
        found = sorted(
            (e for e in found if e.stat(follow_symlinks=False).st_size <= antigravity_subagents.PARENT_MESSAGE_BYTES),
            key=lambda e: e.stat(follow_symlinks=False).st_mtime,
        )
        out[event["conversationId"]] = [{"name": e.name, "message": _mask(_message(Path(e.path)), scratch_dir)} for e in found]
    return {k: v for k, v in out.items() if v}


# The fields of a message a fixture keeps: what the role reading needs, and no text a person or a model wrote.
_MESSAGE_FIELDS = ("id", "recipient", "sender", "priority", "timestamp")
_ARGUMENTS_KEPT = ("TypeName", "Role", "Recipient")


def _message(path: Path) -> dict:
    """A message as pinned: the fields the role reading needs, each prompt as `<prompt>`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    out = {k: data[k] for k in _MESSAGE_FIELDS if k in data}
    if isinstance(data.get("content"), str):
        out["content"] = "<prompt>"
    title = (data.get("renderDetails") or {}).get("messageTitle")
    if isinstance(title, str):
        out["renderDetails"] = {"messageTitle": title}
    tool = (data.get("sourceMetadata") or {}).get("tool")
    if isinstance(tool, dict):
        kept: dict = {k: tool[k] for k in ("conversationId", "stepIndex") if k in tool}
        call = tool.get("toolCall")
        if isinstance(call, dict):
            kept["toolCall"] = {k: call[k] for k in ("id", "name") if k in call}
            args = json.loads(call["argumentsJson"]) if isinstance(call.get("argumentsJson"), str) else None
            if isinstance(args, dict):
                pinned = {k: ("<prompt>" if k in _PROMPTS else v) for k, v in args.items() if k in _ARGUMENTS_KEPT or k in _PROMPTS}
                kept["toolCall"]["argumentsJson"] = json.dumps(pinned)
        out["sourceMetadata"] = {"tool": kept}
    return out


def harness_version(command: str) -> str:
    """The harness's version, from `<program> --version`, as a file name part; `unknown` when it does not say."""
    argv = processes.split_command(command)[:1]
    try:
        said = subprocess.run([*argv, "--version"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    words = [w for w in said.replace("(", " ").split() if any(ch.isdigit() for ch in w)]
    return "".join(ch for ch in words[0] if ch.isalnum() or ch in ".-") if words else "unknown"


def eval_hooks(root: Path, harness: str, agent_command: str, timeout_seconds: float) -> tuple[list[str], list[tuple[str, str, str]], Path | None]:
    """One live session of `harness` in a scratch repository, built from the aidd source checkout at `root`: what the
    agent said last, the checks, and the fixture the events were pinned in (None when no event was captured)."""
    guarded = [h.key for h in config.guarded_harnesses()]
    if harness not in guarded:
        raise ValueError(f"aidd guards {', '.join(guarded)}: --harness {harness} has no hooks to check")
    with tempfile.TemporaryDirectory(prefix="aidd-live-hooks-") as tmp:
        dest = Path(tmp).resolve()
        repo = scratch(dest, harness, root / "src")
        try:
            run = run_agent(agent_command, repo, timeout_seconds)
            said = (run.stdout + run.stderr).strip().splitlines()[-3:]
        except subprocess.TimeoutExpired:
            said = [f"the agent ran past {timeout_seconds:g}s and was stopped"]
        captured = read_capture(dest / CAPTURE)
        checks = judge(harness, captured, repo)
        if not captured or any(verdict == "fail" for _, verdict, _ in checks):
            return said, checks, None  # a failing run never replaces the events pinned before
        fixture = root / "tests" / "fixtures" / "live" / f"{harness}-{harness_version(agent_command)}.jsonl"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        events = "".join(json.dumps(line, sort_keys=True) + "\n" for line in masked(captured, dest))
        messages = antigravity_messages(captured, dest)  # what the replay reads a subagent's role from
        fixture.write_text(events, encoding="utf-8")
        beside = fixture.with_name(f"{fixture.stem}.messages.json")
        if messages:
            beside.write_text(json.dumps(messages, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        else:
            beside.unlink(missing_ok=True)  # never a stale one beside new events
        return said, checks, fixture
