"""`aidd digest` (the team view and the client view), `aidd release-notes`, and the post-launch feedback log.

A fixture repository holds Specs shipped before and inside the window (commits with fixed dates), a blocked draft whose
handoff note asks the client for something, an accepted proposal with an open question and the Initiative that holds
its milestones and risks, a feedback log, and gate events. The rollups are rendered from it deterministically; the HTML pages go through the views renderer
(escaped, strict CSP); the JSON validates against schemas/digest.schema.json and schemas/release-notes.schema.json.
"""

import datetime as dt
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, make_repo, run_cli

from aidd import resources, rollup, schema

TODAY = dt.date(2026, 9, 30)
NOW = dt.datetime(2026, 9, 30, 12, 0, tzinfo=dt.UTC)
HOSTILE = "CSV export <script>alert(1)</script>"


def spec(sid, title, ctype, status, scope, *, extra="", intent="", body_extra=""):
    return f"""+++
aidd_version = "1.0.0"
kind = "spec"
id = "{sid}"
title = {json.dumps(title)}
owner_team = "web"
type = "{ctype}"
route = "normal"
confidence = "high"
open_questions = []
trace_id = "{sid.lower()}"
assisted_by = []
rollback = "Revert the change."
status = "{status}"
{extra}
[risk]
summary = "Who behaves differently."
dimensions = {json.dumps(["security"] if ctype == "fix" and "auth" in scope else [])}
reversible = true

[[tasks]]
id = "{sid}-T1"
title = "The slice"
scope = ["{scope}"]

[tests]
files = ["tests/test_{sid.lower().replace("-", "_")}.py"]

[[tests.commands]]
name = "acceptance"
command = ["python3", "-m", "unittest"]
new_behavior = true
covers = ["A1"]
+++

## Intent

{intent or "TODO: quote the request."}

## Acceptance

- A1: it works
{body_extra}"""


PROPOSAL = """+++
aidd_version = "1.0.0"
kind = "proposal"
id = "PROP-1"
title = "Orders portal for Acme"
audience = "client"
addressee = "Acme Corp"
goal = "Acme's customers download their orders."
go_no_go = { decision = "go", by = "@lead", on = "2026-08-01" }
sign_off = { by = "@lead", on = "2026-08-02" }
outcome = { decision = "accepted", by = "@lead", on = "2026-08-03" }

[[milestones]]
id = "M-0"
name = "Promised, and moved to the Initiative"
due = "2026-08-04"
trigger = { event = "contract signed" }

[[questions]]
id = "Q1"
question = "Which currencies must the export show?"

[[questions]]
id = "Q2"
question = "Who signs off the beta?"
answer = "Dana"
+++

## Needs
"""

INITIATIVE = """+++
aidd_version = "1.0.0"
kind = "initiative"
id = "INIT-PROP-1"
title = "Orders portal for Acme"
goal = "Acme's customers download their orders."
proposal = "PROP-1"

[[milestones]]
id = "M-1"
name = "Beta"
due = "2026-09-15"
trigger = { event = "beta sign-off" }

[[milestones]]
id = "M-2"
name = "Kickoff"
due = "2026-08-05"
reached_on = "2026-08-05"
trigger = { event = "kickoff held" }

[[milestones]]
id = "M-3"
name = "Export"
due = "2026-09-11"
trigger = { specs = ["SPEC-1"] }

[[milestones]]
id = "M-4"
name = "Launch"
due = "2026-10-30"
trigger = { specs = ["SPEC-1", "SPEC-3"] }

[[risks]]
id = "R1"
text = "The payment provider's sandbox is late."
owner = "@pm"
status = "open"
likelihood = "medium"
impact = "high"
mitigation = "Stub it."

[[risks]]
id = "R2"
text = "The currency list changes."
owner = "@pm"
status = "accepted"
likelihood = "low"
impact = "low"
+++
"""

