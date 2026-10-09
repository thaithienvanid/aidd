"""A drift guard on where aidd reaches the network: each module that does is on a list, and SECURITY.md names why.

SECURITY.md's "Data handling" section promises no telemetry and lists where aidd connects. This test reads the
syntax tree of each module under src/aidd and counts these as a network use:

- an import of a network library, such as `urllib.request`, `http.client`, `socket`, or `ssl`, in any form:
  `import urllib.request`, `from urllib import request`, `import urllib` with `urllib.request.urlopen`, or
  `importlib.import_module` and `__import__` with the module's name as a literal
- a call into a sending function of another listed module (SENDERS), such as `github.Client`, `inputs.fetch_text`,
  or `gitutil.fetch`, one hop deep
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

# Each module that reaches the network, and the SECURITY.md "Data handling" phrases that name its destinations.
ALLOWED: dict[str, tuple[str, ...]] = {
    # The shared HTTPS client. Each module that calls it is listed below with its own destination.
    "http.py": ("the platform's API",),
    "github.py": ("the platform's API", "the platform's git server", "the attestation endpoints", "`aidd doctor`"),
    "gitlab.py": ("the platform's API", "the platform's git server"),
    "gitutil.py": ("the platform's git server",),
    "changerecord.py": ("the attestation endpoints", "`aidd record verify --online`"),
    "inputs.py": ("an `extends` parent or org preset fetched by URL",),
    "config.py": ("an `extends` parent or org preset fetched by URL",),
    "knowledge.py": ("`aidd eval standards --online`",),
    "intake.py": ("`aidd import issues --github`",),
    "repo.py": ("`git ls-remote`", "`aidd doctor`"),
    # Commands and tools that run the senders above.
    "cli.py": (
        "the platform's API",
        "`aidd record verify --online`",
        "`aidd eval standards --online`",
        "`aidd import issues --github`",
        "`git ls-remote`",
        "`aidd doctor`",
    ),
    "nextstep.py": ("`aidd doctor`",),
    # Autopilot reads the open work as `aidd list` does, through nextstep.open_work.
    "autopilot.py": ("`aidd doctor`", "the platform's API", "the platform's git server"),
    "rollup.py": ("`aidd doctor`",),
    "mcp.py": ("`aidd doctor`",),
    # The session hooks run the next steps with AIDD_HOOK_OFFLINE=1, so the doctor's network checks skip there.
    "hooks.py": ("`aidd doctor`",),
    # `aidd list --upkeep` runs the doctor with AIDD_OFFLINE=1, so its network checks skip there too.
    "upkeep.py": ("`aidd doctor`",),
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

# The names in aidd.http that send a request. Every other public name must be in HTTP_QUIET, so a new sender
# cannot slip past the scan unclassified.
HTTP_SENDERS = frozenset({"request", "get_bytes", "JsonClient"})
HTTP_QUIET = frozenset({"HttpError", "PageLimitError", "SafeRedirectHandler", "NoRedirectHandler", "with_params", "next_link"})

# The functions and classes of the listed modules that reach the network, as other modules call them.
SENDERS: dict[str, frozenset[str]] = {
    "http": HTTP_SENDERS,
    "github": frozenset({"Client", "gate", "protection_checks", "spec_approval_holds"}),
    "gitlab": frozenset({"Client", "gate"}),
    "gitutil": frozenset({"fetch"}),
    "changerecord": frozenset({"verify_signature"}),
    "inputs": frozenset({"fetch_text"}),
    "knowledge": frozenset({"check_online"}),
    "intake": frozenset({"from_github"}),
    "repo": frozenset({"doctor", "init", "upgrade", "remote_refs", "release_commit", "pin_checks"}),
    # The next steps run the doctor's checks.
    "nextstep": frozenset({"assess", "plan", "open_work"}),
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


def network_uses(source: str, module: str = "") -> set[str]:
    """Every network use in one module's source. `module` (such as `repo`) leaves out calls into itself."""
    tree = ast.parse(source)
    found: set[str] = set()
    aliases: dict[str, str] = {}  # a local name for an aidd module listed in SENDERS
    parents: set[str] = set()  # `import urllib`, whose `urllib.request.*` is a network use
    for node in ast.walk(tree):
        for name in _imported(node):
            if _network_module(name):
                found.add(f"import {name}")
            elif any(m.startswith(name + ".") for m in NETWORK_MODULES):
                parents.add(name)
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            for a in node.names:
                if node.module is None and a.name in SENDERS and a.name != module:
                    aliases[a.asname or a.name] = a.name
                elif node.module in SENDERS and node.module != module and a.name in SENDERS[node.module]:
                    found.add(f"aidd.{node.module}.{a.name}")
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
            if node.attr in SENDERS[target]:
                found.add(f"aidd.{target}.{node.attr}")
        if isinstance(node, ast.Attribute) and (chain := _dotted(node)):
            for parent in parents:
                for m in NETWORK_MODULES:
                    if m.startswith(parent + ".") and (chain == m or chain.startswith(m + ".")):
                        found.add(f"import {m}")
    return found


