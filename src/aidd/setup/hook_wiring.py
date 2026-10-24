"""How a coding agent starts aidd: the launcher (`aidd.cli:main` from this interpreter), the guard and session hook
commands in each shell, the MCP server entry, and wiring them into Claude Code's settings.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

import aidd
from aidd import config
from aidd.kernel import documents, processes, repo_paths
from aidd.setup import guard_message

HOOK_COMMAND = "aidd hook pre-tool"  # the bare form, written when `aidd` is on PATH; every form ends with it
# The same tools the aidd plugin's hooks/hooks.json matches: the edits, Bash and PowerShell for the shell check, and the
# MCP tools that could approve or merge: a name with a word the guard denies on (merge, approve, accept, complete, status,
# review) or a channel an `/aidd approve` line could travel through (a comment, note, discussion, thread, reply, issue,
# pull or merge request, PR or MR, commit, push, or file), in any case style. A browser or a docs search never starts
# the guard. Claude Code tests the name as a case-sensitive regular expression.
_MCP_WORDS = (
    "merge",
    "approv",
    "accept",
    "complete",
    "status",
    "review",
    "comment",
    "note",
    "discussion",
    "thread",
    "reply",
    "issue",
    "pull",
    "request",
    "commit",
    "push",
    "file",
)
_MCP_PR = r"(?:_|-)(?:[Pp][Rr]|[Mm][Rr])s?(?:_|-|$)|(?<=[a-z])(?:Pr|PR|Mr|MR)(?:[A-Z_-]|s?$)"  # no `](`: Markdown would read a link
HOOK_MATCHER = (
    "Edit|Write|MultiEdit|NotebookEdit|Bash|PowerShell|mcp__.*(?:"
    + "|".join(f"[{w[0].upper()}{w[0]}]{w[1:]}|{w.upper()}" for w in _MCP_WORDS)
    + f"|{_MCP_PR}).*"
)
# The session hooks: advisory helpers, so each fails open (`|| true`, `; exit 0` in PowerShell): an aidd too old to know the hook, or missing,
# never blocks a session or a stop. `aidd hook stop` at level strict blocks through its JSON decision, which Claude
# Code reads on exit 0. PreCompact saves the state of the work in the git directory; its output cannot add context, so
# session-start reads the state back (see aidd.guard.session_hooks). UserPromptSubmit adds the next step to each prompt.
SESSION_EVENTS = {"SessionStart": "session-start", "Stop": "stop", "SubagentStop": "stop", "UserPromptSubmit": "prompt-submit", "PreCompact": "pre-compact"}
# On Windows, Claude Code runs a hook command in Git Bash when it is installed and in PowerShell otherwise, so init
# names the shell: PowerShell, which every Windows machine has. Its syntax differs: `$env:NAME = '...';` sets the
# environment, `&` calls a quoted program, and `; exit 0` fails open (Windows PowerShell 5.1 has no `||`).
WINDOWS_HOOK_SHELL = "powershell"
_FAIL_OPEN = {"sh": " || true", "powershell": "; exit 0"}


def _hook_shell() -> str:
    return WINDOWS_HOOK_SHELL if os.name == "nt" else "sh"


# The user launcher: one small script per user and machine, outside every repository, that starts aidd isolated (`-I`)
# from the Python that ran `aidd init`. The hooks and the MCP server name it through the home folder, so
# .claude/settings.json and .mcp.json hold no machine's path: they are the same for every contributor, and each
# contributor's `aidd init --claude-hooks` writes their own launcher. On Windows, init still writes this machine's
# launcher into each command (see WINDOWS_HOOK_SHELL).
USER_LAUNCHER = (".aidd", "bin", "aidd")
USER_LAUNCHER_SHOWN = "~/" + "/".join(USER_LAUNCHER)
HOOK_LAUNCHER = '"$HOME"/' + "/".join(USER_LAUNCHER)  # sh expands $HOME
MCP_LAUNCHER = "${HOME}/" + "/".join(USER_LAUNCHER)  # Claude Code expands ${HOME} in .mcp.json
# When the launcher cannot start aidd (a contributor who has not run init, an aidd that moved), the guard says so and
# fails like a guard that crashed: it allows, unless the project fails closed (fail_closed_test), which blocks (exit 2).
# Exit 1 shows Claude Code's hook error to the person. Session start tells the agent, which tells the person.
_SETUP = "aidd init --claude-hooks"
PROJECT_CONFIG = '"${CLAUDE_PROJECT_DIR:-.}/.aidd/config.yaml"'


def fail_closed_test(path: str = PROJECT_CONFIG) -> str:
    """The shell's guard/repo_config.fails_closed, reading the project's config at `path` (a shell word; by default
    from the project folder Claude Code names): an organization's AIDD_HOOK_FAIL_CLOSED=1, or the config's top-level
    `profile` naming one of config.FAIL_CLOSED_PROFILES or `mode` naming one of config.FAIL_CLOSED_MODES on any line, as
    the Python reads it (CRLF too). Shell builtins only: a program on PATH, which the repository could plant, never
    answers it, and no `[` (LauncherTextTests)."""
    keys = "|".join([*(f"profile:{p}" for p in config.FAIL_CLOSED_PROFILES), *(f"mode:{m}" for m in config.FAIL_CLOSED_MODES)])
    each_line = (
        "k=${l%%:*}; v=${l#*:}; v=${v%%#*}"
        + "; while case $v in ' '*|'\t'*) true;; *) false;; esac; do v=${v#?}; done"
        + "; while case $v in *' '|*'\t'|*'\r') true;; *) false;; esac; do v=${v%?}; done"
        + r"; v=${v#\"}; v=${v#\'}; v=${v%\"}; v=${v%\'}"
        + f"; case $k:$v in {keys}) f=1;; esac"
    )
    scan = f'f=; test -r {path} && while IFS= read -r l || test -n "$l"; do case $l in profile:*|mode:*) {each_line};; esac; done < {path}'
    # A function the environment exports (bash's BASH_FUNC_*) could stand in for a builtin; unset them first.
    return f'{{ unset -f test read true false 2>/dev/null; test "${{AIDD_HOOK_FAIL_CLOSED:-}}" = 1 || {{ {scan}; test "$f" = 1; }}; }}'


_GUARD_UNAVAILABLE = f'echo "{guard_message.guard_missing_message(_SETUP)}" >&2; {fail_closed_test()} && exit 2; exit 1'
_BRIEF_UNAVAILABLE = (
    f'echo "aidd: its hooks could not run on this machine, so the guard is off. Run {_SETUP}, which writes the aidd hooks back; aidd doctor says why."'
)
_PORTABLE_HOOK = re.compile(r'"\$HOME"/\.aidd/bin/aidd hook (pre-tool|session-start|prompt-submit|stop|pre-compact)(?: \|\| .*)?')


def user_launcher_path() -> Path:
    """Where this user's launcher sits: the home folder sh and Claude Code expand, `$HOME`."""
    return Path(user_launcher_file())


