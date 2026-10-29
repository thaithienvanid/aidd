"""The real shell judges what runs: the guard holds a line exactly when the shell runs a held command.

Stub programs named like the deploy tools log their name and arguments. Each line of the held and allowed tables runs
under `bash -c` (and `sh -c` where it is POSIX) with the stubs first on PATH. The guard, with the entries `aidd init`
writes for a repository that uses every tool, must deny the line exactly when the log shows a held command ran.
Deliberate evasion, such as a variable, ANSI-C quoting, or command substitution, is the documented limit
(docs/CONFIG.md, `guard.held_commands`): the table records each such form as allowed.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import test_held_commands as held_tables
from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd.guard import pre_tool
from aidd.guard import held_commands
from aidd.guard import delegation
from aidd.guard import edit_check
from aidd.setup import detection
from aidd.setup import adoption
from aidd import config

BASH = shutil.which("bash")
SH = shutil.which("sh")
TOOLS = ("terraform", "tofu", "pulumi", "cdk", "wrangler", "vercel", "netlify", "serverless", "sls", "fly", "flyctl", "firebase", "helm")
# Programs a line may need that a machine may lack (macOS has no timeout, setsid, ionice, chrt, or taskset); a line that
# names a missing one is skipped here and still checked by the guard-only tables. CI runs on Linux, which has them.
WRAPPERS = ("timeout", "busybox", "setsid", "ionice", "chrt", "taskset", "stdbuf", "caffeinate", "nice", "nohup", "flock")
LOG_ARGS = 'for a in "$@"; do printf \' %s\' "$a"; done'

# Lines the reviews named, the wrappers an agent uses, and a few plain neighbours.
EXTRA = (
    "bash -c -l 'terraform apply'",
    "bash -cx 'terraform apply'",
    "sh -ce 'terraform apply' x",
    "sh -c -- 'terraform apply'",
    "bash -lc 'make deploy'",
    "source ./deploy.sh",
    ". ./deploy.sh",
    "./rollout.sh --canary",
    "sh ./rollout.sh",
    "./provision.sh --env production",
    "bash provision.sh",
    "AWS_PROFILE=prod terraform apply",
    "env terraform apply",
    "env FOO=1 terraform destroy",
    "env -u HOME terraform apply",
    "command terraform apply",
    "nohup terraform apply",
    "timeout 5 terraform apply",
    "nice terraform apply",
    "nice -n 5 make deploy",
    "eval 'terraform apply'",
    "terraform plan && terraform apply",
    "terraform plan; echo done",
    "echo terraform apply | cat",
    "npx --yes wrangler@3 deploy --env production",
    # Wrappers with options; `chrt -o 0` because a real-time policy needs privileges the CI runner lacks.
    *(c for c in held_tables.WRAPPER_HELD + held_tables.WRAPPER_ALLOWED if not c.startswith("chrt -f")),
    "chrt -o 0 terraform apply",
    # Reserved words, and programs that run a command.
    "if true; then terraform apply; fi",
    "{ terraform destroy; }",
    "flock /tmp/oracle.lock terraform apply",
)
# Lines the shell must run as held commands, so the oracle cannot pass by holding nothing: a provision script and target
# buy paid infrastructure, and `aidd init` holds them for a person.
MUST_HOLD = ("./provision.sh --env production", "bash provision.sh", "make provision")
# Lines the guard holds although the shell runs nothing held: the accepted over-holds of test_held_commands.py.
OVER_HOLD = held_tables.OVER_HOLD

# Deliberate evasion: the shell runs a held command and the guard does not see it. The limit is documented in
# docs/CONFIG.md under `guard.held_commands`; the platform's protection and the gate stay the control.
EVASION = (
    "t=terraform; $t apply",
    "for c in apply; do terraform $c; done",
    "$'terraform' apply",
    '"$(echo terraform)" apply',
    "`echo terraform` apply",
    'eval "$(echo terraform apply)"',
)


def lines() -> list[str]:
    tables = (held_tables.TOOL_HELD, held_tables.TOOL_ALLOWED, held_tables.FLAG_HELD, held_tables.FLAG_ALLOWED)
    out = [c for t in tables for c in t] + [c for c, _ in held_tables.SHELL_LINES]
    out += [c for c in (*held_tables.INIT_HELD, *held_tables.INIT_ALLOWED) if not c.startswith("sudo ")]  # sudo would prompt
    return list(dict.fromkeys([*out, *EXTRA, *EVASION, *OVER_HOLD]))


def executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def logger(name: str) -> str:
    return f'#!/bin/sh\n{{ printf %s {name}; {LOG_ARGS}; printf "\\n"; }} >> "$ORACLE_LOG"\n'


@unittest.skipUnless(BASH and SH, "the oracle needs bash and sh to judge what runs")
class OracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name).resolve()
        cls.bin, cls.root, cls.logs = base / "bin", base / "repo", base / "logs"
        cls.logs.mkdir()
        for tool in TOOLS:
            executable(cls.bin / tool, logger(tool))
        # make logs its targets only, as the guard reads them; npx runs the program it names, from this folder.
        executable(
            cls.bin / "make",
            '#!/bin/sh\nout=make\nwhile [ $# -gt 0 ]; do\n  case "$1" in -C|-f|-I|-o|-W) shift ;; -*|*=*) ;; *) out="$out $1" ;; esac\n'
            '  shift\ndone\nprintf "%s\\n" "$out" >> "$ORACLE_LOG"\n',
        )
        executable(cls.bin / "npx", '#!/bin/sh\nwhile [ $# -gt 0 ]; do case "$1" in -*) shift ;; *) break ;; esac; done\np=${1%%@*}; shift\nexec "$p" "$@"\n')
        # A login shell reads /etc/profile, which can reset PATH; the shells here skip it, so the stubs stay first.
        executable(cls.bin / "bash", f'#!/bin/sh\nexec {BASH} --noprofile --norc "$@"\n')
        executable(cls.bin / "sh", f'#!/bin/sh\nexec {BASH} --posix --noprofile --norc "$@"\n')
        files = {**held_tables.EVERY_TOOL, "Makefile": held_tables.MAKEFILE}
        for rel, text in files.items():
            (cls.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (cls.root / rel).write_text(text, encoding="utf-8")
        for rel in ("deploy.sh", "scripts/deploy.sh", "rollout.sh", "provision.sh"):
            executable(cls.root / rel, logger(Path(rel).name))
        subprocess.run(["git", "init", "-q", str(cls.root)], check=True)
        cls.entries = detection.detect(cls.root)["held_commands"]
        adoption.init(
            cls.root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[], held_commands=cls.entries)
        )
        cls.cfg = config.load_file(config.CONFIG_PATH, str(cls.root))
        cls.path = f"{cls.bin}{os.pathsep}/usr/bin{os.pathsep}/bin"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def held(self, logged: str) -> list[str]:
        """The logged commands an init entry holds, judged by the entry's match and unless."""
        out = []
        for line in logged.splitlines():
            for e in self.entries:
                if held_commands._gate_matches(e["match"], line) and not any(held_commands._gate_matches([u], line) for u in e.get("unless", [])):
                    out.append(line)
                    break
        return out

    def run_line(self, n: int, shell: list[str], line: str) -> list[str]:
        log = self.logs / f"{n}.log"
        log.write_text("", encoding="utf-8")
        env = {"PATH": self.path, "ORACLE_LOG": str(log), "HOME": str(self.root), "LC_ALL": "C"}
        subprocess.run([*shell, line], cwd=self.root, env=env, capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
        return self.held(log.read_text(encoding="utf-8"))

    def runnable(self, line: str) -> bool:
        needed = set(WRAPPERS) & set(line.split())
        return all(shutil.which(w, path=self.path) for w in needed)

    def test_the_guard_holds_exactly_what_the_shell_runs(self):
        started = time.monotonic()
        mismatches, evasions = [], []
        skipped = [line for line in lines() if not self.runnable(line)]
        if skipped:
            print(f"\nguard oracle: skipped {len(skipped)} lines whose programs this machine lacks", file=sys.stderr)
        runs = [
            (line, shell)
            for line in lines()
            if self.runnable(line)
            for shell in ([BASH, "--noprofile", "--norc", "-c"], [SH, "-c"])
            if shell[0] == BASH or ("source " not in line and "$'" not in line)  # POSIX lines run under sh too
        ]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda nr: self.run_line(nr[0], nr[1][1], nr[1][0]), enumerate(runs)))
        checked = len(runs)
        for (line, shell), ran in zip(runs, results, strict=True):
            guard_holds = held_commands.held_command(self.cfg, line, environ={}) is not None
            name = Path(shell[0]).name
            if line in EVASION:
                evasions.append((line, name, ran, guard_holds))
            elif line in OVER_HOLD:
                if ran or not guard_holds:
                    mismatches.append(f"{name} -c {line!r}: an accepted over-hold, but the shell ran {ran} and the guard held {guard_holds}")
            elif bool(ran) != guard_holds:
                said = "deny" if guard_holds else "allow"
                mismatches.append(f"{name} -c {line!r}: the shell ran {ran or 'nothing held'}, the guard said {said}")
        self.assertEqual(mismatches, [], "\n".join(mismatches))
        held_lines = {line for (line, _), ran in zip(runs, results, strict=True) if ran}
        for line in MUST_HOLD:
            self.assertIn(line, held_lines, f"{line!r} should run a held command")
            self.assertIsNotNone(held_commands.held_command(self.cfg, line, environ={}), line)
        for line, shell, ran, guard_holds in evasions:
            self.assertTrue(ran, f"{shell}: {line!r} should run a held command")
            self.assertFalse(guard_holds, f"{line!r}: the guard now sees it; move it out of EVASION")
        self.assertGreater(checked, 150)
        # A wall-clock cap, not behavior: 10 s was flaky on a loaded machine.
        self.assertLess(time.monotonic() - started, 30.0)


