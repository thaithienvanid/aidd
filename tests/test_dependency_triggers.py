"""Dependency triggers: a risk rule also fires when a diff adds a dependency it names to a manifest.

Folder and file names miss an unconventional layout: payment code in `lib/money.ts`, sign-in in `web/session-helpers`.
The manifest does not: a change that adds `stripe` or `next-auth` routes as a payments or an auth change wherever the
code sits. Only an added dependency counts (a version bump is the standard-change check's), matching is by exact name,
case- and separator-insensitive, or by a prefix ending in `/`, and nothing reads the network.
"""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, make_repo

from aidd import config
from aidd.evals import suites
from aidd.setup import detection
from aidd.gate import dependency_updates
from aidd.gate import routing
from aidd.kernel import resources
from aidd.config import baseline

BARE_TEAM = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a", "@b"]\n'


def cfg(text: str = BARE_TEAM) -> config.Config:
    return config.load_text(text)


def added(file: str, *names: str) -> list[dict]:
    return [{"file": file, "name": n} for n in names]


def assess(paths: list[str], deps: list[dict], text: str = BARE_TEAM) -> routing.Assessment:
    return routing.assess_route(
        paths=paths,
        cfg=cfg(text),
        ctype="feat",
        risk={"dimensions": [], "reversible": True},
        confidence="high",
        task_count=1,
        changed_lines=10,
        dependencies=deps,
    )


class DeclaredNamesTests(unittest.TestCase):
    """Each ecosystem's manifest read as the names it declares; Python names are case-insensitive, so they read lowercased."""

    CASES = [
        ("package.json", json.dumps({"dependencies": {"next-auth": "^5"}, "devDependencies": {"@ai-sdk/openai": "1"}}), {"next-auth", "@ai-sdk/openai"}),
        ("web/requirements-dev.txt", "Flask-Login==0.6\nauthlib>=1 ; python_version>'3'\n# stripe\n-r base.txt\n", {"flask-login", "authlib"}),
        (
            "pyproject.toml",
            '[project]\ndependencies = ["alembic>=1.13", "stripe[async]"]\n[tool.poetry.dependencies]\nBabel = "*"\n',
            {"alembic", "stripe", "babel"},
        ),
        ("Pipfile", '[packages]\ndjango-allauth = "*"\n[dev-packages]\npytest = "*"\n', {"django-allauth", "pytest"}),
        ("go.mod", "module x\n\nrequire (\n\tgithub.com/stripe/stripe-go/v82 v82.1.0\n)\n", {"github.com/stripe/stripe-go/v82"}),
        ("Cargo.toml", '[dependencies]\nsqlx = "0.8"\n', {"sqlx"}),
        (
            "pom.xml",
            "<project><dependencies><dependency><groupId>org.flywaydb</groupId><artifactId>flyway-core</artifactId></dependency></dependencies></project>",
            {"flyway-core", "org.flywaydb:flyway-core"},
        ),
        (
            "app/build.gradle.kts",
            'dependencies { implementation("org.springframework.boot:spring-boot-starter-security") }\n',
            {"spring-boot-starter-security"},
        ),
        (
            "Api.csproj",
            '<ItemGroup><PackageReference Include="Microsoft.AspNetCore.Identity.EntityFrameworkCore" Version="9.0.0" /></ItemGroup>',
            {"Microsoft.AspNetCore.Identity.EntityFrameworkCore"},
        ),
        ("Gemfile", "source 'https://rubygems.org'\ngem 'devise'\ngem \"omniauth\", '~> 2'\n", {"devise", "omniauth"}),
        ("composer.json", json.dumps({"require": {"laravel/cashier": "^15"}}), {"laravel/cashier"}),
        (
            "mysite/settings.py",
            "INSTALLED_APPS = [\n    'django.contrib.admin',\n    \"django.contrib.auth\",\n]\n",
            {"django.contrib.admin", "django.contrib.auth"},
        ),
    ]

    def test_each_manifest_names_its_dependencies(self):
        for path, text, want in self.CASES:
            self.assertTrue(dependency_updates.is_manifest(path), path)
            got = dependency_updates.declared_dependencies(path, text)
            self.assertLessEqual(want, got, path)

    def test_other_files_are_not_manifests(self):
        for path in ("src/app.ts", "README.md", "docs/settings.md", "lib/package.json.bak"):
            self.assertFalse(dependency_updates.is_manifest(path), path)

    def test_a_broken_manifest_declares_nothing_and_never_raises(self):
        self.assertEqual(dependency_updates.declared_dependencies("package.json", "{not json"), set())
        self.assertEqual(dependency_updates.declared_dependencies("pyproject.toml", "[[[ nope"), set())


