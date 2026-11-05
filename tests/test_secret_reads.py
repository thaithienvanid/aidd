"""Reading a secret file is `secret.use`, which asks: a shell command whose program reads or prints a file in the
`secrets` area, and a harness's own file-read tool on the area's paths. Example files and plain files stay allowed, and
`env` and `printenv` stay out, as SECURITY.md says. The readers and the paths come from the action's `file_reads` in
schemas/risks.json, so each case fails when that rule goes."""

from __future__ import annotations

import dataclasses
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

import helpers  # noqa: F401  # the hermetic environment
from aidd import risk
from aidd.risk import harness_rules
from aidd.risk.rules import Rule


def level(line: str, rs=None) -> str:
    return risk.command_level(rs or risk.rule_set(None), line)["level"]


def without_secret_reads(rs):
    """The rule set with `secret.use` allowed, as if its rule were gone."""
    rules = [r for r in rs.rules if r.action != "secret.use"] + [Rule(action="secret.use", level="allow")]
    return dataclasses.replace(rs, rules=rules)


class AShellCommandThatReadsASecretFileAsks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rs = risk.rule_set(None)
        cls.readers = cls.rs.actions["secret.use"]["file_reads"]["readers"]

    def test_every_reader_asks_on_a_secret_file(self):
        for reader in self.readers:
            line = {"cp": "cp .env /tmp/copy", "grep": "grep x .env", "rg": "rg x .env", "sed": "sed p .env", "awk": "awk 1 .env"}.get(reader, f"{reader} .env")
            with self.subTest(line=line):
                self.assertEqual(level(line, self.rs), "ask")
                self.assertEqual(level(line, without_secret_reads(self.rs)), "allow")

    def test_each_command_form_asks(self):
        cases = [
            "cat ./.env",
            "cat config/.env.local",
            "head -n 3 .env.production",
            "grep -r API_KEY .env",
            "sed -n 1p deploy/server.pem",
            "awk '{print}' ~/.ssh/id_rsa",
            "base64 certs/signing.p12",
            "xxd certs/upload.pfx",
            "set -a && . ./.env",
            "source .env",
            "cp .env backup.env",
            "/bin/cat .env",
            "FOO=1 tail .env",
            "sudo cat .env",
            "bash -c 'cat .env'",
            "cat .env | grep TOKEN",
            "echo $(cat .env)",
        ]
        for line in cases:
            with self.subTest(line=line):
                self.assertEqual(level(line, self.rs), "ask")
                self.assertEqual(level(line, without_secret_reads(self.rs)), "allow")

    def test_example_files_plain_files_and_other_commands_stay_allowed(self):
        cases = [
            "cat .env.example",
            "cat .env.sample",
            "cat .env.template",
            "cat config/credentials.yml.example",
            "cp .env.example .env",  # cp writes `.env`, it reads only the example
            "cat README.md",
            "cat src/crypto/cipher.py",  # cryptography code is no secret file
            "grep -r TOKEN src",
            "vim .env",  # no reader: the skill and the person judge an edit
            "env",
            "printenv",
        ]
        for line in cases:
            with self.subTest(line=line):
                self.assertEqual(level(line, self.rs), "allow")


class OnlyASecretFilesTemplateLeavesTheArea(unittest.TestCase):
    """The `secrets` area's excludes take a path out only when the area's paths match it, and only a final `.example`,
    `.sample`, `.template`, or `.dist` on a secret name makes a template."""

    CASES = [
        (".env", True),
        (".env.local", True),
        (".env.example", False),
        (".env.sample", False),
        (".env.template", False),
        (".env.dist", False),
        ("config/credentials.yaml.example", False),
        ("certs/server.key.sample", False),
        ("certs/server.pem.template", False),
        (".env.example.local", True),  # "example" before the last suffix: a real secret file
        ("keys/example.key", True),  # a real key named example
        ("certs/sample.pem", True),
        ("src/app.example", False),  # in no area: the exclude adds nothing
    ]

    def test_each_path(self):
        rs = risk.rule_set(None)
        for path, secret in self.CASES:
            with self.subTest(path=path):
                self.assertEqual("secret.use" in [a for a, _ in risk.call_actions(rs, f"cat {path}")], secret)
                self.assertEqual(level(f"cat {path}", rs), "ask" if secret else "allow")

    def test_the_exclude_holds_only_in_its_own_area(self):
        rs = risk.rule_set(None)
        self.assertIn("auth", risk.areas_of(rs, "src/auth/settings.example"))


