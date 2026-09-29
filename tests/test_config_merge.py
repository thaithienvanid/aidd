"""How a child config merges with its parents: lists add, owner rules combine, and nothing loosens silently."""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import config

HEAD = 'aidd_version = "1.0.0"\nprofile = "team"\n'


def load(child: str, parent: str):
    return config.load_text(HEAD + 'extends = [{ path = "p.toml" }]\n' + child, prefetched={"p.toml": HEAD + parent})


class ConfigMergeTests(unittest.TestCase):
    def test_owner_areas_from_parent_and_child_both_apply(self):
        cfg = load(
            '[owners]\napprovers = ["@x"]\n[[owners.paths]]\npaths = ["web/"]\napprovers = ["@web"]\n',
            '[owners]\napprovers = ["@x"]\n[[owners.paths]]\npaths = ["infra/"]\napprovers = ["@platform"]\n',
        )
        self.assertEqual(sorted(e["paths"][0] for e in cfg.get("owners", "paths")), ["infra/", "web/"])

    def test_codeowners_stays_on_once_a_parent_turns_it_on(self):
        cfg = load('[owners]\napprovers = ["@x"]\ncodeowners = false\n', '[owners]\napprovers = ["@x"]\ncodeowners = true\n')
        self.assertTrue(cfg.get("owners", "codeowners"))

    def test_local_approvals_only_tighten_to_signed(self):
        base = 'aidd_version = "1.0.0"\nprofile = "{}"\n[owners]\napprovers = ["@x"]\n'
        self.assertEqual(config.load_text(base.format("team")).gates["local_approvals"], "any")
        self.assertEqual(config.load_text(base.format("regulated")).gates["local_approvals"], "signed")
        self.assertEqual(config.load_text(base.format("solo") + '[gates]\nlocal_approvals = "signed"\n').gates["local_approvals"], "signed")
        loose = config.load_text(base.format("regulated") + '[gates]\nlocal_approvals = "any"\n')
        self.assertEqual(loose.gates["local_approvals"], "signed")
        self.assertTrue(any("local_approvals" in w for w in loose.warnings))
        self.assertEqual(load('[gates]\nlocal_approvals = "any"\n', '[gates]\nlocal_approvals = "signed"\n').gates["local_approvals"], "signed")

    def test_a_profile_that_forbids_standard_changes_ignores_the_gate_switch(self):
        cfg = config.load_text('aidd_version = "1.0.0"\nprofile = "regulated"\n[owners]\napprovers = ["@x"]\n[gates]\nstandard_changes = true\n')
        self.assertFalse(cfg.gates["standard_changes"])
        self.assertTrue(any("forbids standard changes" in w for w in cfg.warnings), cfg.warnings)

    def test_a_parents_deploy_gate_cannot_be_dropped_or_redefined(self):
        gate = '[[guard.gated_commands]]\nname = "{n}"\nmatch = ["deploy", "{env}"]\nrequires = "RELEASE_APPROVAL"\n'
        cfg = load(
            '[owners]\napprovers = ["@x"]\n' + gate.format(n="production deploy", env="staging") + gate.format(n="staging deploy", env="staging"),
            '[owners]\napprovers = ["@x"]\n' + gate.format(n="production deploy", env="production"),
        )
        gates = {g["name"]: g["match"] for g in cfg.get("guard", "gated_commands")}
        self.assertEqual(gates, {"production deploy": ["deploy", "production"], "staging deploy": ["deploy", "staging"]})
        self.assertTrue(any("cannot be replaced" in w for w in cfg.warnings), cfg.warnings)

    def test_a_child_cannot_choose_a_weaker_profile(self):
        with self.assertRaises(config.ConfigError):
            config.load_text(
                'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{ path = "p.toml" }]\n[owners]\napprovers = ["@x"]\n',
                prefetched={"p.toml": 'aidd_version = "1.0.0"\nprofile = "org"\n[owners]\napprovers = ["@x"]\n'},
            )


if __name__ == "__main__":
    unittest.main()