class AddedDependencyTests(unittest.TestCase):
    def test_only_a_name_the_head_adds_counts(self):
        base = {"package.json": json.dumps({"dependencies": {"left-pad": "^1.3.0"}})}
        head = {"package.json": json.dumps({"dependencies": {"left-pad": "^1.3.1", "stripe": "^17"}}), "src/x.ts": "x"}
        got = dependency_updates.added_dependencies(["package.json", "src/x.ts"], base.get, head.get)
        self.assertEqual(got, added("package.json", "stripe"))

    def test_a_new_manifest_adds_every_name_and_a_removed_one_adds_none(self):
        head = {"svc/requirements.txt": "stripe\nrequests\n"}
        self.assertEqual(
            dependency_updates.added_dependencies(["svc/requirements.txt"], lambda p: None, head.get), added("svc/requirements.txt", "requests", "stripe")
        )
        self.assertEqual(dependency_updates.added_dependencies(["svc/requirements.txt"], head.get, lambda p: None), [])

    def test_matching_is_by_name_or_a_prefix_ignoring_case_and_separators(self):
        self.assertEqual(dependency_updates.match("Flask_Login", ["flask-login"]), "flask-login")
        self.assertEqual(dependency_updates.match("Adyen", ["adyen"]), "adyen")
        self.assertEqual(dependency_updates.match("@ai-sdk/openai", ["@ai-sdk/"]), "@ai-sdk/")
        self.assertEqual(dependency_updates.match("github.com/stripe/stripe-go/v82", ["github.com/stripe/stripe-go/"]), "github.com/stripe/stripe-go/")
        self.assertIsNone(dependency_updates.match("stripe-mock-helpers", ["stripe"]))
        self.assertIsNone(dependency_updates.match("left-pad", ["stripe", "@stripe/"]))


class RouteTests(unittest.TestCase):
    """The gate and its forecast (`aidd gate --paths`) raise the route for an added dependency a rule names."""

    def test_adding_a_payment_sdk_is_major_on_the_financial_dimension(self):
        a = assess(["web/package.json", "lib/money.ts"], added("web/package.json", "stripe"))
        self.assertEqual(a.required_route, "major")
        self.assertIn("financial", a.dimensions)
        self.assertEqual(a.pools, {"finance"})
        self.assertIn("rule baseline:payments matched dependency stripe added in web/package.json -> at least major", a.reasons)

    def test_adding_left_pad_stays_normal(self):
        a = assess(["web/package.json", "lib/pad.ts"], added("web/package.json", "left-pad"))
        self.assertEqual(a.required_route, "normal")
        self.assertEqual(a.dimensions, {"third_party"})

    def test_auth_and_migration_libraries_raise_their_dimensions(self):
        for file, name, dim in (
            ("package.json", "next-auth", "security"),
            ("Gemfile", "devise", "security"),
            ("settings.py", "django.contrib.auth", "security"),
            ("pom.xml", "spring-boot-starter-security", "security"),
            ("Api.csproj", "Microsoft.AspNetCore.Identity", "security"),
            ("package.json", "prisma", "data"),
            ("requirements.txt", "alembic", "data"),
            ("build.gradle", "flyway-core", "data"),
        ):
            a = assess([file], added(file, name))
            self.assertEqual(a.required_route, "major", name)
            self.assertIn(dim, a.dimensions, name)

    def test_an_excluded_manifest_and_a_disabled_rule_do_not_fire(self):
        self.assertNotEqual(assess(["vendor/x/package.json"], added("vendor/x/package.json", "stripe")).required_route, "major")
        text = BARE_TEAM.replace("\nowners:", "\ndisabled_rules: [baseline:payments]\nowners:")
        self.assertEqual(assess(["package.json"], added("package.json", "stripe"), text).required_route, "normal")

    def test_a_dependency_that_is_not_in_the_diff_never_counts(self):
        # The gate reads only what the adapter found in this diff's manifests; nothing else is looked up.
        self.assertEqual(assess(["lib/money.ts"], []).required_route, "minor")

    def test_a_config_rule_may_name_dependencies_only(self):
        text = BARE_TEAM.replace("\nowners:", "\nrisk_rules:\n  - name: tenancy\n    dependencies: [django-tenants]\n    dimensions: [privacy]\n\nowners:")
        a = assess(["requirements.txt"], added("requirements.txt", "django-tenants"), text)
        self.assertEqual(a.required_route, "major")
        self.assertIn("privacy", a.dimensions)
        with self.assertRaises(config.ConfigError):
            cfg(BARE_TEAM.replace("\nowners:", "\nrisk_rules:\n  - name: empty\n    dimensions: [privacy]\n\nowners:"))

    def test_every_baseline_dependency_rule_raises_to_major(self):
        named = {r["name"]: r for r in baseline.baseline_data()["risk_rules"] if r.get("dependencies")}
        self.assertEqual(set(named), {"baseline:auth", "baseline:personal-data", "baseline:payments", "baseline:migrations"})
        for name, r in named.items():
            self.assertEqual(r["route"], "major", name)
            for dep in r["dependencies"]:
                if not dep.endswith("/"):
                    self.assertEqual(assess(["package.json"], added("package.json", dep)).required_route, "major", (name, dep))

    def test_the_context_schema_takes_the_added_dependencies(self):
        ctx = json.loads((ROOT / "examples" / "20-dependency-raises-route" / "context.json").read_text(encoding="utf-8"))
        self.assertEqual(ctx["dependencies_added"], added("web/package.json", "stripe"))
        sub = resources.load_json("context.schema.json")["properties"]["dependencies_added"]
        self.assertEqual(sub["items"]["required"], ["file", "name"])


