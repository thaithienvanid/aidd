"""What `aidd init` finds in a repository before it writes anything, and what it proposes to fit aidd and the team to it.

Adopting aidd in a repository that already exists means knowing its test commands, its sensitive areas, its
generated code, its owners, and its CI. People rarely have that written down. `aidd init` finds it from the files
alone, with no model and no network, and proposes the config to match. `aidd init --dry-run` prints it and writes
nothing. `aidd init` uses the detected test command and leaves the rest as suggestions, for a person to review in the
setup change, which the gate treats as major.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from aidd import config as cfgmod
from aidd import gate
from aidd.kernel import globs, resources, strict_yaml

SKIP = {".git", "node_modules", "vendor", "third_party", "dist", "build", "target", ".venv", "venv", "__pycache__", ".next", ".tox", "out", "coverage"}
MAX_DEPTH = 3
MAX_FILES = 20000


# Directory names that point to sensitive work the baseline rules may not name, with the risk they carry.
SENSITIVE = (
    (("payment", "payments", "billing", "invoice", "invoices", "checkout", "pricing", "ledger", "wallet"), "payments", ["financial"]),
    (("pii", "gdpr", "consent", "privacy", "profile", "profiles", "customer", "customers", "users", "patient", "patients"), "personal-data", ["privacy"]),
    (("login", "session", "sessions", "oauth", "sso", "saml", "token", "tokens", "password", "passwords"), "sign-in", ["security"]),
    (("ai", "llm", "prompts"), "ai", ["security", "compliance"]),
)
# File names that deploy or release: a change to one reaches production, whatever folder it is in.
DEPLOY_FILE = re.compile(r"^(?:deploy|release|rollout|provision)[\w.-]{0,40}\.(?:sh|bash|ps1|py|rb|js|ts)$", re.I)
# What `aidd init` holds of the deploy files and Makefile targets: names that deploy, roll out, or provision (paid
# infrastructure). A `release` script still routes as risky (DEPLOY_FILE), but it often only builds.
# The words a script or a Makefile target is held by: one that deploys, rolls out, or provisions.
HELD_WORDS = ("deploy", "rollout", "provision")
HELD_NAME = re.compile(rf"^(?:{'|'.join(HELD_WORDS)})[\w.-]{{0,40}}$", re.I)
MAKEFILES = ("Makefile", "makefile", "GNUmakefile")
MAKE_RULE = re.compile(r"^([A-Za-z0-9_.-]+(?:[ \t]+[A-Za-z0-9_.-]+)*)[ \t]*::?(?!=)")
MAX_HELD_SCRIPTS = 10
HELD_PREFIX = "init: "  # init's entry names, which never collide with a parent config's entry for the same command


def _sub(program: str, *words: str) -> list[str]:
    """The glob for `program` running the subcommand `words`, after any options: `terraform* apply *`. The guard reads
    a final ` *` as "then anything or nothing", so it holds `terraform -chdir=x apply` and never `terraform plan -out apply.tfplan`."""
    return [f"{program}* {' '.join(words)} *"]


# What an entry does not hold, by entry name: the Vercel subcommands that take --prod and deploy nothing.
UNLESS = {"vercel --prod": ["vercel build *", "vercel pull *"], "vercel --target production": ["vercel build *", "vercel pull *"]}


# Infrastructure tools by the file that shows a repository uses one, with the commands that change or destroy what it
# runs: (tool, file test, [(name, match)]). The guard matches each pattern against the command as the program it runs
# (`guard.held_command`), so `terraform* apply *` also holds `AWS_PROFILE=prod terraform -chdir=infra apply`.
# No Helm: `helm install` and `helm upgrade` are the local loop against kind or minikube.
IAC_TOOLS: tuple[tuple[str, Callable[[str], bool], list[tuple[str, list[str]]]], ...] = (
    ("Terraform", lambda r: r.endswith(".tf"), [("terraform apply", _sub("terraform", "apply")), ("terraform destroy", _sub("terraform", "destroy"))]),
    ("OpenTofu", lambda r: r.endswith(".tofu"), [("tofu apply", _sub("tofu", "apply")), ("tofu destroy", _sub("tofu", "destroy"))]),
    ("Pulumi", lambda r: Path(r).name in ("Pulumi.yaml", "Pulumi.yml"), [("pulumi up", _sub("pulumi", "up")), ("pulumi destroy", _sub("pulumi", "destroy"))]),
    ("the AWS CDK", lambda r: Path(r).name == "cdk.json", [("cdk deploy", _sub("cdk", "deploy")), ("cdk destroy", _sub("cdk", "destroy"))]),
    ("Wrangler", lambda r: Path(r).name in ("wrangler.toml", "wrangler.json", "wrangler.jsonc"), [("wrangler deploy", _sub("wrangler", "deploy"))]),
    (
        "the Serverless Framework",
        lambda r: Path(r).name in ("serverless.yml", "serverless.yaml", "serverless.ts"),
        [
            ("serverless deploy", _sub("serverless", "deploy")),
            ("serverless remove", _sub("serverless", "remove")),
            ("sls deploy", _sub("sls", "deploy")),
            ("sls remove", _sub("sls", "remove")),
        ],
    ),
    ("Fly.io", lambda r: Path(r).name == "fly.toml", [("fly deploy", _sub("fly", "deploy"))]),  # flyctl too
    ("Firebase", lambda r: Path(r).name == "firebase.json", [("firebase deploy", _sub("firebase", "deploy"))]),
    # Bare `vercel` deploys, and so does `vercel <path>`; `vercel build --prod` and `vercel pull` only prepare a build
    # (vercel.com/docs/cli/deploy). `promote` and `rollback` change which deployment serves production.
    (
        "Vercel",
        lambda r: Path(r).name == "vercel.json",
        [
            ("vercel --prod", ["vercel*", "--prod"]),
            ("vercel --target production", ["vercel*", "--target", "production"]),
            ("vercel promote", _sub("vercel", "promote")),
            ("vercel rollback", _sub("vercel", "rollback")),
        ],
    ),
    # `-p` is the short form of `--prod` (netlify/cli src/commands/deploy); `--prod-if-unlocked` holds `--prod`.
    (
        "Netlify",
        lambda r: Path(r).name == "netlify.toml",
        [("netlify deploy --prod", [*_sub("netlify", "deploy"), "--prod"]), ("netlify deploy -p", [*_sub("netlify", "deploy"), "* -p *"])],
    ),
)
HELD_BY_INIT = "`aidd init` held it"
GENERATED = ("generated", "gen", "__generated__", "autogen", "vendor", "third_party", "dist", "build")
# Environment files: they hold secrets, and their example does not.
ENV_FILE = re.compile(r"(?:^|/)\.env(?:\.[\w.-]+)?$")
ENV_EXAMPLE = re.compile(r"\.(?:example|sample|template|dist)$")
MAX_SECRET_FILES = 20
TEST_FILE = re.compile(r"(^test_.*\.py$|_test\.py$|_test\.go$|\.(test|spec)\.[cm]?[jt]sx?$|Test\.java$|Tests?\.cs$|_spec\.rb$|_test\.rb$|_test\.dart$)")
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs_test", "testing", "e2e"}
AGENT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules", ".github/copilot-instructions.md", "WARP.md", "CONVENTIONS.md", ".windsurfrules")
SPEC_TOOLS = {".specify": "GitHub Spec Kit", "openspec": "OpenSpec", ".kiro": "Kiro"}


def _walk(root: Path) -> list[Path]:
    found: list[Path] = []

    def visit(d: Path, depth: int) -> None:
        if depth > MAX_DEPTH or len(found) >= MAX_FILES:
            return
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for p in entries:
            if p.is_symlink():
                continue  # a link may point out of the repository; what it names is not the repository's to describe
            if p.is_dir():
                if p.name not in SKIP and not (p.name.startswith(".") and p.name not in (".github", ".gitlab", ".specify", ".kiro")):
                    visit(p, depth + 1)
            elif len(found) < MAX_FILES:
                found.append(p)

    visit(root, 0)
    return found


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:200_000]
    except OSError:
        return ""


def _stack(p: Path, root: Path) -> dict | None:
    """What one manifest says: the stack, a test command to run from the repository root, and pack hints."""
    name, text, folder = p.name, _read(p), p.parent
    rel = "" if folder == root else folder.relative_to(root).as_posix()
    cmd: list[str] | None = None
    stack = None
    if name == "package.json":
        stack = "JavaScript/TypeScript"
        try:
            scripts = json.loads(text).get("scripts") or {}
        except (json.JSONDecodeError, AttributeError):
            scripts = {}
        if "test" in scripts and "no test specified" not in str(scripts.get("test")):
            pm = _js_pm(folder)
            at = [_JS_AT[pm], rel] if rel else []
            cmd = ["bun", "run", *at, "test"] if pm == "bun" else [pm, *at, "test"]
    elif name in ("pyproject.toml", "setup.cfg", "requirements.txt", "setup.py"):
        stack = "Python"
        if "pytest" in text or (folder / "tests").is_dir() or (folder / "conftest.py").exists():
            # The project's own runner when its lockfile says which: uv, then Poetry; plain pytest otherwise.
            cmd = _py_tool(folder, rel, ["pytest"], [rel] if rel else [], bare=["python3", "-m", "pytest"])
    elif name == "go.mod":
        stack, cmd = "Go", ["go", "test", f"./{rel}/..." if rel else "./..."]
    elif name == "Cargo.toml" and ("[package]" in text or "[workspace]" in text):
        stack, cmd = "Rust", ["cargo", "test"] + (["--manifest-path", f"{rel}/Cargo.toml"] if rel else [])
    elif name == "pom.xml":
        stack, cmd = "Java (Maven)", _maven(folder, rel) + ["-q", "test"] + (["-f", f"{rel}/pom.xml"] if rel else [])
    elif name in ("build.gradle", "build.gradle.kts"):
        stack, cmd = "JVM (Gradle)", _gradle(folder, rel) + ["test"] + (["-p", rel] if rel else [])
    elif name == "Gemfile":
        stack, cmd = "Ruby", ["bundle", "exec", "rspec" if (folder / "spec").is_dir() else "rake"] + ([] if (folder / "spec").is_dir() else ["test"])
    elif name.endswith((".sln", ".csproj")):
        stack, cmd = ".NET", ["dotnet", "test"] + ([p.relative_to(root).as_posix()] if rel or name.endswith(".sln") else [])
    elif name == "pubspec.yaml":
        stack, cmd = "Dart/Flutter", ["flutter", "test"] + ([rel] if rel else [])
    elif name == "composer.json":
        stack = "PHP"
        cmd = ["composer", "test"] + (["--working-dir", rel] if rel else []) if '"test"' in text else None
    elif name in ("deno.json", "deno.jsonc"):
        stack, cmd = "TypeScript (Deno)", ["deno", "test"] + ([rel] if rel else [])
    elif name == "Package.swift":
        stack, cmd = "Swift", ["swift", "test"] + (["--package-path", rel] if rel else [])
    elif name == "mix.exs":
        stack, cmd = "Elixir", ["mix", "test"] if not rel else None
    elif name == "build.sbt":
        stack, cmd = "Scala (sbt)", ["sbt", "test"] if not rel else None
    elif name == "Makefile" and re.search(r"^test:", text, re.M) and not rel:
        stack, cmd = "Make", ["make", "test"]
    if stack is None:
        return None
    packs = gate.dependency_packs_for(gate.declared_dependencies(p.name, text))
    checks = _checks(name, folder, rel, text)
    return {
        "path": rel or ".",
        "manifest": p.relative_to(root).as_posix(),
        "stack": stack,
        "test": cmd,
        "packs": packs,
        "checks": checks,
        "tool_or_library": _tool_or_library(name, folder, text),
    }


# What says a manifest builds a command-line tool or a library: an entry point, a package build, or a language whose
# module is one. A user interface anywhere in the repository (`UI_FILE`, or a web, mobile, or desktop pack) overrides it.
UI_FILE = re.compile(r"\.(?:html?|jsx|tsx|vue|svelte|astro|css|scss|sass|less|storyboard|xib)$", re.I)
UI_PACKS = frozenset({"web-front-end", "mobile-apps", "desktop-apps"})
# A repository with this many source files already has a structure: `aidd init` writes the `modular_monolith` product
# default off there, with the reason, so the structure stays as it is. A fresh scaffold has fewer.
EXISTING_CODE_FILES = 20


def _tool_or_library(name: str, folder: Path, text: str) -> bool:
    if name in ("pyproject.toml", "setup.cfg", "setup.py"):
        return name == "setup.py" or any(k in text for k in ("[build-system]", "[project.scripts]", "console_scripts", "[tool.poetry.scripts]"))
    if name == "package.json":
        try:
            pkg = json.loads(text)
        except json.JSONDecodeError:
            return False
        return isinstance(pkg, dict) and any(k in pkg for k in ("bin", "exports", "main"))
    return name in ("go.mod", "Cargo.toml")


# Every ESLint configuration file name, the legacy .eslintrc family and the flat eslint.config family.
ESLINT_CONFIGS = (".eslintrc", *(f".eslintrc.{e}" for e in ("js", "cjs", "json", "yaml", "yml")))
ESLINT_CONFIGS += tuple(f"eslint.config.{e}" for e in ("js", "mjs", "cjs", "ts", "mts", "cts"))
TYPECHECK_SCRIPTS = ("typecheck", "type-check", "types", "tsc")


def _maven(folder: Path, rel: str) -> list[str]:
    """The Maven wrapper beside the pom, run from the repository root, else `mvn` on PATH."""
    return [f"./{rel}/mvnw" if rel else "./mvnw"] if (folder / "mvnw").exists() else ["mvn"]


def _gradle(folder: Path, rel: str) -> list[str]:
    return [f"./{rel}/gradlew" if rel else "./gradlew"] if (folder / "gradlew").exists() else ["gradle"]


# How each package manager is pointed at a package folder from the repository root.
_JS_AT = {"bun": "--cwd", "pnpm": "--dir", "yarn": "--cwd", "npm": "--prefix"}


def _js_pm(folder: Path) -> str:
    if (folder / "bun.lock").exists() or (folder / "bun.lockb").exists() or (folder / "bunfig.toml").exists():
        return "bun"
    try:
        manifest = json.loads(_read(folder / "package.json") or "{}")
    except json.JSONDecodeError:
        manifest = {}
    scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
    # A fresh Bun project has no lockfile yet: its scripts, or its packageManager field, say so.
    if str(manifest.get("packageManager", "") if isinstance(manifest, dict) else "").startswith("bun@") or (
        isinstance(scripts, dict) and any(str(v).split()[:1] in (["bun"], ["bunx"]) for v in scripts.values())
    ):
        return "bun"
    if (folder / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (folder / "yarn.lock").exists():
        return "yarn"
    return "npm"


def _js_script(pm: str, rel: str, script: str) -> list[str]:
    """Run a package.json script through the package manager, from the repository root."""
    at = [_JS_AT[pm], rel] if rel else []
    return ["bun", "run", *at, script] if pm == "bun" else [pm, *at, "run", script]


def _js_bin(pm: str, rel: str, args: list[str]) -> list[str]:
    """Run a package's own binary (eslint, tsc) through the package manager."""
    if pm == "bun":
        # `bunx` has no flag for another folder; `bun run --cwd` runs the package's own binary from there.
        return ["bun", "run", "--cwd", rel, *args] if rel else ["bunx", *args]
    if pm == "pnpm":
        return ["pnpm", *(["--dir", rel] if rel else []), "exec", *args]
    if pm == "yarn":
        return ["yarn", *(["--cwd", rel] if rel else []), *args]
    return ["npm", *(["--prefix", rel] if rel else []), "exec", "--", *args]


