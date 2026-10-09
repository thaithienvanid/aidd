"""Names aidd used before 1.0: 1.0.0 is the first release, so none of them is an alias, except the two adopters'
setups already call (PublicNameTests). Each old command, flag, config
key, value, and front-matter key is refused as unknown, and none appears in any help, table, or generated text."""

import contextlib
import io
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import cli, config, docs, mcp, model, repo


def parse(*argv) -> tuple[int | str | None, str]:
    """The exit code argparse stops with, and what it printed on stderr."""
    err = io.StringIO()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err), contextlib.suppress(SystemExit):
        try:
            cli.build_parser().parse_args(list(argv))
        except SystemExit as stop:
            return stop.code, err.getvalue()
    return 0, err.getvalue()


class ConfigNamesTests(unittest.TestCase):
    OLD = (
        'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@a"]\n[owners.reviewers]\nsecurity = ["@sec"]\n'
        '[[risk_rules]]\nname = "payments"\npaths = ["src/pay/**"]\nroute = "major"\nreviewers = ["finance"]\n'
        '[hooks]\nlevel = "standard"\n'
    )

    def test_old_keys_and_values_are_errors(self):
        with self.assertRaises(config.ConfigError) as err:
            config.load_text(self.OLD)
        text = str(err.exception)
        self.assertIn("$.owners: unknown field 'reviewers'", text)
        self.assertIn("$.risk_rules[0]: unknown field 'reviewers'", text)
        self.assertIn('$.hooks.level: must be one of minimal, balanced, strict; got "standard"', text)

    def test_validate_reports_them_as_errors(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".aidd" / "config.toml"
            path.parent.mkdir()
            path.write_text(self.OLD, encoding="utf-8")
            found = repo.validate_file(path)
        self.assertTrue(found and not any(e.startswith("warning: ") for e in found), found)
        self.assertEqual(len(found), 3, found)


class FrontMatterNamesTests(unittest.TestCase):
    SPEC = '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "S-1"\ntitle = "t"\nproposed_by = "agent:sre"\n+++\n'

    def test_proposed_by_is_an_unknown_key(self):
        data, _ = model.split_front_matter(self.SPEC, "S-1")
        self.assertEqual(data.get("proposed_by"), "agent:sre")
        self.assertNotIn("suggested_by", data)
        _, _, errors = model.load_object(self.SPEC, "S-1")
        self.assertTrue(any("proposed_by" in e and not e.startswith("warning: ") for e in errors), errors)
        self.assertFalse(hasattr(model, "RENAMED_KEYS"))


class CliNamesTests(unittest.TestCase):
    def test_old_commands_and_flags_are_refused(self):
        for argv in (
            ("next",),
            ("watch", "series.txt", "--metric", "x"),
            ("init", "--reviewer", "security=@a"),
            ("hash", "specs/S-1.md", "--comment"),
            ("hash", "specs/S-1.md", "--digest"),
            ("metrics", "e.jsonl", "--propose"),
            ("metrics", "e.jsonl", "--by", "owner"),
        ):
            code, err = parse(*argv)
            self.assertEqual(code, 2, argv)
            self.assertNotIn(" is now ", err, argv)

    def test_the_new_names_work(self):
        self.assertEqual(parse("init", "--specialist", "security=@a")[0], 0)
        self.assertEqual(parse("hash", "specs/S-1.md", "--line", "--summary")[0], 0)
        self.assertEqual(parse("metrics", "e.jsonl", "--suggest-standard-changes", "--by", "org")[0], 0)

    def test_no_old_name_is_in_the_help_or_the_generated_table(self):
        overview = cli.build_parser().format_help()
        table = docs.cli_table()
        for old in ("next", "watch", "change", "verify", "export"):
            self.assertNotIn(f"\n  {old} ", overview, old)
            self.assertNotIn(f"| `{old}`", table, old)
        for flag in ("--reviewer", "--comment", "--digest", "--propose"):
            self.assertNotIn(f"`{flag}`", table, flag)
            self.assertNotIn(f"`{flag} ", table, flag)
        self.assertIn("| `record verify`", table)
        self.assertIn("| `record export`", table)
        self.assertFalse(hasattr(mcp, "RENAMED"))

    def test_observe_keeps_the_spec_and_the_band_flags_apart(self):
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cli.main(["observe", "specs/S-1.md", "--baseline", "5"]), 2)
            self.assertEqual(cli.main(["observe", "--band", "x", "series.txt", "--window", "1h"]), 2)
            self.assertEqual(cli.main(["observe", "specs/S-1.md", "--write", "OBS-1"]), 2)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_a_missing_proposal_file_is_named(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=d, check=True)
            err = io.StringIO()
            with contextlib.chdir(d), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                code = cli.main(["proposal", "matrix", "proposals/NOPE/proposal.md"])
        self.assertEqual((code, err.getvalue()), (2, "aidd: proposals/NOPE/proposal.md: no such file\n"))


