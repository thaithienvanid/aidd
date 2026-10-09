"""Domain depth. Each pack and practice skill carries the duties, the checks, and the
pinned test commands a practitioner in that domain expects, each resting on a registry entry with its evidence.

These tests pin what must be there (a standard, a dated obligation, a test command and its tool pin, a rule of the
practice), not how the sentence reads, so an edit that keeps the knowledge passes and one that drops it fails.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT

from aidd import docs, packs, resources

SKILLS = ROOT / "plugins" / "aidd-team" / "skills"
PIN = re.compile(r"\d+\.\d+(\.\d+)?")


def raw() -> dict:
    return resources.load_json("roles.json")


def pack(slug: str) -> dict:
    return next(d for d in raw()["domains"] if d["slug"] == slug)


def ids(refs: list) -> set[str]:
    return {r if isinstance(r, str) else r["id"] for r in refs}


def rendered(slug: str) -> str:
    return docs.render_pack(next(d for d in resources.roles()["domains"] if d["slug"] == slug))


def skill(name: str) -> str:
    """A practice skill's SKILL.md and its references, as one text."""
    folder = SKILLS / name
    return "\n".join(p.read_text(encoding="utf-8") for p in [folder / "SKILL.md", *sorted((folder / "references").glob("*.md"))] if p.is_file())


def test_row(slug: str, name: str) -> dict:
    return next(t for t in pack(slug)["tests"] if t["name"] == name)


def practice_row(name: str, test: str) -> str:
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    return next(r for r in packs.section(text, "Test commands").splitlines() if r.startswith(f"| {test}"))


def entry(sid: str) -> dict:
    return raw()["standards"][sid]


class RegistryEvidenceTests(unittest.TestCase):
    """Every domain entry carries a checked date, a source, and a quote read at the source on that date."""

    NEW = (
        "psd2-strong-customer-authentication",
        "psd3-and-payment-services-regulation",
        "emv-3-d-secure",
        "emv-payment-tokenisation",
        "standard-webhooks",
        "graphql-specification",
        "http-deprecation-and-sunset-headers",
        "rfc-9700-oauth-security-bcp",
        "nist-sp-800-63-4",
        "us-core-and-smart-app-launch",
        "onc-hti-and-information-blocking",
        "fda-524b-cyber-devices",
        "iec-81001-5-1",
        "uk-online-safety-act-childrens-duties",
        "dsa-article-28-protection-of-minors",
        "iso-iec-27566-1-age-assurance",
        "iana-time-zone-database",
        "unicode-bidirectional-algorithm-uax-9",
        "web-platform-baseline",
        "subresource-integrity-and-permissions-policy",
        "eprivacy-directive-art-5-3",
        "open-data-product-standard",
        "eval-statistics-intervals-and-pass-k",
        "dependency-release-age-cooldown",
    )

    def test_each_new_entry_is_checked_with_evidence(self):
        for sid in self.NEW:
            with self.subTest(sid=sid):
                e = entry(sid)
                self.assertRegex(e.get("checked", ""), r"^2026-")
                self.assertTrue(e["source"].startswith("https://"))
                self.assertTrue(e["evidence"]["url"].startswith("https://") and len(e["evidence"]["quote"]) > 20)
                self.assertEqual(e["evidence"]["retrieved"], e["checked"])

    def test_each_new_entry_is_used_by_a_pack_or_a_practice(self):
        data = raw()
        used = set()
        for d in data["domains"]:
            used |= ids(d["standards"])
        for p in data["practices"].values():
            used |= ids(p["standards"])
        self.assertEqual(set(self.NEW) - used, set())


