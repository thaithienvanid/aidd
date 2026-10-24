"""The decision records: a person's approvals and merges on one machine, with no GitHub or GitLab.

A solo founder, or a team that keeps work local and pushes later, still gets the two human decisions. Each decision
is a commit on the private ref `refs/aidd/decisions` (outside every branch and tag) whose message is the approval
line; the local gate reads it as it reads a platform's review or comment. `aidd land` (platforms/local_land.py) then
merges a passing branch into the base branch, keeping its history or squashing it.

The limit, said plainly: on one machine the agent runs as you. The hook denies `aidd approve` and `aidd land` to
agents, and both refuse in a shell an agent started and go on only when a person at an interactive terminal answers
yes. An approval can also come from a dialog the person answers: the aidd-mods plugin's in Claude Code, from a prompt
they typed, or an MCP client's (`--confirmed`); its record carries `Aidd-Decided-Via`. The person's own typed words
count too (`prompt`), and a standing approval they started lets the agent record each approval it covers, citing it
(`standing:<record>`). Set up git
commit signing with an SSH key that asks for your presence (a hardware key, or an SSH agent that prompts), list each
Approver's key in the base branch's allowed signers file (`gates.local_signers`, `.aidd/allowed_signers` by default),
and set `gates.local_approvals: signed` in the base branch\'s config: then only approvals whose SSH signature
ssh-keygen verifies against that file, from the principal the approval's author email names, count. Both the
requirement and the keys come from the base branch, and the check pins its own gpg settings, so neither this
machine's git config nor its `gpg.ssh.allowedSignersFile`, which an agent could edit, decides it; with no signers
file on the base branch, no approval counts. What stays on this machine is the private key and the programs that run
(git, ssh-keygen): an agent that can use your key, or replace those programs, still defeats it. Without signing, a
local approval is as strong as the hook and the terminal check. A platform's review is stronger; push to one when
the work matters to other people.
"""

from __future__ import annotations

import datetime as dt
import os
import re

from aidd.kernel import git

DECISIONS_REF = "refs/aidd/decisions"
# The allowed signers file (`gates.local_signers`), read from the base branch: whose signatures count as approvals.
DEFAULT_SIGNERS = ".aidd/allowed_signers"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
MERGE_TRAILER = "Aidd-Merge-Approval"
# The branch a Merge approval was given on, so another branch's approval is never read as this one's.
BRANCH_TRAILER = "Aidd-Branch"
# Where the person decided, when it was in a dialog or a typed prompt, not at the terminal (`--confirmed`,
# `--decided-via`): `claude-code` for the aidd-mods dialog, `mcp:<client>` for an MCP client's.
DECIDED_VIA_TRAILER = "Aidd-Decided-Via"
# The person's platform login, read from their own token when they gave a standing approval in a
# repository whose Approvers are logins: the email alone never matches one.
LOGIN_TRAILER = "Aidd-Login"
# The remote a person's "publish" names, and each URL it pushed to then: the one place their decision lets the work go.
REMOTE_TRAILER = "Aidd-Remote"
REMOTE_URL_TRAILER = "Aidd-Remote-Url"


def with_login(line: str, login: str | None) -> str:
    """A record that also names the person's platform login, when there is one."""
    return f"{line}\n{LOGIN_TRAILER}: {login}" if login else line


def is_signing_configured(cwd: str = ".") -> bool:
    return bool(git.config_value("user.signingkey", cwd))


# Each record this process wrote: a command's own records, which nothing outside it can add to (records_written).
_WRITTEN: set[str] = set()


def records_written() -> frozenset[str]:
    """The decision records this process wrote (`record_local_approval`): the exact commits a command may call its own."""
    return frozenset(_WRITTEN)


def record_local_approval(line: str, cwd: str = ".") -> tuple[str, bool]:
    """Append one approval to the decision records; signed when git signing is set up. Returns the commit and whether it is signed.

    The ref moves only from the parent read here (or from nothing), so two approvals recorded at once cannot drop one."""
    parent = git.run(["rev-parse", "--verify", "--quiet", DECISIONS_REF], cwd, check=False).strip()
    signed = is_signing_configured(cwd)
    args = ["commit-tree", EMPTY_TREE, "-m", line] + (["-p", parent] if parent else []) + (["-S"] if signed else [])
    sha = git.run(args, cwd).strip()
    git.run(["update-ref", DECISIONS_REF, sha, parent or "0" * len(sha)], cwd)
    _WRITTEN.add(sha)
    return sha, signed