def module_uses(name: str) -> set[str]:
    return network_uses((SRC / name).read_text(encoding="utf-8"), module=name.removesuffix(".py"))


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
        from aidd import knowledge

        section = data_handling()
        self.assertEqual(set(knowledge.FEED_NAMES), set(knowledge.FEEDS))
        missing = sorted(name for name in knowledge.FEED_NAMES.values() if name not in section)
        self.assertEqual(missing, [])
        hosts = sorted(
            {
                urllib.parse.urlsplit(knowledge.feed_url(f, "a/b" if f == "github" else "x")).netloc
                for f in ("go.dev", "nodejs.org", "dotnet", "adoptium", "python.org")
            }
        )
        self.assertEqual([h for h in hosts if h not in section], [])

    def test_each_public_name_of_the_http_client_is_classified(self):
        tree = ast.parse((SRC / "http.py").read_text(encoding="utf-8"))
        public = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")}
        self.assertEqual(public - HTTP_SENDERS - HTTP_QUIET, set())
        self.assertEqual((HTTP_SENDERS | HTTP_QUIET) - public, set())

    def test_each_sender_exists_and_its_module_is_listed(self):
        for module, names in SENDERS.items():
            with self.subTest(module=module):
                self.assertIn(f"{module}.py", ALLOWED)
                tree = ast.parse((SRC / f"{module}.py").read_text(encoding="utf-8"))
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
            "from . import http\nhttp.request('GET', u)": "aidd.http.request",
            "from . import http as h\nh.JsonClient(u)": "aidd.http.JsonClient",
            "from .http import get_bytes": "aidd.http.get_bytes",
            "from . import github\ngithub.Client(t, u)": "aidd.github.Client",
            "from .inputs import fetch_text": "aidd.inputs.fetch_text",
            "from . import gitutil\ngitutil.fetch(cwd, refs)": "aidd.gitutil.fetch",
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

    def test_the_scan_ignores_local_work(self):
        for source in (
            "import urllib.parse",
            "import urllib\nurllib.parse.quote(x)",
            "import importlib\nimportlib.import_module('json')",
            "import subprocess\nsubprocess.run(['git', 'rev-parse', 'HEAD'])",
            "from . import http\nraise http.HttpError(0, u, 'offline')",
            "from . import gitutil\ngitutil.run(['status'], '.')",
            "from . import repo\nrepo.validate_file(p)",
            "subprocess.run([gh, 'auth', 'token'])",
            "print('curl is a tool')",
            "denied = name == 'git' and args[:1] == ['push']",
        ):
            with self.subTest(source=source):
                self.assertEqual(network_uses(source), set())
        self.assertEqual(network_uses("from . import repo\nrepo.doctor(r)", module="repo"), set())


if __name__ == "__main__":
    unittest.main()
