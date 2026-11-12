"""A person's approval of an Intent, from their own terminal: `aidd approve <ID>...`. The commit that records an approval
asks in the harness, and a headless run cannot answer the prompt, so `aidd status` offers the person this command. aidd
sets `approval: {by, at}` itself and commits the Intent alone, as the person, with their `Approved-by` and `Approves` lines.
Nothing a run saved is ever applied, so a crafted patch or file can commit nothing under the person's name."""

import fnmatch
import os
import re
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from helpers import SUBPROCESS_TIMEOUT, aidd_subprocess, git, hermetic_environ, open_work, src_pythonpath

from aidd import config
from aidd.kernel import documents
from aidd.risk import commands, harness_rules, rules
from aidd.workitems import approval

PERSON = "Maya Lee <maya@users.noreply.github.com>"
INTENT = (
    '---\ntype: intent\nid: INTENT-{n}\ntitle: "Plan"\noutcome: "g by 2027-01-01"\n{request}{approval}'
    "phases: [{{id: P1, name: p, specs: [{{id: SPEC-{n}, title: one}}]}}]\n---\n\n## Problem\n"
)
APPROVAL = f'approval: {{by: "{PERSON}", at: "2026-11-10T09:12:00Z"}}\n'
REQUEST = 'request: "specs/requests/2026-11-08-claims.md"\n'
WAITING = "Show me INTENT-1 to approve, then wait for my answer"
TERMINAL = sys.platform != "win32"