class PaymentsTests(unittest.TestCase):
    def test_strong_customer_authentication_3ds_and_network_tokens(self):
        p = pack("payments-and-finance")
        self.assertLessEqual({"pci-dss", "psd2-strong-customer-authentication", "emv-3-d-secure", "emv-payment-tokenisation"}, ids(p["standards"]))
        text = rendered("payments-and-finance")
        for must in ("6.4.3", "11.6.1", "exemption", "network token", "chargeback", "dispute"):
            self.assertIn(must, text, must)

    def test_psd3_and_the_psr_are_agreed_texts_not_yet_law(self):
        e = entry("psd3-and-payment-services-regulation")
        self.assertEqual(e.get("maturity"), "emerging")
        self.assertIn("2026-04-23", e["notes"])
        self.assertIn("Official Journal", e["notes"])
        rows = [o for o in pack("payments-and-finance")["obligations"] if "psd3-and-payment-services-regulation" in o["cites"]]
        self.assertTrue(rows)
        self.assertIn("Official Journal pending", rows[0]["what"])

    def test_psp_webhooks_point_to_the_one_signature_and_replay_test(self):
        self.assertIn({"owner": "api-design", "tests": ["Webhook signature and replay tests"]}, pack("payments-and-finance")["tests_elsewhere"])
        self.assertIn("Payment page script check", {t["name"] for t in pack("payments-and-finance")["tests"]})


class ApiTests(unittest.TestCase):
    def test_the_pack_covers_graphql_grpc_webhooks_and_deprecation(self):
        p = pack("apis-and-services")
        self.assertLessEqual({"graphql-specification", "standard-webhooks", "http-deprecation-and-sunset-headers"}, ids(p["standards"]))
        self.assertIn("graphql-inspector", test_row("apis-and-services", "GraphQL schema diff")["how"])
        self.assertRegex(test_row("apis-and-services", "GraphQL schema diff")["how"], PIN)
        buf = test_row("apis-and-services", "Protobuf lint and breaking check")["how"]
        self.assertIn("buf breaking", buf)
        self.assertIn("buf lint", buf)
        self.assertRegex(buf, PIN)

    def test_api_design_says_how(self):
        text = skill("api-design")
        for must in (
            "Deprecation",
            "Sunset",
            "If-Match",
            "412",
            "ETag",
            "persisted",
            "depth",
            "webhook-signature",
            "webhook-timestamp",
            "RFC 9745",
            "RFC 8594",
        ):
            self.assertIn(must, text, must)
        self.assertLessEqual({"rfc-9110-http-semantics", "http-deprecation-and-sunset-headers"}, ids(raw()["practices"]["api-design"]["standards"]))
        for name in ("Webhook signature and replay tests", "GraphQL depth and cost limits", "Lost-update test"):
            self.assertTrue(practice_row("api-design", name), name)


class AuthenticationTests(unittest.TestCase):
    def test_secure_coding_has_an_authentication_and_sessions_section(self):
        text = skill("secure-coding")
        self.assertIn("Authentication and sessions", text)
        for must in ("RFC 9700", "PKCE", "SP 800-63B-4", "passkey", "WebAuthn", "V6", "V7", "V10", "rotat", "lockout", "recovery"):
            self.assertIn(must.casefold(), text.casefold(), must)
        self.assertLessEqual({"rfc-9700-oauth-security-bcp", "nist-sp-800-63-4", "owasp-asvs"}, ids(raw()["practices"]["secure-coding"]["standards"]))
        for name in ("Session rotation test", "Lockout and throttling tests", "MFA and recovery tests"):
            self.assertTrue(practice_row("secure-coding", name), name)


class HealthTests(unittest.TestCase):
    def test_the_health_pack_covers_the_us_api_rules_devices_and_security(self):
        p = pack("health")
        self.assertLessEqual(
            {"us-core-and-smart-app-launch", "onc-hti-and-information-blocking", "fda-524b-cyber-devices", "iec-81001-5-1"}, ids(p["standards"])
        )
        text = rendered("health")
        for must in ("SBOM", "information blocking", "SMART"):
            self.assertIn(must, text, must)
        self.assertRegex(test_row("health", "Traceability check")["how"], PIN)

    def test_the_hipaa_security_rule_update_and_fhir_r6_are_stated_honestly(self):
        hipaa = entry("hipaa-privacy-and-security-rules")["notes"]
        self.assertIn("proposed", hipaa)
        self.assertIn("2027", hipaa)
        self.assertIn("R6", entry("hl7-fhir")["notes"])