def _py_tool(folder: Path, rel: str, args: list[str], target: list[str], runner_target: list[str] | None = None, bare: list[str] | None = None) -> list[str]:
    """A Python tool through the project's runner (uv, Poetry), else on PATH (as `bare`, when given); `target` is where
    it looks without a runner, and `runner_target` where it looks through one, which runs it in the package folder."""
    if (folder / "uv.lock").exists():
        return ["uv", "run", *(["--directory", rel] if rel else []), *args, *(runner_target or [])]
    if (folder / "poetry.lock").exists():
        return ["poetry", *(["-C", rel] if rel else []), "run", *args, *(runner_target or [])]
    return [*(bare or args), *target]


def _checks(name: str, folder: Path, rel: str, text: str) -> list[dict]:
    """Lint and type-check commands the repository already configures, beside its tests: the stack's standard tools
    only, and only where their configuration is present (Go's vet and Rust's clippy ship with the toolchain)."""
    out: list[dict] = []

    def add(kind: str, tool: str, command: list[str]) -> None:
        out.append({"kind": kind, "tool": tool, "command": command})

    if name == "package.json":
        try:
            data = json.loads(text)
            scripts = data.get("scripts") or {}
        except (json.JSONDecodeError, AttributeError):
            data, scripts = {}, {}
        pm = _js_pm(folder)
        if any((folder / c).is_file() for c in ESLINT_CONFIGS) or (isinstance(data, dict) and "eslintConfig" in data):
            add("lint", "eslint", _js_script(pm, rel, "lint") if "lint" in scripts else _js_bin(pm, rel, ["eslint", "."]))
        if (folder / "tsconfig.json").is_file():
            script = next((s for s in TYPECHECK_SCRIPTS if s in scripts), None)
            add("types", "tsc", _js_script(pm, rel, script) if script else _js_bin(pm, rel, ["tsc", "--noEmit"]))
    elif name in ("pyproject.toml", "setup.cfg", "requirements.txt", "setup.py"):
        pyproject = _read(folder / "pyproject.toml") if (folder / "pyproject.toml").is_file() else ""
        setup_cfg = _read(folder / "setup.cfg") if (folder / "setup.cfg").is_file() else ""
        target = [rel] if rel else []
        if re.search(r"^\[tool\.ruff\b", pyproject, re.M) or any((folder / f).is_file() for f in ("ruff.toml", ".ruff.toml")):
            add("lint", "ruff", _py_tool(folder, rel, ["ruff", "check"], target))
        mypy_ini = next((f for f in ("mypy.ini", ".mypy.ini") if (folder / f).is_file()), None)
        if mypy_ini or re.search(r"^\[tool\.mypy\]", pyproject, re.M) or re.search(r"^\[mypy\]", setup_cfg, re.M):
            # With `files` in its configuration, mypy knows what to check; otherwise it is given the package folder.
            config = (_read(folder / mypy_ini) if mypy_ini else "") + pyproject + setup_cfg
            names_files = re.search(r"^\s*files\s*=", config, re.M) is not None
            # Through uv or Poetry it runs in the package folder, so it is given that folder as `.`.
            add("types", "mypy", _py_tool(folder, rel, ["mypy"], [] if names_files and not rel else (target or ["."]), [] if names_files else ["."]))
    elif name == "go.mod":
        add("lint", "go-vet", ["go", "vet", f"./{rel}/..." if rel else "./..."])
    elif name == "Cargo.toml" and ("[package]" in text or "[workspace]" in text):
        add("lint", "clippy", ["cargo", "clippy", *(["--manifest-path", f"{rel}/Cargo.toml"] if rel else []), "--", "-D", "warnings"])
    elif name == "pom.xml":
        add("check", "maven-verify", _maven(folder, rel) + ["-q", "verify"] + (["-f", f"{rel}/pom.xml"] if rel else []))
    elif name in ("build.gradle", "build.gradle.kts"):
        add("check", "gradle-check", _gradle(folder, rel) + ["check"] + (["-p", rel] if rel else []))
    return out