def windows_launcher_path() -> Path:
    """Where this user's Windows launcher sits: `aidd.cmd`, the user launcher with a `.cmd` suffix, beside the sh script
    `aidd`. The OpenCode plugin starts it through `cmd.exe`, since Windows cannot run the sh script (A9)."""
    return user_launcher_path().with_suffix(".cmd")


def user_launcher_file() -> str:
    """user_launcher_path as text, in this OS's syntax whatever `os.name` claims (tests read Windows commands)."""
    return os.path.join(os.path.expanduser("~"), *USER_LAUNCHER)


def launcher_script(argv: list[str]) -> str:
    """The user launcher's text for a launcher argv (`launcher()`)."""
    return (
        "#!/bin/sh\n"
        f"# Written by `{_SETUP}`. The aidd hooks and MCP server of every repository on this machine start here:\n"
        "# aidd, isolated (-I), from the Python it is installed with. `aidd doctor` checks it; init rewrites it.\n"
        f'exec {" ".join(shlex.quote(a) for a in argv)} "$@"\n'
    )


def windows_launcher_script(argv: list[str]) -> str:
    """The user launcher's text on Windows: `aidd.cmd`, a batch file beside the sh script, which starts the same argv and
    passes its own arguments on (`%*`). The OpenCode plugin starts it through `cmd.exe`; `aidd init` writes it on Windows,
    where the sh script cannot run. The program is quoted, an argument only where cmd needs it quoted, and a `%` in any of
    them is doubled, as a batch file reads it."""

    def word(argument: str, *, first: bool) -> str:
        quoted = argument.replace("%", "%%")
        return f'"{quoted}"' if first or re.search(r'[\s"&|<>^()]', quoted) else quoted

    words = " ".join(word(a, first=i == 0) for i, a in enumerate(argv))
    return (
        "@echo off\n"
        f"rem Written by `{_SETUP}`. The aidd hooks and MCP server of every repository on this machine start here:\n"
        "rem aidd, isolated (-I), from the Python it is installed with. `aidd doctor` checks it; init rewrites it.\n"
        f"{words} %*\n"
    )


def read_user_launcher(path: Path | None = None) -> tuple[list[str] | None, str | None]:
    """(argv, None) for a user launcher that `aidd init` wrote and only this user can change, else (None, why not)."""
    path = path or user_launcher_path()
    try:
        st = path.lstat()
    except OSError:
        return None, f"{USER_LAUNCHER_SHOWN} is missing on this machine"
    if path.is_symlink() or not path.is_file():
        return None, f"{USER_LAUNCHER_SHOWN} is not a file"
    for p, s in ((path, st), (path.parent, path.parent.stat()), (path.parent.parent, path.parent.parent.stat())):
        if (hasattr(os, "getuid") and s.st_uid != os.getuid()) or s.st_mode & 0o022:
            return None, f"{p} is owned by another user, or others can write to it"
    try:
        text = path.read_text(encoding="utf-8")
        line = next(x for x in text.splitlines() if x.startswith("exec "))
        words = shlex.split(line.removeprefix("exec "))
    except (OSError, ValueError, StopIteration):
        words = []
    argv = words[:-1]
    if not words or words[-1] != "$@" or launcher_script(argv) != text or not isolated_launcher(argv):
        return None, f"{USER_LAUNCHER_SHOWN} is not the launcher `aidd init` writes"
    return argv, None


