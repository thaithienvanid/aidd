"""`aidd init` holds the repository's deploy and infrastructure commands for a person.

Agents never ship. So `aidd init` writes a `guard.held_commands` entry for each deploy command it can see: a deploy,
rollout, or provision script, a Makefile target named so, and the destructive or production-changing commands of each infrastructure tool the
repository uses. The entries are active, each under a comment that a person may delete it. Re-running init and
`aidd upgrade` never touch them, so an entry a person deleted stays deleted.
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd import __version__
from aidd.guard import pre_tool
from aidd.guard import denial_log
from aidd.guard import command_check
from aidd.guard import held_commands
from aidd.guard import edit_check
from aidd.guard import path_location
from aidd.guard import shell_parser
from aidd.setup import detection
from aidd.setup import doctor_checks
from aidd.setup import upgrading
from aidd.setup import adoption
from aidd import config


def tree(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return root


def held(files: dict[str, str]) -> list[dict]:
    with tempfile.TemporaryDirectory() as d:
        return detection.detect(tree(Path(d), files))["held_commands"]


MAKEFILE = (
    ".PHONY: build deploy release\n"
    "DEPLOY_DIR := /srv/app\n"
    "build:\n\tgo build ./...\n"
    "deploy: build\n\t./scripts/push.sh $(DEPLOY_DIR)\n"
    "notes release:\n\techo release\n"
    "rollout-canary:\n\techo canary\n"
    "provision:\n\techo db\n"
    "\tdeploy-in-recipe: not a target\n"
)

# Each tool `aidd init` knows, the file that shows the repository uses it, and the commands it holds.
TOOLS = (
    ("terraform", {"infra/main.tf": 'resource "null_resource" "x" {}\n'}, ["terraform apply", "terraform destroy"]),
    ("opentofu", {"infra/main.tofu": ""}, ["tofu apply", "tofu destroy"]),
    (
        "opentofu lock",
        {"main.tf": "", ".terraform.lock.hcl": 'provider "registry.opentofu.org/hashicorp/aws" {}\n'},
        ["terraform apply", "terraform destroy", "tofu apply", "tofu destroy"],
    ),
    ("pulumi", {"Pulumi.yaml": "name: app\nruntime: nodejs\n"}, ["pulumi up", "pulumi destroy"]),
    ("cdk", {"cdk.json": '{"app": "npx ts-node bin/app.ts"}\n'}, ["cdk deploy", "cdk destroy"]),
    ("wrangler toml", {"wrangler.toml": 'name = "worker"\n'}, ["wrangler deploy"]),
    ("wrangler jsonc", {"worker/wrangler.jsonc": "{}\n"}, ["wrangler deploy"]),
    ("serverless", {"serverless.yml": "service: app\n"}, ["serverless deploy", "serverless remove", "sls deploy", "sls remove"]),
    ("fly", {"fly.toml": 'app = "x"\n'}, ["fly deploy"]),
    ("firebase", {"firebase.json": "{}\n"}, ["firebase deploy"]),
    ("vercel", {"vercel.json": "{}\n"}, ["vercel --prod", "vercel --target production", "vercel promote", "vercel rollback"]),
    ("netlify", {"netlify.toml": "[build]\n"}, ["netlify deploy --prod", "netlify deploy -p"]),
)
EVERY_TOOL = {rel: text for _, files, _ in TOOLS for rel, text in files.items() if rel != ".terraform.lock.hcl"}


def names(entries: list[dict]) -> list[str]:
    return [g["name"] for g in entries]


# Held and allowed with the entries for every tool (HeldPatternTests); tests/test_guard_oracle.py runs them all.
TOOL_HELD = (
    "make deploy",
    "make deploy build",
    "make deploy -j4",
    "make deploy -- x",
    "make -C . rollout-canary",
    "make provision",
    "terraform apply",
    "terraform apply -auto-approve",
    "terraform -chdir=x apply",
    "tofu destroy",
    "pulumi up",
    "pulumi up --yes",
    "pulumi destroy",
    "npx cdk deploy",
    "cdk destroy --all",
    "wrangler deploy",
    "wrangler versions deploy",
    "serverless deploy",
    "sls remove",
    "fly deploy",
    "flyctl deploy --remote-only",
    "firebase deploy --only hosting",
    "vercel --prod",
    "vercel deploy --prod",
    "vercel --yes --prod",
    "netlify deploy --prod",
    "source scripts/deploy.sh",
    ". ./scripts/deploy.sh",
    "bash -lc 'make deploy'",
    'sh -ec "terraform apply"',
    "bash -euxc 'pulumi up'",
)
TOOL_ALLOWED = (
    "terraform plan",
    "terraform plan -out apply.tfplan",
    "terraform plan -var-file apply.tfvars",
    "terraform show apply.tfplan",
    "pulumi config set upstreamUrl x",
    "pulumi stack select uptime",
    "pulumi preview",
    "cdk synth DeploymentStack",
    "cdk diff",
    "wrangler dev",
    "vercel build --prod",
    "vercel deploy",
    "netlify deploy",
    "make release",
    "make build",
    "helm upgrade --install app charts/app",
    "source .venv/bin/activate",
    "bash -lc 'make build'",
)
# Vercel and Netlify production flags and shell option forms (ShellAndProductionFlagTests).
FLAG_HELD = (
    "vercel --prod",
    "vercel ./site --prod",
    "vercel site --prod",
    "vercel public --prod",
    "vercel deploy --prod",
    "vercel --target=production",
    "vercel --target production",
    "vercel deploy --target=production",
    "vercel deploy --prebuilt --prod --skip-domain",
    "vercel promote https://app-abc.vercel.app",
    "vercel rollback",
    "netlify deploy --prod",
    "netlify deploy -p",
    "netlify deploy --dir dist -p",
    "netlify deploy --prod-if-unlocked",
)
FLAG_ALLOWED = (
    "bash -c 'make build'",
    "bash -cx 'echo hi'",
    "bash -o pipefail -c 'terraform plan'",
    "vercel build --prod",
    "vercel build --target=production",
    "vercel pull --prod",
    "vercel pull --environment=production",
    "vercel dev",
    "vercel deploy",
    "vercel deploy --target=staging",
    "netlify deploy",
    "netlify build",
)
# Held and allowed in the repository InitHoldsCommandsTests sets up with `aidd init`.
INIT_HELD = (
    "terraform apply",
    "terraform -chdir=infra apply -auto-approve",
    "AWS_PROFILE=prod terraform apply",
    "sudo terraform destroy",
    "./scripts/deploy.sh",
    "sh scripts/deploy.sh --env production",
    "bash -x scripts/deploy.sh",
    "cd scripts && ./deploy.sh",
    "make deploy",
    "make deploy ENV=production",
    "make -C . rollout-canary",
    "make provision",
    "npx wrangler deploy",
    "npx --yes wrangler@3 deploy --env production",
)
INIT_ALLOWED = (
    "terraform plan",
    "terraform plan -out=apply.tfplan",
    "terraform init",
    "cat scripts/deploy.sh",
    "git add scripts/deploy.sh",
    "shellcheck scripts/deploy.sh",
    "make build",
    "make test DEPLOY=1",
    "npx wrangler dev",
    "echo terraform apply",
)


# Wrappers before the program: the guard finds the held program after any wrapper and its options (WrapperTests).
WRAPPER_HELD = (
    "timeout -k 5 10 terraform apply",
    "timeout --foreground 5 terraform apply",
    "timeout -s KILL 5 terraform apply",
    "timeout -v 5 terraform apply",
    "timeout --kill-after=5 10 terraform apply",
    "timeout -k 5 10 bash -c 'terraform apply'",
    "stdbuf -o0 terraform apply",
    "stdbuf -o L make deploy",
    "ionice -c2 make deploy",
    "ionice -c 2 -n 7 terraform apply",
    "setsid terraform apply",
    "chrt -f 10 terraform apply",
    "taskset -c 0-3 terraform apply",
    "taskset 0x3 terraform apply",
    "caffeinate -i terraform apply",
    "nice -n 5 timeout 30 ./scripts/deploy.sh",
)
WRAPPER_ALLOWED = (
    "timeout 5 terraform plan",
    "nice make test",
    "timeout -k 5 10 terraform plan",
    "setsid make build",
)
# Accepted over-holds, the safe direction: after a wrapper, the first word that names a held program counts.
OVER_HOLD = ("timeout 5 echo terraform apply",)


class DetectHeldCommandsTests(unittest.TestCase):
    def test_each_tool_is_held_only_where_the_repository_uses_it(self):
        for label, files, expected in TOOLS:
            with self.subTest(label):
                found = held({"app.py": "x: 1\n", **files})
                self.assertEqual(names(found), [f"init: {n}" for n in expected])
                for g in found:
                    self.assertTrue(g["match"], g)
                    self.assertIn("`aidd init` held it", g["message"])
                    self.assertIn(next(iter(files)) if label != "opentofu lock" else "main.tf", " ".join(x["message"] for x in found))

    def test_a_repository_without_them_holds_nothing(self):
        self.assertEqual(held({"app.py": "x = 1\n", "README.md": "# app\n", "Makefile": "build:\n\tgo build\n"}), [])
        # A Pulumi project holds no wrangler, and a wrangler project no Terraform.
        self.assertNotIn("init: wrangler deploy", names(held({"Pulumi.yaml": "name: x\n"})))
        self.assertFalse([n for n in names(held({"wrangler.toml": ""})) if "terraform" in n])
        # A Terraform lock file from the Terraform registry is no sign of OpenTofu.
        tf = held({"main.tf": "", ".terraform.lock.hcl": 'provider "registry.terraform.io/hashicorp/aws" {}\n'})
        self.assertEqual(names(tf), ["init: terraform apply", "init: terraform destroy"])
        # Helm's install and upgrade are the local loop against kind or minikube, so a chart holds nothing.
        self.assertEqual(held({"charts/app/Chart.yaml": "name: app\n"}), [])

    def test_a_deploy_script_is_held_by_its_name(self):
        found = held(
            {
                "scripts/deploy.sh": "echo deploy\n",
                "ops/release.py": "",
                "scripts/provision-local-db.sh": "",
                "tools/rollout.ts": "",
                "src/deployment.md": "",
            }
        )
        # Provisioning buys paid infrastructure, so a person holds it too (owner, 2026-10-09); a release script often
        # only builds, so it stays allowed.
        self.assertEqual(
            [(g["name"], g["match"]) for g in found],
            [
                ("init: scripts/deploy.sh", ["deploy.sh *"]),
                ("init: scripts/provision-local-db.sh", ["provision-local-db.sh *"]),
                ("init: tools/rollout.ts", ["rollout.ts *"]),
            ],
        )
        self.assertIn("its name says it deploys", found[0]["message"])
        self.assertIn("its name says it provisions infrastructure", found[1]["message"])

    def test_scripts_merge_by_name_before_the_cap(self):
        files = {f"services/s{n:02}/deploy.sh": "" for n in range(12)} | {"tools/rollout.sh": ""}
        found = held(files)
        self.assertEqual([(g["name"], g["match"]) for g in found], [("init: deploy.sh", ["deploy.sh *"]), ("init: tools/rollout.sh", ["rollout.sh *"])])
        self.assertIn("12 files named deploy.sh, such as services/s00/deploy.sh", found[0]["message"])

    def test_a_makefile_deploy_target_is_held(self):
        found = held({"Makefile": MAKEFILE})
        self.assertEqual(
            [(g["name"], g["match"]) for g in found],
            [
                ("init: make deploy", ["make* deploy *"]),
                ("init: make rollout-canary", ["make* rollout-canary *"]),
                ("init: make provision", ["make* provision *"]),
            ],
        )
        self.assertIn("Makefile has a `deploy` target", found[0]["message"])
        self.assertEqual(held({"Makefile": "release:\n\tcargo build --release\n"}), [])
        self.assertEqual(names(held({"Makefile": "provision-db:\n\tterraform apply\n"})), ["init: make provision-db"])

    def test_the_dry_run_proposes_them(self):
        with tempfile.TemporaryDirectory() as d:
            found = detection.detect(tree(Path(d), {"main.tf": ""}))
        snippet = detection.config_snippet(found)
        cfg = config.load_text(f'aidd_version: "{__version__}"\nprofile: solo\nowners:\n  approvers: ["@x"]\n' + snippet)
        self.assertEqual(names(cfg.get("guard", "held_commands")), ["init: terraform apply", "init: terraform destroy"])
        self.assertIn("`init: terraform apply`", detection.detection_markdown(found))

    def test_an_org_entry_of_the_same_command_and_inits_entry_both_stay(self):
        head = f'aidd_version: "{__version__}"\nprofile: team\nowners:\n  approvers: ["@x"]\n'
        parent = head + 'guard:\n  held_commands:\n    - name: terraform apply\n      match: ["terraform apply*"]\n      requires: RELEASE_APPROVAL\n'
        child = head.replace("\nowners:", "\nextends: [{path: org.yaml}]\nowners:") + detection.held_yaml(held({"main.tf": ""}))
        cfg = config.load_text(child, prefetched={"org.yaml": parent})
        self.assertEqual(names(cfg.get("guard", "held_commands")), ["terraform apply", "init: terraform apply", "init: terraform destroy"])
        self.assertFalse([w for w in cfg.warnings if "cannot be replaced" in w], cfg.warnings)

    def test_the_comment_says_how_a_person_approves_one(self):
        text = detection.held_yaml(held({"main.tf": ""}))
        self.assertIn("references/config.md", text)
        self.assertNotIn("docs/CONFIG.md", text)
        self.assertIn("requires: VAR", text)
        self.assertIn("starts the agent with VAR set", text)


class HeldPatternTests(unittest.TestCase):
    """The entries for every tool at once: each one holds the command and lets its neighbours run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = tree(Path(self.tmp.name).resolve(), {**EVERY_TOOL, "Makefile": MAKEFILE, "scripts/deploy.sh": ""})
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        entries = detection.detect(self.root)["held_commands"]
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[], held_commands=entries))

    def decide(self, command):
        return command_check.check_command(str(self.root), str(self.root), command, {})[0]

    def test_held(self):
        for cmd in TOOL_HELD:
            self.assertEqual(self.decide(cmd), "deny", cmd)

    def test_allowed(self):
        for cmd in TOOL_ALLOWED:
            self.assertEqual(self.decide(cmd), "allow", cmd)


