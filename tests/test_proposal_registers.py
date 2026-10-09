"""What a proposal promises, and the scope decisions made around it.

`estimate.parts` breaks the range down, in the total's unit, each part with a closed `kind`. `aidd validate` fails when
a part's low <= likely <= high fails, or when the PERT roll-up of the parts, sum((low + 4 x likely + high) / 6), falls
outside the total's low to high. The claims register lists each claim with its evidence and where the evidence was seen;
`aidd validate` warns on a claim with no evidence, and on an absolute word in a claim seen only in simulation. Parts and
claims are part of the promise, so the proposal hash covers them. The scope decisions log is history a person writes:
the hash leaves it out, `aidd proposal convert` copies it to the Initiative, and `aidd digest` reports each reversal (an
entry with `replaces`) dated in its window.
"""

import datetime as dt
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import test_status_reports as reports
from helpers import ROOT, git

from aidd import model, proposal, repo, resources, rollup, schema

ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"

BASE = """+++
aidd_version = "1.0.0"
kind = "proposal"
id = "PROP-5"
title = "Dealer portal"
audience = "client"
addressee = "Acme Corp"
goal = "Dealers track their orders"
{top}
[[needs]]
id = "N-1"
need = "Track orders"
answer = "met"

[estimate]
unit = "person-days"
low = 40
likely = 55
high = 90
basis = "three comparable portals"
{parts}
{tail}+++

## Summary

We build the dealer portal.
"""

PARTS = """
[[estimate.parts]]
id = "P-1"
name = "Order tracking screens"
low = 20
likely = 30
high = 50
kind = "build"

[[estimate.parts]]
id = "P-2"
name = "ERP export"
low = 10
likely = 15
high = 25
kind = "integration"

[[estimate.parts]]
id = "P-3"
name = "Client reviews and waiting"
low = 5
likely = 8
high = 15
kind = "human"
"""

CLAIMS = """
[[claims]]
id = "C-1"
text = "Order export already runs nightly"
evidence = ["src/orders/export.py:42"]
scope = "code"
"""

DECISIONS = """
[[decisions]]
id = "D-1"
decision = "Card payments only in the first release"
by = "@lead"
on = "2026-09-02"
reason = "Invoice payments need the ERP export first"

[[decisions]]
id = "D-2"
decision = "Card and invoice payments in the first release"
by = "@lead"
on = "2026-09-12"
replaces = "D-1"
reason = "Acme confirmed the ERP export date"
"""


def text(*, top: str = "", parts: str = PARTS, tail: str = "") -> str:
    return BASE.format(top=top, parts=parts, tail=tail)


def errors(t: str) -> list[str]:
    return model.load_object(t, "p.md")[2]


def hard(errs: list[str]) -> list[str]:
    return [e for e in errs if not e.startswith("warning: ")]


def warnings(errs: list[str]) -> list[str]:
    return [e for e in errs if e.startswith("warning: ")]


