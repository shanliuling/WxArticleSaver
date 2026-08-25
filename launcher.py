# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""
WxArticleSaver v1.0.0 - Windows launcher

Security model:
- A local PAC file routes ONLY mp.weixin.qq.com to mitmproxy.
- Every other host goes DIRECT and does not enter mitmproxy at all.
- The generated CA is trusted only while the tool is running and removed on exit.
"""

import ctypes
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import importlib.util
import sysconfig
import site
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "run.log"
CONFDIR = ROOT / ".wxas_ca"
EXPORTS = ROOT / "exports"
BACKUP = ROOT / "proxy_backup.json"
PORT = 8899
PAC_PORT = 8898
KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

def log(msg=""):
    s = str(msg)
    print(s, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass

def fail(msg, code=1):
    log("")
    log("[错误] " + str(msg))
    log("")
    log("错误详情已经写入 run.log")
    try:
        input("按回车退出…")
    except Exception:
        pass
    raise SystemExit(code)

if os.name != "nt":
    fail("当前版本仅支持 Windows 10 / 11。")

import winreg

def wininet_refresh():
    try:
        f = ctypes.windll.Wininet.InternetSetOptionW
        f(0, 39, 0, 0)
        f(0, 37, 0, 0)
    except Exception as e:
        log(f"[警告] WinINet 刷新失败: {e}")

def read_value(key, name):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None

def current_proxy_state():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY_PATH, 0, winreg.KEY_READ) as key:
        return {
            "ProxyEnable": read_value(key, "ProxyEnable"),
            "ProxyServer": read_value(key, "ProxyServer"),
            "ProxyOverride": read_value(key, "ProxyOverride"),
            "AutoConfigURL": read_value(key, "AutoConfigURL"),
        }

def set_or_delete(key, name, value, regtype):
    if value is None:
        try:
            winreg.DeleteValue(key, name)
        except OSError:
            pass
    else:
        winreg.SetValueEx(key, name, 0, regtype, value)

def restore_proxy_from_backup():
    if not BACKUP.exists():
        return False
    try:
        state = json.loads(BACKUP.read_text(encoding="utf-8"))
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            set_or_delete(key, "ProxyEnable", state.get("ProxyEnable"), winreg.REG_DWORD)
            set_or_delete(key, "ProxyServer", state.get("ProxyServer"), winreg.REG_SZ)
            set_or_delete(key, "ProxyOverride", state.get("ProxyOverride"), winreg.REG_SZ)
            set_or_delete(key, "AutoConfigURL", state.get("AutoConfigURL"), winreg.REG_SZ)
        wininet_refresh()
        BACKUP.unlink(missing_ok=True)
        return True
    except Exception as e:
        log(f"[警告] 自动恢复旧代理失败: {e}")
        return False

class PacHandler(BaseHTTPRequestHandler):
    PAC = (
        'function FindProxyForURL(url, host) {\n'
        '  host = host.toLowerCase();\n'
        '  if (host === "mp.weixin.qq.com" ||\n'
        '      host === "findermp.video.qq.com" ||\n'
        '      host === "mpvideo.qpic.cn" ||\n'
        '      dnsDomainIs(host, ".video.qq.com") ||\n'
        '      dnsDomainIs(host, ".vod.tencent-cloud.com")) {\n'
        f'    return "PROXY 127.0.0.1:{PORT}";\n'
        '  }\n'
        '  return "DIRECT";\n'
        '}\n'
    ).encode("utf-8")

    def do_GET(self):
        if self.path.startswith("/proxy.pac"):
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Content-Length", str(len(self.PAC)))
            self.end_headers()
            self.wfile.write(self.PAC)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return

def start_pac_server():
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PAC_PORT), PacHandler)
    except OSError as e:
        fail(f"无法启动本地 PAC 服务 127.0.0.1:{PAC_PORT}: {e}", 15)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server

def backup_and_enable_proxy():
    state = current_proxy_state()
    BACKUP.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    pac_url = f"http://127.0.0.1:{PAC_PORT}/proxy.pac"

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, KEY_PATH, 0, winreg.KEY_SET_VALUE
    ) as key:
        # Disable global manual proxy.
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        try:
            winreg.DeleteValue(key, "ProxyServer")
        except OSError:
            pass
        try:
            winreg.DeleteValue(key, "ProxyOverride")
        except OSError:
            pass

        # Enable PAC so only WeChat article traffic enters mitmproxy.
        winreg.SetValueEx(key, "AutoConfigURL", 0, winreg.REG_SZ, pac_url)

    wininet_refresh()
    return state

def ensure_mitmdump():
    candidates = []

    exe = shutil.which("mitmdump")
    if exe:
        candidates.append(Path(exe))

    try:
        scripts = sysconfig.get_path("scripts")
        if scripts:
            candidates.append(Path(scripts) / "mitmdump.exe")
            candidates.append(Path(scripts) / "mitmdump")
    except Exception:
        pass

    try:
        userbase = site.getuserbase()
        if userbase:
            candidates.append(Path(userbase) / "Scripts" / "mitmdump.exe")
            candidates.append(Path(userbase) / "bin" / "mitmdump")
    except Exception:
        pass

    candidates.append(Path(sys.executable).parent / "Scripts" / "mitmdump.exe")

    try:
        usersite = Path(site.getusersitepackages())
        candidates.append(usersite.parent / "Scripts" / "mitmdump.exe")
    except Exception:
        pass

    seen = set()
    for c in candidates:
        try:
            c = c.resolve()
        except Exception:
            pass
        s = str(c).lower()
        if s in seen:
            continue
        seen.add(s)
        if c.exists():
            log(f"找到 mitmdump: {c}")
            return [str(c)]

    if importlib.util.find_spec("mitmproxy") is not None:
        log("mitmdump.exe 不在 PATH，改用当前 Python 直接启动 mitmproxy。")
        code = "from mitmproxy.tools.main import mitmdump; mitmdump()"
        return [sys.executable, "-c", code]

    fail(
        "当前 Python 中没有找到 mitmproxy 包。\n"
        "请重新运行 install_and_run.bat；如果 pip 安装阶段报错，把窗口截图发给我。",
        20,
    )

def ensure_ca(mitmdump):
    log("[1/4] 准备本机证书...")
    CONFDIR.mkdir(exist_ok=True)
    cert = CONFDIR / "mitmproxy-ca-cert.cer"
    if cert.exists():
        return cert

    tmp_port = PORT + 1
    proc = subprocess.Popen(
        mitmdump + [
            "--set", f"confdir={CONFDIR}",
            "--listen-host", "127.0.0.1",
            "--listen-port", str(tmp_port),
            "--set", "block_global=false",
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    for _ in range(40):
        if cert.exists():
            break
        if proc.poll() is not None:
            break
        time.sleep(0.25)

    if not cert.exists():
        try:
            out, _ = proc.communicate(timeout=2)
        except Exception:
            out = ""
        try:
            proc.terminate()
        except Exception:
            pass
        fail("代理证书生成失败。\n" + (out[-3000:] if out else ""), 30)

    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

    return cert

def trust_ca(cert):
    log("[2/4] 配置安全连接...")
    r = subprocess.run(
        ["certutil", "-user", "-addstore", "-f", "Root", str(cert)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode == 0:
        return

    cert_path = str(cert).replace("'", "''")
    ps = (
        f"$p='{cert_path}';"
        "Import-Certificate -FilePath $p "
        "-CertStoreLocation 'Cert:\\CurrentUser\\Root' | Out-Null"
    )
    r2 = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r2.returncode != 0:
        fail("证书安装失败。\n" + r.stdout + r.stderr + "\n" + r2.stdout + r2.stderr, 40)

def remove_own_ca(cert):
    if not cert or not cert.exists():
        return False
    try:
        cert_ps_path = str(cert).replace("'", "''")
        ps = (
            f"$p='{cert_ps_path}';"
            "$c=New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($p);"
            "$t=$c.Thumbprint;"
            "$target=\"Cert:\\CurrentUser\\Root\\$t\";"
            "if (Test-Path $target) { Remove-Item $target -Force }"
        )
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode == 0:
            log("[安全] 已移除本工具临时根证书。")
            return True
        log("[警告] 自动删除证书失败，可运行 remove_certificate.bat。")
        return False
    except Exception as e:
        log(f"[警告] 自动删除证书失败: {e}")
        return False

def main():
    LOG.write_text(
        f"WxArticleSaver v1.0.0 start: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Python: {sys.version}\nExecutable: {sys.executable}\n\n",
        encoding="utf-8",
    )

    log("=" * 62)
    log(" WxArticleSaver v1.0.0")
    log("=" * 62)

    if BACKUP.exists():
        log("[恢复] 发现上次遗留的代理备份，先恢复。")
        restore_proxy_from_backup()

    mitmdump = ensure_mitmdump()

    cert = ensure_ca(mitmdump)
    trust_ca(cert)

    log("[3/4] 启动本地代理...")
    pac_server = start_pac_server()
    old = backup_and_enable_proxy()

    if old.get("ProxyEnable") or old.get("AutoConfigURL"):
        log("检测到原有代理配置，退出时会自动恢复。")

    EXPORTS.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["WXAS_EXPORT_DIR"] = str(EXPORTS)

    cmd = mitmdump + [
        "--set", f"confdir={CONFDIR}",
        "--listen-host", "127.0.0.1",
        "--listen-port", str(PORT),
        "--set", "block_global=false",
        "-s", str(ROOT / "wx_article_saver.py"),
    ]

    log("[4/4] WxArticleSaver 已启动 ✓")
    log("")
    log("使用方法：")
    log("1. 打开微信，进入你可以正常阅读的公众号文章。")
    log("2. 点击文章右下角【导出本文】。")
    log("3. 没看到按钮：按 Ctrl+R，或右键选择【刷新】后重试。")
    log("4. 文章有视频：先播放几秒，再点击导出。")
    log("")
    log("安全：仅处理微信文章相关流量；退出后自动恢复代理并移除受信任根证书。")
    log("停止：回到这个窗口按 Ctrl+C。")
    log("-" * 62)

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        for line in proc.stdout:
            log(line.rstrip("\r\n"))
        return proc.wait()
    except KeyboardInterrupt:
        log("\n正在停止…")
        if proc:
            try:
                proc.terminate()
                proc.wait(timeout=4)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return 0
    finally:
        log("正在恢复 Windows 原系统代理…")
        if restore_proxy_from_backup():
            log("系统代理已恢复。")
        else:
            log("未找到代理备份或自动恢复失败，请运行 restore_proxy.bat。")

        try:
            pac_server.shutdown()
            pac_server.server_close()
            log("PAC 服务已停止。")
        except Exception:
            pass

        log("正在移除本工具临时根证书…")
        remove_own_ca(cert)

if __name__ == "__main__":
    try:
        rc = main()
        log(f"程序退出，代码: {rc}")
        try:
            input("按回车关闭窗口…")
        except Exception:
            pass
        raise SystemExit(rc or 0)
    except SystemExit:
        raise
    except BaseException:
        tb = traceback.format_exc()
        log("")
        log("========== 未处理异常 ==========")
        log(tb)

        try:
            if BACKUP.exists():
                log("检测到代理备份，尝试恢复…")
                restore_proxy_from_backup()
        except Exception:
            log(traceback.format_exc())

        try:
            cert = CONFDIR / "mitmproxy-ca-cert.cer"
            if cert.exists():
                log("异常退出：尝试移除本工具临时根证书…")
                remove_own_ca(cert)
        except Exception:
            log(traceback.format_exc())

        try:
            input("程序发生异常。错误已写入 run.log，按回车退出…")
        except Exception:
            pass
        raise