def install_user_launcher(root: Path, resolved: tuple[list[str], dict[str, str]], actions: list[str], *, windows: bool | None = None) -> None:
    """Write this user's launcher for `resolved`, unless it is already that one. On Windows `aidd.cmd` is written beside
    it: the batch launcher the OpenCode plugin starts through `cmd.exe` (A9). `windows` names that machine's OS (its
    default: this one). A launcher inside this repository is never written: every repository on the machine starts aidd
    through the file, so one repository would steer them all."""
    argv = resolved[0]
    if why := ("it sets an environment" if resolved[1] else launch_shape(root, [*argv, "mcp"], {}, ["mcp"])):
        actions.append(f"kept     {USER_LAUNCHER_SHOWN} (not rewritten: {why})")
        return
    path = user_launcher_path()
    old = read_user_launcher(path)[0]
    if old == argv:
        actions.append(f"kept     {USER_LAUNCHER_SHOWN} (it starts this aidd)")
    elif from_claude_plugin(argv):
        # A plugin's folder is its installed version's, and Claude Code removes it after an update: a launcher there breaks.
        why = "this aidd runs from the Claude Code plugin, whose folder changes with each update"
        if old:
            actions.append(f"kept     {USER_LAUNCHER_SHOWN} (it starts the aidd CLI; {why})")
        else:
            actions.append(
                f"warn     did not write {USER_LAUNCHER_SHOWN}: {why}. The hooks of agents other than Claude Code start there: "
                "install the aidd CLI (docs/INSTALL.md, The CLI), then run `aidd init` again"
            )
        return
    elif why := write_file(path, launcher_script(argv)):  # `why` reads as a problem: here, the reason it was not written
        actions.append(f"warn     could not write {USER_LAUNCHER_SHOWN} ({why}); the aidd hooks cannot start until it exists")
        return
    else:
        was = f"; they started {launcher_started(old)} before" if old else ""
        actions.append(f"wrote    {USER_LAUNCHER_SHOWN} (the aidd hooks and MCP server of every repository here start {launcher_started(argv)}{was})")
    if os.name == "nt" if windows is None else windows:
        write_cmd_launcher(argv, actions)


def write_file(path: Path, text: str) -> str | None:
    """Write `text` to `path`, making the folders above it; the reason it could not be written, or None. A folder init has
    to make is tightened, so only this user writes there."""
    try:
        for d in (path.parent.parent, path.parent):
            if not d.is_dir():
                d.mkdir(parents=True, exist_ok=True)
                d.chmod(0o755)
        tmp = path.with_name(f".{path.name}.{os.getpid()}")
        tmp.write_text(text, encoding="utf-8")
        tmp.chmod(0o755)
        os.replace(tmp, path)
    except OSError as exc:  # a home folder it cannot write: the rest of init still runs, and doctor names the gap
        return exc.strerror or str(exc)
    return None


def write_cmd_launcher(argv: list[str], actions: list[str]) -> None:
    """Write `aidd.cmd` beside the sh script on Windows (A9): the batch launcher the OpenCode plugin starts through
    `cmd.exe`, since cmd cannot run the sh script. It starts the same argv."""
    path, text = windows_launcher_path(), windows_launcher_script(argv)
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
        actions.append(f"kept     {path.name} (it starts this aidd)")
        return
    if why := write_file(path, text):
        actions.append(f"warn     could not write {path.name} ({why}); the OpenCode plugin cannot start the guard")
        return
    actions.append(f"wrote    {path.name} (the batch launcher the OpenCode plugin starts through `cmd.exe`)")


def launcher_started(argv: list[str]) -> str:
    """A launcher argv as a person reads it: which Python and which folder of aidd it starts, or its own words."""
    return f"{argv[0]} -I, with aidd from {argv[4]}" if len(argv) == 6 and argv[3] == LOADER else " ".join(argv)


def from_claude_plugin(argv: list[str]) -> bool:
    """Whether a launcher's aidd is a Claude Code plugin's own copy, under the plugins folder of Claude Code's config."""
    plugins = config.claude_config_dir() / "plugins"
    return any(Path(a).is_absolute() and Path(a).resolve().is_relative_to(plugins.resolve()) for a in argv)


def expand_launcher(program: str) -> str:
    """A launcher as the shell or Claude Code runs it: the user launcher's `$HOME` forms become its path."""
    return user_launcher_file() if program in (MCP_LAUNCHER, '"$HOME"/' + "/".join(USER_LAUNCHER), "$HOME/" + "/".join(USER_LAUNCHER)) else program


