"""Keeping the knowledge current: the standards check (`aidd eval standards --online`), the review cadence by
maturity, a steward per pack and practice skill, postmortem actions that target a pack or a skill, and the weekly
workflow that runs the check. The online standards check is tested against a local HTTP server only, never the internet."""

import contextlib
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import threading
import time
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from helpers import ROOT, adopted_repo, run_cli

from aidd import cli, docs, evals, knowledge, model, nextstep, repo, resources, schema

QUOTE = "The quick brown fox jumps over the lazy dog’s back, every single time."
PAGE = "<html><body><p>The quick&nbsp;brown <em>fox</em>\n   jumps over the lazy dog&rsquo;s back, every single time.</p></body></html>"


class _Handler(BaseHTTPRequestHandler):
    """Pages for each outcome. The server records the user agents it saw and the most requests in flight at once."""

    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, body: bytes = b"", ctype: str = "text/html; charset=utf-8", headers: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        srv = self.server
        with srv.lock:  # type: ignore[attr-defined]
            srv.agents.append(self.headers.get("User-Agent", ""))  # type: ignore[attr-defined]
            srv.inflight += 1  # type: ignore[attr-defined]
            srv.peak = max(srv.peak, srv.inflight)  # type: ignore[attr-defined]
        try:
            time.sleep(0.02)
            path = self.path
            if path == "/ok":
                self._send(200, PAGE.encode())
            elif path == "/changed":
                self._send(200, b"<p>This page now says something else entirely.</p>")
            elif path == "/gone":
                self._send(404, b"not found")
            elif path == "/redirect-away":
                self._send(301, headers={"Location": "/home"})
            elif path == "/home":
                self._send(200, b"<p>Welcome to the home page.</p>")
            elif path == "/redirect-ok":
                self._send(301, headers={"Location": "/ok"})
            elif path == "/error":
                self._send(500, b"boom")
            elif path == "/forbidden":
                self._send(403, b"no robots")
            elif path == "/big":
                self._send(200, b"<p>" + b"x" * 5000 + b"</p>")
            elif path == "/pdf":
                self._send(200, b"%PDF-1.7", ctype="application/pdf")
            elif path == "/gzip":  # sent compressed whatever the request asked for, as some hosts do
                srv.encodings.append(self.headers.get("Accept-Encoding", ""))  # type: ignore[attr-defined]
                self._send(200, gzip.compress(PAGE.encode()), headers={"Content-Encoding": "gzip"})
            elif path == "/deflate":
                self._send(200, zlib.compress(PAGE.encode()), headers={"Content-Encoding": "deflate"})
            elif path == "/raw-deflate":
                z = zlib.compressobj(wbits=-15)
                self._send(200, z.compress(PAGE.encode()) + z.flush(), headers={"Content-Encoding": "deflate"})
            elif path == "/gzip-bomb":
                self._send(200, gzip.compress(b"<p>" + b"x" * 200_000 + b"</p>"), headers={"Content-Encoding": "gzip"})
            elif path == "/brotli":
                self._send(200, b"\x1b\x00\x00", headers={"Content-Encoding": "br"})
            elif path == "/slow":
                time.sleep(1.5)
                self._send(200, PAGE.encode())
            else:
                self._send(404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with srv.lock:  # type: ignore[attr-defined]
                srv.inflight -= 1  # type: ignore[attr-defined]


class _Server:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.lock, self.httpd.agents, self.httpd.inflight, self.httpd.peak = threading.Lock(), [], 0, 0  # type: ignore[attr-defined]
        self.httpd.encodings = []  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def entry(sid: str, url: str, quote: str = QUOTE) -> dict:
    return {"id": sid, "name": f"Standard {sid}", "where": f"domain {sid}", "url": url, "quote": quote}


def check(entries, **kw):
    kw = {"timeout": 1.0, "max_seconds": 30.0, "max_bytes": 100_000, "concurrency": 2, "host_delay": 0.0} | kw
    return knowledge.check_online(entries, **kw)


class OnlineCheckTests(unittest.TestCase):
    """`aidd eval standards --online` re-fetches each evidence URL and looks for the quoted sentence."""

    @classmethod
    def setUpClass(cls):
        cls.server = _Server().__enter__()
        cls.addClassCleanup(cls.server.__exit__, None, None, None)

    def status_of(self, path: str, **kw) -> dict:
        return check([entry("s", self.server.base + path)], **kw)["results"][0]

    def test_a_quote_still_on_its_page_is_ok_after_normalizing_whitespace_tags_and_entities(self):
        r = self.status_of("/ok")
        self.assertEqual((r["status"], r["http_status"]), ("ok", 200), r)

    def test_a_page_that_no_longer_carries_the_quote_is_missing(self):
        self.assertEqual(self.status_of("/changed")["status"], "missing")

    def test_a_page_gone_or_redirected_elsewhere_is_moved(self):
        self.assertEqual(self.status_of("/gone")["status"], "moved")
        away = self.status_of("/redirect-away")
        self.assertEqual(away["status"], "moved")
        self.assertTrue(away["final_url"].endswith("/home"), away)

    def test_a_redirect_to_a_page_that_still_carries_the_quote_is_ok_and_names_the_new_address(self):
        r = self.status_of("/redirect-ok")
        self.assertEqual(r["status"], "ok")
        self.assertTrue(r["final_url"].endswith("/ok"), r)

    def test_network_failures_are_unreachable_not_findings(self):
        for path, kw in (("/error", {}), ("/forbidden", {}), ("/pdf", {}), ("/slow", {"timeout": 0.3}), ("/big", {"max_bytes": 1000})):
            with self.subTest(path=path):
                self.assertEqual(self.status_of(path, **kw)["status"], "unreachable")
        closed = check([entry("c", "http://127.0.0.1:9/nothing-listens-here")])["results"][0]
        self.assertEqual(closed["status"], "unreachable")
        self.assertTrue(closed["reason"])

    def test_a_compressed_body_is_decoded_before_the_quote_is_looked_for(self):
        # A host that compresses whatever the request asks for (Datadog's docs do) read as `missing` before.
        for path in ("/gzip", "/deflate", "/raw-deflate"):
            with self.subTest(path=path):
                r = self.status_of(path)
                self.assertEqual((r["status"], r["http_status"]), ("ok", 200), r)
        self.assertIn("identity", self.server.httpd.encodings[-1])  # it asks for an uncompressed body first

    def test_a_compressed_body_stays_within_the_byte_limit_and_an_unknown_encoding_is_unreachable(self):
        bomb = self.status_of("/gzip-bomb", max_bytes=1000)
        self.assertEqual(bomb["status"], "unreachable", bomb)
        self.assertIn("1000 bytes", bomb["reason"])
        br = self.status_of("/brotli")
        self.assertEqual(br["status"], "unreachable", br)
        self.assertIn("br", br["reason"])

    def test_the_total_time_cap_marks_what_it_did_not_reach_unreachable(self):
        out = check([entry(f"s{i}", self.server.base + "/ok") for i in range(3)], max_seconds=0)
        self.assertEqual([r["status"] for r in out["results"]], ["unreachable"] * 3)
        self.assertIn("time", out["results"][0]["reason"])

    def test_it_is_polite_names_itself_and_counts_every_status(self):
        paths = ["/ok", "/changed", "/gone", "/error", "/ok", "/redirect-ok"]
        with _Server() as own:  # its own server, so no earlier test's request is still in flight
            out = check([entry(f"s{i}", own.base + p) for i, p in enumerate(paths)], concurrency=8)
        self.assertEqual(out["limits"]["concurrency"], 2)  # clamped: never more than two requests at once
        self.assertEqual(own.httpd.peak, 1)  # and one at a time to one host
        self.assertEqual(out["counts"], {"ok": 3, "moved": 1, "missing": 1, "unreachable": 1})
        self.assertEqual([r["id"] for r in out["results"]], [f"s{i}" for i in range(len(paths))])  # registry order
        self.assertTrue(own.httpd.agents and all(a.startswith("aidd/") for a in own.httpd.agents), own.httpd.agents)
        self.assertEqual(schema.validate(out, "knowledge.schema.json"), [])

    def run_cli_online(self, entries: list[dict], *extra: str) -> tuple[int, str]:
        roles = (ROOT / "schemas" / "roles.json").read_bytes()
        # The library's release feeds are on the internet: none is read here (ReleaseFeedTests mocks the fetcher).
        with mock.patch.object(knowledge, "evidence_entries", lambda: entries), mock.patch.object(knowledge, "release_entries", list):
            code, out = run_cli("eval", "standards", "--online", "--timeout", "1", *extra)
        self.assertEqual(hashlib.sha256((ROOT / "schemas" / "roles.json").read_bytes()).digest(), hashlib.sha256(roles).digest(), "never edits the registry")
        return code, out

    def test_the_cli_prints_json_with_a_schema_and_fails_only_on_moved_or_missing_with_strict(self):
        b = self.server.base
        code, out = self.run_cli_online([entry("a", b + "/ok"), entry("b", b + "/changed")], "--json")
        data = json.loads(out)
        self.assertEqual((code, data["schema_version"], data["counts"]["missing"]), (0, knowledge.SCHEMA_VERSION, 1))
        self.assertEqual(schema.validate(data, "knowledge.schema.json"), [])
        self.assertEqual(self.run_cli_online([entry("b", b + "/changed")], "--strict")[0], 1)
        self.assertEqual(self.run_cli_online([entry("g", b + "/gone")], "--strict")[0], 1)
        self.assertEqual(self.run_cli_online([entry("e", b + "/error"), entry("a", b + "/ok")], "--strict")[0], 0)

    def test_the_text_report_lists_what_to_fix_and_the_counts(self):
        b = self.server.base
        code, out = self.run_cli_online([entry("a", b + "/ok"), entry("gone-one", b + "/gone"), entry("down", b + "/error")])
        self.assertEqual(code, 0)
        self.assertIn("gone-one", out)
        self.assertIn("down", out)
        self.assertIn("1 ok, 1 moved, 0 missing, 1 unreachable", out)
        self.assertNotIn("| a |", out)  # an entry that is fine is counted, not listed

    def test_online_flags_belong_to_the_standards_suite(self):
        for argv in (("eval", "examples", "--online"), ("eval", "standards", "--strict"), ("eval", "standards", "--json")):
            with self.subTest(argv=argv):
                code, out = run_cli(*argv)
                self.assertEqual(code, 2, out)


class NormalizeTests(unittest.TestCase):
    def test_entities_typography_and_whitespace_do_not_matter(self):
        self.assertTrue(knowledge.quote_on_page(QUOTE, PAGE))
        self.assertTrue(knowledge.quote_on_page("It isn't “done” — yet.", "<p>It isn&#39;t &quot;done&quot; - <b>yet</b>.</p>"))
        self.assertFalse(knowledge.quote_on_page(QUOTE, "<p>The quick brown fox.</p>"))

    def test_a_line_quoted_from_an_api_answer_matches_its_compact_json(self):
        sha = "85598ba6e1256f7ebf4867b95d63b833c4549264"
        self.assertTrue(knowledge.quote_on_page(f'"sha": "{sha}",', '{"sha":"' + sha + '","node_id":"C_1"}'))
        self.assertFalse(knowledge.quote_on_page(f'"sha": "{sha}",', '{"sha":"0000","node_id":"C_1"}'))

    def test_every_registry_entry_with_evidence_is_checked_once(self):
        found = knowledge.evidence_entries()
        self.assertGreater(len(found), 100)
        self.assertEqual(len({e["id"] for e in found}), len(found))
        self.assertTrue(all(e["url"].startswith("https://") and e["quote"] for e in found))


def stale(entries, today=dt.date(2026, 9, 30), max_days=None):
    with mock.patch.object(evals, "standards", lambda: entries):
        return evals.stale_standards(today, max_days)


def std(day: str, **kw) -> dict:
    return {"name": "X", "checked": day, "where": "domain x"} | kw


class CadenceTests(unittest.TestCase):
    """The review cadence follows maturity (emerging 90 days, established 365), an entry may set its own, and a known
    dated obligation carries `review_due`."""

    def test_defaults_follow_maturity(self):
        self.assertEqual(knowledge.REVIEW_EVERY_DAYS, {"established": 365, "emerging": 90})
        self.assertEqual(len(stale([std("2026-06-01", maturity="emerging")])), 1)  # 121 days
        self.assertEqual(stale([std("2026-06-01")]), [])
        self.assertEqual(stale([std("2026-06-01", maturity="established")]), [])
        self.assertEqual(len(stale([std("2025-09-01")])), 1)

    def test_an_entry_sets_its_own_cadence_and_a_due_date(self):
        self.assertEqual(len(stale([std("2026-08-01", review_every_days=30)])), 1)
        self.assertEqual(stale([std("2026-06-01", maturity="emerging", review_every_days=180)]), [])
        overdue = stale([std("2026-09-29", review_due="2026-09-01")])
        self.assertEqual(len(overdue), 1)
        self.assertIn("review_due", overdue[0]["why"])
        self.assertEqual(stale([std("2026-09-29", review_due="2026-10-01")]), [])

    def test_max_days_given_by_hand_applies_to_every_entry(self):
        self.assertEqual(stale([std("2026-06-01", maturity="emerging")], max_days=365), [])
        self.assertEqual(len(stale([std("2026-06-01")], max_days=30)), 1)

    def test_the_schema_holds_the_cadence_fields(self):
        base = {"name": "X", "reviewed": "2026-09-30"}
        roles = {"standards": {"x": base | {"review_every_days": 30, "review_due": "2027-04-01"}}}
        sch = resources.load_json("roles.schema.json")["$defs"]["standard"]
        self.assertIn("review_every_days", sch["properties"])
        self.assertIn("review_due", sch["properties"])
        errs = schema.validate(roles["standards"]["x"], "roles.schema.json#/$defs/standard")
        self.assertEqual(errs, [])
        self.assertTrue(schema.validate(base | {"review_every_days": 0}, "roles.schema.json#/$defs/standard"))
        self.assertTrue(schema.validate(base | {"review_due": "spring"}, "roles.schema.json#/$defs/standard"))

    def test_known_dated_obligations_carry_a_review_due_after_their_check(self):
        table = resources.load_json("roles.json")["standards"]
        due = {k: e for k, e in table.items() if e.get("review_due")}
        self.assertTrue(due)
        for k, e in due.items():
            self.assertGreater(e["review_due"], evals.dated(e), k)

    def test_the_offline_report_counts_what_comes_due_within_ninety_days(self):
        entries = [std("2026-09-01", maturity="emerging", id="a"), std("2026-09-01", id="b")]
        with mock.patch.object(evals, "standards", lambda: entries):
            self.assertEqual([s["id"] for s in evals.due_soon(dt.date(2026, 9, 30), 90)], ["a"])


class StewardTests(unittest.TestCase):
    """A steward per pack and practice skill: a person or a team, never an agent."""

    def test_a_steward_is_a_person_or_a_team(self):
        for good in ("@alice", "@acme/payments", "email:alice@example.com"):
            self.assertIsNone(knowledge.steward_problem(good), good)
        for bad in ("agent:claude-code", "renovate[bot]", "@github-actions", "@claude[bot]", "", "developer", "Alice Smith"):
            self.assertIsNotNone(knowledge.steward_problem(bad), bad)

    def test_the_schema_accepts_a_steward_on_a_domain_and_refuses_an_agent(self):
        d = resources.roles()["domains"][0]
        raw = next(x for x in resources.load_json("roles.json")["domains"] if x["slug"] == d["slug"])
        path = "roles.schema.json#/properties/domains/items"
        self.assertEqual(schema.validate(raw | {"steward": "@alice"}, path), [])
        self.assertTrue(schema.validate(raw | {"steward": "agent:claude-code"}, path))
        self.assertTrue(schema.validate(raw | {"steward": "renovate[bot]"}, path))

    def test_a_pack_renders_its_steward(self):
        d = resources.roles()["domains"][0]
        self.assertIn("Steward: @alice", docs.render_pack(d | {"steward": "@alice"}))
        self.assertNotIn("Steward:", docs.render_pack({k: v for k, v in d.items() if k != "steward"}))

    def test_every_pack_and_practice_skill_is_listed_with_its_steward(self):
        found = knowledge.stewards()
        kinds = {(s["kind"], s["id"]) for s in found}
        self.assertTrue({("pack", d["slug"]) for d in resources.roles()["domains"]} <= kinds)
        self.assertTrue({("skill", n) for n in docs.practice_names()} <= kinds)
        real = docs.practice_front
        with mock.patch.object(docs, "practice_front", lambda n: real(n) | ({"steward": "@bob"} if n == "debugging" else {})):
            self.assertIn({"kind": "skill", "id": "debugging", "steward": "@bob"}, knowledge.stewards())

    def test_the_eval_warns_on_an_unset_steward_and_fails_on_an_agent(self):
        entries = [std(dt.date.today().isoformat())]
        with mock.patch.object(evals, "standards", lambda: entries):
            with mock.patch.object(knowledge, "stewards", lambda: [{"kind": "pack", "id": "web-front-end", "steward": None}]):
                code, out = run_cli("eval", "standards")
            self.assertEqual(code, 0, out)
            self.assertIn("warning: 1 pack or skill names no steward", out)
            with mock.patch.object(knowledge, "stewards", lambda: [{"kind": "pack", "id": "web-front-end", "steward": "agent:claude-code"}]):
                code, out = run_cli("eval", "standards")
            self.assertEqual(code, 1, out)
            self.assertIn("agent:claude-code", out)

    def test_owners_lists_the_stewards(self):
        with adopted_repo() as root:
            code, out = run_cli("owners", "--json")
            self.assertEqual(code, 0, out)
            data = json.loads(out)
            self.assertEqual(schema.validate(data, "owners.schema.json"), [])
            steward = next(d.get("steward") for d in resources.roles()["domains"] if d["slug"] == "web-front-end")
            self.assertIn({"kind": "pack", "id": "web-front-end", "steward": steward}, data["stewards"])
            with contextlib.chdir(root):
                code, text = run_cli("owners")
            self.assertIn("## Stewards", text)


PM = """+++
aidd_version = "1.0.0"
kind = "postmortem"
id = "PM-1"
title = "Checkout 500s"
incident_on = "2026-09-01"
severity = "sev2"
status = "{status}"

[[actions]]
what = "Add the double-submit check to the pack"
owner = "@alice"
due = 2026-12-01
target = "{target}"
done = {done}

[[actions]]
what = "Alert on the checkout error rate"
owner = "@bob"
due = 2026-12-01
+++

## Summary
"""


class KnowledgeActionTests(unittest.TestCase):
    """A postmortem action may target a pack or a skill; `aidd validate` checks the id and `aidd list` shows it open."""

    def pm(self, target="pack:web-front-end", status="published", done="false") -> str:
        return PM.format(target=target, status=status, done=done)

    def test_the_schema_takes_a_target_of_a_known_form(self):
        self.assertEqual(model.load_object(self.pm(), "pm")[2], [])
        self.assertEqual(model.load_object(self.pm("skill:debugging"), "pm")[2], [])
        self.assertTrue(any("target" in e for e in model.load_object(self.pm("resilience"), "pm")[2]))

    def test_known_ids_only(self):
        self.assertIsNone(knowledge.target_problem("pack:web-front-end"))
        self.assertIsNone(knowledge.target_problem("skill:debugging"))
        self.assertIn("no pack", knowledge.target_problem("pack:nope") or "")
        self.assertIn("no practice skill", knowledge.target_problem("skill:web-front-end") or "")

    def write(self, root: Path, text: str) -> None:
        (root / "docs" / "postmortems").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "postmortems" / "PM-1.md").write_text(text, encoding="utf-8")

    def test_validate_refuses_an_unknown_target(self):
        with adopted_repo() as root:
            self.write(root, self.pm("pack:nope"))
            errors, _ = repo.check_repo(root)
            self.assertTrue(any("PM-1.md" in e and "pack:nope" in e for e in errors), errors)
            self.write(root, self.pm())
            errors, _ = repo.check_repo(root)
            self.assertFalse(any("PM-1.md" in e for e in errors), errors)

    def test_list_shows_open_knowledge_actions(self):
        with adopted_repo() as root:
            self.write(root, self.pm())
            steps = nextstep.plan(root, filters=nextstep.Filters(all=True))
            found = [s for s in steps if s["code"] == "knowledge.action"]
            self.assertEqual(len(found), 1, steps)
            self.assertEqual((found[0]["where"], found[0]["who"]), ("docs/postmortems/PM-1.md", "@alice"))
            self.assertIn("pack:web-front-end", found[0]["what"])
            self.assertIn("suggested Spec", found[0]["how"])
            self.assertEqual(schema.validate({"schema_version": "1", "steps": steps}, "list.schema.json"), [])
            for text in (self.pm(done="true"), self.pm(status="draft")):
                self.write(root, text)
                self.assertFalse([s for s in nextstep.plan(root, filters=nextstep.Filters(all=True)) if s["code"] == "knowledge.action"])

    def test_the_learn_commands_turn_targeted_actions_into_suggested_specs(self):
        for name in ("postmortem", "retro"):
            text = (ROOT / "plugins" / "aidd-team" / "commands" / f"{name}.md").read_text(encoding="utf-8")
            with self.subTest(command=name):
                self.assertIn("target", text)
                self.assertIn("suggested Spec", text)
        self.assertRegex((ROOT / ".agents" / "skills" / "aidd" / "assets" / "postmortem.md").read_text(encoding="utf-8"), r'target = "(pack|skill):')


