# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""macOS network-service PAC configuration and recovery helpers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

NETWORKSETUP = "networksetup"
STATE_VERSION = 1
MANUAL_PROXY_TYPES = ("web", "secureweb", "socksfirewall")
MANUAL_PROXY_STATE_COMMANDS = {
    "web": "-setwebproxystate",
    "secureweb": "-setsecurewebproxystate",
    "socksfirewall": "-setsocksfirewallproxystate",
}


class NetworkSetupError(RuntimeError):
    """Raised when a macOS networksetup operation fails."""


@dataclass
class ProxyServiceState:
    """The proxy settings changed by WxArticleSaver for one network service."""

    name: str
    auto_enabled: bool
    auto_url: str
    manual_enabled: dict[str, bool]
    raw: dict[str, str]

    @classmethod
    def from_dict(cls, value: dict) -> "ProxyServiceState":
        return cls(
            name=str(value["name"]),
            auto_enabled=bool(value.get("auto_enabled", False)),
            auto_url=str(value.get("auto_url", "")),
            manual_enabled={
                key: bool(value.get("manual_enabled", {}).get(key, False))
                for key in MANUAL_PROXY_TYPES
            },
            raw={str(k): str(v) for k, v in value.get("raw", {}).items()},
        )


@dataclass
class ProxySnapshot:
    """A restorable snapshot of all services modified by the tool."""

    pac_url: str
    services: list[ProxyServiceState]
    created_at: str
    version: int = STATE_VERSION

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "pac_url": self.pac_url,
            "created_at": self.created_at,
            "services": [asdict(service) for service in self.services],
        }

    @classmethod
    def from_dict(cls, value: dict) -> "ProxySnapshot":
        if int(value.get("version", 0)) != STATE_VERSION:
            raise ValueError(f"不支持的 macOS 代理备份版本：{value.get('version')}")
        return cls(
            pac_url=str(value.get("pac_url", "")),
            services=[ProxyServiceState.from_dict(item) for item in value.get("services", [])],
            created_at=str(value.get("created_at", "")),
            version=STATE_VERSION,
        )


CommandRunner = Callable[..., subprocess.CompletedProcess]


def _default_runner(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(args, **kwargs)


def _decode_output(result: subprocess.CompletedProcess) -> str:
    stdout = result.stdout if isinstance(result.stdout, str) else ""
    stderr = result.stderr if isinstance(result.stderr, str) else ""
    return stdout.strip() or stderr.strip()


def parse_key_value_output(output: str) -> dict[str, str]:
    """Parse the `networksetup` human-readable key/value output."""
    result: dict[str, str] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip()
    return result


def parse_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"yes", "on", "true", "1"}


