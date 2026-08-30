# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""WxArticleSaver macOS launcher (experimental source-runner)."""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from certificate_macos import (
    CertificateError,
    certificate_fingerprint,
    remove_certificate,
    trust_instructions,
)
from macos_paths import data_root
from proxy_backend_macos import (
    MacOSProxyBackend,
    NetworkSetupError,
    ProxySnapshot,
    load_snapshot,
    save_snapshot,
)

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
DATA_ROOT = data_root()
LOG = DATA_ROOT / "run_macos.log"
CONFDIR = DATA_ROOT / ".wxas_ca"
EXPORTS = DATA_ROOT / "exports"
BACKUP = DATA_ROOT / "proxy_backup_macos.json"
PORT = 8899
PAC_PORT = 8898


def pac_payload(proxy_port: int) -> bytes:
    return (
        "function FindProxyForURL(url, host) {\n"
        "  host = host.toLowerCase();\n"
        '  if (host === "mp.weixin.qq.com" ||\n'
        '      host === "findermp.video.qq.com" ||\n'
        '      host === "mpvideo.qpic.cn" ||\n'
        '      dnsDomainIs(host, ".video.qq.com") ||\n'
        '      dnsDomainIs(host, ".vod.tencent-cloud.com")) {\n'
        f'    return "PROXY 127.0.0.1:{proxy_port}";\n'
        "  }\n"
        '  return "DIRECT";\n'
        "}\n"
    ).encode("utf-8")


def make_pac_handler(proxy_port: int):
    class PacHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if urlsplit(self.path).path != "/proxy.pac":
                self.send_response(404)
                self.end_headers()
                return
            payload = pac_payload(proxy_port)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt, *args):
            return

    return PacHandler