FEEDBACK = """# Feedback log: launch

## Log

| Date | Channel | Customer or segment | Quote | Theme | Severity | Score | Linked Spec or hypothesis |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-20 | support | SMB | "Export takes a minute" | export speed | high | 9 | SPEC-1 |
| 2026-09-21 | interview | enterprise | "Too slow for 10k orders" | Export speed | medium | 3 | SPEC-1 |
| 2026-09-22 | survey | SMB | "Love it" | delight | low | 10 | |
| 2026-08-01 | survey | SMB | "Old news" | onboarding | low | 5 | |
| TODO | TODO | TODO | TODO | TODO: a theme | TODO | TODO | TODO |
"""

HANDOFF = """
```aidd-handoff
done = "drafted"
next = "developer"
needs = ["client: send the sandbox API keys", "pick the CSV delimiter"]
stopped_at = "none"
```
"""


def at(root, when, *args):
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    return git(root, *args, env=env)


def commit(root, when, msg, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    at(root, when, "commit", "-qm", msg)


def build(root: Path) -> Path:
    make_repo(root, branch=None)
    commit(
        root,
        "2026-08-01T10:00:00Z",
        "fix(login): SPEC-2",
        {
            "specs/SPEC-2.md": spec("SPEC-2", "Login keeps the session", "fix", "done", "src/login/", intent="Sessions dropped at midnight."),
            "src/login/a.py": "x = 1\n",
        },
    )
    git(root, "tag", "v1.0")
    flags = '\n[[flags]]\nname = "csv-export"\ndefault = "off"\nowner = "@pm"\ncleanup_due = "2027-01-01"\n'
    commit(
        root,
        "2026-09-10T10:00:00Z",
        "feat(export): SPEC-1",
        {
            "specs/SPEC-1.md": spec(
                "SPEC-1", HOSTILE, "feat", "shipped", "src/export/", extra=flags, intent="> Customers download their orders as <b>CSV</b>."
            ),
            "src/export/csv.py": "x = 1\n",
        },
    )
    commit(
        root,
        "2026-09-12T10:00:00Z",
        "refactor(core): SPEC-5",
        {
            "specs/SPEC-5.md": spec("SPEC-5", "Split the core module", "refactor", "shipped", "src/core/", intent="The core module is too big."),
            "src/core/x.py": "x = 1\n",
        },
    )
    commit(
        root,
        "2026-09-14T10:00:00Z",
        "fix(auth): SPEC-6",
        {
            "specs/SPEC-6.md": spec("SPEC-6", "Tokens expire on logout", "fix", "shipped", "src/auth/", intent="A token outlived its session."),
            "src/auth/t.py": "x = 1\n",
        },
    )
    commit(
        root,
        "2026-09-02T10:00:00Z",
        "plan: SPEC-4 and PROP-1",
        {
            "specs/SPEC-4.md": spec(
                "SPEC-4",
                "Pay by card",
                "feat",
                "draft",
                "src/pay/",
                extra='blocked_on = "the sandbox API keys"\n',
                intent="Customers pay by card.",
                body_extra=HANDOFF,
            ),
            "proposals/PROP-1/proposal.md": PROPOSAL,
            "specs/INIT-PROP-1.md": INITIATIVE,
            "docs/feedback/launch.md": FEEDBACK,
        },
    )
    git(root, "checkout", "-qb", "spec-3")
    commit(
        root,
        "2026-09-20T10:00:00Z",
        "feat(search): SPEC-3",
        {
            "specs/SPEC-3.md": spec("SPEC-3", "Search orders", "feat", "ready", "src/search/", intent="Find an order by number."),
            "src/search/s.py": "x = 1\n",
        },
    )
    git(root, "checkout", "-q", "main")
    (root / "events.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "repo": "o/r",
                    "change": str(i),
                    "ts": f"2026-09-1{i}T10:00:00Z",
                    "head_sha": f"{i:040x}",
                    "decision": "pass",
                    "pending_rules": [],
                    "failed_rules": [],
                    "route": "normal",
                }
            )
            + "\n"
            for i in range(1, 4)
        ),
        encoding="utf-8",
    )
    (root / "cost.jsonl").write_text(json.dumps({"ts": "2026-09-11T10:00:00Z", "amount": 3.5, "currency": "USD", "branch": "1"}) + "\n", encoding="utf-8")
    return root


