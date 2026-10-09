"""Shared test helpers. Every test module imports this first: it puts src/ on sys.path and makes the run hermetic.

Hermetic means the suite passes the same way on a developer's laptop, inside an agent's shell, and in CI:

- Variables that change what aidd does (AIDD_*, the agent markers Claude Code and other harnesses export, Orca's ORCA_*, the
  GitHub and GitLab CI variables) are removed from the environment once, here, for the whole process and every
  subprocess a test starts. AIDD_OFFLINE=1 stays set, so nothing reaches the network. A test that needs one of them
  sets it with `mock.patch.dict(os.environ, ...)`.
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
import copy
import functools
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
# The routing sentences: the opening of `loop.entry` in schemas/roles.json, copied word for word into the aidd skill,
# its routes reference, and the docs generated from the entry. Three sentences, so each meets the plain-language rule.
ROUTING = (
    "A change's route is a property of the change. aidd computes the minimum from what it touches, the author may declare higher, "
    "and the gate enforces the higher of the two. The lane follows from the route."
)
sys.path.insert(0, str(ROOT / "src"))

# What an agent harness, a CI runner, or a developer's shell may export that changes aidd's behaviour.
HERMETIC_PREFIXES = ("AIDD_", "CI_", "GITHUB_", "GITLAB_", "CLAUDE_CODE_", "ORCA_")
HERMETIC_NAMES = frozenset({"CLAUDECODE", "AI_AGENT", "CI", "GH_TOKEN", "GH_HOST", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "RELEASE_APPROVAL"})


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
_clean = hermetic_environ()
os.environ.clear()
os.environ.update(_clean)
# Claude Code's user folder (its settings name the plugins enabled for this user, which `aidd doctor` reads): empty.
os.environ.update(
    {"GIT_CONFIG_GLOBAL": str(_GITCONFIG), "GIT_CONFIG_NOSYSTEM": "1", "GH_CONFIG_DIR": str(_SANDBOX / "gh"), "CLAUDE_CONFIG_DIR": str(_SANDBOX / "claude")}
)

from aidd import cli, evals, http, repo  # noqa: E402
from aidd.verify import verify  # noqa: E402

real_installed_harnesses = repo.installed_harnesses


def _installed_harnesses(*, home=None, path=None):
    return real_installed_harnesses(home=EMPTY_HOME if home is None else home, path=str(EMPTY_PATH) if path is None else path)


mock.patch.object(repo, "installed_harnesses", _installed_harnesses).start()


@functools.cache
def _example(name: str):
    return evals.load_example(ROOT / "examples" / name)


def example(name: str) -> dict:
    """A fresh, mutable copy of an example context."""
    return copy.deepcopy(_example(name)[0])


def decide(ctx: dict):
    return verify(ctx)


@functools.lru_cache(maxsize=1)
def replayed_corpus() -> tuple:
    """(name, decision, expected) for every case and mutation in examples/, verified once per test process: the
    suite's one replay of the corpus through the loader. Tests that need a decision's findings or record read it
    here; tests/test_cli.py still runs `aidd eval examples` once, as a smoke test of the CLI."""
    out = []
    for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "context.json").is_file()):
        ctx, expected = evals.load_example(case)
        out.append((case.name, verify(copy.deepcopy(ctx)), expected))
        for m in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
            data = json.loads(m.read_text(encoding="utf-8"))
            out.append((f"{case.name}/{m.stem}", verify(evals.apply_ops(copy.deepcopy(ctx), data["ops"])), data["expected"]))
    return tuple(out)


def rules(d, level: str) -> list[str]:
    return d.rules_at(level)


# An unpacked sdist has no .git: tests that need the repository's own history skip there, and tests
# that only need its files walk the tree instead (CI runs the sdist's tests in exactly that state).
IN_GIT_CHECKOUT = (ROOT / ".git").exists()
_SKIP_DIRS = {".git", "__pycache__", "dist", "build", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache", ".tox", ".claude"}


def repo_files() -> list[str]:
    """The repository's files, relative to ROOT: from git when there is an index, else by walking the tree."""
    if IN_GIT_CHECKOUT:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT).stdout.split("\n")
        files = [f for f in out if f]
        if files:
            return files
    return sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and not _SKIP_DIRS & set(p.relative_to(ROOT).parts))


def git(cwd, *args, env: dict[str, str] | None = None) -> str:
    """Run git in `cwd`; fail the test on a non-zero exit. Returns stdout without the trailing newline."""
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8", env=env).stdout.rstrip("\n")


