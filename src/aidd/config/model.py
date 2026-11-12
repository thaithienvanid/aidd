"""The config as aidd reads it: `Config`, the merged `.aidd/config.yaml`, and the defaults and value sets its keys take."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

from aidd.config import limits
from aidd.kernel import globs, resources

CONFIG_PATH = ".aidd/config.yaml"
# The config schema as one file, for an editor's YAML language server (`aidd gen-docs` writes it), and the first line of
# the config `aidd init` writes, which names it at this aidd's release: the editor then completes and explains each key.
EDITOR_SCHEMA = "schemas/editor/config.json"
SCHEMA_MODELINE = re.compile(
    r"(?m)^# yaml-language-server: \$schema=https://raw\.githubusercontent\.com/thaithienvanid/aidd/v[^/\s]+/schemas/editor/config\.json$"
)


def schema_modeline(version: str) -> str:
    """The config's first line: where an editor finds the schema of this aidd's release."""
    return f"# yaml-language-server: $schema=https://raw.githubusercontent.com/thaithienvanid/aidd/v{version}/{EDITOR_SCHEMA}"


# The routes, in order of ceremony: a route is advice about how much of the loop a change needs.
# `common.schema.json` `$defs/route` lists them, and a test ties this tuple to it: importing the config reads no data file.
ROUTES = ("minor", "normal", "major", "emergency")
ROUTE_RANK = {route: rank for rank, route in enumerate(ROUTES)}
# The routes that write the Spec before the code: the ones whose steps in `loop.routes` (schemas/roles.json) start with Specify.
SPEC_FIRST_ROUTES = ("normal", "major")
PROFILES = ("solo", "team")


# What a user-facing surface looks like in a Task's scope: web and mobile screens, components, and styles.
UI_PATHS = [
    *(f"**/*.{ext}" for ext in ("tsx", "jsx", "vue", "svelte", "astro", "html", "css", "scss", "swift", "dart", "xib", "storyboard")),
    *(f"**/{d}/**" for d in ("components", "pages", "screens", "views", "ui", "web", "frontend", "layouts", "templates")),
    "**/res/layout/**",
]


def area_paths(name: str) -> list[str]:
    """The paths of the built-in risk area `name` (schemas/risks.json), read when first asked, never at import."""
    area = resources.load_json("risks.json")["areas"].get(name) or {}
    return list(area.get("paths", []))


def area_exclude(name: str) -> list[str]:
    """The paths the built-in risk area `name` leaves out (schemas/risks.json), read when first asked, never at import."""
    area = resources.load_json("risks.json")["areas"].get(name) or {}
    return list(area.get("exclude", []))


def test_paths() -> list[str]:
    """What a test file looks like, as globs over a repository path (`test_paths` in schemas/risks.json), read when first asked."""
    return list(resources.load_json("risks.json")["test_paths"])


def looks_like_test(rel: str, *, fold_case: bool = False) -> bool:
    """Whether the repository path `rel` is a test file, or sits in a test folder, by `test_paths`. The case must match,
    unless `fold_case`: the delegate check ignores case, as macOS and Windows do, so it errs toward a test."""
    return globs.match_any(test_paths(), rel, fold_case=fold_case)


@functools.cache
def route_words() -> dict[str, str]:
    """How a person reads each route, from `x-words` in common.schema.json's `route`, such as "no Spec" for `minor`. Read when
    first asked, never on import."""
    return dict(resources.load_json("common.schema.json")["$defs"]["route"]["x-words"])


def deploy_paths() -> list[str]:
    """What a service or deploy change looks like in a Task's scope: the `infra` area's paths, and a deploy or release file."""
    named = ["**/deploy/**", "**/deployment/**", "**/*deploy*.*", "**/*release*.yml", "**/*release*.yaml"]
    return area_paths("infra") + named


def major_conditions() -> list[dict]:
    """The reasons a major change needs a tech spec and a runbook, as `any_of` condition sets: a dimension that can harm
    data, people, money, or a service, an irreversible change, or a service or deploy path."""
    return [
        {"dimensions": [*MAJOR_DIMENSIONS, "availability"]},  # availability needs the documents, though it never makes a route major
        {"irreversible": True},
        {"paths": deploy_paths()},
    ]


@functools.cache
def default_docs_required() -> dict[str, list[dict]]:
    """The documents a Spec should link, by route and condition: for each type, a list of rows. A row names the routes
    where it makes `aidd validate` warn (`routes`) and those where `aidd new spec` only suggests (`suggest`), and the
    conditions that must all hold (`any_of`: one of these condition sets must hold). The highest level any matching row
    gives wins. A row with `living` set asks for a linked doc that is living (`true`) or frozen (`false`); without it,
    any linked doc of the type answers. `docs.disabled` turns a type off. Built when first asked, so importing the
    config reads no data file."""
    auth, secrets = area_paths("auth"), area_paths("secrets")
    normal_and_major = ["normal", "major"]
    return {
        "tech-spec": [{"routes": ["major"], "any_of": major_conditions()}],
        # A linked runbook, the standing on-call procedure, answers. So does the Spec's own `## Rollout`, for a change that
        # releases in stages (doc_checks.INLINE_DOC_SECTIONS).
        "runbook": [{"routes": ["major"], "any_of": major_conditions()}],
        "threat-model": [
            {"routes": normal_and_major, "any_of": [{"dimensions": ["security", "privacy", "data"]}, {"compliance": True, "paths": auth + secrets}]}
        ],
        "authz-matrix": [{"routes": normal_and_major, "paths": auth, "any_of": [{"dimensions": ["security"]}, {"compliance": True}]}],
        "design-spec": [{"routes": ["major"], "suggest": ["normal"], "change_types": ["feat"], "paths": UI_PATHS}],
        # The test plan, at its scopes: the Spec's own plan is expected on a major change, and on a normal one with a
        # compliance dimension, or compliance on, and suggested on any other normal change (a manual acceptance or a device
        # path included). With compliance on, the component's living plan is expected too.
        "test-plan": [
            {"routes": ["major"], "living": False},
            {"routes": ["normal"], "living": False, "any_of": [{"dimensions": ["compliance"]}, {"compliance": True}]},
            {"suggest": ["normal"], "living": False},
            {"routes": normal_and_major, "compliance": True, "living": True},
        ],
        "migration-plan": [{"routes": ["major"], "suggest": ["normal"], "any_of": [{"dimensions": ["data"]}, {"irreversible": True}]}],
        "tracking-plan": [{"routes": normal_and_major, "hypothesis": True}],
        # Personal data: the compliance record holds the DPIA (GDPR Art. 35) the compliance analyst plans, and the data map is
        # the living inventory and records of processing (Art. 30) it keeps.
        "compliance-record": [{"routes": normal_and_major, "dimensions": ["privacy"]}],
        "data-map": [{"suggest": normal_and_major, "dimensions": ["privacy"]}],
    }


class ConfigError(ValueError):
    pass


class ConfigUnreadable(ConfigError):
    """The config does not load and the command that decides stops: the message says why and the next step."""


@dataclass
class Config:
    raw: dict
    profile: str
    warnings: list[str] = field(default_factory=list)
    # The repository paths of the parent configs it was built from (`extends: [{path: ...}]`, at any depth).
    parent_paths: tuple[str, ...] = ()
    # Which `extends` preset each rule in `risks.rules` came from, by its selector: `preset <path or url>`, or `org
    # preset` for AIDD_ORG_PRESET. A rule this file sets itself has no entry, so it reads `config`.
    rule_sources: dict[tuple, str] = field(default_factory=dict)
    # Every environment a parent config defines, at any depth, whether or not this file's `environments` replaced it.
    parent_environments: tuple[dict, ...] = ()
    # Whether this repository's own config sets `environments`, as against inheriting it from a parent.
    sets_environments: bool = False

    def get(self, *keys, default=None):
        node = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def setting(self, path: str):
        """The value of the config key at the dotted `path` (`limits.max_task_retries`), else the default its schema gives."""
        return self.get(*path.split("."), default=limits.setting_default(path))

    @property
    def approvers(self) -> list[str]:
        """The people the agents ask for a decision, in order (`owners.approvers`); empty means whoever directs them."""
        return list(self.get("owners", "approvers", default=[]))

    @property
    def specialists(self) -> dict[str, list[str]]:
        return dict(self.get("owners", "specialists", default={}))

    @property
    def specs_dir(self) -> str:
        return globs.normal_dir(str(self.get("specs_dir", default="specs")))

    @property
    def proposals_dir(self) -> str:
        return globs.normal_dir(str(self.get("proposals_dir", default="proposals")))

    @property
    def docs_dir(self) -> str:
        return globs.normal_dir(str(self.get("docs", "dir", default="docs")))

    @property
    def docs_required(self) -> dict[str, list[dict]]:
        off = self.get("docs", "disabled", default={}) or {}
        return {k: v for k, v in default_docs_required().items() if not off.get(k)}

    @property
    def standards(self) -> list[dict]:
        return list(self.get("standards", default=[]))

    @property
    def standards_policy(self) -> dict:
        return dict(self.get("standards_policy", default={}) or {})

    @property
    def max_runbook_age_days(self) -> int:
        return int(self.setting("docs.max_runbook_age_days"))

    @property
    def max_review_age_days(self) -> int:
        return int(self.setting("docs.max_review_age_days"))

    @property
    def max_task_retries(self) -> int:
        """The retries one Task gets (`limits.max_task_retries`)."""
        return int(self.setting("limits.max_task_retries"))

    @property
    def max_paths_shown(self) -> int:
        """The paths of one area an `aidd risk` answer lists (`limits.max_paths_shown`)."""
        return int(self.setting("limits.max_paths_shown"))

    @property
    def tests(self) -> list[dict]:
        return list(self.get("tests", default=[]))


# The config of a repository with none: every setting at its default, and the solo profile. A caller with no config reads
# `(cfg or EMPTY)`, so each default folder and the default profile has this one owner.
EMPTY = Config(raw={}, profile="solo")


# The types of document a Spec links in `docs` (spec.schema.json#/$defs/doc), in the schema's order.
DOC_TYPES = (
    "tech-spec",
    "test-plan",
    "design-spec",
    "design-files",
    "adr",
    "threat-model",
    "authz-matrix",
    "api",
    "runbook",
    "slo",
    "compliance-record",
    "tracking-plan",
    "migration-plan",
    "acceptance",
    "data-map",
    "vendors",
    "other",
)


# The specialist pool that reviews each risk dimension that makes a change major.
POOL_OF = {"data": "data", "security": "security", "privacy": "privacy", "financial": "finance", "compliance": "compliance"}
# The risk dimensions that make a change major, and so need a specialist and a tech spec.
MAJOR_DIMENSIONS = tuple(POOL_OF)


def route_of_risk(dimensions: list[str] | tuple[str, ...], irreversible: bool) -> str:
    """The least route a change's risk gives on its own, as `aidd risk` gives it for declared risk and no path: major for a dimension
    in MAJOR_DIMENSIONS or a change a revert cannot undo, normal for any other dimension, and minor for none
    (tests/test_change_types.py holds it equal to the router's answer)."""
    if irreversible or set(dimensions) & set(MAJOR_DIMENSIONS):
        return "major"
    return "normal" if dimensions else "minor"
