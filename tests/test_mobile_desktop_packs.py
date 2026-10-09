"""The mobile-apps pack as store-review conformance, and the desktop-apps pack.

A mobile change is judged by two stores before any user sees it, and most rejections are preventable by a test: a
crash, a placeholder, a dead link, a missing demo login, an undeclared required-reason API, an SDK the privacy labels
do not cover, a target SDK below the floor. The pack names the rules by section, dates the floors, and gives each
preventable cause a test. A desktop app has its own gates: notarization and Authenticode, the two stores' policies,
and a signed updater.
"""

from __future__ import annotations

import re
import unittest

from helpers import ROOT

from aidd import detect, docs, evals, packs, resources

SKILLS = ROOT / "plugins" / "aidd-team" / "skills"


def pack(slug: str) -> dict:
    return next(d for d in resources.roles()["domains"] if d["slug"] == slug)


def text(slug: str) -> str:
    return docs.render_pack(pack(slug))


def ids(slug: str) -> set[str]:
    return {s["id"] for s in pack(slug)["standards"]}


class MobileStandardsTests(unittest.TestCase):
    def test_the_store_rules_are_each_a_dated_entry(self):
        self.assertEqual(
            ids("mobile-apps"),
            {
                "owasp-masvs-and-mastg",
                "apple-app-review-guidelines",
                "apple-app-privacy-and-tracking",
                "app-store-connect-upload-requirements",
                "google-play-developer-program-policy",
                "google-play-data-safety",
                "google-play-target-api-level",
                "android-developer-verification",
            },
        )
        table = resources.load_json("roles.json")["standards"]
        self.assertIn("MASWE v1.0.0", table["owasp-masvs-and-mastg"]["edition"])
        self.assertIn("2026-06-08", table["apple-app-review-guidelines"]["edition"])
        for sid in ids("mobile-apps"):
            with self.subTest(sid=sid):
                # Re-checking a source is the point of the registry: any check on or after the build date counts.
                self.assertGreaterEqual(table[sid]["checked"], "2026-09-30")
                self.assertTrue(evals.confirms(table[sid]))
        for gone in ("material-design-and-google-play-policy", "platform-privacy-manifests-and-data-safety", "apple-human-interface-guidelines-and-app"):
            self.assertNotIn(gone, table)

    def test_the_platform_floors_are_dated_obligations(self):
        rows = {o["date"]: o["what"] for o in pack("mobile-apps")["obligations"]}
        self.assertIn("Xcode 26", rows["2026-04-28"])
        self.assertIn("iOS 13", rows["2026-09-09"])
        self.assertIn("API level 36", rows["2026-08-31"])
        self.assertRegex(rows["2026-08-31"], r"Wear OS.*35.*Android TV.*34")
        self.assertIn("trader", rows["2025-02-17"])
        self.assertIn("ITMS-91053", rows["2024-05-01"])
        self.assertIn("developer verification", rows["2026-09-30"])
        self.assertEqual(list(rows), sorted(rows))


