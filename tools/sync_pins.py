"""Copy the pins Dependabot moves into the templates that ship them, so a bump is one command.

Dependabot bumps the action SHAs in .github/workflows/ and the root action.yml, and the Claude Code CLI in
tools/mermaid/package-lock.json. It never scans templates/github/, so tests/test_version.py fails until the
templates carry the same pins. This script writes them:

- each `uses: owner/action@<sha> # <tag>` in templates/github/*.yml takes the SHA and tag the workflows and
  action.yml pin for that action;
- templates/github/aidd-diagnose.yml takes the locked CLI version and its linux-x64 integrity.

Run `python3 tools/sync_pins.py`, or `--check` to list what differs and exit 1 without writing. It finds the
repository from its own path (`--root` overrides it), and stops when it finds no workflow pin or no template, so a
wrong folder never reads as in sync. It reads and writes only these files, makes no network call, and uses the
standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

USES = re.compile(r"(uses: )([\w.-]+/[\w./-]+)@([0-9a-f]{40})((?:[ \t]+#[^\n]*)?)")
VERSION = re.compile(r'(CLAUDE_CODE_VERSION: ")([^"]*)(")')
INTEGRITY = re.compile(r"(CLAUDE_CODE_INTEGRITY: )(\S+)")


def source_pins(root: Path) -> dict[str, tuple[str, str]]:
    """The SHA and its tag comment for each action, from the files Dependabot updates. Two SHAs, or two different tag
    comments, for one action stop it, so the answer never depends on which file was read first."""
    pins: dict[str, set[tuple[str, str]]] = {}
    for f in [*sorted((root / ".github" / "workflows").glob("*.yml")), root / "action.yml"]:
        if f.is_file():
            for m in USES.finditer(f.read_text(encoding="utf-8")):
                pins.setdefault(m.group(2), set()).add((m.group(3), m.group(4).strip()))
    if not pins:
        raise SystemExit(f"sync_pins: no `uses: owner/action@<sha>` line in {root}/.github/workflows or action.yml; is --root right?")
    split = {a: sorted(p) for a, p in pins.items() if len({sha for sha, _ in p}) > 1 or len({tag for _, tag in p if tag}) > 1}
    if split:
        raise SystemExit(f"sync_pins: the workflows pin an action to several SHAs or tags; make them agree first: {split}")
    return {a: (sorted(p)[0][0], max(tag for _, tag in p)) for a, p in pins.items()}


def synced_template(text: str, pins: dict[str, tuple[str, str]]) -> str:
    def pin(m: re.Match[str]) -> str:
        if m.group(2) not in pins:
            return m.group(0)  # an action only the templates use: nothing to copy from
        sha, tag = pins[m.group(2)]
        return f"{m.group(1)}{m.group(2)}@{sha}{' ' + tag if tag else ''}"

    return USES.sub(pin, text)


def synced_diagnose(text: str, root: Path) -> str:
    lock = json.loads((root / "tools" / "mermaid" / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    native = lock["node_modules/@anthropic-ai/claude-code-linux-x64"]
    if native["version"] != lock["node_modules/@anthropic-ai/claude-code"]["version"]:
        raise SystemExit("sync_pins: the lock's claude-code and claude-code-linux-x64 versions differ; fix the lock first")
    text = VERSION.sub(lambda m: f"{m.group(1)}{native['version']}{m.group(3)}", text)
    return INTEGRITY.sub(lambda m: f"{m.group(1)}{native['integrity']}", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy the workflow and lock-file pins into templates/github/.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1], help="the repository root (default: the one holding this script)")
    parser.add_argument("--check", action="store_true", help="list what differs and exit 1, without writing")
    args = parser.parse_args(argv)
    root = args.root
    pins = source_pins(root)
    templates = sorted((root / "templates" / "github").glob("*.yml"))
    if not templates:
        raise SystemExit(f"sync_pins: no template in {root}/templates/github; is --root right?")
    changed = []
    for f in templates:
        old = f.read_text(encoding="utf-8")
        new = synced_template(old, pins)
        if f.name == "aidd-diagnose.yml":
            new = synced_diagnose(new, root)
        if new != old:
            changed.append(f.relative_to(root).as_posix())
            if not args.check:
                f.write_text(new, encoding="utf-8", newline="\n")
    if not changed:
        print("sync_pins: the templates already carry the workflows' and the lock's pins")
        return 0
    verb = "differs" if args.check else "updated"
    for name in changed:
        print(f"{verb}: {name}")
    if args.check:
        print("run `python3 tools/sync_pins.py` to write them", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