# The commands with the bare launcher, `aidd` on PATH.
SESSION_HOOKS = {event: f"aidd hook {sub}{_FAIL_OPEN[_hook_shell()]}" for event, sub in SESSION_EVENTS.items()}
SESSION_HOOK_TIMEOUT_SECONDS = 10
_AIDD_HOOK = re.compile(r"(?<![\w-])aidd hook (pre-tool|session-start|prompt-submit|stop|pre-compact)(?![\w-])")


def aidd_hook(command) -> str | None:
    """Which aidd hook a settings command runs (`pre-tool`, `session-start`, `prompt-submit`, `stop`, `pre-compact`), whatever
    launcher it names; else None."""
    m = _AIDD_HOOK.search(command) if isinstance(command, str) else None
    return m.group(1) if m else None


def _on_default_path(directory: str) -> bool:
    """Whether an isolated interpreter (`-I`: no user site) imports from `directory` as is: a site-packages directory."""
    import site

    return any(Path(d).resolve() == Path(directory).resolve() for d in site.getsitepackages() if d)


# Starts aidd from an explicit source folder, as `python -I -c LOADER <src> aidd <args>`. `-I` keeps the working
# directory (the repository) and every PYTHON* variable off sys.path, so a repository cannot replace aidd or a module it
# imports. It holds no quote, so it passes unchanged through sh, PowerShell, and JSON. The plugin's hooks use it too:
# on a Python older than 3.11 it exits 3 before it reads stdin, and the plugin then runs it with a Python uv finds.
LOADER = "import sys; sys.version_info < (3, 11) and sys.exit(3); sys.path.insert(0, sys.argv.pop(1)); sys.argv[0] = sys.argv.pop(1); from aidd.cli import main; sys.exit(main())"


def launcher() -> tuple[list[str], dict[str, str]]:
    """How a hook or the MCP server starts this aidd, resolved when init runs: this interpreter by its absolute path,
    isolated (`-I`), with `-m aidd` when aidd is installed in its site-packages, else LOADER and the source it runs from
    (an install from a checkout or a pyz, which `-I` would not find through PYTHONPATH). Never the bare `aidd` on PATH:
    its console script runs without `-I`, so a PYTHONPATH from the project's settings could replace aidd's modules.
    (argv, extra environment): the environment is always empty."""
    src = str(Path(aidd.__file__).resolve().parent.parent)  # the folder that holds the aidd package, wherever this module sits
    python = os.path.normpath(os.path.abspath(sys.executable))  # never resolved: a venv's python is a link into it
    return ([python, "-I", "-m", "aidd"] if _on_default_path(src) else [python, "-I", "-c", LOADER, src, "aidd"]), {}


def _absolute(path: str) -> bool:
    """An absolute path on this OS: init writes the interpreter's full path. A drive or UNC form (`C:\\...`,
    `\\\\server\\...`) counts only on Windows, where it is one."""
    return os.path.isabs(path) or (os.name == "nt" and re.match(r"[A-Za-z]:[\\/]|\\\\", path) is not None)


def isolated_launcher(words: list[str]) -> bool:
    """Whether a launcher's argv (before `hook ...` or `mcp`) is one a repository cannot hijack: an interpreter by its
    absolute path, run with `-I` and `-m aidd` or LOADER. A bare `aidd` or `python3` is found through PATH, and a Python
    run without `-I` reads PYTHONPATH and puts the working directory first on sys.path."""
    if not words or not _absolute(words[0]):
        return False
    return words[1:] == ["-I", "-m", "aidd"] or (len(words) == 6 and words[1:4] == ["-I", "-c", LOADER] and words[5] == "aidd")


def _ps_quote(word: str) -> str:
    """A PowerShell single-quoted string: literal, backslashes included; a quote doubles."""
    return "'" + word.replace("'", "''") + "'"


def _shell_launcher(argv: list[str], env: dict[str, str], shell: str = "sh") -> str:
    if shell == WINDOWS_HOOK_SHELL:
        words = [a if shlex.quote(a) == a else _ps_quote(a) for a in argv]  # quoted where sh would quote it too
        call = ("& " if words[0].startswith("'") else "") + " ".join(words)
        return "".join(f"$env:{k} = {_ps_quote(v)}; " for k, v in env.items()) + call
    return " ".join([f"{k}={shlex.quote(v)}" for k, v in env.items()] + [shlex.quote(a) for a in argv])


def hook_command(sub: str, resolved: tuple[list[str], dict[str, str]] | None = None, shell: str | None = None) -> str:
    """The settings command for one aidd hook, in the syntax of the shell Claude Code runs it with (PowerShell on
    Windows, see WINDOWS_HOOK_SHELL); the session hooks fail open. In sh it starts the user launcher, the same on every
    machine, and says so when that cannot run (see _GUARD_UNAVAILABLE); `resolved` is then what the launcher holds."""
    shell = shell or _hook_shell()
    kind = sub
    if shell == "sh":
        tail = {"pre-tool": f"{{ {_GUARD_UNAVAILABLE}; }}", "session-start": _BRIEF_UNAVAILABLE}.get(kind, "true")
        return f"{HOOK_LAUNCHER} hook {sub} || {tail}"
    argv, env = resolved or launcher()
    return f"{_shell_launcher(argv, env, shell)} hook {sub}" + ("" if kind == "pre-tool" else _FAIL_OPEN[shell])


