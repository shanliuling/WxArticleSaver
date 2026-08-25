# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path

if os.name != "nt":
    raise SystemExit("仅 Windows")

ROOT = Path(__file__).resolve().parent
cert = ROOT / ".wxas_ca" / "mitmproxy-ca-cert.cer"

if not cert.exists():
    print("没有找到本工具生成的证书文件。")
    input("按回车退出…")
    raise SystemExit(0)

# Read exact thumbprint from the certificate file and remove only that cert
# from the current user's Trusted Root store.
cert_ps_path = str(cert).replace("'", "''")
ps = rf"""
$p='{cert_ps_path}';
$c=New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($p);
$t=$c.Thumbprint;
$target="Cert:\CurrentUser\Root\$t";
if (Test-Path $target) {{
  Remove-Item $target -Force;
  Write-Output "REMOVED:$t";
}} else {{
  Write-Output "NOT_FOUND:$t";
}}
"""
r = subprocess.run(
    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
    text=True,
    capture_output=True,
)
print(r.stdout.strip())
if r.returncode != 0:
    print(r.stderr.strip())
else:
    print("已处理本工具自己的根证书，不会删除其他证书。")
input("按回车退出…")
