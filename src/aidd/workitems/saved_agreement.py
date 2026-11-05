"""An agreement a run could not record. The commit that records an Intent's agreement asks in the harness, and a headless
run cannot answer the prompt, so the run saves the edit as `.aidd/returns/<ID>/agree.patch` and stops. This gives the person
the one command that records it, in their own terminal, with their own git identity. aidd never runs it."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from aidd.workitems import ids

PATCH = ".aidd/returns/{id}/agree.patch"
# A path this command names: the Intent's file, from the config's folder, so its characters stay plain.
PLAIN_PATH = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/-]*")


def person_command(item_id: str, path: str) -> str:
    """The command for the Intent `item_id` at `path`, or "" when either holds text a shell line should not carry. It
    applies the saved patch to that file alone, adds it, and commits that file alone (`--only`, so anything else already
    staged stays out) with the person's own git identity as the `Agreed-by:` trailer, the value `agreed_by` holds."""
    if not ids.is_id(item_id) or not PLAIN_PATH.fullmatch(path) or ".." in path.split("/"):
        return ""
    patch, file = shlex.quote(PATCH.format(id=item_id)), shlex.quote(path)
    return (
        f"git apply --include={file} {patch} && git add {file} && "
        f'git commit --only -m "{item_id}: agreed" -m "Agreed-by: $(git config user.name) <$(git config user.email)>" -- {file}'
    )


def add_to(root: Path, answer: dict) -> None:
    """Give each Intent that waits for its agreement, and has a saved patch, the person's command as its next step's words,
    and in its sentence, which the plain-text status shows."""
    for item in answer["items"]:
        step = item.get("next")
        if item["type"] != "intent" or not step or step["code"] != "intent.agree" or not ids.is_id(item["id"]):
            continue
        if not (root / PATCH.format(id=item["id"])).is_file() or not (command := person_command(item["id"], str(item["path"]))):
            continue
        step["words"] = command
        step["what"] += f"; a run saved the edit that records it, so run this yourself, in the repository's top folder: {command}"
