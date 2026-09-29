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
from pathlib import Path, PurePosixPath

from . import config as cfgmod
from . import globs, resources
from .util import toml_list

SKIP = {".git", "node_modules", "vendor", "third_party", "dist", "build", "target", ".venv", "venv", "__pycache__", ".next", ".tox", "out", "coverage"}
MAX_DEPTH = 3
MAX_FILES = 20000

# Domain packs, from the dependencies a manifest declares. A name ending in "/" is a prefix (an npm scope or a Go module
# path); anything else must match a dependency name exactly. Current, widely used stacks only: an absent hint means the
# roles' own standards apply, which is safe; a wrong hint loads the wrong checklist.
PACK_HINTS: dict[str, tuple[str, ...]] = {
    "web-front-end": tuple(
        (
            "react react-dom next vue nuxt svelte @sveltejs/kit @angular/core solid-js astro react-router @remix-run/ @tanstack/react-router "
            "qwik @builder.io/qwik htmx.org"
        ).split()
    ),
    "apis-and-services": tuple(
        (
            "express fastify hono @nestjs/core koa @trpc/server @apollo/server graphql-yoga elysia fastapi django djangorestframework flask "
            "litestar starlette grpcio github.com/gin-gonic/gin github.com/labstack/echo/ github.com/gofiber/fiber/ github.com/go-chi/chi/ "
            "google.golang.org/grpc connectrpc.com/connect axum actix-web tonic rocket poem spring-boot-starter-web spring-boot-starter-webflux "
            "quarkus-rest micronaut-http-server-netty ktor-server-core rails sinatra laravel/framework symfony/framework-bundle "
            "Microsoft.AspNetCore.OpenApi phoenix"
        ).split()
    ),
    "mobile-apps": tuple("react-native expo flutter com.android.application androidx.compose.ui".split()),
    "ai-features": tuple(
        (
            "openai anthropic @anthropic-ai/sdk ai @ai-sdk/ google-genai @google/genai mistralai @mistralai/mistralai ollama litellm "
            "transformers torch instructor dspy langchain langchain-core @langchain/core llama-index llamaindex sentence-transformers "
            "com.anthropic:anthropic-java github.com/anthropics/anthropic-sdk-go github.com/openai/openai-go"
        ).split()
    ),
    "ai-agents-and-tools": tuple(
        (
            "@modelcontextprotocol/sdk mcp fastmcp claude-agent-sdk @anthropic-ai/claude-agent-sdk openai-agents @openai/agents langgraph "
            "@langchain/langgraph pydantic-ai crewai autogen-agentchat ag2 @mastra/core google-adk github.com/mark3labs/mcp-go "
            "github.com/modelcontextprotocol/go-sdk rmcp"
        ).split()
    ),
    "data-and-analytics": tuple(
        (
            "pandas polars pyspark duckdb dbt-core apache-airflow dagster prefect great-expectations pyarrow clickhouse-connect "
            "@clickhouse/client kafkajs confluent-kafka @duckdb/node-api datafusion"
        ).split()
    ),
    "payments-and-finance": tuple(
        (
            "stripe @stripe/stripe-js @stripe/react-stripe-js @adyen/api-library Adyen braintree @paypal/paypal-js paypal-server-sdk squareup "
            "square @mollie/api-client mollie-api-python github.com/stripe/stripe-go/ stripe-java Stripe.net"
        ).split()
    ),
    "health": tuple("fhir.resources fhirclient @medplum/core hapi-fhir-structures-r4 hl7apy Hl7.Fhir.R4".split()),
    "internationalization": tuple("i18next react-i18next next-intl react-intl vue-i18n @formatjs/intl @lingui/core babel fluent.runtime rails-i18n".split()),
    "cloud-and-infrastructure": tuple("aws-cdk-lib @pulumi/pulumi pulumi cdktf @cdktf/provider-aws sst wrangler".split()),
    "embedded-automotive-industrial": tuple("embedded-hal embassy-executor cortex-m esp-idf-svc zephyr micropython".split()),
}


