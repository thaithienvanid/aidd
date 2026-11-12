"""What the repository's own files say deploys on a push: the workflows (GitHub Actions and GitLab CI) that deploy, with
the branches and tags that start them and the name of the environment they deploy to. `aidd init` writes these as the
config's `environments` and `aidd doctor` compares them with it. The files are read as text and line by line, and a
shape this does not read counts as unread, never as a push that deploys nothing: a file can show that something deploys,
and it can never show that nothing does. A GitLab job is read only when every line of its filter fits `gitlab_refs`'s small
grammar, and a file with an `include:`, a `workflow:`, or an anchor, alias, or tag is read for no job."""

from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path

from aidd import risk
from aidd.delegation import diff_signals as signals
from aidd.delegation import workflow_triggers
from aidd.kernel import documents, regular_files

WORKFLOW_FOLDER = ".github/workflows"
GITLAB_FILE = ".gitlab-ci.yml"
# The words of a GitLab file that are not jobs.
GITLAB_KEYWORDS = frozenset({"stages", "variables", "default", "include", "workflow", "image", "services", "cache", "before_script", "after_script", "spec"})
NAME = re.compile(r"[a-z][a-z0-9_-]*")
# The characters of a path that init copies into the config's comment. A path with any other, such as a new line or an escape, is
# a name a person did not type, so it is named in a line as data and never written (`documents.one_line`).
SAFE_PATH = re.compile(r"[A-Za-z0-9._/-]+")
# A ref the config accepts (the schema's `ref_globs`), with no control character.
SAFE_REF = re.compile(r"[^\s:\x00-\x1f\x7f-\x9f]+")
# A branch no list can name, to ask whether a push to some branch reaches a workflow, as a workflow that filters nothing does.
SOME_BRANCH = "\x00no-such-branch"


@dataclasses.dataclass(frozen=True)
class Found:
    """An environment the files deploy to: its name, the branch and tag globs whose push starts the deploy, and the
    `path:line` of each place that says so."""

    name: str
    branches: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    where: tuple[str, ...] = ()

    def shown(self) -> str:
        """The environment as init says it: its name, its refs, and where the files say so."""
        refs = [*self.branches, *(f"refs/tags/{tag}" for tag in self.tags)]
        return documents.one_line(f"{self.name} ({', '.join(refs)}) at {', '.join(self.where)}", 400)

    def entry(self) -> dict:
        """The config's `environments` entry for it."""
        return {"name": self.name} | ({"branches": list(self.branches)} if self.branches else {}) | ({"tags": list(self.tags)} if self.tags else {})


@dataclasses.dataclass(frozen=True)
class Evidence:
    """Every environment the files name, each once with all its refs, and the `path:line` of each deploy whose refs this could
    not read, such as a workflow that runs on every push."""

    environments: tuple[Found, ...] = ()
    unread: tuple[str, ...] = ()

    def covers(self, branches: list[str], *, every: bool = True) -> bool:
        """Whether an environment found here lists every one of `branches` (any one, with `every` false), such as the names the
        default branch can have."""
        listed = [e.entry() for e in self.environments]
        hit = [bool(risk.deploys_to(listed, "branches", b)) for b in branches]
        return bool(hit) and (all(hit) if every else any(hit))


def environment_name(raw: str, fallback: str) -> str:
    """The config name for a workflow's environment `raw`: lowercase, with a dash for each run of other characters. A name an
    expression builds, or one that does not start with a letter, takes `fallback`, the workflow's file name."""
    if "${{" in raw or "$(" in raw:
        return fallback
    name = re.sub(r"[^a-z0-9_-]+", "-", raw.strip().strip("'\"").lower()).strip("-")
    return name if NAME.fullmatch(name) else fallback


def clean_refs(refs: tuple[list[str], list[str]] | None) -> tuple[list[str], list[str]] | None:
    """`refs` when every branch and tag glob is one the config accepts and holds no control character; else None, which reads as
    unread, because a ref init cannot write as it is would write a config that says something else."""
    safe = refs is not None and all(SAFE_REF.fullmatch(r) and documents.one_line(r, len(r) + 1) == r for r in [*refs[0], *refs[1]])
    return refs if safe else None