class ScenarioTests(unittest.TestCase):
    def test_routing_scenarios_hold_an_added_dependency_to_the_gate(self):
        sc = {"paths": ["web/package.json", "lib/money.ts"], "dependencies": ["web/package.json:stripe"], "lines": 30, "type": "feat"}
        self.assertEqual(suites.gate_route(sc), "major")
        self.assertEqual(suites.gate_route({**sc, "dependencies": ["web/package.json:left-pad"]}), "normal")


class BranchAssessTests(unittest.TestCase):
    """The forecast reads the branch's manifests at the merge-base and in the working tree."""

    def test_the_branch_route_names_the_dependency_and_its_pack(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), branch=None)
            (root / "web").mkdir()
            (root / "web" / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "^1.3.0"}}), encoding="utf-8")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "web")
            git(root, "checkout", "-qb", "feat")
            (root / "web" / "package.json").write_text(json.dumps({"dependencies": {"left-pad": "^1.3.0", "stripe": "^17", "openai": "^5"}}), encoding="utf-8")
            out = routing.assess_diff(root)
            assert out is not None
            self.assertEqual(out["route"], "major")
            self.assertIn("rule baseline:payments matched dependency stripe added in web/package.json -> at least major", out["reasons"])
            self.assertEqual(
                out["packs"],
                [
                    {"pack": "ai-features", "dependency": "openai", "file": "web/package.json"},
                    {"pack": "payments-and-finance", "dependency": "stripe", "file": "web/package.json"},
                ],
            )


class DetectTests(unittest.TestCase):
    """`aidd init --dry-run` names the dependency rules a repository's manifests already call for."""

    def test_a_declared_auth_library_is_reported_with_its_rule(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "web").mkdir()
            (root / "web" / "package.json").write_text(json.dumps({"dependencies": {"next-auth": "^5", "i18next": "^25"}}), encoding="utf-8")
            found = detection.detect(root)
            self.assertIn("internationalization", found["packs"])
            # An auth library holds personal data too: baseline:personal-data watches it beside baseline:auth.
            self.assertEqual(
                found["dependency_rules"],
                [
                    {"rule": "baseline:auth", "dependencies": ["next-auth"], "manifests": ["web/package.json"]},
                    {"rule": "baseline:personal-data", "dependencies": ["next-auth"], "manifests": ["web/package.json"]},
                ],
            )
            text = detection.detection_markdown(found)
            self.assertIn("`web/package.json` declares next-auth, which `baseline:auth` watches", text)


if __name__ == "__main__":
    unittest.main()
