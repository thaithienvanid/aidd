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
# aidd-team's prototype tool: the starting design a Spec's prototype is written from, the viewer every design is shown
# in, and the product prototype's starting sitemap.
PROTOTYPE_TOOL = ROOT / "plugins" / "aidd-team" / "tools" / "prototype"
PROTOTYPE_DESIGN = PROTOTYPE_TOOL / "design.html"
PROTOTYPE_VIEWER = PROTOTYPE_TOOL / "viewer.html"
PROTOTYPE_EXAMPLE = PROTOTYPE_TOOL / "examples" / "showcase.html"  # a complete design to learn from, never a start
# The routing sentences: the opening of `loop.entry` in schemas/roles.json, copied word for word into the aidd skill,
# its routes reference, and the docs generated from the entry. Three sentences, so each meets the plain-language rule.
ROUTING = (
    "A change's route is a property of the change. aidd computes the minimum from what it touches, the author may declare higher, "
    "and the gate enforces the higher of the two. The lane follows from the route."
)
sys.path.insert(0, str(ROOT / "src"))

# What an agent harness, a CI runner, or a developer's shell may export that changes aidd's behavior.
HERMETIC_PREFIXES = ("AIDD_", "ANTIGRAVITY_", "CI_", "GITHUB_", "GITLAB_", "CLAUDE_CODE_", "ORCA_")
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
# The identity a local approval the tests record carries (`email:<git user.email>`): a pool must hold it for it to count.
TEST_APPROVER = "email:tests@example.com"
# Read before the lines below remove every AIDD_ variable: the viewer's browser tests run only when a person opts in.
BROWSER_TESTS_OPTED_IN = os.environ.get("AIDD_BROWSER_TESTS") == "1"
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
    {"GIT_CONFIG_GLOBAL": str(_GITCONFIG), "GIT_CONFIG_NOSYSTEM": "1", "GH_CONFIG_DIR": str(_SANDBOX / "gh"), "CLAUDE_CONFIG_DIR": str(_SANDBOX / "claude")}
)

from aidd.evals import examples  # noqa: E402
from aidd.cli import app  # noqa: E402
from aidd.setup import adoption  # noqa: E402
from aidd.kernel import http  # noqa: E402
from aidd.config import baseline as _baseline  # noqa: E402


def enforce_by_default(case: unittest.TestCase) -> None:
    """For the rest of `case`, a profile with no `mode` enforces, as every profile did before solo and team started
    advisory: for tests of the mode's precedence (the base config, the CI input, AIDD_MODE), which need it unset."""
    patcher = mock.patch.object(_baseline, "profile_mode", return_value="enforce")
    patcher.start()
    case.addCleanup(patcher.stop)


from aidd import gate  # noqa: E402

real_installed_harnesses = adoption.installed_harnesses


def _installed_harnesses(*, home=None, path=None):
    return real_installed_harnesses(home=EMPTY_HOME if home is None else home, path=str(EMPTY_PATH) if path is None else path)


mock.patch.object(adoption, "installed_harnesses", _installed_harnesses).start()


@functools.cache
def _example(name: str):
    return examples.load_example(ROOT / "examples" / name)


# The commit an example's Spec approval names (`approval_commits`): its Spec reads there as at head.
SPEC_COMMIT = "5bec000000000000000000000000000000000001"


def example(name: str) -> dict:
    """A fresh, mutable copy of an example context."""
    return copy.deepcopy(_example(name)[0])


def decide(ctx: dict):
    return gate.decide(ctx)


@functools.lru_cache(maxsize=1)
def replayed_corpus() -> tuple:
    """(name, decision, expected) for every case and mutation in examples/, verified once per test process: the
    suite's one replay of the corpus through the loader. Tests that need a decision's findings or record read it
    here; tests/test_cli.py still runs `aidd eval examples` once, as a smoke test of the CLI."""
    out = []
    for case in sorted(p for p in (ROOT / "examples").iterdir() if (p / "context.json").is_file()):
        ctx, expected = examples.load_example(case)
        out.append((case.name, decide(copy.deepcopy(ctx)), expected))
        for m in sorted((case / "mutations").glob("*.json")) if (case / "mutations").is_dir() else []:
            data = json.loads(m.read_text(encoding="utf-8"))
            out.append((f"{case.name}/{m.stem}", decide(examples.apply_ops(copy.deepcopy(ctx), data["ops"])), data["expected"]))
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


def source_of(module: str) -> str:
    """The source text of an aidd module named by its dotted path (`aidd.gate.rules`), wherever its file lives."""
    import importlib

    path = importlib.import_module(module).__file__
    assert path is not None, module
    return Path(path).read_text(encoding="utf-8")


def modules_under(package: str) -> tuple[str, ...]:
    """A package and every module under it, by dotted name (`aidd.gate.rules`, `aidd.gate.rules.approvals`, ...)."""
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


def package_source(package: str) -> str:
    """The source text of a package and every module under it, one after another (a plain module: its own text)."""
    return "".join(source_of(m) for m in modules_under(package))


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
        code = app.main(list(argv))
    return code, out.getvalue()


