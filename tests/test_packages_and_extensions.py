"""The package-publishing pack and the extensions-and-marketplace-apps pack.

A project that publishes to a package registry, and an extension or app listed in a host's marketplace, each meet
rules the host enforces at the door: trusted publishing and provenance, a registry's required files, a store's review
policy. Each pack names the standards those rules come from, dated and quoted at the source; the per-registry and
per-host facts live in the pack's references, one table each, so the SKILL.md stays under its cap. The published
project's Scorecard and OSPS Baseline belong to package-publishing; the CI pipeline keeps build provenance.
"""

from __future__ import annotations

import unittest

from helpers import ROOT

from aidd import detect, docs, evals, packs, resources

SKILLS = ROOT / "plugins" / "aidd-team" / "skills"
PUBLISHING = "package-publishing"
EXTENSIONS = "extensions-and-marketplace-apps"


def pack(slug: str) -> dict:
    return next(d for d in resources.roles()["domains"] if d["slug"] == slug)


def raw_pack(slug: str) -> dict:
    return next(d for d in resources.load_json("roles.json")["domains"] if d["slug"] == slug)


def ids(refs: list) -> set[str]:
    return {r if isinstance(r, str) else r["id"] for r in refs}


def read(path) -> str:
    return path.read_text(encoding="utf-8")


class BothPacksTests(unittest.TestCase):
    def test_both_packs_exist_with_a_steward_and_meet_the_template(self):
        for slug in (PUBLISHING, EXTENSIONS):
            d = pack(slug)
            self.assertEqual(d["steward"], "@thaithienvanid", slug)
            self.assertEqual(read(docs.pack_path(ROOT, d)), docs.render_pack(d), slug)
            self.assertEqual([p for p in packs.problems() if p["where"].endswith(slug)], [], slug)

    def test_every_standard_they_name_is_confirmed_at_its_source(self):
        table = resources.load_json("roles.json")["standards"]
        for slug in (PUBLISHING, EXTENSIONS):
            for sid in ids(raw_pack(slug)["standards"]):
                entry = table[sid]
                self.assertTrue(entry.get("checked"), sid)
                self.assertTrue(evals.confirms(entry), sid)

    def test_the_per_host_facts_live_in_one_reference_each(self):
        for slug, ref in ((PUBLISHING, "registries.md"), (EXTENSIONS, "hosts.md")):
            listed = [r["path"] for r in raw_pack(slug)["references"]]
            self.assertEqual(listed, [f"references/{ref}"], slug)
            self.assertTrue((SKILLS / slug / "references" / ref).is_file(), slug)


class PackagePublishingTests(unittest.TestCase):
    def setUp(self):
        self.pack = raw_pack(PUBLISHING)
        self.registries = read(SKILLS / PUBLISHING / "references" / "registries.md")

    def test_the_published_project_owns_scorecard_and_the_osps_baseline(self):
        self.assertLessEqual({"openssf-scorecard", "openssf-open-source-project-security-baseline", "slsa"}, ids(self.pack["standards"]))

    def test_every_registry_the_pack_names_has_a_row(self):
        for registry in ("npm", "PyPI", "crates.io", "RubyGems", "NuGet", "Maven Central", "Homebrew"):
            self.assertIn(f"| {registry} |", self.registries, registry)

    def test_the_trusted_publishing_facts_are_the_verified_ones(self):
        self.assertIn("11.5.1", self.registries)
        self.assertIn("PEP 740", self.registries)
        self.assertIn("GitLab.com", self.registries)
        self.assertIn(".asc", self.registries)
        self.assertIn("-sources.jar", self.registries)

    def test_the_cra_steward_duties_and_dates_are_there(self):
        dates = {o["date"] for o in self.pack["obligations"]}
        self.assertLessEqual({"2026-09-11", "2027-12-11"}, dates)
        self.assertIn("incident-response", {x["owner"] for x in self.pack["owned_elsewhere"]})

    def test_a_breaking_change_is_caught_by_an_api_diff(self):
        how = " ".join(t["how"] for t in self.pack["tests"])
        for tool in ("cargo-semver-checks", "api-extractor", "japicmp"):
            self.assertIn(tool, how)


class ExtensionsTests(unittest.TestCase):
    def setUp(self):
        self.pack = raw_pack(EXTENSIONS)
        self.hosts = read(SKILLS / EXTENSIONS / "references" / "hosts.md")

    def test_every_host_has_a_row(self):
        for host in (
            "Chrome Web Store",
            "Firefox (AMO)",
            "VS Code Marketplace",
            "Shopify App Store",
            "Slack Marketplace",
            "Atlassian Marketplace",
            "Teams store",
            "Salesforce AgentExchange",
        ):
            self.assertIn(f"| {host} ", self.hosts, host)

    def test_the_dated_platform_changes_are_there(self):
        dates = {o["date"] for o in self.pack["obligations"]}
        self.assertLessEqual({"2026-08-31", "2026-12-01"}, dates)

    def test_the_shared_tests_cover_what_every_host_reviews(self):
        names = {t["name"] for t in self.pack["tests"]}
        self.assertLessEqual({"Permission and scope diff", "Remote code scan", "Listing links without sign-in", "Reviewer access check"}, names)
        self.assertIn("Slack data", self.hosts)
        self.assertIn("Billing API", self.hosts)

    def test_an_extension_dependency_loads_the_pack(self):
        for dep in ("@types/vscode", "webextension-polyfill", "@shopify/shopify-app-react-router", "@slack/bolt", "@forge/api", "@microsoft/teams-js"):
            self.assertEqual(detect.packs_for({dep}), [EXTENSIONS], dep)


class PointerTests(unittest.TestCase):
    def test_the_cloud_pack_points_each_fact_to_its_owner(self):
        owners = {x["owner"]: x["what"] for x in raw_pack("cloud-and-infrastructure")["owned_elsewhere"]}
        self.assertIn("SLSA", owners["ci-pipeline"])
        self.assertNotIn("Scorecard", owners["ci-pipeline"])
        self.assertIn("Scorecard", owners[PUBLISHING])
        self.assertIn("OSPS Baseline", owners[PUBLISHING])

    def test_the_ci_pipeline_keeps_build_provenance_only(self):
        ci = ids(resources.load_json("roles.json")["practices"]["ci-pipeline"]["standards"])
        self.assertIn("slsa", ci)
        self.assertEqual(ci & {"openssf-scorecard", "openssf-open-source-project-security-baseline"}, set())


if __name__ == "__main__":
    unittest.main()
