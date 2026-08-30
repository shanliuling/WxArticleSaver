#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# -*- coding: utf-8 -*-
"""Build an unsigned or signed arm64 macOS app and DMG for WxArticleSaver."""

from __future__ import annotations

import argparse
import hashlib
import os
import plistlib
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "macos"
DIST_ROOT = ROOT / "dist"
APP_NAME = "WxArticleSaver.app"
BUNDLE_ID = "com.wxarticlesaver.macos"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(str(item) for item in command))
    subprocess.run(command, cwd=cwd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build WxArticleSaver.app and a macOS DMG")
    parser.add_argument(
        "--sign-identity",
        help="codesign identity; omit to produce an unsigned test build",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="do not install PyInstaller into the current Python environment",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DIST_ROOT,
        help="output directory (default: dist)",
    )
    return parser.parse_args()


def ensure_macos() -> None:
    if sys.platform != "darwin":
        raise SystemExit("macOS DMG 只能在 macOS 上构建。")
    if platform.machine() != "arm64":
        raise SystemExit(
            f"当前构建脚本首版只支持 Apple Silicon arm64，检测到：{platform.machine()}"
        )


def ensure_pyinstaller(skip_install: bool) -> None:
    if shutil.which("pyinstaller") or _module_available("PyInstaller"):
        return
    if skip_install:
        raise SystemExit("未找到 PyInstaller，请先执行：python3 -m pip install pyinstaller")
    run([sys.executable, "-m", "pip", "install", "pyinstaller", "--disable-pip-version-check"])


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True


def write_info_plist(path: Path) -> None:
    info = {
        "CFBundleDisplayName": "WxArticleSaver",
        "CFBundleExecutable": "WxArticleSaver",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleName": "WxArticleSaver",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0.0-macos",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
    }
    with path.open("wb") as handle:
        plistlib.dump(info, handle, sort_keys=True)


def write_terminal_launcher(path: Path) -> None:
    path.write_text(
        '''#!/bin/zsh\nset -e\n\nAPP_ROOT="${0:A:h:h}"\nRUNNER="$APP_ROOT/Resources/wxas-runner"\n\nif [[ ! -x "$RUNNER" ]]; then\n  /usr/bin/osascript -e 'display alert "WxArticleSaver 启动失败" message "找不到应用程序组件，请重新下载或重新挂载 DMG。" as critical'\n  exit 1\nfi\n\n/usr/bin/osascript - "$RUNNER" <<'APPLESCRIPT'\non run argv\n    set runnerPath to item 1 of argv\n    tell application "Terminal"\n        activate\n        do script "exec " & quoted form of runnerPath\n    end tell\nend run\nAPPLESCRIPT\n''',
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_resource_commands(resources: Path) -> None:
    restore = resources / "恢复代理.command"
    restore.write_text(
        '''#!/bin/zsh\nset -e\nRUNNER="${0:A:h}/wxas-runner"\nexec "$RUNNER" --restore-only\n''',
        encoding="utf-8",
    )
    restore.chmod(0o755)
    remove = resources / "清理证书.command"
    remove.write_text(
        '''#!/bin/zsh\nset -e\nRUNNER="${0:A:h}/wxas-runner"\nexec "$RUNNER" --remove-certificate\n''',
        encoding="utf-8",
    )
    remove.chmod(0o755)


def build_runner(temp_root: Path) -> Path:
    runner_dist = temp_root / "runner-dist"
    runner_work = temp_root / "runner-work"
    runner_spec = temp_root / "runner-spec"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--name",
        "wxas-runner",
        "--distpath",
        str(runner_dist),
        "--workpath",
        str(runner_work),
        "--specpath",
        str(runner_spec),
        "--collect-all",
        "mitmproxy",
        # wx_article_saver.py is loaded by mitmdump with -s at runtime, so
        # PyInstaller cannot discover its addon dependencies from the import
        # graph. Keep these modules in the frozen runner explicitly.
        "--hidden-import",
        "bs4",
        "--hidden-import",
        "markdownify",
        "--hidden-import",
        "requests",
        "--add-data",
        f"{ROOT / 'wx_article_saver.py'}:.",
        str(ROOT / "scripts" / "macos_runner.py"),
    ]
    run(command, cwd=ROOT)
    runner = runner_dist / "wxas-runner"
    if not runner.exists():
        raise SystemExit(f"PyInstaller 未生成 runner：{runner}")
    return runner


def create_app(runner: Path, app_path: Path) -> None:
    contents = app_path / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runner, resources / "wxas-runner")
    (resources / "wxas-runner").chmod(0o755)
    write_info_plist(contents / "Info.plist")
    write_terminal_launcher(macos_dir / "WxArticleSaver")
    write_resource_commands(resources)
    shutil.copy2(ROOT / "LICENSE", resources / "LICENSE")
    (resources / "使用说明.txt").write_text(
        "WxArticleSaver macOS 使用说明\n\n"
        "1. 双击 WxArticleSaver.app，终端窗口会显示启动状态。\n"
        "2. 首次运行按提示将 CA 导入 Login Keychain，并设置为 Always Trust。\n"
        "3. 完全退出并重新打开微信 Mac，打开公众号文章；没有按钮时按 ⌘R。\n"
        "4. 点击“导出本文”，文件位于 ~/Library/Application Support/WxArticleSaver/exports。\n"
        "5. 停止时回到终端按 Ctrl+C，等待代理恢复。\n\n"
        "异常恢复：双击 Resources/恢复代理.command。\n"
        "清理证书：双击 Resources/清理证书.command。\n\n"
        "这是未签名测试版本。首次打开若出现“无法验证开发者”，请右键 App → 打开。\n",
        encoding="utf-8",
    )


