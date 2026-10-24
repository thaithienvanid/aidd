"""A team's day without a stray denial (V21): each profile runs one Spec as a team would, through the guard. Every
Specify role writes its own work, Spec approval freezes it, two roles implement their own Tasks side by side, the
component's threat model stays living, and a revision after approval reopens the frozen files for their owners. Every
denial left is one an experienced lead would also make, and each names its one next step: the role that owns the
file, the Task scope, or the command that reopens the Spec."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import aidd_subprocess, check_edit, example, git, make_repo

from aidd.workitems import decision_records

SPEC = "specs/SPEC-220.md"
TEST = "tests/checkout/test_rate_limit.py"
TECH = "specs/SPEC-220/tech-spec-limits.md"
MODEL = "docs/security/threat-models/checkout.md"
CODE = "src/checkout/rate_limit/limiter.py"
GUIDE = "docs/limits/rate-limits.md"
ME = "me@example.com"


def spec_text() -> str:
    """The rate-limit Spec, with two Tasks for two roles: the developer's limiter and the tech writer's guide."""
    return example("02-normal-feature")["head_files"][SPEC].replace(
        "    assignee: agent:claude-code\n",
        "    assignee: agent:developer\n  - id: TASK-221\n    title: Document the limits\n    scope: [docs/limits/]\n    assignee: agent:tech-writer\n",
        1,
    )


class TeamDay:
    """One day of one team, on `PROFILE`; a subclass names the profile."""

    PROFILE = "team"
    SIGNED = False

    def setUp(self):
        env = mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "AIDD_SPEC"}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.root = make_repo(Path(tmp) / "repo", self.PROFILE, branch=None, approvers=[f"email:{ME}"])
        git(self.root, "config", "user.email", ME)
        if self.SIGNED:
            self.sign(Path(tmp))
        git(self.root, "checkout", "-qb", "spec/SPEC-220")
        (self.root / SPEC).parent.mkdir(parents=True, exist_ok=True)
        (self.root / SPEC).write_text(spec_text(), encoding="utf-8")

    def sign(self, tmp: Path) -> None:
        """Under audited only signed local approvals count: a key, vouched for on the base branch."""
        key = tmp / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        for k, v in (("gpg.format", "ssh"), ("user.signingkey", str(key))):
            git(self.root, "config", k, v)
        signers = self.root / ".aidd" / "allowed_signers"
        signers.write_text(f"{ME} {Path(f'{key}.pub').read_text(encoding='utf-8').strip()}\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "chore: vouch for the Approver's key")

    def decide(self, role, rel):
        return check_edit(str(self.root), rel, role)

    def allowed(self, cases):
        for role, rel in cases:
            with self.subTest(role=role, rel=rel):
                decision, why = self.decide(role, rel)
                self.assertEqual(decision, "allow", why)

    def denied(self, cases):
        """Each denial with the words of its one next step."""
        for role, rel, step in cases:
            with self.subTest(role=role, rel=rel):
                decision, why = self.decide(role, rel)
                self.assertEqual(decision, "deny", why)
                self.assertIn(step, why)

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def approve(self) -> None:
        git(self.root, "add", "-A")
        if git(self.root, "status", "--porcelain"):
            git(self.root, "commit", "-qm", "spec: SPEC-220")
        head = git(self.root, "rev-parse", "HEAD").strip()
        decision_records.record_local_approval(decision_records.approve_spec_line("SPEC-220", head), str(self.root))

    def test_the_day(self):
        # Specify: each role writes its own work first, and files it before sign-off.
        self.allowed([("architect", TECH), ("security-engineer", MODEL), ("verifier", TEST), ("product-designer", "specs/SPEC-220/design/limits.html")])
        self.assertIn("`frozen: false`", self.decide("security-engineer", MODEL)[1])  # a component's model is living
        self.write(TECH, "# Tech spec for SPEC-220\n")
        self.write(MODEL, "# Threat model: checkout\n\nFirst written for SPEC-220.\n")
        self.write(TEST, "def test_limit():\n    assert False\n")
        filed = f"docs:\n  - kind: tech-spec\n    path: {TECH}\n  - kind: threat-model\n    path: {MODEL}\n    frozen: false\ntests:\n"
        self.write(SPEC, (self.root / SPEC).read_text(encoding="utf-8").replace("tests:\n", filed, 1))
        self.approve()

        # Implement: two roles side by side, each in its own Task; the frozen files stay frozen; the model stays living.
        self.allowed([("developer", CODE), ("tech-writer", GUIDE), ("security-engineer", MODEL)])
        self.denied(
            [
                ("developer", GUIDE, "belongs to the tech-writer role"),
                ("verifier", TEST, "aidd revise SPEC-220"),
                ("architect", TECH, "aidd revise SPEC-220"),
                ("developer", "src/other/x.py", "handoff note"),
                ("developer", TEST, "belongs to the verifier role"),
            ]
        )

        # A test turns out wrong: the Spec reopens in one step, and only the test's owner changes it.
        run = aidd_subprocess("revise", "SPEC-220", "the limit is per card, not per user", cwd=self.root)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.allowed([("verifier", TEST), ("architect", TECH)])
        self.denied([("developer", TEST, "belongs to the verifier role")])

        # Approved again on the new hash: frozen again.
        self.approve()
        self.denied([("verifier", TEST, "aidd revise SPEC-220")])
        self.allowed([("developer", CODE)])


@unittest.skipUnless(shutil.which("git"), "git is required")
class SoloDayTests(TeamDay, unittest.TestCase):
    PROFILE = "solo"


@unittest.skipUnless(shutil.which("git"), "git is required")
class TeamDayTests(TeamDay, unittest.TestCase):
    PROFILE = "team"


@unittest.skipUnless(shutil.which("git") and shutil.which("ssh-keygen"), "git and ssh-keygen are required")
class AuditedDayTests(TeamDay, unittest.TestCase):
    PROFILE = "audited"
    SIGNED = True


if __name__ == "__main__":
    unittest.main()
