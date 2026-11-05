"""What `aidd init` finds in a repository before it writes anything, and what it proposes to fit aidd and the team to it.

Adopting aidd in a repository that already exists means knowing its test commands, its sensitive areas, its
generated code, its owners, and its CI. People rarely have that written down. `aidd init` finds it from the files
alone, with no model and no network, and proposes the config to match. `aidd init --dry-run` prints it and writes
nothing. `aidd init` uses the detected test command and leaves the rest as suggestions, for a person to review in the
setup change.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path, PurePosixPath

from aidd import config as cfgmod
from aidd.kernel import command_names, documents, globs, regular_files, resources, secret_patterns, strict_yaml
from aidd.setup import ignore_lines, manifests

SKIP = {".git", "node_modules", "vendor", "third_party", "dist", "build", "out", "target", ".next", "coverage", ".venv", "venv", "__pycache__", ".tox"}
MAX_DEPTH = 3
MAX_FILES = 20000


# Directory names that point to sensitive work the built-in risk areas may not name, with the risk they carry.
SENSITIVE = (
    (("payment", "payments", "billing", "invoice", "invoices", "checkout", "pricing", "ledger", "wallet"), "payments", ["financial"]),
    (("pii", "gdpr", "consent", "privacy", "profile", "profiles", "customer", "customers", "users", "patient", "patients"), "personal_data", ["privacy"]),
    (("login", "session", "sessions", "oauth", "sso", "saml", "token", "tokens", "password", "passwords"), "sign_in", ["security"]),
    (("ai", "llm", "prompts"), "ai", ["security", "compliance"]),
)
# File names that deploy or release: a change to one reaches production, whatever folder it is in.
DEPLOY_FILE = re.compile(r"^(?:deploy|release|rollout|provision)[\w.-]{0,40}\.(?:sh|bash|ps1|py|rb|js|ts)$", re.I)
# The files that build, ship, or run the code, by type, as globs: the SRE starts on onboarding when the dry run lists one.
# A new CI system, container tool, or infrastructure tool is a row here, never new code.
OPERATIONS_FILES = (
    (
        "ci",
        (
            ".github/workflows/*.yml",
            ".github/workflows/*.yaml",
            ".gitlab-ci.yml",
            ".circleci/config.yml",
            "**/Jenkinsfile",
            "azure-pipelines.yml",
            "bitbucket-pipelines.yml",
        ),
    ),
    (
        "container",
        ("**/Dockerfile", "**/*.Dockerfile", "**/Containerfile", "**/compose.yaml", "**/compose.yml", "**/docker-compose.yaml", "**/docker-compose.yml"),
    ),
    (
        "infrastructure",
        (
            "**/*.tf",
            "**/*.tofu",
            "**/Chart.yaml",
            "**/kustomization.yaml",
            "**/k8s/**/*.yaml",
            "**/k8s/**/*.yml",
            "**/kubernetes/**/*.yaml",
            "**/kubernetes/**/*.yml",
        ),
    ),
)
MAX_OPERATIONS_SHOWN = 10
GENERATED = ("generated", "gen", "__generated__", "autogen", "vendor", "third_party", "dist", "build")
# Environment files: they hold secrets, and their example does not.
ENV_FILE = re.compile(r"(?:^|/)\.env(?:\.[\w.-]+)?$")
ENV_EXAMPLE = re.compile(r"\.(?:example|sample|template|dist)$")
MAX_SECRET_FILES = 20
# The detected files are listed in this order.
AGENT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules", ".github/copilot-instructions.md")
SPEC_TOOLS = {".specify": "GitHub Spec Kit", "openspec": "OpenSpec", ".kiro": "Kiro"}


def _walk(root: Path) -> list[Path]:
    found: list[Path] = []

    def visit(folder: Path, depth: int) -> None:
        if depth > MAX_DEPTH or len(found) >= MAX_FILES:
            return
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            return
        for p in entries:
            if p.is_symlink():
                continue  # a link may point out of the repository; what it names is not the repository's to describe
            if p.is_dir():
                if p.name not in SKIP and not (p.name.startswith(".") and p.name not in (".github", ".gitlab", ".circleci", ".specify", ".kiro")):
                    visit(p, depth + 1)
            elif len(found) < MAX_FILES:
                found.append(p)

    visit(root, 0)
    return found


# The most of one file detection reads.
MAX_READ = 200_000


def _read(p: Path, limit: int = MAX_READ) -> str:
    """The first `limit` bytes of a regular file, as text, never through a link and never from a device or a pipe,
    which a read could hang on; "" for anything else. A larger file is read in part, never taken for an empty one."""
    raw = regular_files.file_head(regular_files.working_root(p), p, limit)
    return raw.decode("utf-8", errors="replace") if raw else ""


# The most of one file the secret scan reads: the files it scans, which are at most this size, whole.
MAX_SECRET_READ = 1_000_000


def _stack(p: Path, root: Path) -> dict | None:
    """What one manifest says: the stack, a test command to run from the repository root, and pack hints. It reads a file
    only when its name is a manifest's (`cfgmod.manifest_names`, from schemas/languages.json): a file of any other name is never opened."""
    if p.name not in cfgmod.manifest_names() and not p.name.endswith((".sln", ".csproj")):
        return None
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
        start = None if "pytest" in text or (folder / "conftest.py").exists() else _unittest_start(folder)
        if start is not None:
            cmd = _unittest_command(folder, rel, start)
        elif "pytest" in text or (folder / "tests").is_dir() or (folder / "conftest.py").exists():
            # The project's own runner when its lockfile says which: uv, then Poetry; plain pytest otherwise.
            cmd = _python_command(folder, rel, ["pytest"], [rel] if rel else [], bare=["python3", "-m", "pytest"])
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
    elif name == "CMakeLists.txt" and re.search(r"^\s*project\s*\(", text, re.I | re.M):
        stack = "C/C++ (CMake)"  # a CMake project's top file: the files it includes name no project
    elif name == "Makefile" and re.search(r"^test:", text, re.M) and not rel:
        stack, cmd = "Make", ["make", "test"]
    if stack is None:
        return None
    packs = manifests.dependency_packs_for(manifests.declared_dependencies(p.name, text))
    checks = _checks(name, folder, rel, text)
    return {
        "path": rel or ".",
        "manifest": p.relative_to(root).as_posix(),
        "stack": stack,
        "test": cmd,
        "packs": packs,
        "checks": checks,
        "tool_or_library": _tool_or_library(name, text),
    }