def push_refs(text: str) -> tuple[list[str], list[str]] | None:
    """The branch globs and the tag globs that a GitHub workflow's `on: push` lists. None when the push trigger lists neither,
    ignores some, negates one, has a filter or a trigger this does not read, or another trigger may also run the workflow,
    because then it runs on more than a list names."""
    triggers = workflow_triggers.read_triggers(text)
    if triggers is None or triggers.other or triggers.push is None or triggers.push.wide:
        return None
    branches, tags = list(triggers.push.branches or ()), list(triggers.push.tags or ())
    if not (branches or tags) or any(ref.startswith("!") or not ref for ref in [*branches, *tags]):
        return None
    return branches, tags


def _map_name(inline: str) -> str:
    """The `name` in an inline map such as `{name: production, url: x}`, or "" when it has none."""
    found = re.search(r"\bname\s*:\s*([^,}]+)", inline)
    return found.group(1) if found else ""


def github_environments(text: str, fallback: str) -> list[tuple[str, int]]:
    """Each job `environment:` of a GitHub workflow as (the config name, its line), from 1; the workflow's file name once, at the
    first deploying line, when it deploys with no `environment:` at all."""
    lines = text.splitlines()
    jobs = next((i for i, line in enumerate(lines) if re.match(r"^jobs\s*:", line)), len(lines))
    found = []
    for n, line in enumerate(lines, 1):
        key = re.match(r"^\s*environment\s*:\s*(.*?)\s*(#.*)?$", line) if n > jobs else None
        if not key:
            continue
        inline = key.group(1)
        if inline.startswith("{"):
            inline = _map_name(inline)
        elif not inline:
            inline = next((m.group(1) for m in (re.match(r"^\s*name\s*:\s*(.+?)\s*(#.*)?$", x) for x in signals.block_under(lines, n - 1)) if m), "")
        found.append((environment_name(inline, fallback), n))
    return found


def gitlab_jobs(text: str, *, templates: bool = False) -> dict[str, tuple[int, list[str]]]:
    """Each job of a `.gitlab-ci.yml`, by name, with the line it starts on (from 1) and its lines. With `templates`, the hidden
    jobs (`.name`) too."""
    lines = text.splitlines()
    jobs = {}
    for i, line in enumerate(lines):
        key = re.match(r"""^(["']?)([.]?[A-Za-z0-9_][\w.-]*)\1\s*:""" if templates else r"""^(["']?)([A-Za-z0-9_][\w.-]*)\1\s*:""", line)
        if key and key.group(2) not in GITLAB_KEYWORDS:
            jobs[key.group(2)] = (i + 1, [line, *signals.block_under(lines, i)])
    return jobs


# What `only:` and `except:` list when they name a kind of pipeline and not a branch.
PIPELINE_KINDS = frozenset(
    {"api", "branches", "chat", "external", "external_pull_requests", "merge_requests", "pipelines", "pushes", "schedules", "tags", "triggers", "web"}
)
RULE_WHEN = frozenset({"on_success", "always", "manual", "on_failure"})
BRANCH_NAME = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*")
JOB_KEY = re.compile(r"""(["']?)([A-Za-z0-9_.-]+)\1\s*:(?:\s+(.*))?""")
DOUBLE = re.compile(r'"[^"\\]*"')
SINGLE = re.compile(r"'[^']*'")
QUOTES = re.compile(r"\"[^\"]*\"|'[^']*'")
PLAIN_KEY = re.compile(r"[A-Za-z0-9_.][\w.-]*\s*:(?:\s|$)")
# An anchor, an alias, a tag, or a merge key where a value or a key starts, outside quotes and comments.
YAML_EXTRAS = re.compile(r"(?:^\s*(?:-\s+)*|:\s+|[\[,{]\s*)[&*!]|^\s*<<\s*:")
BRANCH_TEST = re.compile(r"\$CI_(?:COMMIT_BRANCH|COMMIT_REF_NAME)\s*==\s*(?:[\"']([^\"']+)[\"']|(\$CI_DEFAULT_BRANCH))")
# A `variables:` entry, in a block or a flow map, that sets a variable a rule reads, so the rule no longer means what it says.
OVERRIDE = re.compile(r"""(?:^|[\s{,])["']?(?:CI_COMMIT_BRANCH|CI_COMMIT_REF_NAME|CI_DEFAULT_BRANCH|CI_COMMIT_TAG)["']?\s*:""")
TAG_TEST = re.compile(r"\$CI_COMMIT_TAG(?:\s*=~\s*/(?:[^/\\]|\\.)+/[a-z]*)?")

