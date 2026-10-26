"""The helper rule's shell half (guard/helper_runs.py): a subagent that is not an aidd-team role only reads, so the guard
lets it run only the read programs on its list, without their options that write or start a program.

What holds, pinned here:
(a) each form in WRITES is denied for a helper, and bash really writes a file when it runs that form, so each case is a
    real write the rule stops, never a guess (BACKLOG R91: a helper wrote six source files through `python3 - <<EOF`);
(b) each command in RUNS, which writes, runs code, or changes what later commands run, is denied, and the denial names
    the next step: the reads a helper may run, or a hand-off to a role or the main session;
(c) the plain reads a helper needs still pass;
(d) a role keeps the documented limit, a program that writes by itself, so its interpreter runs pass.
"""

import io
import json
import shutil
import subprocess
import unittest

from helpers import RepoTemplateCase, git, make_repo

from aidd.guard import pre_tool

BASH = shutil.which("bash")
HELPER = "Explore"
ROLE = "aidd-team:developer"
OUT = "src/written.py"

# Each form writes OUT when bash runs it, with the interpreter it needs.
WRITES = (
    ("python3", "python3 - <<'EOF'\nopen('src/written.py', 'w').write('x')\nEOF"),
    ("python3", "python3 -c \"open('src/written.py', 'w').write('x')\""),
    ("python3", "echo \"open('src/written.py', 'w').write('x')\" | python3"),
    ("python3", "python3 <<< \"open('src/written.py', 'w').write('x')\""),
    ("python3", "env python3 -c \"open('src/written.py', 'w').write('x')\""),
    ("python3", "timeout 10 python3 -c \"open('src/written.py', 'w').write('x')\""),
    ("python3", 'sh -c "python3 -c \'open(\\"src/written.py\\", \\"w\\").write(\\"x\\")\'"'),
    ("python3", "cd src && python3 -c \"open('written.py', 'w').write('x')\""),
    ("python3", 'printf \'open("src/written.py", "w").write("x")\' > ../helper-runs.py; python3 ../helper-runs.py'),
    ("perl", 'perl -e \'open(F, ">src/written.py"); print F "x"\''),
    ("ruby", 'ruby -e \'File.write("src/written.py", "x")\''),
    ("node", 'node -e \'require("fs").writeFileSync("src/written.py", "x")\''),
    ("node", "node - <<'EOF'\nrequire('fs').writeFileSync('src/written.py', 'x')\nEOF"),
    ("awk", 'awk \'BEGIN { print "x" > "src/written.py" }\''),
    ("awk", "awk 'BEGIN { system(\"touch src/written.py\") }'"),
    ("bash", "printf 'touch src/written.py' > ../helper-runs.sh; bash ../helper-runs.sh"),
    ("bash", "printf 'touch src/written.py' > ../helper-runs.sh; chmod +x ../helper-runs.sh; ../helper-runs.sh"),
)

# Commands a helper may not run, each for its own reason in helper_runs: not a read, a path, a variable, or an option.
RUNS = (
    "python3 -m unittest -q",
    "make test",
    "npm test",
    "man git",
    "env grep -rn limiter src",
    "timeout 10 grep -rn limiter src",
    "/usr/bin/git status --short",
    "/opt/homebrew/bin/grep -rn limiter src",
    "PATH=../bin grep -rn limiter src",
    "hash -p ../helper-runs.sh grep",
    "BASH_ENV=../helper-runs.sh bash -c 'cat src/limiter.py'",
    "bash --rcfile ../helper-runs.sh -c 'cat src/limiter.py'",
    "bash ../helper-runs.sh",
    "echo 'cat src/limiter.py' | sh",
    "for f in src/limiter.py; do cat $f; done",
    "printf -v PATH ../bin",
    "awk '{print $1}' src/limiter.py",
    "sed -i s/1/2/ src/limiter.py",
    "sed -n 1w../out src/limiter.py",
    "sed -n -f ../script.sed src/limiter.py",
    "find src -name '*.py' -exec touch {} +",
    "find src -delete",
    "sort -o src/written.py src/limiter.py",
    "sort --out=src/written.py src/limiter.py",
    "sort -uo src/written.py src/limiter.py",
    "sort -t -- -o src/written.py src/limiter.py",
    "sort * ",
    "find src -name *.py",
    "tree -R src",
    "file -C -m ../magic",
    "sed --expression=1w../out src/limiter.py",
    "echo $(python3 -c 'print(1)')",
    "[[ 1 -eq 1 ]]",
    "test -v x",
    "while read f; do cat $f; done < ../list",
    "command python3 -c 1",
    "git stash push",
    "git stash",
    "git reflog --output=src/written.py",
    "git remote add origin ../elsewhere",
    "uniq src/limiter.py src/written.py",
    "printf x | uniq - src/written.py",
    "uniq -c -- src/limiter.py src/written.py",
    "rg --pre ../helper-runs.sh limiter src",
    "git -c core.pager=cat log -1",
    "git --exec-path=.. log -1",
    "git diff --output=src/written.py",
    "git grep -O limiter",
    "git branch topic",
    "git help log",
    "aidd gate",
    "aidd list --html ../page.html",
    "aidd init",
)