@unittest.skipUnless(shutil.which("git"), "git is required")
class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = build(Path(cls._tmp.name).resolve() / "repo")
        cls._here = os.getcwd()
        os.chdir(cls.root)

    @classmethod
    def tearDownClass(cls):
        os.chdir(cls._here)
        cls._tmp.cleanup()

    def cli(self, *argv, code=0):
        got, out = run_cli(*argv)
        self.assertEqual(got, code, out)
        return out

    def team(self, **kw):
        from aidd import metrics

        return rollup.digest(self.root, "2026-09-01", events=metrics.load([str(self.root / "events.jsonl")], since="2026-09-01"), today=TODAY, now=NOW, **kw)

    def client(self, **kw):
        return rollup.digest(self.root, "2026-09-01", client=True, today=TODAY, now=NOW, **kw)


class DigestTeamView(Fixture):
    def test_shipped_in_progress_blocked_waiting_and_metrics(self):
        d = self.team()
        self.assertEqual([s["id"] for s in d["shipped"]], ["SPEC-1", "SPEC-5", "SPEC-6"])  # SPEC-2 merged before the window
        self.assertEqual(d["shipped"][0]["merged_on"], "2026-09-10")
        self.assertEqual(d["shipped"][0]["intent"], "Customers download their orders as <b>CSV</b>.")
        self.assertEqual([(p["id"], p["status"]) for p in d["in_progress"]], [("SPEC-3", "in_progress")])
        self.assertEqual([(b["id"], b["days"]) for b in d["blocked"]], [("SPEC-4", 28)])
        self.assertIn("client: send the sandbox API keys", [n["text"] for n in d["needs"]])
        self.assertTrue(d["waiting"] and all(w["items"] for w in d["waiting"]))
        self.assertEqual([r["id"] for r in d["risks"]], ["R1"])
        self.assertEqual(d["metrics"]["changes"], 3)
        self.assertNotIn("cost", d)

    def test_feedback_themes_are_counted_in_the_window(self):
        f = self.team()["feedback"]
        self.assertEqual(f["entries"], 3)
        self.assertEqual(f["themes"], [{"theme": "export speed", "count": 2}, {"theme": "delight", "count": 1}])
        self.assertEqual(f["severity"], {"high": 1, "low": 1, "medium": 1})
        self.assertEqual(f["nps"], 33)  # two promoters, one detractor, of three

    def test_the_same_repository_and_day_give_the_same_bytes(self):
        a, b = self.team(), self.team()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(rollup.digest_markdown(a), rollup.digest_markdown(b))
        with self.assertRaises(ValueError):
            rollup.digest_page(a)  # the page is the client's
        c, d = self.client(), self.client()
        self.assertEqual(rollup.digest_page(c), rollup.digest_page(d))

    def test_the_cli_prints_markdown_and_json_that_matches_its_schema(self):
        out = self.cli("digest", "--since", "2026-09-01", "--events", "events.jsonl")
        for heading in ("## Shipped", "## In progress", "## Waiting on", "## Blocked", "## Risks", "## Metrics", "## Feedback"):
            self.assertIn(heading, out)
        self.assertNotIn("<script>", out)  # Markdown gets pasted where HTML renders: no tag survives
        self.assertIn("&lt;script&gt;", out)
        d = json.loads(self.cli("digest", "--since", "2026-09-01", "--events", "events.jsonl", "--json"))
        self.assertEqual(d["schema_version"], rollup.SCHEMA_VERSION)
        self.assertEqual(schema.validate(d, "digest.schema.json"), [])
        ref = json.loads(self.cli("digest", "--since", "v1.0", "--json"))
        self.assertEqual(ref["window"]["kind"], "ref")
        self.assertEqual(schema.validate(ref, "digest.schema.json"), [])

    def test_a_since_that_is_neither_a_date_nor_a_ref_is_refused(self):
        self.assertIn("neither an ISO date nor a git ref", self.cli("digest", "--since", "no-such-tag", code=2))
        self.assertIn("neither an ISO date nor a git ref", self.cli("digest", "--since=--oneline", code=2))