def make_dmg(app_path: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    dmg_path = output_dir / "WxArticleSaver-macos-arm64.dmg"
    with tempfile.TemporaryDirectory(prefix="wxas-dmg-") as temp_name:
        staging = Path(temp_name) / "WxArticleSaver"
        staging.mkdir()
        shutil.copytree(app_path, staging / APP_NAME)
        (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
        run(
            [
                "/usr/bin/hdiutil",
                "create",
                "-volname",
                "WxArticleSaver",
                "-srcfolder",
                str(staging),
                "-ov",
                "-format",
                "UDZO",
                str(dmg_path),
            ]
        )
    return dmg_path


def maybe_sign(app_path: Path, identity: str | None) -> None:
    if not identity:
        print("警告：未指定 Developer ID，生成的是未签名 DMG。")
        return
    run(["/usr/bin/codesign", "--deep", "--force", "--options", "runtime", "--sign", identity, str(app_path)])
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app_path)])


def write_checksum(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    checksum = path.with_name(path.name + ".sha256")
    checksum.write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    ensure_macos()
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    # Keep PyInstaller's cache inside the repository build directory. This makes
    # the build reproducible in restricted environments and avoids writing to
    # ~/Library/Application Support, which may require extra permissions.
    os.environ.setdefault("PYINSTALLER_CONFIG_DIR", str(BUILD_ROOT / "pyinstaller-config"))
    ensure_pyinstaller(args.skip_install)
    output_dir = args.output_dir.expanduser().resolve()
    app_path = BUILD_ROOT / APP_NAME
    if app_path.exists():
        shutil.rmtree(app_path)
    with tempfile.TemporaryDirectory(prefix="wxas-build-") as temp_name:
        runner = build_runner(Path(temp_name))
        create_app(runner, app_path)
    maybe_sign(app_path, args.sign_identity)
    dmg = make_dmg(app_path, output_dir)
    write_checksum(dmg)
    print("\n构建完成：")
    print(f"App：{app_path}")
    print(f"DMG：{dmg}")
    print(f"SHA-256：{dmg.with_name(dmg.name + '.sha256')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