def is_signature_trusted(sig: str, signer: str, email: str, ssh: bool) -> bool:
    """A good signature from a key git trusts; with SSH signing, from the principal the author email names.

    "U" (a good signature from a key of unknown validity) does not count: anyone can make a key and sign with it."""
    return sig == "G" and (not ssh or signer.strip().lower() == email.strip().lower())


def signers_path(cfg) -> str:
    """Where the base branch keeps the people whose signatures count (`gates.local_signers`)."""
    return str((cfg.gates.get("local_signers") if cfg is not None else None) or DEFAULT_SIGNERS)


def base_signers(cfg, base_ref: str | None, cwd: str = ".") -> str | None:
    """The allowed signers file as the base branch's tip holds it, or None when it has none. Never the working tree's
    copy, and never this machine's `gpg.ssh.allowedSignersFile`: an agent on this machine can edit both."""
    if not base_ref:
        return None
    return git.show(base_ref, signers_path(cfg), cwd)


# The configuration every signature check pins, whatever this machine's git config says: SSH signatures, checked by
# ssh-keygen against the base branch's signers. An agent can point gpg.ssh.program at a script that always says good.
_PINNED = ("gpg.format=ssh", "gpg.ssh.program=ssh-keygen")


def _pinned_env() -> dict[str, str]:
    """This process's environment without configuration passed through it (`GIT_CONFIG_PARAMETERS`, `GIT_CONFIG_COUNT`
    and its keys), which could reach past the `-c` options the check sets."""
    return {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")) or k in ("GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT"))
    }


