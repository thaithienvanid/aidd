"""Fetching an `extends` parent by URL: https only, public addresses only, no redirects."""

import socket
import unittest
from unittest import mock

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import http, inputs


def resolves_to(ip):
    return lambda host, port, proto=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


class ExtendsFetchTests(unittest.TestCase):
    def test_only_https_is_fetched(self):
        with self.assertRaises(http.HttpError) as cm:
            inputs.fetch_text("http://presets.example.com/aidd.toml")
        self.assertIn("only https", str(cm.exception))

    def test_internal_addresses_are_refused(self):
        for ip, kind in (("127.0.0.1", "loopback"), ("10.0.0.5", "private"), ("169.254.169.254", "link-local"), ("224.0.0.1", "multicast")):
            with self.subTest(ip=ip), mock.patch("socket.getaddrinfo", resolves_to(ip)):
                with self.assertRaises(http.HttpError) as cm:
                    inputs.fetch_text("https://presets.example.com/aidd.toml")
                self.assertIn(kind, str(cm.exception))

    def test_an_unresolvable_host_is_refused(self):
        def fail(*a, **k):
            raise socket.gaierror("no such host")

        with mock.patch("socket.getaddrinfo", fail), self.assertRaises(http.HttpError):
            inputs.fetch_text("https://nowhere.invalid/aidd.toml")

    def test_a_public_address_is_fetched_without_following_redirects(self):
        seen = {}

        def get_bytes(url, **kw):
            seen.update(kw, url=url)
            return b'aidd_version = "1.0.0"\n'

        with mock.patch("socket.getaddrinfo", resolves_to("93.184.216.34")), mock.patch.object(http, "get_bytes", get_bytes):
            self.assertIn("aidd_version", inputs.fetch_text("https://presets.example.com/aidd.toml"))
        self.assertIs(seen["follow_redirects"], False)

    def test_loading_a_config_from_disk_uses_the_protected_fetch(self):
        import tempfile
        from pathlib import Path

        from aidd import config

        with tempfile.TemporaryDirectory() as d:
            Path(d, ".aidd").mkdir()
            Path(d, ".aidd/config.toml").write_text(
                'aidd_version = "1.0.0"\nprofile = "solo"\nextends = [{ url = "https://metadata.example.com/p.toml", sha256 = "' + "0" * 64 + '" }]\n',
                encoding="utf-8",
            )
            with (
                mock.patch.dict("os.environ", {"AIDD_HOOK_OFFLINE": ""}),
                mock.patch("socket.getaddrinfo", resolves_to("169.254.169.254")),
                mock.patch.object(http, "get_bytes") as get,
                self.assertRaises(http.HttpError) as cm,
            ):
                config.load_file(config.CONFIG_PATH, d)
            get.assert_not_called()  # refused before any request, as the gate's own fetch refuses it
            self.assertIn("link-local", str(cm.exception))

    def test_host_and_port_survive_a_malformed_port(self):
        self.assertEqual(inputs.host_and_port("https://presets.example.com:8443/a.toml"), ("presets.example.com", 8443))
        self.assertEqual(inputs.host_and_port("https://presets.example.com:99999/a.toml"), ("presets.example.com", 443))


if __name__ == "__main__":
    unittest.main()
