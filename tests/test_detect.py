"""What `aidd init` finds in an existing repository, and the config it proposes to fit aidd and the team to it."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config, depdiff, detect


def tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


class DetectTests(unittest.TestCase):
    def run_on(self, files):
        with tempfile.TemporaryDirectory() as d:
            return detect.detect(tree(Path(d), files))

    def test_a_single_service(self):
        found = self.run_on(
            {
                "package.json": json.dumps({"scripts": {"test": "vitest"}, "dependencies": {"react": "^19", "stripe": "^17"}}),
                "pnpm-lock.yaml": "",
                "src/app.tsx": "",
                "src/app.test.tsx": "",
                "src/ledger/entries.ts": "",
                "src/generated/api.ts": "",
                ".github/CODEOWNERS": "* @org/web\n",
                ".github/workflows/ci.yml": "name: ci\n",
                "CLAUDE.md": "# notes\n",
            }
        )
        self.assertEqual([t["test"] for t in found["tests"]], [["pnpm", "test"]])
        self.assertEqual(found["packs"], ["payments-and-finance", "web-front-end"])
        # payments/ and billing/ are baseline:payments, so detect proposes a rule only for a money folder the baseline misses.
        self.assertEqual(found["risk_rules"], [{"name": "payments", "paths": ["src/ledger/**"], "dimensions": ["financial"]}])
        self.assertEqual(found["budget_exclude_paths"], ["src/generated/**"])
        self.assertEqual((found["codeowners"], found["ci"], found["agent_files"]), (".github/CODEOWNERS", [".github/workflows/ci.yml"], ["CLAUDE.md"]))
        self.assertFalse(found["monorepo"])
        self.assertEqual(found["untested"], [])

    def test_a_symlink_out_of_the_repository_is_not_followed(self):
        with tempfile.TemporaryDirectory() as outside, tempfile.TemporaryDirectory() as d:
            tree(Path(outside), {"package.json": json.dumps({"scripts": {"test": "jest"}}), "billing/charge.ts": ""})
            root = tree(Path(d), {"README.md": "# app\n"})
            try:
                (root / "vendor-link").symlink_to(outside, target_is_directory=True)
                (root / "package.json").symlink_to(Path(outside) / "package.json")
            except OSError:
                self.skipTest("symlinks are not available here")
            files = detect._walk(root)
            self.assertEqual([p.name for p in files], ["README.md"])
            found = detect.detect(root)
            self.assertEqual((found["tests"], found["risk_rules"]), ([], []))

    def test_the_baseline_rules_are_not_proposed_again(self):
        found = self.run_on({"pyproject.toml": "[tool.pytest.ini_options]\n", "app/auth/login.py": "", "app/migrations/0001.py": "", "app/models/user.py": ""})
        self.assertEqual(found["risk_rules"], [])  # auth and migrations are baseline rules; a models folder is not sensitive
        self.assertEqual(found["untested"], ["app"])  # no tests beside the code: the first change needs a characterization test

    def test_a_monorepo_gets_one_suite_per_package(self):
        found = self.run_on(
            {
                "go.work": "go 1.23\n",
                "services/api/go.mod": "module api\n",
                "services/api/main_test.go": "",
                "web/package.json": json.dumps({"scripts": {"test": "jest"}}),
            }
        )
        self.assertTrue(found["monorepo"])
        snippet = detect.config_snippet(found)
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n' + snippet)
        suites = {t["name"]: (t["command"], t.get("when_changed")) for t in cfg.get("tests")}
        self.assertEqual(suites["services-api"], (["go", "test", "./services/api/..."], ["services/api/**"]))
        self.assertEqual(suites["web"], (["npm", "--prefix", "web", "test"], ["web/**"]))

    def test_each_ecosystem_runs_its_own_current_tools(self):
        found = self.run_on(
            {
                "py/pyproject.toml": '[project]\nname = "x"\ndependencies = ["fastapi>=0.115", "langgraph", "pydantic-ai[openai]"]\n[dependency-groups]\ndev = ["pytest"]\n',
                "py/uv.lock": "",
                "js/package.json": json.dumps({"scripts": {"test": "bun test"}, "dependencies": {"hono": "^4", "@ai-sdk/anthropic": "^2"}}),
                "js/bun.lock": "",
                "go/go.mod": "module x\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.10.0\n\tgithub.com/stripe/stripe-go/v82 v82.1.0\n)\n",
            }
        )
        by = {s["path"]: s for s in found["stacks"]}
        self.assertEqual(by["py"]["test"], ["uv", "run", "--directory", "py", "pytest"])
        self.assertEqual(by["js"]["test"], ["bun", "run", "--cwd", "js", "test"])
        self.assertEqual(by["py"]["packs"], ["ai-agents-and-tools", "apis-and-services"])
        self.assertEqual(by["js"]["packs"], ["ai-features", "apis-and-services"])
        self.assertEqual(by["go"]["packs"], ["apis-and-services", "payments-and-finance"])

    def test_a_dependency_name_matches_exactly_not_by_substring(self):
        self.assertEqual(detect.packs_for({"reactive-streams", "aiohttp", "stripe-mock-server"}), [])
        self.assertEqual(detect.packs_for({"@langchain/langgraph"}), ["ai-agents-and-tools"])

    def test_an_empty_repository_proposes_nothing_risky(self):
        found = self.run_on({"README.md": "# hi\n"})
        self.assertEqual((found["stacks"], found["risk_rules"], found["tests"]), ([], [], []))
        self.assertIn("no test suite", detect.markdown(found))


class ManifestTests(unittest.TestCase):
    """Each ecosystem's manifest: the stack, the test command run from the repository root, and the pack hints."""

    def stack(self, files, manifest):
        with tempfile.TemporaryDirectory() as d:
            root = tree(Path(d), files)
            return detect._stack(root / manifest, root)

    def test_every_manifest_names_its_test_command(self):
        for files, manifest, stack, command in (
            ({"pyproject.toml": "[tool.pytest.ini_options]\n", "poetry.lock": ""}, "pyproject.toml", "Python", ["poetry", "run", "pytest"]),
            (
                {"py/pyproject.toml": "[tool.pytest.ini_options]\n", "py/poetry.lock": ""},
                "py/pyproject.toml",
                "Python",
                ["poetry", "-C", "py", "run", "pytest"],
            ),
            ({"requirements.txt": "flask\n", "tests/test_a.py": ""}, "requirements.txt", "Python", ["python3", "-m", "pytest"]),
            ({"Cargo.toml": '[package]\nname = "x"\n'}, "Cargo.toml", "Rust", ["cargo", "test"]),
            ({"crates/a/Cargo.toml": '[package]\nname = "a"\n'}, "crates/a/Cargo.toml", "Rust", ["cargo", "test", "--manifest-path", "crates/a/Cargo.toml"]),
            ({"pom.xml": "<project/>", "mvnw": ""}, "pom.xml", "Java (Maven)", ["./mvnw", "-q", "test"]),
            ({"svc/pom.xml": "<project/>"}, "svc/pom.xml", "Java (Maven)", ["mvn", "-q", "test", "-f", "svc/pom.xml"]),
            ({"svc/pom.xml": "<project/>", "svc/mvnw": ""}, "svc/pom.xml", "Java (Maven)", ["./svc/mvnw", "-q", "test", "-f", "svc/pom.xml"]),
            ({"build.gradle.kts": "", "gradlew": ""}, "build.gradle.kts", "JVM (Gradle)", ["./gradlew", "test"]),
            ({"app/build.gradle": "", "app/gradlew": ""}, "app/build.gradle", "JVM (Gradle)", ["./app/gradlew", "test", "-p", "app"]),
            ({"build.gradle": ""}, "build.gradle", "JVM (Gradle)", ["gradle", "test"]),
            ({"Gemfile": "gem 'rails'\n", "spec/a_spec.rb": ""}, "Gemfile", "Ruby", ["bundle", "exec", "rspec"]),
            ({"Gemfile": "gem 'sinatra'\n"}, "Gemfile", "Ruby", ["bundle", "exec", "rake", "test"]),
            ({"App.sln": ""}, "App.sln", ".NET", ["dotnet", "test", "App.sln"]),
            ({"src/Api/Api.csproj": "<Project/>"}, "src/Api/Api.csproj", ".NET", ["dotnet", "test", "src/Api/Api.csproj"]),
            ({"pubspec.yaml": "name: app\n"}, "pubspec.yaml", "Dart/Flutter", ["flutter", "test"]),
            ({"composer.json": json.dumps({"scripts": {"test": "phpunit"}})}, "composer.json", "PHP", ["composer", "test"]),
            ({"composer.json": json.dumps({"require": {"php": ">=8.3"}})}, "composer.json", "PHP", None),  # no test script: nothing to run
            ({"deno.json": "{}"}, "deno.json", "TypeScript (Deno)", ["deno", "test"]),
            ({"Package.swift": "// swift-tools-version:6.0\n"}, "Package.swift", "Swift", ["swift", "test"]),
            ({"pkg/Package.swift": ""}, "pkg/Package.swift", "Swift", ["swift", "test", "--package-path", "pkg"]),
            ({"mix.exs": "defmodule X.MixProject do\nend\n"}, "mix.exs", "Elixir", ["mix", "test"]),
            ({"umbrella/mix.exs": ""}, "umbrella/mix.exs", "Elixir", None),  # mix runs from its own project folder only
            ({"build.sbt": ""}, "build.sbt", "Scala (sbt)", ["sbt", "test"]),
            ({"Makefile": "build:\n\tcc x.c\ntest:\n\t./run-tests\n"}, "Makefile", "Make", ["make", "test"]),
        ):
            with self.subTest(manifest=manifest, files=sorted(files)):
                found = self.stack(files, manifest)
                self.assertEqual((found["stack"], found["test"]), (stack, command))
        self.assertIsNone(self.stack({"Makefile": "build:\n\tcc x.c\n"}, "Makefile"))  # a Makefile without a test target is no stack
        self.assertIsNone(self.stack({"Cargo.toml": "[dependencies]\n"}, "Cargo.toml"))  # neither a package nor a workspace

    def test_each_manifest_format_yields_its_dependencies_and_packs(self):
        for manifest, text, deps, packs in (
            (
                "package.json",
                json.dumps({"dependencies": {"react": "19"}, "devDependencies": {"@ai-sdk/openai": "2"}}),
                {"react", "@ai-sdk/openai"},
                ["ai-features", "web-front-end"],
            ),
            (
                "composer.json",
                json.dumps({"require": {"laravel/framework": "^11"}, "require-dev": {"phpunit/phpunit": "^11"}}),
                {"laravel/framework", "phpunit/phpunit"},
                ["apis-and-services"],
            ),
            ("pyproject.toml", '[tool.poetry.dependencies]\npython = "^3.12"\nDjango = "^5"\n', {"python", "django"}, ["apis-and-services"]),
            (
                "pyproject.toml",
                '[project]\ndependencies = ["pandas>=2", "stripe[async] ; python_version>\'3\'"]\n',
                {"pandas", "stripe"},
                ["data-and-analytics", "payments-and-finance"],
            ),
            ("Cargo.toml", '[package]\nname = "x"\n[dependencies]\naxum = "0.8"\n[dev-dependencies]\ntokio = "1"\n', {"axum", "tokio"}, ["apis-and-services"]),
            ("Cargo.toml", '[workspace]\n[workspace.dependencies]\nembedded-hal = "1"\n', {"embedded-hal"}, ["embedded-automotive-industrial"]),
            ("requirements.txt", "# pinned\nfastapi==0.115\n-r base.txt\nTorch>=2\n", {"fastapi", "torch"}, ["ai-features", "apis-and-services"]),
            ("go.mod", "module x\n\nrequire github.com/labstack/echo/v4 v4.12.0\n", {"github.com/labstack/echo/v4"}, ["apis-and-services"]),
            (
                "Gemfile",
                "source 'https://rubygems.org'\ngem 'rails', '~> 8.0'\ngem \"rails-i18n\"\n",
                {"rails", "rails-i18n"},
                ["apis-and-services", "internationalization"],
            ),
            ("pubspec.yaml", "name: app\ndependencies:\n  flutter:\n    sdk: flutter\n  intl: any\n", {"flutter", "intl"}, ["mobile-apps"]),
            (
                "pom.xml",
                "<project><dependency><artifactId>spring-boot-starter-web</artifactId></dependency></project>",
                {"spring-boot-starter-web"},
                ["apis-and-services"],
            ),
            (
                "build.gradle.kts",
                'plugins { id("com.android.application") }\ndependencies { implementation("com.stripe:stripe-java:28.0.0") }\n',
                {"com.android.application", "stripe-java", "com.stripe:stripe-java"},
                ["mobile-apps", "payments-and-finance"],
            ),
            (
                "Api.csproj",
                '<Project><ItemGroup><PackageReference Include="Stripe.net" Version="47" /></ItemGroup></Project>',
                {"Stripe.net"},
                ["payments-and-finance"],
            ),
            ("mix.exs", 'defp deps do\n  [{:phoenix, "~> 1.7"}, {:jason, "~> 1.4"}]\nend\n', {"phoenix", "jason"}, ["apis-and-services"]),
            ("package.json", "{ not json", set(), []),  # an unreadable manifest yields nothing rather than failing init
        ):
            with self.subTest(manifest=manifest, deps=sorted(deps)):
                found = depdiff.declared(manifest, text)
                self.assertLessEqual(deps, found)
                self.assertEqual(detect.packs_for(found), packs)


