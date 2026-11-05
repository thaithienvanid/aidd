"""What `aidd init` fills in: the starting .aidd/config.yaml, the Dependabot file, and the verification block that says
what done means.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from aidd import __version__, config
from aidd.kernel import documents, resources, strict_yaml
from aidd.kernel import text as kernel_text
from aidd.setup import detection

# The owner_team a solo repository's Specs get, so none starts with a TODO.
SOLO_TEAM = "maintainers"
# The smoke test `aidd init` binds when it finds no test command, so the first change has a suite to pass: every tracked
# Python file parses, and no tracked file holds a merge-conflict marker. Replace it with the real suite.
SMOKE_TEST: list[str] = [
    "python3",
    "-c",
    "import ast, subprocess, sys\n"
    "bad = []\n"
    "for p in subprocess.run(['git', 'ls-files', '-z'], capture_output=True, text=True).stdout.split('\\0'):\n"
    "    try:\n"
    "        t = open(p, encoding='utf-8').read()\n"
    "        if p.endswith('.py'):\n"
    "            ast.parse(t, p)\n"
    "    except SyntaxError as e:\n"
    "        bad.append(f'{p}:{e.lineno}: {e.msg}')\n"
    "        continue\n"
    "    except (OSError, ValueError):\n"
    "        continue\n"
    "    if '\\n<<<<<<< ' in '\\n' + t:\n"
    "        bad.append(f'{p}: a merge-conflict marker')\n"
    "print('\\n'.join(bad) or 'smoke: the tracked Python files parse, and no file holds a conflict marker')\n"
    "sys.exit(1 if bad else 0)\n",
]


DEPENDABOT = ".github/dependabot.yml"
# A manifest's file name and the Dependabot ecosystem that updates it; `*.csproj` and `*.tf` match by suffix.
DEPENDABOT_ECOSYSTEMS = {
    "package.json": "npm",
    "pyproject.toml": "pip",
    "requirements.txt": "pip",
    "Pipfile": "pip",
    "go.mod": "gomod",
    "Cargo.toml": "cargo",
    "Gemfile": "bundler",
    "composer.json": "composer",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    ".csproj": "nuget",
    "Dockerfile": "docker",
    "mix.exs": "mix",
    "pubspec.yaml": "pub",
    "Package.swift": "swift",
    ".tf": "terraform",
}


def origin_repo(root: Path) -> str | None:
    """The GitHub `owner/name` of `origin` when a person runs `aidd init`, if it is one; else None."""
    from aidd.kernel import git

    url = git.run(["remote", "get-url", "origin"], str(root), check=False).strip()
    m = re.match(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$", url)
    return m.group(1) if m and m.group(1).split("/")[1] not in (".", "..") else None


@dataclass(frozen=True)
class ConfigTemplate:
    """The values `config_text` fills the config template with: `aidd init`'s options, and what `written_by_init` reads
    back from a config to render it again."""

    profile: str
    approvers: list[str] | None = None
    specialists: dict[str, list[str]] | None = None
    test: list[str] | None = None
    test_name: str = "unit"
    default_owner_team: str | None = None
    risk_areas: list[dict] | None = None
    stack: list[str] | None = None
    preview: list[str] | None = None
    ui: bool = True
    compliance_targets: list[str] | None = None
    repo: str | None = None
    existing_code: bool = False


def config_text(template: ConfigTemplate) -> str:
    """The starting .aidd/config.yaml, filled from the skill's template. `risk_areas` are the sensitive folders `aidd
    init` detected, written as `risks.areas` with a rule that asks before an edit there; `stack` is the technology radar
    it detected, written as a commented `project.stack`; `preview`, the local preview command when `preview_command`
    found an obvious one, else a commented example; `ui` False (a command-line tool or a library) writes the interface
    product defaults off, with the reason. `repo` is the GitHub `owner/name` of `origin`, written as `project.repo`.
    `existing_code` (a repository that already has a structure) writes the `modular_monolith` default off."""
    tpl = config.schema_modeline(__version__) + "\n" + (resources.data_dir("skill") / "assets" / "config.yaml").read_text(encoding="utf-8")
    flow = strict_yaml.flow
    pools = "\n".join(f"    {strict_yaml.key(pool)}: {flow(who)}" for pool, who in (template.specialists or {}).items())
    test_entry = {"name": template.test_name, "command": template.test} if template.test else None
    text = kernel_text.fill_template(
        tpl,
        profile=strict_yaml.scalar(template.profile),
        approvers=flow(template.approvers)
        if template.approvers
        else '[]   # the people agents ask for a decision, such as ["@you"]; empty: whoever directs them',
        specialists=f"  specialists:\n{pools}" if pools else '  # specialists:\n  #   security: ["@org/security"]',
        tests=(
            (SMOKE_COMMENT if template.test == SMOKE_TEST else "") + strict_yaml.dump({"tests": [test_entry]}).rstrip("\n")
            if test_entry
            else "# tests:\n#   - name: unit\n#     command: [npm, test]"
        ),
        preview=f'preview:\n  command: {flow(template.preview)}\n  # url: "http://localhost:3000"'
        if template.preview
        else '# preview:\n#   command: [docker, compose, up, --build]   # starts the app with its seed data\n#   url: "http://localhost:3000"',
    )
    if template.default_owner_team:
        text = text.replace('  # default_owner_team: "@org/team"', f"  default_owner_team: {strict_yaml.scalar(template.default_owner_team)}", 1)
    if template.risk_areas:
        text = text.rstrip("\n") + "\n\n" + RISK_COMMENT + detection.risk_areas_yaml(template.risk_areas)
    project = config.project_block(
        repo=template.repo, stack=template.stack, ui=template.ui, existing_code=template.existing_code, compliance=template.compliance_targets
    )
    return text.rstrip("\n") + "\n\n" + project


COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")


# The detected technology radar, which config_text writes only as comments (config.project_block).
_STACK_ADOPT = re.compile(r"^ *# *stack:\n *# *adopt: (\[.*\])$", re.M)


def written_by_init(text: str) -> bool:
    """Whether `text` is a config `aidd init` writes: rendered again from what it holds (and from the commented stack
    radar init wrote), it is the same text. `aidd uninstall` removes only such a config. An edit init could not make,
    such as a comment or a field it never writes, keeps it; another value init writes, such as another goal, does not."""
    try:
        raw = documents.parse_yaml(text, "config")
        owners, tests, project = raw.get("owners") or {}, raw.get("tests") or [], raw.get("project") or {}
        disabled = (project.get("defaults") or {}).get("disabled") or {}
        stack = _STACK_ADOPT.search(text)
        rendered = config_text(
            ConfigTemplate(
                raw.get("profile", "solo"),
                approvers=owners.get("approvers"),
                specialists=owners.get("specialists"),
                test=tests[0].get("command") if tests else None,
                test_name=tests[0].get("name", "unit") if tests else "unit",
                default_owner_team=owners.get("default_owner_team"),
                risk_areas=[
                    {"name": k, "paths": v.get("paths", []), "dimensions": v.get("dimensions", [])}
                    for k, v in ((raw.get("risks") or {}).get("areas") or {}).items()
                ]
                or None,
                stack=documents.parse_yaml(f"adopt: {stack.group(1)}", "stack")["adopt"] if stack else None,
                preview=(raw.get("preview") or {}).get("command"),
                ui=disabled.get("dark_mode") != config.PROJECT_NO_UI,
                compliance_targets=(project.get("compliance") or {}).get("targets"),
                repo=project.get("repo"),
                existing_code=disabled.get("modular_monolith") == config.EXISTING_STRUCTURE,
            )
        )
    except Exception:  # noqa: BLE001  # a config init could not have written: the person's, so it stays
        return False
    return rendered == text


def preview_command(root: Path) -> list[str] | None:
    """The local preview command when it is obvious: a Docker Compose file at the root. None otherwise; guessing a
    command that does not start the app would send the verifier after the wrong thing."""
    return ["docker", "compose", "up", "--build"] if any((root / f).is_file() for f in COMPOSE_FILES) else None


SMOKE_COMMENT = (
    "# `aidd init` found no test command, so this smoke test holds the place of one: every tracked Python file parses, and no\n"
    "# tracked file holds a merge-conflict marker. Replace it with your suite, as its own change.\n"
)
RISK_COMMENT = (
    "# Sensitive areas `aidd init` found from folder names alone (a guess, not a finding): an agent asks before it edits\n"
    "# one, and a change there needs a Spec. Remove an area that is wrong, or narrow its paths.\n"
)


def dependabot_text(root: Path) -> str:
    """templates/github/dependabot.yml with an entry per ecosystem whose manifest sits at the root or one or two
    folders down (skipping dependency and build folders): a cheap walk, never the whole tree."""
    from aidd.setup.detection import SKIP

    found: dict[str, set[str]] = {}

    def walk(d: Path, depth: int) -> None:
        try:
            entries = sorted(d.iterdir())
        except OSError:
            return
        for p in entries:
            if p.is_dir() and not p.is_symlink():
                if depth < 2 and p.name not in SKIP and not p.name.startswith("."):
                    walk(p, depth + 1)
                continue
            eco = DEPENDABOT_ECOSYSTEMS.get(p.name) or next((e for k, e in DEPENDABOT_ECOSYSTEMS.items() if k.startswith(".") and p.name.endswith(k)), None)
            if eco:
                rel = p.parent.relative_to(root).as_posix()
                found.setdefault(eco, set()).add("/" if rel == "." else f"/{rel}")

    walk(root, 0)
    text = (resources.data_dir("templates") / "github" / "dependabot.yml").read_text(encoding="utf-8")
    for eco, dirs in sorted(found.items()):
        listed = ", ".join(json.dumps(x) for x in sorted(dirs))
        text += (
            f"\n  - package-ecosystem: {eco}\n    directories: [{listed}]\n    schedule:\n      interval: monthly\n"
            f'    cooldown:\n      default-days: 7\n    groups:\n      {eco}:\n        patterns: ["*"]\n'
        )
    return text


VERIFY_HEADING = "### Verifying your work"


def configured_tests(root: Path) -> list[dict]:
    """The `tests` of the repository's config as init left it (`--test`, or what an existing config already names):
    each `{"command": [...], "when_changed": [...]}`, the filter empty when the test always runs."""
    try:
        raw = documents.parse_yaml((root / config.CONFIG_PATH).read_text(encoding="utf-8"), "config")
    except (OSError, UnicodeDecodeError, documents.DocumentError):
        return []
    tests = raw.get("tests")
    if not isinstance(tests, list):
        return []
    return [
        {"command": [str(a) for a in t["command"]], "when_changed": [str(p) for p in t.get("when_changed") or []]}
        for t in tests
        if isinstance(t, dict) and isinstance(t.get("command"), list)
    ]


def verification_block(tests: list[dict]) -> str:
    """What "done" means: the commands to run and paste before reporting a task complete, as a `###` subsection of
    aidd's AGENTS.md section, so uninstall removes it with the rest."""
    if not tests:
        steps = [
            "the repository's tests (none configured yet: add `tests` to `.aidd/config.yaml`)",
            "`aidd test`: the Spec's tests, red on base and green on head",
        ]
    else:
        always = [f"`{shlex.join(t['command'])}`" for t in tests if not t["when_changed"]]
        selected = " and each test this diff selects" if len(always) < len(tests) else ""
        runs = f"runs {', '.join(always)}{selected} once" if always else "runs the tests this diff selects"
        skips = [f"   - `{shlex.join(t['command'])}`: run it yourself when this diff does not select it (`when_changed`)" for t in tests if t["when_changed"]]
        skips += ["   - on the emergency route `aidd test` runs only the smoke tests: run the rest yourself"]
        steps = [
            f"`aidd test`: {runs}, the Spec's tests red on base and green on head. Paste its result lines and its `evidence:` line;"
            " never run the same tests again on this head. Run a test directly only where `aidd test` leaves it out:\n" + "\n".join(skips)
        ]
    lines = "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1))
    return (
        f"{VERIFY_HEADING}\n\nBefore you report a task that changed code or tests complete, run these and paste their output:\n\n{lines}\n\n"
        "`aidd test` finds the Spec in the diff; name it with `--spec specs/<ID>.md`. "
        "If a test fails, fix the code, not the test: never skip, weaken, or delete a failing test.\n"
    )
