"""A deterministic generator of shell lines that end up running one ref-moving git command, for the guard sweep
(`tests/test_guard_shell_sweep.py`). It composes the shell forms a line can take around a small core of git commands
that move a protected ref, so the oracle can judge many shapes at once: the guard reads each, then real bash and git
run it in a throwaway copy, and a line the guard allowed that git moved is a bypass.

Each core is one git command that, run alone, moves the base branch (`main`), lands a worktree on an explore branch,
or writes `refs/aidd/decisions`. Around it the generator draws, from a seed, one choice on each independent axis:

- how the branch or ref name is quoted: single, double, ANSI-C `$'…'`, a backslash, split quotes, or its case
  (a case-insensitive disk reads `MAIN` as `main`);
- a `git` option before the subcommand (`-C .`, `-c …`, `--no-pager`);
- a wrapper that runs it (`env`, `nice`, `timeout`, `command`);
- a compound that holds it (`&&`, `||`, `;`, a subshell, a brace group, `if`, `for`, `case`);
- one level of indirection that runs the text (`bash -c`, `eval`, a here-string, a pipe from `echo` or `printf`);
- a variable set earlier on the line that the name comes from (`B=main; git … "$B"`);
- a `cd` that stays in the repository, so paths and refspecs still resolve.

A few fixed forms add globs and braces a file made on the line fills in, which do not cross-produce cleanly.

The generator never emits the guard's documented limits (SECURITY.md, "known limits"): an alias expanded after
`shopt -s expand_aliases`, a script a shell runs from a file or a download (`bash x.sh`, `curl | sh`), or a writer
outside the documented list. Every form it does emit is one the guard is meant to read, so a bypass is a real gap.

The seed keeps a run the same on every machine. A small sample runs in the normal suite; a larger one, seeded by the
ISO week, runs weekly in CI.

This sweep found one guard gap on 2026-10-22, since closed: `echo 'git branch -qf mai\n feature' | bash` moved the
base branch, because bash's own `echo` keeps a backslash, which the shell it feeds then unescapes. The guard now reads
echo text with any backslash as text it cannot follow.
"""

from __future__ import annotations

import random

# Each core is (template, name, cased): a git command after the word `git`, with `{n}` where the branch or ref goes,
# the plain name, and a case variant that a case-insensitive disk resolves to the same ref (None where there is none).
# Several spellings of one move (a short cluster, a long-option prefix) are separate cores, so the sweep covers them.
_CORES: dict[str, tuple[tuple[str, str, str | None], ...]] = {
    "base": (
        ("branch -f {n} feature", "main", "MAIN"),
        ("branch --force {n} feature", "main", "MAIN"),
        ("branch -qf {n} feature", "main", "MAIN"),
        ("branch --forc {n} feature", "main", "MAIN"),
        ("branch -M feature {n}", "main", "MAIN"),
        ("update-ref refs/heads/{n} feature", "main", "MAIN"),
        ("push . feature:{n}", "main", None),
        ("push . +feature:refs/heads/{n}", "main", None),
        ("fetch . feature:{n}", "main", None),
        ("checkout -B {n} feature", "main", "MAIN"),
        ("checkout -qB {n} feature", "main", "MAIN"),
        ("switch -C {n} feature", "main", "MAIN"),
    ),
    "explore": (
        ("checkout {n}", "explore/topic", None),
        ("switch {n}", "explore/topic", None),
        ("switch -c {n}", "explore/new", None),
        ("checkout -B {n} feature", "explore/topic", None),
        ("checkout -qB {n} feature", "explore/topic", None),
        ("checkout --orphan {n}", "explore/orphan", None),
        ("branch -m {n}", "explore/renamed", None),
        ("branch -M feature {n}", "explore/renamed", None),
        ("worktree add ../wt-{w} {n}", "explore/topic", None),
        ("symbolic-ref HEAD refs/heads/{n}", "explore/topic", None),
    ),
    "decisions": (
        ("update-ref {n} HEAD", "refs/aidd/decisions", "refs/aidd/Decisions"),
        ("update-ref -d {n}", "refs/aidd/decisions", None),
        ("push . HEAD:{n}", "refs/aidd/decisions", None),
        ("push . +HEAD:{n}", "refs/aidd/decisions", None),
        ("fetch . HEAD:{n}", "refs/aidd/decisions", None),
        ("symbolic-ref {n} refs/heads/feature", "refs/aidd/decisions", None),
        # The decision records' name before 1.0, which the guard protects until `aidd upgrade` moves it.
        ("update-ref {n} HEAD", "refs/aidd/approvals", "refs/aidd/Approvals"),
        ("push . HEAD:{n}", "refs/aidd/approvals", None),
    ),
}

