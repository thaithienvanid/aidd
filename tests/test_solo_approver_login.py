"""`aidd init` names the solo approver from local configuration only, and never guesses a login from gh's active
account while gh holds more than one: that account is one machine-wide choice, and may be another identity's."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts src/ on the path, as for every test file)

from aidd.config import identities

ONE = "github.com:\n    users:\n        solo-dev:\n    user: solo-dev\n    git_protocol: https\n"
TWO = "github.com:\n    users:\n        work-login:\n        home-login:\n    user: work-login\n    git_protocol: https\n"
OLD = "github.com:\n    user: solo-dev\n    oauth_token: x\n"
OTHER_HOST = "ghe.example.com:\n    users:\n        a:\n        b:\n    user: a\ngithub.com:\n    users:\n        solo-dev:\n    user: solo-dev\n"


class GhAccountsTests(unittest.TestCase):
    def count(self, text: str | None) -> int:
        with tempfile.TemporaryDirectory() as d:
            if text is not None:
                Path(d, "hosts.yml").write_text(text, encoding="utf-8")
            with mock.patch.dict(os.environ, {"GH_CONFIG_DIR": d}):
                return identities.gh_account_count()

    def test_it_counts_the_accounts_gh_holds_for_github(self):
        self.assertEqual(self.count(ONE), 1)
        self.assertEqual(self.count(TWO), 2)
        self.assertEqual(self.count(OLD), 1)  # gh before multiple accounts
        self.assertEqual(self.count(OTHER_HOST), 1)  # another host's accounts are not github.com's
        self.assertEqual(self.count(None), 0)

    def test_two_accounts_mean_no_guess_from_gh_and_git_config_still_counts(self):
        probes = {("git", "config", "github.user"): None, ("gh", "config", "get", "-h", "github.com", "user"): "work-login"}
        with (
            mock.patch.object(identities, "_probe", side_effect=lambda cmd, root: probes[cmd]),
            mock.patch.object(identities, "gh_account_count", return_value=2),
        ):
            self.assertIsNone(identities.operator_login(Path(".")))
            probes[("git", "config", "github.user")] = "home-login"
            self.assertEqual(identities.operator_login(Path(".")), "home-login")
        with (
            mock.patch.object(identities, "_probe", side_effect=lambda cmd, root: {**probes, ("git", "config", "github.user"): None}[cmd]),
            mock.patch.object(identities, "gh_account_count", return_value=1),
        ):
            self.assertEqual(identities.operator_login(Path(".")), "work-login")


if __name__ == "__main__":
    unittest.main()