def _shell_field() -> str | None:
    """The `shell` field init writes on a hook entry: PowerShell on Windows, none elsewhere."""
    return WINDOWS_HOOK_SHELL if _hook_shell() == WINDOWS_HOOK_SHELL else None


def _hook_entry(command: str, timeout_seconds: int) -> dict:
    """A settings hook entry; on Windows it names the shell its command is written for."""
    return _rewire({"type": "command", "command": "", "timeout": timeout_seconds}, command)


def _rewire(hook: dict, command: str) -> dict:
    """Point a settings hook entry at `command`, naming the shell on Windows and dropping one that no longer applies."""
    hook["command"] = command
    if _hook_shell() == WINDOWS_HOOK_SHELL:
        hook["shell"] = WINDOWS_HOOK_SHELL
    else:
        hook.pop("shell", None)
    return hook


def mcp_server(resolved: tuple[list[str], dict[str, str]] | None = None) -> dict:
    """The .mcp.json entry that starts `aidd mcp`: the user launcher, except on Windows (see USER_LAUNCHER)."""
    if os.name != "nt":
        return {"command": MCP_LAUNCHER, "args": ["mcp"]}
    argv, env = resolved or launcher()
    entry: dict = {"command": argv[0], "args": [*argv[1:], "mcp"]}
    if env:
        entry["env"] = dict(env)
    return entry


_PS_ENV = re.compile(r"\$env:([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*'((?:[^']|'')*)'[ \t]*;[ \t]*")
_PS_WORD = re.compile(r"'((?:[^']|'')*)'|([^\s']+)")


def _hook_words(command: str) -> tuple[list[str], dict[str, str]] | None:
    """A hook command as (argv, environment), in either syntax init writes: POSIX sh (`NAME=value 'prog' ... || true`)
    or PowerShell (`$env:NAME = 'value'; & 'prog' ...; exit 0`). None when it does not parse. On Windows a backslash
    is a path separator, never an escape, in both. The user launcher's form names the launcher's file."""
    text, env = command.strip(), dict[str, str]()
    if m := _PORTABLE_HOOK.fullmatch(text):
        return [user_launcher_file(), "hook", m.group(1)], env
    if text.startswith(("&", "$env:")) or re.search(r";[ \t]*exit[ \t]+0[ \t]*$", text):
        while m := _PS_ENV.match(text):
            env[m.group(1)] = m.group(2).replace("''", "'")
            text = text[m.end() :]
        text = re.sub(r";[ \t]*exit[ \t]+0[ \t]*$", "", text).removeprefix("&").strip()
        return [m.group(1).replace("''", "'") if m.group(1) is not None else m.group(2) for m in _PS_WORD.finditer(text)], env
    try:
        words = processes.split_command(re.sub(r"[ \t]*\|\|[ \t]*true[ \t]*$", "", text))
    except ValueError:
        return None
    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
        k, _, v = words.pop(0).partition("=")
        env[k] = v
    return words, env


def command_program(command: str) -> str | None:
    """The program a hook command starts, after any environment it sets."""
    parsed = _hook_words(command)
    return parsed[0][0] if parsed and parsed[0] else None


def _hook_repair(root: Path, command: str, sub: str, shell: str | None = None) -> str | None:
    """Why init replaces a configured aidd hook: doctor would not run it (`launch_shape`: inside the repository, extra
    words, not isolated) or it is not exactly what init writes. None when it may stay."""
    parsed = parse_hook(command, sub)
    if parsed is None:
        return "it does not parse"
    return launch_shape(root, *parsed, parsed[0][-2:]) or (None if written_by_init(command, sub, parsed, shell) else NOT_INIT_WRITTEN)


def _machine_path(command: str, sub: str, shell: str | None) -> bool:
    """An older init's sh command: an isolated launcher by this machine's path, where init now names the user launcher."""
    parsed = parse_hook(command, sub)
    return shell is None and _hook_shell() == "sh" and parsed is not None and not parsed[1] and isolated_launcher(parsed[0][:-2])


NOT_INIT_WRITTEN = "it is not a command `aidd init` writes; `aidd init --claude-hooks` repairs it"