class EstimatePartsTests(unittest.TestCase):
    def test_parts_whose_roll_up_falls_in_the_range_pass(self):
        # PERT: (20 + 120 + 50) / 6 + (10 + 60 + 25) / 6 + (5 + 32 + 15) / 6 = 31.67 + 15.83 + 8.67 = 56.17, inside 40 to 90.
        self.assertEqual(errors(text()), [])
        self.assertEqual(errors(text(parts="")), [], "parts are optional")

    def test_a_part_out_of_order_fails_and_names_its_numbers(self):
        errs = errors(text(parts=PARTS.replace("low = 10\nlikely = 15", "low = 18\nlikely = 15")))
        self.assertIn("p.md: estimate.parts P-2: low <= likely <= high must hold (low 18, likely 15, high 25)", errs)

    def test_a_roll_up_outside_the_total_range_fails_and_names_its_numbers(self):
        big = PARTS.replace("low = 20\nlikely = 30\nhigh = 50", "low = 60\nlikely = 80\nhigh = 120")
        # (60 + 320 + 120) / 6 = 83.33; with 15.83 and 8.67 the roll-up is 107.83, above 90.
        (err,) = hard(errors(text(parts=big)))
        self.assertEqual(
            err, "p.md: estimate.parts: the PERT roll-up of the parts is 107.83 person-days, outside the total's range of 40 to 90; fix the parts or the range"
        )
        small = PARTS.replace("low = 20\nlikely = 30\nhigh = 50", "low = 1\nlikely = 2\nhigh = 3")
        (err,) = hard(errors(text(parts=small)))
        self.assertIn("is 26.5 person-days, outside the total's range of 40 to 90", err)

    def test_money_sized_parts_that_match_the_total_pass_and_messages_show_every_digit(self):
        # Floating-point error grows with the numbers: a fixed 1e-9 tolerance failed totals exactly equal to the parts.
        total = 'unit = "person-days"\nlow = 40\nlikely = 55\nhigh = 90\n'
        money = 'unit = "EUR"\nlow = 7564239.24\nlikely = 7564239.24\nhigh = 7564239.24\n'
        parts = "".join(
            f'\n[[estimate.parts]]\nid = "{pid}"\nname = "Part"\nlow = {n}\nlikely = {n}\nhigh = {n}\nkind = "build"\n'
            for pid, n in (("P-1", "3210817.23"), ("P-2", "4353422.01"))
        )
        exact = text(parts=parts).replace(total, money)
        self.assertEqual(errors(exact), [])
        (err,) = hard(errors(exact.replace(money, 'unit = "EUR"\nlow = 1234567\nlikely = 1234567\nhigh = 1234567.5\n')))
        self.assertIn("is 7564239.24 EUR, outside the total's range of 1234567 to 1234567.5", err)

    def test_the_kind_is_a_closed_list_and_a_part_has_no_unit_of_its_own(self):
        sch = resources.load_json("proposal.schema.json")["properties"]["estimate"]["properties"]["parts"]["items"]
        self.assertEqual(sch["properties"]["kind"]["enum"], ["build", "port", "integration", "research", "human"])
        self.assertEqual(sorted(sch["required"]), ["high", "id", "kind", "likely", "low", "name"])
        self.assertTrue(hard(errors(text(parts=PARTS.replace('kind = "human"', 'kind = "waiting"')))))
        self.assertTrue(hard(errors(text(parts=PARTS.replace('kind = "build"', 'kind = "build"\nunit = "hours"')))))

    def test_part_ids_are_unique(self):
        errs = errors(text(parts=PARTS.replace('id = "P-3"', 'id = "P-1"')))
        self.assertIn("p.md: estimate.parts: ids must be unique (P-1)", errs)

    def test_the_parts_are_part_of_the_promise(self):
        h = model.proposal_hash(text())
        self.assertNotEqual(model.proposal_hash(text(parts=PARTS.replace("likely = 8", "likely = 9"))), h)
        self.assertNotEqual(model.proposal_hash(text(parts=PARTS.replace('kind = "human"', 'kind = "research"'))), h)