class TheReadListIsSecretFilesNotSecretsCode(unittest.TestCase):
    """The R407 re-review: reads have their own list of files that hold secrets (M2), apart from the `secrets` area,
    and a reader's pattern word or redirect target is no file it reads (L2)."""

    CASES = [
        ("cat ~/.netrc", "ask"),
        ("cat .envrc", "ask"),
        ("cat .dev.vars", "ask"),
        ("cat ~/.aws/credentials", "ask"),
        ("cat config/credentials.json", "ask"),
        ("cat ~/.ssh/id_ecdsa", "ask"),
        ("cat config/secrets.yml", "ask"),
        ("cat src/secrets/client.py", "allow"),  # code that handles secrets
        ("cat lib/secrets.ts", "ask"),  # a file named secrets asks, whatever its extension (`file_reads.include`)
        ("rg TOKEN .env", "ask"),
        ("diff .env .env.example", "ask"),
        ("grep -e TOKEN .env", "ask"),
        ("grep -f .env notes.txt", "ask"),  # `-f` reads its patterns from the file
        ("grep .env README.md", "allow"),  # the pattern, never a file
        ("sed s/.env/x/ notes.txt", "allow"),
        ("awk /.env/ notes.txt", "allow"),
        ("cat README.md > .env", "allow"),  # it writes the file, never reads it
        ("cat README.md >> .env", "allow"),
        ("cat < .env", "ask"),
    ]

    def test_each_command(self):
        rs = risk.rule_set(None)
        for line, want in self.CASES:
            with self.subTest(line=line):
                self.assertEqual(level(line, rs), want)


class APatternOrARedirectIsReadAsTheShellReadsIt(unittest.TestCase):
    """The second R407 re-review: an attached `-e`, `-f`, `--regexp=`, `--file=`, or `--expression=` gives the pattern
    too, and an attached `-f` or `--file` reads its file. An option aidd does not fully understand keeps the first word,
    which may then be a file. Only an unquoted operator is a redirection, and `<` reads its file."""

    CASES = [
        ("grep -eTOKEN .env", "ask"),
        ("grep --regexp=TOKEN .env", "ask"),
        ("rg --regexp TOKEN .env", "ask"),
        ("sed --expression=p .env", "ask"),
        ("sed -ep .env", "ask"),
        ("sed -n -e p .env", "ask"),
        ("grep -f.env notes.txt", "ask"),  # an attached `-f` reads its file
        ("grep --file=.env notes.txt", "ask"),
        ("awk -f.env notes.txt", "ask"),
        ("grep -if.env notes.txt", "ask"),  # `-i`, then `-f` with its file attached
        ("grep -ief.env notes.txt", "allow"),  # `-i`, then `-e` with the pattern `f.env`
        ("grep --some-new-flag .env", "ask"),  # an option aidd does not know: `.env` may be a file
        ("grep -A 3 .env", "ask"),  # `-A` takes a value, so `.env` may be a file
        ("rg -g x .env", "ask"),
        ("sed -i.bak s/a/b/ .env", "ask"),
        ("grep -rn .env src", "allow"),  # flags aidd knows: `.env` is the pattern
        ("grep -i --count .env src", "allow"),
        ("grep -- .env README.md", "allow"),
        ("grep -e x -- .env", "ask"),
        ("cat -e .env", "ask"),  # `cat -e` shows line ends: `-e` gives a pattern only to a grep-like reader
        ("tail -f .env", "ask"),
        ('grep ">" .env', "ask"),  # a quoted `>` is a word, never a redirection
        ("grep '>>' .env", "ask"),
        ('cat ">" .env', "ask"),
        (r"grep \> .env", "ask"),
        ('"cat" .env', "ask"),
        ("cat <.env", "ask"),  # the shell opens `.env` for the command to read
        ("cat 0< .env", "ask"),
        ("cat .env 2>&1", "ask"),
        ("cat README.md >.env", "allow"),
        ("cat README.md 2>.env", "allow"),
        ("cat README.md 2> .env", "allow"),
        ("cat README.md &> .env", "allow"),
        ("cat README.md >| .env", "allow"),
    ]

    def test_each_command(self):
        rs = risk.rule_set(None)
        for line, want in self.CASES:
            with self.subTest(line=line):
                self.assertEqual(level(line, rs), want)


