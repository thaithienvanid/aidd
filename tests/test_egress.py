"""A drift guard on where aidd reaches the network: each module that does is on a list, and SECURITY.md names why.

SECURITY.md's "Data handling" section promises no telemetry and lists where aidd connects. This test reads the
syntax tree of each module under src/aidd and counts these as a network use:

- an import of a network library, such as `urllib.request`, `http.client`, `socket`, or `ssl`, in any form:
  `import urllib.request`, `from urllib import request`, `import urllib` with `urllib.request.urlopen`, or
  `importlib.import_module` and `__import__` with the module's name as a literal
- a call into a sending function of another listed module (SENDERS), such as `github.Client`, `egress.fetch_text`,
  or `git.fetch`, one hop deep
- a process argument list that runs curl or wget, a git command that talks to a remote, or a `gh` command that
  calls GitHub, and a command string that names curl or wget

A module with a network use must be in ALLOWED, which maps it to the purposes it serves. Each purpose must appear,
word for word, in SECURITY.md's "Data handling" section. So a new destination needs a line there first.

Its limits: it is a drift guard for reviewers, not a security boundary. It reads names, not behavior. It misses a
module name built at run time, a sender reached through more than one hop (such as any command that loads a config
whose `extends` names a URL), and network use inside a program aidd starts, such as a project's own test command.
"""

import ast
import re
import unittest
import urllib.parse

from helpers import ROOT

SRC = ROOT / "src" / "aidd"

# Each module that reaches the network, by its path under src/aidd, and the SECURITY.md "Data handling" phrases that
# name its destinations.
ALLOWED: dict[str, tuple[str, ...]] = {
    # The shared HTTPS client. Each module that calls it is listed below with its own destination.
    "kernel/http.py": ("the platform's API",),
    "platforms/github.py": ("the platform's API", "the platform's git server", "the attestation endpoints", "`aidd doctor`"),
    "platforms/gitlab.py": ("the platform's API", "the platform's git server"),
    "platforms/local_ship.py": ("the platform's git server", "`aidd integrate`"),
    # The platforms' door passes the adapters' senders on (github_gate, gitlab_gate, protection_checks, ...).
    "platforms/__init__.py": ("the platform's API", "the platform's git server", "`aidd doctor`"),
    "kernel/git.py": ("the platform's git server",),
    "gate/change_record.py": ("the attestation endpoints", "`aidd record verify --online`"),
    # The gate's door passes change_record.verify_signature on, as `aidd.gate.verify_signature`.
    "gate/__init__.py": ("the attestation endpoints", "`aidd record verify --online`"),
    "kernel/egress.py": ("an `extends` parent or org preset fetched by URL",),
    "gate/inputs.py": ("an `extends` parent or org preset fetched by URL",),
    "config/loading.py": ("an `extends` parent or org preset fetched by URL",),
    "config/extends.py": ("an `extends` parent or org preset fetched by URL",),
    "knowledge/bounded_fetch.py": ("`aidd eval standards --online`",),
    "knowledge/evidence_recheck.py": ("`aidd eval standards --online`",),
    "knowledge/release_feeds.py": ("`aidd eval standards --online`",),
    # The knowledge door passes evidence_recheck.check_online and release_feeds.check_releases on.
    "knowledge/__init__.py": ("`aidd eval standards --online`",),
    "setup/issue_import.py": ("`aidd import issues --github`",),
    "setup/__init__.py": ("`git ls-remote`", "`aidd doctor`", "`aidd self-update`"),
    "setup/pins.py": ("`git ls-remote`",),
    "setup/adoption.py": ("`git ls-remote`",),
    "setup/upgrading.py": ("`git ls-remote`",),
    "setup/self_updating.py": ("`git ls-remote`", "`aidd self-update`"),
    "setup/doctor_checks.py": ("`aidd doctor`",),
    # Commands and tools that run the senders above.
    "cli/commands/check.py": ("the platform's API", "`aidd record verify --online`"),
    "cli/commands/maintain.py": ("`aidd eval standards --online`",),
    "cli/commands/author.py": ("`aidd import issues --github`",),
    "cli/commands/setup.py": ("`git ls-remote`", "`aidd doctor`", "`aidd self-update`"),
    # Every command ends with the daily update check.
    "cli/app.py": ("`aidd self-update`",),
    "cli/commands/understand.py": ("`aidd doctor`",),
    # `aidd goal list` reads the open work as `aidd list` does.
    "cli/commands/goals.py": ("`aidd doctor`",),
    # `aidd approve` alone lists what waits on the person, as `aidd list --waiting-on-me` does.
    # ... and, where a platform's gate decides, posts the person's approval on the pull request.
    "cli/commands/decide.py": ("`aidd doctor`", "the platform's API"),
    "cli/commands/autopilot.py": ("`aidd doctor`",),
    "tracking/next_steps.py": ("`aidd doctor`",),
    # The tracking door passes the next steps on (forecast, plan, open_work), which run the doctor's checks.
    "tracking/__init__.py": ("`aidd doctor`",),
    # Autopilot reads the open work as `aidd list` does, through tracking.next_steps.open_work, and asks the platform
    # whether a Spec approval holds.
    "autopilot/turn.py": ("`aidd doctor`",),
    "autopilot/clearance.py": ("the platform's API", "the platform's git server"),
    "tracking/status_rollup.py": ("`aidd doctor`",),
    "cli/mcp_server.py": ("`aidd doctor`",),
    # The session hooks run the next steps with AIDD_HOOK_OFFLINE=1, so the doctor's network checks skip there.
    "guard/session_hooks.py": ("`aidd doctor`",),
    # The prompt hook's typed decisions read what waits on the person as `aidd list` does, offline as the hook is.
    "cli/commands/typed_decisions.py": ("`aidd doctor`",),
    # `aidd list --upkeep` runs the doctor with AIDD_OFFLINE=1, so its network checks skip there too.
    "tracking/upkeep.py": ("`aidd doctor`",),
}

