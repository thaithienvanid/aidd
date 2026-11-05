"""What a proposal owes while it is drafted and signed off."""

from __future__ import annotations

from pathlib import Path

from aidd.workitems import spec_file


def proposal_findings(path: Path, text: str, data: dict) -> list[str]:
    """What a proposal owes. While it is drafted (go recorded, no sign-off yet), an open dependency names its owner, due
    date, and mitigation (a warning): a person sets them before the sign-off, so the change needs no new sign-off.
    Once signed off, its text still matches `sign_off.hash` (an error otherwise: a person signs it off again once the
    client approved the change order). A sign-off with no hash binds no text (a warning)."""
    out = []
    if spec_file.proposal_status(data) == "drafting":
        for dep in data.get("dependencies") or []:
            if not isinstance(dep, dict) or dep.get("status") != "open":
                continue
            missing = [what for key, what in (("owner", "owner"), ("due", "due date"), ("mitigation", "mitigation")) if not str(dep.get(key) or "").strip()]
            if missing:
                them = "it" if len(missing) == 1 else "them"
                out.append(
                    f"warning: {path}: dependency {dep.get('id')} is open and has no {' and no '.join(missing)}; a person sets {them} before the sign-off"
                )
    sign_off = data.get("sign_off")
    if not isinstance(sign_off, dict):
        return out
    pid = data.get("id") or "<proposal>"
    signed = sign_off.get("hash")
    if not signed:
        out.append(
            f"warning: {path}: sign_off records no hash, so it binds no text; a person signs it off again: they type `sign off {pid}`, and aidd records it"
        )
    elif signed != spec_file.proposal_hash(text):
        out.append(
            f"{path}: the proposal changed after sign-off. Once the client approved the change order, a person signs it off again: "
            f"they type `sign off {pid}` at the prompt, and aidd records the text as it reads now"
        )
    return out
