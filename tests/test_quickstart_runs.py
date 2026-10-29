"""docs/QUICKSTART.md runs as written: every `sh` block on the page, in order, in a temporary folder, with `aidd`
resolving to this checkout.

The walk follows the page, step by step. Each command runs in `sh` from the folder the one before it left, and must exit
as the page says it does: 0, but where the page says otherwise (EXPECTED_EXIT). Three steps on the page are a person's,
not a command's, so the test does them the way the page names:

- A table of `Replace` and `With` code edits the Spec in place, so the test makes each replacement in the Spec the last
  `aidd new spec` wrote.
- A `text` block holds the words a person types at their coding agent's prompt, such as `approve SPEC-1`. Without an
  agent, the page names the terminal command for the same decision, so the test runs that command.
- A person's decision, `aidd approve spec` or `aidd land`, asks `[y/N]` at an interactive terminal. The test runs it on
  a pseudo-terminal and answers `y`, as the person does.

The "With a team" section reuses steps 1, 3, and 5 in a second repository, so the test walks those steps again with the
team profile's `aidd init`, and then the section's own blocks.

Nothing on the page needs the network, a platform, or a real coding agent today, so NOT_RUN is empty. A command added
later that does needs an entry there with its reason, and the test says which command it is.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from helpers import ROOT

from aidd.platforms import local_land

QUICKSTART = ROOT / "docs" / "QUICKSTART.md"
# Commands the walk never runs, each with its reason: a command's first words, and why. Empty, because every command on
# the page runs offline in a temporary folder.
NOT_RUN: dict[str, str] = {}
# The steps the "With a team" section takes again in its second repository, after its own `aidd init`.
TEAM_STEPS = (1, 3, 5)
# How long one command may take: `aidd test` and `aidd land` run the practice repository's tests.
COMMAND_SECONDS = 300

BLOCK = re.compile(r"^```(\w*)\n(.*?)^```[ \t]*$", re.S | re.M)
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")


def expected_exit(command: str) -> int:
    """The exit code the page gives `command`, from CLI.md's exit codes."""
    words = command.split()
    if words[:3] == ["aidd", "new", "spec"] and "--paths" in words and "--force" not in words:
        return 1  # the fast lane needs no Spec, so it writes nothing and exits 1
    if words[:2] == ["aidd", "gate"]:
        return 0 if "--approvals" in words else 3  # pending: only the approvals are left
    return 0


@dataclass
class Part:
    kind: str  # "sh", "text", or "table"
    body: str = ""
    rows: list[tuple[str, str]] = field(default_factory=list)


def steps(text: str) -> dict[str, list[Part]]:
    """Each `##` section of the page, by its heading, with its code blocks and its replace tables in page order."""
    out: dict[str, list[Part]] = {}
    for section in re.split(r"^## ", text, flags=re.M)[1:]:
        heading, _, body = section.partition("\n")
        parts: list[tuple[int, Part]] = [(m.start(), Part(m.group(1), m.group(2))) for m in BLOCK.finditer(body)]
        outside = BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), body)
        rows: list[tuple[str, str]] = []
        start = 0
        for m in re.finditer(r"^\|.*$", outside, re.M):
            cells = [c.strip() for c in m.group(0).strip().strip("|").split("|")]
            if len(cells) == 3 and cells[1].startswith("`") and cells[2].startswith("`"):
                rows.append((re.match(r"`([^`]*)`", cells[1]).group(1), re.match(r"`([^`]*)`", cells[2]).group(1)))  # type: ignore[union-attr]
                start = start or m.start()
        if rows:
            parts.append((start, Part("table", rows=rows)))
        out[heading.strip()] = [p for _, p in sorted(parts, key=lambda x: x[0])]
    return out


