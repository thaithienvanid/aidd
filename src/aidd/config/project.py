"""The project's constraints and rules: `project` in .aidd/config.yaml.

Humans set them: a technology radar (`adopt`, `trial`, `hold`), the hosting, a budget, the team's own rules each with
its why (BCP 14 levels), and time-boxed waivers a person approves. Agents read them in Specify and Review, `aidd risk
--paths` prints the rules that apply to the paths in question, and `aidd validate` checks them. aidd never
reads them: a rule is enforced by its `check`, a command or a `tests` entry, or by a reviewer.

A parent config that lists `project` in `locks` binds its `project`: a child adds rules, raises a rule's requirement level, adds
to the stack lists, and tightens the budget; it never lowers a requirement level, waives a locked rule, adopts what the parent
holds, raises the spend, or moves the hosting.
"""

from __future__ import annotations

import copy
import datetime as dt
import functools
import re

from aidd.config import identities, model
from aidd.config.harness_settings import PACKS_PLUGIN
from aidd.kernel import globs, resources, strict_yaml, timestamps
from aidd.kernel.documents import fmt_number, markdown_section, merge_members, one_line

LEVELS = ("must", "should", "may")  # strictest first
RINGS = ("adopt", "trial", "hold")  # a stack prints its rings in this order
CONTROLS_PACK = "enterprise-controls"
# The targets whose auditors expect separation of duties, which the solo profile waives: `aidd validate` warns.
DUTIES_TARGETS = ("soc2", "iso27001", "hipaa", "pci-dss", "fedramp")
# The EU Cyber Resilience Act: the target that needs a declared support period (Art. 13(8)) and a security.txt.
CRA_TARGET = "cra"
WAIVER_WARNING_DAYS = 14
# A delegation's `review_due` further ahead than this warns. `aidd init --delegate` sets it 90 days ahead, so a date past
# twice that is a choice, and a delegation nobody reviews is the one that goes stale.
DELEGATION_REVIEW_HORIZON_DAYS = 180
# The delegated actions that merge a change. A merge of a change with a Spec counts only the delegate's own accept of the
# Spec's approval, so it needs `spec.approve` delegated too (delegation/action_checks.py, `approval_of`).
DELEGATED_MERGES = ("pr.merge", "git.merge")
# `project.defaults`: what every product gets unless `disabled` names it, with the reason. The order is the schema's, and
# tests/test_product_defaults.py checks it.
PROJECT_DEFAULTS: tuple[str, ...] = (
    "dark_mode",
    "responsive",
    "i18n_ready",
    "perf_budget",
    "public_page_basics",
    "api_conventions",
    "data_conventions",
    "operability",
    "security_headers",
    "legal_placeholders",
    "transactional_email",
    "dev_basics",
    "api_latency",
    "outbound_calls",
    "slo",
    "backup_restore",
    "request_limits",
    "modular_monolith",
)
# The defaults that only a user interface needs: `aidd init` turns them off in a command-line tool or a library.
UI_DEFAULTS = ("dark_mode", "responsive", "perf_budget", "public_page_basics")
PROJECT_NO_UI = "no user interface"
# `aidd init` in a repository that already has code: the structure stays until a person adopts the modular monolith.
EXISTING_STRUCTURE = "an existing structure; an ADR adopts the modular monolith"


# ---- Layering ---------------------------------------------------------------------------------------------------


