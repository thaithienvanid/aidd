"""Shared test helpers. Every test module imports this first: it puts src/ on sys.path and makes the run hermetic.

Hermetic means the suite passes the same way on a developer's laptop, inside an agent's shell, and in CI:

- Variables that change what aidd does (AIDD_*, the agent markers Claude Code and other harnesses export, Orca's ORCA_*, the
  GitHub and GitLab CI variables) are removed from the environment once, here, for the whole process and every
  subprocess a test starts. AIDD_OFFLINE=1 stays set, so nothing reaches the network. A test that needs one of them
  sets it with `mock.patch.dict(os.environ, ...)`.
- The clock, the language, the hash seed, and the user folders are pinned: TZ=UTC, LC_ALL=C.UTF-8, PYTHONHASHSEED=0 (for
  every Python a test starts; tests/run.py sets it for each test file too), and the XDG folders under a temporary one.
  A test that needs another value sets it with `mock.patch.dict(os.environ, ...)`.
- git and gh read a configuration this module writes (a test identity, no signing, no system config) instead of the
  developer's global one, so `operator_login` and commit signing do not depend on the machine.
- `repo.installed_harnesses` (init's hint about agents this machine has) looks at an empty home directory and an empty
  PATH unless a test passes its own; a test that wants the real probes calls `helpers.real_installed_harnesses`.
  `repo.detect_harnesses` reads only the repository, so it needs nothing.
- No test reaches the network: a name lookup or a connection to a host other than this machine raises NetworkUsed,
  and the run fails at exit when one happened. A test of a fetch mocks the fetcher or serves it from 127.0.0.1.
"""

import atexit
import contextlib
import datetime
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
# How long a shared helper waits for a child it starts. A hung child fails the test as subprocess.TimeoutExpired instead
# of hanging the run; a caller whose child is slow passes a larger `timeout=`.
SUBPROCESS_TIMEOUT = 60
# aidd-team's prototype tool: the starting design a Spec's prototype is written from, the viewer every design is shown
# in, and the product prototype's starting sitemap.
PROTOTYPE_TOOL = ROOT / "plugins" / "aidd-team" / "tools" / "prototype"
PROTOTYPE_DESIGN = PROTOTYPE_TOOL / "design.html"
PROTOTYPE_VIEWER = PROTOTYPE_TOOL / "viewer.html"
PROTOTYPE_EXAMPLE = PROTOTYPE_TOOL / "examples" / "showcase.html"  # a complete design to learn from, never a start


def copy_showcase_images(folder) -> None:
    """The showcase's drawings beside a copy of it in `folder`: its fixtures name them as files beside the design."""
    import shutil

    shutil.copytree(PROTOTYPE_TOOL / "examples" / "sitters", Path(folder) / "sitters", dirs_exist_ok=True)


# The routing sentences: the opening of `loop.entry` in schemas/roles.json, copied word for word into the aidd skill,
# its routes reference, and the docs generated from the entry. Two sentences, so each meets the plain-language rule.
ROUTING = "A change's route is a property of the change. aidd advises the minimum from the paths it touches, and the author may declare higher."
sys.path.insert(0, str(ROOT / "src"))

# What an agent harness, a CI runner, or a developer's shell may export that changes aidd's behavior.
HERMETIC_PREFIXES = ("AIDD_", "ANTIGRAVITY_", "CI_", "CLAUDE_CODE_", "GITHUB_", "GITLAB_", "ORCA_")
# Every agent's own session variable (`AGENT_ENV`) is one, because `aidd init` names the agent of the session it runs in.
from aidd.config import harnesses as _harnesses  # noqa: E402

HERMETIC_NAMES = frozenset({"AI_AGENT", "CI", "GH_HOST", "GH_TOKEN", "GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE", "RELEASE_APPROVAL", *_harnesses.AGENT_ENV})


def hermetic_environ(env: dict[str, str] | None = None) -> dict[str, str]:
    """`env` (default: os.environ) without the variables above, and with AIDD_OFFLINE=1."""
    env = dict(os.environ if env is None else env)
    out = {k: v for k, v in env.items() if k not in HERMETIC_NAMES and not k.startswith(HERMETIC_PREFIXES)}
    # The tests never reach GitHub: `aidd init` and `upgrade` keep the release tag instead of resolving it (an unpacked
    # sdist has no git checkout, so without this they would ask GitHub for the release's commit).
    out["AIDD_OFFLINE"] = "1"
    return out


class NetworkUsed(RuntimeError):
    """A unit test looked up or connected to a host that is not this machine. Not an OSError, so code that treats a
    network error as "unreachable" cannot hide it."""