def _deps(p: Path, text: str) -> set[str]:
    """Dependency names a manifest declares, read the way its ecosystem writes them."""
    name, out = p.name, set()
    try:
        if name in ("package.json", "composer.json"):
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "require", "require-dev"):
                out |= set((data.get(key) or {}).keys())
        elif name in ("pyproject.toml", "Cargo.toml"):
            import tomllib

            data = tomllib.loads(text)
            proj = data.get("project") or {}
            reqs = list(proj.get("dependencies", []))
            for group in list((proj.get("optional-dependencies") or {}).values()) + list((data.get("dependency-groups") or {}).values()):
                reqs += [r for r in group if isinstance(r, str)]
            out |= {re.split(r"[\s\[<>=!~;@(]", r.strip(), maxsplit=1)[0].lower() for r in reqs if r.strip()}
            poetry = (data.get("tool") or {}).get("poetry") or {}
            out |= {k.lower() for k in (poetry.get("dependencies") or {})}
            for table in ("dependencies", "dev-dependencies", "build-dependencies"):
                out |= set((data.get(table) or {}).keys())
            out |= set(((data.get("workspace") or {}).get("dependencies") or {}).keys())
        elif name == "requirements.txt":
            out |= {re.split(r"[\s\[<>=!~;@]", ln.strip(), maxsplit=1)[0].lower() for ln in text.splitlines() if ln.strip() and not ln.startswith(("#", "-"))}
        elif name == "go.mod":
            out |= {m.group(1) for m in re.finditer(r"^\s*(?:require\s+)?([a-z0-9.-]+\.[a-z]+/[^\s]+)\s+v", text, re.M)}
        elif name == "Gemfile":
            out |= set(re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, re.M))
        elif name == "pubspec.yaml":
            out |= set(re.findall(r"^  ([a-z_][a-z0-9_]*):", text, re.M))
        elif name in ("pom.xml",):
            out |= set(re.findall(r"<artifactId>([^<]+)</artifactId>", text))
        elif name in ("build.gradle", "build.gradle.kts"):
            for group, artifact in re.findall(r"['\"]([\w.-]+):([\w.-]+)(?::[^'\"]*)?['\"]", text):
                out |= {artifact, f"{group}:{artifact}"}
            out |= set(re.findall(r"id\s*\(?\s*['\"]([\w.-]+)['\"]", text))
        elif name.endswith(".csproj"):
            out |= set(re.findall(r'PackageReference\s+Include="([^"]+)"', text))
        elif name == "mix.exs":
            out |= set(re.findall(r"\{:([a-z_]+),", text))
    except (ValueError, TypeError, AttributeError):
        pass
    return {d for d in out if d}


def packs_for(deps: set[str]) -> list[str]:
    def hit(hint: str) -> bool:
        return any(d.startswith(hint) for d in deps) if hint.endswith("/") else hint in deps

    return sorted(pack for pack, hints in PACK_HINTS.items() if any(hit(h) for h in hints))