def merge(parent: dict | None, child: dict, *, locked: bool, where: str, warnings: list[str]) -> dict:
    """A child's `project` over its parent's. Unlocked, a mapping merges member by member and a list the child names replaces
    the parent's; locked, the child may only add or tighten, and whatever would loosen is dropped with a warning."""
    out = copy.deepcopy(parent or {})
    for key, value in child.items():
        if key == "rules":
            out[key] = _merge_rules(out.get(key, []), value, locked, where, warnings)
        elif key == "waivers":
            bound = {r["id"] for r in out.get("rules", [])} if locked else set()
            for w in value:
                if w["rule"] in bound:
                    warnings.append(f"{where}: project.waivers of {w['rule']!r} ignored; a parent config locks the rule, so only it may waive it")
            out[key] = list(out.get(key, [])) + [w for w in value if w["rule"] not in bound]
        elif key == "stack":
            out[key] = _merge_stack(out.get(key, {}), value, locked, where, warnings)
        elif key == "budget":
            out[key] = _merge_budget(out.get(key, {}), value, locked, where, warnings)
        elif key == "defaults":
            out[key] = _merge_defaults(out.get(key, {}), value, locked, where, warnings)
        elif key == "compliance":
            out[key] = _merge_compliance(out.get(key, {}), value, locked)
        elif key == "writing":
            out[key] = _merge_writing(out.get(key, {}), value, locked)
        elif key == "hosting" and locked and out.get(key) and value != out[key]:
            warnings.append(f"{where}: project.hosting {value!r} ignored; a parent config sets {out[key]!r}")
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_members(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _merge_rules(parents: list[dict], children: list[dict], locked: bool, where: str, warnings: list[str]) -> list[dict]:
    """The parent's rules, then the child's. A child rule with a parent's id replaces it, or, when the parent locks
    its rules, may only raise its requirement level. A repeated id inside one file stays repeated, for `aidd validate` to report."""
    out = [dict(r) for r in parents]
    index = {r["id"]: i for i, r in enumerate(parents)}
    for rule in children:
        i = index.get(rule["id"])
        if i is None:
            out.append(dict(rule))
        elif not locked:
            out[i] = dict(rule)
        else:
            mine = out[i]
            if LEVELS.index(rule["requirement_level"]) > LEVELS.index(mine["requirement_level"]):
                warnings.append(
                    f"{where}: project.rules {rule['id']!r} requirement_level {rule['requirement_level']!r} ignored; a parent config locks it at {mine['requirement_level']!r}"
                )
            else:
                mine["requirement_level"] = rule["requirement_level"]
            if any(rule.get(k) != mine.get(k) for k in set(rule) | set(mine) if k != "requirement_level"):
                warnings.append(f"{where}: project.rules {rule['id']!r} is set by a parent config; a child may only raise its requirement_level")
    return out


def _merge_stack(parent: dict, child: dict, locked: bool, where: str, warnings: list[str]) -> dict:
    """Each list adds the child's items. Unlocked, the child's ring wins for an item both name; locked, an item the
    parent holds stays on hold."""
    out = {ring: list(parent.get(ring, [])) for ring in RINGS if ring in parent or ring in child}
    held = {h.lower() for h in parent.get("hold", [])}
    for ring in RINGS:
        for item in child.get(ring, []):
            if locked and ring != "hold" and item.lower() in held:
                warnings.append(f"{where}: project.stack.{ring} {item!r} ignored; a parent config holds it")
                continue
            if not locked:
                for other in RINGS:
                    if other != ring and other in out:
                        out[other] = [x for x in out[other] if x.lower() != item.lower()]
            if item.lower() not in {x.lower() for x in out[ring]}:
                out[ring].append(item)
    return out


def _merge_defaults(parent: dict, child: dict, locked: bool, where: str, warnings: list[str]) -> dict:
    """The child's `disabled` starts from the parent's. `false` turns a default back on, which only tightens, so a lock never
    stops it. A default the child names otherwise is added, unless the parent locks `project`: then only a default the parent
    already disables takes the child's reason, and a default the parent keeps on stays on."""
    out = copy.deepcopy(parent)
    if "disabled" not in child:
        return out
    disabled = dict(parent.get("disabled") or {})
    for key, reason in child["disabled"].items():
        if reason is False:
            disabled.pop(key, None)
        elif locked and key not in disabled:
            warnings.append(f"{where}: project.defaults.disabled.{key} ignored; a parent config keeps it on")
        else:
            disabled[key] = reason
    out["disabled"] = disabled
    return out


def _merge_budget(parent: dict, child: dict, locked: bool, where: str, warnings: list[str]) -> dict:
    out = dict(parent)
    for key, value in child.items():
        cur = parent.get(key)
        if locked and cur is not None and value != cur:
            looser = (key == "max_infra_per_month" and value > cur) or key == "currency"
            if looser:
                warnings.append(f"{where}: project.budget.{key}={value!r} ignored; a parent config sets {cur!r}")
                continue
        out[key] = value
    return out


def _merge_compliance(parent: dict, child: dict, locked: bool) -> dict:
    """The child's targets replace the parent's; locked, they join them, and the later support period's end holds."""
    out = dict(parent)
    if "targets" in child:
        out["targets"] = list(dict.fromkeys([*(parent.get("targets") or []), *child["targets"]])) if locked else list(child["targets"])
    if "support_period" in child:
        mine, theirs = child["support_period"], parent.get("support_period")
        out["support_period"] = theirs if locked and theirs and str(theirs.get("ends_on", "")) > str(mine.get("ends_on", "")) else mine
    return out


def _merge_writing(parent: dict, child: dict, locked: bool) -> dict:
    """The child's `controlled` types replace the parent's; locked, they join them."""
    out = dict(parent)
    if "controlled" in child:
        out["controlled"] = list(dict.fromkeys([*(parent.get("controlled") or []), *child["controlled"]])) if locked else list(child["controlled"])
    return out


def project_compliance(cfg: model.Config | None) -> dict:
    """The project's compliance stance, the one place that decides it: on when `project.compliance` names a target
    (`source` targets), else off. When it is on, the enterprise-controls pack applies, the security docs are asked for
    on security and auth paths, and `aidd init` writes the security CI."""
    c = (cfg.get("project", "compliance", default={}) if cfg else {}) or {}
    targets = list(c.get("targets") or [])
    source = "targets" if targets else "off"
    return {"on": source != "off", "targets": targets, "source": source}


# ---- Checks ------------------------------------------------------------------------------------------------------


def project_findings(cfg: model.Config, today: dt.date | None = None) -> tuple[list[str], list[str]]:
    """(errors, warnings) for `aidd validate`: a repeated rule id, a waiver of an unknown rule or granted by an agent,
    an expired waiver (a warning in its last 14 days), a rule past its `review_due`, a target that expects
    separation of duties under the solo profile, which waives it, the `cra` target's support period, and a delegation whose
    `review_due` is far ahead."""
    today = today or dt.date.today()
    p = cfg.get("project") or {}
    errors: list[str] = []
    warnings: list[str] = []
    rules = p.get("rules", [])
    ids = [r["id"] for r in rules]
    for rid in dict.fromkeys(i for i in ids if ids.count(i) > 1):
        errors.append(f"project.rules: id {rid!r} names {ids.count(rid)} rules; a rule's id is stable and unique")
    test_names = {t["name"] for t in cfg.tests}
    for r in rules:
        for name in r.get("enforced_by", []):
            if name not in test_names:
                errors.append(
                    f"project.rules {r['id']!r}: enforced_by names {name!r}, which is no entry in `tests`; add the command as a `tests` entry, or name one that is there"
                )
        if r.get("requirement_level") not in LEVELS:
            errors.append(f"project.rules {r['id']!r}: requirement_level {r.get('requirement_level')!r} is not one of must, should, may")
        due = timestamps.parse_date(r.get("review_due"))
        if due and due < today:
            warnings.append(f"project.rules {r['id']!r}: review_due {due} has passed; {r['owner']} reviews the rule and sets a new date, or drops it")
    if isinstance(delegation := cfg.get("delegation"), dict):
        warnings += delegation_warnings(delegation, today)
    duties = [t for t in project_compliance(cfg)["targets"] if t in DUTIES_TARGETS]
    if duties and cfg.profile == "solo":
        warnings.append(
            f"project.compliance targets {', '.join(duties)} under the solo profile. Its auditors expect separation of duties, which solo "
            "waives (one person approves their own work). Move to the team profile with a second approver before the audit"
        )
    period_errors, period_warnings = support_period_findings(p.get("compliance") or {}, today)
    errors += period_errors
    warnings += period_warnings
    for w in p.get("waivers", []):
        rid = w["rule"]
        if rid not in ids and rid not in industry_standard_ids():
            errors.append(f"project.waivers: the waiver of {rid!r} names no rule in project.rules and no industry standard in the registry")
        if identities.approver_is_agent(str(w["by"])):
            errors.append(
                f"project.waivers: the waiver of {rid!r} is granted by {w['by']}, an agent or bot account; a person approves a waiver: write the person's `@handle`"
            )
        elif problem := identities.approved_by_problem(str(w["by"]), f"the waiver of {rid!r}: by"):
            warnings.append(f"project.waivers: {problem}")
        until = timestamps.parse_date(w["until"])
        if until and until < today:
            errors.append(f"project.waivers: the waiver of {rid!r} expired on {until}; meet the rule, or a person approves a new waiver")
        elif until and (until - today).days <= WAIVER_WARNING_DAYS:
            warnings.append(f"project.waivers: the waiver of {rid!r} expires on {until} (in {(until - today).days} days); plan the work or ask for a renewal")
    return errors, warnings


@functools.cache
def industry_standard_ids() -> frozenset[str]:
    """The ids of the industry standards in the registry (`schemas/industry-standards.json`), which a waiver may name beside a project rule's id."""
    return frozenset(resources.load_json("industry-standards.json"))


def delegation_warnings(delegation: dict, today: dt.date) -> list[str]:
    """What a delegation's owner should know before it surprises them, once each: a review date far ahead, and a merge delegated
    without `spec.approve`. `aidd validate`, `aidd doctor`, and `aidd init --delegate` all print these."""
    return [w for w in (delegation_review_warning(delegation, today), delegation_merge_warning(delegation)) if w]


def delegation_merge_warning(delegation: dict) -> str | None:
    """A warning when `decides` (less `reserved`) holds a merge action and not `spec.approve`: every merge of a change with a Spec
    then waits for the person, who delegated the merge. A change with no Spec on the minor route still merges."""
    decides = delegation.get("decides")
    covered = [a for a in decides if isinstance(a, str) and a not in (delegation.get("reserved") or [])] if isinstance(decides, list) else []
    merges = [a for a in DELEGATED_MERGES if a in covered]
    if not merges or "spec.approve" in covered:
        return None
    return (
        f"delegation.decides has {' and '.join(merges)} but not spec.approve, so a merge with a Spec waits for you "
        "(a minor change with none still merges). Add spec.approve to decides in a reviewed change, or merge those yourself"
    )


def delegation_review_warning(delegation: dict, today: dt.date) -> str | None:
    """A warning when the delegation's `review_due` is more than DELEGATION_REVIEW_HORIZON_DAYS ahead, else None. A date
    in the past is no warning here: the delegate check defers on it, and says so."""
    due = timestamps.parse_date(delegation.get("review_due"))
    if not due or (due - today).days <= DELEGATION_REVIEW_HORIZON_DAYS:
        return None
    return (
        f"delegation.review_due {due} is {(due - today).days} days away, past the {DELEGATION_REVIEW_HORIZON_DAYS} days after which a delegation "
        "is easy to forget. Set an earlier date, or keep it on purpose and review the delegation when your team changes"
    )


def support_period_findings(compliance: dict, today: dt.date) -> tuple[list[str], list[str]]:
    """(errors, warnings) for the `cra` target: it needs a declared support period, and a period whose last day has
    passed has ended the product's security updates."""
    if CRA_TARGET not in (compliance.get("targets") or []):
        return [], []
    period = compliance.get("support_period") or {}
    if not period.get("ends_on"):
        return [
            "project.compliance targets cra with no support_period. The CRA makes you declare how long the product gets security "
            'updates (Art. 13(8)), at least five years. Add support_period: {ends_on: "YYYY-MM-DD"} under project.compliance'
        ], []
    if str(period["ends_on"]) < today.isoformat():
        return [], [
            f"project.compliance.support_period ended on {period['ends_on']}, so the product gets no more security updates. A person sets a "
            "later end, or takes the product off the market"
        ]
    return [], []


def project_defaults(cfg: model.Config | None) -> dict[str, bool]:
    """Each product default, on unless `project.defaults.disabled` names it."""
    disabled = (cfg.get("project", "defaults", "disabled", default={}) if cfg else {}) or {}
    return {k: not disabled.get(k) for k in PROJECT_DEFAULTS}


def theme_hint(cfg: model.Config | None, design_specs: list[tuple[str, str]]) -> list[str]:
    """Hints for `aidd validate`, never a check that stops work: each design spec (path, text) whose Screen inventory table names no
    dark theme while `dark_mode` is on (a case-insensitive text match on the table's rows)."""
    if not project_defaults(cfg)["dark_mode"]:
        return []
    out = []
    for rel, text in design_specs:
        rows = [line for line in markdown_section(text, "Screen inventory").splitlines() if line.lstrip().startswith("|")]
        if not any(re.search(r"\bdark\b", line, re.I) for line in rows):
            out.append(
                f"the design spec {rel} has no dark column in its Screen inventory and `project.defaults` keeps dark_mode on. Add a "
                "Theme column, light and dark, for each screen. Or turn dark_mode off in `project.defaults.disabled`, with its reason (a text-match hint)"
            )
    return out


def hold_hint(text: str, data: dict, cfg: model.Config | None) -> str | None:
    """A hint for `aidd validate`, never a check that stops work: the `hold` technologies a Spec's Context or Design names (a
    case-insensitive match on the whole name) when the Spec links no ADR. None when there is nothing to say."""
    hold = (cfg.get("project", "stack", "hold", default=[]) if cfg else []) or []
    if not hold or any(isinstance(d, dict) and d.get("type") == "adr" for d in data.get("docs") or []):
        return None
    body = markdown_section(text, "Context") + "\n" + markdown_section(text, "Design")
    named = [h for h in hold if re.search(rf"(?<![\w.-]){re.escape(h)}(?![\w-])", body, re.I)]
    if not named:
        return None
    return (
        f"the Context or Design names {', '.join(named)}, on the `project.stack.hold` list, and the Spec links no ADR. Record a "
        "person's decision in one (`aidd new adr <topic> --spec <ID>`), or choose from adopt or trial (a text-match hint)"
    )


# ---- The cost of an infrastructure change ------------------------------------------------------------------------

_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
# The ISO 4217 codes (list one, published 2026-09-17), so a three-letter word before a number ("SLA 99.9") is no money.
_ISO_4217 = frozenset(
    """
    AED AFN ALL AMD AOA ARS AUD AWG AZN BAM BBD BDT BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD CAD CDF CHE CHF
    CHW CLF CLP CNY COP COU CRC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD
    HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD
    MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN
    PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD
    TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV WST XAD XAF XAG XAU XBA XBB XBC XBD XCD XCG XDR XOF XPD
    XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWG
    """.split()
)

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
# An amount with its currency, the symbol or ISO 4217 code before it or the code after it.
_CODE = "|".join(sorted(_ISO_4217))
_MONEY = re.compile(rf"(?<![\w.])(?:(?P<pre>[$€£]|(?:{_CODE}))\s?(?P<a1>{_NUMBER})|(?P<a2>{_NUMBER})\s?(?P<post>(?:{_CODE})|[€£$]))(?![\w])")
# A month right after the amount ("a month", "per month", "/month", "/mo", "monthly"), or "monthly" shortly before it.
_MONTH_AFTER = re.compile(r"^\s*(?:(?:a|per|each|every)\s+month\b|/\s*mo(?:nth)?\b|monthly\b)", re.I)
_MONTH_BEFORE = re.compile(r"\bmonthly\b[^\n|.]{0,40}$", re.I)


def monthly_estimates(text: str) -> list[tuple[float, str]]:
    """The monthly amounts `text` states, in order, as (amount, ISO 4217 code): "40 EUR a month", "$120/month", or
    "monthly cost: 75 EUR". A unit price ("0.002 USD per request") is not one."""
    out = []
    for m in _MONEY.finditer(text):
        after, before = text[m.end() : m.end() + 30], text[max(0, m.start() - 50) : m.start()]
        if not (_MONTH_AFTER.search(after) or _MONTH_BEFORE.search(before)):
            continue
        amount = float((m.group("a1") or m.group("a2")).replace(",", ""))
        cur = m.group("pre") or m.group("post")
        out.append((amount, _SYMBOLS.get(cur, cur)))
    return out


def cost_hint(data: dict, cfg: model.Config | None, tracked: list[str] | None = None) -> str | None:
    """A hint for `aidd validate`, never a check that stops work: a Spec that changes infrastructure code (its Task scopes hit the
    `infra` area's paths), or whose risk names `cost`, and that gives no `risk.cost_estimate`; or one whose monthly estimate,
    in the budget's currency, is above `project.budget.max_infra_per_month`. None when there is nothing to say. With
    `tracked` (the repository's files), a glob or a folder scope also hits through an IaC file it holds."""
    scopes = [s for task in data.get("tasks") or [] for s in task.get("scope") or [] if isinstance(s, str)]

    # What an infrastructure change looks like in a Task's scope: the paths of the `infra` risk area.
    iac_paths, iac_exclude = model.area_paths("infra"), model.area_exclude("infra")

    def iac(scope: str) -> bool:
        paths = (scope, globs.sample_path(scope))
        return any(globs.match_any(iac_paths, x) for x in paths) and not any(globs.match_any(iac_exclude, x) for x in paths)

    def held(scope: str) -> str | None:
        if not (globs.is_pattern(scope) or scope.endswith("/")):
            return None
        pattern = scope.removeprefix("./") + ("**" if scope.endswith("/") else "")
        return next((t for t in tracked or [] if globs.match_any([pattern], t) and iac(t)), None)

    hit = []
    for s in scopes:
        if iac(s):
            hit.append(s)
        elif f := held(s):
            hit.append(f"{s}, holding {f}")
    costly = "cost" in ((data.get("risk") or {}).get("dimensions") or []) and data.get("route") in model.SPEC_FIRST_ROUTES
    given = (data.get("risk") or {}).get("cost_estimate")
    monthly = given.get("monthly") if isinstance(given, dict) else None
    found = monthly_estimates(f"{monthly} a month") if isinstance(monthly, str) else []
    if monthly is not None and not found:
        return f'`risk.cost_estimate.monthly` is "{monthly}": give an amount and its currency, such as "40 EUR" or "$120"'
    if not found:
        if not hit and not costly:
            return None
        why = f"a Task scopes infrastructure code ({', '.join(hit)})" if hit else "its risk names cost"
        return (
            f"{why}, and the Spec gives no `risk.cost_estimate`. Give it at today's load and at 10x, with its source, such as "
            '`risk.cost_estimate: {monthly: "40 EUR", at_10x: "300 EUR", source: "infracost diff"}`, per aidd-packs:cloud-and-infrastructure'
        )
    budget = (cfg.get("project", "budget", default={}) if cfg else {}) or {}
    most, cur = budget.get("max_infra_per_month"), budget.get("currency")
    if most is None:
        return None
    same = next((e for e in found if e[1] == cur), None)
    if same is None:
        return f"the monthly cost estimate is in {found[0][1]}, and `project.budget` in {cur}: give it in {cur} too, so it is compared with the budget"
    if same[0] > most:
        return (
            f"the monthly cost estimate {fmt_number(same[0])} {cur} is above `project.budget.max_infra_per_month` {fmt_number(most)} {cur}. Change the "
            "placement or the sizing, or have a person raise the budget before Spec approval"
        )
    return None


# ---- What applies ------------------------------------------------------------------------------------------------


# ---- What applies ------------------------------------------------------------------------------------------------


def radar_line(stack: dict | None) -> str:
    """The stack radar in one line."""
    parts = [f"{ring} {', '.join(stack[ring])}" for ring in RINGS if stack and stack.get(ring)]
    return "Stack: " + ("; ".join(parts) if parts else "not set (`project.stack` in .aidd/config.yaml)")


def _waiver(rule_id: str, waivers: list[dict], today: dt.date) -> dict | None:
    """The waiver in force for a rule: the one lasting longest among those not yet expired."""
    live = [w for w in waivers if w["rule"] == rule_id and (d := timestamps.parse_date(w["until"])) and d >= today]
    w = max(live, key=lambda w: str(w["until"]), default=None)
    return {"until": str(w["until"]), "by": w["by"], "reason": w["reason"]} if w else None


def effective_project(cfg: model.Config | None, paths: list[str] | None = None, today: dt.date | None = None) -> dict | None:
    """The constraints for `paths` (None: the whole repository): the radar, the hosting, the budget, and the rules whose
    `when_changed` match one of them (a rule without `when_changed` always does), must first, each with the waiver in force.
    None when the config has no `project`."""
    p = cfg.get("project") if cfg else None
    stance = project_compliance(cfg)
    if not p and not stance["on"]:
        return None
    p = p or {}
    today = today or dt.date.today()

    def applies(rule: dict) -> bool:
        return not rule.get("when_changed") or paths is None or any(globs.match_any(rule["when_changed"], x) for x in paths)

    rules = sorted(
        (r for r in p.get("rules", []) if applies(r)), key=lambda r: LEVELS.index(r["requirement_level"]) if r["requirement_level"] in LEVELS else len(LEVELS)
    )
    out = {
        "radar": radar_line(p.get("stack")),
        "stack": {ring: list((p.get("stack") or {}).get(ring, [])) for ring in RINGS},
        "hosting": p.get("hosting"),
        "budget": dict(p["budget"]) if p.get("budget") else None,
        "rules": [
            {
                "id": r["id"],
                "requirement_level": r["requirement_level"],
                "statement": r["statement"],
                "why": r["why"],
                "when_changed": list(r.get("when_changed", [])),
                "enforced_by": list(r.get("enforced_by", [])),
                "source": r.get("source"),
                "owner": r["owner"],
                "review_due": r.get("review_due"),
                "waiver": _waiver(r["id"], p.get("waivers", []), today),
            }
            for r in rules
        ],
    }
    if stance["on"]:
        out["compliance"] = {"targets": stance["targets"], "pack": CONTROLS_PACK}
    return out


def compliance_line(compliance: dict) -> str:
    """The compliance stance in one line, for `aidd risk --paths`."""
    why = f"for {', '.join(compliance['targets'])}"
    return (
        f"Compliance: on, {why}. Load `{PACKS_PLUGIN}:{compliance['pack']}` for the control set and its evidence; a threat model and an "
        "authorization matrix are asked for on security and auth paths."
    )


# The longest a config value shows in the text of `aidd risk --paths`: the schema's longest rule text is 500 characters.
MAX_SHOWN = 500


def _shown(value: object) -> str:
    """A config value as a terminal line may show it: it is a committed file's text, so on one line, with no control or
    direction character, cut to MAX_SHOWN."""
    return one_line(value, MAX_SHOWN)


def project_markdown(settings: dict | None) -> list[str]:
    """The constraints as lines: the radar, the hosting and budget, then each rule with its why. Every value is a committed
    file's text, so each shows through `_shown`, on one line."""
    if not settings:
        return []
    lines = ["## Project constraints", "", _shown(settings["radar"]) + " (a hold needs an ADR and a person's decision)"]
    if settings.get("compliance"):
        lines += ["", compliance_line(settings["compliance"])]
    b = settings.get("budget") or {}
    money = f"infra at most {fmt_number(b['max_infra_per_month'])} {_shown(b['currency'])} a month" if "max_infra_per_month" in b else ""
    facts = [x for x in (f"Hosting: {_shown(settings['hosting'])}" if settings.get("hosting") else "", f"Budget: {money}" if money else "") if x]
    if facts:
        lines += ["", ". ".join(facts) + "."]
    lines.append("")
    if not settings["rules"]:
        return lines + ["No project rule applies to these paths."]
    for r in settings["rules"]:
        extra = [
            f"checked by {', '.join(f'`{_shown(n)}`' for n in r['enforced_by'])}" if r.get("enforced_by") else "",
            f"decided in {_shown(r['source'])}" if r.get("source") else "",
        ]
        w = r.get("waiver")
        if w:
            extra.append(f"waived until {_shown(w['until'])} by {_shown(w['by'])}: {_shown(w['reason'])}")
        tail = "; ".join(x for x in extra if x)
        lines.append(f"- {r['requirement_level'].upper()} {_shown(r['id'])}: {_shown(r['statement'])} Why: {_shown(r['why'])}" + (f" ({tail})" if tail else ""))
    return lines


# ---- aidd init ---------------------------------------------------------------------------------------------------

STACK_COMMENT = "# The technology radar `aidd init` detected: it binds nothing until a person uncomments and edits it.\n"


def _commented(lines: list[tuple[int, str, bool]]) -> list[str]:
    """(indent, text, active) lines as YAML text. An inactive line is commented out with its `#` where its topmost
    inactive ancestor starts, so removing `# ` from the lines a person wants (that ancestor included) gives valid YAML."""
    out: list[str] = []
    marks: list[tuple[int, int]] = []  # (indent of an open ancestor, where its comment mark sits, or -1 when active)
    for indent, text, active in lines:
        while marks and marks[-1][0] >= indent:
            marks.pop()
        mark = next((m for _, m in marks if m >= 0), -1)
        if mark < 0 and not active:
            mark = indent
        out.append(" " * indent + text if mark < 0 else " " * mark + "# " + " " * (indent - mark) + text)
        marks.append((indent, mark))
    return out


def project_block(
    *,
    stack: list[str] | None = None,
    ui: bool = True,
    existing_code: bool = False,
    compliance: list[str] | None = None,
) -> str:
    """The starting config's `project` mapping, holding only what `aidd init` knows, or "" when it knows nothing:

    - `stack`: the technology radar it detected, always commented, for a person to edit.
    - `defaults.disabled`: every product default is on; with `ui` False (a command-line tool or a library), the interface
      defaults written disabled with the reason; with `existing_code` (a repository that already has a structure),
      `modular_monolith` written disabled with the reason, so the structure stays as it is.
    - `compliance.targets`: written when init was given targets; with `cra`, a commented `support_period` for a person
      to declare."""
    disabled = {k: PROJECT_NO_UI for k in ([] if ui else UI_DEFAULTS)} | ({"modular_monolith": EXISTING_STRUCTURE} if existing_code else {})
    if not (stack or disabled or compliance):
        return ""
    active = bool(disabled or compliance)
    lines: list[tuple[int, str, bool]] = [(0, "project:", active)]
    if stack:
        # The radar's note sits by its own lines; with no active `project` it sits above the commented block.
        lines += [(2, STACK_COMMENT.rstrip("\n"), True)] if active else []
        lines += [(2, "stack:", False), (4, f"adopt: {strict_yaml.flow(stack)}", False), (4, "trial: []", False), (4, "hold: []", False)]
    if disabled:
        lines += [(2, "defaults:", True), (4, "disabled:", True)]
        lines += [(6, f"{strict_yaml.key(k)}: {strict_yaml.scalar(disabled[k])}", True) for k in PROJECT_DEFAULTS if k in disabled]
    if compliance:
        lines += [(2, "compliance:", True), (4, f"targets: {strict_yaml.flow(compliance)}", True)]
        if CRA_TARGET in compliance:
            lines += [(4, "support_period:", False), (6, 'ends_on: "YYYY-MM-DD"  # the last day of security updates, at least five years out', False)]
    return (STACK_COMMENT if stack and not active else "") + "\n".join(_commented(lines)) + "\n"