# Shell lines whose inline script the splitter and `_as_run` must read alike: (command, the program that runs).
SHELL_LINES = (
    ("bash -c 'terraform apply'", "terraform"),
    ("bash -c -l 'terraform apply'", "terraform"),
    ("bash -c -x 'terraform apply'", "terraform"),
    ("bash -cl 'terraform apply'", "terraform"),
    ("bash -cx 'terraform apply'", "terraform"),
    ("bash -lc 'terraform apply'", "terraform"),
    ("sh -ce 'terraform apply' deploy.sh", "terraform"),
    ("sh -c -- 'terraform apply'", "terraform"),
    ("bash -o pipefail -c 'terraform apply'", "terraform"),
    ("bash -c -o pipefail 'terraform apply'", "terraform"),
    ("bash -euo pipefail -c 'terraform apply'", "terraform"),
    ("bash +x -c 'terraform apply'", "terraform"),
    ("bash --norc -c 'terraform apply'", "terraform"),
    ("bash --rcfile x.rc -c 'terraform apply'", "terraform"),
    ("busybox sh -c 'terraform apply'", "terraform"),
    ("bash -x scripts/deploy.sh", "deploy.sh"),
    ("bash -o pipefail scripts/deploy.sh -c x", "deploy.sh"),
    ("sh -- scripts/deploy.sh", "deploy.sh"),
)


