import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import certificate_macos
from proxy_backend_macos import (
    MacOSProxyBackend,
    NetworkSetupError,
    ProxyServiceState,
    ProxySnapshot,
    parse_key_value_output,
    save_snapshot,
)


class MacOSSupportTests(unittest.TestCase):
    def test_frozen_runner_uses_internal_mitmdump_dispatch(self):
        from launcher_macos import ensure_mitmdump

        with patch.object(__import__("launcher_macos").sys, "frozen", True, create=True):
            with patch.object(__import__("launcher_macos").sys, "executable", "/app/wxas-runner"):
                self.assertEqual(ensure_mitmdump(), ["/app/wxas-runner", "--mitmdump"])

    def test_parse_networksetup_output(self):
        values = parse_key_value_output("Enabled: Yes\nURL: http://127.0.0.1:8898/proxy.pac\n")
        self.assertEqual(values, {"Enabled": "Yes", "URL": "http://127.0.0.1:8898/proxy.pac"})

    def test_snapshot_round_trip(self):
        snapshot = ProxySnapshot(
            pac_url="http://127.0.0.1:8898/proxy.pac",
            created_at="2026-08-29T00:00:00+00:00",
            services=[
                ProxyServiceState(
                    name="Wi-Fi",
                    auto_enabled=False,
                    auto_url="",
                    manual_enabled={"web": True, "secureweb": False, "socksfirewall": False},
                    raw={"web.Server": "proxy.example"},
                )
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backup.json"
            save_snapshot(path, snapshot)
            restored = ProxySnapshot.from_dict(json.loads(path.read_text()))
        self.assertEqual(restored.to_dict(), snapshot.to_dict())

    def test_apply_disables_manual_proxies_without_overwriting_values(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            if args[1] == "-getautoproxyurl":
                return Mock(returncode=0, stdout="Enabled: No\nURL: (null)\n", stderr="")
            if args[1] in {"-getwebproxy", "-getsecurewebproxy", "-getsocksfirewallproxy"}:
                return Mock(returncode=0, stdout="Enabled: No\nServer: proxy\nPort: 8080\n", stderr="")
            return Mock(returncode=0, stdout="", stderr="")

        backend = MacOSProxyBackend(runner=runner)
        snapshot = backend.snapshot(["Wi-Fi"], "http://127.0.0.1:8898/proxy.pac")
        backend.apply(snapshot)
        commands = [tuple(call[1:]) for call in calls if len(call) > 1]
        self.assertIn(("-setautoproxyurl", "Wi-Fi", "http://127.0.0.1:8898/proxy.pac"), commands)
        self.assertIn(("-setwebproxystate", "Wi-Fi", "off"), commands)
        self.assertIn(("-setsecurewebproxystate", "Wi-Fi", "off"), commands)

    def test_apply_restores_service_when_setting_fails_midway(self):
        calls = []
        failed = False

        def runner(args, **kwargs):
            nonlocal failed
            calls.append(args)
            if args[1] == "-setautoproxystate" and args[3] == "on" and not failed:
                failed = True
                return Mock(returncode=1, stdout="", stderr="simulated failure")
            return Mock(returncode=0, stdout="", stderr="")

        backend = MacOSProxyBackend(runner=runner)
        snapshot = ProxySnapshot(
            pac_url="http://127.0.0.1:8898/proxy.pac",
            created_at="2026-08-29T00:00:00+00:00",
            services=[
                ProxyServiceState(
                    name="Wi-Fi",
                    auto_enabled=False,
                    auto_url="",
                    manual_enabled={"web": True, "secureweb": False, "socksfirewall": False},
                    raw={},
                )
            ],
        )

        with self.assertRaises(NetworkSetupError):
            backend.apply(snapshot)

        commands = [tuple(call[1:]) for call in calls]
        self.assertNotIn(("-setautoproxyurl", "Wi-Fi", ""), commands)
        self.assertIn(("-setautoproxystate", "Wi-Fi", "off"), commands)
        self.assertIn(("-setwebproxystate", "Wi-Fi", "on"), commands)

    def test_restore_does_not_pass_empty_pac_url_to_networksetup(self):
        calls = []

        def runner(args, **kwargs):
            calls.append(args)
            return Mock(returncode=0, stdout="", stderr="")

        state = ProxyServiceState(
            name="Wi-Fi",
            auto_enabled=False,
            auto_url="",
            manual_enabled={"web": False, "secureweb": False, "socksfirewall": False},
            raw={},
        )
        from proxy_backend_macos import restore_service_state

        restore_service_state(state, runner=runner)

        self.assertNotIn(
            ["networksetup", "-setautoproxyurl", "Wi-Fi", ""],
            calls,
        )
        self.assertIn(
            ["networksetup", "-setautoproxystate", "Wi-Fi", "off"],
            calls,
        )

    def test_select_services_deduplicates_explicit_names(self):
        def runner(args, **kwargs):
            if args[1] == "-listallnetworkservices":
                return Mock(returncode=0, stdout="An asterisk denotes...\nWi-Fi\n", stderr="")
            raise AssertionError(args)

        backend = MacOSProxyBackend(runner=runner)
        self.assertEqual(backend.select_services([" Wi-Fi ", "Wi-Fi"]), ["Wi-Fi"])


    def test_pac_contains_allowlist_and_direct_fallback(self):
        from launcher_macos import pac_payload

        pac = pac_payload(9900).decode("utf-8")
        self.assertIn('host === "mp.weixin.qq.com"', pac)
        self.assertIn('PROXY 127.0.0.1:9900', pac)
        self.assertIn('return "DIRECT"', pac)

    def test_normalize_fingerprint(self):
        self.assertEqual(
            certificate_macos.normalize_fingerprint("aa:bb:01"),
            "AABB01",
        )


if __name__ == "__main__":
    unittest.main()
