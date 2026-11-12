"""Where a push deploys, for `aidd init`: the environments it reads from the deploying workflows, and what it says about the
rest. Only a person can say that nothing else deploys, because a host's Git integration deploys on a push with no file in the
repository. So init writes what it read only when an environment it read names the default branch, which makes a merge into
that branch the person's anyway. A list that left the default branch out would say that nothing deploys there, and that is
the person's word: `--environment none`, or the environments they name."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from aidd import config, delegation
from aidd.kernel import documents, git

FLAGS = "--environment NAME=REF (a branch, or refs/tags/PATTERN), --own-environment NAME=REF for one only you use, or --environment none if nothing deploys"


@dataclasses.dataclass(frozen=True)
class Fill:
    """What init read about where a push deploys. `environments` is the list it writes when no flag answered (None: it writes
    none), with the `path:line` of each in `read_from`. `lines` are what it says, as init's output lines."""

    environments: list[dict] | None = None
    read_from: dict[str, tuple[str, ...]] = dataclasses.field(default_factory=dict)
    lines: list[str] = dataclasses.field(default_factory=list)


def kept_environments(text: str | None) -> list[dict] | None:
    """The `environments` of the config that is already there (`text`), as init keeps it: None when there is no config, it does not
    parse, or it leaves `environments` unset; `[]` when it says nothing deploys."""
    try:
        listed = documents.parse_yaml(text, config.CONFIG_PATH).get("environments") if text else None
    except documents.DocumentError:
        return None
    return listed if isinstance(listed, list) else None


def plan(root: Path, answered: list[dict] | None, delegate: bool, kept: list[dict] | None, writes_config: bool) -> Fill:
    """What init does about where a push deploys. `answered` is what the flags gave (None: no flag), `delegate` whether a
    delegation is being written, `kept` the `environments` of the config that stays (None: it sets none), and `writes_config`
    whether this run writes a config file, as against keeping one, where only a flag changes `environments`."""
    names, sure = git.default_branches(str(root))
    evidence = delegation.read_deploy_evidence(root, names if sure else [])  # a default branch no one has named is no branch to expand
    shown = "; ".join(e.shown() for e in evidence.environments)
    where = [w for e in evidence.environments for w in e.where] + list(evidence.unread)
    deploys = evidence.covers(names, every=False) or bool(evidence.unread)
    label = names[0] if sure else "the default branch"
    if answered is not None:
        if answered or not deploys:
            return Fill()
        return Fill(
            lines=[
                f"note     you said nothing deploys from a push, but your workflows deploy at {', '.join(where)}: a merge into {label} stays yours while they do"
            ]
        )
    if not writes_config:
        if kept:
            return Fill()
        if not (evidence.environments or evidence.unread):
            return Fill()
        if kept is not None:
            return Fill(
                lines=[
                    f"note     {config.CONFIG_PATH} says nothing deploys from a push, but your workflows deploy at {', '.join(where)}: a merge into {label} stays yours while they do"
                ]
                if deploys
                else []
            )
        return Fill(
            lines=[
                f"hint     your workflows deploy at {', '.join(where)}, and the config you kept leaves `environments` unset, so a merge into {label} stays yours. "
                f"Say where a push deploys with {FLAGS}"
            ]
        )
    if not sure:
        if not (evidence.environments or evidence.unread):
            return Fill()
        return Fill(
            lines=[
                f"hint     your workflows deploy at {', '.join(where)}, but git cannot tell the default branch ({', '.join(names[:5])} could be it), so init wrote no environments. "
                f"Name it with `git remote set-head origin --auto` or `git config init.defaultBranch <branch>`, then run init again, or say where a push deploys with {FLAGS}"
            ]
        )
    if evidence.covers(names):
        read_from = {e.name: e.where for e in evidence.environments}
        wrote = [f"config   wrote environments from your workflows: {shown}"]
        stays = (
            [f"note     a push to {names[0]} deploys (see the comment beside each environment in the config), so a merge into it stays yours"]
            if delegate
            else []
        )
        return Fill([e.entry() for e in evidence.environments], read_from, wrote + stays)
    if not (evidence.environments or evidence.unread):
        return Fill()
    seen = ([shown] if shown else []) + [f"{w} (init could not turn it into an environment)" for w in evidence.unread]
    return Fill(
        lines=[
            f"hint     your workflows deploy: {'; '.join(seen)}. None names {names[0]}, so `environments` stays unset: a list without it would say that nothing deploys there, "
            f"and only you can say that. Say where a push deploys with {FLAGS}"
        ]
    )


def delegation_notes(found: list[str], answered: list[dict] | None, fill: Fill, kept: list[dict] | None) -> list[str]:
    """What `--delegate` says about where a push deploys, from the host files it `found`, `answered` (the flags), what the
    fill-in `fill` read, and the `environments` of the config that `kept` stays. The question is asked only when none of them says."""
    said = answered if answered is not None else fill.environments if fill.environments is not None else kept
    if said is None:
        shown = f" It found {', '.join(found)}, which a host deploys from." if found else ""
        flags = "" if any(FLAGS in line for line in fill.lines) else f" Say so with {FLAGS}."  # the hint below names them once
        return [
            f"note     does a push to the default branch deploy anything, such as a host's Git integration?{shown}{flags} "
            "Until then environments stays unset and a merge stays yours"
        ]
    if not said and found:
        who = "you said" if answered is not None else f"{config.CONFIG_PATH} says"
        return [
            f"note     {who} nothing deploys from a push, but it found {', '.join(found)}, which a host deploys from on a merge: a merge stays yours while it is tracked"
        ]
    return []
