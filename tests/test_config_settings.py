"""What a person can set, found without the docs: the schema an editor reads through the config's first line, and
`aidd config`, which lists every setting with its value here, where it comes from, and what it does."""

import json
import re
import shutil
import unittest

from helpers import ROOT, adopted_repo, run_cli

from aidd import __version__, config
from aidd.kernel import documents, json_schema
from aidd.setup import upgrading


class EditorSchemaTests(unittest.TestCase):
    def test_the_editor_schema_is_one_file_that_validates_as_the_split_schema_does(self):
        bundled = json.loads((ROOT / config.EDITOR_SCHEMA).read_text(encoding="utf-8"))
        self.assertEqual(bundled, json_schema.bundled("config.schema.json"))  # generated, never hand-edited
        refs = re.findall(r'"\$ref": "([^"]+)"', json.dumps(bundled))
        self.assertTrue(refs)
        self.assertEqual([r for r in refs if not r.startswith("#/$defs/")], [])  # nothing outside the file
        self.assertEqual([r for r in refs if r.removeprefix("#/$defs/") not in bundled["$defs"]], [])
        good = documents.parse_yaml((ROOT / config.CONFIG_PATH).read_text(encoding="utf-8"), config.CONFIG_PATH)
        bad = {**good, "mode": "loose"}
        for case in (good, bad):
            errs: list[str] = []
            json_schema._check(case, bundled, "$", bundled, errs)
            self.assertEqual(bool(errs), bool(json_schema.validate(case, "config.schema.json")), case.get("mode"))

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_init_names_the_schema_of_this_release_and_upgrade_moves_it(self):
        with adopted_repo("team") as root:
            path = root / config.CONFIG_PATH
            first = path.read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(first, config.schema_modeline(__version__))
            self.assertIn(f"/v{__version__}/{config.EDITOR_SCHEMA}", first)
            path.write_text(path.read_text(encoding="utf-8").replace(f"/v{__version__}/", "/v0.9.0/", 1), encoding="utf-8")
            upgrading.upgrade(root, yes=True)
            self.assertEqual(path.read_text(encoding="utf-8").splitlines()[0], config.schema_modeline(__version__))


@unittest.skipUnless(shutil.which("git"), "git is required")
class SettingsTests(unittest.TestCase):
    def test_the_settings_this_config_sets_then_the_ones_to_consider_then_where_the_rest_are(self):
        from aidd.config import settings_view

        with adopted_repo("team", enforce=False) as root:
            own = documents.parse_yaml((root / config.CONFIG_PATH).read_text(encoding="utf-8"), config.CONFIG_PATH)
            code, out = run_cli("config")
        self.assertEqual(code, 0, out)
        mine, _, offered = out.partition("\nYou may want to set:\n")
        mine_keys = [line.split()[0] for line in mine.splitlines()[2:] if line]
        nested = [f"{t}.{k}" for t in ("gates", "limits") for k in own.get(t) or {}]
        # What the file sets, and nothing it leaves to the profile or the default.
        self.assertEqual(sorted(mine_keys), sorted([k for k in own if k not in ("gates", "limits")] + nested))
        self.assertIn("this config", out.splitlines()[2])
        offered_rows = [line for line in offered.splitlines() if line and not line.startswith(("All settings", "Set one"))]
        offered_keys = [line.split()[0] for line in offered_rows]
        self.assertEqual(offered_keys, [k for k in settings_view.SUGGESTED if k not in own])
        self.assertLessEqual(len(offered_keys), 6)
        self.assertIn("profile team", next(line for line in offered_rows if line.startswith("mode ")))
        self.assertIn("All settings: `aidd config --all`.", out)
        self.assertLess(len(out.splitlines()), 30)

    def test_every_setting_with_its_value_its_source_and_what_it_does(self):
        with adopted_repo("team"):
            code, out = run_cli("config", "--all")
        self.assertEqual(code, 0, out)
        rows = {line.split()[0]: line for line in out.splitlines()[2:] if line and not line.startswith("`")}
        self.assertIn("this config", rows["profile"])
        self.assertIn("enforce", rows["mode"])  # these test repositories set mode: enforce
        self.assertIn("profile team", rows["gates.approvals"])
        self.assertIn("the default", rows["specs_dir"])
        schema = json.loads((ROOT / "schemas" / "config.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(k for k in rows if "." not in k), sorted(k for k in schema["properties"] if k not in ("gates", "limits"))
        )  # every top-level key, from the schema

    def test_a_gate_says_which_config_set_it_and_a_shared_key_its_values(self):
        from aidd.config import settings_view

        cfg = config.load_text(f'aidd_version: "{__version__}"\nprofile: team\ngates:\n  red_green: warn\n')
        rows = {r["key"]: r for r in settings_view.settings(cfg, {"profile": "team", "gates": {"red_green": "warn"}})}
        self.assertIn("is looser, so it is ignored", rows["gates.red_green"]["source"])  # team requires red-then-green
        self.assertEqual(rows["profile"]["allowed"], ["solo", "team", "org", "audited"])
        self.assertTrue(rows["aidd_version"]["what"])

    def test_a_key_in_the_wrong_place_is_unknown(self):
        from aidd.config import settings_view

        head = f'aidd_version: "{__version__}"\nprofile: team\n'
        for old, _new_place in (
            ("gates:\n  max_branch_days: 2\n", "`limits.max_branch_age_days`"),
            ("gates:\n  escalate_after_minutes: 60\n", "`limits.escalate_after_minutes`"),
        ):
            with self.subTest(old=old), self.assertRaises(config.ConfigError) as caught:
                config.load_text(head + old)
            self.assertIn(f"unknown field {old.split()[1][:-1]!r}", str(caught.exception))
        # The same leaf under another parent is a plain unknown field: the hint names one path only.
        with self.assertRaises(config.ConfigError) as caught:
            config.load_text(head + "hooks:\n  max_branch_age_days: 2\n")
        self.assertNotIn("moved it", str(caught.exception))
        cfg = config.load_text(head + "limits:\n  max_branch_age_days: 1\n")
        self.assertEqual((cfg.limits["max_branch_age_days"], cfg.limits["max_open_per_approver"]), (1, 3))  # its own, and the profile's
        rows = {r["key"]: r for r in settings_view.settings(cfg, {"limits": {"max_branch_age_days": 1}})}
        self.assertEqual((rows["limits.max_branch_age_days"]["source"], rows["limits.max_open_per_approver"]["source"]), ("this config", "profile team"))

    def test_one_setting_in_full_and_an_unknown_one_says_where_to_look(self):
        with adopted_repo("team", enforce=False):
            code, out = run_cli("config", "mode")
            self.assertEqual(code, 0, out)
            self.assertTrue(out.startswith('mode: "advisory" (from profile team)'), out)
            self.assertIn('allowed: "enforce", "advisory"', out)
            code, out = run_cli("config", "gates")
            self.assertEqual(code, 0, out)
            self.assertIn("gates.approvals: ", out)
            code, out = run_cli("config", "nope")
            self.assertEqual(code, 2, out)
            self.assertIn("`aidd config --all` lists them all", out)

    def test_the_value_is_the_one_the_gate_reads(self):
        with adopted_repo("team") as root:
            path = root / config.CONFIG_PATH
            path.write_text(path.read_text(encoding="utf-8") + "\nlocale: vi\n", encoding="utf-8")
            code, out = run_cli("config", "locale")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith('locale: "vi" (from this config)'), out)


if __name__ == "__main__":
    unittest.main()
