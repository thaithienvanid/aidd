"""A file of the product scope as the person approved it: its front matter and its body at the commit that recorded the approval.

It is the Intent approval's lookup (`intent_checks.stamped_version`) with this file's loose pair, `approved_by` and `approved_at`,
in the file's one place. The commit holds it with an `Approved-by:` line of the person and an `Approves:` line that names the file's
path exactly, such as `Approves: product/prd.md`, and changes nothing in the file but the pair. The two lines are the ones an
Intent's approval carries, so a commit that approves an Intent (`Approves: INTENT-1`) holds no approval of this file, and the other
way round: each lookup matches its own id. A trailer is a branch's record, and no proof of who said yes.
"""

from __future__ import annotations

from pathlib import Path

from aidd.kernel import documents, git
from aidd.workitems import approval_commits, intent_checks

APPROVAL = intent_checks.Stamp(None, "approved_by", "approved_at", "product-scope.schema.json", ("$defs", "approved_at"), None)
BY, AT = APPROVAL.by, APPROVAL.at
# The most commits of a file's history that the search for its last approval reads.
MAX_READ = 200


def approved_text(root: Path, rel: str, data: dict, tip: str = "HEAD") -> tuple[dict, str] | None:
    """The front matter and the body of the file `rel` as its `approved_by` approved it at `approved_at`, or None when no
    approval stands. `data` is the file's front matter, now or at some commit, and `tip` the commit whose history holds the file."""
    return intent_checks.stamped_version(root, [rel], data, tip, APPROVAL)


def last_approved_text(root: Path, rel: str, tip: str = "HEAD") -> tuple[dict, str] | None:
    """The file `rel` as the newest approval in its history says yes to it, or None when none does. It reads the history and never
    the stamps the file holds today, so removing or moving them hides nothing. It reads each commit's file once and looks up each
    distinct `approved_by` and `approved_at` once, so the git processes grow with the history and not with its square. Parsing a file once for each distinct stamp is not bounded that way."""
    try:
        history = git.log_fields([tip, "--", rel], ["%H"], str(root), check=False)
    except git.GitError:
        return None
    seen: set[tuple[str, str]] = set()
    for (sha,) in history[:MAX_READ]:
        try:
            data, _ = documents.split_front_matter(approval_commits.file_at(str(root), sha, rel) or "", rel)
        except documents.DocumentError:
            continue
        stamp = (str(data.get(BY) or ""), str(data.get(AT) or "")) if isinstance(data, dict) else ("", "")
        if not all(stamp) or stamp in seen:  # each distinct stamp is looked up once, so a stamp kept through many commits costs one lookup
            continue
        seen.add(stamp)
        if (found := approved_text(root, rel, data, tip)) is not None:
            return found
    return None
