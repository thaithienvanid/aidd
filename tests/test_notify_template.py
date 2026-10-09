"""templates/github/aidd-notify.yml: the CI notifier with no server. Its shape follows the repository's workflow rules
(every action pinned by SHA with its version, least privilege, no `${{ }}` inside a run script, secrets only in the
env of the one job that posts), and its jq programs turn the gate's status, the approver waits, and the metrics into
the lines it posts. actionlint and zizmor check it in CI (ci.yml)."""

import json
import re
import shutil
import subprocess
import unittest

from helpers import ROOT

from aidd import metrics

TEMPLATE = ROOT / "templates" / "github" / "aidd-notify.yml"
TEXT = TEMPLATE.read_text(encoding="utf-8")


def jobs() -> dict[str, str]:
    """Each job's text, by name (the two-space-indented keys under `jobs:`)."""
    body = TEXT.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z][\w-]*):\n", body)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def jq_program(anchor: str) -> str:
    """The single-quoted jq program that follows `anchor` in the template, with the YAML block indent removed."""
    start = TEXT.index(anchor)
    open_quote = TEXT.index("'", start)
    close_quote = TEXT.index("'", open_quote + 1)
    return TEXT[open_quote + 1 : close_quote]


def jq(program: str, *args: str, stdin: str = "null", slurp: bool = False) -> str:
    cmd = ["jq", "-r", *(["-s"] if slurp else ["-n"] if stdin == "null" else []), *args, program]
    run = subprocess.run(cmd, input=stdin, capture_output=True, text=True, encoding="utf-8", check=True)
    return run.stdout.strip()


class ShapeTests(unittest.TestCase):
    def test_every_action_is_pinned_by_sha_with_its_version(self):
        uses = re.findall(r"(?m)^\s+(?:- )?uses: (\S+)(.*)", TEXT)
        self.assertTrue(uses)
        for ref, comment in uses:
            self.assertRegex(ref, r"@[0-9a-f]{40}$", ref)
            self.assertRegex(comment, r"# v\d+\.\d+\.\d+", ref)

    def test_no_expression_inside_a_run_script(self):
        for name, job in jobs().items():
            for script in re.findall(r"(?ms)^\s+run: \|\n(.*?)(?=^\s{6}- |\Z)", job):
                self.assertNotIn("${{", script, name)
            for line in re.findall(r"(?m)^\s+run: (?!\|)(.*)$", job):
                self.assertNotIn("${{", line, name)

    def test_least_privilege_and_secrets_only_where_it_posts(self):
        self.assertIn("\npermissions: {}\n", TEXT)
        found = jobs()
        self.assertEqual(set(found), {"status", "digest", "weekly", "post"})
        for name, job in found.items():
            self.assertIn("permissions:", job, name)
            self.assertNotIn("write", re.search(r"(?ms)permissions:.*?(?=\n    \w)", job).group(0), name)
            self.assertEqual("secrets." in job, name == "post", name)
        self.assertIn("permissions: {}", found["post"])
        self.assertNotIn("actions/checkout", found["post"])
        # The webhook secrets live on an environment of their own, which only the post job names.
        for name, job in found.items():
            self.assertEqual(bool(re.search(r"(?m)^    environment: aidd-notify\b", job)), name == "post", name)
        # Every checkout keeps no credentials; the digest reads pull request heads in a step with no token.
        self.assertEqual(TEXT.count("actions/checkout@"), TEXT.count("persist-credentials: false"))
        step = found["digest"].split("- name: What waits on an approver", 1)[1].split("- name:", 1)[0]
        self.assertNotIn("TOKEN", step)

    def test_it_never_approves_and_posts_nothing_without_a_webhook(self):
        self.assertNotIn("/aidd approve", TEXT.split("\nname:", 1)[1])
        self.assertIn("nothing to post", TEXT)
        self.assertIn('if [ -n "$SLACK_WEBHOOK_URL" ]', TEXT)
        self.assertIn('if [ -n "$TEAMS_WEBHOOK_URL" ]', TEXT)