class ShellLineTests(unittest.TestCase):
    """The splitter and `_as_run` share one reading of a shell's options, so they always agree on what runs."""

    def program(self, command):
        outer, *inner = shell_parser.simple_commands(command)
        as_run = held_commands._as_run(outer.argv)
        shell = shell_parser.program_name(shell_parser.program_argv(outer.argv)[0])
        if inner:
            self.assertEqual(as_run.split()[0], shell, command)  # an inline script: `_as_run` keeps the shell
            return shell_parser.program_name(inner[0].argv[0])
        return as_run.split()[0]

    def test_both_see_the_same_program(self):
        for command, program in SHELL_LINES:
            self.assertEqual(self.program(command), program, command)

    def test_the_shared_reading(self):
        self.assertEqual(shell_parser.shell_operand("bash", ["-c", "-o", "pipefail", "x"]), (True, 3))
        self.assertEqual(shell_parser.shell_operand("bash", ["-euo", "pipefail", "-c", "x"]), (True, 3))
        self.assertEqual(shell_parser.shell_operand("sh", ["-x", "deploy.sh", "-c"]), (False, 1))
        self.assertEqual(shell_parser.shell_operand("bash", ["--long-c"]), (False, None))


class UnlessTests(unittest.TestCase):
    """`unless` names the commands an entry does not hold, matched like `match`."""

    def cfg(self, entry: str):
        head = f'aidd_version: "{__version__}"\nprofile: solo\nowners:\n  approvers: ["@x"]\n'
        item = "    - " + entry.rstrip("\n").replace("\n", "\n      ") + "\n"
        return config.load_text(head + "guard:\n  held_commands:\n" + item)

    def test_an_unless_pattern_keeps_the_entry_from_holding_a_command(self):
        cfg = self.cfg('name: vercel --prod\nmatch: ["vercel*", --prod]\nunless: ["vercel build *", "vercel pull *"]\n')
        self.assertIsNotNone(held_commands.held_command(cfg, "vercel --prod", environ={}))
        self.assertIsNotNone(held_commands.held_command(cfg, "npx vercel deploy --prod", environ={}))
        for cmd in ("vercel build --prod", "vercel build", "npx vercel pull --prod", "FOO=1 vercel build --prod"):
            self.assertIsNone(held_commands.held_command(cfg, cmd, environ={}), cmd)

    def test_unless_is_validated(self):
        with self.assertRaises(config.ConfigError):
            self.cfg("name: x\nmatch: [x]\nunless: []\n")
        with self.assertRaises(config.ConfigError):
            self.cfg('name: x\nmatch: [x]\nunless: [""]\n')

    def test_an_exclamation_mark_in_match_is_a_literal(self):
        self.assertTrue(held_commands._gate_matches(["!vercel build *"], "!vercel build x"))
        self.assertFalse(held_commands._gate_matches(["!vercel build *"], "terraform apply"))
        self.assertFalse(held_commands._gate_matches(["vercel*", "!vercel build *"], "vercel --prod"))

    def test_init_writes_unless_for_vercel(self):
        text = detection.held_yaml(held({"vercel.json": "{}\n"}))
        self.assertIn("unless: [vercel build *, vercel pull *]", text)
        self.assertNotIn('"!', text)


