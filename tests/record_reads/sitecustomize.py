"""The read record: which files of this checkout a test file reads, in its own process and in every Python process it starts.

A full run of `python3 tests/run.py` puts this folder on PYTHONPATH and names a log in TESTS_READS_LOG for each test
file. Python runs this module at start-up (site imports `sitecustomize`), and so does every Python process a test starts
with that environment. The process appends a line to the log for each path of the checkout it reads, from CPython's
audit events (PEP 578) and `os.stat`: `path` it opens to read, `path/` it lists, and `?path` whose existence it checks.

A process cannot see what another program reads. So it writes `*` and `# why` when it starts one that may read the
checkout: a Python process that does not record (run with -I, or with PYTHONPATH or the log removed), or another program
whose working folder, arguments, script, or environment name the checkout. `*` means "may read anything", so
`run.py --changed` always runs that test file. The rule assumes a program finds a file of the checkout only when
something names it. An `aidd` installed into the interpreter from this checkout breaks that, so run.py then sets
TESTS_READS_STRICT, and every Python process that does not record writes `*`.

It imports only `os`, `sys`, and `stat`, so a process starts as fast as before, and it runs the interpreter's own
`sitecustomize` after it.
"""

from __future__ import annotations

import os
import sys
from stat import S_ISREG

LOG = "TESTS_READS_LOG"
STRICT = "TESTS_READS_STRICT"
MAIN = "TESTS_READS_MAIN"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ROOTS = tuple(sorted({ROOT, os.path.realpath(ROOT)}))
OWN = os.path.relpath(HERE, ROOT)
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})
# Programs that run another program with arguments or an environment of their own (`env -i`, `xargs`), which this
# record cannot follow.
LAUNCHERS = frozenset({"env", "exec", "nice", "nohup", "script", "stdbuf", "sudo", "time", "timeout", "xargs", "npx", "uv", "uvx"})
# Values that name the checkout in every test's environment without telling a program to read it: the folder the run
# started in (pyenv's shims set PYENV_DIR to it), and the search path, whose programs are checked by where they resolve.
QUIET_ENV = frozenset({"PWD", "OLDPWD", "PYENV_DIR", "PATH", "_", LOG})
REAL_STAT = os.stat  # before `start` wraps it, so this module's own checks are not recorded as reads


def relative(path: object) -> str | None:
    """`path` relative to the checkout, or None when it is outside it or is not a path."""
    if isinstance(path, (bytes, os.PathLike)):
        path = os.fsdecode(path)
    if not isinstance(path, str) or not path:
        return None
    try:
        path = os.path.normpath(path if os.path.isabs(path) else os.path.join(os.getcwd(), path))
    except OSError:  # a working folder a test removed
        return None
    for root in ROOTS:
        if path == root:
            return "."
        if path.startswith(root + os.sep):
            return path[len(root) + 1 :]
    return None


def source_path(rel: str) -> str:
    """The source a cached module came from: `a/__pycache__/m.cpython-312.pyc` is `a/m.py`."""
    head, found, name = rel.rpartition("__pycache__/")
    if not found or not name.endswith(".pyc"):
        return rel
    return head + name.split(".", 1)[0] + ".py"


def names_checkout(text: object) -> bool:
    if isinstance(text, bytes):
        text = os.fsdecode(text)
    return isinstance(text, str) and any(root in text for root in ROOTS)


def is_python(program: str) -> bool:
    name = os.path.basename(program)
    return name == "python" or (name.startswith("python") and name[6:].replace(".", "").isdigit()) or program == sys.executable


def isolated(argv: list[str]) -> bool:
    """Python options that skip `sitecustomize` or PYTHONPATH (-I, -E, -S), up to the code, module, or script."""
    takes_value = False
    for arg in argv[1:]:
        if takes_value:
            takes_value = False
            continue
        if not arg.startswith("-") or arg in ("-", "--"):
            return False
        if arg.startswith("--"):
            continue
        flags = arg[1:]
        for i, flag in enumerate(flags):
            if flag in "IES":
                return True
            if flag in "cm":
                return False
            if flag in "XW":
                takes_value = i == len(flags) - 1
                break
    return False


def records(argv: list[str], env: dict[str, str]) -> bool:
    """Whether a Python process with these arguments and environment records its own reads."""
    return bool(env.get(LOG)) and HERE in env.get("PYTHONPATH", "").split(os.pathsep) and not isolated(argv)