Section = tuple[str, list[tuple[int, str]]]


def _yaml_extras(text: str) -> bool:
    """Whether `text` holds an anchor, an alias, a tag (`!reference`), or a merge key, which bring lines from elsewhere."""
    return any(YAML_EXTRAS.search(QUOTES.sub('""', workflow_triggers.strip_comment(line))) for line in text.splitlines())


def gitlab_file_unread(text: str) -> bool:
    """Whether a `.gitlab-ci.yml` brings jobs or rules from where these lines do not look, so no job of it is read. It holds a
    top-level `include:` or `workflow:`, an anchor, an alias, a tag, or a merge key anywhere, or a top-level line that is no plain
    `key:` (a quoted or flow key, a directive, a second document), or a first line, after an optional `---`, that is not at column 0
    (the whole mapping is indented, so no job starts at the left margin), or a `variables:` entry anywhere that sets a variable
    the rules read (`CI_COMMIT_BRANCH`, `CI_COMMIT_REF_NAME`, `CI_DEFAULT_BRANCH`, `CI_COMMIT_TAG`)."""
    live = [x for x in text.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    body = live[1:] if live and live[0].strip() == "---" else live
    if body and body[0] != body[0].lstrip():
        return True
    top = [x for x in live if x[0] != " "]
    for n, line in enumerate(top):
        plain = PLAIN_KEY.match(line)
        shaped = plain or line == "-" or line.startswith("- ") or (n == 0 and line.strip() == "---")
        if not shaped or (plain and line.split(":")[0].strip() in ("include", "workflow")):
            return True
    return _yaml_extras(text) or any(OVERRIDE.search(workflow_triggers.strip_comment(x)) for x in text.splitlines())


def _shared_deploys(text: str) -> bool:
    """Whether a top-level `default:`, `before_script:`, `after_script:`, `image:`, or `services:` holds a deploy word. Every job
    runs those, so then every job deploys."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^(?:default|before_script|after_script|image|services)\s*:", line):
            if any(signals.names_a_deploy(x.split(" #")[0]) for x in [line, *signals.block_under(lines, i)]):
                return True
    return False


def _job_keys(job: list[str]) -> dict[str, Section] | None:
    """The keys directly under a job's name, each as the text after its colon and its (indent, text) lines, with comments
    dropped. None for a job this does not read: a value on the name's own line, a tab in an indent, a key twice, or a line at
    the keys' indent that is no `key:` and no `- ` item of the key above."""
    if workflow_triggers.strip_comment(job[0].split(":", 1)[-1]).strip() or any("\t" in x[: len(x) - len(x.lstrip())] for x in job[1:]):
        return None
    body = [(len(x) - len(x.lstrip(" ")), workflow_triggers.strip_comment(x.strip())) for x in job[1:] if x.strip() and not x.lstrip().startswith("#")]
    keys: dict[str, Section] = {}
    current = ""
    for indent, text in body:
        if indent == body[0][0] and not (current and not keys[current][0] and (text == "-" or text.startswith("- "))):
            found = JOB_KEY.fullmatch(text)
            if not found or found.group(2) in keys:
                return None
            current = found.group(2)
            keys[current] = ((found.group(3) or "").strip(), [])
        elif not current or indent < body[0][0]:
            return None
        else:
            keys[current][1].append((indent, text))
    return keys


def _condition(raw: str, default_branches: list[str]) -> tuple[list[str], list[str]] | None:
    """The (branches, tags) one rule condition names, or None. Only the whole of `raw` matching one comparison reads: a block
    scalar marker, a `||`, or a part-quoted value matches none."""
    quoted = DOUBLE.fullmatch(raw) or SINGLE.fullmatch(raw)
    cond = raw[1:-1].strip() if quoted else raw
    branch = BRANCH_TEST.fullmatch(cond)
    if branch:  # `$CI_DEFAULT_BRANCH` with no branch named is a branch no one has named: not every branch
        return (([branch.group(1)] if branch.group(1) else default_branches), []) if branch.group(1) or default_branches else None
    return ([], ["*"]) if TAG_TEST.fullmatch(cond) else None  # "every tag" is the wider reading of any tag pattern


def _rule_refs(section: Section, default_branches: list[str]) -> tuple[list[str], list[str]] | None:
    """The refs of a `rules:` section: every line is an entry `- if: <cond>` or the `when:` that follows it, or the job is unread."""
    inline, lines = section
    branches: list[str] = []
    tags: list[str] = []
    entry, seen_when = -1, False
    for indent, text in lines if not inline else []:
        start = re.fullmatch(r"(-\s+)if\s*:\s+(.+)", text) if indent == lines[0][0] else None
        when = re.fullmatch(r"when\s*:\s+(\S+)", text) if indent == entry and not seen_when else None
        if start and (refs := _condition(start.group(2), default_branches)):
            (branches, tags), entry, seen_when = ([*branches, *refs[0]], [*tags, *refs[1]]), indent + len(start.group(1)), False
        elif when and when.group(1) in RULE_WHEN:
            seen_when = True
        else:
            return None
    return (list(dict.fromkeys(branches)), list(dict.fromkeys(tags))) if branches or tags else None


def _listed_names(section: Section) -> list[str] | None:
    """The branch names of an `only:` or `except:` section: `[a, b]` on its line, or `- a` lines at one indent under it. None for
    anything else, and for a name that is a kind of pipeline, a /regular expression/, or not a plain branch name."""
    inline, lines = section
    if inline:
        items = inline[1:-1].split(",") if inline[0] == "[" and inline[-1] == "]" and not lines else []
    else:
        found = [re.fullmatch(r"-\s+(.+)", text) for _, text in lines]
        items = [m.group(1) for m in found if m] if len({i for i, _ in lines}) == 1 and all(found) else []
    names = [x.strip()[1:-1] if DOUBLE.fullmatch(x.strip()) or SINGLE.fullmatch(x.strip()) else x.strip() for x in items]
    return names if names and all(BRANCH_NAME.fullmatch(n) and n not in PIPELINE_KINDS for n in names) else None


def gitlab_refs(job: list[str], default_branches: list[str]) -> tuple[list[str], list[str]] | None:
    """The branches and tags a GitLab job runs on, or None when it runs on every ref or this does not fully read how it is
    filtered. The job is read only if all of its `rules:`, `only:`, and `except:` lines fit this grammar, else it is unread:

    - the keys directly under the job's name are `key:` lines (and `- ` items of the key above); the job holds no `extends:` or
      merge key, and no `rules:` beside `only:` or `except:` (an anchor, alias, or tag unreads the file: `gitlab_file_unread`);
    - a rules entry is `- if: <cond>` on one line, then an optional `when:` line aligned with `if` and set to `on_success`,
      `always`, `manual`, or `on_failure`; any other line in the section, such as a deeper one, makes the job unread;
    - `<cond>` is one plain or quoted scalar: `$CI_COMMIT_BRANCH == "x"` (or `$CI_COMMIT_REF_NAME`, or `== $CI_DEFAULT_BRANCH`),
      `$CI_COMMIT_TAG`, or `$CI_COMMIT_TAG =~ /re/` with no unescaped `/`; no block scalar, no continuation, no `||`, `&&`, `!`,
      or group, and no other variable;
    - `only:` is `[a, b]` or `- a` lines of plain branch names (not a kind of pipeline such as `tags` or `pushes`, and no
      /regular expression/); `except:`, when present, fits the same shape and narrows the job, so it is not read further."""
    keys = _job_keys(job)
    if keys is None or "extends" in keys:
        return None  # rules a template brings are not in these lines
    if "rules" in keys:
        return None if {"only", "except"} & keys.keys() else _rule_refs(keys["rules"], default_branches)
    only = _listed_names(keys["only"]) if "only" in keys else None
    if only is None or ("except" in keys and _listed_names(keys["except"]) is None):
        return None
    return list(dict.fromkeys(only)), []


def _gitlab_deploys(job: str, lines: list[str]) -> bool:
    """Whether a GitLab job with no `environment:` clearly deploys: GitLab Pages' `pages` job, a `deploy` stage, or a script line
    that runs a deploy by its words. A value on the job's own line, as in a flow map, is read as one line too."""
    own = workflow_triggers.strip_comment(lines[0].split(":", 1)[-1])
    return (
        job == "pages"
        or any(re.match(r"^\s+[\"']?stage[\"']?\s*:\s*['\"]?deploy", x) or signals.names_a_deploy(x.split(" #")[0]) for x in lines[1:])
        or bool(own.strip() and re.search(r"environment|deploy|pages", own, re.I))
    )


def gitlab_environment(job: list[str], fallback: str) -> tuple[str, int] | None:
    """The config name of a GitLab job's `environment:` and its line offset in the job, or None when it names none."""
    for i, line in enumerate(job):
        key = re.match(r"^\s+[\"']?environment[\"']?\s*:\s*(.*?)\s*(#.*)?$", line)
        if not key:
            continue
        inline = key.group(1)
        if inline.startswith("{"):
            inline = _map_name(inline)
        elif not inline:
            inline = next((m.group(1) for m in (re.match(r"^\s*name\s*:\s*(.+?)\s*$", x) for x in signals.block_under(job, i)) if m), "")
        return environment_name(inline, fallback), i
    return None


def _merged(found: list[Found]) -> tuple[Found, ...]:
    """One `Found` for each name, with its refs and places joined in the order they were read."""
    by_name: dict[str, Found] = {}
    for f in found:
        old = by_name.get(f.name, Found(f.name))
        join = lambda a, b: tuple(dict.fromkeys([*a, *b]))  # noqa: E731
        by_name[f.name] = Found(f.name, join(old.branches, f.branches), join(old.tags, f.tags), join(old.where, f.where))
    return tuple(by_name.values())


def _github(path: str, text: str, rs: risk.RuleSet, found: list[Found], unread: list[str]) -> None:
    line = signals.deploy_line(text, rs)
    if line is None:
        return
    listed = push_refs(text)
    refs = clean_refs(listed)
    if refs is None or not SAFE_PATH.fullmatch(path):
        if listed is not None or workflow_triggers.push_reaches(text, SOME_BRANCH):
            unread.append(f"{documents.one_line(path, 160)}:{line}")
        return
    stem = environment_name(Path(path).stem, "deploy")
    named = github_environments(text, stem) or [(stem, line)]
    found += [Found(name, tuple(refs[0]), tuple(refs[1]), (f"{path}:{n}",)) for name, n in named]


def _gitlab(text: str, default_branches: list[str], found: list[Found], unread: list[str]) -> None:
    jobs = gitlab_jobs(text)
    whole = gitlab_file_unread(text)
    before = len(unread)
    shared = {n for n, (_, ls) in gitlab_jobs(text, templates=True).items() if gitlab_environment(ls, "x") or _gitlab_deploys(n, ls)}
    shared_deploy = _shared_deploys(text)
    for job, (start, lines) in jobs.items():
        if shared_deploy or any(re.match(r"^\s+[\"']?trigger[\"']?\s*:", x) for x in lines[1:]):
            unread.append(f"{GITLAB_FILE}:{start}")  # every job runs the shared lines, and a `trigger:` job runs another pipeline
            continue
        stem = environment_name(job, "deploy")
        env = gitlab_environment(lines, stem)
        extends = any(re.match(r"^\s+[\"']?extends[\"']?\s*:", x) for x in lines[1:])
        if env is None:
            if _gitlab_deploys(job, lines) or (extends and shared - {job}):
                unread.append(f"{GITLAB_FILE}:{start}")  # it deploys, and no `environment:` says where
            continue
        name, offset = env
        where = f"{GITLAB_FILE}:{start + offset}"
        refs = None if whole else clean_refs(gitlab_refs(lines, default_branches))
        if refs is None:
            unread.append(where)
        else:
            found.append(Found(name, tuple(refs[0]), tuple(refs[1]), (where,)))
    mention = next(
        (
            n
            for n, x in enumerate(text.splitlines(), 1)
            if re.search(r"""["']?environment["']?\s*:|stage["']?\s*:\s*["']?deploy""", x) or signals.names_a_deploy(x)
        ),
        0,
    )
    if (whole or shared_deploy) and mention and len(unread) == before:
        unread.append(f"{GITLAB_FILE}:{mention}")  # a file read as a whole that names a deploy, in no job this found


def _workflows(root: Path) -> list[tuple[str, str | None]]:
    """Each workflow file of the working tree of `root` as (path, text), in name order. The text is None for one that is not a
    regular file or is too large, such as a link: it may deploy, so the callers count it as unread."""
    try:
        names = sorted(p.name for p in (root / WORKFLOW_FOLDER).iterdir() if p.suffix in (".yml", ".yaml") and not p.is_dir())
    except OSError:
        return []
    return [(f"{WORKFLOW_FOLDER}/{name}", regular_files.repository_text(root, f"{WORKFLOW_FOLDER}/{name}")) for name in names]


def read_deploy_evidence(root: Path, default_branches: list[str], rs: risk.RuleSet | None = None) -> Evidence:
    """What the workflows in the working tree of `root` say deploys on a push, under the rules `rs` (the built-in ones by
    default). `default_branches` are the names `$CI_DEFAULT_BRANCH` can mean (none: it is unread). The delegate check reads the tip's files itself."""
    rules = rs or risk.rule_set(None)
    found: list[Found] = []
    unread: list[str] = []
    for path, text in _workflows(root):
        if text is None:
            unread.append(f"{documents.one_line(path, 160)} (not a regular file, or too large)")
        else:
            _github(path, text, rules, found, unread)
    gitlab = regular_files.repository_text(root, GITLAB_FILE)
    if gitlab is not None:
        _gitlab(gitlab, default_branches, found, unread)
    elif os.path.lexists(root / GITLAB_FILE):
        unread.append(f"{GITLAB_FILE} (not a regular file, or too large)")
    return Evidence(_merged(found), tuple(unread))


def gitlab_deploying_on(text: str, branch: str, default_branches: list[str]) -> list[str]:
    """Each job of a `.gitlab-ci.yml` that deploys on a push to `branch`, as `path:line`: one whose rules name `branch`
    (`$CI_DEFAULT_BRANCH` is any of `default_branches`), or whose rules this cannot read."""
    found: list[Found] = []
    unread: list[str] = []
    _gitlab(text, default_branches, found, unread)
    return [w for f in found if risk.deploys_to([f.entry()], "branches", branch) for w in f.where] + unread


def workflows_deploying_on(root: Path, branch: str, rs: risk.RuleSet) -> list[str]:
    """Each workflow in the working tree of `root` that deploys on a push to `branch`, as `path:line`. It reads a GitHub workflow
    as the delegate check reads the tip's, so a trigger it cannot read counts as reaching the branch. A GitLab job counts when
    its rules name `branch` (`$CI_DEFAULT_BRANCH` is `branch`) or this cannot read them."""
    out = []
    for path, text in _workflows(root):
        line = None if text is None or not workflow_triggers.push_reaches(text, branch) else signals.deploy_line(text, rs)
        if text is None or line:
            out.append(f"{documents.one_line(path, 160)}{' (unreadable)' if text is None else f':{line}'}")
    gitlab = regular_files.repository_text(root, GITLAB_FILE)
    if gitlab is None:
        return out + ([f"{GITLAB_FILE} (unreadable)"] if os.path.lexists(root / GITLAB_FILE) else [])
    return out + gitlab_deploying_on(gitlab, branch, [branch])