# ---- the write oracle: the guard denies a shell write exactly when real bash writes a path it holds ----------------
#
# Every case below runs twice: through
# `guard.pre_tool_hook`, as the harness sends it, and under real bash in a scenario with a sibling and a nested
# worktree, a folder outside the repository with a symbolic link into it, and a tracked file in an ignored folder.
# The ground truth is what bash changed (each worktree's `git status`), judged path by path with the rule the actor
# meets for an Edit: the lead that holds the autopilot lease meets `delegate`, the developer role its area, and the
# person's own session nothing. So any later parser change is checked against bash.

LEAD_ID, PERSON_ID, DEV = "lead-session-1", "person-session-2", "aidd-team:developer"
W_CODE, W_APP = "src/checkout/rate_limit/limiter.py", "src/app.py"
L, P, D = "lead", "person", "developer"

# (actor, cwd, command[, setup]): the guard must deny exactly when bash writes a path the actor may not edit.
WRITES: tuple[tuple, ...] = (
    # the target's repository, not the cwd's
    (L, "R", "echo y > {SIB}/{CODE}"),
    (L, "R", "echo y > .claude/worktrees/nest/{CODE}"),
    (L, "SIB", "echo y > {R}/{CODE}"),
    (L, "OUT", "echo y > {R}/{CODE}"),
    (L, "OUT", "cd {R} && echo y > {CODE}"),
    (L, "R", "sed -i.bak 's/x/y/' {SIB}/{CODE}"),
    (L, "R", "echo y > {OUT}/scratch.txt"),
    (L, "OUT", "echo y > {OUT}/scratch.txt"),
    (P, "R", "echo y > {SIB}/{CODE}"),
    (D, "R", "echo y > {SIB}/docs/notes.md"),
    (D, "SIB", "echo y > {R}/docs/notes.md"),
    (D, "R", "echo y > .claude/worktrees/nest/docs/notes.md"),
    (D, "R", "echo y > {SIB}/{CODE}"),
    (D, "R", "echo y > {OUT}/scratch.txt"),
    # hard links
    (L, "R", "ln {APP} {OUT}/h && echo y > {OUT}/h"),
    (L, "R", "ln -s {CODE} {OUT}/s"),
    (L, "R", "echo y > {OUT}/h", "link"),
    (L, "R", "cd {OUT} && echo y > h", "link"),
    (L, "R", "rm {OUT}/h", "link"),
    (P, "R", "echo y > {OUT}/h", "link"),
    (D, "R", "echo y > {OUT}/h", "link"),
    # redirects after a group or a substitution
    (L, "R", "(echo y) > {APP}"),
    (L, "R", "echo $(cat {OUT}/payload) > {APP}"),
    (L, "R", "echo `cat {OUT}/payload` > {CODE}"),
    (L, "R", "{{ echo y; }} > {CODE}"),
    (L, "R", "(cd src && echo y) >> {CODE}"),
    (L, "R", "(echo y)>{CODE}"),
    (L, "R", "(echo y) > /dev/null"),
    (D, "R", "(echo y) > docs/notes.md"),
    # case on disk (as the file system spells it: on a case-sensitive one `BUILD/` is a new folder, so a new file in it
    # is new repository content, and on a case-insensitive one it is the ignored build/), and a tracked file in an
    # ignored folder
    (L, "R", "mkdir -p BUILD && echo y > BUILD/KEEP.txt"),
    (L, "R", "mkdir -p BUILD && echo y > BUILD/new.txt"),
    (L, "R", "echo y > build/keep.txt"),
    (L, "R", "mkdir -p build && echo y > build/new.txt"),
    # eval nesting
    *((L, "R", "eval " * n + "'echo y > {APP}'") for n in (2, 50, 400, 1200)),
    # a symbolic link then `..`, groups, here-documents, `cd -`
    (L, "R", "echo y > {OUT}/l/../app.py"),
    (L, "OUT", "echo y > l/../app.py"),
    (L, "R", "cd {OUT}/l/.. && echo y > app.py"),
    (L, "R", "bash -c 'echo y > {APP}'; cat <<EOF\n(((\nEOF"),
    (L, "R", "bash -c 'echo y > {APP}'"),
    (L, "R", "(((true))); bash -c 'echo y > {APP}'"),
    (L, "R", "(cd {OUT}; cat <<EOF\n(\nEOF\n); echo y > {APP}"),
    (L, "R", "(case x in x) cd {OUT};; esac); echo y > {APP}"),
    (L, "R", "case x in (x) cd {OUT};; y) true;; esac; echo y > app.py"),
    (L, "R", "cd {OUT} && cd - && echo y > {APP}"),
    (L, "R", "cd -P {OUT}/l/.. && echo y > app.py"),
    (L, "R", "case x in\nx) cd {OUT};;\nesac\necho y > {APP}"),
    (L, "R", "case x in\nx) true;;\nesac\n(echo y) > {APP}"),
    (L, "R", "aidd autopilot start --work all --session {LEAD}"),
    # honest work in each worktree must pass
    *(
        row
        for wt in ("R", "SIB", "NEST")
        for row in (
            (D, wt, "echo y > {CODE}"),
            (D, wt, "cd src/checkout && echo y > rate_limit/limiter.py && sed -i.bak 's/x/y/' rate_limit/limiter.py"),
            (D, wt, "git add -A && git commit -qm 'feat: x' && git log -1 > /dev/null"),
            (D, wt, "echo y > {OUT}/scratch.txt && mktemp -d > {OUT}/x.txt"),
            (P, wt, "cd src && echo y > checkout/rate_limit/limiter.py"),
            (P, wt, "git commit -qam 'x' && git push -q origin HEAD:feature"),
            (L, wt, "git commit -qam 'x'"),
            (L, wt, "echo y > {OUT}/scratch.txt; (cd {OUT} && echo z > s2.txt)"),
            (P, wt, "aidd autopilot start --work all --session {PERSON}"),
        )
    ),
    (L, "OUT", "echo y > {OUT}/s.txt"),
    # Code the parser cannot read, run by a writer the guard holds (the four closed classes, and brace expansion)
    (L, "R", "$(printf sh) -c 'echo y > {APP}'"),
    (L, "R", "`printf sh` -c 'echo y > {APP}'"),
    (L, "R", "\"$(printf sh)\" -c 'echo y > {APP}'"),
    (L, "R", "FOO=1 $(printf bash) -c 'echo y > {APP}'"),
    (L, "R", "bash <<< 'echo y > {APP}'"),
    (L, "R", "echo 'echo y > {APP}' | bash"),
    (L, "R", "printf 'echo y > %s\\n' {APP} | sh"),
    (L, "R", "bash <<'EOF'\necho y > {APP}\nEOF"),
    (L, "R", "printf 'echo y > {APP}\\n' > {OUT}/s.sh; bash < {OUT}/s.sh"),
    (L, "R", "trap 'echo y > {APP}' EXIT"),
    (L, "R", "printf 'echo y > {APP}\\n' > {OUT}/s.sh; source {OUT}/s.sh"),
    (L, "R", "printf 'echo y > {APP}\\n' > {OUT}/s.sh; . {OUT}/s.sh"),
    (L, "R", "echo {APP} | xargs rm"),
    (L, "R", "find src -name app.py -exec rm {{}} \\;"),
    (L, "R", "find src -name app.py -execdir rm {{}} +"),
    (L, "R", "parallel rm ::: {APP}"),
    (L, "R", "exec rm {APP}"),
    (L, "R", "command rm {APP}"),
    (L, "R", "builtin echo y > {APP}"),
    (L, "R", "rm src/{{app,zz}}.py"),
    (D, "R", "find docs -name notes.md -exec rm {{}} \\;"),
    # Reserved words, a loop over literal words, and find's own writes (the defensive review, 2026-10-22)
    (L, "R", "if true; then rm {APP}; fi"),
    (L, "R", "{{ rm {APP}; }}"),
    (L, "R", 'for f in {APP}; do rm "$f"; done'),
    (L, "R", "find src -name app.py -delete"),
    (D, "R", "find docs -name notes.md -delete"),
    (D, "R", "! rm docs/notes.md"),
    (P, "R", "find src -name cache.db -exec rm {{}} \\;"),
    (P, "R", "find src -name cache.db -delete"),
    (P, "R", 'git restore --staged -- "$f"'),
    # Quoting read exactly: a loop over literal words judged per value, and a quoted find pattern as find's own
    (L, "R", 'for f in {OUT}/a.txt {OUT}/b.txt; do echo y > "$f"; done'),
    (L, "R", 'for f in {OUT}/a.txt {APP}; do echo y > "$f"; done'),
    (L, "R", "for f in '{APP}'; do echo y > \"${{f}}\"; done"),
    (L, "R", 'for f in {OUT}/a.txt; do f={APP}; echo y > "$f"; done'),
    (L, "R", 'for f in {OUT}/a.txt; do read -r f <<< {APP}; echo y > "$f"; done'),
    (L, "R", 'for f in {OUT}/a.txt; do printf -v f %s {APP}; echo y > "$f"; done'),
    (L, "R", "trap 'f={APP}' DEBUG; for f in {OUT}/a.txt; do echo y > \"$f\"; done"),
    (L, "R", 'for f in {OUT}/a.txt; do eval f={APP}; echo y > "$f"; done'),
    (L, "R", 'for f in {OUT}/a.txt; do echo y > "${{f/a.txt/../repo/src/app.py}}"; done'),
    (P, "R", "find src -name '*.pyc' -delete"),
    (D, "R", "echo 'echo y > docs/notes.md' | sh"),
    # xargs and find that run a reader the input or find could make write, or another program: still opaque
    (L, "R", "echo {APP} | xargs -I F sh -c 'echo y > F'"),
    (L, "R", "printf '%s\\n' -o {APP} {OUT}/payload | xargs sort"),
    (L, "R", "echo {OUT}/payload | xargs sort -o {APP} --"),
    (L, "R", "printf '%s\\n' {OUT}/payload {APP} | xargs uniq"),
    (L, "R", "find src -name app.py -exec sort -o {{}} {OUT}/payload \\;"),
    (L, "R", "find src -name app.py -exec cat {{}} \\; -exec rm {{}} \\;"),
    (L, "R", "find src -name app.py -delete -exec cat {{}} +"),
    (D, "R", "printf '%s\\n' -o docs/notes.md {OUT}/payload | xargs sort"),
    (D, "R", "find docs -name notes.md -exec sort -o {{}} {OUT}/payload \\;"),
    # xargs and find that run only a literal reader: the guard reads the line, so a held writer runs it
    *(
        (actor, "R", command)
        for actor in (L, D)
        for command in (
            "git ls-files src | xargs wc -l",
            "git ls-files -z src | xargs -0 grep -n x",
            "git ls-files src | xargs -I{{}} head -n1 {{}}",
            "ls src | xargs -n1 basename",
            "git ls-files src | xargs sort --",
            "printf '%s\\n' -o {APP} | xargs grep -n x",
            "printf '%s\\n' -o {APP} {OUT}/payload | xargs sort --",
            "find src -name app.py -exec grep -l x {{}} +",
            "find src -name '*.py' -exec grep -l x {{}} +",
            "find src -name app.py -execdir wc -l {{}} \\;",
            "find src -type f -exec sort -r -- {{}} +",
        )
    ),
    # Honest work a held writer runs: never denied
    *(
        (actor, "R", command)
        for actor in (L, D)
        for command in (
            "pnpm test",
            "uv run pytest -q",
            'git commit -m "x"',
            "rg foo | head",
            "cat {APP} | jq .",
            "make test",
            "x=$(git rev-parse HEAD); echo $x",
            "git log --oneline | head -5",
            "ls src | wc -l",
            "trap - EXIT",
            'git commit -m "fix; `x` works"',
            "git commit -F - <<'EOF'\n`x` works\n$(not run)\nEOF",
            "git ls-files src | wc -l",
        )
    ),
    (D, "OUT", "echo y > s.txt"),
)
# Where the file system folds case, `BUILD/KEEP.txt` is the tracked build/keep.txt; where it does not, `BUILD/` does not
# exist, bash writes nothing, and the guard still denies the new repository file the line names.
CASE_FOLDING = ((L, "R", "echo y > BUILD/KEEP.txt"),)
# BSD sed (macOS) reads `-i ''` as an empty backup suffix; GNU sed reads `''` as the script.
BSD_SED = ((D, "R", "sed -i '' 's/x/y/' {CODE}"), (D, "R", "sed -i'' 's/x/y/' {CODE}"), (L, "R", "sed -i '' 's/x/y/' {CODE}"))
# Accepted over-holds: the guard denies though bash writes nothing the actor may not edit.
WRITE_OVER_HOLD = {
    "ln {APP} {OUT}/h": "a hard link to repository content is the first half of a write the guard could not see",
    "aidd autopilot start --work all --session {PERSON}": "another session's lease: it writes the git directory, not content",
    "uvx aidd autopilot stop --session={PERSON}": "another session's lease",
    "aidd autopilot stop --s {PERSON}": "another session's lease, by a prefix of `--session`",
    "aidd autopilot start --se {PERSON}": "another session's lease, by a prefix of `--session`",
    "find src -name '*.pyc' -delete": "a held writer's `-delete` by a glob: which files it removes, only the disk says",
    'for f in {APP}; do git checkout -q HEAD -- "$f"; done': "git writes a file only where it differs from HEAD, which only the disk says",
}
WRITES_HELD_ONLY = tuple((L, "R", c) for c in WRITE_OVER_HOLD)
# Known limits (SECURITY.md): bash writes a path the actor may not edit, and the guard does not see it.
WRITE_LIMITS: dict[str, str] = {}