class DigestClientView(Fixture):
    def test_the_client_view_holds_rag_milestones_shipped_asks_and_next_steps(self):
        d = self.client()
        self.assertEqual(d["rag"]["status"], "red")
        self.assertIn("milestone Beta (INIT-PROP-1) was due 2026-09-15", d["rag"]["reasons"])
        self.assertIn("SPEC-4 has been blocked for 28 days", d["rag"]["reasons"])
        self.assertEqual(len(d["rag"]["rules"]), 3)
        self.assertEqual([(m["name"], m["late"]) for m in d["milestones"]], [("Kickoff", False), ("Export", False), ("Beta", True), ("Launch", False)])
        self.assertEqual([s["title"] for s in d["shipped"]], [HOSTILE, "Split the core module", "Tokens expire on logout"])
        self.assertEqual(sorted(a["text"] for a in d["asks"]), ["Which currencies must the export show?", "send the sandbox API keys"])
        self.assertIn("SPEC-3", [n["id"] for n in d["next_steps"]])
        for internal in ("metrics", "waiting", "needs", "cost", "risks"):
            self.assertNotIn(internal, d)

    def test_cost_is_left_out_unless_asked(self):
        self.assertNotIn(
            "cost", json.loads(self.cli("digest", "--since", "2026-09-01", "--client", "--events", "events.jsonl", "--cost", "cost.jsonl", "--json"))
        )
        d = json.loads(self.cli("digest", "--since", "2026-09-01", "--client", "--events", "events.jsonl", "--cost", "cost.jsonl", "--include-cost", "--json"))
        self.assertIn("USD", d["cost"]["currencies"])
        self.assertEqual(schema.validate(d, "digest.schema.json"), [])
        self.assertIn("--include-cost goes with --client", self.cli("digest", "--since", "2026-09-01", "--include-cost", code=2))

    def test_the_client_page_is_escaped_self_contained_and_themed(self):
        out = self.cli("digest", "--since", "2026-09-01", "--client", "--html", "client.html")
        self.assertIn("client.html", out)
        page = (self.root / "client.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<b>CSV</b>", page)
        self.assertIn("default-src &#x27;none&#x27;", page)
        self.assertEqual(len(re.findall(r"<script\b", page)), 1)  # only the hash-pinned copy script
        self.assertNotRegex(page, r"(?i)<(link|iframe|img)\b[^>]*\b(src|href)=\"https?:")
        self.assertIn("prefers-color-scheme: dark", page)
        self.assertIn("How the status is set", page)

    def test_the_team_view_has_no_page(self):
        self.assertIn("--html goes with --client", self.cli("digest", "--since", "2026-09-01", "--html", "team.html", code=2))
        self.assertFalse((self.root / "team.html").exists())


class RagRules(unittest.TestCase):
    late = [{"name": "Beta", "source": "PROP-1", "due": "2026-09-15"}]

    def test_red_when_a_milestone_is_late_or_an_item_is_blocked_too_long(self):
        self.assertEqual(rollup.rag(self.late, [], [], [])["status"], "red")
        self.assertEqual(rollup.rag([], [{"id": "SPEC-4", "days": 6}], [], [])["status"], "red")
        self.assertEqual(rollup.rag([], [{"id": "SPEC-4", "days": 3}], [], [], blocked_days=2)["status"], "red")

    def test_amber_when_a_risk_or_an_ask_is_open(self):
        self.assertEqual(rollup.rag([], [{"id": "SPEC-4", "days": 5}], [{"id": "R1"}], [])["status"], "amber")
        r = rollup.rag([], [], [], [{"source": "PROP-1", "text": "which currencies?"}])
        self.assertEqual((r["status"], r["reasons"]), ("amber", ["1 item(s) wait on the client"]))

    def test_green_otherwise_and_the_rules_are_written_out(self):
        r = rollup.rag([], [], [], [], blocked_days=7)
        self.assertEqual(r["status"], "green")
        self.assertIn("more than 7 days", r["rules"][0])

    def test_milestones_of_a_proposal_being_decided(self):
        objects = [
            (
                "proposals/P/proposal.md",
                {
                    "kind": "proposal",
                    "id": "P",
                    "go_no_go": {"decision": "go"},
                    "milestones": ["Kickoff", {"name": "Beta", "due": "2026-09-01"}, {"name": "M3", "due": "2026-09-02", "reached_on": "2026-09-02"}, 7],
                },
                "",
                "",
            )
        ]
        got = rollup.milestones(objects, TODAY)
        self.assertEqual(
            [(m["name"], m["due"], m["late"], m["status"]) for m in got],
            [("Beta", "2026-09-01", True, "open"), ("M3", "2026-09-02", False, "done")],
        )
        self.assertEqual(
            rollup.milestones(
                [("x", {"kind": "proposal", "id": "P", "go_no_go": {"decision": "no_go"}, "milestones": [{"name": "A", "due": "2020-01-01"}]}, "", "")], TODAY
            ),
            [],
        )