def commands(block: str) -> list[str]:
    """The commands in a `sh` block, one a line, with a heredoc's body and a `\\` continuation kept with its line."""
    out: list[str] = []
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        cmd = lines[i]
        while cmd.endswith("\\") and i + 1 < len(lines):
            i += 1
            cmd = cmd[:-1] + lines[i]
        here = HEREDOC.search(cmd)
        if here:
            while i + 1 < len(lines):
                i += 1
                cmd += "\n" + lines[i]
                if lines[i].strip() == here.group(1):
                    break
        if cmd.strip() and not cmd.lstrip().startswith("#"):
            out.append(cmd)
        i += 1
    return out


def terminal_command(typed: str, page: str) -> str:
    """The command a person runs in a terminal for the words `typed` at the agent's prompt, which the page names too."""
    words = typed.split()
    if words[:1] == ["approve"] and len(words) > 1:
        command = "aidd approve spec " + " ".join(f"specs/{w}.md" for w in words[1:])
        if local_land.typed_words_for(command) == typed and f"`{command}`" in page:
            return command
    raise AssertionError(f"the page asks a person to type {typed!r}, and names no terminal command the test can run for it")


def at_a_terminal(script: str, cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    """Run `script` in `sh` on a pseudo-terminal, as a person at their own terminal, and answer `y` to its `[y/N]`."""
    import pty
    import select

    leader, follower = pty.openpty()
    p = subprocess.Popen(["sh", "-c", script], cwd=cwd, env=env, stdin=follower, stdout=follower, stderr=follower, start_new_session=True)
    os.close(follower)
    out, answered, deadline = b"", False, time.monotonic() + COMMAND_SECONDS
    try:
        while True:
            ready, _, _ = select.select([leader], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                p.kill()
                break
            try:
                chunk = os.read(leader, 4096)
            except OSError:  # Linux: the terminal closed with the last process
                break
            if not chunk:
                break
            out += chunk
            if not answered and b"[y/N]" in out:
                os.write(leader, b"y\n")
                answered = True
    finally:
        os.close(leader)
    return p.wait(timeout=COMMAND_SECONDS), out.decode("utf-8", errors="replace")


class Walk:
    """One run through the page's commands: the folder each command starts in, and the Spec the last one wrote."""

    def __init__(self, case: unittest.TestCase, home: Path, page: str):
        self.case, self.page, self.cwd, self.spec = case, page, home, ""
        self.marker = home.parent / f".{home.name}-cwd"
        bin_dir = home.parent / "bin"
        bin_dir.mkdir(exist_ok=True)
        launcher = bin_dir / "aidd"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m aidd "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
        self.env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}

    def run(self, command: str) -> None:
        if any(command.startswith(prefix) for prefix in NOT_RUN):
            return  # listed with its reason in NOT_RUN
        script = f"{command}\nrc=$?\npwd > '{self.marker}'\nexit $rc\n"
        if local_land.typed_words_for(command):
            code, out = at_a_terminal(script, self.cwd, self.env)
        else:
            p = subprocess.run(
                ["sh", "-c", script],
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=COMMAND_SECONDS,
            )
            code, out = p.returncode, p.stdout + p.stderr
        self.case.assertEqual(code, expected_exit(command), f"`{command}` in {self.cwd} exited {code}:\n{out[-3000:]}")
        self.cwd = Path(self.marker.read_text(encoding="utf-8").strip())
        words = command.split()
        if words[:3] == ["aidd", "new", "spec"] and "--force" in words:
            self.spec = words[3]

    def edit_the_spec(self, rows: list[tuple[str, str]]) -> None:
        self.case.assertTrue(self.spec, "the page edits a Spec before any `aidd new spec --force` wrote one")
        path = self.cwd / "specs" / f"{self.spec}.md"
        text = path.read_text(encoding="utf-8")
        for old, new in rows:
            self.case.assertEqual(text.count(old), 1, f"{path.name} holds `{old}` {text.count(old)} times, so the table's edit is not one place")
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    def take(self, parts: list[Part]) -> None:
        for part in parts:
            if part.kind == "sh":
                for command in commands(part.body):
                    self.run(command)
            elif part.kind == "table":
                self.edit_the_spec(part.rows)
            elif part.kind == "text":
                self.run(terminal_command(part.body.strip(), self.page))
            else:
                self.case.fail(f"the page has a `{part.kind or 'plain'}` code block the walk cannot take; make it `sh` or `text`, or teach the walk")


def numbered(sections: dict[str, list[Part]]) -> dict[int, list[Part]]:
    return {int(m.group(1)): parts for heading, parts in sections.items() if (m := re.match(r"(\d+)\. ", heading))}


@unittest.skipIf(os.name == "nt", "the page's commands are sh, and a person's terminal is a pseudo-terminal")
@unittest.skipUnless(shutil.which("git") and shutil.which("sh"), "git and sh are required")
class QuickstartRunsTests(unittest.TestCase):
    def setUp(self):
        self.page = QUICKSTART.read_text(encoding="utf-8")
        self.sections = steps(self.page)
        self.steps = numbered(self.sections)
        tmp = tempfile.TemporaryDirectory(prefix="aidd-quickstart-")
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def walk(self, name: str) -> Walk:
        home = self.tmp / name
        home.mkdir()
        return Walk(self, home, self.page)

    def test_the_solo_walk_lands_the_change_on_main(self):
        self.assertGreaterEqual(len(self.steps), 6, "the page has numbered steps 1 to 6")
        walk = self.walk("solo")
        for number in sorted(self.steps):
            with self.subTest(step=number):
                walk.take(self.steps[number])
        landed = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"], cwd=walk.cwd, capture_output=True, text=True, check=True).stdout.split()
        self.assertIn("app/discount.py", landed, "the change is on main once `aidd land` ran")

    def test_the_team_walk_passes_the_gate_with_the_dry_run_approvals(self):
        team = [parts for heading, parts in self.sections.items() if not heading[:1].isdigit() and any(p.kind == "sh" for p in parts)]
        self.assertEqual(len(team), 1, "one unnumbered section on the page holds commands: the team one")
        (init, *rest) = [p for p in team[0] if p.kind == "sh"]
        walk = self.walk("team")
        walk.take(self.steps[TEAM_STEPS[0]])
        walk.take([init])
        walk.run("git add -A && git commit -m 'chore: adopt aidd'")  # the page says "Commit it."
        for number in TEAM_STEPS[1:]:
            with self.subTest(step=number):
                walk.take(self.steps[number])
        walk.take(rest)

    def test_every_command_the_walk_skips_is_on_the_page(self):
        """An entry no command on the page starts with is stale: take it out, so NOT_RUN never grows."""
        run = [c for parts in self.sections.values() for p in parts if p.kind == "sh" for c in commands(p.body)]
        for prefix in NOT_RUN:
            with self.subTest(prefix=prefix):
                self.assertTrue(any(c.startswith(prefix) for c in run), prefix)


class PageReadingTests(unittest.TestCase):
    def test_a_heredoc_and_a_continuation_stay_one_command(self):
        block = "cat > f <<EOF\na b\nEOF\naidd gate \\\n  --base main\n# a comment\n"
        self.assertEqual(commands(block), ["cat > f <<EOF\na b\nEOF", "aidd gate   --base main"])

    def test_the_exit_codes_follow_cli_md(self):
        self.assertEqual(expected_exit("aidd new spec SPEC-1 --title t --paths a.py"), 1)
        self.assertEqual(expected_exit("aidd new spec SPEC-1 --title t --paths a.py --force"), 0)
        self.assertEqual(expected_exit("aidd gate --base main"), 3)
        self.assertEqual(expected_exit("aidd gate --base main --approvals ../a.json"), 0)

    def test_a_typed_decision_maps_to_the_command_the_page_names(self):
        self.assertEqual(terminal_command("approve SPEC-1", "run `aidd approve spec specs/SPEC-1.md` there"), "aidd approve spec specs/SPEC-1.md")
        with self.assertRaises(AssertionError):
            terminal_command("approve SPEC-1", "no command named here")


if __name__ == "__main__":
    unittest.main()