READS = (
    "grep -rn limiter src",
    "grep -rn python3 src",
    "rg -n limiter src",
    "cat src/limiter.py",
    "head -5 src/limiter.py && tail -5 src/limiter.py && wc -l src/limiter.py",
    "ls -la src && stat src/limiter.py",
    "sed -n 1,5p src/limiter.py",
    "sed -n -e 1p -e '$p' src/limiter.py",
    "sed -n '/x/,/y/p' src/limiter.py",
    "find src -name '*.py' -type f",
    "sort src/limiter.py | uniq -c",
    "cut -d= -f1 src/limiter.py | tr a-z A-Z",
    "jq . schemas/roles.json",
    "diff src/limiter.py src/limiter.py",
    "git log --oneline -3",
    "git -C src --no-pager show HEAD --stat",
    "git diff --stat HEAD && git status --short",
    "git blame src/limiter.py",
    "git branch --show-current",
    "sh -c 'cat src/limiter.py'",
    "bash -ec 'grep -rn limiter src'",
    "which python3",
    "cd src && cat limiter.py",
    "if grep -q x src/limiter.py; then echo found; fi",
    "grep -rn limiter src > /dev/null 2>&1",
    "aidd list --mine",
    "aidd gate --paths src/limiter.py",
    "aidd gate --paths=src/limiter.py",
    "git merge-base HEAD HEAD",
    "git --version",
    "git stash list && git worktree list && git remote -v && git tag -l",
    "git reflog -5",
    "ls src | xargs wc -l",
    "find src -name '*.py' -exec wc -l {} +",
    "command -v git",
    "[ -f src/limiter.py ] && echo yes",
    "uniq -f 1 src/limiter.py",
    "sed -s -n 1p src/limiter.py",
    "tac src/limiter.py | sha256sum",
    "printf '%s\\n' limiter",
)


class HelperRunsTests(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md", status="ready")
        (root / "src").mkdir(exist_ok=True)
        (root / "src" / "limiter.py").write_text("x = 1\n", encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "the Spec and the code")

    def decision(self, command: str, agent: str) -> dict:
        event = {"cwd": str(self.root), "tool_name": "Bash", "tool_input": {"command": command}, "agent_type": agent, "session_id": "s1"}
        out = io.StringIO()
        self.assertEqual(pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out), 0)
        return json.loads(out.getvalue())["hookSpecificOutput"] if out.getvalue() else {}

    def denied(self, command: str) -> str:
        out = self.decision(command, HELPER)
        self.assertEqual(out.get("permissionDecision"), "deny", out)
        reason = out["permissionDecisionReason"]
        self.assertIn("may only read (the loop contract's helper rule", reason)
        return reason

    def test_a_helper_is_denied_each_form_that_really_writes(self):
        for program, command in WRITES:
            with self.subTest(command=command):
                self.denied(command)
                if not BASH or not shutil.which(program):
                    continue  # the denial holds without bash; only the proof that the form writes needs it
                (self.root / OUT).unlink(missing_ok=True)
                subprocess.run([BASH, "-c", command], cwd=self.root, capture_output=True, timeout=30, check=False)
                self.assertTrue((self.root / OUT).exists(), f"the form wrote nothing, so it proves no write: {command}")

    def test_a_helper_runs_nothing_off_the_read_list_and_is_told_what_works(self):
        for command in RUNS:
            with self.subTest(command=command):
                reason = self.denied(command)
                self.assertIn("A helper runs only these reads", reason)
                self.assertIn("grep", reason)
                self.assertIn("Hand a test run or a script back the same way", reason)

    def test_the_denial_names_each_reason_and_the_reads_once(self):
        reason = self.denied("python3 -c 1; make test")
        self.assertIn("`python3` is not a read program; `make` is not a read program:", reason)
        self.assertEqual(reason.count("A helper runs only these reads"), 1, reason)

    def test_a_helper_runs_no_powershell(self):
        event = {
            "cwd": str(self.root),
            "tool_name": "PowerShell",
            "tool_input": {"command": "Get-Content src/limiter.py"},
            "agent_type": HELPER,
            "session_id": "s1",
        }
        out = io.StringIO()
        self.assertEqual(pre_tool.pre_tool_hook(io.StringIO(json.dumps(event)), out), 0)
        decision = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(decision.get("permissionDecision"), "deny", decision)
        self.assertIn("a helper runs no PowerShell", decision["permissionDecisionReason"])

    def test_a_helper_still_reads(self):
        for command in READS:
            with self.subTest(command=command):
                self.assertNotEqual(self.decision(command, HELPER).get("permissionDecision"), "deny", command)

    def test_a_role_keeps_the_documented_limit(self):
        for command in ("python3 -c 'print(1)'", "python3 -m unittest -q", "node -e 'console.log(1)'", "bash tools/check.sh"):
            with self.subTest(command=command):
                self.assertNotEqual(self.decision(command, ROLE).get("permissionDecision"), "deny", command)


if __name__ == "__main__":
    unittest.main()
