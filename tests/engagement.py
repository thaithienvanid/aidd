"""What the engagement tests share: the sentence that names the first command, what a coding agent has in context at the start of
a session, and the layouts of a person's Claude Code files (tests/test_engagement.py, tests/test_claude_md_import.py)."""

from __future__ import annotations

import re
from pathlib import Path

import helpers
from aidd import config
from aidd.setup import adoption

ROOT = helpers.ROOT
SNIPPET = (ROOT / "templates" / "AGENTS.snippet.md").read_text(encoding="utf-8")
BLOCK = SNIPPET.split("\n", 3)[3]  # the paragraph after the heading
# The sentence that names the first command, as the block states it.
FIRST_COMMAND = next((s for s in re.split(r"(?<=\.) ", BLOCK) if "`aidd risk --paths" in s), "NO SENTENCE OF THE BLOCK NAMES `aidd risk --paths`")
# The block loads in every session of every harness that reads AGENTS.md, and aidd writes it into a file the person owns, so it
# says the first command and where the skill is, and no more. 811 bytes is about 203 estimated tokens, 0.1% of a 200,000-token
# window. A harness's own limit on the file is far above it (config.SIZES), so this cap is aidd's, for the person's file.
BLOCK_CAP = 811
# The agents whose vendor page does not say they read AGENTS.md at the start of a session (`Load.confirmed`). It only shrinks:
# a harness leaves it when a page says it, with the page in its data.
UNCONFIRMED = frozenset({"cursor", "deepseek-harness", "muse-code", "trae"})
OURS = "# Ours\n\nUse pnpm. Never edit `dist/`.\n"


def options(harness: str, skill: bool = True) -> adoption.InitOptions:
    return adoption.InitOptions(profile="team", ci="none", links=[], approvers=["@org/leads"], harnesses=[harness], test=["pytest", "-q"], skill=skill)


def expand(root: Path, rel: str, seen: tuple[str, ...] = (), depth: int = 4) -> str:
    """The text a harness reads from the file at `rel`: its own, and each `@path` import (outside code spans and fences,
    relative to the file) expanded where Claude Code's page says, to a depth of four."""
    path = root / rel
    if rel in seen or not path.is_file():
        return ""
    text, out, fence = path.read_text(encoding="utf-8"), [], False
    for line in text.splitlines():
        out.append(line)
        if line.strip().startswith(("```", "~~~")):
            fence = not fence
        elif not fence and depth:
            for token in re.findall(r"(?<![\w`@/.-])@(\S+)", re.sub(r"`[^`\n]*`", "", line)):
                target = Path(rel).parent.joinpath(token).as_posix()
                out.append(expand(root, re.sub(r"^(\./)+", "", _normal(target)), (*seen, rel), depth - 1))
    return "\n".join(out)


def _normal(path: str) -> str:
    parts: list[str] = []
    for part in path.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return "/".join(parts)


def read_at_start(root: Path, harness: config.Harness) -> str:
    """The text `harness` has in context at the start of a session: each file in its `loads` that exists, unless a file
    that hides it exists, with its imports."""
    return "\n".join(expand(root, load.file) for load in harness.loads if (root / load.file).is_file() and not any((root / f).exists() for f in load.unless))


FILES = {
    "CLAUDE.md": {"CLAUDE.md": OURS},
    "CLAUDE.md with no final newline": {"CLAUDE.md": OURS.rstrip("\n")},
    "CLAUDE.md in CRLF": {"CLAUDE.md": OURS.replace("\n", "\r\n")},
    ".claude/CLAUDE.md": {".claude/CLAUDE.md": OURS},
    "CLAUDE.local.md alone": {"CLAUDE.local.md": OURS},
    "CLAUDE.md and .claude/CLAUDE.md": {"CLAUDE.md": OURS, ".claude/CLAUDE.md": "dot\n"},
    "CLAUDE.md that already imports": {"CLAUDE.md": "@AGENTS.md\n\n## Claude Code\n\nPlan mode for billing.\n"},
    "CLAUDE.md that names the import in code": {"CLAUDE.md": "Write `@AGENTS.md` to import.\n\n```\n@AGENTS.md\n```\n"},
}


def lay_out(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode())
