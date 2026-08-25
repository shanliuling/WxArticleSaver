# SPDX-License-Identifier: AGPL-3.0-only
"""
WxArticleSaver portable launcher stub.
Compiled to WxArticleSaver.exe via PyInstaller.
Only uses stdlib — zero third-party imports.
"""
import os
import signal
import subprocess
import sys


def main():
    root = os.path.dirname(
        sys.executable if getattr(sys, "frozen", False)
        else os.path.abspath(__file__)
    )
    python = os.path.join(root, "runtime", "python.exe")
    launcher = os.path.join(root, "launcher.py")

    if not os.path.isfile(python):
        print(f"[错误] 找不到内置 Python: {python}")
        print("请确保 runtime 文件夹与 WxArticleSaver.exe 在同一目录下。")
        input("按回车退出…")
        return 1

    if not os.path.isfile(launcher):
        print(f"[错误] 找不到 launcher.py: {launcher}")
        input("按回车退出…")
        return 1

    cleanup_notice_shown = False

    def on_ctrl_c(signum, frame):
        nonlocal cleanup_notice_shown
        # The child Python process shares the same Windows console and receives
        # Ctrl+C as well. launcher.py handles KeyboardInterrupt and performs the
        # proxy/certificate cleanup. The stub must stay alive while that happens.
        if not cleanup_notice_shown:
            cleanup_notice_shown = True
            print("\n正在停止 WxArticleSaver，请等待代理和证书清理完成…", flush=True)

    signal.signal(signal.SIGINT, on_ctrl_c)

    proc = subprocess.Popen([python, "-u", launcher], cwd=root)
    return proc.wait()


if __name__ == "__main__":
    sys.exit(main() or 0)
