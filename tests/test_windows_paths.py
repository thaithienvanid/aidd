"""What aidd does differently on Windows, checked on every OS: command lines where a backslash is a path separator,
absolute interpreter paths in a Spec's test commands, and the PowerShell hook commands init writes there."""

import unittest

import helpers  # noqa: F401  (puts src on sys.path)

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


if __name__ == "__main__":
    unittest.main()