def written_by_init(command: str, sub: str, parsed: tuple[list[str], dict[str, str]], shell: str | None = None) -> bool:
    """Whether `command` is exactly what `hook_command` renders for its parsed launcher in the shell that runs it: the
    entry's `shell` (`"powershell"`, which counts only on Windows), else sh. Doctor trusts the parse only then: a parser
    and a shell can read one string two ways (`...; other; exit 0`), and a PowerShell command under sh fails to parse,
    a non-blocking error that would leave the guard off."""
    words, env = parsed
    if words[-2] != "hook" or words[-1] != sub:
        return False
    if shell == WINDOWS_HOOK_SHELL and os.name != "nt":
        return False
    return command.strip() == hook_command(words[-1], (words[:-2], env), WINDOWS_HOOK_SHELL if shell == WINDOWS_HOOK_SHELL else "sh")


def aidd_wrote(command: str, sub: str, shell: str | None = None) -> bool:
    """Whether a hook command is exactly one some `aidd init` wrote for the hook `sub`: the bare `aidd hook <sub>` (a
    session hook with its fail-open tail), the user launcher's, or an isolated launcher by its path (`written_by_init`).
    A command with anything else in it, such as a person's own step or an environment, is the person's."""
    text = command.strip()
    for name in (sub,):
        bare = f"aidd hook {name}"
        tails = ("",) if sub == "pre-tool" else ("", *_FAIL_OPEN.values())
        if text in (*(bare + tail for tail in tails), hook_command(name, shell="sh")):
            return True
    parsed = parse_hook(text, sub)
    if parsed is None or parsed[1] or not isolated_launcher(parsed[0][:-2]):
        return False
    machine = f"{_shell_launcher(parsed[0][:-2], {})} hook {parsed[0][-1]}"  # an older init's sh command, by this machine's path
    return text in (machine, machine + _FAIL_OPEN["sh"]) or written_by_init(text, sub, parsed, shell)


def mcp_written_by_init(server: dict) -> bool:
    """Whether an .mcp.json entry is one `mcp_server` writes: an isolated launcher (`isolated_launcher`) and `mcp`, and
    no environment, since init writes none. Other keys (such as `"type": "stdio"`) are the client's and do not count.
    Outside Windows, init writes only the user launcher."""
    command, args, env = server.get("command"), server.get("args"), server.get("env")
    if not isinstance(command, str) or not isinstance(args, list) or not args or args[-1] != "mcp" or env:
        return False
    if os.name != "nt":
        return command == MCP_LAUNCHER and args == ["mcp"]
    return isolated_launcher([command, *map(str, args[:-1])])


def resolves(program: str | None) -> bool:
    return bool(program) and shutil.which(expand_launcher(program)) is not None  # type: ignore[arg-type]


def session_hooks_missing(settings: Path) -> list[str]:
    """The SESSION_EVENTS a Claude Code settings file does not wire, with whatever launcher."""
    try:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
    except (OSError, ValueError, AttributeError):
        return list(SESSION_EVENTS)
    return [
        event
        for event, sub in SESSION_EVENTS.items()
        if not any(aidd_hook(h.get("command")) == sub for e in hooks.get(event, []) or [] if isinstance(e, dict) for h in e.get("hooks", []) or [])
    ]


def local_first(root: Path) -> bool:
    """The local gate is the gate here (no remote, or no CI gate): see gate.placement.trunk_on_platform."""
    from aidd import gate

    return (root / ".git").exists() and not gate.trunk_on_platform(str(root))


def session_hooks_wired(settings: Path) -> list[str]:
    """The SESSION_EVENTS a Claude Code settings file wires."""
    missing = session_hooks_missing(settings)
    return [event for event in SESSION_EVENTS if event not in missing]


