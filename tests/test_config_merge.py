"""How a child config merges with its parents: lists add, owner rules combine, and nothing loosens silently."""

import unittest

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import config

HEAD = 'aidd_version: "1.0.0"\nprofile: team\n'


def load(child: str, parent: str):
    return config.load_text(HEAD + "extends: [{path: p.yaml}]\n" + child, prefetched={"p.yaml": HEAD + parent})


class ConfigMergeTests(unittest.TestCase):
    def test_owner_areas_from_parent_and_child_both_apply(self):
        cfg = load(
            'owners:\n  approvers: ["@x"]\n  paths:\n    - paths: [web/]\n      approvers: ["@web"]\n',
            'owners:\n  approvers: ["@x"]\n  paths:\n    - paths: [infra/]\n      approvers: ["@platform"]\n',
        )
        self.assertEqual(sorted(e["paths"][0] for e in cfg.get("owners", "paths")), ["infra/", "web/"])

    def test_codeowners_stays_on_once_a_parent_turns_it_on(self):
        cfg = load('owners:\n  approvers: ["@x"]\n  codeowners: false\n', 'owners:\n  approvers: ["@x"]\n  codeowners: true\n')
        self.assertTrue(cfg.get("owners", "codeowners"))

    def test_local_approvals_only_tighten_to_signed(self):
        base = 'aidd_version: "1.0.0"\nprofile: "{}"\nowners:\n  approvers: ["@x"]\n'
        self.assertEqual(config.load_text(base.format("team")).gates["local_approvals"], "any")
        self.assertEqual(config.load_text(base.format("audited")).gates["local_approvals"], "signed")
        self.assertEqual(config.load_text(base.format("solo") + "gates:\n  local_approvals: signed\n").gates["local_approvals"], "signed")
        loose = config.load_text(base.format("audited") + "gates:\n  local_approvals: any\n")
        self.assertEqual(loose.gates["local_approvals"], "signed")
        self.assertTrue(any("local_approvals" in w for w in loose.warnings))
        self.assertEqual(load("gates:\n  local_approvals: any\n", "gates:\n  local_approvals: signed\n").gates["local_approvals"], "signed")

    def test_a_profile_that_forbids_standard_changes_ignores_the_gate_switch(self):
        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: audited\nowners:\n  approvers: ["@x"]\ngates:\n  standard_changes: true\n')
        self.assertFalse(cfg.gates["standard_changes"])
        self.assertTrue(any("forbids standard changes" in w for w in cfg.warnings), cfg.warnings)

    def test_a_parents_deploy_gate_cannot_be_dropped_or_redefined(self):
        gate = '    - name: "{n}"\n      match: [deploy, "{env}"]\n      requires: RELEASE_APPROVAL\n'
        held = "guard:\n  held_commands:\n"
        cfg = load(
            'owners:\n  approvers: ["@x"]\n' + held + gate.format(n="production deploy", env="staging") + gate.format(n="staging deploy", env="staging"),
            'owners:\n  approvers: ["@x"]\n' + held + gate.format(n="production deploy", env="production"),
        )
        gates = {g["name"]: g["match"] for g in cfg.get("guard", "held_commands")}
        self.assertEqual(gates, {"production deploy": ["deploy", "production"], "staging deploy": ["deploy", "staging"]})
        self.assertTrue(any("cannot be replaced" in w for w in cfg.warnings), cfg.warnings)

    def test_a_child_cannot_choose_a_weaker_profile(self):
        with self.assertRaises(config.ConfigError):
            config.load_text(
                'aidd_version: "1.0.0"\nprofile: solo\nextends: [{path: p.yaml}]\nowners:\n  approvers: ["@x"]\n',
                prefetched={"p.yaml": 'aidd_version: "1.0.0"\nprofile: org\nowners:\n  approvers: ["@x"]\n'},
            )


if __name__ == "__main__":
    unittest.main()
