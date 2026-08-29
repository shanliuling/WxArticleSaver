#!/bin/zsh
set -e
cd "${0:A:h}"
exec python3 - <<'PY'
from pathlib import Path
from proxy_backend_macos import MacOSProxyBackend, load_snapshot

backup = Path("proxy_backup_macos.json")
if not backup.exists():
    print("没有找到 proxy_backup_macos.json，没有需要恢复的代理备份。")
    raise SystemExit(0)

snapshot = load_snapshot(backup)
errors = MacOSProxyBackend().restore(snapshot)
if errors:
    print("代理恢复不完整：")
    print("\n".join(errors))
    raise SystemExit(1)
backup.unlink(missing_ok=True)
print("macOS 系统代理已恢复。")
PY