def _make_targets(text: str) -> list[str]:
    """The Makefile's targets whose name says they deploy, roll out, or provision, in order: rule lines only, never a recipe line,
    a special target such as `.PHONY`, or a variable assignment."""
    out: list[str] = []
    for line in text.splitlines():
        m = None if line[:1] in ("\t", "#") else MAKE_RULE.match(line)
        for t in m.group(1).split() if m else ():
            if HELD_NAME.match(t) and t not in out:
                out.append(t)
    return out


def held_commands(root: Path, rels: list[str]) -> tuple[list[dict], int]:
    """The `guard.held_commands` entries `aidd init` writes: each deploy, rollout, or provision script by its name,
    each Makefile target named so, and the commands that change or destroy infrastructure, for each tool the
    repository's files show it uses. Only what the file names and the Makefiles say; never a guess from a dependency or a word in a file.
    Scripts merge by name first (one entry for twelve `deploy.sh`), then the first MAX_HELD_SCRIPTS names stay; the
    count it did not hold comes second."""
    out: list[dict] = []

    def add(name: str, match: list[str], why: str) -> None:
        if all(e["match"] != match for e in out):
            entry = {"name": HELD_PREFIX + name, "match": match, "message": f"{HELD_BY_INIT}: {why}."}
            out.append(entry | ({"unless": UNLESS[name]} if name in UNLESS else {}))

    by_name: dict[str, list[str]] = {}
    for r in sorted(r for r in rels if DEPLOY_FILE.match(Path(r).name) and HELD_NAME.match(Path(r).name)):
        by_name.setdefault(Path(r).name, []).append(r)
    scripts = sorted(by_name.items(), key=lambda kv: kv[1][0])
    for base, paths in scripts[:MAX_HELD_SCRIPTS]:
        many = f" ({len(paths)} files named {base}, such as {paths[0]})" if len(paths) > 1 else ""
        does = "provisions infrastructure" if base.lower().startswith("provision") else "deploys"
        add(base if many else paths[0], [f"{base} *"], f"its name says it {does}{many}")
    for r in sorted(r for r in rels if Path(r).name in MAKEFILES):
        for t in _make_targets(_read(root / r)):
            add(f"make {t}", _sub("make", t), f"{r} has a `{t}` target")
    tofu_lock = next((r for r in rels if Path(r).name == ".terraform.lock.hcl" and "registry.opentofu.org" in _read(root / r)), None)
    for tool, uses, commands in IAC_TOOLS:
        seen = next((r for r in rels if uses(r)), None) or (tofu_lock if tool == "OpenTofu" else None)
        for name, match in commands if seen else ():
            add(name, match, f"{seen} shows this repository uses {tool}")
    return out, max(0, len(scripts) - MAX_HELD_SCRIPTS)