# What says a manifest builds a command-line tool or a library: an entry point, a package build, or a language whose
# module is one. A user interface anywhere in the repository (`UI_FILE`, or a web, mobile, or desktop pack) overrides it.
UI_FILE = re.compile(r"\.(?:html?|jsx|tsx|vue|svelte|astro|css|scss|sass|less|storyboard|xib)$", re.I)
UI_PACKS = frozenset({"web-front-end", "mobile-apps", "desktop-apps"})
# A repository with this many source files already has a structure: `aidd init` writes the `modular_monolith` product
# default off there, with the reason, so the structure stays as it is. A fresh scaffold has fewer.
EXISTING_CODE_FILES = 20


# What says a Python folder's tests are `unittest` tests: a test file that imports it, and none that imports pytest.
UNITTEST_IMPORT = re.compile(r"^\s*(?:import|from)\s+unittest\b", re.M)
PYTEST_IMPORT = re.compile(r"^\s*(?:import|from)\s+pytest\b", re.M)
MAX_TEST_FILES = 50


def _unittest_start(folder: Path) -> str | None:
    """Where `python -m unittest discover` starts in `folder` ("tests", or "" for the folder itself), when its `test*.py`
    files are `unittest` tests alone; None when none imports unittest, or one imports pytest."""
    for start in ("tests", ""):
        texts = [_read(p) for p in sorted((folder / start).glob("test*.py"))[:MAX_TEST_FILES]]
        if any(PYTEST_IMPORT.search(t) for t in texts):
            return None
        if any(UNITTEST_IMPORT.search(t) for t in texts):
            return start
    return None


def _unittest_command(folder: Path, rel: str, start: str) -> list[str]:
    """`python -m unittest discover` from `start`, through the project's runner (uv, Poetry) when its lockfile says which."""
    where = "/".join(part for part in (rel, start) if part) or "."
    target, inside = ["discover", "-s", where], ["discover", "-s", start or "."]
    return _python_command(folder, rel, ["python", "-m", "unittest"], target, runner_target=inside, bare=["python3", "-m", "unittest"])


def _tool_or_library(name: str, text: str) -> bool:
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
TYPECHECK_SCRIPTS = ("typecheck", "type-check", "types", "tsc")  # the first one the package defines wins


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


