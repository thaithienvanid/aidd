"""templates/devcontainer/: an optional dev container that denies outbound traffic except to an allow-list, and
`aidd init --devcontainer`, which copies it. aidd sandboxes nothing itself; this is a starting point, and its files
are protected paths, so changing the allow-list is a major change."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git

from aidd.setup import uninstalling
from aidd.setup import adoption
from aidd.gate import routing
from aidd import config

TPL = ROOT / "templates" / "devcontainer"
# The firewall script runs as root inside the Linux dev container. On Windows, the `bash` on PATH is WSL's launcher or
# the one Git for Windows ships, where the script's root check and its faked tools do not hold: its runs are POSIX only.
LINUX_SCRIPT = "the firewall script runs in the Linux dev container, never on Windows"


def jsonc(text: str) -> dict:
    """devcontainer.json allows // comments; none of its strings holds one."""
    return json.loads(re.sub(r"(?m)^\s*//.*$", "", text))


class TemplateTests(unittest.TestCase):
    def test_the_container_gets_the_capabilities_and_starts_the_firewall(self):
        conf = jsonc((TPL / "devcontainer.json").read_text(encoding="utf-8"))
        self.assertEqual(conf["build"]["dockerfile"], "Dockerfile")
        self.assertEqual(sorted(conf["runArgs"]), ["--cap-add=NET_ADMIN", "--cap-add=NET_RAW"])
        self.assertEqual(conf["postStartCommand"], "sudo /usr/local/sbin/aidd-init-firewall")
        self.assertEqual(conf["waitFor"], "postStartCommand")
        docker = (TPL / "Dockerfile").read_text(encoding="utf-8")
        # Every build arg the JSON sets is one the Dockerfile declares; the model API host is one of them.
        declared = set(re.findall(r"(?m)^ARG (\w+)", docker))
        self.assertLessEqual(set(conf["build"]["args"]), declared)
        self.assertIn("MODEL_API_HOST", conf["build"]["args"])
        self.assertEqual(conf["remoteUser"], re.search(r"(?m)^ARG USERNAME=(\w+)", docker).group(1))

    def test_the_allow_list_is_baked_in_root_owned_and_sudo_runs_only_the_script(self):
        docker = (TPL / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY init-firewall.sh /usr/local/sbin/aidd-init-firewall", docker)
        self.assertIn("> /etc/aidd-egress/allowed-hosts", docker)
        (sudoers,) = re.findall(r"printf '(%s ALL=[^']*)'", docker)
        self.assertEqual(sudoers, r"%s ALL=(root) NOPASSWD: /usr/local/sbin/aidd-init-firewall\n")
        self.assertRegex(docker, r"(?m)^FROM \S+@sha256:[0-9a-f]{64}$")  # the base image by digest
        self.assertRegex(docker, r"(?m)^USER \$USERNAME$")  # the agent never runs as root

    def test_the_firewall_denies_by_default_and_reads_no_input(self):
        script = (TPL / "init-firewall.sh").read_text(encoding="utf-8")
        for rule in ("iptables -P OUTPUT DROP", "iptables -P INPUT DROP", "iptables -P FORWARD DROP", "ip6tables -P OUTPUT DROP"):
            self.assertIn(rule, script)
        self.assertIn('--match-set "$SET" dst -j ACCEPT', script)
        self.assertIn("https://example.com", script)  # it checks that a host off the list is refused
        self.assertNotRegex(re.sub(r"'[^'\n]*'", "", script), r"\$[1-9@*]")  # no arguments (awk's $1 is in quotes)
        self.assertIn("ALLOW=/etc/aidd-egress/allowed-hosts", script)

    @unittest.skipIf(os.name == "nt", LINUX_SCRIPT)
    @unittest.skipUnless(shutil.which("bash"), "bash is required")
    def test_the_script_is_valid_bash(self):
        run = subprocess.run(["bash", "-n", str(TPL / "init-firewall.sh")], capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        if shutil.which("shellcheck"):
            run = subprocess.run(["shellcheck", str(TPL / "init-firewall.sh")], capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 0, run.stdout)

    @unittest.skipIf(os.name == "nt", LINUX_SCRIPT)
    def test_ipv6_is_denied_when_it_is_on_and_a_failure_stops_the_start(self):
        bash = shutil.which("bash")
        if not bash or subprocess.run([bash, "-c", "[ ${BASH_VERSINFO[0]} -ge 4 ]"], check=False).returncode != 0:
            self.skipTest("bash 4 or later is required (mapfile)")
        tools = {t: shutil.which(t) for t in ("grep", "awk", "sort", "head", "cat")}
        if not all(tools.values()):
            self.skipTest("grep, awk, sort, head, and cat are required")
        for ipv6, ip6tables, expect, said in (
            ("0", "ok", 0, "ip6tables -P OUTPUT DROP"),
            ("0", None, 1, "ip6tables is missing"),
            ("0", "fail", None, "ip6tables -F"),
            ("1", None, 0, "outbound traffic allowed only to"),
        ):
            with self.subTest(ipv6=ipv6, ip6tables=ip6tables), tempfile.TemporaryDirectory() as tmp:
                code, log, out = self._run_firewall(Path(tmp), bash, tools, ipv6, ip6tables)
                if expect is None:
                    self.assertNotEqual(code, 0, out)
                else:
                    self.assertEqual(code, expect, out)
                self.assertIn(said, log + out)
                if ipv6 == "1":
                    self.assertNotIn("ip6tables", log)

    def _run_firewall(self, tmp: Path, bash: str, tools: dict, ipv6: str, ip6tables: str | None) -> tuple[int, str, str]:
        """Run a copy of the script whose fixed paths point into `tmp`, with every command it runs faked but the text tools."""
        etc, stubs, bins = tmp / "etc", tmp / "stubs", tmp / "bin"
        for d in (etc, stubs, bins):
            d.mkdir()
        (etc / "allowed-hosts").write_text("git.example\n", encoding="utf-8")
        (etc / "code-host").write_text("git.example\n", encoding="utf-8")
        (etc / "resolv.conf").write_text("nameserver 10.0.0.53\n", encoding="utf-8")
        (etc / "disable_ipv6").write_text(ipv6 + "\n", encoding="utf-8")
        log = tmp / "log"
        script = (TPL / "init-firewall.sh").read_text(encoding="utf-8")
        for real, fake in (
            ("/proc/sys/net/ipv6/conf/all/disable_ipv6", etc / "disable_ipv6"),
            ("/etc/aidd-egress/allowed-hosts", etc / "allowed-hosts"),
            ("/etc/aidd-egress/code-host", etc / "code-host"),
            ("/etc/resolv.conf", etc / "resolv.conf"),
        ):
            self.assertIn(real, script)
            script = script.replace(real, str(fake))
        (tmp / "fw.sh").write_text(script, encoding="utf-8")
        fakes = {
            "id": "echo 0",
            "getent": "echo '192.0.2.10 STREAM git.example'",
            "iptables": f'echo "iptables $*" >> {log}',
            "ipset": f'echo "ipset $*" >> {log}',
            "curl": 'case "$*" in *example.com*) exit 7;; esac; exit 0',
        }
        if ip6tables:
            fakes["ip6tables"] = f'echo "ip6tables $*" >> {log}' + ("; exit 1" if ip6tables == "fail" else "")
        for name, body in fakes.items():
            (stubs / name).write_text(f"#!{bash}\n{body}\n", encoding="utf-8")
            (stubs / name).chmod(0o755)
        for name, path in tools.items():
            (bins / name).symlink_to(path)
        run = subprocess.run([bash, str(tmp / "fw.sh")], env={"PATH": f"{stubs}:{bins}"}, capture_output=True, text=True, check=False, timeout=60)
        return run.returncode, log.read_text(encoding="utf-8") if log.exists() else "", run.stdout + run.stderr

    def test_changing_it_is_a_major_change(self):
        cfg = config.load_text('aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n')
        self.assertEqual(routing.assess_paths(cfg, [".devcontainer/devcontainer.json"]).required_route, "major")


@unittest.skipUnless(shutil.which("git"), "git is required")
class InitTests(unittest.TestCase):
    def test_init_writes_it_only_when_asked_and_uninstall_removes_it_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            git(root, "init", "-q")
            adoption.init(root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[]))
            self.assertFalse((root / ".devcontainer").exists())
            actions = adoption.init(
                root, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@x"], harnesses=[], devcontainer=True)
            )
            for name in adoption.DEVCONTAINER_FILES:
                self.assertEqual((root / ".devcontainer" / name).read_bytes(), (TPL / name).read_bytes())
                self.assertIn(f"wrote    {root / '.devcontainer' / name}", actions)
            (root / ".devcontainer" / "devcontainer.json").write_text("{}\n", encoding="utf-8")  # the team's own edit
            out = uninstalling.uninstall(root, yes=True)
            self.assertFalse((root / ".devcontainer" / "Dockerfile").exists())
            self.assertTrue((root / ".devcontainer" / "devcontainer.json").is_file())
            self.assertIn(f"kept     {root / '.devcontainer' / 'devcontainer.json'} (changed since init)", out)


if __name__ == "__main__":
    unittest.main()