def default_held() -> list[dict]:
    """What the guard holds when a repository's config cannot be read: every command `held_commands` could detect,
    whatever the files show. A script or a Makefile target named for each HELD_WORDS word, and each infrastructure
    tool's commands, from the same data, so an invalid config never lets a deploy through."""
    out: list[dict] = []
    for word in HELD_WORDS:
        out.append({"name": f"{HELD_PREFIX}{word}*", "match": [f"{word}* *"]})
        out.append({"name": f"{HELD_PREFIX}make {word}*", "match": _sub("make", f"{word}*")})
    for _, _, commands in IAC_TOOLS:
        for name, match in commands:
            out.append({"name": HELD_PREFIX + name, "match": match} | ({"unless": UNLESS[name]} if name in UNLESS else {}))
    return out


def held_yaml(entries: list[dict]) -> str:
    """The entries as an active `guard.held_commands` list, each saying a person may delete it. Empty for none."""
    if not entries:
        return ""
    out = [HELD_COMMENT.rstrip("\n"), "guard:", "  held_commands:"]
    for e in entries:
        item = {"name": e["name"], "match": e["match"]} | ({"unless": e["unless"]} if e.get("unless") else {}) | {"message": e["message"]}
        lines = strict_yaml.dump_lines(item, 6)
        out += [f"    - {lines[0][6:]}   # {HELD_ENTRY}", *lines[1:]]
    return "\n".join(out) + "\n"


