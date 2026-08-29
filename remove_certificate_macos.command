#!/bin/zsh
set -e
cd "${0:A:h}"
exec python3 - <<'PY'
from pathlib import Path
from certificate_macos import CertificateError, remove_certificate

cert = Path(".wxas_ca/mitmproxy-ca-cert.cer")
try:
    remove_certificate(cert)
except CertificateError as exc:
    print(f"证书清理失败：{exc}")
    raise SystemExit(1)
print("本工具生成的 CA 已从 Login Keychain 中删除。")
PY