def _run(
    args: list[str],
    *,
    runner: CommandRunner = _default_runner,
    check: bool = True,
) -> str:
    try:
        result = runner(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise NetworkSetupError(f"无法执行 macOS 命令：{' '.join(args)}：{exc}") from exc
    if check and result.returncode != 0:
        detail = _decode_output(result)
        raise NetworkSetupError(
            f"macOS 命令执行失败（{result.returncode}）：{' '.join(args)}"
            + (f"\n{detail}" if detail else "")
        )
    return _decode_output(result)


def list_network_services(*, runner: CommandRunner = _default_runner) -> list[str]:
    """Return configured network service names, excluding disabled markers."""
    output = _run([NETWORKSETUP, "-listallnetworkservices"], runner=runner)
    services = []
    for line in output.splitlines():
        name = line.strip()
        if not name or name.startswith("An asterisk"):
            continue
        if name.startswith("*"):
            # networksetup prefixes disabled services with an asterisk.
            continue
        if name:
            services.append(name)
    return services


def service_has_address(service: str, *, runner: CommandRunner = _default_runner) -> bool:
    """Best-effort check that a service currently has an IP address."""
    output = _run([NETWORKSETUP, "-getinfo", service], runner=runner, check=False)
    values = parse_key_value_output(output)
    address = values.get("IP address", "").strip().lower()
    return bool(address and address not in {"none", "off", "(null)"})


def active_network_services(*, runner: CommandRunner = _default_runner) -> list[str]:
    """Return active services, falling back to all services when detection is inconclusive."""
    services = list_network_services(runner=runner)
    active = [service for service in services if service_has_address(service, runner=runner)]
    return active or services


def _unique_services(services: Iterable[str]) -> list[str]:
    """Normalize service names while preserving the user's order."""
    result: list[str] = []
    seen: set[str] = set()
    for item in services:
        name = str(item).strip()
        if name and name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _proxy_command(proxy_type: str) -> str:
    return {
        "web": "-getwebproxy",
        "secureweb": "-getsecurewebproxy",
        "socksfirewall": "-getsocksfirewallproxy",
    }[proxy_type]


def read_service_state(service: str, *, runner: CommandRunner = _default_runner) -> ProxyServiceState:
    auto = parse_key_value_output(
        _run([NETWORKSETUP, "-getautoproxyurl", service], runner=runner, check=False)
    )
    raw: dict[str, str] = {f"auto.{key}": value for key, value in auto.items()}
    manual_enabled: dict[str, bool] = {}
    for proxy_type in MANUAL_PROXY_TYPES:
        values = parse_key_value_output(
            _run([NETWORKSETUP, _proxy_command(proxy_type), service], runner=runner, check=False)
        )
        manual_enabled[proxy_type] = parse_bool(values.get("Enabled"))
        raw.update({f"{proxy_type}.{key}": value for key, value in values.items()})
    return ProxyServiceState(
        name=service,
        auto_enabled=parse_bool(auto.get("Enabled")),
        auto_url=auto.get("URL", "") if auto.get("URL", "") not in {"(null)", "None"} else "",
        manual_enabled=manual_enabled,
        raw=raw,
    )


def set_auto_proxy(service: str, pac_url: str, *, runner: CommandRunner = _default_runner) -> None:
    _run([NETWORKSETUP, "-setautoproxyurl", service, pac_url], runner=runner)
    _run([NETWORKSETUP, "-setautoproxystate", service, "on"], runner=runner)
    # PAC must be authoritative while the tool is running. Manual proxy values
    # remain untouched and are restored to their original enabled state later.
    for proxy_type in MANUAL_PROXY_TYPES:
        _run(
            [NETWORKSETUP, MANUAL_PROXY_STATE_COMMANDS[proxy_type], service, "off"],
            runner=runner,
        )


def restore_service_state(state: ProxyServiceState, *, runner: CommandRunner = _default_runner) -> None:
    # `networksetup -setautoproxyurl SERVICE ""` is rejected by recent macOS
    # versions. An empty URL means that no PAC URL was configured, so disabling
    # the auto-proxy state is the correct and safe restoration on those systems.
    if state.auto_url:
        _run([NETWORKSETUP, "-setautoproxyurl", state.name, state.auto_url], runner=runner)
    _run(
        [NETWORKSETUP, "-setautoproxystate", state.name, "on" if state.auto_enabled else "off"],
        runner=runner,
    )
    for proxy_type, enabled in state.manual_enabled.items():
        _run(
            [
                NETWORKSETUP,
                MANUAL_PROXY_STATE_COMMANDS[proxy_type],
                state.name,
                "on" if enabled else "off",
            ],
            runner=runner,
        )


def save_snapshot(path: Path, snapshot: ProxySnapshot) -> None:
    """Atomically persist a proxy snapshot with restrictive permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(snapshot.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def load_snapshot(path: Path) -> ProxySnapshot:
    return ProxySnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))


class MacOSProxyBackend:
    """Manage only the network services selected for this WxArticleSaver run."""

    def __init__(self, *, runner: CommandRunner = _default_runner):
        self.runner = runner

    def select_services(self, requested: Iterable[str] | None = None) -> list[str]:
        requested_list = _unique_services(requested or [])
        if requested_list:
            known = set(list_network_services(runner=self.runner))
            unknown = [item for item in requested_list if item not in known]
            if unknown:
                raise NetworkSetupError("找不到 macOS 网络服务：" + ", ".join(unknown))
            return requested_list
        env_services = _unique_services(
            item for item in os.environ.get("WXAS_NETWORK_SERVICES", "").split(",") if item.strip()
        )
        return env_services or active_network_services(runner=self.runner)

    def snapshot(self, services: Iterable[str], pac_url: str) -> ProxySnapshot:
        return ProxySnapshot(
            pac_url=pac_url,
            services=[read_service_state(service, runner=self.runner) for service in services],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def apply(self, snapshot: ProxySnapshot) -> None:
        applied: list[ProxyServiceState] = []
        try:
            for state in snapshot.services:
                # Record the service before changing it so a failure midway through
                # its setter sequence also triggers restoration of that service.
                applied.append(state)
                set_auto_proxy(state.name, snapshot.pac_url, runner=self.runner)
        except Exception:
            for state in reversed(applied):
                try:
                    restore_service_state(state, runner=self.runner)
                except Exception:
                    pass
            raise

    def restore(self, snapshot: ProxySnapshot) -> list[str]:
        errors = []
        for state in snapshot.services:
            try:
                restore_service_state(state, runner=self.runner)
            except Exception as exc:
                errors.append(f"{state.name}: {exc}")
        return errors