def aidd_subprocess(*args: str, cwd, env: dict[str, str] | None = None, input: str | None = None) -> subprocess.CompletedProcess:
    """`python -m aidd <args>` in a child process, with this checkout's src/ on PYTHONPATH."""
    return subprocess.run(
        [sys.executable, "-m", "aidd", *args],
        cwd=cwd,
        env={**(os.environ if env is None else env), "PYTHONPATH": str(ROOT / "src")},
        input=input,
        stdin=None if input is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def run_cli(*argv: str) -> tuple[int, str]:
    """`aidd <argv>` in this process: its exit code and everything it printed."""
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


def make_repo(root: Path, profile: str = "team", *, spec: str | None = None, branch: str | None = "feat", **init) -> Path:
    """A git repository at `root` that adopted aidd with `profile` on main, then (with `branch`) a branch off it.

    `spec` names an example Spec (such as "02-normal-feature:specs/SPEC-220.md") written, uncommitted, on the branch."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    init.setdefault("approvers", ["@x"])
    init.setdefault("skill", False)
    repo.init(root, profile=profile, ci=init.pop("ci", "none"), links=init.pop("links", []), harnesses=init.pop("harnesses", []), **init)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "day 0")
    if branch:
        git(root, "checkout", "-qb", branch)
    if spec:
        name, _, rel = spec.partition(":")
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(example(name)["head_files"][rel], encoding="utf-8")
    return root


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


class FakeTransport:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, auth=None, data=None, headers=None, timeout=30, max_bytes=None):
        self.calls.append((method, url, auth, data))
        for prefix, (headers_out, body) in self.routes.items():
            if url.startswith(prefix):
                return 200, headers_out, body if isinstance(body, bytes) else json.dumps(body).encode()
        raise http.HttpError(404, url, "not found")


# Test-only helpers: nothing in src/ uses them, so they live here rather than in the package.


def open_work(root, filters=None, today=None, now=None) -> list[dict]:
    """`aidd list`: the next step of every open piece of work, from the base branch and every open branch."""
    from aidd import nextstep

    f = filters or nextstep.Filters()
    f.all = True
    return nextstep.plan(root, today, f, now)


def for_spec(rel: str, data: dict, status: str | None = None, *, committed: bool = False, approval: bool | None = None) -> dict:
    """The Spec's next step in `status` (its derived status; the stored one when not given), with its Tasks."""
    from aidd import nextstep, state

    approval = state.needs_approval(data, None) if approval is None else approval
    status = status or state.spec_status(data, approval=approval)
    blockers = state.blocked(data, status)
    return nextstep._spec_step(rel, data, status, committed=committed, approval=approval, blockers=blockers) | {
        "tasks": nextstep.tasks(data, status, approval=approval, blockers=blockers)
    }


def role_mcp_tools() -> list[str]:
    """The aidd MCP tools every role may call: all of them read, compute, or check, and none writes or approves."""
    from aidd import docs, mcp

    return [prefix + str(t["name"]) for prefix in docs.MCP_TOOL_PREFIXES for t in mcp.TOOLS]


# The values Claude Code accepts in an agent's `model:` frontmatter, besides a full model ID (`claude-...`).
CLAUDE_CODE_MODEL_ALIASES = frozenset({"opus", "sonnet", "haiku", "fable", "inherit"})


def is_claude_code_model(value: str) -> bool:
    """True for an alias or `inherit`, or a full Claude model ID such as `claude-opus-5-5`."""
    return value in CLAUDE_CODE_MODEL_ALIASES or bool(re.fullmatch(r"claude-[a-z0-9]+(?:-[a-z0-9.]+)*(?:\[1m\])?", value))


# The two model tiers a role may carry (schemas/roles.json `tier`), and what each means.
TIER_MEANING = {
    "reasoning": "Decides, designs, or judges, or builds where a mistake is irreversible or invisible to tests. Use the strongest model the harness offers.",
    "execution": "Builds or writes inside a frozen Spec, or proposes what a human decides, where the tests, the gate, or a human catch the mistake. A mid-size model; a role is promoted only on eval evidence, and `[agents.models]` can set `inherit` to run it on the session's model instead.",
}

# A Change Request block in Markdown: ```toml aidd ... ```.
CHANGE_BLOCK = re.compile(r"^[ ]{0,3}```[ \t]*toml[ \t]+aidd[ \t]*\r?\n(.*?)^[ ]{0,3}```[ \t]*$", re.M | re.S)

# Draft 2020-12 assertion keywords aidd.schema does not implement: a schema that used one would be silently looser.
KNOWN_IGNORED: frozenset[str] = frozenset(
    {
        "patternProperties",
        "dependentRequired",
        "dependentSchemas",
        "prefixItems",
        "contains",
        "propertyNames",
        "maxProperties",
        "minProperties",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "unevaluatedProperties",
        "unevaluatedItems",
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
    from aidd import schema

    errs: list[str] = []
    schema._check(instance, schema_doc, "$", schema_doc, errs)
    return errs