class InitTests(unittest.TestCase):
    def aidd(self, cwd, *args):
        env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
        return subprocess.run([sys.executable, "-m", "aidd", *args], cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8")

    def test_dry_run_writes_nothing_and_init_uses_the_detected_suite(self):
        with tempfile.TemporaryDirectory() as d:
            root = tree(Path(d), {"go.mod": "module x\n", "main_test.go": "", "internal/ledger/post.go": ""})
            subprocess.run(["git", "init", "-q", d], check=True)
            dry = self.aidd(d, "init", "--dry-run")
            self.assertEqual(dry.returncode, 0, dry.stderr)
            self.assertIn("`internal/ledger/**`", dry.stdout)
            self.assertFalse((root / ".aidd").exists())
            done = self.aidd(d, "init", "--approvers", "@lead", "--ci", "none", "--harness", "none")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("detected the test command: go test ./...", done.stdout)
            # The footer names what it found, and only that.
            # The sensitive areas it found are written as risk rules; the footer names only what is left to fit.
            self.assertIn("wrote the sensitive areas it found as [[risk_rules]]: payments (internal/ledger/**)", done.stdout)
            self.assertIn("It also found folders without tests internal:", done.stdout)
            self.assertNotIn("generated code", done.stdout)
            self.assertNotIn("owners", done.stdout.split("It also found", 1)[1].split("\n", 1)[0])
            cfg = config.load_text((root / ".aidd" / "config.toml").read_text(encoding="utf-8"))
            self.assertEqual(cfg.get("tests")[0]["command"], ["go", "test", "./..."])
            self.assertEqual([r["name"] for r in cfg.get("risk_rules")], ["payments"])
            # `go vet` is proposed by the dry run, never written: lint and type checks stay suggestions.
            self.assertIn('command = ["go", "vet", "./..."]', dry.stdout)
            self.assertEqual([t["name"] for t in cfg.get("tests")], ["unit"])

    def test_nothing_found_means_no_footer(self):
        with tempfile.TemporaryDirectory() as d:
            tree(Path(d), {"app/cart.py": "", "tests/test_cart.py": ""})
            subprocess.run(["git", "init", "-q", d], check=True)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "commit", "-qm", "scaffold"], check=True)
            done = self.aidd(d, "init", "--approvers", "@lead", "--ci", "none")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("It also found", done.stdout)
            self.assertEqual(detect.found_to_fit(detect.detect(Path(d))), [])