# Every blocked lookup or connection, in order. The run fails at exit when one happened, even if code caught the error.
NETWORK_USES: list[str] = []
_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect


def _local(host: object) -> bool:
    if host is None or host in ("", b""):
        return True
    name = (host.decode() if isinstance(host, bytes) else str(host)).split("%", 1)[0].strip("[]").lower()
    if name == "localhost" or name.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _blocked(what: str) -> NetworkUsed:
    NETWORK_USES.append(what)
    return NetworkUsed(f"a unit test reached the network ({what}); mock the fetch or serve it from 127.0.0.1")


def _numeric(host: object) -> bool:
    """An address written as numbers: looking it up sends nothing, so an SSRF check may resolve it."""
    try:
        ipaddress.ip_address((host.decode() if isinstance(host, bytes) else str(host)).split("%", 1)[0].strip("[]"))
        return True
    except ValueError:
        return False


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not (_local(host) or _numeric(host)):
        raise _blocked(f"lookup of {host!r}")
    return _real_getaddrinfo(host, *args, **kwargs)


def _guarded_connect(self, address):
    if isinstance(address, tuple) and not _local(address[0]):
        raise _blocked(f"connection to {address[0]!r}")
    return _real_connect(self, address)


def _fail_if_the_network_was_used() -> None:
    if NETWORK_USES:
        sys.stdout.flush()
        sys.stderr.write("\nunit tests reached the network, which they never may:\n" + "".join(f"  {x}\n" for x in NETWORK_USES))
        sys.stderr.flush()
        os._exit(1)


socket.getaddrinfo = _guarded_getaddrinfo
socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
# Registered before any other exit hook, so it runs last and the others still clean up.
atexit.register(_fail_if_the_network_was_used)

_SANDBOX = Path(tempfile.mkdtemp(prefix="aidd-tests-"))
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)
EMPTY_HOME = _SANDBOX / "home"
EMPTY_PATH = _SANDBOX / "bin"
EMPTY_HOME.mkdir()
EMPTY_PATH.mkdir()
(_SANDBOX / "gh").mkdir()
_GITCONFIG = _SANDBOX / "gitconfig"
# No automatic maintenance: a commit may start a detached `git repack` (git 2.55 does so for a fresh repository of a few
# dozen loose objects), which then writes into a test's temporary repository while the test removes it.
_GITCONFIG.write_text(
    "[user]\n\tname = aidd tests\n\temail = tests@example.com\n[init]\n\tdefaultBranch = main\n"
    "[commit]\n\tgpgsign = false\n[tag]\n\tgpgsign = false\n[advice]\n\tdetachedHead = false\n"
    "[maintenance]\n\tauto = false\n[gc]\n\tauto = 0\n",
    encoding="utf-8",
)

