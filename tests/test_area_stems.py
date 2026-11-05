"""The auth and infra areas reach a file by its folder and name stem in every language, and only by a stem or a place that
means it. Three tables hold it. The old reading (the two lists before R524) stays inside the new one, over generated paths
and over this repository's tracked files, so no route or edit level falls. Each stem a language writes reaches its area in
every language, where the old lists missed all but a few. And a name that only holds the stem inside another word, a
documentation file, or a project's own name reaches no area it did not before."""

from __future__ import annotations

import unittest

import helpers  # the hermetic environment, and the repository's files
from aidd import config, risk
from aidd.kernel import globs

ROOT = helpers.ROOT
RANK = config.ROUTE_RANK
EXTENSIONS = tuple(helpers.language_columns().values())  # one file in each language of schemas/languages.json
AREAS = risk.builtin()["areas"]

# The two lists as they were before the change (`schemas/risks.json` at the commit before it), so the new reading is held
# against the old one. The excludes are the areas' own, which the change leaves alone.
OLD_AUTH = [
    "**/auth/**",
    "**/authn/**",
    "**/authz/**",
    "**/iam/**",
    "**/rbac/**",
    "**/permissions/**",
    "**/*.rego",
    "**/oauth/**",
    "**/oidc/**",
    "**/sso/**",
    "**/saml/**",
    "**/security/**",
    "**/login/**",
    "**/signin/**",
    "**/sign-in/**",
    "**/signup/**",
    "**/sign-up/**",
    "**/mfa/**",
    "**/password/**",
    "**/*auth.*",
    "**/auth_*.*",
    "**/auth-*.*",
    "**/authenticat*.*",
    "**/authoriz*.*",
    "**/authoris*.*",
    "**/login*.*",
    "**/logout*.*",
    "**/signin*.*",
    "**/sign-in*.*",
    "**/sign_in*.*",
    "**/signup*.*",
    "**/sign-up*.*",
    "**/sign_up*.*",
    "**/session*.*",
    "**/*password*.*",
    "**/passkey*.*",
    "**/webauthn*.*",
    "**/mfa*.*",
    "**/otp*.*",
    "**/totp*.*",
    "**/*2fa*.*",
    "**/two*factor*.*",
    "**/security.*",
    "**/*SecurityConfig*.*",
    "**/*jwt*.*",
    "**/*.guard.ts",
    "**/middleware.ts",
    "**/middleware.js",
]
OLD_INFRA = [
    "**/*.tf",
    "**/*.tfvars",
    "**/terraform/**",
    "**/k8s/**",
    "**/kubernetes/**",
    "**/helm/**",
    "**/Chart.yaml",
    "**/charts/*/templates/**",
    "**/*.bicep",
    "**/cloudformation/**",
    "**/pulumi/**",
    "**/kustomization.yaml",
    "**/serverless.yml",
    "**/serverless.yaml",
    "**/serverless.ts",
    "**/fly.toml",
    "**/vercel.json",
    "**/netlify.toml",
    "**/wrangler.toml",
    "**/wrangler.json",
    "**/wrangler.jsonc",
    "**/app.yaml",
    "**/Procfile",
    "**/cdk.json",
    "**/cdk/**",
    "**/nginx/**",
    "**/nginx.conf",
    "**/Caddyfile",
    "**/render.yaml",
    "**/railway.json",
    "**/railway.toml",
    "**/firebase.json",
    "**/amplify.yml",
    "**/ansible/**",
    "**/Dockerfile",
    "**/*.dockerfile",
    "**/Containerfile",
    "**/docker-compose*.yml",
    "**/docker-compose*.yaml",
    "**/compose.yaml",
]
OLD = {"auth": OLD_AUTH, "infra": OLD_INFRA}