class WrapperTests(HeldPatternTests):
    """No registry of wrapper options is ever complete, so the guard scans past a wrapper for a held program."""

    def test_held(self):
        for cmd in (*WRAPPER_HELD, *OVER_HOLD):
            self.assertEqual(self.decide(cmd), "deny", cmd)

    def test_allowed(self):
        for cmd in WRAPPER_ALLOWED:
            self.assertEqual(self.decide(cmd), "allow", cmd)

    def test_an_option_value_named_like_a_held_program_does_not_hide_the_real_one(self):
        # The scan alone would take the value `terraform` as the program; the guard also keeps the plain reading.
        for cmd in ("env -C terraform make deploy", "env -C infra/terraform make deploy", "sudo -D /srv/terraform make deploy"):
            self.assertEqual(self.decide(cmd), "deny", cmd)


class ShellAndProductionFlagTests(HeldPatternTests):
    """The reviewed parser differential and the production flags of Vercel (vercel.com/docs/cli/deploy) and Netlify."""

    def test_held(self):
        for command, program in SHELL_LINES:
            if program == "terraform":
                self.assertEqual(self.decide(command), "deny", command)
        for cmd in FLAG_HELD:
            self.assertEqual(self.decide(cmd), "deny", cmd)

    def test_allowed(self):
        for cmd in FLAG_ALLOWED:
            self.assertEqual(self.decide(cmd), "allow", cmd)


