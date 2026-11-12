"""A pool in `owners.specialists` that no risk dimension asks for is warned about, as `--specialist` refuses it: `aidd
validate` and `aidd doctor` name it, with the closest pool when it is a typo."""

import tempfile
import unittest
from pathlib import Path

from helpers import run_cli

from aidd import config
from aidd.setup import doctor_checks

HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@org/leads"]\n  specialists:\n'
POOLS = {pool: ["@org/x"] for pool in sorted(set(config.POOL_OF.values()))}


def text(*pools: str) -> str:
    return HEAD + "".join(f'    {p}: ["@org/x"]\n' for p in pools)


class PoolWarningTests(unittest.TestCase):
    def pool_warnings(self, cfg: config.Config) -> list[str]:
        return [w for w in cfg.warnings if "owners.specialists" in w]

    def test_a_typo_names_the_closest_pool(self):
        found = self.pool_warnings(config.load_text(text("secuirty")))
        self.assertEqual(len(found), 1, found)
        self.assertIn("'secuirty' is not a pool aidd asks for a risk dimension", found[0])
        self.assertIn("Did you mean `security`?", found[0])

    def test_a_name_that_is_no_typo_lists_the_pools(self):
        found = self.pool_warnings(config.load_text(text("zzz")))
        self.assertEqual(len(found), 1, found)
        self.assertIn("The pools: " + ", ".join(POOLS) + ".", found[0])

    def test_every_pool_a_dimension_asks_is_quiet(self):
        self.assertEqual(self.pool_warnings(config.load_text(text(*POOLS))), [])

    def test_a_parents_pool_is_warned_once_and_names_the_parents_file(self):
        child = HEAD.replace("  specialists:\n", "") + "extends: [{path: p.yaml}]\n"
        cfg = config.load_text(child, prefetched={"p.yaml": text("secuirty")})
        found = self.pool_warnings(cfg)
        self.assertEqual(len(found), 1, cfg.warnings)
        self.assertTrue(found[0].startswith("p.yaml: "), found)

    def test_a_pool_named_for_an_area_is_an_expert_pool_and_stays_quiet(self):
        area = "risks:\n  areas:\n    clinical: {paths: ['src/dosing/**'], route: major}\n"
        self.assertEqual(self.pool_warnings(config.load_text(text("clinical") + area)), [])
        self.assertEqual(len(self.pool_warnings(config.load_text(text("clinical")))), 1, "no area has the name")
        self.assertEqual(self.pool_warnings(config.load_text(text("infra"))), [], "a built-in area's name counts too")

    def test_validate_and_doctor_both_say_so(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".aidd").mkdir()
            path = root / ".aidd" / "config.yaml"
            path.write_text(text("secuirty"), encoding="utf-8")
            _, out = run_cli("validate", str(path))
            self.assertIn("Did you mean `security`?", out)
            said = [msg for level, msg in doctor_checks.doctor(root) if level == "warning" and "owners.specialists" in msg]
        self.assertEqual(len(said), 1, said)


if __name__ == "__main__":
    unittest.main()