def install_claude_hooks(root: Path, actions: list[str]) -> None:
    """Claude Code: the guard as a PreToolUse hook, and `aidd mcp` as a project MCP server. Both start aidd through `launcher()`, resolved now: this interpreter by its absolute path, isolated (`-I`), held in
    the user launcher outside Windows (USER_LAUNCHER), so the repository's files name no machine's path. Both files
    are merged, never overwritten; an aidd entry whose program does not resolve on this machine is repaired, and an
    older init's entry that named this machine's path is moved to the user launcher. The plugin ships the same wiring
    for plugin users; when the project enables the aidd plugin, the session hooks are left to it, so they do not run twice.
    """
    resolved = launcher()
    if os.name != "nt":
        install_user_launcher(root, resolved, actions)
    pre_command = hook_command("pre-tool", resolved)
    if (why := launch_shape(root, [*resolved[0], "hook", "pre-tool"], resolved[1], ["hook", "pre-tool"])) and "inside the repository" in why:
        # aidd installed into the project's own environment (its `.venv`): the repository can change that interpreter.
        actions.append(
            f"warn     aidd runs from {resolved[0][0]}, inside this repository, so `aidd doctor` will not trust the hook. "
            "Install aidd with `uv tool install` or `pipx`, then run `aidd init --claude-hooks`"
        )
    settings = root / ".claude" / "settings.json"
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    except ValueError:
        actions.append(f"kept     {repo_paths.shown(settings)} (not valid JSON; add the aidd hook by hand)")
        data = None
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", []) if data is not None else None
    ours = [entry for entry in pre or [] if any(aidd_hook(h.get("command")) == "pre-tool" for h in entry.get("hooks", []))]
    changed = False
    if pre is not None and ours:
        notes = []
        if not all(entry.get("matcher") == HOOK_MATCHER for entry in ours):
            # An older init matched fewer tools (edits only, or no PowerShell and MCP tools).
            for entry in ours:
                entry["matcher"] = HOOK_MATCHER
            notes.append("the aidd hook now matches every tool it checks")
        for h in (h for entry in ours for h in entry.get("hooks", []) if aidd_hook(h.get("command")) == "pre-tool"):
            if h["command"] == pre_command and h.get("shell") == _shell_field():
                continue
            if not resolves(command_program(h["command"])):
                _rewire(h, pre_command)
                notes.append(f"the aidd hook's launcher did not resolve here; it runs {pre_command.split(' || ')[0]}")
            elif _machine_path(h["command"], "pre-tool", h.get("shell")):
                _rewire(h, pre_command)
                notes.append(f"the aidd hooks now start aidd through {USER_LAUNCHER_SHOWN}, so the file names no machine's path")
            elif why := _hook_repair(root, h["command"], "pre-tool", h.get("shell")):
                _rewire(h, pre_command)
                notes.append(f"the aidd hook's launcher was not one doctor runs ({why}); it runs {pre_command.split(' || ')[0]}")
        if notes:
            changed = True
            actions.append(f"updated  {repo_paths.shown(settings)} ({'; '.join(dict.fromkeys(notes))})")
        else:
            actions.append(f"kept     {repo_paths.shown(settings)} (the aidd hook is there)")
    elif pre is not None:
        pre.append({"matcher": HOOK_MATCHER, "hooks": [_hook_entry(pre_command, 20)]})
        changed = True
        actions.append(f"updated  {repo_paths.shown(settings)} (PreToolUse: {pre_command.split(' || ')[0]})")
    if data is not None and config.plugin_enabled(root):
        actions.append(f"kept     {repo_paths.shown(settings)} (the aidd plugin is enabled and runs the session hooks; they are not added twice)")
    elif data is not None:
        added = []
        for event, sub in SESSION_EVENTS.items():
            entries = data["hooks"].setdefault(event, [])
            mine = [h for e in entries for h in e.get("hooks", []) if aidd_hook(h.get("command")) == sub]
            if not mine:
                entries.append({"hooks": [_hook_entry(hook_command(sub, resolved), SESSION_HOOK_TIMEOUT_SECONDS)]})
                added.append(event)
            for h in mine:
                want = hook_command(sub, resolved)
                same = h["command"] == want and h.get("shell") == _shell_field()
                if not same and (not resolves(command_program(h["command"])) or _hook_repair(root, h["command"], sub, h.get("shell"))):
                    _rewire(h, want)
                    added.append(event)
        if added:
            changed = True
            actions.append(f"updated  {repo_paths.shown(settings)} ({', '.join(dict.fromkeys(added))}: the aidd session hooks)")
    if changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    mcp_file = root / ".mcp.json"
    try:
        data = json.loads(mcp_file.read_text(encoding="utf-8")) if mcp_file.exists() else {}
    except ValueError:
        actions.append(f"kept     {repo_paths.shown(mcp_file)} (not valid JSON; add the aidd server by hand)")
        return
    servers = data.setdefault("mcpServers", {})
    current = servers.get("aidd")
    args = current.get("args") if isinstance(current, dict) else None
    words = [str(current.get("command")), *map(str, args[:-1])] if isinstance(current, dict) and isinstance(args, list) else []
    shape = launch_shape(root, [*words, "mcp"], {}, ["mcp"]) if words else "no entry"
    if isinstance(current, dict) and (current == mcp_server(resolved) or (resolves(current.get("command")) and not shape and mcp_written_by_init(current))):
        actions.append(f"kept     {repo_paths.shown(mcp_file)} (the aidd server is there)")
        return
    servers["aidd"] = mcp_server(resolved)
    mcp_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    shown = " ".join([servers["aidd"]["command"], *servers["aidd"]["args"]])
    why = (
        ")"
        if not current
        else ", its launcher did not resolve here)"
        if not resolves(current.get("command"))
        else ", its launcher was not one init writes now)"
    )
    actions.append(f"updated  {repo_paths.shown(mcp_file)} (MCP server: {shown}{why}")