def _records(cwd: str, signers: str | None, limit: int | None = None) -> list[list[str]]:
    fields = ["%H", "%ae", "%aI", "%G?", "%GS"]
    refs = [DECISIONS_REF, *(["-n", str(limit)] if limit else [])]
    if signers is None:
        return git.log_fields(refs, fields, cwd)
    import tempfile

    fd, path = tempfile.mkstemp(prefix="aidd-signers-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(signers)
        options = [x for kv in (*_PINNED, f"gpg.ssh.allowedSignersFile={path}") for x in ("-c", kv)]
        return git.log_fields(refs, fields, cwd, options=options, env=_pinned_env())
    finally:
        os.unlink(path)


# What an approval's message may never hold: the separators an older reader split records on, and NUL.
_SEPARATORS = ("\x00", "\x1e", "\x1f")


def load_local_approvals(
    cwd: str = ".", require_signed: bool = False, *, signers: str | None = None, signers_file: str = DEFAULT_SIGNERS
) -> tuple[list[dict], list[dict], list[str]]:
    """The recorded approvals as the gate reads them: (reviews, comments, notes about what did not count).

    Every approval carries `verified`: whether its signature verifies. `signers` is the allowed signers file the base
    branch holds (`base_signers`, at `signers_file`): when given, only an SSH signature from a key it lists for the
    approval's author email verifies, checked with ssh-keygen whatever this machine's gpg.* config says. Without it, git
    checks as this machine is configured, which an agent on it can change; so under `require_signed` (the base branch's
    `gates.local_approvals: signed`) no approval verifies until the base branch holds the file.

    `require_signed` comes from the base branch's config, which an agent on this machine cannot change the way it can
    clear `user.signingkey`. When it is set, unverified approvals stay in the context with `verified: false` and the
    gate drops them (`merge_approval.unsigned`, `spec_approval.unsigned`), so the rule is checkable from the context
    alone. When only this machine has git signing set up, they are dropped here.

    Each approval's fields are read NUL-separated and its message by its length, so a message cannot forge another
    approval, its author, or its signature; a message holding NUL or an ASCII record or unit separator never counts."""
    if not git.ok(["rev-parse", "--verify", "--quiet", DECISIONS_REF], cwd):
        return [], [], []
    records = _records(cwd, signers)
    raw = git.raw_commits([r[0] for r in records], cwd)
    need_signature = require_signed or is_signing_configured(cwd)
    pinned = signers is not None
    ssh = pinned or git.config_value("gpg.format", cwd).lower() == "ssh"
    reviews: list[dict] = []
    comments: list[dict] = []
    notes: list[str] = []
    if require_signed and not pinned:
        notes.append(
            f'gates.local_approvals: "signed", but the base branch has no {signers_file}, so no local approval counts. Add one '
            f"`<email> <public key>` line per Approver to {signers_file} (git's allowed signers format), and merge it to the base branch"
        )
    for sha, email, when, sig, signer in records:
        obj = raw.get(sha)
        if obj is None:
            notes.append(f"skipped approval {sha[:12]} on {DECISIONS_REF}: git could not read it")
            continue
        body = git.commit_message(obj)
        if any(c in body for c in _SEPARATORS):
            notes.append(f"approval {sha[:12]} does not count: its message holds a control separator, which no approval carries")
            continue
        # With pinned signers, only an SSH signature: an OpenPGP or X.509 one is checked against this machine's keyring.
        good = is_signature_trusted(sig, signer, email, ssh) and (not pinned or git.signature_kind(obj) == "ssh")
        if require_signed and not pinned:
            good = False  # the note above says why
        elif need_signature and not good:
            notes.append(f"approval {sha[:12]} is not signed with a trusted key of its author, so it does not count")
        if need_signature and not good:
            if not require_signed:
                continue
        user = f"email:{email}"
        lines = body.splitlines()
        branch = next((ln.split(": ", 1)[1].strip() for ln in lines if ln.startswith(f"{BRANCH_TRAILER}: ")), None)
        for line in lines:
            if line.startswith(f"{MERGE_TRAILER}: "):
                review = {"user": user, "state": "approved", "commit_sha": line.split(": ", 1)[1].strip(), "submitted_at": when, "verified": good}
                if branch:
                    review["branch"] = branch  # for the adapter only (local_context drops it): never part of a context
                reviews.append(review)
            elif line.startswith("/aidd "):
                comments.append({"user": user, "body": line, "created_at": when, "verified": good})
    if not need_signature and (reviews or comments):
        notes.append(
            "local approvals are not signed. Set up git commit signing with an SSH key that asks for your presence. List the key in "
            f'{signers_file} on the base branch. Then set gates.local_approvals: "signed" in the base branch\'s config: only signed approvals count after that'
        )
    return reviews, comments, notes


def approve_spec_line(spec_id: str, commit: str) -> str:
    """A Spec approval: the Spec, and the commit the person read it at, which git keeps for the gate to compare."""
    return f"/aidd approve-spec {spec_id} {commit}"


def since_text(since: dict, more_command: str = "") -> str:
    """What changed in a Spec since the person's last approval of it, as they read it before approving again: each file
    with its counts, then the changed lines (`aidd approve spec --show`'s `since`)."""
    out = [f"Changed since your last approval ({since['commit'][:12]}):"]
    out += [f"  {f['path']}  +{f['added']} -{f['removed']}" for f in since["files"]] or ["  (no change in the frozen files)"]
    out += [f"    {line}" for line in since["lines"]]
    if since["more"]:
        out.append(f"    ... {since['more']} more changed lines" + (f": {more_command}" if more_command else ""))
    return "\n".join(out) + "\n"


def decided_via(line: str, where: str) -> str:
    """A decision record that says where the person decided, when they confirmed in a dialog, not at the terminal."""
    return f"{line}\n\n{DECIDED_VIA_TRAILER}: {where}"


# A person's standing approval: from it on, the agent records each Spec approval and Merge approval it covers, citing
# it (`Aidd-Decided-Via: standing:<commit>`), until the person stops it or its date passes. `all-but-major` leaves
# major changes to the person. Only a person starts one; anyone may stop one.
STANDING_TRAILER = "Aidd-Standing-Approval"
UNTIL_TRAILER = "Aidd-Until"
STANDING_SCOPES = ("all", "all-but-major", "all-and-publish", "all-and-publish-but-major")


def day(value: object) -> dt.date | None:
    """`value` as a calendar day when it is exactly YYYY-MM-DD in ASCII digits and a real date, else None. The last
    day of a standing approval is checked with it, written and read alike."""
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def ended(until: str | None, today: dt.date) -> bool:
    """Whether a record's last day (`Aidd-Until`) has passed. One aidd cannot read has ended: it never holds forever."""
    if until is None:
        return False
    last = day(until)
    return last is None or last < today


def standing_line(scope: str, until: str | None = None, *, remote: str | None = None, urls: list[str] | None = None) -> str:
    """The record of a standing approval (`scope` one of STANDING_SCOPES), or of its end (`stop`). One that publishes
    names the remote it publishes to and each URL that remote pushed to when the person gave it (`Aidd-Remote`,
    `Aidd-Remote-Url`), as a typed "publish" does: a later change to where it points ends what it lets through."""
    stamp = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    where = (f"\n{REMOTE_TRAILER}: {remote}" + "".join(f"\n{REMOTE_URL_TRAILER}: {u}" for u in urls or [])) if remote else ""
    return (
        f"{STANDING_TRAILER}: {scope}"
        + (f"\n{UNTIL_TRAILER}: {until}" if until else "")
        + where
        + f"\n\n{'Stopped' if scope == 'stop' else 'Given'} at {stamp}."
    )


def read_decision_records(
    cwd: str, approvers: list[str] | None, require_signed: bool, signers: str | None, limit: int | None = None
) -> list[tuple[str, str, str, list[str], bool]]:
    """Each record in the decision records, newest first, as (sha, email, when, message lines, counts). It `counts` as a
    person's decision only when its author is a listed Approver, never when the list is unknown (`approvers` None), and
    its signature verifies wherever load_local_approvals would need one to. Its author is its email, or, where the
    Approvers are platform logins, the login it records (`Aidd-Login`, read from the person's own token when they gave
    it). The login is as strong a claim as the email, never stronger: aidd writes both when the person decides, on a ref
    the guard keeps agents from writing, and under `gates.local_approvals: signed` only a listed signer's key makes
    either count."""
    if not git.ok(["rev-parse", "--verify", "--quiet", DECISIONS_REF], cwd):
        return []
    from aidd import config

    allowed = {config.normalize_identity(str(a)) for a in approvers or []}
    records = _records(cwd, signers, limit)
    raw = git.raw_commits([r[0] for r in records], cwd)
    need_signature = require_signed or is_signing_configured(cwd)
    pinned = signers is not None
    ssh = pinned or git.config_value("gpg.format", cwd).lower() == "ssh"
    out = []
    for sha, email, when, sig, signer in records:
        obj = raw.get(sha)
        if obj is None:
            continue
        body = git.commit_message(obj)
        good = is_signature_trusted(sig, signer, email, ssh) and (not pinned or git.signature_kind(obj) == "ssh") and (pinned or not require_signed)
        lines = body.splitlines()
        who = {config.normalize_identity(f"email:{email}")} | ({config.normalize_identity(login)} if (login := trailer(lines, LOGIN_TRAILER)) else set())
        counts = bool(who & allowed) and not any(c in body for c in _SEPARATORS) and (good or not need_signature)
        out.append((sha, email, when, lines, counts))
    return out


def trailer(lines: list[str], name: str) -> str | None:
    return next((ln.split(": ", 1)[1].strip() for ln in lines if ln.startswith(f"{name}: ")), None)


def live_standing(
    cwd: str = ".", approvers: list[str] | None = None, today: dt.date | None = None, *, require_signed: bool = False, signers: str | None = None
) -> dict | None:
    """The standing approval in force, or None: the newest standing record from a listed Approver, signed where
    approvals must be (`read_decision_records`), unless a later stop, from anyone, ends it, or its `Aidd-Until` date has
    passed. Its `scope`, `since`, `by`, `sha`, and `until`."""
    for sha, email, when, lines, counts in read_decision_records(cwd, approvers, require_signed, signers):
        scope = trailer(lines, STANDING_TRAILER)
        if scope is None or (scope in STANDING_SCOPES and not counts):
            continue
        if scope not in STANDING_SCOPES:
            return None  # `stop` (anyone may stop one), or a scope this aidd does not know: nothing stands
        until = trailer(lines, UNTIL_TRAILER)
        if ended(until, today or dt.datetime.now(dt.UTC).date()):
            return None
        urls = sorted(line.split(": ", 1)[1].strip() for line in lines if line.startswith(f"{REMOTE_URL_TRAILER}: "))
        return {"scope": scope, "since": when, "by": f"email:{email}", "sha": sha, "until": until, "remote": trailer(lines, REMOTE_TRAILER), "urls": urls}
    return None


def signing(cfg, cwd: str) -> tuple[list[str] | None, bool, str | None]:
    """The Approvers, whether approvals must be signed, and the base branch's signers, as `cfg` and its base say."""
    if cfg is None:
        return None, False, None
    try:
        base = git.default_base(cwd)
    except git.GitError:
        base = None
    return list(cfg.approvers), cfg.gates.get("local_approvals") == "signed", base_signers(cfg, base, cwd)


def live_standing_for(cfg, cwd: str = ".", today: dt.date | None = None) -> dict | None:
    """live_standing as the config says: its Approvers, its `gates.local_approvals`, and the base branch's signers."""
    approvers, signed, signers = signing(cfg, cwd)
    return live_standing(cwd, approvers, today, require_signed=signed, signers=signers)


# "land it" (or, on a pull request, "merge it"), typed by the person: a standing approval for this one change. aidd's prompt hook records the head they
# said it for; the Merge approval of that head, or of a later head of the same work while the Spec stays as approved
# (land_decision), is then recorded with nobody asked again, each naming this record in its `Aidd-Decided-Via` line (`land-it:<sha>`), so a fix the
# gate or the reviewer asks for never asks the person again. It ends when its work lands.
LAND_TRAILER = "Aidd-Land"
# The words a "land it" record holds when the person said `merge it`: only that covers a Merge approval on the platform.
SAID_TRAILER = "Aidd-Said"


def land_said_line(head: str, branch: str | None = None, words: str = "land it") -> str:
    """The record of a typed "land it" for `head`, with the branch it was said on (`Aidd-Branch`), which a later head
    must be on for the decision to carry over (land_decision), and `Aidd-Said: merge it` when that is what they typed."""
    on = f"\n{BRANCH_TRAILER}: {branch}" if branch and branch != "HEAD" else ""
    on += f"\n{SAID_TRAILER}: merge it" if words == "merge it" else ""
    return f"{LAND_TRAILER}: {head}{on}\n\nSaid at {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}.\n\n{DECIDED_VIA_TRAILER}: prompt"


def covers_platform_merge(said: dict, platform: str) -> bool:
    """Whether the person's decision `said` (land_decision) covers a Merge approval where `platform` decides: anywhere for
    a local trunk, and on a platform (`preflight`) only when they typed `merge it`, never `land it` alone, which lands on
    the local trunk."""
    return platform != "preflight" or said.get("words") == "merge it"


def land_said_records(cwd: str, approvers: list[str] | None = None, *, require_signed: bool = False, signers: str | None = None) -> list[dict]:
    """Each "land it" a listed Approver said, among the newest records, newest first, signed where approvals must be
    (`read_decision_records`): {"sha": the record, "head": the head they said it for, "branch": "" when it names none,
    "words": "merge it" or "land it"}."""
    said: list[dict] = []
    for sha, _, _when, lines, counts in read_decision_records(cwd, approvers, require_signed, signers, limit=50):
        heads = [line.split(": ", 1)[1] for line in lines if re.fullmatch(rf"{LAND_TRAILER}: [0-9a-f]{{40,64}}", line)]
        branch = trailer(lines, BRANCH_TRAILER) or ""
        words = "merge it" if trailer(lines, SAID_TRAILER) == "merge it" else "land it"
        if counts:
            said += [{"sha": sha, "head": h, "branch": branch, "words": words} for h in heads]
    return said


def land_said(cwd: str, head: str, approvers: list[str] | None = None, *, require_signed: bool = False, signers: str | None = None) -> bool:
    """Whether a listed Approver said "land it" for exactly `head` (land_said_records)."""
    return any(r["head"] == head for r in land_said_records(cwd, approvers, require_signed=require_signed, signers=signers))


def land_decision(cfg, cwd: str, head: str) -> dict | None:
    """The person's "land it" that covers `head`, as the config says (signing): the record, the head they said it for,
    and whether that is `head` itself (`exact`); None when none covers it. It covers `head` itself, or a later head of
    the same branch that builds on the one they saw, when the commits since touch no Spec and no file an approval froze
    (_contract_unchanged) and the work they saw has not landed on the base yet: one "land it" lands one change. A
    change with no Spec, or on another branch, carries nothing over."""
    approvers, signed, signers = signing(cfg, cwd)
    said = land_said_records(cwd, approvers, require_signed=signed, signers=signers)
    if exact := next((r for r in said if r["head"] == head), None):
        return exact | {"exact": True}
    if cfg is not None and cfg.gates.get("approval_carry", "none") == "none":
        return None  # approvals never carry here (the audited profile): the person decides each head
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], cwd, check=False).strip()
    for r in said:
        if (
            branch
            and r["branch"] == branch
            and git.ok(["merge-base", "--is-ancestor", r["head"], head], cwd)
            and not _landed(cwd, r["head"])
            and _contract_unchanged(cfg, cwd, r["head"], head)
        ):
            return r | {"exact": False}
    return None