# Every identity form any check once refused as an approver, a waiver's approver, or an Intent's agreer: bare, tenant-qualified,
# bot, known account, known address, and each of them in the name or the address of a `Name <email>`, with lookalike letters.
AGENT_APPROVERS = (
    "agent:developer",
    "acme:agent:developer",
    "role:architect",  # a team role, which is no person
    "acme:role:architect",
    "role:architect <d@example.com>",
    "claude[bot]",
    "@claude",
    "@devin",
    "ghost",
    "github-actions",
    "copilot-swe-agent",
    "email:noreply@anthropic.com",
    "Claude <noreply@anthropic.com>",
    "agent:developer <d@example.com>",
    "acme:agent:x <x@example.com>",
    "claude[bot] <x@example.com>",
    "Maya <49699333+dependabot[bot]@users.noreply.github.com>",
    "\uff23laude <x@example.com>",  # a fullwidth C
    "\u0421laude <x@example.com>",  # a Cyrillic C
    "cl\u0430ude",  # a Cyrillic a
    "@clau\u0331de",  # a combining macron below no letter holds
    "agent\u0301:dev",  # an accent on the `t`
    "<noreply@anthropic.com>",  # an agent's address with no name
    "Bob <noreply+x@anthropic.com>",  # and with a +tag
    "ag\u00e9nt:developer <d@example.com>",  # an accent on the `e`
    "acme:ag\u00e9nt:x <x@example.com>",
    "agent\u0301:dev <d@example.com>",
    "email:noreply@anthropi\uff43.com",  # a fullwidth c in the domain
    "Bob <noreply@\u0430nthropic.com>",  # a Cyrillic a in it
    "Bob <noreply@anthro\u200bpic.com>",  # a zero-width space in it
    "@cl\u0251ude",  # an IPA alpha
    "\u1d04odex",  # a small capital c
    "Cl\u0251ude <x@example.com>",
    "@cl\u0261ude",  # an IPA g
)
# People, in every form an approver is written: accents on Latin letters are a name, never a sign of an agent, and a name that
# only holds an agent's word is still a person.
PEOPLE_APPROVERS = (
    "@maya",
    "@org/leads",
    "email:maya@example.com",
    "Van Hoang <van@example.com>",
    "Jos\u00e9 Garc\u00eda <jose@example.com>",
    "Nguy\u1ec5n V\u0103n <van@example.com>",
    "Zo\u00eb <z@example.com>",
    "S\u00f8ren \u00d8stergaard <s@example.dk>",
    "Devin Lee <devin@example.com>",
    "Claude Martin <cm@example.com>",
    "Role Lee <r@example.com>",  # `role` is a word in a name, not a prefix
    "@role-lee",
    "\u0141ukasz Kowalski <l@example.pl>",
    "\u0110\u1ed7 Anh <d@example.vn>",
    "Stra\u00dfe <s@example.de>",
    "\u00c6gir <a@example.is>",
    "\u0152dipe <o@example.fr>",
    "\u00de\u00f3r <t@example.is>",
    "\u0131smail <i@example.tr>",
    "\u0126ussein <h@example.mt>",
    "\u018fli <e@example.az>",
    "K\u0254fi <k@example.com>",
    "Ad\u00e9\u1e63\u1ecd\u0300l\u00e1 Ogun <a@example.com>",
    "Ol\u00fam\u00edd\u00e9 \u1ecc\u1ecd\u0301 <o@example.com>",
    "\u0418\u0432\u0430\u043d \u041f\u0435\u0442\u0440\u043e\u0432 <i@example.ru>",
)
# Read before the lines below remove every AIDD_ variable: the viewer's browser tests run only when a person opts in, and
# the axe test reads axe-core from AIDD_AXE_JS when a person names another copy.
BROWSER_TESTS_OPTED_IN = os.environ.get("AIDD_BROWSER_TESTS") == "1"
AXE_JS = os.environ.get("AIDD_AXE_JS", "")
_clean = hermetic_environ()
os.environ.clear()
os.environ.update(_clean)
# The home folder `aidd init` writes the user launcher into (~/.aidd/bin/aidd): never the real one. REAL_HOME is for a
# test that needs what the real one holds, such as the Pythons uv installed.
REAL_HOME = os.environ.get("HOME", "")
USER_HOME = _SANDBOX / "user"
USER_HOME.mkdir()
os.environ["HOME"] = str(USER_HOME)
# Claude Code's user folder (its settings name the plugins enabled for this user, which `aidd doctor` reads): empty.
os.environ.update(
    {
        "GIT_CONFIG_GLOBAL": str(_GITCONFIG),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",  # git fails instead of waiting for a password
        "GH_CONFIG_DIR": str(_SANDBOX / "gh"),
        "CLAUDE_CONFIG_DIR": str(_SANDBOX / "claude"),
        # The same answer on every machine: the time zone, the language of git's messages and the sort order, and the
        # order of a set's strings in every Python a test starts.
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        # The folders a program keeps its cache, settings, and state in: temporary, never the developer's own.
        "XDG_CACHE_HOME": str(_SANDBOX / "xdg" / "cache"),
        "XDG_CONFIG_HOME": str(_SANDBOX / "xdg" / "config"),
        "XDG_DATA_HOME": str(_SANDBOX / "xdg" / "data"),
        "XDG_STATE_HOME": str(_SANDBOX / "xdg" / "state"),
    }
)
if hasattr(time, "tzset"):
    time.tzset()  # this process reads TZ once, so tell it

from aidd.cli import app  # noqa: E402
from aidd.setup import adoption  # noqa: E402


real_installed_harnesses = adoption.installed_harnesses


def _installed_harnesses(*, home=None, path=None):
    return real_installed_harnesses(home=EMPTY_HOME if home is None else home, path=str(EMPTY_PATH) if path is None else path)


_HARNESS_PATCH = mock.patch.object(adoption, "installed_harnesses", _installed_harnesses)
_HARNESS_PATCH.start()


def _stop_global_patches() -> None:
    """Undo what this module patched for the whole process, so nothing it started outlives the run."""
    _HARNESS_PATCH.stop()
    socket.getaddrinfo = _real_getaddrinfo
    socket.socket.connect = _real_connect  # type: ignore[method-assign]


