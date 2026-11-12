"""A GitHub remote's `owner/name`: the delegate check puts it into every `gh api repos/<slug>` path, with the one parser
in `kernel.remote_urls`. `aidd init` reads the remote for nothing: the config holds no `project.repo`."""

import tempfile
import unittest

import helpers  # noqa: F401  # puts src on the path
from init_plan_helpers import plan_of, repo

from aidd.kernel import documents, remote_urls

SLUGS = [
    ("https://github.com/acme/shop", "acme/shop"),
    ("https://github.com/acme/shop.git", "acme/shop"),
    ("https://github.com/acme/shop/", "acme/shop"),
    ("  https://github.com/acme/shop.git\n", "acme/shop"),
    ("https://token@github.com/acme/shop.git", "acme/shop"),
    ("git@github.com:acme/shop.git", "acme/shop"),
    ("ssh://git@github.com/acme/shop", "acme/shop"),
    ("https://github.com/octo_acme/my.repo-2", "octo_acme/my.repo-2"),
    ("https://gitlab.com/acme/shop", None),
    ("https://github.com.evil.example/acme/shop", None),
    ("https://github.com/acme/..", None),
    ("https://github.com/acme/.", None),
    ("https://github.com/acme/..git", None),
    ("https://github.com/../shop", None),
    ("https://github.com/" + "a" * 40 + "/shop", None),
    ("https://github.com/acme", None),
    ("https://github.com/acme/shop/extra", None),
    ("file:///github.com/acme/shop", None),
    ("", None),
]


class GitHubSlugTests(unittest.TestCase):
    def test_one_parser_reads_the_slug(self):
        for url, slug in SLUGS:
            with self.subTest(url=url):
                self.assertEqual(remote_urls.github_slug(url), slug)

    def test_init_writes_no_repo_into_the_config_from_origin(self):
        with tempfile.TemporaryDirectory() as d:
            plan, _ = plan_of(repo(d), [])
        self.assertNotIn("repo:", plan.config)
        self.assertNotIn("repo", (documents.parse_yaml(plan.config, "config").get("project") or {}))


if __name__ == "__main__":
    unittest.main()
