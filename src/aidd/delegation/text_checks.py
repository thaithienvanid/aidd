"""The checks of the text the delegate reads, whatever the action: no text claims an approval or hides a character, and
every text the accept covers reaches the delegate whole (parts.py).

The delegate is a model, so the asker can shape what it reads. Each check here can only defer."""

from __future__ import annotations

from aidd import workitems
from aidd.delegation import parts, policy
from aidd.delegation.check import Check
from aidd.kernel import documents, git, secret_patterns


def _plain(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def tripwire(check: Check, texts: dict[str, str], hidden: bool = True) -> None:
    """No text claims an approval, addresses an approver or a model, or (with `hidden`) holds a character a reader cannot
    see. A phrase is found as written and as the secret scan reads text: folded to NFKC, with the format characters out,
    so a fullwidth or zero-width spelling of it is found too. The fold serves only the comparison; the text stays as it is."""
    words = policy.builtin()["tripwires"]
    for where, text in texts.items():
        check.scanned.add(where)
        written, folded = _plain(text), _plain(secret_patterns.comparable(text or ""))
        if hit := next((w for w in words if w in written or w in folded), None):
            check.defer("text_claims_approval", f"{where} says {hit!r}")
            return
        if hidden and (found := workitems.hidden_characters(text or "")):
            check.defer("text_hides_characters", f"{where} holds {', '.join(found[:3])}")
            return


def fit(check: Check, texts: dict[str, str]) -> None:
    """Every text the delegate reads is held whole: a text past its cap, or a diffstat past its file count, defers and is
    named, so a cap that decides says so."""
    over = [
        f"{name} has {len(text):,} characters and the packet carries {parts.caps()[name]:,}" for name, text in texts.items() if len(text) > parts.caps()[name]
    ]
    try:
        files = len(parts.diffstat(check))
    except git.GitError:
        check.defer("base_moved", f"the head {check.req.head[:12]} shares no history with the tip of {check.default}, so its changes cannot be listed")
        files = 0
    if files > parts.max_diffstat_files():
        over.append(f"the change touches {files:,} files and the packet lists {parts.max_diffstat_files():,}")
    if over:
        check.defer("text_too_long", "; ".join(over))


def guard(check: Check) -> None:
    """After the action's own checks: the texts they did not read are read too, and every text is held whole."""
    if not (check.tip and check.top):
        return
    scan: dict[str, str] = {}
    try:
        text = parts.spec_text(check)
        if text:
            body = documents.split_front_matter(text, str(check.spec_path))[1]
            scan[f"{check.spec_path}'s body"] = body
            scan[f"{check.spec_path}'s front matter"] = text[: len(text) - len(body)]
        texts = parts.read(check)
    except documents.DocumentError as exc:
        check.defer("validate_errors", documents.one_line(str(exc), 300))
        return
    if saved := parts.saved_request(check):
        scan[f"the saved request {saved[0]}"] = saved[1]
    scan |= {f"commit {c['sha'][:12]}'s subject": c["message"].splitlines()[0] for c in git.commits(check.tip, check.req.head, check.top) if c["message"]}
    # The delegate reads the parsed parts, not the file: a YAML escape or a folded scalar can hold in the value what the raw
    # text does not spell, so each part is read as the packet carries it, besides the raw text above.
    if not any(r["code"] in ("text_claims_approval", "text_hides_characters") for r in check.reasons):
        scan |= {f"the packet's {name}": text for name, text in texts.items()}
    tripwire(check, {label: text for label, text in scan.items() if label not in check.scanned})
    fit(check, texts)