atexit.register(_stop_global_patches)


# An unpacked sdist has no .git: tests that need the repository's own history skip there, and tests
# that only need its files walk the tree instead (CI runs the sdist's tests in exactly that state).
IN_GIT_CHECKOUT = (ROOT / ".git").exists()
_SKIP_DIRS = {".git", ".claude", "node_modules", ".venv", "venv", "dist", "build", "__pycache__", ".mypy_cache", ".ruff_cache", ".tox"}


def repo_files() -> list[str]:
    """The repository's files, relative to ROOT: from git when there is an index, else by walking the tree."""
    if IN_GIT_CHECKOUT:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=SUBPROCESS_TIMEOUT).stdout.split("\n")
        files = [f for f in out if f]
        if files:
            return files
    return sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and not _SKIP_DIRS & set(p.relative_to(ROOT).parts))


def language_columns() -> dict[str, str]:
    """Each language of schemas/languages.json with the extension of its usual source file, without the dot, in the table's
    order. The one list of languages for a test that writes a file in every language, so no test keeps a list of its own."""
    rows = json.loads((ROOT / "schemas" / "languages.json").read_text(encoding="utf-8"))["languages"]
    return {name: row["extensions"][0].removeprefix(".") for name, row in rows.items()}


def source_of(module: str) -> str:
    """The source text of an aidd module named by its dotted path (`aidd.risk.rules`), wherever its file lives."""
    import importlib

    path = importlib.import_module(module).__file__
    assert path is not None, module
    return Path(path).read_text(encoding="utf-8")


def modules_under(package: str) -> tuple[str, ...]:
    """A package and every module under it, by dotted name (`aidd.risk.rules`, `aidd.risk.rules.approvals`, ...)."""
    import importlib

    path = importlib.import_module(package).__file__
    assert path is not None, package
    if Path(path).name != "__init__.py":
        return (package,)
    folder = Path(path).parent
    return tuple(
        ".".join([package, *p.relative_to(folder).with_suffix("").parts]).removesuffix(".__init__")
        for p in sorted(folder.rglob("*.py"))
        if p.name != "__main__.py"
    )


def git(cwd, *args, env: dict[str, str] | None = None, timeout: float = SUBPROCESS_TIMEOUT) -> str:
    """Run git in `cwd`; fail the test on a non-zero exit or after `timeout` seconds. Returns stdout without the trailing newline.
    Its stdin is empty: a program a hostile fixture names, such as an fsmonitor that reads stdin, would else wait on the test
    runner's open pipe until the timeout, which made a test fail only under `tests/run.py`."""
    run = subprocess.run
    return run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8", env=env, timeout=timeout, stdin=subprocess.DEVNULL
    ).stdout.rstrip("\n")


def src_pythonpath(env: dict[str, str] | None = None) -> str:
    """A PYTHONPATH for a child that runs this checkout's aidd: its src/, and tests/run.py's read record when the run
    records (on `env`'s PYTHONPATH, default os.environ's), so the child's reads count as the test's."""
    recorder = str(ROOT / "tests" / "record_reads")
    keep = [recorder] if recorder in (os.environ if env is None else env).get("PYTHONPATH", "").split(os.pathsep) else []
    return os.pathsep.join([str(ROOT / "src"), *keep])


def aidd_subprocess(
    *args: str, cwd, env: dict[str, str] | None = None, input: str | None = None, timeout: float = SUBPROCESS_TIMEOUT
) -> subprocess.CompletedProcess:
    """`python -m aidd <args>` in a child process, with `src_pythonpath` on PYTHONPATH. It raises subprocess.TimeoutExpired
    after `timeout` seconds."""
    base = os.environ if env is None else env
    done = subprocess.run(
        [sys.executable, "-m", "aidd", *args],
        cwd=cwd,
        env={**base, "PYTHONPATH": src_pythonpath(base)},
        input=input,
        stdin=None if input is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )
    return done


def aidd_here(*args: str, cwd, input: str | None = None) -> subprocess.CompletedProcess:
    """`aidd <args>` in this process, in `cwd`, as `aidd_subprocess` would run it in a child with no terminal: its exit
    code and what it printed on each stream. It saves the start-up of a child, so a test uses it where the process is not
    what it tests (a test of the launcher, the hooks as a harness runs them, isolation, or `-I` keeps the child)."""
    import io

    out, err = io.StringIO(), io.StringIO()
    code: object = 0
    with contextlib.chdir(cwd), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), mock.patch.object(sys, "stdin", io.StringIO(input or "")):
        try:
            code = app.main(list(args))
        except SystemExit as stop:  # argparse ends a usage error this way, as `python -m aidd` exits
            code = stop.code
    return subprocess.CompletedProcess(["aidd", *args], code if isinstance(code, int) else int(code is not None), out.getvalue(), err.getvalue())