def is_file(path: str) -> bool:
    try:
        return S_ISREG(REAL_STAT(path).st_mode)
    except (OSError, ValueError):
        return False


def resolve(program: str, env: dict[str, str]) -> str:
    if os.sep in program:
        return program
    for folder in env.get("PATH", os.defpath).split(os.pathsep):
        candidate = os.path.join(folder or ".", program)
        if is_file(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return program


def script_names_checkout(path: str) -> bool:
    """A script (a file that starts with `#!`) whose text names the checkout."""
    try:
        with open(path, "rb") as fh:
            if fh.read(2) != b"#!":
                return False
            return names_checkout(fh.read(1 << 20))
    except OSError:
        return False


# git commands that read only git's own settings, refs, and names, never a file of the work tree or its history, so one
# that runs in the checkout (as aidd does, to find where a repository starts) reads nothing a change edits.
GIT_METADATA = frozenset({"--version", "version", "var", "config", "remote", "tag", "rev-parse", "symbolic-ref", "for-each-ref"})
# `git ls-files` options that print more than the names of files: their content ids, their state, or line endings.
LS_FILES_CONTENT = frozenset({"-s", "--stage", "-m", "--modified", "-d", "--deleted", "-u", "--unmerged", "-t", "-v", "-f", "--eol", "--debug"})
# What `unseen` answers for a child that only lists the names of the checkout's files: a read of its top folder.
LISTS_CHECKOUT = "./"
GIT_OPTIONS_WITH_VALUE = frozenset({"-c", "-C", "--exec-path", "--git-dir", "--namespace", "--work-tree"})


def git_subcommand(argv: list[str]) -> str:
    """The git command in `argv` after git's own options (`git -c k=v rev-parse` runs `rev-parse`); `--version` too."""
    args = iter(argv[1:])
    for arg in args:
        if arg == "--version":
            return arg
        if arg in GIT_OPTIONS_WITH_VALUE:
            next(args, None)
        elif not arg.startswith("-"):
            return arg
    return ""


# Programs that only remove or make what they name, so with absolute paths they read nothing through their folder.
MAKERS = frozenset({"rm", "rmdir", "mkdir", "touch", "chmod"})


def git_folder(argv: list[str], cwd: str) -> str:
    """The folder git works in: `cwd`, moved by each `-C <path>`."""
    for i, arg in enumerate(argv[:-1]):
        if arg == "-C":
            cwd = os.path.join(cwd, argv[i + 1])
    return cwd


def folder_free(name: str, argv: list[str]) -> bool:
    """A command that reads nothing through its working folder: `rm -rf /tmp/x`, `git init -q /tmp/x`."""
    if name == "ssh-keygen":
        targets = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "-f"]
    elif name == "git":
        sub = git_subcommand(argv)
        targets = [a for a in argv[argv.index(sub) + 1 :] if not a.startswith("-")] if sub == "init" else []
    else:
        targets = [a for a in argv[1:] if not a.startswith("-")] if name in MAKERS else []
    return bool(targets) and all(os.path.isabs(t) for t in targets)


def unseen(program: object, args: object, cwd: object, env: object) -> str:
    """Why a child process may read the checkout without this record seeing it; empty when it cannot."""
    argv = [os.fsdecode(a) if isinstance(a, (bytes, str, os.PathLike)) else str(a) for a in (args if isinstance(args, (list, tuple)) else [args])]
    if not argv:
        return "a process with no arguments"
    environ = {os.fsdecode(k): os.fsdecode(v) for k, v in (os.environ if env is None else env).items()}  # type: ignore[attr-defined]
    exe = resolve(os.fsdecode(program) if isinstance(program, (bytes, str, os.PathLike)) else argv[0], environ)
    name = os.path.basename(exe)
    python = is_python(exe) or is_python(argv[0])
    if python and records(argv, environ):
        return ""
    if python and os.environ.get(STRICT):
        return f"{name}: a Python that does not record, with aidd installed from this checkout"
    if name in LAUNCHERS:
        return f"{name}: it starts another program this record cannot follow"
    if name == "git" and git_subcommand(argv) in GIT_METADATA:
        return ""
    folder = os.fsdecode(cwd) if isinstance(cwd, (bytes, str, os.PathLike)) else os.getcwd()
    inside = relative(git_folder(argv, folder) if name == "git" else folder) is not None
    if inside and name == "git" and git_subcommand(argv) == "ls-files" and LS_FILES_CONTENT.isdisjoint(argv):
        return LISTS_CHECKOUT
    if inside and not folder_free(name, argv):
        return f"{name} {' '.join(argv[1:3])[:40]}: it runs inside the checkout"
    if relative(exe) is not None or any(names_checkout(a) for a in argv) or script_names_checkout(exe):
        return f"{name}: its program or arguments name the checkout"
    if any(script_names_checkout(a) for a in argv[1:] if is_file(a)):
        return f"{name}: a script it runs names the checkout"
    for key, value in environ.items():
        if key in QUIET_ENV or (key == "PYTHONPATH" and HERE in value.split(os.pathsep)):
            continue
        if names_checkout(value):
            return f"{name}: its environment names the checkout in {key}"
    if (python or name in SHELLS) and not [a for a in argv[1:] if not a.startswith("-")]:
        return f"{name}: it reads its commands from standard input"
    return ""