class ChildrenTests(unittest.TestCase):
    def test_the_children_pack_carries_its_dated_duties(self):
        p = pack("products-for-children")
        self.assertLessEqual(
            {"coppa", "uk-online-safety-act-childrens-duties", "dsa-article-28-protection-of-minors", "iso-iec-27566-1-age-assurance"}, ids(p["standards"])
        )
        dates = {o["date"] for o in p["obligations"]}
        self.assertIn("2026-04-22", dates)
        text = rendered("products-for-children")
        for must in ("retention policy", "age assurance", "third part"):
            self.assertIn(must, text, must)

    def test_readability_is_one_pinned_test_the_writers_own(self):
        self.assertIn({"owner": "technical-writing", "tests": ["Reading-level check"]}, pack("products-for-children")["tests_elsewhere"])
        self.assertRegex(practice_row("technical-writing", "Reading-level check"), PIN)


class InternationalizationTests(unittest.TestCase):
    def test_cldr_is_pinned_and_mf2_is_stated_honestly(self):
        cldr = entry("unicode-cldr")
        self.assertEqual(cldr["edition"], "CLDR 48")
        self.assertIn("49", cldr["notes"])
        self.assertTrue(cldr.get("review_due"))
        self.assertIn("preview", entry("icu-messageformat")["notes"].casefold())

    def test_time_zones_bidi_and_pinned_linters(self):
        p = pack("internationalization")
        self.assertLessEqual({"iana-time-zone-database", "unicode-bidirectional-algorithm-uax-9"}, ids(p["standards"]))
        for name in ("Message-format lint", "Pseudo-localization build"):
            self.assertRegex(test_row("internationalization", name)["how"], PIN, name)


class WebTests(unittest.TestCase):
    def test_the_web_pack_covers_baseline_trusted_types_sri_and_consent(self):
        p = pack("web-front-end")
        self.assertLessEqual({"web-platform-baseline", "subresource-integrity-and-permissions-policy", "eprivacy-directive-art-5-3"}, ids(p["standards"]))
        text = rendered("web-front-end")
        for must in ("Trusted Types", "integrity", "Permissions-Policy", "Global Privacy Control", "consent"):
            self.assertIn(must, text, must)
        compat = test_row("web-front-end", "Browser support check")["how"]
        self.assertIn("eslint-plugin-compat", compat)
        self.assertRegex(compat, PIN)


class DataAndEvalTests(unittest.TestCase):
    def test_data_contracts_and_products_are_pinned(self):
        self.assertEqual(entry("open-data-contract-standard")["edition"], "v3.2.0")
        self.assertEqual(entry("open-data-product-standard")["edition"], "v1.1.0")
        self.assertIn("open-data-product-standard", ids(pack("data-and-analytics")["standards"]))

    def test_ai_evals_report_uncertainty_and_reliability(self):
        text = skill("ai-evals")
        for must in ("confidence interval", "pass^k", "contamination", "retire", "sample"):
            self.assertIn(must.casefold(), text.casefold(), must)
        self.assertIn("eval-statistics-intervals-and-pass-k", ids(raw()["practices"]["ai-evals"]["standards"]))


class SmallItemTests(unittest.TestCase):
    def test_each_practice_names_its_tool_or_rule(self):
        cases = {
            "threat-model": ("Threat Dragon", "pytm"),
            "estimation": ("Monte Carlo", "85th"),
            "dependency-upgrade": ("minimumReleaseAge", "cooldown"),
            "schema-migration": ("gh-ost", "pgroll"),
            "code-review": ("AI-generated", "hallucinat"),
            "technical-writing": ("Reading-level check",),
        }
        for name, musts in cases.items():
            text = skill(name)
            for must in musts:
                self.assertIn(must, text, (name, must))
        self.assertIn("ai-assisted-coding-verify-every-generated", ids(raw()["practices"]["code-review"]["standards"]))
        self.assertIn("dependency-release-age-cooldown", ids(raw()["practices"]["dependency-upgrade"]["standards"]))

    def test_public_sector_names_its_tools(self):
        text = rendered("public-sector")
        for must in ("compliance-trestle", "CBOM"):
            self.assertIn(must, text, must)
        self.assertIn("cyclonedx", ids(pack("public-sector")["standards"]))


if __name__ == "__main__":
    unittest.main()
