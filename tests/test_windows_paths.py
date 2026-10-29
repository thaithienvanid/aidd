"""What aidd does differently on Windows, checked on every OS: command lines where a backslash is a path separator,
absolute interpreter paths in a Spec's test commands, and the PowerShell hook commands init writes there."""

import shlex
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src on sys.path)

from aidd.setup import hook_wiring
from aidd.workitems import spec_file
from aidd.kernel import processes

PY = r"C:\hostedtoolcache\windows\Python\3.11.9\x64\python.exe"


class SplitCommandTests(unittest.TestCase):
    def test_a_windows_path_keeps_its_backslashes(self):
        self.assertEqual(processes.split_command(rf"{PY} C:\work\agent.py", windows=True), [PY, r"C:\work\agent.py"])

    def test_quotes_group_words_on_every_os(self):
        line = "'C:\\Program Files\\py.exe' \"C:\\a b\\x.py\" -p"
        self.assertEqual(processes.split_command(line, windows=True), [r"C:\Program Files\py.exe", r"C:\a b\x.py", "-p"])
        self.assertEqual(processes.split_command('claude -p --model "x y"', windows=False), ["claude", "-p", "--model", "x y"])
        self.assertEqual(processes.split_command(r"a\ b", windows=False), ["a b"])  # POSIX keeps its escapes


class CommandPathTests(unittest.TestCase):
    def test_an_absolute_interpreter_is_not_a_repository_path(self):
        for exe in ("/usr/bin/python3", "C:/Python311/python.exe", PY, r"\\server\share\python.exe"):
            self.assertEqual(spec_file._path_literals([exe, "checks/test_greet.py"]), ["checks/test_greet.py"], exe)


class PowerShellHookTests(unittest.TestCase):
    launcher = ([PY, "-m", "aidd"], {"PYTHONPATH": r"D:\a\aidd\src"})

    def test_the_command_sets_the_environment_calls_the_program_and_fails_open(self):
        pre = hook_wiring.hook_command("pre-tool", self.launcher, shell="powershell")
        self.assertEqual(pre, rf"$env:PYTHONPATH = 'D:\a\aidd\src'; & '{PY}' -m aidd hook pre-tool")
        self.assertTrue(pre.endswith(f"{shlex.quote(PY)} -m aidd hook pre-tool"))
        self.assertEqual(hook_wiring.hook_command("stop", self.launcher, shell="powershell"), pre.replace("pre-tool", "stop") + "; exit 0")
        self.assertEqual(hook_wiring.hook_command("stop", (["aidd"], {}), shell="powershell"), "aidd hook stop; exit 0")

    def test_doctor_reads_back_what_init_writes_in_either_syntax(self):
        for shell in ("sh", "powershell"):
            for sub in ("pre-tool", "stop"):
                command = hook_wiring.hook_command(sub, self.launcher, shell=shell)
                # In sh, init names the user launcher; PowerShell names the launcher itself.
                want = ([hook_wiring.user_launcher_file(), "hook", sub], {}) if shell == "sh" else ([PY, "-m", "aidd", "hook", sub], self.launcher[1])
                with mock.patch.object(processes.os, "name", "nt"):
                    self.assertEqual(hook_wiring.parse_hook(command, sub), want, command)
                self.assertEqual(hook_wiring.aidd_hook(command), sub)
        quoted = hook_wiring.hook_command("pre-tool", ([r"C:\it's\python.exe", "-m", "aidd"], {}), shell="powershell")
        self.assertEqual(hook_wiring.command_program(quoted), r"C:\it's\python.exe")

    def test_an_unquoted_windows_path_is_not_mangled(self):
        command = rf"PYTHONPATH=C:\Users\RUNNER~1\tmp\nowhere {PY} -m aidd hook pre-tool"
        with mock.patch.object(processes.os, "name", "nt"):
            self.assertEqual(
                hook_wiring.parse_hook(command, "pre-tool"), ([PY, "-m", "aidd", "hook", "pre-tool"], {"PYTHONPATH": r"C:\Users\RUNNER~1\tmp\nowhere"})
            )

    def test_windows_entries_name_their_shell(self):
        with mock.patch.object(hook_wiring, "_hook_shell", return_value="powershell"):
            self.assertEqual(hook_wiring._hook_entry("aidd hook stop; exit 0", 10)["shell"], "powershell")
        with mock.patch.object(hook_wiring, "_hook_shell", return_value="sh"):
            self.assertNotIn("shell", hook_wiring._hook_entry("aidd hook stop || true", 10))
            self.assertNotIn("shell", hook_wiring._rewire({"command": "x", "shell": "powershell"}, "aidd hook stop || true"))


if __name__ == "__main__":
    unittest.main()