def _python_command(
    folder: Path, rel: str, args: list[str], target: list[str], runner_target: list[str] | None = None, bare: list[str] | None = None
) -> list[str]:
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

    def add(check_type: str, tool: str, command: list[str]) -> None:
        out.append({"type": check_type, "tool": tool, "command": command})

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
            add("lint", "ruff", _python_command(folder, rel, ["ruff", "check"], target))
        mypy_ini = next((f for f in ("mypy.ini", ".mypy.ini") if (folder / f).is_file()), None)
        if mypy_ini or re.search(r"^\[tool\.mypy\]", pyproject, re.M) or re.search(r"^\[mypy\]", setup_cfg, re.M):
            # With `files` in its configuration, mypy knows what to check; otherwise it is given the package folder.
            config = (_read(folder / mypy_ini) if mypy_ini else "") + pyproject + setup_cfg
            names_files = re.search(r"^\s*files\s*=", config, re.M) is not None
            # Through uv or Poetry it runs in the package folder, so it is given that folder as `.`.
            add("types", "mypy", _python_command(folder, rel, ["mypy"], [] if names_files and not rel else (target or ["."]), [] if names_files else ["."]))
    elif name == "go.mod":
        add("lint", "go-vet", ["go", "vet", f"./{rel}/..." if rel else "./..."])
    elif name == "Cargo.toml" and ("[package]" in text or "[workspace]" in text):
        add("lint", "clippy", ["cargo", "clippy", *(["--manifest-path", f"{rel}/Cargo.toml"] if rel else []), "--", "-D", "warnings"])
    elif name == "pom.xml":
        add("check", "maven-verify", _maven(folder, rel) + ["-q", "verify"] + (["-f", f"{rel}/pom.xml"] if rel else []))
    elif name in ("build.gradle", "build.gradle.kts"):
        add("check", "gradle-check", _gradle(folder, rel) + ["check"] + (["-p", rel] if rel else []))
    return out


