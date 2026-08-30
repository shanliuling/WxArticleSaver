# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""macOS Keychain guidance and exact-certificate cleanup helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class CertificateError(RuntimeError):
    """Raised when certificate inspection or cleanup fails."""


def normalize_fingerprint(value: str) -> str:
    return re.sub(r"[^0-9A-Fa-f]", "", value).upper()


def _openssl_fingerprint(
    cert_path: Path, inform: str | None = None, algorithm: str = "sha256"
) -> str:
    command = ["openssl", "x509", "-in", str(cert_path), "-noout", "-fingerprint", f"-{algorithm}"]
    if inform:
        command[2:2] = ["-inform", inform]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    match = re.search(r"Fingerprint\s*=\s*([0-9A-Fa-f:]+)", result.stdout, re.IGNORECASE)
    return normalize_fingerprint(match.group(1)) if match else ""


def certificate_fingerprint(cert_path: Path) -> str:
    """Return the SHA-256 fingerprint for PEM or DER certificate files."""
    if not cert_path.exists():
        raise CertificateError(f"找不到代理证书：{cert_path}")
    fingerprint = _openssl_fingerprint(cert_path)
    if not fingerprint:
        fingerprint = _openssl_fingerprint(cert_path, "DER")
    if not fingerprint:
        raise CertificateError(f"无法读取代理证书指纹：{cert_path}")
    return fingerprint


def login_keychain_path() -> Path:
    return Path.home() / "Library" / "Keychains" / "login.keychain-db"


def trust_instructions(cert_path: Path, fingerprint: str) -> str:
    return (
        "请在微信 Mac 启动前，将下面的 CA 导入当前用户的 Login Keychain，并明确设为信任。\n"
        f"证书路径：{cert_path}\n"
        f"SHA-256 指纹：{fingerprint}\n"
        "操作：双击证书打开 Keychain Access → 选择 Login → 导入后双击该证书 → Trust → "
        "When using this certificate 选择 Always Trust。\n"
        "本工具不会在首版中静默修改 Keychain；完成导出后可运行 remove_certificate_macos.command 清理。"
    )


def open_certificate_in_finder(cert_path: Path) -> None:
    subprocess.run(["open", "-R", str(cert_path)], check=False)


def remove_certificate(cert_path: Path, *, keychain: Path | None = None) -> None:
    fingerprint = certificate_fingerprint(cert_path)
    keychain_path = keychain or login_keychain_path()
    digests = [fingerprint]
    sha1 = _openssl_fingerprint(cert_path, algorithm="sha1")
    if sha1 and sha1 not in digests:
        digests.append(sha1)
    last_detail = ""
    for digest in digests:
        result = subprocess.run(
            ["security", "delete-certificate", "-Z", digest, str(keychain_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        last_detail = (result.stderr or result.stdout).strip()
    raise CertificateError(
        f"从 Login Keychain 删除证书失败：{fingerprint}"
        + (f"\n{last_detail}" if last_detail else "")
    )
