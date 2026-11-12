"""Pressure variants of plugin cases. Each copies a case's fixture and graders byte for byte, so the same graders score it.

Only the prompt changes: it adds a push to skip a step (hurry, a comment that says approved). The loaders in
test_plugin_evals check that every case parses; this checks the copy is exact, so a variant never drifts into a different
measurement. One variant, work already written, has its own fixture and graders, because its pressure is a file the source
lacks: the code sits uncommitted in the working tree.
"""

import unittest

from helpers import ROOT
from test_plugin_evals import front_matter

PLUGIN = ROOT / "evals" / "plugin"
# In order of the variant's name.
VARIANTS = {
    "asks-before-merge-under-demo-pressure": "asks-before-merge",
    "asks-before-payments-edit-under-authority": "asks-before-payments-edit",
    "spec-before-code-when-code-exists": "spec-before-code",
}
OWN_FIXTURE = {"spec-before-code-when-code-exists"}


def files(case) -> dict[str, bytes]:
    """Every file of a case but its prompt and case.yaml (whose name differs), by relative path."""
    return {str(p.relative_to(case)): p.read_bytes() for p in sorted(case.rglob("*")) if p.is_file() and p.name not in ("prompt.md", "case.yaml")}


class PressureVariantTests(unittest.TestCase):
    def test_the_variants_are_listed_in_order_of_their_names_and_all_exist(self):
        self.assertEqual(list(VARIANTS), sorted(VARIANTS))
        for variant in VARIANTS:
            self.assertTrue((PLUGIN / variant / "prompt.md").is_file(), variant)

    def test_a_variant_copies_the_fixture_and_every_grader_of_its_source(self):
        for variant, source in VARIANTS.items():
            if variant not in OWN_FIXTURE:
                with self.subTest(variant=variant):
                    self.assertTrue(files(PLUGIN / source), source)
                    self.assertEqual(files(PLUGIN / variant), files(PLUGIN / source))

    def test_a_variant_with_its_own_fixture_adds_what_its_pressure_needs(self):
        for variant in OWN_FIXTURE:
            with self.subTest(variant=variant):
                own, source = files(PLUGIN / variant), files(PLUGIN / VARIANTS[variant])
                self.assertNotEqual(own["fixture.sh"], source["fixture.sh"])
                self.assertEqual(
                    {k for k in own if k.startswith("graders/")} - {k for k in source if k.startswith("graders/")},
                    {"graders/code-not-committed.md", "graders/keeps-the-persons-code.md"},
                )

    def test_a_variant_keeps_its_source_settings_and_adds_the_pressure_tag(self):
        for variant, source in VARIANTS.items():
            with self.subTest(variant=variant):
                new, body = front_matter(PLUGIN / variant / "prompt.md")
                old, old_body = front_matter(PLUGIN / source / "prompt.md")
                self.assertEqual(new["max_turns"], old["max_turns"])
                if variant in OWN_FIXTURE:  # it reads the commit log, so the agent needs a shell to commit with
                    self.assertEqual(new["allowed_tools"], [*old["allowed_tools"], "Bash"])
                else:
                    self.assertEqual(new["allowed_tools"], old["allowed_tools"])
                own = ("claim:", "tier:", "shape:", "world:")  # a variant names its own claims and tier, so only the other tags must match
                self.assertEqual([t for t in new["tags"] if not t.startswith(own)], [*[t for t in old["tags"] if not t.startswith(own)], "pressure"])
                for kind in ("shape:", "world:"):
                    project = [[t for t in data["tags"] if t.startswith(kind)] for data in (new, old)]
                    self.assertEqual(project[0], project[1], "a variant is the same project as its source, under pressure")
                self.assertNotEqual(new["description"], old["description"])
                self.assertIn(old_body.strip().split(". ")[0], body, "the variant keeps the source's request")
                self.assertGreater(len(body), len(old_body), "the variant adds the pressure")

    def test_a_variant_seeds_its_workspace_as_its_source_does(self):
        for variant, source in VARIANTS.items():
            with self.subTest(variant=variant):
                has = (PLUGIN / variant / "case.yaml").is_file()
                self.assertEqual(has, (PLUGIN / source / "case.yaml").is_file())
                if has:
                    text = (PLUGIN / variant / "case.yaml").read_text(encoding="utf-8")
                    self.assertEqual(text, (PLUGIN / source / "case.yaml").read_text(encoding="utf-8").replace(source, variant))


if __name__ == "__main__":
    unittest.main()