# Fixed forms that a glob or a brace fills in, each a whole `git` line already (no core wrapping). They mirror the
# oracle's own glob and brace lines, so the sweep keeps covering them as it grows.
_SPECIALS: dict[str, tuple[str, ...]] = {
    "base": (
        "touch main && git branch -f ma[i]n feature",
        "git branch -f {main,feature}",
        "git branch -f ma\\\nin feature",
    ),
    "explore": (
        "mkdir -p explore/new && git switch -c explor[e]/new",
        "git checkout {explore/topic,}",
    ),
    "decisions": (
        "git push . HEAD:refs/aidd/approval{s,}",
        "git push . HEAD:refs/aidd/decision{s,}",
        "git update-ref refs/aidd/'approvals' HEAD",
    ),
}

_GIT_OPTS = ("", "-C . ", "-c core.pager=cat ", "--no-pager ")
_WRAPPERS = ("", "env ", "nice ", "timeout 30 ", "command ")
_COMPOUNDS = ("plain", "and", "or", "semi", "subshell", "brace", "if", "for", "case")
_INDIRECT = ("none", "bashc", "eval", "herestring", "echo", "printf")
_CDS = ("", "cd . && ", 'cd "$(echo .)" && ')
_NAME_FORMS = ("plain", "single", "double", "ansic", "backslash", "splitquote", "cased")


def _sh_single(text: str) -> str:
    """`text` as one single-quoted word for the shell, so a runner such as `bash -c` sees it unchanged."""
    return "'" + text.replace("'", "'\\''") + "'"


def _name(form: str, name: str, cased: str | None, rng: random.Random) -> str:
    """The branch or ref `name` written in one quoting form. A form that would need a different name (a case variant
    with none) falls back to the plain name."""
    if form == "single":
        return "'" + name + "'"
    if form == "double":
        return '"' + name + '"'
    if form == "cased":
        return cased or name
    # Pick an interior alphabetic character to rewrite, so the form is non-trivial but resolves to the same name.
    spots = [i for i, c in enumerate(name) if c.isalpha()]
    if not spots:
        return name
    i = rng.choice(spots[1:] or spots)
    if form == "ansic":
        return "$'" + name[:i] + f"\\x{ord(name[i]):02x}" + name[i + 1 :] + "'"
    if form == "backslash":
        return name[:i] + "\\" + name[i:]
    if form == "splitquote":
        return name[:i] + '""' + name[i:]
    return name


def _compound(kind: str, cmd: str) -> str:
    return {
        "plain": cmd,
        "and": "true && " + cmd,
        "or": "false || " + cmd,
        "semi": "true ; " + cmd,
        "subshell": "( " + cmd + " )",
        "brace": "{ " + cmd + " ; }",
        "if": "if true; then " + cmd + "; fi",
        "for": "for _x in 1; do " + cmd + "; done",
        "case": "case x in x) " + cmd + " ;; esac",
    }[kind]


def _indirect(kind: str, text: str) -> str:
    if kind == "none":
        return text
    quoted = _sh_single(text)
    return {
        "bashc": "bash -c " + quoted,
        "eval": "eval " + quoted,
        "herestring": "bash <<< " + quoted,
        "echo": "echo " + quoted + " | bash",
        "printf": "printf '%s\\n' " + quoted + " | bash",
    }[kind]