def run_cli(*argv: str) -> tuple[int, str]:
    """`aidd <argv>` in this process: its exit code and everything it printed."""
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = app.main(list(argv))
    return code, out.getvalue()


def run_eval_cli(*argv: str) -> tuple[int, str]:
    """`run_cli` for a test of `aidd eval`: a run that records names a model, because a record without one is refused."""
    named = "--record" not in argv or "--model-label" in argv or argv[:1] != ("eval",)
    return run_cli(*argv, *(() if named else ("--model-label", "test-model")))


@contextlib.contextmanager
def fake_opencode(version: str = "2.0.0"):
    """A fake `opencode` first on PATH for the block, answering `--version` with `version`, so a doctor probe never starts a
    real harness from the machine's PATH. It writes nothing outside a temp folder and restores PATH after."""
    with tempfile.TemporaryDirectory() as d:
        # On Windows, PATH finds a program by its PATHEXT extension, so the fake is also an `opencode.cmd`.
        program = Path(d) / "opencode"
        program.write_text(f"#!/bin/sh\necho {version}\n", encoding="utf-8")
        program.chmod(0o755)
        (Path(d) / "opencode.cmd").write_text(f"@echo {version}\r\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"PATH": d + os.pathsep + os.environ.get("PATH", "")}):
            yield program


def make_repo(root: Path, profile: str = "team", *, spec: str | None = None, status: str | None = None, branch: str | None = "feat", **init) -> Path:
    """A git repository at `root` that adopted aidd with `profile` on main, then (with `branch`) a branch off it.

    `spec` names a Spec path (such as "specs/SPEC-220.md") written from `SAMPLE_SPEC`, uncommitted, on the branch;
    `status` stores that status in it (`approved`: Spec approval happened, so its Tasks may be built).

    The first repository for a set of arguments is kept, and a later call copies it (`_REPO_TEMPLATES`)."""
    root = Path(root)
    fresh = not root.exists() or not any(root.iterdir())
    key = (profile, branch, repr(sorted(init.items())), tuple(sorted(os.environ.items())), os.getcwd(), datetime.date.today())
    kept = _REPO_TEMPLATES.get(key) if fresh else None
    if kept is not None and _unpatched(kept[1]):
        shutil.copytree(kept[0], root, symlinks=True, dirs_exist_ok=True)
    else:
        _build_repo(root, profile, branch, init)
        if fresh:
            template = Path(tempfile.mkdtemp(dir=_SANDBOX)) / "repo"
            shutil.copytree(root, template, symlinks=True)
            _REPO_TEMPLATES[key] = (template, _module_names())
    if spec:
        rel = spec.partition(":")[2] or spec
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        text = SAMPLE_SPEC.replace("SPEC-220", Path(rel).stem)
        target.write_text(text.replace("\nroute: ", f'\nstatus: "{status}"\nroute: ', 1) if status else text, encoding="utf-8")
    return root


def _build_repo(root: Path, profile: str, branch: str | None, init: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    init.setdefault("approvers", ["@x"])
    init.setdefault("skill", False)
    adoption.init(
        root, adoption.InitOptions(profile=profile, ci=init.pop("ci", "none"), links=init.pop("links", []), harnesses=init.pop("harnesses", []), **init)
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "day 0")
    if branch:
        git(root, "checkout", "-qb", branch)


# Each `make_repo` repository built so far, by its arguments, the environment, the working folder, and the day: its copy
# and the names its modules held then. A copy costs a tenth of a build (git init, aidd's init, and a commit), and each
# test still gets its own repository.
_REPO_TEMPLATES: dict[tuple, tuple[Path, dict[tuple[str, str], object]]] = {}
# The modules aidd's init reads through: aidd's own, and the standard ones a test may patch around `make_repo`.
_PATCHABLE = ("aidd", "datetime", "getpass", "os", "pathlib", "platform", "posixpath", "shutil", "subprocess", "tempfile", "time")
_GONE = object()


def _module_names() -> dict[tuple[str, str], object]:
    """Each name those modules hold, and its value. A test that patches one, as `mock.patch` does, changes it."""
    modules = [(m, mod) for m, mod in list(sys.modules.items()) if m.split(".", 1)[0] in _PATCHABLE and mod is not None]
    return {(m, k): v for m, mod in modules for k, v in list(vars(mod).items())}


def _unpatched(names: dict[tuple[str, str], object]) -> bool:
    """Whether every name still holds the same object (`is`: the record keeps each alive, so no other takes its id), so
    a copy of a repository built then is what a build now makes."""
    return all(vars(sys.modules[m]).get(k, _GONE) is v if m in sys.modules else False for (m, k), v in names.items())


@contextlib.contextmanager
def adopted_repo(profile: str = "team", **kwargs):
    """A temporary `make_repo` repository as the working directory, for a test of a command that reads git state: it
    passes outside a git checkout of aidd too (an unpacked sdist, an export), where ROOT has no .git."""
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp).resolve() / "repo", profile, **kwargs)
        with contextlib.chdir(root):
            yield root