def _scenario(base: Path) -> dict[str, Path]:
    """The repository (with the Spec, the code, and build/keep.txt tracked in an ignored folder), a sibling and a
    nested worktree, and a folder outside with `l` -> repo/src/sub."""
    from helpers import git, make_repo

    root = make_repo(base / "repo", "team", spec="02-normal-feature:specs/SPEC-220.md", status="ready")
    for rel, text in (
        (W_CODE, "x = 1\n"),
        (W_APP, "x = 1\n"),
        ("src/sub/k.py", "k\n"),
        ("docs/notes.md", "n\n"),
        ("build/keep.txt", "k\n"),
        (".gitignore", "build/\n.claude/\n"),
    ):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "add", "-f", "build/keep.txt")
    git(root, "commit", "-qm", "scenario")
    git(root, "worktree", "add", "-q", str(base / "sib"), "-b", "sib")
    git(root, "worktree", "add", "-q", str(root / ".claude" / "worktrees" / "nest"), "-b", "nest")
    return {"R": root, "SIB": base / "sib", "NEST": root / ".claude" / "worktrees" / "nest", "OUT": base / "out", "BIN": base / "bin"}


@unittest.skipUnless(BASH, "the write oracle needs bash")
class WriteOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from aidd.autopilot import lease

        cls.tmp = tempfile.TemporaryDirectory()
        cls.places = _scenario(Path(cls.tmp.name).resolve())
        for stub in ("aidd", "uvx", "pnpm", "uv", "rg", "jq", "make"):  # no-ops: the guard judges the line, the stub writes nothing
            executable(cls.places["BIN"] / stub, "#!/bin/sh\nexit 0\n")
        # GNU parallel's `cmd ::: items` form: run the command once per item.
        executable(
            cls.places["BIN"] / "parallel",
            '#!/bin/sh\nn=0\nfor a in "$@"; do n=$((n+1)); [ "$a" = ":::" ] && break; done\n'
            'i=0; for a in "$@"; do i=$((i+1)); [ $i -gt $n ] && { set -- "$@"; c=""; j=0; for b in "$@"; do j=$((j+1)); [ $j -lt $n ] && c="$c $b"; done; sh -c "$c $a"; }; done\n',
        )
        cls.heads = {
            k: subprocess.run(["git", "rev-parse", "HEAD"], cwd=cls.places[k], capture_output=True, text=True, check=True).stdout.strip()
            for k in ("R", "SIB", "NEST")
        }
        lease.take_lease(cls.places["R"], work="all", session_id=LEAD_ID)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fill(self, text: str) -> str:
        p = self.places
        return text.format(R=p["R"], SIB=p["SIB"], NEST=p["NEST"], OUT=p["OUT"], CODE=W_CODE, APP=W_APP, LEAD=LEAD_ID, PERSON=PERSON_ID)

    def event(self, actor: str, cwd: Path, command: str) -> dict:
        ev = {
            "session_id": PERSON_ID if actor != L else LEAD_ID,
            "cwd": str(cwd),
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": command},
        }
        if actor == D:
            ev["agent_type"] = DEV
        return ev

    def reset(self, setup: str | None) -> None:
        for key, head in self.heads.items():
            subprocess.run(["git", "reset", "-q", "--hard", head], cwd=self.places[key], check=True)
            subprocess.run(["git", "clean", "-fdq"], cwd=self.places[key], check=True)
        out = self.places["OUT"]
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir()
        os.symlink(self.places["R"] / "src" / "sub", out / "l")
        (out / "payload").write_text("y\n", encoding="utf-8")
        if setup == "link":
            os.link(self.places["R"] / W_APP, out / "h")

    def status(self) -> dict[str, set[str]]:
        found = {}
        for key in ("R", "SIB", "NEST"):
            raw = subprocess.run(["git", "status", "--porcelain=v1", "-z", "-uall"], cwd=self.places[key], capture_output=True, text=True, check=True).stdout
            found[key] = {e[3:] for e in raw.split("\0") if len(e) > 3}
        return found

    def forbidden(self, actor: str, key: str, rel: str) -> bool:
        """Whether the actor's Edit of `rel` in worktree `key` is denied: the ground truth for a path bash wrote."""
        top = str(self.places[key])
        ev = self.event(actor, self.places[key], "")
        if actor == L:
            cfg = config.load_file(config.CONFIG_PATH, top)
            return delegation.delegate_check(top, rel, ev, cfg) is not None
        if actor == D:
            return edit_check.check_agent_edit(top, rel, ev)[0] == "deny"
        return False

    def judge(self, actor: str, cwd_key: str, raw: str, setup: str | None) -> tuple[bool, list[str]]:
        """(the guard denies, the paths bash wrote that the actor may not edit)."""
        import io
        import json

        self.reset(setup)
        command, cwd = self.fill(raw), self.places[cwd_key]
        out = io.StringIO()
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(self.event(actor, cwd, command))), out)
        denies = bool(out.getvalue()) and json.loads(out.getvalue())["hookSpecificOutput"].get("permissionDecision") == "deny"
        before = self.status()
        env = {"PATH": f"{self.places['BIN']}{os.pathsep}/usr/bin{os.pathsep}/bin", "HOME": str(self.places["OUT"]), "LC_ALL": "C"}
        subprocess.run([BASH, "--noprofile", "--norc", "-c", command], cwd=cwd, env=env, capture_output=True, timeout=20, stdin=subprocess.DEVNULL)
        after = self.status()
        wrote = [f"{k}:{rel}" for k in after for rel in sorted(after[k] - before[k]) if self.forbidden(actor, k, rel)]
        return denies, wrote

    def test_the_guard_denies_exactly_the_writes_bash_makes(self):
        folds = (self.places["R"] / "BUILD" / "KEEP.txt").exists()
        rows = [*WRITES, *(BSD_SED if sys.platform == "darwin" else ()), *(CASE_FOLDING if folds else ())]
        mismatches = []
        for row in rows:
            actor, cwd_key, raw = row[:3]
            denies, wrote = self.judge(actor, cwd_key, raw, row[3] if len(row) > 3 else None)
            if raw in WRITE_LIMITS:
                if not wrote or denies:
                    mismatches.append(f"{actor} {raw[:120]!r}: a known limit, but bash wrote {wrote} and the guard denied {denies}; update WRITE_LIMITS")
            elif denies != bool(wrote):
                mismatches.append(f"{actor} in {cwd_key}: {raw[:120]!r}: bash wrote {wrote or 'nothing held'}, the guard said {'deny' if denies else 'allow'}")
        self.assertEqual(mismatches, [], "\n".join(mismatches))

    def test_the_accepted_over_holds_write_nothing(self):
        for actor, cwd_key, raw in WRITES_HELD_ONLY:
            denies, wrote = self.judge(actor, cwd_key, raw, None)
            self.assertTrue(denies, raw)
            self.assertEqual(wrote, [], raw)


if __name__ == "__main__":
    unittest.main()
