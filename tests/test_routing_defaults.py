"""The baseline's routing defaults on the paths real repositories hold.

Every config inherits the baseline, so a path it misses routes minor in every adopter's repository, and a path it
over-protects makes every adopter's routine edit major. These tests hold the baseline to a sample of realistic paths
under a bare `team` config: payments, single-file auth, secrets, deploy config, and migrations outside `migrations/`
raise the route; aidd's own release files, docs, and Markdown do not.
"""

import unittest

from helpers import ROOT

from aidd import config
from aidd.evals import standards_audit
from aidd.gate import routing
from aidd.config import baseline, harnesses
from aidd.kernel import globs, json_schema, resources

BARE_TEAM = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a", "@b"]\n'

# (path, minimum route under a bare team config)
SAMPLE = [
    # Payments: major, the financial dimension, reviewed by the finance pool.
    ("src/payments/stripe_webhook.py", "major"),
    ("app/billing/charge.rb", "major"),
    ("services/api/internal/handlers/payment.go", "major"),
    ("src/lib/stripe.ts", "major"),
    ("app/services/invoicing/create.rb", "major"),
    # Auth in a single file.
    ("src/lib/auth.ts", "major"),
    ("apps/web/middleware.ts", "major"),
    ("src/server/jwt.ts", "major"),
    ("backend/app/core/security.py", "major"),
    ("src/main/java/com/acme/config/SecurityConfig.java", "major"),
    ("app/Http/Middleware/Authenticate.php", "major"),
    ("src/oauth/callback.ts", "major"),
    ("src/sso/saml.go", "major"),
    ("src/hooks/useAuth.ts", "major"),
    ("src/utils/crypto.ts", "major"),
    # Secrets in a single file.
    ("config/secrets.yml", "major"),
    ("config/credentials.yml.enc", "major"),
    ("android/app/release.keystore", "major"),
    ("android/app/upload.jks", "major"),
    ("ios/AuthKey_ABC123.p8", "major"),
    ("ios/dist.mobileprovision", "major"),
    ("android/app/google-services.json", "major"),
    ("ios/Runner/GoogleService-Info.plist", "major"),
    # Migrations outside migrations/.
    ("drizzle/0001_add_users.sql", "major"),
    ("db/schema.sql", "major"),
    ("db/structure.sql", "major"),
    ("supabase/seed.sql", "major"),
    # Deploy config.
    ("serverless.yml", "normal"),
    ("fly.toml", "normal"),
    ("vercel.json", "normal"),
    ("netlify.toml", "normal"),
    ("wrangler.toml", "normal"),
    ("app.yaml", "normal"),
    ("Procfile", "normal"),
    ("cdk.json", "normal"),
    ("cdk/lib/stack.ts", "normal"),
    ("nginx/nginx.conf", "normal"),
    ("render.yaml", "normal"),
    ("railway.json", "normal"),
    ("railway.toml", "normal"),
    # Mobile app manifests: the permissions and capabilities an app asks for.
    ("ios/Runner/Info.plist", "normal"),
    ("android/app/src/main/AndroidManifest.xml", "normal"),
    ("ios/App/App.entitlements", "normal"),
    # Manifests are dependencies (normal) for every adopter, never protected.
    ("pyproject.toml", "normal"),
    ("packages/api/pyproject.toml", "normal"),
    ("setup.py", "normal"),
    ("setup.cfg", "normal"),
    ("package.json", "normal"),
    ("apps/web/package.json", "normal"),
    # Not sensitive: docs, Markdown, and names that only look like a sensitive word.
    ("docs/auth/overview.md", "minor"),
    ("src/auth/README.md", "minor"),
    ("docs/payments/refunds.md", "minor"),
    ("docs/secrets/rotation.md", "minor"),
    ("src/models/author.py", "minor"),
    ("src/web/checkout/Button.tsx", "minor"),
    ("src/components/Button.tsx", "minor"),
    ("README.md", "minor"),
    ("install.sh", "minor"),
    ("SECURITY.md", "minor"),
    ("GOVERNANCE.md", "minor"),
    ("RELEASING.md", "minor"),
    ("REVIEW.md", "minor"),
]


def assess(path: str, text: str = BARE_TEAM, **kw) -> routing.Assessment:
    return routing.assess_paths(config.load_text(text), [path], **kw)