class RepoTemplateCase(unittest.TestCase):
    """A repository built once per class by `build_template(root)`; each test works on its own copy at `self.root`
    (resolved, so it compares equal to what git prints), inside the temporary directory `self.tmp`."""

    @classmethod
    def build_template(cls, root: Path) -> None:
        raise NotImplementedError

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._template_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._template_dir.cleanup)
        cls._template = Path(cls._template_dir.name).resolve() / "repo"
        cls._template.mkdir()
        cls.build_template(cls._template)

    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / "repo"
        shutil.copytree(self._template, self.root, symlinks=True)


_BUILT: dict[tuple, Path] = {}


def build_once(key: tuple, root, build) -> None:
    """The repository `build()` makes at `root`, built the first time this process asks for `key` and copied into
    `root` every later time: for a journey's setup that several tests start from. `key` names everything the build
    depends on (`repo_state` names where it starts); the copy has the commits, refs, and files the build made."""
    root = Path(root)
    built = _BUILT.get(key)
    if built is None:
        build()
        built = _SANDBOX / "built" / str(len(_BUILT))
        shutil.copytree(root, built, symlinks=True)
        _BUILT[key] = built
        return
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(built, root, symlinks=True)


def repo_state(root) -> tuple[str, ...]:
    """What a build on top of the repository at `root` starts from, for `build_once`'s key: its commit, its working
    tree's changes, and every ref."""
    return tuple(git(root, *args) for args in (("rev-parse", "HEAD"), ("status", "--porcelain"), ("for-each-ref",)))


_EXECUTABLES = _SANDBOX / "executables"
# A fake shell program's one shim: it runs the fake's own text, from the plain file beside it (`<path>.body`), in
# its own shell, so `$0`, `$@`, `exit`, and `exec` mean what they mean in a script. It fails loudly without that file.
# A `$0` with no slash would make `.` search PATH for the text, so the shim gives it one.
FAKE_PROGRAM_SHIM = (
    '#!/bin/sh\n[ -f "$0.body" ] || { echo "fake $0: its text $0.body is missing" >&2; exit 127; }\ncase $0 in */*) b=$0.body;; *) b=./$0.body;; esac\n. "$b"\n'
)
# Kept across runs in __pycache__, which git ignores, so macOS checks it once on this machine, never once a run.
_LAUNCHER = ROOT / "tests" / "__pycache__" / "fake-launcher"


def _kept_launcher() -> Path | None:
    """The launcher, written again when it is missing or was changed (its text or its mode); None when it cannot be."""
    try:
        if _LAUNCHER.read_text(encoding="utf-8") == FAKE_PROGRAM_SHIM and _LAUNCHER.stat().st_mode & 0o777 == 0o755:
            return _LAUNCHER
    except OSError:
        pass
    try:
        _LAUNCHER.parent.mkdir(exist_ok=True)
        fresh = _LAUNCHER.with_name(f"fake-launcher-{os.getpid()}")
        fresh.write_text(FAKE_PROGRAM_SHIM, encoding="utf-8")
        fresh.chmod(0o755)
        os.replace(fresh, _LAUNCHER)  # whole, even when several test files write it at once
        return _LAUNCHER
    except OSError:
        return None


