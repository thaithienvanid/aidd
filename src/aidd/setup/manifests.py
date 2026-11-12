"""What a repository's files declare, read with no network for `aidd init`'s detection: the dependencies each manifest
names (and the domain packs they call for), and the lines that look like they hold a secret."""

from __future__ import annotations

import json
import re
import tomllib

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


# Declared dependency names, for the domain packs `aidd init`
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
