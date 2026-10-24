"""Dependency updates read from a diff's manifests and lockfiles, for standard changes (`standard_changes[].update_types`).

Pragmatic, not a package manager: each supported file is read as a map of dependency name to version at the base and at
the head, and every version that changed is classified by its numbers as a patch, minor, or major update. Anything it
cannot classify is `unknown`, which the gate treats as major: an added or removed dependency, a downgrade, a version
without numbers, and a changed file whose versions it cannot read (a lockfile it does not parse, or one whose only change
is a checksum or a source).
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Callable

from aidd import config

UPDATE_TYPES = ("patch", "minor", "major")
_NUMBERS = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _versions_package_json(text: str) -> dict[str, str]:
    data = json.loads(text)
    out: dict[str, str] = {}
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        for name, spec in (data.get(key) or {}).items():
            if isinstance(spec, str):
                out[f"{key}:{name}"] = spec
    return out


def _versions_package_lock(text: str) -> dict[str, str]:
    data = json.loads(text)
    out: dict[str, str] = {}
    for path, entry in (data.get("packages") or {}).items():
        if path and isinstance(entry, dict) and isinstance(entry.get("version"), str):
            out[path] = entry["version"]

    def walk(deps: dict, prefix: str) -> None:
        for name, entry in (deps or {}).items():
            if isinstance(entry, dict):
                if isinstance(entry.get("version"), str):
                    out.setdefault(f"{prefix}node_modules/{name}", entry["version"])
                walk(entry.get("dependencies") or {}, f"{prefix}node_modules/{name}/")

    walk(data.get("dependencies") or {}, "")
    return out


def _versions_pipfile_lock(text: str) -> dict[str, str]:
    data = json.loads(text)
    return {
        f"{group}:{name}": str(e.get("version", "")) for group in ("default", "develop") for name, e in (data.get(group) or {}).items() if isinstance(e, dict)
    }


_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(===|==|~=|>=|<=|!=|>|<)?\s*([^;#\s,]*)")


def _versions_requirements(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if not s or s.startswith(("-", "--")):
            continue
        m = _REQUIREMENT.match(s)
        if m:
            out[m.group(1).lower().replace("_", "-")] = m.group(3) or ""
    return out


def _versions_toml_packages(text: str) -> dict[str, str]:
    """uv.lock, poetry.lock, Cargo.lock: `[[package]]` tables with a name and a version."""
    data = tomllib.loads(text)
    return {f"{p.get('name')}@{p.get('source', '') if isinstance(p.get('source'), str) else ''}": str(p.get("version", "")) for p in data.get("package") or []}


def _versions_cargo_toml(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    out: dict[str, str] = {}
    tables = [(k, data.get(k)) for k in ("dependencies", "dev-dependencies", "build-dependencies")]
    tables.append(("workspace.dependencies", (data.get("workspace") or {}).get("dependencies")))
    for key, deps in tables:
        for name, spec in (deps or {}).items():
            version = spec if isinstance(spec, str) else spec.get("version") if isinstance(spec, dict) else None
            out[f"{key}:{name}"] = str(version or "")
    return out


_GO_REQUIRE = re.compile(r"^\s*(?:require\s+)?([^\s()]+)\s+(v[^\s]+)(?:\s*//.*)?$")


def _versions_go_mod(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    block = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("require ("):
            block = True
            continue
        if block and s == ")":
            block = False
            continue
        if block or s.startswith("require "):
            m = _GO_REQUIRE.match(s)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def _unparsed(text: str) -> dict[str, str]:
    """A lockfile read as its bytes only: any change to it is unknown."""
    return {}


PARSERS: dict[str, Callable[[str], dict[str, str]]] = {
    "package.json": _versions_package_json,
    "package-lock.json": _versions_package_lock,
    "npm-shrinkwrap.json": _versions_package_lock,
    "Pipfile.lock": _versions_pipfile_lock,
    "uv.lock": _versions_toml_packages,
    "poetry.lock": _versions_toml_packages,
    "Cargo.lock": _versions_toml_packages,
    "Cargo.toml": _versions_cargo_toml,
    "go.mod": _versions_go_mod,
    "go.sum": _unparsed,
    "yarn.lock": _unparsed,
    "pnpm-lock.yaml": _unparsed,
    "Gemfile.lock": _unparsed,
    "composer.lock": _unparsed,
}


def parser_for(path: str) -> Callable[[str], dict[str, str]] | None:
    name = path.rsplit("/", 1)[-1]
    if name in PARSERS:
        return PARSERS[name]
    if (name.startswith("requirements") and name.endswith((".txt", ".in"))) or (path.startswith(".github/requirements/") and name.endswith(".txt")):
        return _versions_requirements
    return None


def classify(old: str | None, new: str | None) -> str:
    """patch, minor, or major by the first number that grew; unknown when either has no numbers, or nothing grew."""
    a = _NUMBERS.search((old or "").lstrip("^~=<>! v"))
    b = _NUMBERS.search((new or "").lstrip("^~=<>! v"))
    if not a or not b:
        return "unknown"
    x = [int(g or 0) for g in a.groups()]
    y = [int(g or 0) for g in b.groups()]
    for i, kind in enumerate(("major", "minor", "patch")):
        if y[i] > x[i]:
            return kind
        if y[i] < x[i]:
            return "unknown"  # a downgrade is no routine update
    return "unknown"


def updates(paths: list[str], read_base: Callable[[str], str | None], read_head: Callable[[str], str | None]) -> list[dict]:
    """Every dependency whose version a changed manifest or lockfile moves: {file, name, from, to, update_type}."""
    out: list[dict] = []
    for path in paths:
        parse = parser_for(path)
        if parse is None:
            continue
        old_text, new_text = read_base(path), read_head(path)
        try:
            old = parse(old_text) if old_text is not None else {}
            new = parse(new_text) if new_text is not None else {}
        except (ValueError, tomllib.TOMLDecodeError, AttributeError, TypeError):
            out.append({"file": path, "name": None, "from": None, "to": None, "update_type": "unknown"})
            continue
        found = [
            {"file": path, "name": name, "from": old.get(name), "to": new.get(name), "update_type": classify(old.get(name), new.get(name))}
            for name in sorted(set(old) | set(new))
            if old.get(name) != new.get(name)
        ]
        if not found and old_text != new_text:
            found = [{"file": path, "name": None, "from": None, "to": None, "update_type": "unknown"}]
        out += found
    return out


_DEPENDABOT_TYPE = re.compile(r"^\s*update-type:\s*version-update:semver-(patch|minor|major)\s*$", re.M)
_DEPENDABOT_NAME = re.compile(r"^\s*-\s*dependency-name:\s*\S", re.M)


def dependabot_types(texts: list[str]) -> list[str]:
    """The update types Dependabot's `updated-dependencies` metadata declares, in a PR body or commit message: one per
    dependency, and `unknown` for a dependency it names without an update type."""
    out: list[str] = []
    for text in texts:
        if "updated-dependencies:" not in text:
            continue
        kinds = _DEPENDABOT_TYPE.findall(text)
        out += kinds + ["unknown"] * max(0, len(_DEPENDABOT_NAME.findall(text)) - len(kinds))
    return out


# Declared dependency names, for the risk rules that name a dependency (`dependencies`) and the domain packs `aidd init`
# proposes: what each manifest declares, read the way its ecosystem writes it, with no versions and no network. A Django
# settings module's `INSTALLED_APPS` counts too: `django.contrib.auth` is an app the settings add, not a package.
MANIFEST_NAMES = frozenset(
    {"package.json", "composer.json", "pyproject.toml", "Pipfile", "Cargo.toml", "go.mod", "Gemfile", "pubspec.yaml", "pom.xml", "mix.exs"}
    | {"build.gradle", "build.gradle.kts", "settings.py"}
)
_PEP508_NAME = re.compile(r"[\s\[<>=!~;@(]")
_INSTALLED_APPS = re.compile(r"^\s*INSTALLED_APPS\s*\+?=\s*[\[(](.*?)[\])]", re.M | re.S)


def is_manifest(path: str) -> bool:
    """Whether `path` is a file `declared` reads: a manifest, a requirements file, a .csproj, or a Django settings module."""
    parts = path.split("/")
    name = parts[-1]
    if name in MANIFEST_NAMES or name.endswith(".csproj"):
        return True
    if name.startswith("requirements") and name.endswith((".txt", ".in")):
        return True
    return len(parts) > 1 and parts[-2] == "settings" and name.endswith(".py")


def _pep508(reqs: list) -> set[str]:
    """Python requirement names, lowercased: PyPI names are case-insensitive."""
    return {_PEP508_NAME.split(r.strip(), maxsplit=1)[0].lower() for r in reqs if isinstance(r, str) and r.strip()}


def declared_dependencies(path: str, text: str) -> set[str]:
    """The dependency names `path` declares; empty for a file it cannot read, never an error."""
    name = path.rsplit("/", 1)[-1]
    out: set[str] = set()
    try:
        if name in ("package.json", "composer.json"):
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies", "require", "require-dev"):
                out |= set((data.get(key) or {}).keys())
        elif name in ("pyproject.toml", "Cargo.toml", "Pipfile"):
            data = tomllib.loads(text)
            proj = data.get("project") or {}
            reqs = list(proj.get("dependencies", []))
            for group in list((proj.get("optional-dependencies") or {}).values()) + list((data.get("dependency-groups") or {}).values()):
                reqs += [r for r in group if isinstance(r, str)]
            out |= _pep508(reqs)
            out |= {k.lower() for k in ((data.get("tool") or {}).get("poetry") or {}).get("dependencies") or {}}
            for table in ("dependencies", "dev-dependencies", "build-dependencies"):  # Cargo's
                out |= set((data.get(table) or {}).keys())
            for table in ("packages", "dev-packages"):  # Pipfile's
                out |= {k.lower() for k in data.get(table) or {}}
            out |= set(((data.get("workspace") or {}).get("dependencies") or {}).keys())
        elif name.startswith("requirements") and name.endswith((".txt", ".in")):
            out |= _pep508([ln.split("#", 1)[0] for ln in text.splitlines() if not ln.strip().startswith(("#", "-"))])
        elif name == "go.mod":
            out |= set(_versions_go_mod(text))
        elif name == "Gemfile":
            out |= set(re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"]", text, re.M))
        elif name == "pubspec.yaml":
            out |= set(re.findall(r"^  ([a-z_][a-z0-9_]*):", text, re.M))
        elif name == "pom.xml":
            for group, artifact in re.findall(r"<groupId>([^<]+)</groupId>\s*<artifactId>([^<]+)</artifactId>", text):
                out.add(f"{group.strip()}:{artifact.strip()}")
            out |= {a.strip() for a in re.findall(r"<artifactId>([^<]+)</artifactId>", text)}
        elif name in ("build.gradle", "build.gradle.kts"):
            for group, artifact in re.findall(r"['\"]([\w.-]+):([\w.-]+)(?::[^'\"]*)?['\"]", text):
                out |= {artifact, f"{group}:{artifact}"}
            out |= set(re.findall(r"id\s*\(?\s*['\"]([\w.-]+)['\"]", text))
        elif name.endswith(".csproj"):
            out |= set(re.findall(r'PackageReference\s+Include="([^"]+)"', text))
        elif name == "mix.exs":
            out |= set(re.findall(r"\{:([a-z_]+),", text))
        elif name.endswith(".py") and is_manifest(path):
            for block in _INSTALLED_APPS.findall(text):
                out |= set(re.findall(r"['\"]([\w.]+)['\"]", block))
    except (ValueError, TypeError, AttributeError):  # tomllib.TOMLDecodeError is a ValueError
        return set()
    return {d for d in out if isinstance(d, str) and d}


def added_dependencies(paths: list[str], read_base: Callable[[str], str | None], read_head: Callable[[str], str | None]) -> list[dict]:
    """Every dependency a changed manifest declares at the head and not at the base: {file, name}, sorted. A new
    manifest adds every name it declares; a removed one adds none; a version change adds nothing."""
    out: list[dict] = []
    for path in sorted(set(paths)):
        if not is_manifest(path):
            continue
        head = read_head(path)
        if head is None:
            continue
        base = read_base(path)
        before = declared_dependencies(path, base) if base is not None else set()
        out += [{"file": path, "name": n} for n in sorted(declared_dependencies(path, head) - before)]
    return out


def _norm(name: str) -> str:
    """A name compared across ecosystems: case-insensitive, with `-`, `_`, and `.` alike, as PEP 503 compares them."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def match(name: str, patterns: list[str]) -> str | None:
    """The first pattern `name` matches: the same name, or, for a pattern ending in `/`, a name it starts."""
    n = _norm(name)
    for p in patterns:
        q = _norm(p)
        if n.startswith(q) if p.endswith("/") else n == q:
            return p
    return None


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
    "desktop-apps": tuple("electron electron-builder @electron-forge/cli @tauri-apps/api @tauri-apps/cli tauri".split()),
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
    "extensions-and-marketplace-apps": tuple(
        (
            "@types/vscode @vscode/vsce webextension-polyfill wxt plasmo @types/chrome @types/firefox-webext-browser @shopify/shopify-app-remix "
            "@shopify/shopify-app-react-router @shopify/shopify-api @slack/bolt slack-bolt @forge/api @forge/bridge @microsoft/teams-js"
        ).split()
    ),
    "cloud-and-infrastructure": tuple("aws-cdk-lib @pulumi/pulumi pulumi cdktf @cdktf/provider-aws sst wrangler".split()),
    "embedded-automotive-industrial": tuple("embedded-hal embassy-executor cortex-m esp-idf-svc zephyr micropython".split()),
}


def dependency_packs_for(deps: set[str]) -> list[str]:
    return sorted(pack for pack, hints in PACK_HINTS.items() if any(match(d, list(hints)) for d in deps))


def dependency_packs(found: list[dict]) -> list[dict]:
    """The domain pack each added dependency calls for ({pack, dependency, file}), for the forecast on a branch."""
    out = [{"pack": pack, "dependency": d["name"], "file": d["file"]} for d in found for pack, hints in PACK_HINTS.items() if match(d["name"], list(hints))]
    return sorted(out, key=lambda x: (x["pack"], x["dependency"], x["file"]))


def dependency_rules(manifests: dict[str, set[str]]) -> list[dict]:
    """The baseline rules that name a dependency a manifest already declares ({rule, dependencies, manifests}): the
    rule fires when a change adds one, so code that already uses it may sit outside the rule's paths."""
    out = []
    for r in config.baseline_data()["risk_rules"]:
        hits = {rel: sorted(n for n in names if match(n, r.get("dependencies", []))) for rel, names in sorted(manifests.items())}
        hits = {rel: names for rel, names in hits.items() if names}
        if hits:
            out.append({"rule": r["name"], "dependencies": sorted({n for names in hits.values() for n in names}), "manifests": sorted(hits)})
    return out
