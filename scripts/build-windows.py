# SPDX-License-Identifier: AGPL-3.0-only
"""
WxArticleSaver - Windows Portable Package Builder
Builds a standalone portable distribution bundling Python embeddable runtime.
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

PYTHON_VERSION = "3.12.8"
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
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
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

def main():
    manifest_file = ROOT / "manifest.json"
    if not manifest_file.exists():
        fail("manifest.json not found")
    with open(manifest_file, "r", encoding="utf-8") as f:
        version = json.load(f).get("version", "1.0.0")

    zip_name = f"WxArticleSaver-v{version}-Windows-x64.zip"
    zip_output = DIST_DIR / zip_name

    print("=" * 60)
    print(f" WxArticleSaver v{version} - Windows Portable Builder")
    print(f" Python Embeddable: {PYTHON_VERSION}")
    print("=" * 60)

    # 0. Clean old build
    log("Cleaning previous build folder...")
    if PORTABLE_DIR.exists():
        shutil.rmtree(PORTABLE_DIR, ignore_errors=True)
    if zip_output.exists():
        zip_output.unlink(missing_ok=True)
    
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    PORTABLE_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    SITE_PACKAGES.mkdir(parents=True, exist_ok=True)

    # 1. Download Python Embeddable (cached in build_cache)
    py_zip_url = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
    py_zip_path = CACHE_DIR / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    download_file(py_zip_url, py_zip_path)

    log("Extracting Python embeddable to runtime/...")
    with zipfile.ZipFile(py_zip_path, "r") as zf:
        zf.extractall(RUNTIME_DIR)

    # 2. Configure ._pth to include site-packages
    log("Configuring runtime environment (._pth)...")
    pth_files = list(RUNTIME_DIR.glob("python*._pth"))
    if not pth_files:
        fail("No ._pth file found in runtime directory")
    pth_file = pth_files[0]
    
    pth_content = "python312.zip\n.\nLib/site-packages\nimport site\n"
    pth_file.write_text(pth_content, encoding="utf-8")

    # 3. Install dependencies directly into Lib/site-packages
    req_file = ROOT / "requirements.txt"
    log("Installing dependencies directly into runtime/Lib/site-packages...")
    
    dep_cmd = [
        sys.executable, "-m", "pip", "install",
        "--target", str(SITE_PACKAGES),
        "--no-user",
        "--disable-pip-version-check",
        "-r", str(req_file),
        "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"
    ]
    res = subprocess.run(dep_cmd)
    if res.returncode != 0:
        log("Tsinghua mirror failed, retrying with default PyPI...")
        res = subprocess.run([
            sys.executable, "-m", "pip", "install",
            "--target", str(SITE_PACKAGES),
            "--no-user",
            "--disable-pip-version-check",
            "-r", str(req_file)
        ])
        if res.returncode != 0:
            fail("Failed to install project dependencies into runtime")

    # Move/copy bin/Scripts
    target_bin = SITE_PACKAGES / "bin"
    scripts_dir = RUNTIME_DIR / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    if target_bin.exists():
        for item in target_bin.iterdir():
            shutil.copy2(item, scripts_dir / item.name)

    # Clean __pycache__ to reduce size
    for p in RUNTIME_DIR.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

    # 4. Build stub exe via PyInstaller
    log("Compiling WxArticleSaver.exe stub launcher...")
    stub_py = SCRIPTS_DIR / "stub.py"
    
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller", "--quiet", "--disable-pip-version-check"])
    
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",
        "--clean",
        "--noconfirm",
        "--name", "WxArticleSaver",
        "--distpath", str(PORTABLE_DIR),
        "--workpath", str(TEMP_DIR / "pyinstaller_work"),
        "--specpath", str(TEMP_DIR),
        str(stub_py)
    ]
    res = subprocess.run(pyinstaller_cmd)
    if res.returncode != 0:
        fail("PyInstaller build failed")

    exe_path = PORTABLE_DIR / "WxArticleSaver.exe"
    if not exe_path.exists():
        fail("WxArticleSaver.exe was not created")

    # 5. Copy project files into portable folder
    log("Copying application files...")
    files_to_copy = [
        "launcher.py",
        "wx_article_saver.py",
        "manifest.json",
        "requirements.txt",
        "restore_proxy.bat",
        "restore_proxy.py",
        "remove_certificate.bat",
        "remove_certificate.py",
        "diagnose.bat",
        "LICENSE",
        "README.md",
        "README_EN.md",
    ]
    for filename in files_to_copy:
        src = ROOT / filename
        if src.exists():
            shutil.copy2(src, PORTABLE_DIR / filename)
            log(f"  + {filename}")

    # Copy docs folder if exists
    docs_src = ROOT / "docs"
    if docs_src.exists():
        shutil.copytree(docs_src, PORTABLE_DIR / "docs", dirs_exist_ok=True)
        log("  + docs/")

    # 6. Create ZIP archive
    log(f"Creating portable archive: {zip_name}...")
    shutil.make_archive(
        base_name=str(DIST_DIR / f"WxArticleSaver-v{version}-Windows-x64"),
        format="zip",
        root_dir=str(DIST_DIR),
        base_dir="WxArticleSaver"
    )

    # 7. Clean temp directory
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

    size_mb = zip_output.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print(" Portable build succeeded!")
    print(f" Output: {zip_output}")
    print(f" Size:   {size_mb:.1f} MB")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