def make_repo(root: Path, profile: str = "team", *, spec: str | None = None, status: str | None = None, branch: str | None = "feat", **init) -> Path:
    """A git repository at `root` that adopted aidd with `profile` on main, then (with `branch`) a branch off it.

    `spec` names an example Spec (such as "02-normal-feature:specs/SPEC-220.md") written, uncommitted, on the branch;
    `status` stores that status in it (`ready`: Spec approval happened, so its Tasks may be built)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    init.setdefault("approvers", ["@x"])
    init.setdefault("skill", False)
    # These repositories test the loop's rules as enforce mode applies them; a test of advisory mode passes enforce=False.
    init.setdefault("enforce", True)
    adoption.init(
        root, adoption.InitOptions(profile=profile, ci=init.pop("ci", "none"), links=init.pop("links", []), harnesses=init.pop("harnesses", []), **init)
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "day 0")
    if branch:
        git(root, "checkout", "-qb", branch)
    if spec:
        name, _, rel = spec.partition(":")
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        text = example(name)["head_files"][rel]
        target.write_text(text.replace("\nroute: ", f'\nstatus: "{status}"\nroute: ', 1) if status else text, encoding="utf-8")
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


def check_edit(root: str, rel: str, role: str | None = None, old_text: str | None = None, new_text: str | None = None):
    """`edit_check.check_edit` inside `git.memo()`, as the guard's hook runs it (the hook also runs `git.system_only()`,
    which no test here needs), so a read-only git query the check asks twice runs once. The check writes nothing, so its
    answer is the same; only the time it takes changes."""
    from aidd.guard import edit_check
    from aidd.kernel import git as gitutil

    with gitutil.memo():
        return edit_check.check_edit(root, rel, role, old_text, new_text)


def check_agent_edit(root: str, rel: str, event: dict, **kwargs):
    """`edit_check.check_agent_edit` inside `git.memo()`, as `check_edit` is."""
    from aidd.guard import edit_check
    from aidd.kernel import git as gitutil

    with gitutil.memo():
        return edit_check.check_agent_edit(root, rel, event, **kwargs)


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


def write_executable(path: Path, text: str) -> Path:
    """`text` at `path` as an executable file (mode 755), for a fake program a test runs. Each distinct text is one file
    for the whole run, and `path` a hard link to it: macOS checks a new executable file the first time it runs, which
    costs a fifth of a second or more, and a hard link is the same file. The file is shared, so a test that changes its
    fake (its text or its mode) writes a new one with this function instead of editing it in place."""
    import hashlib

    _EXECUTABLES.mkdir(exist_ok=True)
    kept = _EXECUTABLES / hashlib.sha256(text.encode("utf-8")).hexdigest()
    if not kept.exists():
        kept.write_text(text, encoding="utf-8")
        kept.chmod(0o755)
    path = Path(path)
    path.unlink(missing_ok=True)
    try:
        os.link(kept, path)
    except OSError:  # another file system: a copy, which macOS checks again
        shutil.copy2(kept, path)
    return path


class FakeTransport:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, auth=None, data=None, headers=None, timeout_seconds=30, max_bytes=None):
        self.calls.append((method, url, auth, data))
        for prefix, (headers_out, body) in self.routes.items():
            if url.startswith(prefix):
                return 200, headers_out, body if isinstance(body, bytes) else json.dumps(body).encode()
        raise http.HttpError(404, url, "not found")


# Test-only helpers: nothing in src/ uses them, so they live here rather than in the package.


def open_work(root, filters=None, today=None, now=None) -> list[dict]:
    """`aidd list`: the next step of every open piece of work, from the base branch and every open branch."""
    from aidd.tracking import next_steps

    f = filters or next_steps.Filters()
    f.all = True
    return next_steps.plan(root, today, f, now)


def for_spec(rel: str, data: dict, status: str | None = None, *, committed: bool = False, approval: bool | None = None) -> dict:
    """The Spec's next step in `status` (its derived status; the stored one when not given), with its Tasks."""
    from aidd.tracking import next_steps
    from aidd.workitems import derived_status

    approval = derived_status.needs_spec_approval(data, None) if approval is None else approval
    status = status or derived_status.spec_status(data, approval=approval)
    blockers = derived_status.blocked_reasons(data, status)
    return next_steps._spec_step(rel, data, status, committed=committed, approval=approval, blockers=blockers) | {
        "tasks": next_steps.tasks(data, status, approval=approval, blockers=blockers)
    }


# The legacy handshake a test sends before a request with no 2026-07-28 `_meta`: without it, `aidd mcp` refuses such a
# request with -32602 instead of guessing its era.
MCP_LEGACY_INITIALIZE = {"jsonrpc": "2.0", "id": "initialize", "method": "initialize", "params": {"protocolVersion": "2025-11-25", "capabilities": {}}}


def role_mcp_tools() -> list[str]:
    """The aidd MCP tools every role may call: they read, compute, or check, and `approve_spec` asks the person, whose
    answer alone records an approval (tests/test_mcp_approve.py)."""
    from aidd.cli import mcp_server
    from aidd.docsgen import pack_render

    return [prefix + str(t["name"]) for prefix in pack_render.MCP_TOOL_PREFIXES for t in mcp_server.TOOLS]


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
    "execution": "Builds or writes inside a frozen Spec, or proposes what a human decides, where the tests, the gate, or a human catch the mistake. A mid-size model; a role is promoted only on eval evidence, and `[agents.models]` can set `inherit` to run it on the session's model instead.",
}

# A Change Request block in Markdown: ```yaml aidd ... ```.
CHANGE_BLOCK = re.compile(r"^[ ]{0,3}```[ \t]*yaml[ \t]+aidd[ \t]*\r?\n(.*?)^[ ]{0,3}```[ \t]*$", re.M | re.S)

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