class ReleaseNotes(Fixture):
    def test_grouped_by_keep_a_changelog_for_users(self):
        d = json.loads(self.cli("release-notes", "--since", "v1.0", "--json"))
        self.assertEqual(schema.validate(d, "release-notes.schema.json"), [])
        self.assertEqual([(g["name"], [e["id"] for e in g["entries"]]) for g in d["groups"]], [("Added", ["SPEC-1"]), ("Security", ["SPEC-6"])])
        self.assertEqual(d["groups"][0]["entries"][0]["flags"], [{"name": "csv-export", "default": "off"}])

    def test_developers_also_read_the_internal_changes(self):
        d = json.loads(self.cli("release-notes", "--since", "v1.0", "--audience", "developers", "--json"))
        self.assertEqual([g["name"] for g in d["groups"]], ["Added", "Changed", "Security"])

    def test_the_markdown_follows_the_template_and_is_escaped(self):
        out = self.cli("release-notes", "--since", "v1.0")
        template = (resources.data_dir("skill") / "assets" / "release-notes.md").read_text(encoding="utf-8")
        order = [h for h in re.findall(r"(?m)^## (\w+)$", template)]
        self.assertEqual(order, list(rollup.CHANGE_GROUPS))
        shown = re.findall(r"(?m)^## (\w+)$", out)
        self.assertEqual(shown, [g for g in order if g in shown])
        self.assertIn("behind the flag `csv-export` (off by default)", out)
        self.assertNotIn("<script>", out)

    def test_labels_override_the_group_and_the_audience(self):
        s = {"type": "chore", "labels": ["changelog:removed", "audience:users"], "dimensions": []}
        self.assertEqual(rollup.change_group(s), "Removed")
        self.assertTrue(rollup.for_audience(s, "users"))
        self.assertFalse(rollup.for_audience({"type": "feat", "labels": ["audience:developers"]}, "users"))
        self.assertEqual(rollup.change_group({"type": "perf", "labels": [], "dimensions": []}), "Changed")


@unittest.skipUnless(shutil.which("git"), "git is required")
class FeedbackCapture(unittest.TestCase):
    def test_new_feedback_writes_the_living_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", branch=None)
            here = os.getcwd()
            self.addCleanup(os.chdir, here)
            os.chdir(root)
            code, out = run_cli("new", "feedback", "launch")
            self.assertEqual(code, 0, out)
            path = root / "docs" / "feedback" / "launch.md"
            self.assertTrue(path.is_file(), out)
            text = path.read_text(encoding="utf-8")
            for column in ("Date", "Channel", "Customer or segment", "Quote", "Theme", "Severity", "Linked Spec or hypothesis"):
                self.assertIn(column, text)
            self.assertIn("kind: feedback", text)
            self.assertEqual(rollup.feedback(root, "docs", None)["entries"], 0)  # the template's TODO row is not an entry


class RoleWiring(unittest.TestCase):
    def test_the_tech_writer_and_the_product_manager_know_the_new_files(self):
        roles = resources.load_json("roles.json")["roles"]
        self.assertIn("aidd release-notes", roles["tech-writer"]["done_when"])
        self.assertIn("feedback", roles["product-manager"]["reads"])
        skill = (ROOT / "plugins" / "aidd-team" / "skills" / "product-discovery" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("docs/feedback/", skill)


if __name__ == "__main__":
    unittest.main()