def land_said_for(cfg, cwd: str, head: str) -> bool:
    """Whether the person's "land it" covers `head` (land_decision)."""
    return land_decision(cfg, cwd, head) is not None


# "explore branch <topic>", typed by the person: they start an explore branch, where the guard holds no edit. The record
# names the branch, and the guard frees edits only on a `explore/` branch a listed Approver's record names
# (branch_kinds.guard_mode): a branch that merely has the prefix is ordinary.
EXPLORE_TRAILER = "Aidd-Explore"


def explore_said_line(branch: str) -> str:
    """The record of a person's typed `explore branch <topic>` for `branch`."""
    return f"{EXPLORE_TRAILER}: {branch}\n\nSaid at {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}.\n\n{DECIDED_VIA_TRAILER}: prompt"


def explore_said_for(cfg, cwd: str, branch: str) -> bool:
    """Whether a listed Approver started `branch` as an explore branch, as the config says (signing)."""
    approvers, signed, signers = signing(cfg, cwd)
    want = f"{EXPLORE_TRAILER}: {branch}"
    return any(counts and lines[:1] == [want] for _, _, _, lines, counts in read_decision_records(cwd, approvers, signed, signers, limit=200))


# "publish", typed by the person: they take the work at `head` off this machine. Its record lets the agent run `aidd
# publish` for exactly that head, which pushes it and opens its PR/MR. A standing approval never covers it, and a later
# commit needs a new "publish": what leaves the machine is what the person saw.
PUBLISH_TRAILER = "Aidd-Publish"


