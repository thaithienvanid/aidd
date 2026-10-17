"""The files that hold a decision only a person makes: a proposal's go or no-go and sign-off, an Initiative's go_no_go,
an exploration's pick, and the config's profile, mode, and gates.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from aidd import config
from aidd.guard import repo_config, review_dismissals, verdicts
from aidd.kernel import documents, globs

# Who writes which part of a proposal's folder: the product manager and the tech writer the proposal itself, and each
# specialist only its own part. The decisions in it (go_no_go, sign_off, outcome) are a person's, never an agent's.
PROPOSAL_PARTS = {
    "product-manager": ("proposal.md",),
    "delivery-manager": ("proposal.md", "contract.md", "change-orders/"),
    "tech-writer": ("proposal.md",),
    "architect": ("architecture.md",),
    "product-designer": ("experience.md",),
    "security-engineer": ("security.md",),
    "compliance-analyst": ("compliance.md",),
    "sre": ("operations.md",),
}
PROPOSAL_RULE = (
    "in a proposal's folder the product manager, the delivery manager, and the tech writer write proposal.md. The delivery manager "
    "also writes the contract (contract.md) and its change orders (change-orders/). Each specialist writes only its own part: "
    "architect architecture.md, product designer experience.md, security engineer security.md, compliance analyst compliance.md, "
    "and SRE operations.md. In the folder, only a person records go_no_go, sign_off, and outcome"
)
PROPOSAL_DECISIONS = ("go_no_go", "sign_off", "outcome")
# The one agent that writes the feedback log: every other role drafts an entry with its source and hands it over.
FEEDBACK_WRITER = "product-manager"
# A decision named anywhere as a key, in YAML (`go_no_go:`, quoted, or inside a flow mapping) or in a TOML spelling, so
# front matter that does not parse is still read as naming it (fail-closed).
_DECISION_KEY = re.compile(r"""(?:^|[\s{,\[])["']?(?:go_no_go|sign_off|outcome)["']?\s*[:=\]]""", re.M)


def _decisions(text: str, rel: str, keys: tuple[str, ...] = PROPOSAL_DECISIONS) -> tuple | None:
    """The decisions (`keys`) a file's front matter records, or None when its front matter does not parse."""
    try:
        data, _ = documents.split_front_matter(text, rel)
    except documents.DocumentError:
        return None
    return tuple(json.dumps(data.get(k), sort_keys=True, default=str) for k in keys)


# A YAML reader decodes the escapes in a double-quoted key or value (`"go_no\u005fgo"`), so text that does not parse is
# searched both as written and with them decoded.
_ESCAPE = re.compile(r"\\(?:x([0-9A-Fa-f]{2})|u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8}))")


def _decoded(m: re.Match[str]) -> str:
    try:
        return chr(int(m.group(1) or m.group(2) or m.group(3), 16))
    except ValueError:
        return m.group(0)


def _names(pattern: re.Pattern, text: str) -> bool:
    """Whether `pattern` finds its key in `text`, as written or with its escapes decoded."""
    return bool(pattern.search(text) or pattern.search(_ESCAPE.sub(_decoded, text)))


def changes_decisions(rel: str, old_text: str | None, new_text: str | None, keys: tuple[str, ...], named: re.Pattern) -> bool:
    """Whether the edit adds or changes one of `keys`. Front matter that does not parse cannot be compared: naming a
    decision in it (`named`) is enough."""
    if new_text is None:
        return False
    after = _decisions(new_text, rel, keys)
    if after is None:
        return _names(named, new_text)
    before = _decisions(old_text, rel, keys) if old_text else None
    return after != (before or ("null",) * len(keys))


def proposal_edit(role: str, rel: str, old_text: str | None, new_text: str | None) -> verdicts.Verdict:
    own = PROPOSAL_PARTS.get(role)
    if own and Path(rel).name not in own and f"{Path(rel).parent.name}/" not in own:
        return "deny", f"the {role} role writes only {', '.join(own)} of a proposal; {rel} is another part. Hand off instead: {PROPOSAL_RULE}"
    if changes_decisions(rel, old_text, new_text, PROPOSAL_DECISIONS, _DECISION_KEY):
        return "deny", (
            f"{rel}: this edit adds or changes go_no_go, sign_off, or outcome, which only a person records. Leave them to the person "
            f"who decides, and write the rest. The rule: {PROPOSAL_RULE}"
        )
    return "allow", f"a proposal, inside the {role} role's part"


# An Initiative's go_no_go, in the proposal's shape, is a person's decision too: no aidd-team role adds or changes it.
# Its kind is read by parsing the front matter, and from the text only when the front matter does not parse (any YAML or
# TOML spelling of the key and the value), so a broken file is still known as an Initiative's.
_GO_NO_GO_KEY = re.compile(r"""(?:^|[\s{,\[])["']?go_no_go["']?\s*[:=\]]""", re.M)
_INITIATIVE = re.compile(r"""(?:^|[\s{,])["']?kind["']?\s*[:=]\s*["']{0,3}initiative\b""", re.M)


def _is_initiative(text: str | None, rel: str = "") -> bool:
    if not text:
        return False
    try:
        return documents.split_front_matter(text, rel)[0].get("kind") == "initiative"
    except documents.DocumentError:
        return _names(_INITIATIVE, text)


def initiative_decision(rel: str, old_text: str | None, new_text: str | None) -> bool:
    """Whether the edit adds or changes an Initiative's go_no_go: the file is an Initiative before or after it."""
    if not (_is_initiative(old_text, rel) or _is_initiative(new_text, rel)):
        return False
    return changes_decisions(rel, old_text, new_text, ("go_no_go",), _GO_NO_GO_KEY)


# The config keys that decide who must approve, and whether the gate binds. An agent may make them stricter, or fix
# a broken profile, but never looser, whatever scope a Spec approved: that is a person's decision.
_CONFIG_DECISION_KEY = re.compile(r"""(?:^|[\s{,])["']?(?:profile|mode|gates|extends|components)["']?\s*[:=]""", re.M)
_LOCKED_KEYS = ("gates", "extends", "components")  # any change: a looser one is not told from a stricter one here
CONFIG_DENY = (
    "this edit loosens who must approve, or whether the gate binds: {what}. Only a person does that, in their own "
    "editor or with `aidd init --profile <name> --force` at their own terminal, and never because someone said yes in "
    "the chat. Leave it as it is, and edit the rest"
)


def _config_data(text: str) -> dict | None:
    try:
        data = documents.parse_yaml(text, config.CONFIG_PATH) if text.strip() else {}
    except documents.DocumentError:
        return None
    return data if isinstance(data, dict) else None


def config_loosening(rel: str, old_text: str | None, new_text: str | None) -> str | None:
    """What an edit of `.aidd/config.yaml` loosens, or None: a looser or broken profile, `mode` off `enforce`, or any
    change to `gates`, `extends`, or `components`. Text that does not parse is enough when it names one of those keys
    (fail-closed)."""
    if new_text is None or rel.casefold() != config.CONFIG_PATH.casefold():
        return None
    new = _config_data(new_text)
    if new is None:
        return (
            "the new text does not parse, and it names `profile`, `mode`, `gates`, `extends`, or `components`"
            if _names(_CONFIG_DECISION_KEY, new_text)
            else None
        )
    old = _config_data(old_text or "") or {}
    order = config.profiles()["order"]
    was, now = old.get("profile"), new.get("profile")
    if now != was and was in order and (now not in order or order.index(now) < order.index(was)):
        return f"it changes the profile from {was} to {now!r}"
    if old.get("mode") == "enforce" and new.get("mode") != "enforce":
        return "it moves `mode` off `enforce`"
    changed = [k for k in _LOCKED_KEYS if json.dumps(old.get(k), sort_keys=True, default=str) != json.dumps(new.get(k), sort_keys=True, default=str)]
    return f"it changes {', '.join(f'`{k}`' for k in changed)}" if changed else None


UNREADABLE_DECISION = "use the Edit or Write tool so the change can be checked"


def decision_file(root: str, rel: str) -> str | None:
    """What a file holds that only a person decides, when it is one the guard checks on the Edit or Write tool's text:
    REVIEW.md, an Initiative (or a new file in the specs folder, which may become one), a proposal, or an exploration."""
    if rel.casefold() == review_dismissals.REVIEW_POLICY.casefold():
        return "dismissal"
    if rel.casefold() == config.CONFIG_PATH.casefold():
        return "the profile, the mode, and the gates"
    cfg = repo_config.load_config(root)
    if cfg is None:
        return None
    if is_exploration(cfg, rel):
        return "an exploration's outcome"
    if globs.match_any([globs.under(cfg.proposals_dir, "*/proposal.md")], rel, fold_case=True):
        return "a proposal's go_no_go, sign_off, and outcome"
    if globs.match_any([globs.under(cfg.specs_dir, "**")], rel, fold_case=True):
        path = Path(root) / rel
        if not path.exists():
            return "a new work item, which may be an Initiative with its go_no_go"
        try:
            if _is_initiative(path.read_text(encoding="utf-8", errors="replace"), rel):
                return "an Initiative's go_no_go"
        except OSError:
            return "a work item the guard cannot read"
    return None


def is_exploration(cfg: config.Config, rel: str) -> bool:
    """An exploration's file, in its home: `specs/<ID>/explore/<slug>/` or `specs/explore/<topic>/`."""
    specs = cfg.specs_dir
    return globs.match_any([globs.under(specs, "*/explore/*/exploration.md"), globs.under(specs, "explore/*/exploration.md")], rel)
