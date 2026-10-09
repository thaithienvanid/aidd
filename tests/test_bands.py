"""Control bands: deterministic detection after release, tiered by how far a metric strays, written back as a draft Spec."""

import contextlib
import datetime as dt
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import bands, cli, model, workitems

BASE = [10.0, 11.0, 9.0, 10.0, 12.0, 8.0, 10.0, 11.0, 9.0, 10.0]  # mean 10, standard deviation about 1.1


def tier(values, **kw):
    return bands.assess(values, bands.Band("x", **kw)).tier


class TierTests(unittest.TestCase):
    def test_each_tier(self):
        self.assertEqual(tier(BASE + [10.0]), "ok")
        self.assertEqual(tier(BASE + [11.5]), "log")
        self.assertEqual(tier(BASE + [12.6]), "diagnose")
        self.assertEqual(tier(BASE + [14.0]), "propose")
        self.assertEqual(tier(BASE + [6.0]), "propose")  # both directions

    def test_slow_drift_is_diagnosed_without_a_spike(self):
        # Eight values in a row just above the mean: no single point is unusual, the run is.
        drift = BASE * 3 + [10.3] * 8
        reading = bands.assess(drift, bands.Band("x", window=30))
        self.assertEqual(reading.tier, "diagnose")
        self.assertTrue(any(r.startswith("4:") for r in reading.rules), reading.rules)

    def test_too_little_history_decides_nothing(self):
        reading = bands.assess([1.0, 50.0], bands.Band("x"))
        self.assertEqual(reading.tier, "ok")
        self.assertIn("not enough history", reading.note)

    def test_a_flat_baseline_flags_any_change(self):
        self.assertEqual(tier([5.0] * 10 + [5.0]), "ok")
        self.assertEqual(tier([5.0] * 10 + [5.1]), "propose")

    def test_thresholds_are_configurable(self):
        self.assertEqual(tier(BASE + [12.6], diagnose_sigma=3.0, propose_sigma=4.0), "log")

    def test_series_formats(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s"
            p.write_text('ts,value\n2026-09-01,1.5\n{"ts": "2026-09-02", "value": 2}\n# note\n3\n', encoding="utf-8")
            self.assertEqual(bands.load_series(p), [1.5, 2.0, 3.0])


@unittest.skipUnless(shutil.which("git"), "git is required")
class ObserveBandTests(unittest.TestCase):
    def test_a_breach_writes_a_draft_spec_that_validates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            (root / ".aidd").mkdir()
            (root / ".aidd/config.toml").write_text(
                'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@x"]\ndefault_team = "web"\n'
                '[observe]\n[[observe.bands]]\nmetric = "http_5xx_rate"\ndiagnose_sigma = 2\npropose_sigma = 3\n',
                encoding="utf-8",
            )
            (root / "series.txt").write_text("\n".join(str(v) for v in BASE + [14.0]) + "\n", encoding="utf-8")
            out = io.StringIO()
            with contextlib.chdir(root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = cli.main(["observe", "--band", "http_5xx_rate", "series.txt", "--write", "OBS-1"])
            self.assertEqual(code, 1, out.getvalue())
            text = (root / "specs/OBS-1.md").read_text(encoding="utf-8")
            self.assertIn("## Observed anomaly", text)
            self.assertIn("http_5xx_rate", text)
            _, _, errors = model.load_object(text, "OBS-1")
            self.assertEqual(errors, [])
            # Work nobody asked for: an agent suggested it, so `aidd list` puts its triage in front of a person first.
            data, _ = model.split_front_matter(text, "OBS-1")
            self.assertEqual(data["suggested_by"], "agent:sre")
            self.assertEqual(workitems.triage_state(data, set(), dt.date.today()), "needed")

    def test_no_breach_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
            (root / "series.txt").write_text("\n".join(str(v) for v in BASE + [10.0]) + "\n", encoding="utf-8")
            with contextlib.chdir(root), contextlib.redirect_stdout(io.StringIO()):
                code = cli.main(["observe", "--band", "x", "series.txt", "--write"])
            self.assertEqual(code, 0)
            self.assertFalse((root / "specs").exists())


if __name__ == "__main__":
    unittest.main()