def publish_said_line(head: str, branch: str, remote: str, urls: list[str], decided_via: str = "prompt") -> str:
    """The record of a person's "publish" for `head`, typed or answered in a dialog (`decided_via`): the branch it was
    said on (`Aidd-Branch`), the remote it goes to (`Aidd-Remote`), and each URL that remote pushed to when the person
    said it (`Aidd-Remote-Url`). A later change to the remote's URLs ends what the decision lets through."""
    where = "".join(f"\n{REMOTE_URL_TRAILER}: {u}" for u in urls)
    return (
        f"{PUBLISH_TRAILER}: {head}\n{BRANCH_TRAILER}: {branch}\n{REMOTE_TRAILER}: {remote}{where}\n\n"
        f"Said at {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}.\n\n{DECIDED_VIA_TRAILER}: {decided_via}"
    )


def remote_urls(cwd: str, remote: str) -> list[str]:
    """Every URL a push to `remote` goes to, as git resolves them (`git remote get-url --push --all`)."""
    return sorted(u for u in git.run(["remote", "get-url", "--push", "--all", remote], cwd, check=False).splitlines() if u)


def publish_grant(cfg, cwd: str, head: str, branch: str) -> dict | None:
    """What the person let the agent publish here, or None: {"branch", "remote", "urls", "head"}. Their "publish" for
    exactly `head` grants it (`head` is that head). A "publish" for an earlier head of the same branch grants the fixes
    built on it (`head` None: that head is an ancestor of this one, and its work has not landed on the trunk yet), to
    the same remote. Their standing approval that publishes (`approve all and publish`) grants this branch to the remote
    it recorded. Either way the remote's URLs must still be the ones the decision saw. Records are a listed Approver's,
    signed where approvals must be (`signing`), on the ref agents cannot write."""
    if not branch:
        return None
    standing = live_standing_for(cfg, cwd)
    if standing_publishes(standing) and standing is not None:
        # The remote and URLs the person's standing approval recorded, never this machine's config as it reads now.
        remote, urls = standing.get("remote"), standing.get("urls") or []
        if remote and urls and urls == remote_urls(cwd, remote):
            return {"branch": branch, "remote": remote, "urls": urls, "head": head}
    approvers, signed, signers = signing(cfg, cwd)
    for _sha, _, _when, lines, counts in read_decision_records(cwd, approvers, signed, signers, limit=50):
        said, on, remote = trailer(lines, PUBLISH_TRAILER), trailer(lines, BRANCH_TRAILER), trailer(lines, REMOTE_TRAILER)
        if not counts or not said or on != branch or not remote:
            continue
        urls = sorted(line.split(": ", 1)[1].strip() for line in lines if line.startswith(f"{REMOTE_URL_TRAILER}: "))
        if not urls or urls != remote_urls(cwd, remote):
            continue  # the remote points elsewhere now: the decision named the old place
        if said == head:
            return {"branch": branch, "remote": remote, "urls": urls, "head": head}
        if git.ok(["merge-base", "--is-ancestor", said, head], cwd) and not _landed(cwd, said):
            return {"branch": branch, "remote": remote, "urls": urls, "head": None}
    return None


