# SPDX-License-Identifier: AGPL-3.0-only
"""
WxArticleSaver - Windows Portable Package Builder
Builds a lean, clean standalone distribution bundling Python embeddable runtime.
Zero Python installation required for end-users.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

# Force UTF-8 on Windows stdout/stderr to prevent encoding crashes on CI.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PYTHON_VERSION = "3.12.8"
REQUIRED_BUILD_PYTHON = (3, 12)
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
DIST_DIR = ROOT / "dist"
CACHE_DIR = ROOT / "build_cache"
TEMP_DIR = DIST_DIR / "_build_temp"
PORTABLE_DIR = DIST_DIR / "WxArticleSaver"
RUNTIME_DIR = PORTABLE_DIR / "runtime"
SITE_PACKAGES = RUNTIME_DIR / "Lib" / "site-packages"


def log(msg):
    print(f"[build] {msg}", flush=True)


def fail(msg):
    print(f"\n[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def validate_build_python():
    current = (sys.version_info.major, sys.version_info.minor)
    if current != REQUIRED_BUILD_PYTHON:
        fail(
            "Windows portable builds must run under Python 3.12. "
            f"Current interpreter: {sys.version.split()[0]} ({sys.executable})\n"
            "Use: py -3.12 scripts/build-windows.py"
        )


def safe_remove(path):
    p = Path(path)
    if not p.exists():
        return
    for _ in range(5):
        try:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            return
        except Exception:
            time.sleep(0.5)


def download_file(url, dest_path, retries=3):
    dest = Path(dest_path)
    if dest.exists() and dest.stat().st_size > 1024:
        log(f"Using cached: {dest.name}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries + 1):
        log(f"Downloading: {url} (attempt {attempt}/{retries})")
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
            log(f"Downloaded {dest.name} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")
            return
        except Exception as e:
            log(f"Download failed on attempt {attempt}: {e}")
            if dest.exists():
                dest.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(2)
            else:
                fail(f"Failed to download {url}: {e}")


def trim_runtime_size():
    """Strip unnecessary development and metadata files to minimize package size."""
    log("Trimming unused files from runtime (tests, docs, pycache)...")
    patterns_to_remove = ["__pycache__", "tests", "test", "testing", "idlelib", "tkinter", "turtledemo"]
    for dir_path in RUNTIME_DIR.rglob("*"):
        if dir_path.is_dir() and dir_path.name.lower() in patterns_to_remove:
            shutil.rmtree(dir_path, ignore_errors=True)

    extensions_to_remove = {".pyi", ".c", ".h", ".pdb", ".exe.manifest"}
    for file_path in RUNTIME_DIR.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in extensions_to_remove:
            file_path.unlink(missing_ok=True)


def create_clean_zip(source_dir, output_zip_path):
    source_path = Path(source_dir)
    target_path = Path(output_zip_path)

    if target_path.exists():
        try:
            target_path.unlink()
        except OSError:
            log(f"Target {target_path.name} is in use; creating timestamped package...")
            target_path = target_path.parent / f"{target_path.stem}_{int(time.time())}.zip"

    with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(source_path):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(source_path.parent)
                zf.write(full_path, rel_path)
    return target_path


def main():
    validate_build_python()

    manifest_file = ROOT / "manifest.json"
    if not manifest_file.exists():
        fail("manifest.json not found")
    with open(manifest_file, "r", encoding="utf-8") as f:
        version = json.load(f).get("version", "1.0.0")

    zip_name = f"WxArticleSaver-v{version}-Windows-x64.zip"
    zip_output = DIST_DIR / zip_name

    print("=" * 60)
    print(f" WxArticleSaver v{version} - Clean Portable Builder")
    print(f" Build Python:      {sys.version.split()[0]}")
    print(f" Python Embeddable: {PYTHON_VERSION}")
    print("=" * 60)

    log("Cleaning previous build folder...")
    safe_remove(PORTABLE_DIR)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    PORTABLE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SITE_PACKAGES.mkdir(parents=True, exist_ok=True)

    py_zip_url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
    py_zip_path = CACHE_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    download_file(py_zip_url, py_zip_path)

    log("Extracting Python embeddable to runtime/...")
    with zipfile.ZipFile(py_zip_path, "r") as zf:
        zf.extractall(RUNTIME_DIR)

    log("Configuring runtime environment (._pth)...")
    pth_files = list(RUNTIME_DIR.glob("python*._pth"))
    if not pth_files:
        fail("No ._pth file found in runtime directory")
    pth_file = pth_files[0]
    pth_file.write_text("python312.zip\n.\nLib/site-packages\nimport site\n", encoding="utf-8")

    req_file = ROOT / "requirements.txt"
    log("Installing dependencies directly into runtime/Lib/site-packages...")
    dep_cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(SITE_PACKAGES),
        "--no-user",
        "--disable-pip-version-check",
        "-r",
        str(req_file),
        "-i",
        "https://pypi.tuna.tsinghua.edu.cn/simple",
    ]
    res = subprocess.run(dep_cmd)
    if res.returncode != 0:
        log("Tsinghua mirror failed, retrying with default PyPI...")
        res = subprocess.run([
            sys.executable,
            "-m",
            "pip",
            "install",
            "--target",
            str(SITE_PACKAGES),
            "--no-user",
            "--disable-pip-version-check",
            "-r",
            str(req_file),
        ])
        if res.returncode != 0:
            fail("Failed to install project dependencies into runtime")

    target_bin = SITE_PACKAGES / "bin"
    scripts_dir = RUNTIME_DIR / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    if target_bin.exists():
        for item in target_bin.iterdir():
            shutil.copy2(item, scripts_dir / item.name)

    trim_runtime_size()

    log("Compiling WxArticleSaver.exe stub launcher...")
    stub_py = SCRIPTS_DIR / "stub.py"
    subprocess.run([
        sys.executable,
        "-m",
        "pip",
        "install",
        "pyinstaller",
        "--quiet",
        "--disable-pip-version-check",
    ], check=True)

    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--name",
        "WxArticleSaver",
        "--distpath",
        str(PORTABLE_DIR),
        "--workpath",
        str(TEMP_DIR / "pyinstaller_work"),
        "--specpath",
        str(TEMP_DIR),
        str(stub_py),
    ]
    res = subprocess.run(pyinstaller_cmd)
    if res.returncode != 0:
        fail("PyInstaller build failed")

    exe_path = PORTABLE_DIR / "WxArticleSaver.exe"
    if not exe_path.exists():
        fail("WxArticleSaver.exe was not created")

    log("Copying minimal application files...")
    runtime_files = [
        "launcher.py",
        "wx_article_saver.py",
        "restore_proxy.bat",
        "restore_proxy.py",
        "remove_certificate.bat",
        "remove_certificate.py",
        "diagnose.bat",
        "LICENSE",
    ]
    for filename in runtime_files:
        src = ROOT / filename
        if src.exists():
            shutil.copy2(src, PORTABLE_DIR / filename)
            log(f"  + {filename}")

    readme_txt = PORTABLE_DIR / "使用说明.txt"
    readme_txt.write_text(
        "WxArticleSaver 使用说明\n"
        "========================\n\n"
        "1. 启动工具：\n"
        "   双击【WxArticleSaver.exe】打开程序（运行时请保持黑色窗口开启）。\n\n"
        "2. 导出文章：\n"
        "   打开微信电脑版，进入公众号文章，点击右下角绿色【导出本文】按钮。\n"
        "   - 如果没看到按钮：在文章页面内按 Ctrl+R 或右键选择【刷新】。\n"
        "   - 如果文章包含视频：建议先播放几秒再点击导出。\n\n"
        "3. 查看导出文件：\n"
        "   导出的 Markdown、HTML、TXT、图片与视频默认保存在【exports】文件夹中。\n\n"
        "4. 退出程序：\n"
        "   推荐回到黑色窗口按 Ctrl+C 正常退出，并等待代理与证书清理完成。\n"
        "   请尽量不要直接点击窗口右上角 X 强制关闭。\n"
        "   如遇异常退出或网络异常，双击运行 restore_proxy.bat 恢复代理。\n",
        encoding="utf-8",
    )
    log("  + UserGuide.txt")

    log("Creating clean portable archive...")
    final_zip = create_clean_zip(PORTABLE_DIR, zip_output)
    safe_remove(TEMP_DIR)

    size_mb = final_zip.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print(" Clean portable build succeeded!")
    print(f" Output: {final_zip}")
    print(f" Size:   {size_mb:.1f} MB")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