def refresh_claude_hooks(root: Path, *, write: bool) -> tuple[list[str], list[str]]:
    """`aidd upgrade` for Claude Code's repository hooks: (each event in `.claude/settings.json` whose aidd hook is an
    older form some init wrote, `aidd_wrote`, the commands left as the person wrote them). Only aidd's own forms change:
    a command with a person's step or environment in it stays, and the guard's matcher widens only on a group of aidd's
    own handlers. A group shared with a person's handler keeps its matcher, and aidd's handler moves into its own group.
    With `write`, the file keeps its indentation and its text as written; every other hook and settings key stays."""
    settings = root / ".claude" / "settings.json"
    try:
        text = settings.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError):
        return [], []
    hooks = data.get("hooks") if isinstance(data, dict) else None
    stale: list[str] = []
    kept: list[str] = []
    for event, sub in {"PreToolUse": "pre-tool", **SESSION_EVENTS}.items():
        found = hooks.get(event) if isinstance(hooks, dict) else None
        entries: list = found if isinstance(found, list) else []
        for group in [g for g in entries if isinstance(g, dict) and isinstance(g.get("hooks"), list)]:
            mine = [h for h in group["hooks"] if isinstance(h, dict) and aidd_hook(h.get("command")) == sub]
            ours = [h for h in mine if aidd_wrote(h["command"], sub, h.get("shell"))]
            kept += [f"{event} runs `{documents.one_line(h['command'], 80)}`" for h in mine if h not in ours]
            for h in ours:
                if h["command"] != hook_command(sub) or h.get("shell") != _shell_field():
                    _rewire(h, hook_command(sub))
                    stale.append(event)
            if ours and event == "PreToolUse" and group.get("matcher") != HOOK_MATCHER:
                stale.append(event)
                if len(ours) == len(group["hooks"]):
                    group["matcher"] = HOOK_MATCHER
                else:  # never widen a person's handler: aidd's moves into a group of its own
                    group["hooks"] = [h for h in group["hooks"] if not any(h is o for o in ours)]
                    entries.append({"matcher": HOOK_MATCHER, "hooks": ours})
    if stale and write:
        settings.write_text(_json_as_written(text, data), encoding="utf-8")
    return list(dict.fromkeys(stale)), kept


def _json_as_written(original: str, data: object) -> str:
    """`data` as JSON in the layout of `original`: its indentation (one line when it had none), its trailing newline,
    and every character as it was written, never as a `\\u` escape."""
    m = re.search(r"^[ \t]+(?=\")", original, re.M)
    return json.dumps(data, indent=m.group(0) if m else None, ensure_ascii=False) + ("\n" if original.endswith("\n") else "")


def launch_shape(root: Path, words: list[str], env: dict[str, str], tail: list[str]) -> str | None:
    """Why doctor will not run this launcher, or None when it has the shape init writes: an isolated Python (`-I`) by
    its absolute path, with `-m aidd <tail>` or LOADER and its source folder, every path outside the repository. `aidd doctor` runs it, so a
    command the repository chose (a file inside it, another program) never runs."""
    if set(env) - {"PYTHONPATH"}:
        return f"it sets {', '.join(sorted(set(env) - {'PYTHONPATH'}))}"
    top = root.resolve()
    paths = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    if not words:
        return "it names no program"
    if expand_launcher(words[0]) == user_launcher_file():  # the user launcher: what it starts must pass the same checks
        argv, why = read_user_launcher()
        if argv is None:
            return why
        words = [*argv, *words[1:]]
    program, name = words[0], Path(words[0]).name
    here = Path(os.path.abspath(root))

    def inside(p: str) -> bool:
        q = Path(p) if _absolute(p) else root / p
        # Both as written and with links resolved: a repository's `.venv/bin/python` links to a Python outside it.
        # Each parent is compared as a file (samefile), not as text, so a case-changed path or a macOS firmlink counts.
        for path in (Path(os.path.normpath(os.path.abspath(q))), q.resolve()):
            if path.is_relative_to(here) or path.is_relative_to(top):
                return True
            for parent in (path, *path.parents):
                try:
                    if os.path.samefile(parent, top):
                        return True
                except OSError:
                    continue
        return False

    if _absolute(program) and inside(program):
        return f"{program} is inside the repository"
    repair = "`aidd init --claude-hooks` repairs it"
    if name in ("aidd", "aidd.exe") and words[1:] == tail:
        return f"it runs `aidd` without -I, so a PYTHONPATH from the project could replace aidd's modules; {repair}"
    is_python = re.fullmatch(r"python(?:\d+(?:\.\d+)?)?(?:\.exe)?", name)
    if is_python and words[1:] == ["-m", "aidd", *tail]:
        return f"it runs Python without -I, so the repository could replace aidd; {repair}"
    python = is_python and words[1:] == ["-I", "-m", "aidd", *tail]
    loader = is_python and len(words) == 6 + len(tail) and words[1:4] == ["-I", "-c", LOADER] and words[5:] == ["aidd", *tail]
    if not python and not loader:
        return "it is not an aidd launcher that init writes"
    if not _absolute(program):
        return f"it finds {program} through PATH, which the project's settings can change; {repair}"
    if loader:
        paths.append(words[4])
    for p in paths:
        if inside(p):
            return f"{p} is inside the repository"
    return None


def parse_hook(command: str, sub: str) -> tuple[list[str], dict[str, str]] | None:
    parsed = _hook_words(command)
    return parsed if parsed and len(parsed[0]) >= 2 and parsed[0][-2] == "hook" and parsed[0][-1] == sub else None
