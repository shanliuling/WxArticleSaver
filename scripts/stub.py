# SPDX-License-Identifier: AGPL-3.0-only
"""
WxArticleSaver portable launcher stub.
Compiled to WxArticleSaver.exe via PyInstaller.
Only uses stdlib — zero third-party imports.
"""
import os
import sys
import subprocess


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

    return subprocess.call([python, "-u", launcher], cwd=root)


if __name__ == "__main__":
    sys.exit(main() or 0)
