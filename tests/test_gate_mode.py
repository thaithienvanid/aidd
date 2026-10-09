"""Who decides whether the gate blocks, and what a child config may relax."""

import unittest

from helpers import ROOT, decide, example  # noqa: F401  (ROOT puts src on sys.path)

from aidd import config

PARENT = 'aidd_version = "1.0.0"\nprofile = "team"\nmode = "enforce"\n[owners]\napprovers = ["@org/leads"]\n'
CHILD = 'aidd_version = "1.0.0"\nprofile = "team"\nextends = [{ path = "p.toml" }]\n'


class EffectiveModeTests(unittest.TestCase):
    def test_the_base_config_wins(self):
        self.assertEqual(config.effective_mode("enforce", "advisory", input_trusted=True), "enforce")
        self.assertEqual(config.effective_mode("advisory", "enforce", input_trusted=False), "advisory")

    def test_a_trusted_ci_setting_applies_when_the_config_is_silent(self):
        self.assertEqual(config.effective_mode(None, "advisory", input_trusted=True), "advisory")

    def test_an_untrusted_ci_setting_never_relaxes_the_gate(self):
        self.assertEqual(config.effective_mode(None, "advisory", input_trusted=False), "enforce")
        self.assertEqual(config.effective_mode(None, None, input_trusted=True), "enforce")
        self.assertEqual(config.effective_mode(None, "nonsense", input_trusted=True), "enforce")


class ConfigModeTests(unittest.TestCase):
    def test_the_record_carries_the_base_config_mode(self):
        ctx = example("02-normal-feature")
        ctx["base_config"] = ctx["base_config"].replace('profile = "team"', 'profile = "team"\nmode = "advisory"', 1)
        self.assertEqual(decide(ctx).record.get("config_mode"), "advisory")

    def test_a_child_cannot_relax_a_parent_that_enforces(self):
        cfg = config.load_text(CHILD + 'mode = "advisory"\n', prefetched={"p.toml": PARENT})
        self.assertEqual(cfg.get("mode"), "enforce")
        self.assertTrue(any("mode" in w for w in cfg.warnings), cfg.warnings)


class OrgPresetTests(unittest.TestCase):
    PRESET = 'aidd_version = "1.0.0"\nprofile = "org"\n[owners]\napprovers = ["@org/leads"]\n'
    REPO = 'aidd_version = "1.0.0"\nprofile = "org"\n'

    def test_a_repository_cannot_loosen_an_org_preset(self):
        loose = self.REPO + 'disable_rules = ["baseline:auth"]\nscope_exempt_paths = ["src/"]\n'
        cfg = config.load_text(loose, root_preset=self.PRESET)
        self.assertFalse(cfg.get("disable_rules"))
        self.assertFalse(cfg.get("scope_exempt_paths"))
        self.assertEqual(sum("locked" in w for w in cfg.warnings), 2, cfg.warnings)

    def test_replacing_the_parents_approvers_warns(self):
        cfg = config.load_text(self.REPO + '[owners]\napprovers = ["@me"]\n', root_preset=self.PRESET)
        self.assertTrue(any("replaces the parent's approvers" in w for w in cfg.warnings), cfg.warnings)

    def test_extends_deeper_than_five_levels_is_refused(self):
        texts = {f"p{i}.toml": f'aidd_version = "1.0.0"\nprofile = "team"\nextends = [{{ path = "p{i + 1}.toml" }}]\n' for i in range(7)}
        with self.assertRaises(config.ConfigError):
            config.load_text(texts["p0.toml"], prefetched=texts)


if __name__ == "__main__":
    unittest.main()