def from_discovery() -> bool:
    """Whether unittest's discovery made this call: it lists the tests folder for the one file it runs."""
    frame = sys._getframe(3)
    for _ in range(12):
        if frame is None:
            return False
        if frame.f_globals.get("__name__") == "unittest.loader":
            return True
        frame = frame.f_back
    return False


def start(log: str, main: bool) -> None:
    """Record this process's reads of the checkout in `log`. `main` is the test file's own process, whose discovery
    lists every test file, which is not a read of the test."""
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    seen: set[str] = set()

    def note(entry: str) -> None:
        if entry not in seen:
            seen.add(entry)
            os.write(fd, (entry + "\n").encode("utf-8", "surrogateescape"))

    def read(path: object, how: str = "") -> None:
        rel = relative(path)
        if rel is None or rel.startswith(OWN):  # a change to this folder runs every file anyway
            return
        if main and how and rel.startswith("tests") and from_discovery():
            return
        note(rel.rstrip(os.sep) + "/" if how == "/" else how + source_path(rel))

    def cannot_see(why: str) -> None:
        if why == LISTS_CHECKOUT:
            note(why)
        elif why:
            note("*")
            note("# " + why)

    def hook(event: str, args: tuple) -> None:
        try:
            if event == "open":
                mode, flags = args[1], args[2]
                if isinstance(mode, str):
                    writes = any(c in mode for c in "wax") and "+" not in mode
                else:
                    writes = isinstance(flags, int) and flags & 3 == os.O_WRONLY
                if not writes:
                    read(args[0])
            elif event in ("os.listdir", "os.scandir"):
                read("." if args[0] is None else args[0], "/")
            elif event == "subprocess.Popen":
                cannot_see(unseen(args[0], args[1], args[2], args[3]))
            elif event in ("os.posix_spawn", "os.exec"):
                cannot_see(unseen(args[0], args[1], None, args[2]))
            elif event == "os.spawn":
                cannot_see(unseen(args[1], args[2], None, args[3]))
            elif event == "os.system":
                cannot_see(unseen("sh", ["sh", "-c", args[0]], None, None))
        except Exception as error:  # a hook that fails must not change the test; it records that it cannot tell
            cannot_see(f"the record failed on {event}: {error!r}")

    real_lstat = os.lstat

    def stat(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        read(path, "?")
        return REAL_STAT(path, *args, **kwargs)

    def lstat(path, *args, **kwargs):  # type: ignore[no-untyped-def]
        read(path, "?")
        return real_lstat(path, *args, **kwargs)

    os.stat, os.lstat = stat, lstat  # existence checks: os.path.exists, Path.is_file, and the rest
    for module in list(sys.modules.values()):  # what loaded before this record started
        read(getattr(module, "__file__", None))
    sys.addaudithook(hook)


def run_next_sitecustomize() -> None:
    """The interpreter's own `sitecustomize`, which this module hides by its name (Homebrew's sets sys.executable)."""
    import importlib.machinery
    import importlib.util

    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", [p for p in sys.path if os.path.abspath(p or ".") != HERE])
    if spec is not None and spec.loader is not None:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


if __name__ == "sitecustomize":  # at start-up; a test that loads this file under another name only reads its rules
    if os.environ.get(LOG):
        start(os.environ[LOG], main=os.environ.pop(MAIN, "") == "1")
    run_next_sitecustomize()