HELD_COMMENT = (
    "# Deploy commands `aidd init` holds for a person (field reference: references/config.md). A person may delete an entry.\n"
    "# To approve one per session, add requires: VAR; a person then starts the agent with VAR set to a non-empty value.\n"
)
HELD_ENTRY = "held for a person by aidd init; a person may delete this entry"


def detect(root: Path) -> dict:
    root = root.resolve()
    files = _walk(root)
    rels = [p.relative_to(root).as_posix() for p in files]
    stacks = [s for p in files if (s := _stack(p, root))]
    # Checks come from every manifest of a folder (a package.json beside a pyproject.toml), each tool once.
    checks: dict[tuple[str, str], dict] = {}
    for s in stacks:
        for c in s["checks"]:
            checks.setdefault((s["path"], c["tool"]), {"path": s["path"], **c})
    # One stack per folder: the first manifest with a test command wins (a pyproject.toml over a requirements.txt).
    by_folder: dict[str, dict] = {}
    for s in sorted(stacks, key=lambda s: (s["path"], s["test"] is None)):
        by_folder.setdefault(s["path"], s)
    stacks = list(by_folder.values())
    folders = {str(PurePosixPath(r).parent) for r in rels}
    dirs = sorted({part for r in rels for part in [str(PurePosixPath(*PurePosixPath(r).parts[: i + 1])) for i in range(len(PurePosixPath(r).parts) - 1)]})
    workspace = any((root / f).is_file() for f in ("pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", "go.work"))
    monorepo = workspace or len([s for s in stacks if s["path"] != "."]) >= 2
    if any(r.endswith((".tf", ".tofu")) for r in rels) or any(Path(r).name == "Chart.yaml" for r in rels):
        stacks.append({"path": ".", "manifest": "*.tf", "stack": "Infrastructure as code", "test": None, "packs": ["cloud-and-infrastructure"], "checks": []})

    baseline = resources.load_json("baseline.json")
    covered = [p for r in baseline["risk_rules"] for p in r["paths"]] + list(baseline["protected_paths"])
    sensitive: dict[str, dict] = {}
    for d in dirs:
        leaf = Path(d).name.lower()
        for names, rule, dims in SENSITIVE:
            if leaf in names and not globs.match_any(covered, d + "/x", fold_case=True):
                sensitive.setdefault(rule, {"name": rule, "paths": [], "dimensions": dims})["paths"].append(f"{d}/**")
    deploy = sorted(r for r in rels if DEPLOY_FILE.match(Path(r).name) and not globs.match_any(covered, r, fold_case=True))
    if deploy:
        sensitive["deploy"] = {"name": "deploy", "paths": deploy[:10], "dimensions": ["availability"]}
    generated = sorted({f"{d}/**" for d in dirs if Path(d).name.lower() in GENERATED} | {"**/*.pb.go"} & {"**/*.pb.go" for r in rels if r.endswith(".pb.go")})

    manifests = {r: gate.declared_dependencies(r, _read(root / r)) for r in rels if gate.is_manifest(r)}
    tested = {str(PurePosixPath(r).parent) for r in rels if TEST_FILE.search(Path(r).name)} | {d for d in dirs if Path(d).name in TEST_DIRS}
    source_ext = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".cs", ".php", ".dart", ".swift")
    top_source = sorted({Path(r).parts[0] for r in rels if r.endswith(source_ext) and len(Path(r).parts) > 1})
    untested = [d for d in top_source if d not in TEST_DIRS and not any(t == d or t.startswith(d + "/") for t in tested) and not (root / "tests").is_dir()]

    codeowners = next((c for c in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS") if (root / c).is_file()), None)
    ci = sorted(r for r in rels if r.startswith(".github/workflows/") and r.endswith((".yml", ".yaml"))) + (
        [".gitlab-ci.yml"] if ".gitlab-ci.yml" in rels else []
    )
    held = held_commands(root, rels)
    has_ui = any(UI_FILE.search(r) for r in rels) or any(UI_PACKS & set(s["packs"]) for s in stacks)
    return {
        "root": str(root),
        # A command-line tool or a library with no web, mobile, or desktop interface: `aidd init` writes the interface product
        # defaults off. An empty repository, or one it cannot tell, keeps them on.
        "no_ui": not has_ui and any(s.get("tool_or_library") for s in stacks),
        # Code with a structure of its own, not yet in modules/: `aidd init` keeps that structure (`modular_monolith` off).
        "existing_code": len([r for r in rels if r.endswith(source_ext)]) >= EXISTING_CODE_FILES and not (root / "modules").is_dir(),
        "aidd_configured": (root / cfgmod.CONFIG_PATH).is_file(),
        "monorepo": monorepo,
        "stacks": stacks,
        "tests": [s for s in stacks if s["test"]],
        # Lint and type checks the repository configures: proposed as `tests` entries, never written by `aidd init`.
        "checks": sorted(checks.values(), key=lambda c: (c["path"], list(KIND_LABEL).index(c["kind"]), c["tool"])),
        "packs": sorted({p for s in stacks for p in s["packs"]}),
        "risk_rules": sorted(sensitive.values(), key=lambda r: r["name"]),
        # Deploy and infrastructure commands `aidd init` holds for a person, as `guard.held_commands` entries.
        "held_commands": held[0],
        "not_held": held[1],  # deploy script names past MAX_HELD_SCRIPTS
        "dependency_rules": gate.dependency_rules(manifests),
        "budget_exclude_paths": generated,
        "untested": untested,
        "codeowners": codeowners,
        "ci": ci,
        "agent_files": [f for f in AGENT_FILES if (root / f).is_file()],
        "spec_tools": sorted(tool for d, tool in SPEC_TOOLS.items() if (root / d).is_dir()),
        "secrets": secrets(root, rels),
        "folders": len(folders),
        "files": len(files),
        "truncated": len(files) >= MAX_FILES,
    }


# Test runners by the word their command names; a package script (`npm test`) names no runner, so it adds none.
RUNNERS = ("pytest", "unittest", "vitest", "jest", "mocha", "playwright", "rspec", "phpunit", "go test", "cargo test", "dotnet test", "flutter test")


def stack_radar(found: dict) -> list[str]:
    """What `aidd init` pre-fills as `project.stack.adopt`: each detected stack, then each test runner, once."""
    out = [s["stack"] for s in found["stacks"] if s["manifest"] != "*.tf"]
    for s in found["tests"]:
        cmd = " ".join(s["test"])
        out += [r for r in RUNNERS if re.search(rf"(?<![\w-]){re.escape(r)}(?![\w-])", cmd)]
    return list(dict.fromkeys(out))


def secrets(root: Path, rels: list[str]) -> dict:
    """{"env_files": tracked environment files, "files": [(path, kinds)]}: what looks like a secret in the repository, by
    file and kind, never the value. Tracked files when git knows them, else the files found."""
    from aidd.kernel import git

    tracked = [p for p in git.run(["ls-files", "-z"], str(root), check=False).split("\0") if p] if (root / ".git").exists() else rels
    env = [p for p in tracked if ENV_FILE.search(p) and not ENV_EXAMPLE.search(p)]
    found: list[tuple[str, list[str]]] = []
    for rel in tracked[:MAX_FILES]:
        path = root / rel
        if len(found) >= MAX_SECRET_FILES or not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        kinds: list[str] = []
        for line in _read(path).splitlines():
            kinds += [k for k in gate.secret_kinds(line) if k not in kinds]
        if kinds:
            found.append((rel, kinds))
    return {"env_files": env, "files": found}


def found_to_fit(s: dict) -> list[str]:
    """What detection found that the new config should fit, each named: only what is there, never a list of kinds that
    might be. Empty when nothing needs fitting."""
    out = []
    if s["risk_rules"]:
        out.append("sensitive areas " + ", ".join(f"{r['name']} ({', '.join(r['paths'][:2])})" for r in s["risk_rules"][:3]))
    if s["budget_exclude_paths"]:
        out.append("generated code " + ", ".join(s["budget_exclude_paths"][:3]))
    if s["codeowners"]:
        out.append(f"owners in {s['codeowners']}")
    if s["monorepo"]:
        out.append(f"{len([x for x in s['stacks'] if x['path'] != '.'])} packages (a monorepo)")
    if s["untested"]:
        out.append("folders without tests " + ", ".join(s["untested"][:3]))
    return out


KIND_LABEL = {"lint": "lint", "types": "type check", "check": "the build's own checks"}


def config_snippet(s: dict) -> str:
    """The config `aidd init --dry-run` proposes, to review and merge into .aidd/config.yaml in the setup change."""
    out = ["# Proposed by `aidd init --dry-run`. Review every line: it reads file names and manifests, not intent."]
    if s["budget_exclude_paths"]:
        out.append(f"budget_exclude_paths: {strict_yaml.flow(s['budget_exclude_paths'])}   # generated or vendored code")
    if s["codeowners"]:
        out += ["", "owners:", "  codeowners: true   # per-path approvers from " + s["codeowners"]]
    entries = [("", "unit", "", t["test"], t["path"]) for t in s["tests"]]
    entries += [
        (f"   # {KIND_LABEL[c['kind']]}, which the repository already configures", c["tool"], f"{c['tool']}-", c["command"], c["path"])
        for c in s.get("checks", [])
    ]
    if entries:
        out += ["", "tests:"]
    for note, root_name, prefix, command, path in entries:
        name = root_name if path == "." else prefix + re.sub(r"[^a-z0-9-]+", "-", path.lower()).strip("-")
        out += [f"  - name: {strict_yaml.scalar(name)}{note}", f"    command: {strict_yaml.flow(command)}"]
        if s["monorepo"] and path != ".":
            out.append(f"    when_changed: {strict_yaml.flow([path + '/**'])}")
    if s["risk_rules"]:
        out += ["", "risk_rules:"]
    for r in s["risk_rules"]:
        out += strict_yaml.dump_lines({"risk_rules": [{"name": r["name"], "paths": r["paths"], "dimensions": r["dimensions"]}]})[1:]
    if s.get("held_commands"):
        out += ["", held_yaml(s["held_commands"]).rstrip("\n")]
    return "\n".join(out) + "\n"


def detection_markdown(s: dict) -> str:
    lines = [
        "# What aidd init found",
        "",
        f"{s['files']} files in {s['folders']} folders" + (" (stopped early: a very large tree)" if s["truncated"] else "") + ".",
    ]
    if s["aidd_configured"]:
        lines.append("aidd is already set up here; compare the proposals below with .aidd/config.yaml.")
    lines += ["", "## Stacks and tests", ""]
    if s["stacks"]:
        lines += [
            f"- `{x['path']}`: {x['stack']} ({x['manifest']})" + (f"; tests: `{' '.join(x['test'])}`" if x["test"] else "; no test command found")
            for x in s["stacks"]
        ]
    else:
        lines.append("- none recognized; name the test command yourself with `aidd init --test`")
    if s["monorepo"]:
        lines.append("- a monorepo: one `tests` entry per package, each with `when_changed`, and an `owners.paths` entry for each package's approvers")
    if not s["tests"]:
        lines.append("- no test suite: every Spec brings a characterization test first (Characterization)")
        lines.append(
            "- no test command: every change fails `tests` until one exists, so `aidd init` binds a smoke test in the setup commit. "
            "The smoke test checks that every tracked Python file parses and that no file holds a conflict marker. "
            "`--test` names your real suite instead"
        )
    if s.get("checks"):
        lines.append(
            "- lint and type checks the repository already configures, proposed as `tests` entries below (`aidd init` writes only the test command): "
            + ", ".join(f"`{' '.join(c['command'])}` ({KIND_LABEL[c['kind']]}{'' if c['path'] == '.' else ', ' + c['path']})" for c in s["checks"])
        )
    lines += ["", "## For the delivery team", ""]
    lines.append("- domain packs to name in Specs: " + (", ".join(f"`aidd-team:{p}`" for p in s["packs"]) or "none detected; the roles' own standards apply"))
    if s["untested"]:
        lines.append("- code with no tests beside it, where the first change needs a characterization test: " + ", ".join(f"`{d}/`" for d in s["untested"]))
    if s["agent_files"]:
        lines.append("- agent instructions already here, which `aidd init` keeps and points at the skill: " + ", ".join(f"`{f}`" for f in s["agent_files"]))
    if s["spec_tools"]:
        lines.append("- planning tools already here, which stay: " + ", ".join(s["spec_tools"]) + "; they plan, aidd gates")
    found = s.get("secrets") or {}
    if found.get("env_files") or found.get("files"):
        lines += ["", "## Secrets", ""]
        for env in found.get("env_files", []):
            lines.append(f"- `{env}` is tracked by git: take it out (`git rm --cached {env}`), rotate what it holds; `aidd init` ignores `.env*`")
        for rel, kinds in found.get("files", []):
            lines.append(f"- `{rel}` holds a line shaped like {', '.join(kinds)}: if it is real, rotate it and load it from the environment")
    lines += ["", "## Risk and ownership", ""]
    if s["risk_rules"]:
        lines += [
            f"- `{r['name']}`: {', '.join(f'`{p}`' for p in r['paths'])} ({', '.join(r['dimensions'])}), which the baseline rules do not cover"
            for r in s["risk_rules"]
        ]
    else:
        lines.append("- no sensitive area beyond what the baseline rules already cover")
    for d in s.get("dependency_rules", []):
        where = ", ".join(f"`{m}`" for m in d["manifests"])
        lines.append(
            f"- {where} declares {', '.join(d['dependencies'])}, which `{d['rule']}` watches. The rule fires when a change adds "
            "one, and code that already uses it outside the rule's paths needs its folders in a `risk_rules` entry"
        )
    if s.get("held_commands"):
        lines.append(
            "- deploy and infrastructure commands `aidd init` holds for a person in `guard.held_commands`: "
            + ", ".join(f"`{g['name']}`" for g in s["held_commands"])
            + ". A person may delete any of them"
            + (f". {s['not_held']} more deploy script names are not held; a person can add them" if s.get("not_held") else "")
        )
    if s["budget_exclude_paths"]:
        lines.append("- generated or vendored code to keep out of the changed-line budget: " + ", ".join(f"`{p}`" for p in s["budget_exclude_paths"]))
    lines.append(
        f"- owners: {'`' + s['codeowners'] + '` exists, so `owners.codeowners: true` reuses it' if s['codeowners'] else 'no CODEOWNERS; name approvers per area in `owners.paths` if areas have different owners'}"
    )
    lines.append(
        "- CI: "
        + (
            ", ".join(f"`{c}`" for c in s["ci"]) + "; to reuse its checks as evidence, list their names in `evidence.status_checks`"
            if s["ci"]
            else "none found; `aidd init` writes the test workflow"
        )
    )
    lines += [
        "",
        "## Proposed config",
        "",
        "```yaml",
        config_snippet(s).rstrip(),
        "```",
        "",
        "Nothing was written. Next: run `aidd init` in a setup change (with `--team` for the delivery team). "
        "`aidd init` uses the detected test command unless you pass `--test`. Merge the rest of this config after review. "
        "Keep the gate advisory until its findings match your judgment.",
    ]
    return "\n".join(lines) + "\n"