def _one(core: tuple[str, str, str | None], rng: random.Random, serial: int) -> str:
    template, name, cased = core
    indirect = rng.choice(_INDIRECT)
    # A variable only works when the name's own use runs in the line's shell, so it and `cd` wait for no new shell.
    use_var = indirect == "none" and rng.random() < 0.3
    forms = _NAME_FORMS if indirect == "none" else [f for f in _NAME_FORMS if f not in ("single", "ansic")]
    token = '"$B"' if use_var else _name(rng.choice(forms), name, cased, rng)
    core_cmd = template.format(n=token, w=serial)
    git_cmd = rng.choice(_WRAPPERS) + "git " + rng.choice(_GIT_OPTS) + core_cmd
    line = _indirect(indirect, _compound(rng.choice(_COMPOUNDS), git_cmd))
    if indirect == "none":
        line = rng.choice(_CDS) + line
    if use_var:
        line = f"B={name}; " + line
    return line


# A person's decision claimed with `--confirmed` or a prefix of it (the security fix): aidd once let argparse read
# `--confirm HEAD` as `--confirmed HEAD`. Where a standing approval lets the agent run the plain command, the guard must
# still deny each of these, in every shell form.
_CONFIRMED_CORES = ("aidd land {o}", "aidd approve merge {o}", "aidd approve spec SPEC-1 {o}", "aidd publish {o}")
_CONFIRMED_PREFIXES = ("--co", "--con", "--conf", "--confi", "--confir", "--confirm", "--confirme", "--confirmed")


def confirmed_claims(seed: int, count: int) -> list[str]:
    """A deterministic list of up to `count` lines, each an aidd decision with `--confirmed` or a prefix of it (as
    `--conf HEAD` or `--conf=HEAD`), dressed in one draw of the wrappers, compounds, and indirections."""
    rng = random.Random(f"confirmed:{seed}")
    lines: list[str] = []
    for _ in range(count * 40):
        prefix = rng.choice(_CONFIRMED_PREFIXES)
        core = rng.choice(_CONFIRMED_CORES).format(o=f"{prefix}=HEAD" if rng.random() < 0.3 else f"{prefix} HEAD")
        line = _indirect(rng.choice(_INDIRECT), _compound(rng.choice(_COMPOUNDS), rng.choice(_WRAPPERS) + core))
        if line not in lines:
            lines.append(line)
        if len(lines) >= count:
            break
    return lines


# An agent started through Orca with a person's decision as its first prompt, which the new agent's prompt hook would
# record: `orca agent launch` and `orca worktree create --agent`, with the prompt quoted, split, or from a variable.
# Orca reads its options anywhere, so the prompt stands last, first, or between the command's words, and the first
# command word may come from an expansion.
_LAUNCH_CORES = (
    ("agent", "launch", "--agent claude", "--prompt"),
    ("agent", "launch", "--agent codex --json", "--prompt"),
    ("worktree", "create", "--name t{w} --agent claude", "--prompt"),
    ("orchestration", "task-create", "--task-title T{w}", "--spec"),
    ("orchestration", "worker-start", "--agent claude", "--spec"),
)
_PROMPT_PLACES = ("last", "first", "between")
_GROUP_FORMS = ("plain", "plain", "plain", "ansic", "brace", "variable")
_DECISIONS = ("approve SPEC-1", "approve all", "land it", "Land it.", "merge it", "publish", "approve SPEC-1 and SPEC-2", "aidd land")
_PROMPT_FORMS = ("double", "single", "ansic", "backslash", "splitquote", "variable")


def _prompt(form: str, text: str, rng: random.Random) -> str:
    """The prompt `text` as one shell word in one quoting form, which bash joins back into `text`."""
    if form == "single":
        return "'" + text + "'"
    if form == "backslash":
        return text.replace(" ", "\\ ").replace(".", "\\.")
    i = rng.choice([i for i, c in enumerate(text) if c.isalpha()][1:])
    if form == "ansic":
        return "$'" + text[:i] + f"\\x{ord(text[i]):02x}" + text[i + 1 :] + "'"
    if form == "splitquote":
        return '"' + text[:i] + '""' + text[i:] + '"'
    return '"' + text + '"'