def start_pac_server(pac_port: int, proxy_port: int) -> ThreadingHTTPServer:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", pac_port), make_pac_handler(proxy_port))
    except OSError as exc:
        fail(f"无法启动本地 PAC 服务 127.0.0.1:{pac_port}：{exc}", 15)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def log(message: str = "") -> None:
    print(message, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    except OSError:
        pass


def fail(message: str, code: int = 1) -> None:
    log(f"[错误] {message}")
    raise SystemExit(code)


def ensure_mitmdump() -> list[str]:
    # A PyInstaller one-file executable is not a Python interpreter. In frozen
    # mode, route mitmdump back through the runner's explicit dispatch path
    # instead of trying to execute `wxas-runner -c ...`.
    if getattr(sys, "frozen", False):
        return [sys.executable, "--mitmdump"]

    executable = shutil.which("mitmdump")
    if executable:
        return [executable]
    if importlib.util.find_spec("mitmproxy") is not None:
        code = "from mitmproxy.tools.main import mitmdump; mitmdump()"
        return [sys.executable, "-c", code]
    fail(
        "没有找到 mitmdump 或 mitmproxy。请先执行：python3 -m pip install -r requirements.txt",
        20,
    )


def wait_for_file(path: Path, process: subprocess.Popen, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            break
        time.sleep(0.2)
    output = ""
    try:
        output = (process.communicate(timeout=1)[0] or "")[-3000:]
    except Exception:
        pass
    raise RuntimeError(f"代理证书生成失败。\n{output}")


def ensure_ca(mitmdump: list[str], port: int) -> Path:
    CONFDIR.mkdir(exist_ok=True)
    cert = CONFDIR / "mitmproxy-ca-cert.cer"
    if cert.exists():
        return cert
    process = subprocess.Popen(
        mitmdump
        + [
            "--set",
            f"confdir={CONFDIR}",
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(port),
            "--set",
            "block_global=false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        wait_for_file(cert, process)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
    return cert


def restore_saved_proxy(backend: MacOSProxyBackend) -> None:
    if not BACKUP.exists():
        return
    try:
        snapshot = load_snapshot(BACKUP)
    except Exception as exc:
        log(f"[警告] 无法读取遗留代理备份：{exc}")
        return
    errors = backend.restore(snapshot)
    if errors:
        log("[警告] 遗留代理备份恢复不完整：" + "；".join(errors))
    else:
        BACKUP.unlink(missing_ok=True)
        log("[恢复] 已恢复上次遗留的 macOS 代理配置。")


def terminate_process(process: subprocess.Popen | None) -> None:
    if not process or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WxArticleSaver macOS source runner")
    parser.add_argument(
        "--service",
        action="append",
        default=[],
        help="指定 macOS 网络服务，可重复传入；默认使用当前有 IP 的服务",
    )
    parser.add_argument("--port", type=int, default=PORT, help="mitmproxy 端口")
    parser.add_argument("--pac-port", type=int, default=PAC_PORT, help="PAC 服务端口")
    parser.add_argument(
        "--restore-only",
        action="store_true",
        help="只恢复上次保存的 macOS 代理配置，不启动代理",
    )
    parser.add_argument(
        "--remove-certificate",
        action="store_true",
        help="按指纹清理本工具生成的 Login Keychain 证书，不启动代理",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    if sys.platform != "darwin":
        fail("launcher_macos.py 只能在 macOS 上运行。")

    args = parse_args(argv)
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    LOG.write_text(
        f"WxArticleSaver macOS start: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Python: {sys.version}\nExecutable: {sys.executable}\n",
        encoding="utf-8",
    )
    backend = MacOSProxyBackend()
    pac_server = None
    mitm_process = None
    snapshot: ProxySnapshot | None = None
    try:
        if args.restore_only:
            restore_saved_proxy(backend)
            return 0
        if args.remove_certificate:
            cert = CONFDIR / "mitmproxy-ca-cert.cer"
            if not cert.exists():
                log(f"[提示] 未找到证书：{cert}")
                return 0
            remove_certificate(cert)
            log("[完成] 已从 Login Keychain 清理 WxArticleSaver 证书。")
            return 0

        restore_saved_proxy(backend)
        mitmdump = ensure_mitmdump()
        cert = ensure_ca(mitmdump, args.port + 1)
        fingerprint = certificate_fingerprint(cert)
        log(trust_instructions(cert, fingerprint))

        pac_server = start_pac_server(args.pac_port, args.port)
        pac_url = f"http://127.0.0.1:{args.pac_port}/proxy.pac"
        services = backend.select_services(args.service)
        if not services:
            fail("没有找到可配置的 macOS 网络服务。", 16)
        log("[代理] 将修改网络服务：" + ", ".join(services))
        snapshot = backend.snapshot(services, pac_url)
        save_snapshot(BACKUP, snapshot)
        backend.apply(snapshot)

        EXPORTS.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["WXAS_EXPORT_DIR"] = str(EXPORTS)
        command = mitmdump + [
            "--set",
            f"confdir={CONFDIR}",
            "--listen-host",
            "127.0.0.1",
            "--listen-port",
            str(args.port),
            "--set",
            "block_global=false",
            "-s",
            str(ROOT / "wx_article_saver.py"),
        ]
        mitm_process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        log("[完成] WxArticleSaver macOS 已启动。")
        log("1. 请确认上面的 CA 已在 Login Keychain 中设为 Always Trust。")
        log("2. 完全退出并重新打开微信 Mac。")
        log("3. 打开可正常阅读的公众号文章；没有按钮时手动按 ⌘R。")
        log("4. 停止程序请回到此窗口按 Ctrl+C，等待代理恢复完成。")
        for line in mitm_process.stdout or []:
            log(line.rstrip("\r\n"))
        return mitm_process.wait()
    except KeyboardInterrupt:
        log("正在停止 WxArticleSaver macOS…")
        return 0
    except (CertificateError, NetworkSetupError, RuntimeError) as exc:
        log(f"[错误] {exc}")
        return 1
    finally:
        terminate_process(mitm_process)
        if snapshot is not None:
            errors = backend.restore(snapshot)
            if errors:
                log("[警告] macOS 代理恢复不完整：" + "；".join(errors))
            else:
                BACKUP.unlink(missing_ok=True)
                log("[恢复] macOS 系统代理已恢复。")
        if pac_server is not None:
            pac_server.shutdown()
            pac_server.server_close()
            log("[恢复] PAC 服务已停止。")


if __name__ == "__main__":
    raise SystemExit(main())