WORKFLOW = ROOT / ".github" / "workflows" / "standards.yml"
TEMPLATE = ROOT / "templates" / "github" / "aidd-standards.yml"


def jobs(text: str) -> dict[str, str]:
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z][\w-]*):\n", body)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


class WorkflowTests(unittest.TestCase):
    """The weekly workflow, in this repository and as an adopter template: it runs the online standards check, writes the job
    summary, and opens an issue only when asked to, with `issues: write` only in the job that does it. It never commits."""

    def test_both_exist_and_agree_on_every_security_relevant_line(self):
        from test_release_surface import _blocks

        ours, theirs = WORKFLOW.read_text(encoding="utf-8"), TEMPLATE.read_text(encoding="utf-8")
        for key in ("on", "permissions", "concurrency", "if"):
            with self.subTest(key=key):
                self.assertEqual(_blocks(ours, key), _blocks(theirs, key))

    def test_weekly_and_by_hand_with_least_privilege(self):
        for path in (WORKFLOW, TEMPLATE):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                cron = re.search(r'cron: "([^"]+)"', text)
                self.assertIsNotNone(cron)
                assert cron is not None
                self.assertNotEqual(cron.group(1).split()[4], "*", "weekly: one day of the week")
                self.assertIn("workflow_dispatch:", text)
                self.assertIn("\npermissions: {}\n", text)
                found = jobs(text)
                self.assertEqual(set(found), {"check", "issue"})
                self.assertNotIn("write", found["check"].split("steps:", 1)[0])
                self.assertIn("issues: write", found["issue"])
                self.assertEqual(text.count("issues: write"), 1)
                cond = re.search(r"(?m)^    if: (.+)$", found["issue"])
                self.assertIsNotNone(cond)
                assert cond is not None
                self.assertIn("inputs.open_issue", cond.group(1))
                self.assertIn("vars.AIDD_STANDARDS_ISSUES", cond.group(1))
                self.assertNotIn("actions/checkout", found["issue"])

    def test_it_runs_the_online_check_writes_the_summary_and_never_commits(self):
        for path in (WORKFLOW, TEMPLATE):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("eval standards --online", text)
                self.assertIn("GITHUB_STEP_SUMMARY", text)
                for never in ("git push", "git commit", "contents: write", "pull-requests: write", "secrets."):
                    self.assertNotIn(never, text)
                self.assertEqual(text.count("actions/checkout@"), text.count("persist-credentials: false"))
                for ref, comment in re.findall(r"(?m)^\s+(?:- )?uses: (\S+)(.*)", text):
                    self.assertRegex(ref, r"@[0-9a-f]{40}$", ref)
                    self.assertRegex(comment, r"# v\d+\.\d+\.\d+", ref)
                for name, job in jobs(text).items():
                    for script in re.findall(r"(?ms)^\s+run: \|\n(.*?)(?=^\s{6}- |\Z)", job):
                        self.assertNotIn("${{", script, name)

    def test_the_template_runs_the_pinned_release(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(text, r"# aidd-pin: .*\n.*\n\s+with:\n\s+repository: thaithienvanid/aidd\n\s+ref: v\d+\.\d+\.\d+")


class DocsTests(unittest.TestCase):
    def test_the_owner_page_and_contributing_say_how_knowledge_stays_current(self):
        team = (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8")
        self.assertIn("## Keeping the knowledge current", team)
        section = team.split("## Keeping the knowledge current", 1)[1].split("\n## ", 1)[0]
        for words in ("--online", "review_every_days", "review_due", "steward", "target", "standards.yml"):
            self.assertIn(words, section)
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn("## Update a standard", contributing)
        section = contributing.split("## Update a standard", 1)[1].split("\n## ", 1)[0]
        for words in ("evidence", "steward", "route", "aidd eval standards"):
            self.assertIn(words, section)


class CliHelpTests(unittest.TestCase):
    def test_the_standards_flags_are_documented(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            cli.main(["eval", "--help"])
        for flag in ("--online", "--strict", "--json", "--max-seconds", "--max-bytes", "--concurrency"):
            self.assertIn(flag, out.getvalue())


if __name__ == "__main__":
    unittest.main()