def launch_prompts(seed: int, count: int) -> list[str]:
    """A deterministic list of up to `count` lines, each starting an agent through Orca with a decision as its first
    prompt (`--prompt <word>` or `--prompt=<word>`), dressed in one draw of the wrappers, compounds, and indirections."""
    rng = random.Random(f"launch:{seed}")
    lines: list[str] = []
    for attempt in range(count * 40):
        indirect = rng.choice(_INDIRECT)
        forms = _PROMPT_FORMS if indirect == "none" else [f for f in _PROMPT_FORMS if f not in ("single", "ansic")]
        form, text = rng.choice(forms), rng.choice(_DECISIONS)
        word = '"$P"' if form == "variable" else _prompt(form, text, rng)
        group, sub, rest, flag = rng.choice(_LAUNCH_CORES)
        option = flag + ("=" if rng.random() < 0.3 else " ") + word
        shown = {"plain": group, "ansic": f"$'{group}'", "brace": "{" + group + ",}", "variable": '"$G"'}
        group_form = rng.choice(_GROUP_FORMS if indirect == "none" else ("plain", "brace", "variable"))
        words = [shown[group_form], sub, rest.format(w=attempt), option]
        place = rng.choice(_PROMPT_PLACES)
        if place != "last":
            words.insert(0 if place == "first" else 1, words.pop())
        inner = _compound(rng.choice(_COMPOUNDS), rng.choice(_WRAPPERS) + "orca " + " ".join(words))
        if group_form == "variable":
            inner = f"G={group}; " + inner
        if form == "variable":
            inner = f"P={_sh_single(text)}; " + inner
        line = _indirect(indirect, inner)
        if line not in lines:
            lines.append(line)
        if len(lines) >= count:
            break
    return lines


# macOS `arch` runs the program after its options: an agent started under it with a decision as its prompt.
_ARCH_OPTIONS = ("-arm64", "-x86_64", "-arch arm64", "-arm64 -e K=1", "-arch x86_64 -d K", "-64 -c", "-arm64e")
_ARCH_AGENTS = ("claude -p {p}", "claude --print {p}", "codex exec {p}", "orca agent launch --agent claude --prompt {p}", "orca claude-teams -p {p}")


def arch_agent_starts(seed: int, count: int) -> list[str]:
    """A deterministic list of up to `count` lines, each `arch` with its options starting an agent with a decision as its
    prompt, dressed in one draw of the wrappers, compounds, and indirections. Only the guard judges them, so they need
    no macOS."""
    rng = random.Random(f"arch:{seed}")
    lines: list[str] = []
    for _ in range(count * 40):
        indirect = rng.choice(_INDIRECT)
        forms = [f for f in _PROMPT_FORMS if f != "variable"]
        forms = forms if indirect == "none" else [f for f in forms if f not in ("single", "ansic")]
        prompt = _prompt(rng.choice(forms), rng.choice(_DECISIONS), rng)
        core = f"arch {rng.choice(_ARCH_OPTIONS)} " + rng.choice(_ARCH_AGENTS).format(p=prompt)
        line = _indirect(indirect, _compound(rng.choice(_COMPOUNDS), rng.choice(_WRAPPERS) + core))
        if line not in lines:
            lines.append(line)
        if len(lines) >= count:
            break
    return lines


def generate(category: str, seed: int, count: int) -> list[str]:
    """A deterministic list of up to `count` shell lines for `category` (`base`, `explore`, or `decisions`), each a
    core git move dressed in one draw of the shell forms, plus the fixed glob and brace lines. The same seed gives the
    same list on every machine."""
    rng = random.Random(f"{category}:{seed}")
    cores = _CORES[category]
    lines = list(_SPECIALS.get(category, ()))
    seen = set(lines)
    for attempt in range(count * 40):
        line = _one(cores[attempt % len(cores)], rng, attempt)
        if line not in seen:
            seen.add(line)
            lines.append(line)
        if len(lines) >= count:
            break
    return lines