def detect(root: Path) -> dict:
    root = root.resolve()
    files = _walk(root)
    rels = [p.relative_to(root).as_posix() for p in files]
    stacks = [s for p in files if (s := _stack(p, root))]
    if not any(s["path"] == "." for s in stacks) and (start := _unittest_start(root)) is not None:  # tests alone name the stack
        stacks.append(
            {
                "path": ".",
                "manifest": f"{start}/test*.py" if start else "test*.py",
                "stack": "Python",
                "test": _unittest_command(root, "", start),
                "packs": [],
                "checks": [],
                "tool_or_library": False,
            }
        )
    stack_names = sorted({s["stack"] for s in stacks})  # every manifest's, before one stack per folder wins
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

    covered = [p for a in resources.load_json("risks.json")["areas"].values() for p in a["paths"]]
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

    tested = {str(PurePosixPath(r).parent) for r in rels if cfgmod.looks_like_test(r)}
    source_ext = cfgmod.source_extensions()
    top_source = sorted({Path(r).parts[0] for r in rels if r.endswith(source_ext) and len(Path(r).parts) > 1})
    untested = [d for d in top_source if not any(t == d or t.startswith(d + "/") for t in tested) and not (root / "tests").is_dir()]

    asks = ask_first(rels, dirs)
    codeowners = next((c for c in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS") if (root / c).is_file()), None)
    ci = sorted(r for r in rels if r.startswith(".github/workflows/") and r.endswith((".yml", ".yaml"))) + (
        [".gitlab-ci.yml"] if ".gitlab-ci.yml" in rels else []
    )
    has_ui = any(UI_FILE.search(r) for r in rels) or any(UI_PACKS & set(s["packs"]) for s in stacks)
    operations = [{"path": r, "type": kind} for r in rels for kind, paths in OPERATIONS_FILES if globs.match_any(paths, r)]
    operations += [{"path": r, "type": "deploy"} for r in rels if DEPLOY_FILE.match(Path(r).name)]
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
        "checks": sorted(checks.values(), key=lambda c: (c["path"], list(CHECK_LABEL).index(c["type"]), c["tool"])),
        "packs": sorted({p for s in stacks for p in s["packs"]}),
        # Folders that look sensitive and no built-in area covers: `aidd init` writes them as `risks.areas`.
        "risk_areas": sorted(sensitive.values(), key=lambda r: r["name"]),
        "generated": generated,
        "untested": untested,
        "codeowners": codeowners,
        "ci": ci,
        # The files that build, ship, or run the code (OPERATIONS_FILES, and the deploy scripts), each with its type.
        "operations": sorted(operations, key=lambda o: o["path"]),
        "remotes": git_remotes(root),
        # The folders and files a built-in area covers where an edit asks first: what a person meets on day one.
        "ask_first": asks,
        "agent_files": [f for f in AGENT_FILES if (root / f).is_file()],
        "spec_tools": sorted(tool for d, tool in SPEC_TOOLS.items() if (root / d).is_dir()),
        "secrets": secrets(root, rels),
        # What `aidd init` adds to .gitignore, so what a test run leaves keeps the tree clean.
        "test_outputs_ignore": ignore_lines.missing_ignore_lines(root, _read(root / ".gitignore") if (root / ".gitignore").is_file() else "", stack_names),
        "folders": len(folders),
        "files": len(files),
        "truncated": len(files) >= MAX_FILES,
    }


def stack_names(root: Path) -> list[str]:
    """Every stack a manifest in the repository names, as `detect` finds them, for `aidd upgrade`'s .gitignore lines."""
    root = root.resolve()
    return sorted({s["stack"] for p in _walk(root) if (s := _stack(p, root))})


def stack_radar(found: dict) -> list[str]:
    """What `aidd init` pre-fills as `project.stack.adopt`: each detected stack, then each test runner, once. A runner is found by the
    name schemas/test-runners.json gives, in its order; a package script (`npm test`) names no runner, so it adds none."""
    out = [s["stack"] for s in found["stacks"] if s["manifest"] != "*.tf"]
    for s in found["tests"]:
        cmd = " ".join(s["test"])
        out += [r for r in cfgmod.test_runner_names() if re.search(rf"(?<![\w-]){re.escape(r)}(?![\w-])", cmd)]
    return list(dict.fromkeys(out))


def secrets(root: Path, rels: list[str]) -> dict:
    """{"env_files": tracked environment files, "files": [(path, shapes)]}: what looks like a secret in the repository, by
    file and shape, never the value. Tracked files when git knows them, else the files found."""
    from aidd.kernel import git

    tracked = [p for p in git.run(["ls-files", "-z"], str(root), check=False).split("\0") if p] if (root / ".git").exists() else rels
    env = [p for p in tracked if ENV_FILE.search(p) and not ENV_EXAMPLE.search(p)]
    found: list[tuple[str, list[str]]] = []
    for rel in tracked[:MAX_FILES]:
        path = root / rel
        if len(found) >= MAX_SECRET_FILES or regular_files.link_on_the_way(root, rel) or not path.is_file() or path.stat().st_size > MAX_SECRET_READ:
            continue  # a link may name a file outside the repository, such as a key, so no shape of it is read
        shapes: list[str] = []
        for line in _read(path, MAX_SECRET_READ).splitlines():
            shapes += [k for k in secret_patterns.secret_types(line) if k not in shapes]
        if shapes:
            found.append((rel, shapes))
    return {"env_files": env, "files": found}


def found_to_fit(detected: dict) -> list[str]:
    """What detection found that the new config should fit, each named: only what is there, never a list of types that
    might be. Empty when nothing needs fitting."""
    out = []
    if detected["risk_areas"]:
        out.append("sensitive areas " + ", ".join(f"{r['name']} ({', '.join(r['paths'][:2])})" for r in detected["risk_areas"][:3]))
    if detected["codeowners"]:
        out.append(f"owners in {detected['codeowners']}")
    if detected["monorepo"]:
        out.append(f"{len([x for x in detected['stacks'] if x['path'] != '.'])} packages (a monorepo)")
    if detected["untested"]:
        out.append("folders without tests " + ", ".join(detected["untested"][:3]))
    return out


# The most folders and files the dry run names as asking first; the rest are counted.
MAX_ASK_FIRST = 10


def ask_first(rels: list[str], dirs: list[str]) -> list[dict]:
    """The topmost folders, and the files outside them, that a built-in area covers where the built-in rules ask before an
    edit (`code.edit`), each with its area, such as `src/auth/` (auth)."""
    data = resources.load_json("risks.json")
    asking = [r["area"] for r in data["rules"] if r["action"] == "code.edit" and r.get("area") and r["level"] == "ask"]
    out: list[dict] = []
    for area in asking:
        paths = data["areas"][area]["paths"]
        hit = [d for d in dirs if globs.match_any(paths, d + "/x", fold_case=True)]
        top = [d for d in hit if not any(d.startswith(h + "/") for h in hit)]
        files = [r for r in rels if globs.match_any(paths, r, fold_case=True) and not any(r.startswith(t + "/") for t in top)]
        out += [{"path": d + "/", "area": area} for d in top] + [{"path": f, "area": area} for f in files]
    return out


def git_remotes(root: Path) -> list[str]:
    """The repository's git remotes, by name; [] for none, or outside a repository."""
    from aidd.kernel import git

    return git.run(["remote"], str(root), check=False).split()


# Checks sort by this order.
CHECK_LABEL = {"lint": "lint", "types": "type check", "check": "the build's own checks"}


def config_snippet(detected: dict) -> str:
    """The config `aidd init --dry-run` proposes, to review and merge into .aidd/config.yaml in the setup change."""
    out = ["# Proposed by `aidd init --dry-run`. Review every line: it reads file names and manifests, not intent."]
    entries = [("", "unit", "", t["test"], t["path"]) for t in detected["tests"]]
    entries += [
        (f"   # {CHECK_LABEL[c['type']]}, which the repository already configures", c["tool"], f"{c['tool']}-", c["command"], c["path"])
        for c in detected.get("checks", [])
    ]
    if entries:
        out += ["", "tests:"]
    for note, root_name, prefix, command, path in entries:
        name = root_name if path == "." else prefix + re.sub(r"[^a-z0-9-]+", "-", path.lower()).strip("-")
        out += [f"  - name: {strict_yaml.scalar(name)}{note}", f"    command: {strict_yaml.flow(command)}"]
        if detected["monorepo"] and path != ".":
            out.append(f"    when_changed: {strict_yaml.flow([path + '/**'])}")
    if detected["risk_areas"]:
        out += ["", *risk_areas_yaml(detected["risk_areas"]).rstrip("\n").split("\n")]
    return "\n".join(out) + "\n"


def detection_markdown(detected: dict, written: str = "", steps: list[str] | None = None, heading: str = "The config `aidd init` writes") -> str:
    """What `aidd init --dry-run` prints. `steps` are the lines a real run prints, as init_plan words them, and `written` is
    the config it leaves, under `heading` (`init_plan.Plan`). The lint and type checks the repository configures follow it, as entries to add after review."""
    lines = [
        "# What aidd init found",
        "",
        f"{detected['files']} files in {detected['folders']} folders" + (" (stopped early: a very large tree)" if detected["truncated"] else "") + ".",
    ]
    if detected["aidd_configured"]:
        lines.append("aidd is already set up here; compare the proposals below with .aidd/config.yaml.")
    lines += ["", "## Stacks and tests", ""]
    if detected["stacks"]:
        lines += [
            f"- `{x['path']}`: {x['stack']} ({x['manifest']})" + (f"; tests: `{shlex.join(x['test'])}`" if x["test"] else "; no test command found")
            for x in detected["stacks"]
        ]
    else:
        lines.append("- none recognized; name the test command yourself with `aidd init --test`")
    if detected["monorepo"]:
        lines.append("- a monorepo: one `tests` entry per package, each with `when_changed`")
    if not detected["tests"]:
        lines.append("- no test suite: every Spec brings a test that pins today's behavior first")
        lines.append(
            "- no test command: `aidd init` binds a smoke test in the setup commit, which checks that every tracked Python file parses "
            "and that no file holds a conflict marker. `--test` names your real suite instead"
        )
    if detected.get("checks"):
        lines.append(
            "- lint and type checks the repository already configures, proposed as `tests` entries below (`aidd init` writes only the test command): "
            + ", ".join(f"`{shlex.join(c['command'])}` ({CHECK_LABEL[c['type']]}{'' if c['path'] == '.' else ', ' + c['path']})" for c in detected["checks"])
        )
    if detected.get("test_outputs_ignore"):
        lines.append(f"- `aidd init` adds lines to `.gitignore`, so {ignore_lines.ignore_lines_reason(detected['test_outputs_ignore'])}")
    lines += ["", "## For the delivery team", ""]
    lines.append(
        "- domain packs to name in Specs: "
        + (", ".join(f"`{cfgmod.PACKS_PLUGIN}:{p}`" for p in detected["packs"]) or "none detected; the roles' own standards apply")
    )
    if detected["untested"]:
        lines.append(
            "- code with no tests beside it, where the first change needs a test that pins today's behavior: "
            + ", ".join(f"`{d}/`" for d in detected["untested"])
        )
    if detected["agent_files"]:
        lines.append(
            "- agent instructions already here, which `aidd init` keeps and points at the skill: " + ", ".join(f"`{f}`" for f in detected["agent_files"])
        )
    if detected["spec_tools"]:
        lines.append("- planning tools already here, which stay: " + ", ".join(detected["spec_tools"]) + "; they plan, aidd advises")
    found = detected.get("secrets") or {}
    if found.get("env_files") or found.get("files"):
        lines += ["", "## Secrets", ""]
        for env in found.get("env_files", []):
            word = command_names.quoted(env)
            out = f"`git rm --cached -- {word}`" if word else f"by hand: {command_names.NO_COMMAND}"
            lines.append(f"- `{env}` is tracked by git: take it out ({out}), rotate what it holds; `aidd init` ignores `.env*`")
        for rel, shapes in found.get("files", []):
            lines.append(f"- `{rel}` holds a line shaped like {', '.join(shapes)}: if it is real, rotate it and load it from the environment")
    lines += ["", "## Risk", ""]
    if detected["risk_areas"]:
        lines += [
            f"- `{r['name']}`: {', '.join(f'`{p}`' for p in r['paths'])} ({', '.join(r['dimensions'])}), which no built-in area covers: "
            "`aidd init` writes it as a risk area, and an agent asks before it edits there"
            for r in detected["risk_areas"]
        ]
    else:
        lines.append("- no sensitive folder beyond what the built-in areas cover (`aidd risk --list`)")
    asks = detected.get("ask_first") or []
    if asks:
        shown = ", ".join(f"`{a['path']}` ({a['area']})" for a in asks[:MAX_ASK_FIRST]) + (
            f", and {len(asks) - MAX_ASK_FIRST} more" if len(asks) > MAX_ASK_FIRST else ""
        )
        lines.append(f"- your folders where an agent asks you before it edits, by the built-in areas: {shown}")
    if detected["ci"]:
        lines.append("- CI: " + ", ".join(f"`{c}`" for c in detected["ci"]) + "; `aidd init --ci github` adds the aidd test workflow beside them")
    elif detected.get("remotes"):
        lines.append("- CI: none found; `aidd init` writes the aidd test workflow for GitHub (`--ci gitlab` for GitLab, `--ci none` for none)")
    else:
        lines.append("- CI: none found, and no git remote, so `aidd init` writes no CI files. Add them later with `aidd init --ci github` or `--ci gitlab`")
    ops = detected.get("operations") or []
    if ops:
        shown = ", ".join(f"`{o['path']}` ({o['type']})" for o in ops[:MAX_OPERATIONS_SHOWN])
        lines.append(
            f"- files that build, ship, or run the code: {shown}" + (f", and {len(ops) - MAX_OPERATIONS_SHOWN} more" if len(ops) > MAX_OPERATIONS_SHOWN else "")
        )
    extra = config_snippet({**detected, "tests": [], "risk_areas": []}) if detected.get("checks") else ""
    # A path or a name read from the repository may hold a control character: each line shows it as a space. The config below is
    # data written for a file, so it is shown as it is.
    lines = [documents.one_line(part, 4000) for line in lines for part in line.split("\n")]
    if steps:
        lines += ["", "## What `aidd init` would do", "", "```", *(documents.one_line(step, 4000) for step in steps), "```"]
    lines += ["", f"## {heading}", "", "```yaml", (written or config_snippet(detected)).rstrip(), "```"]
    if extra:
        lines += ["", "The lint and type checks the repository already configures, to add to `tests` after review:", "", "```yaml", extra.rstrip(), "```"]
    lines += [
        "",
        "Nothing was written. Next: run `aidd init` in a setup change (with `--aidd-team` for the delivery team). "
        "It uses the detected test command unless you pass `--test`.",
    ]
    return "\n".join(lines) + "\n"


def risk_areas_yaml(areas: list[dict]) -> str:
    """The sensitive folders detection found, as a config's `risks` block: each an area that asks before an edit."""
    out = ["risks:", "  areas:"]
    for r in areas:
        out += [f"    {r['name']}:   # found by aidd init; a person may delete it", f"      paths: {strict_yaml.flow(r['paths'])}"]
        if r["dimensions"]:
            out += [f"      dimensions: {strict_yaml.flow(r['dimensions'])}", "      route: major"]
    out += ["  rules:"]
    out += [f"    - {{action: code.edit, area: {r['name']}, level: ask}}" for r in areas]
    return "\n".join(out) + "\n"
