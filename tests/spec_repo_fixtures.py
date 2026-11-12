"""A repository on `main` with a passing `unit` suite, and the config and Spec texts the `aidd test` control tests build
on: each command runs `python -c <code>`, so a test decides by its exit code alone."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from helpers import RepoTemplateCase, git

from aidd import testing

PY = sys.executable.replace("\\", "/")
PASS, FAIL = "raise SystemExit(0)", "raise SystemExit(1)"


def config_text(*tests: tuple, smoke: tuple[str, ...] = (), extra: str = "") -> str:
    """A config whose `tests` are (name, code, when_changed) triples, with the folder it runs in (`runs_in`) as a fourth item when it has
    one: each runs `python -c <code>`; those named in `smoke` are smoke commands."""
    lines = ['aidd_version: "1.0.0"', "profile: team", "owners:", "  approvers: [bob]"]
    if tests:
        lines.append("tests:")
        for name, code, when, *folder in tests:
            lines.append(f"  - name: {name}")
            lines.append(f"    command: {json.dumps([PY, '-c', code])}")
            if folder:
                lines.append(f"    runs_in: {json.dumps(folder[0])}")
            if when:
                lines.append(f"    when_changed: {json.dumps(when)}")
            if name in smoke:
                lines.append("    smoke: true")
    else:
        lines.append("tests: []")
    return "\n".join(lines) + "\n" + extra


EMERGENCY = """emergency:
  severity: sev3
  type: outage
  commander: "email:bob@example.com"
  incident: INC-1
  backfill_due: "2026-12-01"
"""


def spec_text(
    sid: str,
    *,
    status: str = "draft",
    scope: str = "app/",
    code: str = PASS,
    new_behavior: bool = False,
    route: str = "normal",
    files: tuple[str, ...] = (),
    when_changed: tuple[str, ...] = (),
    runs_in: str = "",
) -> str:
    """A Spec with one Task over `scope`, frozen `files` (default `checks/<id>.py`), and one command `check` that runs `code`, in the
    folder `runs_in` when it names one."""
    return f"""---
type: spec
id: {sid}
title: Greeting says hello
status: {status}
change_type: feat
route: {route}
confidence: high
open_questions: []
trace_id: {sid.lower()}
rollback: Revert the PR.
risk:
  summary: Adds a greeting function.
  dimensions: []
  irreversible: false
tasks:
  - id: T1
    title: Implement greet
    scope: [{scope}]
tests:
  files: {json.dumps(list(files) or [f"checks/{sid}.py"])}
  commands:
    - name: check
      command: {json.dumps([PY, "-c", code])}
{f"      runs_in: {json.dumps(runs_in)}" + chr(10) if runs_in else ""}      new_behavior: {str(new_behavior).lower()}
{f"      when_changed: {json.dumps(list(when_changed))}" + chr(10) if when_changed else ""}{EMERGENCY if route == "emergency" else ""}---
## Context
Tiny example.
## Acceptance
Invariant: greet() returns "hello".
"""


class RepoCase(RepoTemplateCase):
    """A repository on `main` with a passing `unit` suite; each test starts from its own copy."""

    @classmethod
    def build_template(cls, root: Path) -> None:
        git(root, "init", "-q", "-b", "main")
        for k, v in (("user.email", "me@example.com"), ("user.name", "Me"), ("commit.gpgsign", "false")):
            git(root, "config", k, v)
        cls.put(root, ".gitignore", "__pycache__/\n/.aidd/*/\n")
        cls.put(root, ".aidd/config.yaml", config_text(("unit", PASS, [])))
        cls.put(root, "app/__init__.py", "")
        cls.commit(root, "base")

    @staticmethod
    def put(root: Path, rel: str, text: str) -> None:
        path = Path(root, rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    @staticmethod
    def commit(root: Path, message: str) -> None:
        git(root, "add", "-A")
        git(root, "commit", "-qm", message, "--allow-empty")

    def fresh(self) -> None:
        """Start this subtest again from the template."""
        shutil.rmtree(self.root)
        shutil.copytree(self._template, self.root, symlinks=True)

    def branch(self, name: str = "feat") -> None:
        git(self.root, "switch", "-qc", name)

    def run_aidd(self, **kwargs):
        evidence, notes = testing.run_tests(repo=str(self.root), base="main", out_dir=str(self.root / ".aidd" / "evidence"), **kwargs)
        return evidence, notes

    @staticmethod
    def ran(evidence: dict) -> set[tuple[str, str]]:
        return {(r["name"], r["red_green"]) for r in evidence["results"]}