# Each family of stems the change adds, with the convention it comes from, a file in its usual place in each language,
# and the area it reaches. `{x}` is a source extension. A file is in only where the old lists missed it in some language.
FAMILIES = (
    ("middleware.{x}", "auth", "a request middleware: Django's middleware.py, Next.js's middleware.ts, any framework's file of that name"),
    ("src/web/basic_auth_handler.{x}", "auth", "a snake-case file with auth inside its name: Python, Ruby, Rust, Go, PHP"),
    ("src/web/AuthMiddleware.{x}", "auth", "a middleware named for authentication: Express, Koa, Rails Rack, ASP.NET"),
    ("src/web/authGuard.{x}", "auth", "an authentication guard: Angular, NestJS, Laravel guards, Spring"),
    ("src/web/user.guard.{x}", "auth", "the dotted name of a route guard: Angular's and NestJS's style guide"),
    ("src/web/authFilter.{x}", "auth", "an authentication filter: Spring Security, ASP.NET, Java servlets"),
    ("src/web/authInterceptor.{x}", "auth", "an authentication interceptor: Angular, gRPC, Spring"),
    ("src/api/permissions.{x}", "auth", "a permissions module: Django REST framework's permissions.py, Go and Rust modules"),
    ("src/api/permission.{x}", "auth", "a permission module"),
    ("src/api/rbac.{x}", "auth", "a role-based access control module: Casbin, Kubernetes RBAC, Go and Rust"),
    ("src/api/acl.{x}", "auth", "an access control list module: Zend and Symfony ACL, Go and Rust"),
    ("deploy/Dockerfile.{x}", "infra", "Docker's documented Dockerfile.<variant> name"),
)
# Names that are a tool's own, whatever the language: each is read as the tool's own file, so its extension is fixed.
TOOL_NAMES = (
    ("Pulumi.yaml", "infra", "Pulumi's project file, whose program is in any language"),
    ("Pulumi.dev.yaml", "infra", "Pulumi's stack file"),
    ("terragrunt.hcl", "infra", "Terragrunt's config"),
    ("main.tf.json", "infra", "Terraform's JSON syntax"),
    ("cdktf.json", "infra", "CDK for Terraform's config"),
    ("cdk8s.yaml", "infra", "cdk8s's config"),
    ("skaffold.yaml", "infra", "Skaffold's config"),
    ("Tiltfile", "infra", "Tilt's file"),
    ("Vagrantfile", "infra", "Vagrant's file"),
    ("kustomization.yml", "infra", "Kustomize's file, in its two spellings"),
    ("compose.yml", "infra", "Compose's file, in its two spellings"),
    ("docker-bake.hcl", "infra", "Docker Buildx Bake's file"),
    ("serverless.json", "infra", "the Serverless Framework's config in JSON"),
    ("infra/main.go", "infra", "the folder an infrastructure program lives in, at the top"),
    ("infrastructure/stack.py", "infra", "the same folder, spelled out"),
    ("iac/app.ts", "infra", "the same folder, as infrastructure as code"),
    ("apps/web/infra/main.rs", "infra", "that folder inside a workspace's package"),
    ("packages/api/infra/index.js", "infra", "that folder inside a workspace's package"),
    ("services/billing/infra/Stack.java", "infra", "that folder inside a service"),
)
# Paths that must not reach the area: the stem inside another word, a project's own name, and a document.
ORDINARY = (
    ("src/author.py", "auth"),
    ("src/authority/list.go", "auth"),
    ("src/authors.rb", "auth"),
    ("src/author_filter.py", "auth"),
    ("lib/authored.ts", "auth"),
    ("src/guardian.rb", "auth"),
    ("src/safeguard.py", "auth"),
    ("src/bodyguard.cs", "auth"),
    ("src/scope_guard.rs", "auth"),
    ("src/launcher_guard.py", "auth"),
    ("src/premiddleware.go", "auth"),
    ("src/middlewares.go", "auth"),
    ("src/permissionless.py", "auth"),
    ("src/acls.py", "auth"),
    ("src/rbacx.py", "auth"),
    ("docs/middleware.md", "auth"),
    ("docs/permissions.md", "auth"),
    ("docs/guide/auth_guard.md", "auth"),
    ("src/permissions.css", "auth"),
    ("src/infrared/camera.py", "infra"),
    ("src/myinfra/x.go", "infra"),
    ("src/infrastructure.txt", "infra"),
    ("src/iaccount.py", "infra"),
    ("docs/infra/guide.md", "infra"),
    ("examples/infra/main.go", "infra"),
    ("tests/fixtures/infra/main.go", "infra"),
    ("tests/iac/test_app.py", "infra"),
    ("src/pulumi.py", "infra"),
    ("src/compose.py", "infra"),
    ("src/dockerfile_parser.py", "infra"),
    ("src/tilt.go", "infra"),
)


def reaches(name: str, path: str, paths: list[str] | None = None) -> bool:
    """Whether `path` is in the built-in area `name`, or in the area as the given pattern list would make it."""
    area = AREAS[name]
    return globs.match_any(paths if paths is not None else area["paths"], path, fold_case=True) and not globs.match_any(
        area.get("exclude", []), path, fold_case=True
    )


def advised(path: str) -> str:
    return risk.advice(None, [path])["route"]


def tracked() -> list[str]:
    """The repository's files: from git in a checkout, and by walking the tree in an unpacked sdist, which has no `.git`."""
    return helpers.repo_files()