class BaselineSampleTests(unittest.TestCase):
    def test_each_sample_path_routes_as_its_risk_needs(self):
        wrong = [(p, want, got) for p, want in SAMPLE if (got := assess(p).required_route) != want]
        self.assertEqual(wrong, [])

    def test_payments_is_major_on_the_financial_dimension_for_the_finance_pool(self):
        for path in ("src/payments/refund.ts", "app/billing/charge.rb", "services/api/handlers/payment.go"):
            a = assess(path)
            self.assertEqual(a.required_route, "major", path)
            self.assertIn("financial", a.dimensions, path)
            self.assertEqual(a.pools, {"finance"}, path)
            self.assertTrue(any("baseline:payments" in r for r in a.reasons), a.reasons)

    def test_a_docs_or_markdown_file_under_a_sensitive_folder_is_excluded(self):
        for rule in ("baseline:auth", "baseline:secrets-crypto", "baseline:payments"):
            entry = next(r for r in baseline.baseline_data()["risk_rules"] if r["name"] == rule)
            for path in ("docs/x/y.ts", "src/auth/notes.md", "packages/web/docs/billing/intro.mdx"):
                self.assertTrue(globs.match_any(entry["exclude"], path), (rule, path))

    def test_rule_exclusions_narrow_a_rule_for_a_ui_folder(self):
        text = BARE_TEAM.replace("\nowners:", '\nrule_exclusions: {"baseline:auth": ["src/components/permissions/**"]}\nowners:')
        self.assertEqual(assess("src/components/permissions/Badge.tsx").required_route, "major")
        self.assertEqual(assess("src/components/permissions/Badge.tsx", text).required_route, "minor")
        self.assertEqual(assess("src/auth/session.ts", text).required_route, "major")

    def test_type_infra_needs_at_least_normal(self):
        self.assertEqual(assess("scripts/rotate.sh", ctype="infra").required_route, "normal")
        self.assertEqual(assess("scripts/rotate.sh", ctype="chore").required_route, "minor")
        self.assertEqual(assess("db/migrations/1.sql", ctype="infra").required_route, "major")


class OwnFilesTests(unittest.TestCase):
    """aidd's own release and packaging files are protected in this repository's config, not in everyone's baseline."""

    OWN = ("install.sh", "pyproject.toml", "SECURITY.md", ".github/SECURITY.md", "GOVERNANCE.md", "RELEASING.md", "REVIEW.md")

    def test_the_baseline_does_not_protect_aidd_s_own_files(self):
        protected = baseline.baseline_data()["protected_paths"]
        for path in (*self.OWN, "packages/api/pyproject.toml", "tools/install.sh", "setup.py", "setup.cfg", "docs/SECURITY.md"):
            self.assertFalse(globs.match_any(protected, path, fold_case=True), path)

    def test_this_repository_still_protects_them(self):
        cfg = config.load_file(config.CONFIG_PATH, str(ROOT))
        protected = routing.protected_paths(cfg)
        for path in self.OWN:
            self.assertTrue(globs.match_any(protected, path, fold_case=True), path)
            self.assertEqual(routing.assess_paths(cfg, [path]).required_route, "major", path)


def _redundant(patterns: list[str]) -> list[tuple[str, str]]:
    """(covered, by) pairs: a pattern whose plainest path another pattern in the list already matches, such as `X` next to
    `**/X`, or `.clinerules/**` next to `.clinerules` (a pattern with no wildcard covers everything under it)."""
    return [(p, q) for p in patterns for q in patterns if q != p and globs.match(q, globs.literal_form(p))]


class BaselineShapeTests(unittest.TestCase):
    def test_harness_paths_are_a_generated_key_apart_from_the_hand_list(self):
        raw = resources.load_json("baseline.json")
        derived = set(harnesses.harness_protected_paths())
        self.assertIn("harness_paths", raw)
        self.assertEqual([p for p in raw["protected_paths"] if p in derived], [], "a harness path belongs in harness_paths")
        self.assertTrue(set(raw["harness_paths"]) <= derived)
        merged = baseline.baseline_data()["protected_paths"]
        self.assertTrue(set(raw["protected_paths"]) | set(raw["harness_paths"]) <= set(merged))

    def test_no_protected_path_or_rule_path_is_redundant(self):
        self.assertEqual(_redundant(baseline.baseline_data()["protected_paths"]), [])
        self.assertEqual(_redundant(harnesses.harness_protected_paths()), [])
        for r in baseline.baseline_data()["risk_rules"]:
            self.assertEqual(_redundant(r["paths"]), [], r["name"])

    def test_the_description_says_risk_rules_can_be_disabled_and_protected_paths_cannot(self):
        text = resources.load_json("baseline.json")["description"]
        self.assertNotIn("cannot disable", text)
        self.assertIn("disable_rules", text)
        self.assertIn("rule_exclusions", text)

    def test_every_harness_path_validates_as_a_glob(self):
        for p in resources.load_json("baseline.json")["harness_paths"]:
            self.assertEqual(json_schema.validate(p, "common.schema.json#/$defs/glob"), [], p)


class SchemaTextTests(unittest.TestCase):
    def test_locale_is_labelled_agent_facing_only(self):
        text = resources.load_json("config.schema.json")["properties"]["locale"]["description"]
        self.assertIn("agent-facing only", text.lower())


class EvidenceBoilerplateTests(unittest.TestCase):
    def test_a_copyright_line_does_not_confirm_a_date(self):
        entry = {"name": "x", "checked": "2026-09-29"}
        entry["evidence"] = {
            "url": "https://www.rfc-editor.org/rfc/rfc5646",
            "quote": "Copyright (c) 2009 IETF Trust and the persons identified as the document authors.",
        }
        self.assertFalse(standards_audit.confirms(entry))

    def test_no_registry_entry_quotes_a_copyright_line(self):
        table = resources.load_json("roles.json")["standards"]
        bad = [k for k, e in table.items() if str((e.get("evidence") or {}).get("quote", "")).lstrip().lower().startswith("copyright")]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