class MobileChecklistTests(unittest.TestCase):
    def setUp(self):
        self.body = packs.section(text("mobile-apps"), "Checklist by loop step")

    def test_the_store_rules_are_named_by_section(self):
        for cue in (
            "demo account",
            "purpose string",
            "Play Console declaration",
            "SDK inventory",
            "3.1.3",
            "Play Billing",
            "1.2",
            "1.3",
            "Families",
            "5.1.2(i)",
            "third-party AI",
            "5.1.1(v)",
            "web link",
            "4.8",
            "2.3.1(a)",
            "12 testers",
            "14 days",
        ):
            self.assertIn(cue, self.body, cue)

    def test_phased_release_points_to_release_rollout(self):
        self.assertIn("phased release", self.body)
        self.assertIn("release-rollout", [x["owner"] for x in pack("mobile-apps")["owned_elsewhere"]])
        rollout = (SKILLS / "release-rollout" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("aidd-team:mobile-apps", rollout)
        self.assertLessEqual(packs.estimate_tokens(rollout), packs.PRACTICE_TOKENS)


class MobileTestCommandTests(unittest.TestCase):
    def test_each_preventable_rejection_has_a_test(self):
        tests = {t["name"]: t for t in pack("mobile-apps")["tests"]}
        self.assertEqual(
            set(tests),
            {
                "MobSF static scan",
                "UI tests on the OS matrix",
                "Required-reason API declarations",
                "Store SDK floors",
                "Sensitive permission allow-list",
                "SDK inventory against declarations",
                "Account deletion end to end",
                "Review readiness smoke",
            },
        )
        self.assertRegex(tests["Store SDK floors"]["how"], r"bundletool \d+\.\d+\.\d+")
        self.assertIn("targetSdkVersion", tests["Store SDK floors"]["how"])
        self.assertIn("NSPrivacyAccessedAPITypes", tests["Required-reason API declarations"]["how"])
        self.assertIn("merged manifest", tests["Sensitive permission allow-list"]["how"])
        self.assertIn("web", tests["Account deletion end to end"]["how"])
        self.assertRegex(tests["Review readiness smoke"]["how"], r"lychee.*v\d")
        self.assertIn({"owner": "accessible-ui", "tests": ["Mobile accessibility checks"]}, pack("mobile-apps")["tests_elsewhere"])

    def test_the_store_review_reference_holds_the_causes_and_the_notes_template(self):
        ref = (SKILLS / "mobile-apps" / "references" / "store-review.md").read_text(encoding="utf-8")
        for cue in ("2.1", "5.1.1", "4.2", "4.3", "Data safety", "target API", "ITMS-91053", "Notes for Review", "demo account"):
            self.assertIn(cue, ref, cue)
        self.assertIn("```", ref)
        self.assertLessEqual(packs.estimate_tokens(ref), packs.REFERENCE_TOKENS)


class DesktopPackTests(unittest.TestCase):
    def test_the_pack_exists_with_its_standards(self):
        self.assertEqual(
            ids("desktop-apps"),
            {
                "apple-notarization",
                "authenticode-code-signing",
                "microsoft-store-policies",
                "apple-app-review-guidelines",
                "electron-security-checklist",
                "tauri-security",
            },
        )
        self.assertEqual(resources.load_json("roles.json")["standards"]["microsoft-store-policies"]["edition"], "7.20")
        self.assertEqual(pack("desktop-apps")["steward"], "@thaithienvanid")
        self.assertTrue((SKILLS / "desktop-apps" / "SKILL.md").is_file())

    def test_the_signing_checks_are_test_commands(self):
        how = " ".join(t["how"] for t in pack("desktop-apps")["tests"])
        for cmd in ("spctl --assess", "stapler validate", "signtool verify /pa", "@electron/fuses"):
            self.assertIn(cmd, how, cmd)

    def test_the_runtime_hardening_and_the_signed_updater_are_in_the_checklist(self):
        body = packs.section(text("desktop-apps"), "Checklist by loop step")
        for cue in ("context isolation", "fuses", "CSP", "remote code", "capabilit", "signed", "hardened runtime", "stapled", "Trusted Root", "2.4.5"):
            self.assertIn(cue, body, cue)

    def test_the_distribution_reference_names_each_channel(self):
        ref = (SKILLS / "desktop-apps" / "references" / "distribution.md").read_text(encoding="utf-8")
        for channel in ("Mac App Store", "Microsoft Store", "Steam", "direct download"):
            self.assertIn(channel, ref)
        self.assertEqual(len(re.findall(r"(?m)^.*Steam.*$", ref)), 1, "Steam is one line")

    def test_detection_hints_the_pack_and_counts_it_as_an_interface(self):
        self.assertEqual(detect.packs_for({"electron"}), ["desktop-apps"])
        self.assertEqual(detect.packs_for({"@tauri-apps/api"}), ["desktop-apps"])
        self.assertIn("desktop-apps", detect.UI_PACKS)


if __name__ == "__main__":
    unittest.main()