# Standard-library and common third-party modules that open connections. aidd has no dependencies, so a third-party
# name here only guards against one arriving unnoticed.
NETWORK_MODULES = frozenset(
    {
        "urllib.request",
        "http.client",
        "http.server",
        "socket",
        "socketserver",
        "ssl",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "xmlrpc.client",
        "requests",
        "httpx",
        "urllib3",
        "aiohttp",
    }
)

# The names in aidd.kernel.http that send a request. Every other public name must be in HTTP_QUIET, so a new sender
# cannot slip past the scan unclassified.
HTTP_SENDERS = frozenset({"request", "get_bytes", "JsonClient"})
HTTP_QUIET = frozenset({"HttpError", "PageLimitError", "SafeRedirectHandler", "NoRedirectHandler", "with_params", "next_link"})

# The functions and classes of the listed modules (by dotted name under aidd) that reach the network, as other modules
# call them.
SENDERS: dict[str, frozenset[str]] = {
    "kernel.http": HTTP_SENDERS,
    "platforms.github": frozenset(
        {
            "Client",
            "github_gate",
            "protection_checks",
            "spec_approval_holds",
            "approval_target",
            "post_spec_approval",
            "approve_pull_request",
            "enable_auto_merge",
        }
    ),
    "platforms.gitlab": frozenset({"Client", "gitlab_gate"}),
    "kernel.git": frozenset({"fetch"}),
    "gate.change_record": frozenset({"verify_signature"}),
    "kernel.egress": frozenset({"fetch_text"}),
    "knowledge.bounded_fetch": frozenset({"fetch"}),
    "knowledge.evidence_recheck": frozenset({"check_online"}),
    "knowledge.release_feeds": frozenset({"check_releases"}),
    "setup.issue_import": frozenset({"issues_from_github"}),
    "setup.pins": frozenset({"remote_refs", "release_commit", "pin_checks", "resolve_pin"}),
    "setup.adoption": frozenset({"init"}),
    "setup.upgrading": frozenset({"upgrade"}),
    "setup.self_updating": frozenset({"check", "auto_update", "self_update"}),
    "setup.doctor_checks": frozenset({"doctor"}),
    # The next steps run the doctor's checks.
    "tracking.next_steps": frozenset({"forecast", "plan", "open_work"}),
}