class ClaimsTests(unittest.TestCase):
    def test_a_claim_with_evidence_and_a_scope_passes(self):
        self.assertEqual(errors(text(tail=CLAIMS)), [])
        sch = resources.load_json("proposal.schema.json")["properties"]["claims"]["items"]
        self.assertEqual(sch["properties"]["scope"]["enum"], ["simulated", "real-device", "production", "code", "external"])
        self.assertTrue(hard(errors(text(tail=CLAIMS.replace('scope = "code"', 'scope = "demo"')))))

    def test_a_claim_with_no_evidence_is_a_warning(self):
        for evidence in ('evidence = ["src/orders/export.py:42"]\n', ""):
            with self.subTest(evidence=evidence):
                changed = CLAIMS.replace('evidence = ["src/orders/export.py:42"]\n', evidence.replace('["src/orders/export.py:42"]', "[]"))
                self.assertEqual(
                    errors(text(tail=changed)),
                    ["warning: p.md: claims C-1 has no evidence; add a file:line, a test, or a recording, or take the claim out"],
                )

    def test_an_absolute_word_in_a_simulated_claim_is_a_warning(self):
        for words in ("every", "always", "never", "same", "already works", "all"):
            with self.subTest(words=words):
                claim = CLAIMS.replace("Order export already runs nightly", f"Sync {words.upper() if words == 'all' else words} works on the phone").replace(
                    'scope = "code"', 'scope = "simulated"'
                )
                (warn,) = errors(text(tail=claim))
                self.assertEqual(
                    warn,
                    f'warning: p.md: claims C-1 says "{words.upper() if words == "all" else words}" but was seen only in simulation; '
                    "narrow the words, or add evidence from a real device or production",
                )
                self.assertEqual(errors(text(tail=claim.replace('scope = "simulated"', 'scope = "real-device"'))), [])
        # Whole words only, and a hyphen joins a word: none of these is absolute.
        for words in ("Sync allows retries", "Same-day delivery", "An all-in price", "An always-on sync", "Retries never-ending queues"):
            with self.subTest(words=words):
                claim = CLAIMS.replace("Order export already runs nightly", words).replace('scope = "code"', 'scope = "simulated"')
                self.assertEqual(errors(text(tail=claim)), [])
        # A word that starts with "every", "none", "guaranteed", and "100%" are absolute.
        for words, found in (
            ("Sync works for everyone", "everyone"),
            ("None of the orders is lost", "None"),
            ("Delivery is guaranteed", "guaranteed"),
            ("Sync is 100% reliable", "100%"),
        ):
            with self.subTest(words=words):
                claim = CLAIMS.replace("Order export already runs nightly", words).replace('scope = "code"', 'scope = "simulated"')
                self.assertEqual(
                    warnings(errors(text(tail=claim))),
                    [
                        f'warning: p.md: claims C-1 says "{found}" but was seen only in simulation; narrow the words, or add evidence from a real device or production'
                    ],
                )

    def test_claim_ids_are_unique(self):
        errs = errors(text(tail=CLAIMS + CLAIMS))
        self.assertIn("p.md: claims: ids must be unique (C-1)", errs)

    def test_the_claims_are_part_of_the_promise(self):
        h = model.proposal_hash(text(tail=CLAIMS))
        self.assertNotEqual(model.proposal_hash(text(tail=CLAIMS.replace("nightly", "hourly"))), h)
        self.assertNotEqual(model.proposal_hash(text(tail=CLAIMS.replace('scope = "code"', 'scope = "production"'))), h)
        self.assertNotEqual(model.proposal_hash(text(tail=CLAIMS.replace(":42", ":43"))), h)