class TheReadListCoversEverySecretFileOfTheArea(unittest.TestCase):
    """The second R407 re-review: the read list dropped the area's key stores and mobile config files. Every path of the
    `secrets` area that names a file that holds secrets is in it, a data file under `secrets/` asks, and code does not."""

    # The area's paths that also name code, and why a read of them does not ask as a whole.
    CODE = {
        "**/crypto/**": "cryptography code, which holds no secret",
        "**/crypto.*": "a cryptography module, such as crypto.py",
        "**/encryption.*": "an encryption module, such as encryption.ts",
        "**/secrets/**": "code that handles secrets, such as src/secrets/client.py: only its data files ask",
    }
    DATA = ("yml", "yaml", "json", "toml", "env", "txt", "pem", "key", "p12", "pfx", "crt")

    @classmethod
    def setUpClass(cls):
        cls.rs = risk.rule_set(None)
        cls.area = cls.rs.areas["secrets"]["paths"]

    def test_every_secret_file_path_of_the_area_asks_on_a_read(self):
        for glob in self.area:
            if glob not in self.CODE:
                path = glob.replace("**/", "config/").replace("*", "server")
                with self.subTest(glob=glob, path=path):
                    self.assertEqual(level(f"cat {path}", self.rs), "ask")

    def test_each_code_exclusion_is_still_a_path_of_the_area(self):
        self.assertLessEqual(set(self.CODE), set(self.area))

    def test_a_data_file_under_secrets_asks_and_code_does_not(self):
        for ext in self.DATA:
            for path in (f"config/secrets/prod.{ext}", f"deploy/secrets/db/prod.{ext}", f"config/secrets.{ext}"):
                with self.subTest(path=path):
                    self.assertEqual(level(f"cat {path}", self.rs), "ask")
        for path in ("src/secrets/client.py", "src/secrets/index.ts", "src/crypto/cipher.py", "src/encryption.py"):
            with self.subTest(path=path):
                self.assertEqual(level(f"cat {path}", self.rs), "allow")

    def test_a_credentials_data_file_asks_and_its_code_does_not(self):
        """The security confirm of ace25f6, and the review after it: `credentials.*` and `secrets.*` stay broad, so an
        extension aidd has never seen asks, and source code is excluded, so reading it does not."""
        for ext in ("json", "yml", "toml", "ini", "env", "txt", "cfg", "conf", "bak", "old", "gpg", "enc", "local", "db", "zzz"):
            with self.subTest(ext=ext):
                self.assertEqual(level(f"cat config/credentials.{ext}", self.rs), "ask")
        for path in (
            "src/auth/credentials.py",
            "lib/credentials.ts",
            "lib/credentials.test.ts",
            "pkg/credentials.go",
            "src/Credentials.java",
            "src/secrets/vault.rs",
        ):
            with self.subTest(path=path):
                self.assertEqual(level(f"cat {path}", self.rs), "allow")
        self.assertEqual(level("cat ~/.aws/credentials", self.rs), "ask")

    def test_a_secrets_file_asks_whatever_its_extension(self):
        """The final security confirm of f7fdec0: `file_reads.include` wins over the code excludes, so a file named
        `secrets.<ext>` asks, such as Django's settings/secrets.py, while other code stays allowed."""
        for path in ("config/settings/secrets.py", "include/secrets.h", "App/Secrets.swift", "lib/secrets.dart"):
            with self.subTest(path=path):
                self.assertEqual(level(f"cat {path}", self.rs), "ask")
        for path in ("src/auth/credentials.py", "config/local_settings.py", "src/secrets/client.py"):
            with self.subTest(path=path):
                self.assertEqual(level(f"cat {path}", self.rs), "allow")

    def test_a_public_key_is_no_secret(self):
        for line, want in (("cat ~/.ssh/id_rsa.pub", "allow"), ("cat id_ed25519.pub", "allow"), ("cat ~/.ssh/id_rsa", "ask")):
            with self.subTest(line=line):
                self.assertEqual(level(line, self.rs), want)


class AHarnessReadToolAsksOnASecretFile(unittest.TestCase):
    """Each harness whose ask rules hold a file-read rule gets one for each of the area's paths; the others get none."""

    READS = {
        "claude-code": lambda root: json.loads((root / ".claude/settings.json").read_text())["permissions"]["ask"],
        "qwen": lambda root: json.loads((root / ".qwen/settings.json").read_text())["permissions"]["ask"],
        "grok": lambda root: tomllib.loads((root / ".grok/config.toml").read_text())["permission"]["ask"],
    }

    def written(self, fmt: str, rs) -> str:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            risk.apply_harness_rules(root, fmt, risk.harness_patterns(rs, "main"), read_paths=risk.harness_read_paths(rs))
            if fmt in self.READS:
                return json.dumps(self.READS[fmt](root))
            return "".join(p.read_text() for p in root.rglob("*") if p.is_file() and p.name != "harness-rules.json")

    def test_every_format_is_in_the_table_or_has_no_read_tool(self):
        self.assertEqual(sorted(self.READS), sorted(f for f, spec in harness_rules.FORMATS.items() if spec.reads))

    def test_each_harness_with_a_read_tool_asks_on_every_secret_path(self):
        rs = risk.rule_set(None)
        paths = rs.actions["secret.use"]["file_reads"]["paths"]
        for fmt in harness_rules.FORMATS:
            with self.subTest(fmt=fmt):
                text = self.written(fmt, rs)
                for p in paths:
                    self.assertEqual(json.dumps(f"Read({p})") in text, fmt in self.READS, p)

    def test_no_harness_asks_once_the_rule_is_gone(self):
        rs = without_secret_reads(risk.rule_set(None))
        self.assertEqual(risk.harness_read_paths(rs), [])
        for fmt in harness_rules.FORMATS:
            with self.subTest(fmt=fmt):
                self.assertNotIn("Read(", self.written(fmt, rs))


if __name__ == "__main__":
    unittest.main()