class VerificationRecipeTests(unittest.TestCase):
    """Lint and type-check commands `aidd init --dry-run` proposes: only for tools the repository already configures."""

    def checks(self, files):
        with tempfile.TemporaryDirectory() as d:
            return [(c["path"], c["tool"], c["command"]) for c in detect.detect(tree(Path(d), files))["checks"]]

    def test_each_stack_proposes_only_the_checks_it_configures(self):
        pkg = lambda **scripts: json.dumps({"scripts": {"test": "vitest", **scripts}})  # noqa: E731
        for label, files, expected in (
            ("python, nothing configured", {"pyproject.toml": "[tool.pytest.ini_options]\n"}, []),
            ("python ruff in pyproject", {"pyproject.toml": "[tool.ruff]\nline-length = 100\n"}, [(".", "ruff", ["ruff", "check"])]),
            (
                "python ruff.toml with uv",
                {"pyproject.toml": "[project]\nname='x'\n", "uv.lock": "", "ruff.toml": ""},
                [(".", "ruff", ["uv", "run", "ruff", "check"])],
            ),
            ("python .ruff.toml with poetry", {"pyproject.toml": "", "poetry.lock": "", ".ruff.toml": ""}, [(".", "ruff", ["poetry", "run", "ruff", "check"])]),
            ("python mypy.ini", {"requirements.txt": "flask\n", "mypy.ini": "[mypy]\nstrict = True\n"}, [(".", "mypy", ["mypy", "."])]),
            ("python mypy with files", {"pyproject.toml": '[tool.mypy]\nfiles = ["src"]\n'}, [(".", "mypy", ["mypy"])]),
            ("python mypy in setup.cfg", {"setup.cfg": "[metadata]\nname = x\n\n[mypy]\nstrict = True\n"}, [(".", "mypy", ["mypy", "."])]),
            (
                "python package folder",
                {"svc/pyproject.toml": "[tool.ruff]\n[tool.mypy]\n"},
                [("svc", "ruff", ["ruff", "check", "svc"]), ("svc", "mypy", ["mypy", "svc"])],
            ),
            (
                "python package with uv",
                {"svc/pyproject.toml": "[tool.ruff]\n", "svc/uv.lock": ""},
                [("svc", "ruff", ["uv", "run", "--directory", "svc", "ruff", "check"])],
            ),
            ("python mypy with uv", {"pyproject.toml": "[tool.mypy]\n", "uv.lock": ""}, [(".", "mypy", ["uv", "run", "mypy", "."])]),
            (
                "python mypy with files and poetry",
                {"pyproject.toml": '[tool.mypy]\nfiles = ["src"]\n', "poetry.lock": ""},
                [(".", "mypy", ["poetry", "run", "mypy"])],
            ),
            (
                "python package with uv and mypy",
                {"svc/pyproject.toml": "[tool.mypy]\n", "svc/uv.lock": ""},
                [("svc", "mypy", ["uv", "run", "--directory", "svc", "mypy", "."])],
            ),
            (
                "python package with poetry and mypy",
                {"svc/pyproject.toml": "[tool.mypy]\n", "svc/poetry.lock": ""},
                [("svc", "mypy", ["poetry", "-C", "svc", "run", "mypy", "."])],
            ),
            (
                "python package with uv and mypy files",
                {"svc/mypy.ini": "[mypy]\nfiles = app\n", "svc/requirements.txt": "", "svc/uv.lock": ""},
                [("svc", "mypy", ["uv", "run", "--directory", "svc", "mypy"])],
            ),
            ("js, nothing configured", {"package.json": pkg()}, []),
            ("js eslint flat config", {"package.json": pkg(), "eslint.config.js": ""}, [(".", "eslint", ["npm", "exec", "--", "eslint", "."])]),
            (
                "js eslint lint script with pnpm",
                {"package.json": pkg(lint="eslint ."), "pnpm-lock.yaml": "", ".eslintrc.json": "{}"},
                [(".", "eslint", ["pnpm", "run", "lint"])],
            ),
            (
                "js eslintConfig in package.json",
                {"package.json": json.dumps({"eslintConfig": {}}), "yarn.lock": ""},
                [(".", "eslint", ["yarn", "eslint", "."])],
            ),
            ("ts tsc with bun", {"package.json": pkg(), "bun.lock": "", "tsconfig.json": "{}"}, [(".", "tsc", ["bunx", "tsc", "--noEmit"])]),
            (
                "ts package folder with bun",
                {"web/package.json": pkg(), "web/bun.lock": "", "web/eslint.config.js": "", "web/tsconfig.json": "{}"},
                [("web", "eslint", ["bun", "run", "--cwd", "web", "eslint", "."]), ("web", "tsc", ["bun", "run", "--cwd", "web", "tsc", "--noEmit"])],
            ),
            (
                "ts package folder with bun scripts",
                {"web/package.json": pkg(lint="eslint .", typecheck="tsc"), "web/bun.lockb": "", "web/eslint.config.js": "", "web/tsconfig.json": "{}"},
                [("web", "eslint", ["bun", "run", "--cwd", "web", "lint"]), ("web", "tsc", ["bun", "run", "--cwd", "web", "typecheck"])],
            ),
            ("ts typecheck script", {"package.json": pkg(typecheck="tsc -b"), "tsconfig.json": "{}"}, [(".", "tsc", ["npm", "run", "typecheck"])]),
            (
                "ts package folder",
                {"web/package.json": pkg(lint="eslint ."), "web/pnpm-lock.yaml": "", "web/eslint.config.mjs": "", "web/tsconfig.json": "{}"},
                [("web", "eslint", ["pnpm", "--dir", "web", "run", "lint"]), ("web", "tsc", ["pnpm", "--dir", "web", "exec", "tsc", "--noEmit"])],
            ),
            ("go", {"go.mod": "module x\n"}, [(".", "go-vet", ["go", "vet", "./..."])]),
            ("go package folder", {"api/go.mod": "module x\n"}, [("api", "go-vet", ["go", "vet", "./api/..."])]),
            ("rust", {"Cargo.toml": '[package]\nname = "x"\n'}, [(".", "clippy", ["cargo", "clippy", "--", "-D", "warnings"])]),
            (
                "rust crate folder",
                {"crates/a/Cargo.toml": '[package]\nname = "a"\n'},
                [("crates/a", "clippy", ["cargo", "clippy", "--manifest-path", "crates/a/Cargo.toml", "--", "-D", "warnings"])],
            ),
            ("maven", {"pom.xml": "<project/>", "mvnw": ""}, [(".", "maven-verify", ["./mvnw", "-q", "verify"])]),
            (
                "maven module folder with a wrapper",
                {"svc/pom.xml": "<project/>", "svc/mvnw": ""},
                [("svc", "maven-verify", ["./svc/mvnw", "-q", "verify", "-f", "svc/pom.xml"])],
            ),
            ("maven module folder without a wrapper", {"svc/pom.xml": "<project/>"}, [("svc", "maven-verify", ["mvn", "-q", "verify", "-f", "svc/pom.xml"])]),
            ("gradle", {"build.gradle.kts": "", "gradlew": ""}, [(".", "gradle-check", ["./gradlew", "check"])]),
            ("gradle without a wrapper", {"app/build.gradle": ""}, [("app", "gradle-check", ["gradle", "check", "-p", "app"])]),
            (
                "python and js side by side",
                {"pyproject.toml": "[tool.ruff]\n", "package.json": pkg(), "eslint.config.js": ""},
                [(".", "eslint", ["npm", "exec", "--", "eslint", "."]), (".", "ruff", ["ruff", "check"])],
            ),
        ):
            with self.subTest(label):
                self.assertEqual(self.checks(files), expected)

    def test_the_proposed_checks_are_valid_suite_entries_with_unique_names(self):
        with tempfile.TemporaryDirectory() as d:
            found = detect.detect(
                tree(
                    Path(d),
                    {
                        "pnpm-workspace.yaml": "",
                        "pyproject.toml": "[tool.ruff]\n[tool.mypy]\n",
                        "web/package.json": json.dumps({"scripts": {"test": "vitest"}}),
                        "web/eslint.config.js": "",
                        "web/tsconfig.json": "{}",
                        "api/go.mod": "module x\n",
                    },
                )
            )
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n' + detect.config_snippet(found))
        suites = {t["name"]: t for t in cfg.get("tests")}
        self.assertEqual(sorted(suites), ["api", "eslint-web", "go-vet-api", "mypy", "ruff", "tsc-web", "web"])
        self.assertEqual(suites["eslint-web"]["when_changed"], ["web/**"])
        self.assertNotIn("when_changed", suites["ruff"])
        self.assertIn("lint and type checks the repository already configures", detect.markdown(found))
        self.assertNotIn("already configures", detect.markdown({**found, "checks": []}))


if __name__ == "__main__":
    unittest.main()