DOWNLOADERS = frozenset({"curl", "wget"})
DOWNLOADER_WORD = re.compile(r"\b(curl|wget)\b")
GIT_REMOTE = frozenset({"fetch", "ls-remote", "clone", "pull", "push"})
GH_LOCAL = frozenset({"auth", "config", "version", "--version", "help", "--help"})
RUNNERS = frozenset({"system", "popen", "run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"})


def _network_module(name: str) -> bool:
    return name in NETWORK_MODULES or name.split(".")[0] in NETWORK_MODULES


def _imported(node: ast.AST) -> list[str]:
    """The dotted names an import statement binds, `from urllib import request` as `urllib.request`."""
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module, *(f"{node.module}.{a.name}" for a in node.names)]
    return []


def _aidd_source(node: ast.AST, package: str) -> str | None:
    """The aidd module a `from ... import` reads from, as its dotted name under aidd: `from aidd import x` and
    `from . import x` (in the top-level package) as "", `from aidd.kernel.http import y` as "kernel.http"; None for any
    other statement. `package` resolves a relative import."""
    if not isinstance(node, ast.ImportFrom):
        return None
    if node.level:
        base = package.split(".") if package else []
        base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
        return ".".join([*base, *([node.module] if node.module else [])])
    if node.module and (node.module == "aidd" or node.module.startswith("aidd.")):
        return node.module.removeprefix("aidd").removeprefix(".")
    return None