if __name__ == "__main__":
    unittest.main()


class PublicNameTests(unittest.TestCase):
    """The public names: each old name is refused, the new one works, and only two aliases stay, because
    adopters' setups already call them (`aidd hook pre-edit`, the `/aidd approve <sha>` comment)."""

    BASE = 'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@a"]\n'

    def test_old_config_names_are_errors_and_the_new_ones_load(self):
        old = {
            '[[guard.gated_commands]]\nname = "d"\nmatch = ["deploy"]\nrequires = "OK"\n': "gated_commands",
            '[hooks]\nlevel = "default"\n': '$.hooks.level: must be one of minimal, balanced, strict; got "default"',
            '[agents]\ncost_cap_per_change = { amount = 5, currency = "USD" }\n': "cost_cap_per_change",
            "[targets]\nflow_efficiency_min = 0.4\n": "flow_efficiency_min",
            "[targets]\nlead_time_hours = 24\n": "lead_time_hours",
            "[targets]\nchange_fail_rate = 0.1\n": "change_fail_rate",
            "[targets]\nrecovery_days = 1\n": "recovery_days",
            "[targets]\nfirst_feedback_minutes = 30\n": "first_feedback_minutes",
            "[targets]\ncost_per_change = 5\n": "cost_per_change",
            "[targets]\nmax_cost_per_change = 5\n": "max_cost_per_change",  # the [agents] cap is per change; this is the mean
            '[project.budget]\ninfra_monthly_max = 50\ncurrency = "EUR"\n': "infra_monthly_max",
        }
        for extra, named in old.items():
            with self.subTest(extra=extra), self.assertRaises(config.ConfigError) as err:
                config.load_text(self.BASE + extra)
            self.assertIn(named, str(err.exception))
        for extra in (
            '[[guard.held_commands]]\nname = "d"\nmatch = ["deploy"]\nrequires = "OK"\n',
            '[hooks]\nlevel = "balanced"\n',
            '[agents]\nmax_cost_per_change = { amount = 5, currency = "USD" }\n',
            "[targets]\nmin_flow_efficiency = 0.4\n",
            "[targets]\nmin_deployments_per_week = 10\nmax_lead_time_hours = 24\nmax_change_fail_rate = 0.1\nmax_recovery_days = 1\n"
            "max_rework_rate = 0.05\nmax_first_feedback_minutes = 30\nmax_approval_wait_p90_minutes = 1440\nmax_mean_cost_per_change = 5\n",
            '[project.budget]\nmax_infra_per_month = 50\ncurrency = "EUR"\n',
        ):
            with self.subTest(extra=extra):
                config.load_text(self.BASE + extra)

    def test_old_spec_values_are_refused(self):
        head = '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "S-1"\ntitle = "t"\n'
        for extra, named in (('priority = "normal"\n', "priority"), ('[outcome]\nreleased_at = "2026-09-01"\n', "released_at")):
            _, _, errors = model.load_object(head + extra + "+++\n", "S-1")
            self.assertTrue(any(named in e and not e.startswith("warning: ") for e in errors), (extra, errors))
        for extra in ('priority = "medium"\n', "[outcome]\nreleased_on = 2026-09-01\n"):
            _, _, errors = model.load_object(head + extra + "+++\n", "S-1")
            self.assertFalse(any("priority" in e or "released" in e for e in errors), (extra, errors))

    def test_old_flags_and_kinds_are_refused(self):
        for argv in (
            ("doctor", "--autonomous"),
            ("metrics", "--autonomy", "--runs"),
            ("autopilot", "start", "--scope", "SPEC-1"),
            ("new", "ui", "cart"),
        ):
            self.assertEqual(parse(*argv)[0], 2, argv)
        for argv in (
            ("doctor", "--autopilot"),
            ("metrics", "--autopilot"),
            ("autopilot", "start", "--work", "SPEC-1"),
            ("new", "design-spec", "cart", "--prototype"),
            ("hook", "pre-tool"),
            ("hook", "pre-edit"),  # the kept alias
        ):
            self.assertEqual(parse(*argv)[0], 0, argv)

    def test_the_conventions_are_written_down(self):
        text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        section = text.split("## Naming", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(len(re.findall(r"^\d+\. ", section, re.M)), 12, section)
        for must in ("`max_` or `min_`", "`_on`", "`schema_version`", "`<group>/<topic>`", "`AIDD_<NOUN>`", "low, medium, and high"):
            self.assertIn(must, section, must)
        self.assertIn("**Experimental names.**", text)
        self.assertIn("`/aidd-team:autopilot`) may change in a minor release", text)
        self.assertIn("`aidd hook pre-edit`", text)