class DecisionsTests(unittest.TestCase):
    def test_a_decision_records_who_when_and_why(self):
        self.assertEqual(errors(text(tail=DECISIONS)), [])
        item = resources.load_json("proposal.schema.json")["$defs"]["decision"]
        self.assertEqual(sorted(item["required"]), ["by", "decision", "id", "on", "reason"])
        self.assertEqual(item["properties"]["by"]["$ref"], "urn:aidd:1:common#/$defs/identity")
        self.assertTrue(hard(errors(text(tail=DECISIONS.replace('reason = "Invoice payments need the ERP export first"\n', "")))))
        self.assertTrue(hard(errors(text(tail=DECISIONS.replace('on = "2026-09-02"', 'on = "early September"')))))
        self.assertTrue(hard(errors(text(tail=DECISIONS.replace('by = "@lead"', 'by = "the lead"', 1)))))

    def test_a_reversal_names_an_earlier_entry_of_the_log(self):
        errs = errors(text(tail=DECISIONS.replace('replaces = "D-1"', 'replaces = "D-9"')))
        self.assertEqual(hard(errs), ["p.md: decisions D-2 replaces D-9, which is not an earlier entry of the log"])
        errs = errors(text(tail=DECISIONS.replace('replaces = "D-1"', 'replaces = "D-2"')))
        self.assertEqual(hard(errs), ["p.md: decisions D-2 replaces D-2, which is not an earlier entry of the log"])
        self.assertIn("p.md: decisions: ids must be unique (D-1)", errors(text(tail=DECISIONS.replace('id = "D-2"', 'id = "D-1"'))))
        # A reversal comes after what it reverses: in the log and in time. The same day is fine.
        errs = errors(text(tail=DECISIONS.replace('on = "2026-09-12"', 'on = "2026-09-01"')))
        self.assertEqual(hard(errs), ["p.md: decisions D-2 replaces D-1 but is dated 2026-09-01, before D-1 (2026-09-02)"])
        self.assertEqual(errors(text(tail=DECISIONS.replace('on = "2026-09-12"', 'on = "2026-09-02"'))), [])

    def test_the_hash_leaves_the_log_out(self):
        h = model.proposal_hash(text())
        self.assertEqual(model.proposal_hash(text(tail=DECISIONS)), h)
        self.assertEqual(model.proposal_hash(text(tail=DECISIONS.replace("first release", "second release"))), h)
        self.assertIn("decisions", model.PROPOSAL_UNSIGNED_KEYS)

    def test_an_agent_account_cannot_decide_scope(self):
        for kind, rel, body in (
            ("proposal", "proposals/PROP-5/proposal.md", text(tail=DECISIONS)),
            (
                "initiative",
                "specs/INIT-1.md",
                '+++\naidd_version = "1.0.0"\nkind = "initiative"\nid = "INIT-1"\ntitle = "Portal"\ngoal = "Dealers track their orders"\n'
                + DECISIONS
                + "+++\n",
            ),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / ".aidd").mkdir()
                (root / ".aidd" / "config.toml").write_text(
                    'aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@lead"]\n[identities]\nbots = ["claude[bot]"]\n', encoding="utf-8"
                )
                path = root / rel
                path.parent.mkdir(parents=True)
                path.write_text(body, encoding="utf-8")
                errs, _ = repo.check_repo(root)
                self.assertFalse([e for e in errs if "decisions" in e], errs)
                path.write_text(body.replace('by = "@lead"\non = "2026-09-12"', 'by = "claude[bot]"\non = "2026-09-12"'), encoding="utf-8")
                errs, _ = repo.check_repo(root)
                self.assertIn(f"{rel}: decisions D-2.by claude[bot] is an agent account; a person decides scope", errs)
                path.write_text(body.replace('by = "@lead"\non = "2026-09-12"', 'by = "agent:planner"\non = "2026-09-12"'), encoding="utf-8")
                errs, _ = repo.check_repo(root)
                self.assertIn(f"{rel}: decisions D-2.by agent:planner is an agent account; a person decides scope", errs)
                # A tenant-qualified agent is still an agent.
                path.write_text(body.replace('by = "@lead"\non = "2026-09-12"', 'by = "acme:agent:planner"\non = "2026-09-12"'), encoding="utf-8")
                errs, _ = repo.check_repo(root)
                self.assertIn(f"{rel}: decisions D-2.by acme:agent:planner is an agent account; a person decides scope", errs)

    def test_an_initiative_checks_its_log_as_a_proposal_does(self):
        init = '+++\naidd_version = "1.0.0"\nkind = "initiative"\nid = "INIT-1"\ntitle = "Portal"\ngoal = "Dealers track their orders"\n' + DECISIONS + "+++\n"
        self.assertEqual(model.load_object(init, "i.md")[2], [])
        bad = model.load_object(init.replace('replaces = "D-1"', 'replaces = "D-7"'), "i.md")[2]
        self.assertEqual(bad, ["i.md: decisions D-2 replaces D-7, which is not an earlier entry of the log"])
        props = resources.load_json("initiative.schema.json")["properties"]
        self.assertEqual(props["decisions"]["items"]["$ref"], "urn:aidd:1:proposal#/$defs/decision")

    def test_convert_copies_the_log_to_the_initiative(self):
        top = (
            'go_no_go = { decision = "go", by = "@lead", on = "2026-09-01" }\nsign_off = { by = "@lead", on = "2026-09-20" }\n'
            'outcome = { decision = "accepted", by = "@lead", on = "2026-09-25" }\n'
        )
        data, _, errs = model.load_object(text(top=top, tail=DECISIONS + CLAIMS), "proposals/PROP-5/proposal.md")
        self.assertEqual(errs, [])
        with tempfile.TemporaryDirectory() as d:
            paths = proposal.convert(data, Path(d))
            init = next(p for p in paths if p.name.startswith("INIT-"))
            parsed, _, errs = model.load_object(init.read_text(encoding="utf-8"), str(init))
        self.assertEqual(errs, [])
        self.assertEqual(parsed["decisions"], data["decisions"])
        self.assertNotIn("claims", parsed)  # the claims are the promise: they stay in the proposal


def _objects(*items: tuple[str, dict]) -> list[tuple[str, dict, str, str]]:
    return [(rel, data, "", "") for rel, data in items]