def in_a_terminal(cwd: Path, *args: str) -> tuple[int, str]:
    """`aidd <args>` with a terminal on stdin and stdout, as a person's own shell gives it: its exit code and its output."""
    import pty

    main, child = pty.openpty()
    env = {**hermetic_environ(), "PYTHONPATH": src_pythonpath()}
    proc = subprocess.Popen([sys.executable, "-m", "aidd", *args], cwd=cwd, stdin=child, stdout=child, stderr=child, env=env)
    os.close(child)
    out, deadline = b"", time.monotonic() + SUBPROCESS_TIMEOUT
    while time.monotonic() < deadline:
        ready, _, _ = select.select([main], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(main, 4096)
            except OSError:
                break  # the child closed its end
            if not chunk:
                break
            out += chunk
        elif proc.poll() is not None:
            break
    os.close(main)
    return proc.wait(timeout=SUBPROCESS_TIMEOUT), out.decode("utf-8", errors="replace")


@unittest.skipUnless(shutil.which("git") and TERMINAL, "git and a terminal are required")
class ApproveCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "repo"
        (self.root / "product" / "intents").mkdir(parents=True)
        (self.root / "specs").mkdir()
        (self.root / ".aidd").mkdir()
        (self.root / ".aidd/config.yaml").write_text('aidd_version: "1.0.0"\nprofile: solo\n', encoding="utf-8")
        (self.root / ".gitignore").write_text(config.OUTPUT_IGNORE + "\n", encoding="utf-8")  # as `aidd init` writes it
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.name", "Maya Lee")
        git(self.root, "config", "user.email", "maya@users.noreply.github.com")
        self.file = self.root / "product" / "intents" / "INTENT-1.md"
        self.file.write_text(INTENT.format(n=1, request="", approval=""), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "plan")

    def tearDown(self):
        self.tmp.cleanup()

    def split(self, count: int) -> None:
        """Intents 1 to `count` of one request, committed and waiting for their approval."""
        for n in range(1, count + 1):
            (self.root / f"product/intents/INTENT-{n}.md").write_text(INTENT.format(n=n, request=REQUEST, approval=""), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "the split")

    def approve(self, *ids: str) -> subprocess.CompletedProcess:
        """`aidd approve` as a person runs it, in their own terminal."""
        code, out = in_a_terminal(self.root, "approve", *ids)
        return subprocess.CompletedProcess(["aidd", "approve", *ids], code, out, out)

    def test_the_command_refuses_with_no_terminal_a_net_for_an_agents_plain_shell_call(self):
        head = git(self.root, "rev-parse", "HEAD")
        done = aidd_subprocess("approve", "INTENT-1", cwd=self.root, env=hermetic_environ())
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Run this in your own terminal", done.stderr)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), head)
        self.assertEqual(self.step()["code"], "intent.approve")

    def step(self) -> dict:
        return open_work(self.root)[0]["next"]

    def last_commit_files(self) -> list[str]:
        return git(self.root, "show", "--name-only", "--format=", "HEAD").split()

    def test_status_offers_the_command_beside_the_words_for_the_chat(self):
        step = self.step()
        self.assertEqual((step["code"], step["words"]), ("intent.approve", WAITING), "the chat's words stay the person's first way")
        self.assertIn("aidd approve INTENT-1", step["what"])
        shown = aidd_subprocess("status", cwd=self.root, env=hermetic_environ())
        self.assertIn("aidd approve INTENT-1", shown.stdout)

    def test_the_command_records_the_persons_approval_as_their_commit(self):
        done = self.approve("INTENT-1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(git(self.root, "log", "-1", "--format=%an <%ae>"), PERSON)
        message = git(self.root, "log", "-1", "--format=%B")
        self.assertEqual(message.splitlines()[0], "INTENT-1: approved")
        self.assertEqual(message.strip().split("\n\n")[-1].splitlines(), [f"Approved-by: {PERSON}", "Approves: INTENT-1"])
        self.assertEqual(self.last_commit_files(), ["product/intents/INTENT-1.md"])
        self.assertEqual(git(self.root, "status", "--porcelain"), "")
        data, _ = documents.split_front_matter(self.file.read_text(encoding="utf-8"), "INTENT-1")
        self.assertEqual(data["approval"]["by"], PERSON)
        self.assertNotEqual(self.step()["code"], "intent.approve", "a commit with the two lines records the approval")
        checked = aidd_subprocess("validate", "product/intents/INTENT-1.md", cwd=self.root, env=hermetic_environ())
        self.assertNotIn("no hold", checked.stdout + checked.stderr)

    def test_the_commit_holds_the_intent_alone_when_another_file_is_staged(self):
        (self.root / "staged.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "staged.txt")
        self.assertEqual(self.approve("INTENT-1").returncode, 0)
        self.assertEqual(self.last_commit_files(), ["product/intents/INTENT-1.md"])
        self.assertEqual(git(self.root, "diff", "--cached", "--name-only"), "staged.txt", "the staged file stays staged, uncommitted")

    def test_one_command_records_every_intent_of_a_request_in_one_commit(self):
        self.split(3)
        steps = [item["next"] for item in open_work(self.root)]
        command = "aidd approve INTENT-1 INTENT-2 INTENT-3"
        self.assertTrue(all(command in step["what"] for step in steps), steps)
        done = self.approve("INTENT-1", "INTENT-2", "INTENT-3")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.last_commit_files(), [f"product/intents/INTENT-{n}.md" for n in (1, 2, 3)])
        self.assertEqual([item for item in open_work(self.root) if item["next"]["code"] == "intent.approve"], [])

    def test_the_command_refuses_what_it_must_not_record(self):
        """Each refusal commits nothing and names the next step."""
        approved = INTENT.format(n=2, request="", approval="")
        cases = (
            # (what, the setup, the ids, a fragment of the refusal)
            ("an Intent already approved", lambda: self.commit_approved(approved), ("INTENT-2",), "waits for no approval"),
            ("an id that is no work item's", lambda: None, ("$(x)",), "no work item id"),
            ("an id no Intent holds", lambda: None, ("INTENT-9",), "no Intent has the id"),
            (
                "an edit no commit holds",
                lambda: self.file.write_text(self.file.read_text().replace('"g by', '"big g by'), encoding="utf-8"),
                ("INTENT-1",),
                "no commit holds",
            ),
            ("an agent's git identity", lambda: git(self.root, "config", "user.name", "dependabot[bot]"), ("INTENT-1",), "agent or a bot"),
        )
        for what, setup, ids, fragment in cases:
            with self.subTest(what):
                setup()
                head = git(self.root, "rev-parse", "HEAD")
                done = self.approve(*ids)
                self.assertNotEqual(done.returncode, 0, done.stdout)
                self.assertIn(fragment, done.stderr)
                self.assertEqual(git(self.root, "rev-parse", "HEAD"), head, "a refusal commits nothing")
                git(self.root, "checkout", "-q", "--", ".")
                git(self.root, "config", "user.name", "Maya Lee")

    def commit_approved(self, text: str) -> None:
        """INTENT-2 in two commits, as the hold needs: the Intent, then a commit that changes only its approval."""
        path = self.root / "product/intents/INTENT-2.md"
        path.write_text(text, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "plan INTENT-2")
        path.write_text(text.replace("outcome:", APPROVAL + "outcome:"), encoding="utf-8")
        git(self.root, "commit", "-q", "-a", "-m", "INTENT-2: approved", "--trailer", f"Approved-by: {PERSON}", "--trailer", "Approves: INTENT-2")

    def test_a_saved_patch_is_never_applied_whatever_it_holds(self):
        """A crafted `approve.patch`, the shape a run once saved, changes neither the command nor what it commits."""
        (self.root / ".env.local").write_text("TOKEN=x\n", encoding="utf-8")
        (self.root / "product/intents/INTENT-2.md").write_text(INTENT.format(n=2, request="", approval=""), encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "more")
        key = Path(self.tmp.name) / "id_ed25519"
        key.write_text("PRIVATE\n", encoding="utf-8")
        patches = {
            "a copy from an absolute path": f"diff --git a/product/intents/INTENT-1.md b/product/intents/INTENT-1.md\ncopy from {key}\ncopy to product/intents/INTENT-1.md\n",
            "a rename from .env.local": "diff --git a/.env.local b/product/intents/INTENT-1.md\nrename from .env.local\nrename to product/intents/INTENT-1.md\n",
            "a waiting Intent outside the split": "diff --git a/product/intents/INTENT-2.md b/product/intents/INTENT-2.md\n--- a/product/intents/INTENT-2.md\n+++ b/product/intents/INTENT-2.md\n",
            "a hunk that changes the goal": (
                "diff --git a/product/intents/INTENT-1.md b/product/intents/INTENT-1.md\n--- a/product/intents/INTENT-1.md\n+++ b/product/intents/INTENT-1.md\n"
                '@@ -6 +6 @@\n-outcome: "g by 2027-01-01"\n+outcome: "anything"\n'
            ),
        }
        for what, patch in patches.items():
            with self.subTest(what):
                saved = self.root / ".aidd/returns/INTENT-1/approve.patch"
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_text(patch, encoding="utf-8")
                self.assertNotIn("approve.patch", str(open_work(self.root)))
                self.assertNotIn("git apply", str(open_work(self.root)))
        tracked = self.root / "specs/approve.patch"
        tracked.write_text(patches["a hunk that changes the goal"], encoding="utf-8")
        git(self.root, "add", "-A", "-f")
        git(self.root, "commit", "-q", "-m", "a tracked patch")
        self.assertEqual(self.approve("INTENT-1").returncode, 0)
        self.assertEqual(self.last_commit_files(), ["product/intents/INTENT-1.md"])
        diff = git(self.root, "diff", "HEAD~1", "HEAD", "--unified=0", "--", "product/intents/INTENT-1.md").splitlines()
        changed = [ln for ln in diff if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
        self.assertEqual(sorted(ln.split(":")[0] for ln in changed), ["+approval"], changed)
        self.assertEqual((self.root / ".env.local").read_text(encoding="utf-8"), "TOKEN=x\n")
        self.assertIn('outcome: "g by 2027-01-01"', self.file.read_text(encoding="utf-8"))

    def test_the_command_only_takes_plain_ids(self):
        self.assertEqual(approval.person_command(["INTENT-1", "INTENT-2"]), "aidd approve INTENT-1 INTENT-2")
        for bad in ([], ["$(x)"], ["INTENT-1", "a;b"], ["-INTENT-1"]):
            with self.subTest(ids=bad):
                self.assertEqual(approval.person_command(bad), "")


# Every spelling a shell may run `aidd approve` by.
SPELLINGS = (
    "aidd approve INTENT-1",
    "./scripts/aidd approve INTENT-1",
    "/opt/tools/bin/aidd approve INTENT-1 INTENT-2",
    "env aidd approve INTENT-1",
    "python aidd.pyz approve INTENT-1",
    "python3 /tmp/aidd.pyz approve INTENT-1",
    "uvx aidd approve INTENT-1",
    "python3 -m aidd approve INTENT-1",
)


def written_asks(fmt: str, entry: str, line: str) -> bool:
    """Whether one ask rule a glob or regex format holds matches `line`, as that harness reads it."""
    if harness_rules.FORMATS[fmt].match == "regex":
        return re.fullmatch(entry, line) is not None
    return fnmatch.fnmatchcase(line, entry.removeprefix("Bash(").removesuffix(")"))


class ApproveAsksTests(unittest.TestCase):
    def test_every_spelling_asks_in_aidd_and_in_every_harness_that_reads_a_pattern_anywhere(self):
        """aidd's own reading asks for each spelling. Each harness whose rules match anywhere in the line asks for each
        one too; a leading-words harness (Codex, Qwen Code) holds the bare and launcher forms, and the command refuses
        without a terminal: a net for an agent's plain shell call, not for one that makes a pseudo-terminal."""
        rs = rules.rule_set(None)
        patterns = harness_rules.harness_patterns(rs, "main")
        approve = [p for p in patterns if "approve" in p and p.startswith(("aidd", "*aidd", "python", "uv", "pipx"))]
        for line in SPELLINGS:
            with self.subTest(line=line):
                self.assertEqual(commands.command_level(rs, line, cwd=None)["level"], "ask")
        for fmt, form in harness_rules.FORMATS.items():
            entries = harness_rules._entries(fmt, approve)
            for line in SPELLINGS if form.match != "words" else ():
                with self.subTest(format=fmt, line=line):
                    self.assertTrue(any(written_asks(fmt, e, line) for e in entries), entries)
            with self.subTest(format=fmt):
                self.assertEqual(harness_rules.unwritten(fmt, ["aidd approve *"]), [], "every format holds the bare form")


if __name__ == "__main__":
    unittest.main()