def publish_said_for(cfg, cwd: str, head: str) -> bool:
    """Whether the person let this head of the branch checked out be published (publish_grant)."""
    branch = git.run(["symbolic-ref", "-q", "--short", "HEAD"], cwd, check=False).strip()
    return publish_grant(cfg, cwd, head, branch) is not None


def _landed(cwd: str, head: str) -> bool:
    """Whether `head` is already on the base branch, remote or local: the work a "land it" named has landed. A squash or
    rebase merge leaves `head` off the base's history, so the base also counts when it holds every file the work
    changed as `head` holds it."""
    try:
        base = git.default_base(cwd)
    except git.GitError:
        return False
    for ref in {base, base.removeprefix("origin/")}:
        if not git.ok(["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"], cwd):
            continue
        if git.ok(["merge-base", "--is-ancestor", head, ref], cwd):
            return True
        fork = git.run(["merge-base", ref, head], cwd, check=False).strip()
        changed = [p for p in git.run(["diff", "--name-only", "-z", fork, head], cwd, check=False).split("\0") if p] if fork else []
        if changed and git.ok(["diff", "--quiet", ref, head, "--", *changed], cwd):
            return True
    return False


def _contract_unchanged(cfg, cwd: str, said: str, head: str) -> bool:
    """Whether the commits from `said` to `head` leave the branch's Specs, and what their approvals froze, as they
    were: at least one Spec, no file in the Specs folder changed (one added, edited, or deleted), and no frozen file."""
    from aidd.kernel import globs
    from aidd.workitems import branch_specs, spec_file

    if cfg is None:
        return False
    try:
        specs = branch_specs.carried_specs(cwd, cfg)
    except Exception:  # noqa: BLE001  # a Spec aidd cannot read holds no contract to carry a decision over
        return False
    # With --no-renames a moved file counts at both its old and its new path.
    changed = [p for p in git.run(["diff", "--name-only", "--no-renames", "-z", said, head], cwd, check=False).split("\0") if p]
    in_specs = any(p.startswith(f"{cfg.specs_dir}/") for p in changed)
    return bool(specs) and not in_specs and not any(globs.match_any(spec_file.frozen_paths(data), p) for _, data in specs for p in changed)


def standing_covers(standing: dict | None, route: str | None) -> bool:
    """Whether a standing approval covers a change on `route`: `all` covers every route, `all-but-major` all but major
    and emergency (and a change whose route is not known)."""
    if not standing:
        return False
    scope = str(standing["scope"])
    return not scope.endswith("but-major") or route in ("standard", "minor", "normal")


def standing_publishes(standing: dict | None) -> bool:
    """Whether a standing approval also takes work off this machine for the person (`approve all and publish`): never
    `all` alone, which keeps publishing theirs."""
    return standing is not None and "and-publish" in str(standing.get("scope"))


def approve_merge_line(head: str, *, branch: str | None = None) -> str:
    """The Merge approval's record: the head, then the branch it was given on, when there is one."""
    extra = f"\n{BRANCH_TRAILER}: {branch}" if branch and branch != "HEAD" else ""
    return f"{MERGE_TRAILER}: {head}{extra}\n\nApproved at {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}."