class TheOldReadingStaysInsideTheNewOne(unittest.TestCase):
    def samples(self):
        for name, paths in OLD.items():
            for pattern in paths:
                yield name, globs.sample_path(pattern)
                yield name, pattern
        for name, template in ((n, f) for f, n, _ in FAMILIES):
            for x in EXTENSIONS:
                yield name, template.format(x=x)

    def test_a_path_the_old_lists_reached_is_reached_still_with_no_lower_route_or_edit_level(self):
        checked = 0
        for name, path in self.samples():
            if "*" in path or "?" in path or "[" in path or not reaches(name, path, OLD[name]):
                continue
            checked += 1
            self.assertTrue(reaches(name, path), f"{path} left the {name} area")
            self.assertGreaterEqual(RANK[advised(path)], RANK[AREAS[name]["route"]], path)
            edit = risk.edit_level(risk.rule_set(None), [path])[0]
            self.assertGreaterEqual({"allow": 0, "report": 1, "ask": 2}[edit], {"auth": 2, "infra": 1}[name], path)
        self.assertGreater(checked, 40)

    def test_no_tracked_file_of_this_repository_leaves_an_area_or_routes_lower(self):
        lost = [(n, f) for f in tracked() for n in OLD if reaches(n, f, OLD[n]) and not reaches(n, f)]
        self.assertEqual(lost, [])

    def test_the_other_areas_are_as_they_were(self):
        # Only the two lists changed: the excludes and every other area are the schema's own, and a pattern is only ever added.
        for name, paths in OLD.items():
            self.assertTrue(set(paths) - set(AREAS[name]["paths"]) <= {"**/*.guard.ts", "**/middleware.ts", "**/middleware.js"}, name)


class EachStemReachesItsAreaInEveryLanguage(unittest.TestCase):
    def test_a_stem_in_its_usual_place_reaches_the_area_in_each_language(self):
        for template, name, source in FAMILIES:
            self.assertTrue(source.strip())
            for x in EXTENSIONS:
                path = template.format(x=x)
                with self.subTest(path=path):
                    self.assertTrue(reaches(name, path), source)
                    self.assertGreaterEqual(RANK[advised(path)], RANK[AREAS[name]["route"]])

    def test_the_old_lists_missed_each_family_in_some_language(self):
        """The change is needed: for every family, at least one language's file was in no area before."""
        for template, name, _ in FAMILIES:
            missed = [template.format(x=x) for x in EXTENSIONS if not reaches(name, template.format(x=x), OLD[name])]
            with self.subTest(template=template):
                self.assertTrue(missed)

    def test_a_tools_own_names_and_the_infra_folders_reach_the_infra_area(self):
        for path, name, source in TOOL_NAMES:
            with self.subTest(path=path):
                self.assertTrue(reaches(name, path), source)

    def test_the_newly_reached_paths_route_higher_than_before(self):
        """Each path the old lists missed gains its area's route: the rise, old to new, that the change makes."""
        rose = {}
        for template, name, _ in FAMILIES:
            for x in EXTENSIONS:
                path = template.format(x=x)
                if not reaches(name, path, OLD[name]):
                    rose.setdefault((name, template), AREAS[name]["route"])
        self.assertEqual(set(rose.values()), {"major", "normal"})


class AnOrdinaryFileReachesNoNewArea(unittest.TestCase):
    def test_a_stem_inside_another_word_a_document_or_a_project_name_stays_out(self):
        for path, name in ORDINARY:
            with self.subTest(path=path):
                self.assertFalse(reaches(name, path), f"{path} reaches {name}")

    def test_a_generated_word_around_each_stem_stays_out(self):
        """Each stem with a letter run before or after it is another word: it is in no area unless the old lists had it there."""
        stems = ("middleware", "permissions", "permission", "rbac", "acl", "tiltfile", "vagrantfile")
        for stem in stems:
            for around in ("pre{}", "x{}", "{}er", "re{}ed"):
                for x in ("py", "go", "ts"):
                    path = f"src/{around.format(stem)}.{x}"
                    for name in ("auth", "infra"):
                        with self.subTest(path=path, area=name):
                            if not reaches(name, path, OLD[name]):
                                self.assertFalse(reaches(name, path))

    def test_the_new_infra_folders_hold_only_at_the_top_or_in_a_workspace_package(self):
        for path in ("docs/infra/a.go", "src/infra/a.go", "examples/iac/a.py", "tests/fixtures/infrastructure/a.py", "vendor/infra/a.go"):
            with self.subTest(path=path):
                self.assertFalse(reaches("infra", path) and not reaches("infra", path, OLD["infra"]))


if __name__ == "__main__":
    unittest.main()