@unittest.skipUnless(shutil.which("jq"), "jq is required")
class MessageTests(unittest.TestCase):
    PR = json.dumps({"number": 12, "title": "Albums", "html_url": "https://github.com/o/r/pull/12"})

    def line(self, state: str, description: str, context: str = "aidd/gate") -> str:
        status = json.dumps({"context": context, "state": state, "description": description})
        program = jq_program('jq -n -r --argjson s "$now"')
        return jq(program, "--argjson", "s", status, "--argjson", "pr", self.PR, "--arg", "who", "@alice, @org/leads")

    def test_the_status_line_names_the_spec_the_wait_and_who(self):
        self.assertEqual(
            self.line("pending", "pending: spec_approval: Spec SPEC-9 needs approval of hash 3f2c1a9"),
            "SPEC-9 waits for Spec approval: @alice, @org/leads -> https://github.com/o/r/pull/12",
        )
        self.assertEqual(
            self.line("pending", "pending: merge_approval: needs 1 approval(s) on head 3f2c1a9, has 0", "aidd/gate (advisory)"),
            "PR #12 waits for Merge approval: @alice, @org/leads [aidd/gate (advisory)] -> https://github.com/o/r/pull/12",
        )
        self.assertEqual(
            self.line("pending", "pending: tests: no test evidence for head 3f2c1a9 yet"),
            "PR #12 waits: no test evidence for head 3f2c1a9 yet -> https://github.com/o/r/pull/12",
        )
        self.assertEqual(
            self.line("failure", "fail: scope: src/pay.py is outside every Task's scope"),
            "PR #12 is red on aidd/gate: src/pay.py is outside every Task's scope -> https://github.com/o/r/pull/12",
        )
        self.assertEqual(
            self.line("success", "pass: normal route, every gate holds"), "PR #12 passed aidd/gate: it may merge -> https://github.com/o/r/pull/12"
        )

    def test_an_unchanged_status_is_not_announced_again(self):
        program = jq_program("if jq -e '.[0] as $n")
        same = [{"context": "aidd/gate", "state": "pending", "description": "d"}] * 2
        run = subprocess.run(["jq", "-e", program], input=json.dumps(same), capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 0)
        changed = [same[0], {"context": "aidd/gate", "state": "pending", "description": "older"}]
        run = subprocess.run(["jq", "-e", program], input=json.dumps(changed), capture_output=True, text=True, check=False)
        self.assertNotEqual(run.returncode, 0)

    def test_the_digest_groups_waits_by_approver(self):
        program = jq_program("jq -s -r 'add")
        main = [{"what": "SPEC-3 waits for Merge approval on its head commit", "approvers": ["@alice"], "waiting_minutes": 90, "url": "u0"}]
        prs = [{"what": "SPEC-9 waits for Spec approval of its current hash", "approvers": ["@alice", "@bob"], "waiting_minutes": None, "url": "u9"}]
        out = jq("add // [] | " + program.split("add // [] | ", 1)[1], stdin=json.dumps(main) + "\n" + json.dumps(prs), slurp=True)
        self.assertEqual(
            out.splitlines(),
            [
                "@alice: SPEC-3 waits for Merge approval on its head commit (90 min) -> u0; SPEC-9 waits for Spec approval of its current hash -> u9",
                "@bob: SPEC-9 waits for Spec approval of its current hash -> u9",
            ],
        )

    def test_the_weekly_summary_reads_aidd_metrics_json(self):
        def ev(change, ts, **kw):
            return {"repo": "o/r", "change": change, "ts": ts, "head_sha": "a" * 40, "failed_rules": [], "route": "major"} | kw

        events = [
            ev("1", "2026-09-21T10:00:00Z", decision="pending", pending_rules=["merge_approval"]),
            ev("1", "2026-09-21T10:03:00Z", decision="pass", pending_rules=[]),
        ]
        program = jq_program("jq -r --arg repo")
        out = jq(program, "--arg", "repo", "o/r", "--arg", "since", "2026-09-21", stdin=json.dumps(metrics.summarize(events)))
        lines = out.splitlines()
        self.assertEqual(lines[0], "aidd weekly for o/r since 2026-09-21: 1 changes (pass 1)")
        self.assertIn("Merge approval 3.0/3.0", lines[2])
        self.assertEqual(lines[3], "major changes merge-approved within 10 minutes: 1 of 1 (look again: o/r#1)")

    def test_webhook_payloads_escape_slack_and_wrap_teams(self):
        post = jobs()["post"]
        slack = re.search(r"jq -n --arg t \"\$TEXT\" '(\{text:.*?\})'", post).group(1)
        payload = json.loads(jq(slack, "--arg", "t", "A <!channel> & B"))
        self.assertEqual(payload, {"text": "A &lt;!channel&gt; &amp; B"})
        teams = re.search(r"jq -n --arg t \"\$TEXT\" '(\{type: \"message\"[^']*)'", post).group(1)
        card = json.loads(jq(teams, "--arg", "t", "line one\nline two"))
        attachment = card["attachments"][0]
        self.assertEqual(attachment["contentType"], "application/vnd.microsoft.card.adaptive")
        self.assertEqual([b["text"] for b in attachment["content"]["body"]], ["line one", "line two"])


if __name__ == "__main__":
    unittest.main()