class DigestTests(unittest.TestCase):
    def setUp(self):
        self.decisions = model.load_object(text(tail=DECISIONS), "p.md")[0]["decisions"]

    def test_reversals_in_the_window(self):
        objs = _objects(("specs/INIT-1.md", {"kind": "initiative", "id": "INIT-1", "decisions": self.decisions}))
        got = rollup.reversals(objs, dt.date(2026, 9, 10), dt.date(2026, 9, 30))
        self.assertEqual(
            got,
            [
                {
                    "source": "INIT-1",
                    "id": "D-2",
                    "replaces": "D-1",
                    "decision": "Card and invoice payments in the first release",
                    "by": "@lead",
                    "on": "2026-09-12",
                    "reason": "Acme confirmed the ERP export date",
                }
            ],
        )
        self.assertEqual(rollup.reversals(objs, dt.date(2026, 9, 13), dt.date(2026, 9, 30)), [], "dated before the window")
        self.assertEqual(rollup.reversals(objs, dt.date(2026, 9, 1), dt.date(2026, 9, 11)), [], "dated after the digest's day")

    def test_an_accepted_proposal_is_history_and_counts_once(self):
        accepted = {
            "kind": "proposal",
            "id": "PROP-5",
            "go_no_go": {"decision": "go"},
            "sign_off": {"by": "@lead"},
            "outcome": {"decision": "accepted"},
            "decisions": self.decisions,
        }
        drafting = {"kind": "proposal", "id": "PROP-6", "go_no_go": {"decision": "go"}, "decisions": self.decisions}
        objs = _objects(("proposals/PROP-5/proposal.md", accepted), ("proposals/PROP-6/proposal.md", drafting))
        got = rollup.reversals(objs, dt.date(2026, 9, 1), dt.date(2026, 9, 30))
        self.assertEqual([(r["source"], r["id"]) for r in got], [("PROP-6", "D-2")])


@unittest.skipUnless(shutil.which("git"), "git is required")
class DigestRepoTests(unittest.TestCase):
    def test_the_team_digest_reports_the_reversal_and_matches_its_schema(self):
        with tempfile.TemporaryDirectory() as d:
            root = reports.build(Path(d).resolve() / "repo")
            init = root / "specs" / "INIT-PROP-1.md"
            init.write_text(init.read_text(encoding="utf-8").replace('proposal = "PROP-1"\n', 'proposal = "PROP-1"\n' + DECISIONS), encoding="utf-8")
            git(root, "add", "-A")
            reports.at(root, "2026-09-25T10:00:00Z", "commit", "-qm", "scope: D-2")
            here = os.getcwd()
            os.chdir(root)
            try:
                out = rollup.digest(root, "2026-09-01", today=reports.TODAY, now=reports.NOW)
            finally:
                os.chdir(here)
        self.assertEqual(schema.validate(json.loads(json.dumps(out)), "digest.schema.json"), [])
        self.assertEqual([(r["source"], r["id"], r["replaces"]) for r in out["reversed"]], [("INIT-PROP-1", "D-2", "D-1")])
        md = rollup.digest_markdown(out)
        self.assertIn(
            "## Scope decisions reversed\n\n- INIT-PROP-1 D-2 replaces D-1 (@lead, 2026-09-12): Card and invoice payments in the first release. "
            "Why: Acme confirmed the ERP export date",
            md,
        )


class TemplateTests(unittest.TestCase):
    def test_the_template_starts_the_new_fields_commented_out(self):
        tpl = (ASSETS / "proposal.md").read_text(encoding="utf-8")
        for table in ("# [[estimate.parts]]", "# [[claims]]", "# [[decisions]]"):
            self.assertIn(table, tpl, table)
        filled = repo.fill(tpl, id="PROP-1", title="T", audience="client", addressee="A", owner_team="t", today="2026-09-30")
        # Uncomment each new block: the `# [[...]]` line and the `# key = value` lines under it.
        lines, out, live = filled.splitlines(), [], False
        for ln in lines:
            if ln in ("# [[estimate.parts]]", "# [[claims]]", "# [[decisions]]"):
                live = True
            elif not re.match(r"^# \w+ = ", ln):
                live = False
            out.append(ln[2:] if live else ln)
        data, _, errs = model.load_object("\n".join(out) + "\n", "proposal.md")
        self.assertEqual(hard(errs), [])
        for key in ("claims", "decisions"):
            self.assertEqual(len(data[key]), 1, key)
        self.assertEqual(len(data["estimate"]["parts"]), 1)


if __name__ == "__main__":
    unittest.main()