# Directory names that point to sensitive work the baseline rules may not name, with the risk they carry.
SENSITIVE = (
    (("payment", "payments", "billing", "invoice", "invoices", "checkout", "pricing", "ledger", "wallet"), "payments", ["financial"]),
    (("pii", "gdpr", "consent", "privacy", "profile", "profiles", "customer", "customers", "users", "patient", "patients"), "personal-data", ["privacy"]),
    (("login", "session", "sessions", "oauth", "sso", "saml", "token", "tokens", "password", "passwords"), "sign-in", ["security"]),
    (("ai", "llm", "prompts"), "ai", ["security", "compliance"]),
)
GENERATED = ("generated", "gen", "__generated__", "autogen", "vendor", "third_party", "dist", "build")
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
    packs = packs_for(_deps(p, text))
    checks = _checks(name, folder, rel, text)
    return {"path": rel or ".", "manifest": p.relative_to(root).as_posix(), "stack": stack, "test": cmd, "packs": packs, "checks": checks}


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
    if (folder / "bun.lock").exists() or (folder / "bun.lockb").exists():
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
    generated = sorted({f"{d}/**" for d in dirs if Path(d).name.lower() in GENERATED} | {"**/*.pb.go"} & {"**/*.pb.go" for r in rels if r.endswith(".pb.go")})

    tested = {str(PurePosixPath(r).parent) for r in rels if TEST_FILE.search(Path(r).name)} | {d for d in dirs if Path(d).name in TEST_DIRS}
    source_ext = (".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt", ".rb", ".cs", ".php", ".dart", ".swift")
    top_source = sorted({Path(r).parts[0] for r in rels if r.endswith(source_ext) and len(Path(r).parts) > 1})
    untested = [d for d in top_source if d not in TEST_DIRS and not any(t == d or t.startswith(d + "/") for t in tested) and not (root / "tests").is_dir()]

    codeowners = next((c for c in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS") if (root / c).is_file()), None)
    ci = sorted(r for r in rels if r.startswith(".github/workflows/") and r.endswith((".yml", ".yaml"))) + (
        [".gitlab-ci.yml"] if ".gitlab-ci.yml" in rels else []
    )
    return {
        "root": str(root),
        "aidd_configured": (root / cfgmod.CONFIG_PATH).is_file(),
        "monorepo": monorepo,
        "stacks": stacks,
        "tests": [s for s in stacks if s["test"]],
        # Lint and type checks the repository configures: proposed as [[tests]], never written by `aidd init`.
        "checks": sorted(checks.values(), key=lambda c: (c["path"], list(KIND_LABEL).index(c["kind"]), c["tool"])),
        "packs": sorted({p for s in stacks for p in s["packs"]}),
        "risk_rules": sorted(sensitive.values(), key=lambda r: r["name"]),
        "budget_exclude_paths": generated,
        "untested": untested,
        "codeowners": codeowners,
        "ci": ci,
        "agent_files": [f for f in AGENT_FILES if (root / f).is_file()],
        "spec_tools": sorted(tool for d, tool in SPEC_TOOLS.items() if (root / d).is_dir()),
        "folders": len(folders),
        "files": len(files),
        "truncated": len(files) >= MAX_FILES,
    }


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
    """The config `aidd init --dry-run` proposes, to review and merge into .aidd/config.toml in the setup change."""
    out = ["# Proposed by `aidd init --dry-run`. Review every line: it reads file names and manifests, not intent."]
    if s["budget_exclude_paths"]:
        out.append(f"budget_exclude_paths = {toml_list(s['budget_exclude_paths'])}   # generated or vendored code")
    if s["codeowners"]:
        out += ["", "[owners]", "codeowners = true   # per-path approvers from " + s["codeowners"]]
    entries = [("[[tests]]", "unit", "", t["test"], t["path"]) for t in s["tests"]]
    entries += [
        (f"[[tests]]   # {KIND_LABEL[c['kind']]}, which the repository already configures", c["tool"], f"{c['tool']}-", c["command"], c["path"])
        for c in s.get("checks", [])
    ]
    for table, root_name, prefix, command, path in entries:
        name = root_name if path == "." else prefix + re.sub(r"[^a-z0-9-]+", "-", path.lower()).strip("-")
        out += ["", table, f'name = "{name}"', f"command = {toml_list(command)}"]
        if s["monorepo"] and path != ".":
            out.append(f'when_changed = ["{path}/**"]')
    for r in s["risk_rules"]:
        out += ["", "[[risk_rules]]", f'name = "{r["name"]}"', f"paths = {toml_list(r['paths'])}", f"dimensions = {toml_list(r['dimensions'])}"]
    return "\n".join(out) + "\n"


def markdown(s: dict) -> str:
    lines = [
        "# What aidd init found",
        "",
        f"{s['files']} files in {s['folders']} folders" + (" (stopped early: a very large tree)" if s["truncated"] else "") + ".",
    ]
    if s["aidd_configured"]:
        lines.append("aidd is already set up here; compare the proposals below with .aidd/config.toml.")
    lines += ["", "## Stacks and tests", ""]
    if s["stacks"]:
        lines += [
            f"- `{x['path']}`: {x['stack']} ({x['manifest']})" + (f"; tests: `{' '.join(x['test'])}`" if x["test"] else "; no test command found")
            for x in s["stacks"]
        ]
    else:
        lines.append("- none recognized; name the test command yourself with `aidd init --test`")
    if s["monorepo"]:
        lines.append("- a monorepo: one `[[tests]]` entry per package, each with `when_changed`, and `[[owners.paths]]` for each package's approvers")
    if not s["tests"]:
        lines.append("- no test suite: every Spec brings a characterization test first (Characterization)")
    if s.get("checks"):
        lines.append(
            "- lint and type checks the repository already configures, proposed as `[[tests]]` below (`aidd init` writes only the test command): "
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
    lines += ["", "## Risk and ownership", ""]
    if s["risk_rules"]:
        lines += [
            f"- `{r['name']}`: {', '.join(f'`{p}`' for p in r['paths'])} ({', '.join(r['dimensions'])}), which the baseline rules do not cover"
            for r in s["risk_rules"]
        ]
    else:
        lines.append("- no sensitive area beyond what the baseline rules already cover")
    if s["budget_exclude_paths"]:
        lines.append("- generated or vendored code to keep out of the changed-line budget: " + ", ".join(f"`{p}`" for p in s["budget_exclude_paths"]))
    lines.append(
        f"- owners: {'`' + s['codeowners'] + '` exists, so `owners.codeowners = true` reuses it' if s['codeowners'] else 'no CODEOWNERS; name approvers per area in `[[owners.paths]]` if areas have different owners'}"
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
        "```toml",
        config_snippet(s).rstrip(),
        "```",
        "",
        "Nothing was written. Next: `aidd init` in a setup change (add `--team` for the delivery team; it uses the detected test "
        "command unless you pass `--test`), merge the rest of this config after review, and keep the gate advisory until its "
        "findings match your judgment.",
    ]
    return "\n".join(lines) + "\n"