def write_executable(path: Path, text: str) -> Path:
    """`text` at `path` as an executable file (mode 755), for a fake program a test runs. macOS checks a new executable
    file the first time it runs, which costs a fifth of a second or more, and far more while many tests start files at
    once, and a hard link is the same file. So a shell script (`#!/bin/sh`) is a hard link to FAKE_PROGRAM_SHIM, kept across
    runs, with its text in `<path>.body`; another text is one file for the whole run, and `path` a hard link to it. The
    file is shared, so a test that changes its fake (its text or its mode) writes a new one with this function instead of
    editing it in place. For the same reason an edit in place, or an identity check (`os.path.samefile`, `test -ef`), sees
    every shell fake, and every fake of one text, as a single file: tell fakes apart by what they print."""
    import hashlib

    path = Path(path)
    launcher = _kept_launcher() if text.startswith("#!/bin/sh\n") and os.name == "posix" else None
    if launcher is not None:
        path.with_name(path.name + ".body").write_text(text, encoding="utf-8")
        kept = launcher
    else:
        _EXECUTABLES.mkdir(exist_ok=True)
        kept = _EXECUTABLES / hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not kept.exists():
            kept.write_text(text, encoding="utf-8")
            kept.chmod(0o755)
    path.unlink(missing_ok=True)
    try:
        os.link(kept, path)
    except OSError:  # another file system: a copy, which macOS checks again
        shutil.copy2(kept, path)
    return path


# Test-only helpers: nothing in src/ uses them, so they live here rather than in the package.


def open_work(root, today=None, include_done: bool = False) -> list[dict]:
    """`aidd status`: every open work item with its next step."""
    from aidd import config, workitems

    cfg = config.load_file(config.CONFIG_PATH, str(root)) if (Path(root) / config.CONFIG_PATH).is_file() else None
    return workitems.open_work(Path(root), cfg, today=today, include_done=include_done)["items"]


# A normal Spec that passes `aidd validate`, for a test that needs one on a branch (`make_repo(spec=...)`).
SAMPLE_SPEC = """---
type: spec
id: SPEC-220
title: Add a percentage discount
change_type: feat
route: normal
confidence: high
risk:
  summary: Shoppers with a code pay less at checkout.
  dimensions: []
  irreversible: false
rollback: revert the commit
tasks:
  - id: T1
    title: Apply the discount at checkout
    scope: ["src/checkout/"]
    risk: low
    proof: test `discount`
tests:
  files: ["tests/test_discount.py"]
  commands:
    - name: discount
      command: [python3, -m, unittest, tests.test_discount]
      new_behavior: true
      covers: [A1]
---

## Request

"Let shoppers use a percentage discount code at checkout."

## Context

The checkout totals the cart in `src/checkout/`.

## Acceptance

- A1: Given a cart of 100.00 and a 10% code, when the shopper applies it, then the total is 90.00.

## Design

One function applies the code to the total.

## Policy conflicts

none
"""