class ScriptCapNoticeTests(unittest.TestCase):
    def test_init_says_how_many_script_names_it_did_not_hold(self):
        with tempfile.TemporaryDirectory() as d:
            tree(Path(d), {f"scripts/deploy-{c}.sh": "" for c in "abcdefghijkl"})
            subprocess.run(["git", "init", "-q", d], check=True)
            found = detection.detect(Path(d))
            self.assertEqual((len(found["held_commands"]), found["not_held"]), (10, 2))
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            done = subprocess.run(
                [sys.executable, "-m", "aidd", "init", "--approvers", "@lead", "--ci", "none", "--harness", "none"],
                cwd=d,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("2 more deploy script names are not held", done.stdout)
            self.assertIn("a person can add them to `guard.held_commands`", done.stdout)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(detection.detect(tree(Path(d), {"deploy.sh": ""}))["not_held"], 0)


class GuardRobustnessTests(unittest.TestCase):
    """The held-command check fails closed, and a huge command costs little."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = tree(Path(self.tmp.name).resolve(), {"main.tf": "", "scripts/deploy.sh": ""})
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        entries = detection.detect(self.root)["held_commands"]
        adoption.init(self.root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[], held_commands=entries))
        self.cfg = config.load_file(config.CONFIG_PATH, str(self.root))

    def test_an_error_in_the_check_denies(self):
        def broken(*args, **kwargs):
            raise ValueError("boom")

        with mock.patch.object(held_commands, "_as_run", broken):
            decision, reason = command_check.check_command(str(self.root), str(self.root), "ls", {})
        self.assertEqual(decision, "deny")
        self.assertIn("aidd could not check this command against the held commands: ValueError", reason)
        self.assertIn("ask a person to run it, or fix the config", reason)
        self.assertNotEqual(denial_log.reason_code(reason), "other")

    def test_a_huge_command_is_quick(self):
        padded = "bash " + "-x " * 400_000 + "scripts/deploy.sh"
        started = time.monotonic()
        with self.assertRaises(held_commands.CommandTooLong):
            held_commands.held_command(self.cfg, padded)
        long_message = "git commit -m " + "word " * 400_000
        self.assertIsNone(held_commands.held_command(self.cfg, long_message))
        # Two commands of 400,000 words each. A wall-clock cap, not behavior: 2 s was flaky on a loaded machine.
        self.assertLess(time.monotonic() - started, 10.0)
        started = time.monotonic()
        with self.assertRaises(held_commands.CommandTooLong):
            held_commands._as_run(["bash", *["-x"] * 400_000, "deploy.sh"])
        self.assertEqual(held_commands._as_run(["git", "commit", "-m", *["word"] * 400_000])[:15], "git commit -m w")
        self.assertLess(time.monotonic() - started, 0.2)
        # Padding cannot hide a held script: the check that cannot reach it denies.
        decision, reason = command_check.check_command(str(self.root), str(self.root), padded, {})
        self.assertEqual(decision, "deny")
        self.assertIn("could not check this command against the held commands", reason)


class InitHoldsCommandsTests(unittest.TestCase):
    """Through the command line, as a person runs it."""

    FILES = {
        "app.py": "x = 1\n",
        "infra/main.tf": 'resource "null_resource" "x" {}\n',
        "scripts/deploy.sh": "#!/bin/sh\necho deploy\n",
        "Makefile": MAKEFILE,
        "wrangler.toml": 'name = "worker"\n',
    }
    NAMES = [
        f"init: {n}"
        for n in ("scripts/deploy.sh", "make deploy", "make rollout-canary", "make provision", "terraform apply", "terraform destroy", "wrangler deploy")
    ]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = tree(Path(self.tmp.name).resolve(), self.FILES)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.out = self.init()
        self.config = self.root / config.CONFIG_PATH

    def aidd(self, *args):
        env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
        done = subprocess.run([sys.executable, "-m", "aidd", *args], cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def init(self):
        return self.aidd("init", "--approvers", "@lead", "--ci", "none", "--harness", "none")

    def names(self):
        return [g["name"] for g in config.load_file(config.CONFIG_PATH, str(self.root)).get("guard", "held_commands", default=[])]

    def decide(self, command):
        return command_check.check_command(str(self.root), str(self.root), command, {})

    def test_init_writes_active_entries_each_with_the_comment(self):
        self.assertEqual(self.names(), self.NAMES)
        text = self.config.read_text(encoding="utf-8")
        self.assertIn("\nguard:\n  held_commands:\n", text)
        headers = [ln for ln in text.splitlines() if "a person may delete this entry" in ln]
        self.assertEqual(len(headers), len(self.NAMES))
        for line in headers:
            self.assertTrue(line.startswith("    - name: "), line)  # active, not commented out
        self.assertIn("held     deploy and infrastructure commands for a person", self.out)
        self.assertIn("terraform apply", self.out.split("held     ", 1)[1].split("\n", 1)[0])

    def test_re_running_init_keeps_the_config_as_it_is(self):
        before = self.config.read_text(encoding="utf-8")
        again = self.init()
        self.assertEqual(self.config.read_text(encoding="utf-8"), before)
        self.assertEqual(self.names(), self.NAMES)
        self.assertNotIn("held     ", again)  # it wrote no config, so it holds nothing new

    def test_upgrade_never_brings_back_an_entry_a_person_deleted(self):
        text = self.config.read_text(encoding="utf-8")
        start = text.index('    - name: "init: terraform destroy"')
        end = text.index("\n    - ", start) + 1
        self.config.write_text(text[:start] + text[end:], encoding="utf-8")
        self.assertNotIn("init: terraform destroy", self.names())
        upgrading.upgrade(self.root, ref="a" * 40, yes=True)
        self.assertEqual(self.names(), [n for n in self.NAMES if n != "init: terraform destroy"])
        self.assertEqual(self.decide("terraform destroy")[0], "allow")

    def test_a_held_command_is_denied_and_its_neighbours_run(self):
        for cmd in INIT_HELD:
            decision, reason = self.decide(cmd)
            self.assertEqual(decision, "deny", cmd)
            self.assertIn("is a held command: agents never run it.", reason, cmd)
            self.assertIn("`aidd init` held it", reason, cmd)
        decision, reason = self.decide("terraform apply")
        self.assertIn("`init: terraform apply` is a held command", reason)
        for cmd in INIT_ALLOWED:
            self.assertEqual(self.decide(cmd)[0], "allow", cmd)

    def test_doctor_lists_each_held_command(self):
        lines = [m for level, m in doctor_checks.doctor(self.root) if m.startswith("held for a person:")]
        self.assertEqual(len(lines), len(self.NAMES), lines)
        self.assertIn("held for a person: `init: terraform apply` (terraform* apply *)", lines)

    def test_a_repository_without_deploy_commands_gets_no_guard_section(self):
        with tempfile.TemporaryDirectory() as d:
            root = tree(Path(d), {"app.py": "x: 1\n"})
            subprocess.run(["git", "init", "-q", d], check=True)
            env = os.environ | {"PYTHONPATH": str(ROOT / "src")}
            done = subprocess.run(
                [sys.executable, "-m", "aidd", "init", "--approvers", "@lead", "--ci", "none", "--harness", "none"],
                cwd=d,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("guard", (root / config.CONFIG_PATH).read_text(encoding="utf-8"))
            self.assertNotIn("held     ", done.stdout)
            self.assertFalse([m for _, m in doctor_checks.doctor(root) if m.startswith("held for a person")])


class InvalidConfigFailsClosedTests(unittest.TestCase):
    """An invalid or unreadable config never disables the guard: every session still meets the commands `aidd init`
    could detect, a role or a helper writes nothing, the person's own session may edit (to fix the config), and
    session-start says what is wrong. An old `guard.gated_commands` list is named with its new name."""

    OLD = '\nguard:\n  gated_commands:\n    - name: production deploy\n      match: ["make* deploy *"]\n'

    def setUp(self):
        import shutil

        from helpers import make_repo

        if not shutil.which("git"):
            self.skipTest("git is required")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", branch=None)
        self.cfg = self.root / ".aidd" / "config.yaml"
        self.good = self.cfg.read_text(encoding="utf-8")

    def event(self, agent: str | None = None, **kw) -> dict:
        return {"cwd": str(self.root), "session_id": "s1", "hook_event_name": "PreToolUse"} | ({"agent_type": agent} if agent else {}) | kw

    def command(self, line: str, agent: str | None = None):
        return command_check.check_command(str(self.root), str(self.root), line, self.event(agent, tool_name="Bash", tool_input={"command": line}))

    def test_an_old_gated_commands_table_still_holds_the_detected_commands(self):
        self.cfg.write_text(self.good + self.OLD, encoding="utf-8")
        for line in ("make deploy", "terraform apply", "tofu -chdir=infra destroy", "./scripts/deploy.sh prod", "bash rollout.sh", "wrangler deploy"):
            for agent in (None, "aidd-team:developer"):
                decision, reason = self.command(line, agent)
                self.assertEqual(decision, "deny", (line, agent))
                self.assertIn("the aidd config is invalid", reason, line)
                self.assertIn("`guard.held_commands`", reason, line)
                self.assertIn("run `aidd validate`", reason, line)
        self.assertEqual(self.command("ls -la")[0], "allow")
        self.assertEqual(self.command("make test")[0], "allow")

    def test_any_invalid_config_fails_closed_for_roles_and_helpers(self):
        self.cfg.write_text(self.good.replace("\nprofile: ", "\nprofile: 7\nx_profile: ", 1), encoding="utf-8")
        (self.root / "src").mkdir(exist_ok=True)
        target = self.root / "src" / "app.py"
        for agent in ("aidd-team:developer", "aidd-team:tech-writer"):
            ev = self.event(agent, tool_name="Write", tool_input={"file_path": str(target), "content": "x\n"})
            decision, reason = edit_check.check_agent_edit(str(self.root), "src/app.py", ev)
            self.assertEqual(decision, "deny", agent)
            self.assertIn("the aidd config is invalid", reason, agent)
        # A shell write by a role is denied too, and a held command for the person's own session.
        self.assertEqual(self.command("echo x > src/app.py", "aidd-team:developer")[0], "deny")
        self.assertEqual(self.command("make deploy")[0], "deny")
        # The person's own session may still edit, so they can fix the config.
        person = self.event(tool_name="Write", tool_input={"file_path": str(self.cfg), "content": self.good})
        self.assertEqual(edit_check.check_agent_edit(str(self.root), ".aidd/config.yaml", person)[0], "allow")
        self.assertEqual(self.command("echo x > src/app.py")[0], "allow")

    def test_the_hook_and_session_start_say_so(self):
        import io
        import json

        from aidd.guard import session_hooks

        self.cfg.write_text(self.good + self.OLD, encoding="utf-8")
        out = io.StringIO()
        pre_tool.pre_tool_hook(io.StringIO(json.dumps(self.event(tool_name="Bash", tool_input={"command": "make deploy"}))), out)
        answer = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(answer["permissionDecision"], "deny")
        self.assertIn("the aidd config is invalid", answer["permissionDecisionReason"])
        out = io.StringIO()
        session_hooks.session_start({"cwd": str(self.root), "session_id": "s1", "hook_event_name": "SessionStart", "source": "startup"}, out)
        context = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
        self.assertIn("the aidd config is invalid", context)
        self.assertIn("`guard.held_commands`", context)

    def test_an_unfetched_url_parent_is_expected_and_never_fails_closed(self):
        """The guard runs offline by design, so a URL parent it cannot fetch is skipped with a warning: the local config
        still applies, its held commands are held, and a role's edit is judged as before."""
        import io
        import json

        from aidd.guard import session_hooks

        parent = 'extends: [{ url: "https://example.invalid/aidd-org-preset.yaml", sha256: "' + "a" * 64 + '" }]\n'
        held_entry = '\nguard:\n  held_commands:\n    - name: ship it\n      match: ["shipit *"]\n'
        self.cfg.write_text(parent + self.good + held_entry, encoding="utf-8")
        with mock.patch("aidd.kernel.egress.fetch_text", side_effect=AssertionError("the guard reached the network")):
            self.assertIsNone(path_location.config_problem(str(self.root)))
            decision, reason = self.command("shipit now", "aidd-team:developer")
            self.assertEqual(decision, "deny")
            self.assertIn("`ship it` is a held command", reason)
            self.assertEqual(self.command("make deploy")[0], "allow")  # only the local config's entries, no fallback
            (self.root / "src").mkdir(exist_ok=True)
            ev = self.event("aidd-team:developer", tool_name="Write", tool_input={"file_path": str(self.root / "src" / "app.py"), "content": "x\n"})
            self.assertEqual(edit_check.check_agent_edit(str(self.root), "src/app.py", ev)[0], "allow")
            out = io.StringIO()
            session_hooks.session_start({"cwd": str(self.root), "session_id": "s1", "hook_event_name": "SessionStart", "source": "startup"}, out)
            context = json.loads(out.getvalue())["hookSpecificOutput"]["additionalContext"]
            self.assertIn("https://example.invalid/aidd-org-preset.yaml was not read", context)
            doctor = [m for level, m in doctor_checks.doctor(self.root) if level == "warn"]
            self.assertTrue(any("was not read" in m for m in doctor), doctor)

    def test_the_fallback_reuses_the_detection_data(self):
        names = {e["name"] for e in detection.default_held()}
        for _, _, commands in detection.IAC_TOOLS:
            for name, _ in commands:
                self.assertIn(detection.HELD_PREFIX + name, names)
        for word in detection.HELD_WORDS:
            self.assertTrue(any(word in n for n in names), word)


if __name__ == "__main__":
    unittest.main()
