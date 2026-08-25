# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
import ctypes
import json
import os
from pathlib import Path

if os.name != "nt":
    raise SystemExit("仅 Windows")

import winreg

ROOT = Path(__file__).resolve().parent
BACKUP = ROOT / "proxy_backup.json"
KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

def refresh():
    try:
        f = ctypes.windll.Wininet.InternetSetOptionW
        f(0, 39, 0, 0)
        f(0, 37, 0, 0)
    except Exception:
        pass

def set_or_delete(key, name, value, regtype):
    if value is None:
        try:
            winreg.DeleteValue(key, name)
        except OSError:
            pass
    else:
        winreg.SetValueEx(key, name, 0, regtype, value)

if not BACKUP.exists():
    print("没有找到 proxy_backup.json。看起来没有需要恢复的代理备份。")
    input("按回车退出…")
    raise SystemExit(0)

state = json.loads(BACKUP.read_text(encoding="utf-8"))
with winreg.OpenKey(
    winreg.HKEY_CURRENT_USER, KEY_PATH, 0, winreg.KEY_SET_VALUE
) as key:
    set_or_delete(key, "ProxyEnable", state.get("ProxyEnable"), winreg.REG_DWORD)
    set_or_delete(key, "ProxyServer", state.get("ProxyServer"), winreg.REG_SZ)
    set_or_delete(key, "ProxyOverride", state.get("ProxyOverride"), winreg.REG_SZ)
    set_or_delete(key, "AutoConfigURL", state.get("AutoConfigURL"), winreg.REG_SZ)

refresh()
BACKUP.unlink(missing_ok=True)
print("系统代理已恢复。")

# Best-effort remove this tool's exact generated CA as well.
try:
    cert = ROOT / ".wxas_ca" / "mitmproxy-ca-cert.cer"
    if cert.exists():
        cert_ps_path = str(cert).replace("'", "''")
        ps = rf"""
$p='{cert_ps_path}';
$c=New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($p);
$t=$c.Thumbprint;
$target="Cert:\CurrentUser\Root\$t";
if (Test-Path $target) {{ Remove-Item $target -Force }}
"""
        import subprocess
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
        )
        print("本工具根证书也已尝试移除。")
except Exception as e:
    print("证书自动清理失败，可再运行 remove_certificate.bat：", e)

input("按回车退出…")