# The legacy handshake a test sends before a request with no 2026-07-28 `_meta`: without it, `aidd mcp` refuses such a
# request with -32602 instead of guessing its era.
MCP_LEGACY_INITIALIZE = {"jsonrpc": "2.0", "id": "initialize", "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}}}


def role_mcp_tools() -> list[str]:
    """The aidd MCP tools every role may call: those that read, compute, or check. `record`, which writes a record of
    history, goes only to a role that writes files."""
    from aidd.docsgen import pack_render

    return [prefix + name for prefix in pack_render.MCP_TOOL_PREFIXES for name in pack_render.MCP_READING_TOOLS]


def opencode_permissions(text: str) -> list[dict[str, str]]:
    """The `permissions:` rule list of an OpenCode agent file's front matter, in order: each rule's action, resource,
    and effect. A small reader for the block-list shape OpenCode documents, so a test checks what the rules say, not
    how they are spelled. A `permissions` key that is not a list of rules fails the test that reads it."""
    if not text.startswith("---\n"):
        raise ValueError("no front matter")
    front = text[4 : text.index("\n---", 4)].splitlines()
    rules: list[dict[str, str]] = []
    inside = False
    for line in front:
        if not line.startswith(" "):
            inside = line.rstrip() == "permissions:"
            continue
        if not inside:
            continue
        m = re.fullmatch(r"  (- |  )(action|resource|effect): (.+)", line)
        if not m:
            raise ValueError(f"not a permissions rule line: {line!r}")
        if m.group(1) == "- ":
            rules.append({})
        value = m.group(3).strip()
        rules[-1][m.group(2)] = json.loads(value) if value.startswith('"') else value
    return rules


def opencode_effect(rules: list[dict[str, str]], action: str, resource: str = "anything") -> str | None:
    """The effect OpenCode applies to `action` on `resource`: the last matching rule wins
    (https://opencode.ai/v2/docs/agents, "The last matching rule wins")."""
    import fnmatch

    found = [r["effect"] for r in rules if fnmatch.fnmatchcase(action, r["action"]) and fnmatch.fnmatchcase(resource, r["resource"])]
    return found[-1] if found else None


# The values Claude Code accepts in an agent's `model:` frontmatter, besides a full model ID (`claude-...`).
CLAUDE_CODE_MODEL_ALIASES = frozenset({"opus", "sonnet", "haiku", "fable", "inherit"})


def is_claude_code_model(value: str) -> bool:
    """True for an alias or `inherit`, or a full Claude model ID such as `claude-opus-5-5`."""
    return value in CLAUDE_CODE_MODEL_ALIASES or bool(re.fullmatch(r"claude-[a-z0-9]+(?:-[a-z0-9.]+)*(?:\[1m\])?", value))


# The two model tiers a role may carry (schemas/roles.json `tier`), and what each means.
TIER_MEANING = {
    "reasoning": "Decides, designs, or judges, or builds where a mistake is irreversible or invisible to tests. Use the strongest model the harness offers.",
    "execution": "Builds or writes inside a frozen Spec, or proposes what a human decides, where the tests, the reviewer, or a person catch the mistake. A mid-size model; a role is promoted only on eval evidence, and `[agents.models]` can set `inherit` to run it on the session's model instead.",
}

# Draft 2020-12 assertion keywords aidd.schema does not implement: a schema that used one would be silently looser.
KNOWN_IGNORED: frozenset[str] = frozenset(
    {
        "patternProperties",
        "dependentRequired",
        "dependentSchemas",
        "maxProperties",
        "minProperties",
        "unevaluatedProperties",
        "prefixItems",
        "contains",
        "unevaluatedItems",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)


def unsupported_keywords(schema_doc) -> set[str]:
    """Every KNOWN_IGNORED keyword a schema uses, at any depth."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k in KNOWN_IGNORED:
                    found.add(k)
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema_doc)
    return found


def validate_with(instance, schema_doc) -> list[str]:
    """Validate against an in-memory schema whose $refs are local (#/...)."""
    from aidd.kernel import json_schema

    errs: list[str] = []
    json_schema._check(instance, schema_doc, "$", schema_doc, errs)
    return errs


# ---- Facts a page states, checked without pinning its sentences ----------------------------------------------------

HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.M)
ANCHOR_ID = re.compile(r'<a id="([^"]+)"')


def slug(heading: str) -> str:
    """GitHub's anchor for a heading: code marks and emphasis stars dropped, underscores kept (`risk_rules`)."""
    text = re.sub(r"[`*]", "", heading).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return re.sub(r"\s", "-", text)


def anchors(path) -> set[str]:
    """Every anchor a Markdown page offers: its headings' slugs and its `<a id>` targets."""
    text = Path(path).read_text(encoding="utf-8")
    return {slug(h) for h in HEADING.findall(text)} | set(ANCHOR_ID.findall(text))


def sentences(text: str) -> list[str]:
    """A page's sentences, with its line breaks and list marks folded into spaces."""
    flat = " ".join(text.split())
    return [s for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*(\[])", flat) if s]


def says(text: str, *terms: str) -> bool:
    """Whether one sentence of `text` holds every term: a fact a page states, whatever words carry it. A term is a
    command, a key, or a word the fact turns on (`never`, `only`), so a rewrite keeps passing and a dropped fact fails."""
    return any(all(term in sentence for term in terms) for sentence in sentences(text))


# Mermaid's link arrows, the longer first: the solid `-->` and the dotted `-.->`.
MERMAID_ARROWS = ("-.->", "-->")


def mermaid_split(line: str) -> list[str | None]:
    """One Mermaid line split at its links, as `re.split` with groups would: [node, arrow, label or None, node, ...].
    A label is the `|"text"|` right after an arrow; the spaces around an arrow and its label go."""
    parts: list[str | None] = []
    current, i = "", 0
    while i < len(line):
        arrow = next((a for a in MERMAID_ARROWS if line.startswith(a, i)), None)
        if arrow is None:
            current += line[i]
            i += 1
            continue
        parts.append(current.rstrip())
        i += len(arrow)
        label = None
        end = line.find('"|', i + 2) if line.startswith('|"', i) else -1
        if end != -1 and '"' not in line[i + 2 : end]:
            label, i = line[i + 2 : end], end + 2
        while i < len(line) and line[i].isspace():
            i += 1
        parts += [arrow, label]
        current = ""
    parts.append(current)
    return parts


def mermaid_arrows(line: str) -> list[str]:
    """The arrows of one Mermaid line, in order: a chain `a --> b --> c` has two."""
    return [p for p in mermaid_split(line)[1::3] if p]