def _dotted(node: ast.expr) -> str | None:
    """`urllib.request.urlopen` as a string, or None when the chain does not start at a name."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


def _argument_lists(node: ast.AST) -> list[ast.List | ast.Tuple]:
    """The list and tuple literals a call takes or an assignment binds, nested ones too: the argument lists a
    process could run. A literal in a comparison, such as `args[:1] == ["push"]`, only inspects a command."""
    if isinstance(node, ast.Call):
        roots: list[ast.expr] = list(node.args)
    elif isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
        roots = [node.value]
    else:
        return []
    out: list[ast.List | ast.Tuple] = []
    while roots:
        root = roots.pop()
        if isinstance(root, (ast.List, ast.Tuple)):
            out.append(root)
            roots += root.elts
    return out


def _argv_use(node: ast.List | ast.Tuple) -> str | None:
    """The network command an argument list runs, or None."""
    words = node.elts
    if not words:
        return None
    first = words[0].value if isinstance(words[0], ast.Constant) else None
    second = words[1].value if len(words) > 1 and isinstance(words[1], ast.Constant) else None
    if first in DOWNLOADERS:
        return str(first)
    if first in GIT_REMOTE:
        return f"git {first}"
    if first == "git" and second in GIT_REMOTE:
        return f"git {second}"
    is_gh = first == "gh" or (isinstance(words[0], ast.Name) and words[0].id == "gh")
    if is_gh and isinstance(second, str) and second not in GH_LOCAL:
        return f"gh {second}"
    return None


def _runner(func: ast.expr) -> bool:
    """Whether a call starts a process, such as `os.system(...)` or `subprocess.run(...)`."""
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    return name in RUNNERS


def _strings(node: ast.expr) -> list[str]:
    """The literal text in a command expression: constants, f-string parts, and concatenations."""
    return [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def _door_exports() -> dict[str, dict[str, tuple[str, str]]]:
    """Each package door (aidd.kernel.doors), by its dotted name under aidd: door name -> (child module, defined name)."""
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for init in sorted(SRC.rglob("__init__.py")):
        for call in ast.walk(ast.parse(init.read_text(encoding="utf-8"))):
            if isinstance(call, ast.Call) and ast.unparse(call.func) == "doors.exports":
                package = module_name(init.relative_to(SRC).as_posix())
                exports = ast.literal_eval(call.args[1])
                out[package] = {door: (f"{package}.{where.partition(':')[0]}", where.partition(":")[2] or door) for door, where in exports.items()}
    return out


def senders() -> dict[str, frozenset[str]]:
    """SENDERS, and each package door under the names by which it passes a sender on: a call through the door reaches
    the network as a call of the child does."""
    out = dict(SENDERS)
    for package, exports in _door_exports().items():
        through = {door for door, (child, name) in exports.items() if name in SENDERS.get(child, ())}
        if through:
            out[package] = out.get(package, frozenset()) | through
    return out


def network_uses(source: str, module: str = "") -> set[str]:
    """Every network use in one module's source. `module` (its dotted name under aidd, such as `kernel.git`) leaves out
    calls into itself and resolves its relative imports."""
    tree = ast.parse(source)
    found: set[str] = set()
    all_senders = senders()
    aliases: dict[str, str] = {}  # a local name for an aidd module listed in SENDERS
    parents: set[str] = set()  # `import urllib`, whose `urllib.request.*` is a network use
    for node in ast.walk(tree):
        for name in _imported(node):
            if _network_module(name):
                found.add(f"import {name}")
            elif any(m.startswith(name + ".") for m in NETWORK_MODULES):
                parents.add(name)
        if (source := _aidd_source(node, module.rpartition(".")[0])) is not None:
            for a in node.names:
                imported = f"{source}.{a.name}".lstrip(".")
                if imported in all_senders and imported != module:
                    aliases[a.asname or a.name] = imported
                elif source in all_senders and source != module and a.name in all_senders[source]:
                    found.add(f"aidd.{source}.{a.name}")
        for argv in _argument_lists(node):
            if use := _argv_use(argv):
                found.add(use)
        if isinstance(node, ast.Call):
            callee = _dotted(node.func)
            literal = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
            if callee in ("importlib.import_module", "__import__", "import_module") and isinstance(literal, str) and _network_module(literal):
                found.add(f"import {literal}")
            if _runner(node.func) and node.args:
                for text in _strings(node.args[0]):
                    if m := DOWNLOADER_WORD.search(text):
                        found.add(m.group(1))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            target = aliases[node.value.id]
            if node.attr in all_senders[target]:
                found.add(f"aidd.{target}.{node.attr}")
        if isinstance(node, ast.Attribute) and (chain := _dotted(node)):
            for parent in parents:
                for m in NETWORK_MODULES:
                    if m.startswith(parent + ".") and (chain == m or chain.startswith(m + ".")):
                        found.add(f"import {m}")
    return found


def module_name(path: str) -> str:
    """`kernel/git.py` as `kernel.git`, and `setup/__init__.py` as `setup`."""
    return path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")


def module_file(module: str) -> str:
    """The path under src/aidd of a dotted module name: a package's `__init__.py`, or the module's own file."""
    rel = module.replace(".", "/")
    return f"{rel}/__init__.py" if (SRC / rel / "__init__.py").is_file() else f"{rel}.py"


def module_uses(name: str) -> set[str]:
    return network_uses((SRC / name).read_text(encoding="utf-8"), module=module_name(name))


def data_handling() -> str:
    text = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    return text.split("## Data handling", 1)[1].split("\n## ", 1)[0]


class EgressTests(unittest.TestCase):
    def test_each_network_use_is_on_the_list(self):
        unlisted = {}
        for path in sorted(SRC.rglob("*.py")):
            name = path.relative_to(SRC).as_posix()
            uses = module_uses(name)
            if uses and name not in ALLOWED:
                unlisted[name] = sorted(uses)
        self.assertEqual(unlisted, {}, "add each module to ALLOWED, and its destination to SECURITY.md's Data handling")

    def test_each_listed_module_still_reaches_the_network(self):
        quiet = [name for name in ALLOWED if not module_uses(name)]
        self.assertEqual(quiet, [], "remove a module from ALLOWED once it no longer reaches the network")

    def test_security_md_names_each_purpose(self):
        section = data_handling()
        self.assertIn("no telemetry", section)
        missing = sorted({p for purposes in ALLOWED.values() for p in purposes if p not in section})
        self.assertEqual(missing, [])

    def test_security_md_names_each_release_feed(self):
        # `aidd eval standards --online` asks each library tool's release feed; a new feed is named there first.
        from aidd.knowledge import release_feeds

        section = data_handling()
        self.assertEqual(set(release_feeds.FEED_NAMES), set(release_feeds.FEEDS))
        missing = sorted(name for name in release_feeds.FEED_NAMES.values() if name not in section)
        self.assertEqual(missing, [])
        hosts = sorted(
            {
                urllib.parse.urlsplit(release_feeds.feed_url(f, "a/b" if f == "github" else "x")).netloc
                for f in ("go.dev", "nodejs.org", "dotnet", "adoptium", "python.org")
            }
        )
        self.assertEqual([h for h in hosts if h not in section], [])

    def test_each_public_name_of_the_http_client_is_classified(self):
        tree = ast.parse((SRC / module_file("kernel.http")).read_text(encoding="utf-8"))
        public = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")}
        self.assertEqual(public - HTTP_SENDERS - HTTP_QUIET, set())
        self.assertEqual((HTTP_SENDERS | HTTP_QUIET) - public, set())

    def test_each_sender_exists_and_its_module_is_listed(self):
        for module, names in SENDERS.items():
            with self.subTest(module=module):
                self.assertIn(module_file(module), ALLOWED)
                tree = ast.parse((SRC / module_file(module)).read_text(encoding="utf-8"))
                defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
                self.assertEqual(names - defined, set())

    def test_the_scan_finds_each_form(self):
        cases = {
            "import urllib.request": "import urllib.request",
            "from urllib import request": "import urllib.request",
            "import urllib\nurllib.request.urlopen(u)": "import urllib.request",
            "import http.client": "import http.client",
            "import socket": "import socket",
            "import ssl": "import ssl",
            "from socket import create_connection": "import socket",
            "import requests": "import requests",
            "import importlib\nimportlib.import_module('socket')": "import socket",
            "__import__('http.client')": "import http.client",
            "from aidd.kernel import http\nhttp.request('GET', u)": "aidd.kernel.http.request",
            "from aidd.kernel import http as h\nh.JsonClient(u)": "aidd.kernel.http.JsonClient",
            "from aidd.kernel.http import get_bytes": "aidd.kernel.http.get_bytes",
            "from aidd.platforms import github\ngithub.Client(t, u)": "aidd.platforms.github.Client",
            "from aidd.kernel.egress import fetch_text": "aidd.kernel.egress.fetch_text",
            "from aidd.kernel import git\ngit.fetch(cwd, refs)": "aidd.kernel.git.fetch",
            "subprocess.run(['curl', '-s', u])": "curl",
            "os.system('wget ' + u)": "wget",
            "subprocess.run(f'cd x && curl -s {u}', shell=True)": "curl",
            "gitutil.run(['ls-remote', u], '.')": "git ls-remote",
            "subprocess.run(['git', 'fetch', 'origin'])": "git fetch",
            "subprocess.run([gh, 'api', '/user'])": "gh api",
        }
        for source, use in cases.items():
            with self.subTest(source=source):
                self.assertIn(use, network_uses(source))
        # A relative import resolves against the module's own package.
        relative = {
            "from . import http\nhttp.request('GET', u)": "aidd.kernel.http.request",
            "from . import http as h\nh.JsonClient(u)": "aidd.kernel.http.JsonClient",
            "from .http import get_bytes": "aidd.kernel.http.get_bytes",
            "from . import git\ngit.fetch(cwd, refs)": "aidd.kernel.git.fetch",
            "from .egress import fetch_text": "aidd.kernel.egress.fetch_text",
            "from ..platforms import github\ngithub.Client(t, u)": "aidd.platforms.github.Client",
        }
        for source, use in relative.items():
            with self.subTest(source=source):
                self.assertIn(use, network_uses(source, module="kernel.example"))

    def test_the_scan_ignores_local_work(self):
        for source in (
            "import urllib.parse",
            "import urllib\nurllib.parse.quote(x)",
            "import importlib\nimportlib.import_module('json')",
            "import subprocess\nsubprocess.run(['git', 'rev-parse', 'HEAD'])",
            "from aidd.kernel import http\nraise http.HttpError(0, u, 'offline')",
            "from aidd.kernel import git\ngit.run(['status'], '.')",
            "from aidd import setup\nsetup.validate_file(p)",
            "subprocess.run([gh, 'auth', 'token'])",
            "print('curl is a tool')",
            "denied = name == 'git' and args[:1] == ['push']",
        ):
            with self.subTest(source=source):
                self.assertEqual(network_uses(source), set())
        self.assertEqual(network_uses("from aidd import setup\nsetup.doctor(r)", module="setup"), set())
        self.assertEqual(network_uses("from . import http\nraise http.HttpError(0, u, 'offline')", module="kernel.example"), set())


if __name__ == "__main__":
    unittest.main()
