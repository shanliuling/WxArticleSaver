<#
.SYNOPSIS
    Build WxArticleSaver Windows portable package.
.DESCRIPTION
    Downloads Python embeddable, installs dependencies, compiles stub launcher,
    and produces a ready-to-distribute ZIP that requires no Python installation.
.PARAMETER PythonVersion
    Python embeddable version to bundle. Default: 3.12.8
#>
param(
    [string]$PythonVersion = "3.12.8"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# ── Paths ──
$ScriptDir    = $PSScriptRoot
$ProjectRoot  = Split-Path -Parent $ScriptDir
$DistDir      = Join-Path $ProjectRoot "dist"
$TempDir      = Join-Path $DistDir "_build_temp"

# Read version from manifest.json
$Manifest = Get-Content (Join-Path $ProjectRoot "manifest.json") -Raw | ConvertFrom-Json
$Version  = $Manifest.version

$PortableDir  = Join-Path $DistDir "WxArticleSaver"
$RuntimeDir   = Join-Path $PortableDir "runtime"
$ZipName      = "WxArticleSaver-v${Version}-Windows-x64.zip"
$ZipPath      = Join-Path $DistDir $ZipName

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " WxArticleSaver v$Version - Windows Portable Build"             -ForegroundColor Cyan
Write-Host " Python Embeddable: $PythonVersion"                             -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ── Step 0: Clean ──
Write-Host "`n[0/6] 清理上次构建产物..." -ForegroundColor Yellow
if (Test-Path $PortableDir) { Remove-Item $PortableDir -Recurse -Force }
if (Test-Path $ZipPath)     { Remove-Item $ZipPath -Force }
New-Item -ItemType Directory -Path $TempDir    -Force | Out-Null
New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

# ── Step 1: Download Python Embeddable ──
$PythonZipUrl  = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
$PythonZipPath = Join-Path $TempDir "python-embed.zip"

Write-Host "`n[1/6] 下载 Python $PythonVersion embeddable..." -ForegroundColor Yellow
if (-not (Test-Path $PythonZipPath)) {
    try {
        Invoke-WebRequest -Uri $PythonZipUrl -OutFile $PythonZipPath -UseBasicParsing
    } catch {
        Write-Error "下载失败: $PythonZipUrl`n请检查网络连接或更换 PythonVersion 参数。"
        exit 1
    }
}
Write-Host "  解压到 runtime/..."
Expand-Archive -Path $PythonZipPath -DestinationPath $RuntimeDir -Force

# ── Step 2: Enable site-packages ──
Write-Host "`n[2/6] 启用 site-packages..." -ForegroundColor Yellow
$PthFile = Get-ChildItem $RuntimeDir -Filter "python*._pth" | Select-Object -First 1
if (-not $PthFile) {
    Write-Error "找不到 ._pth 文件，Python embeddable 解压可能不完整。"
    exit 1
}
$PthContent = Get-Content $PthFile.FullName -Raw
$PthContent = $PthContent -replace "#import site", "import site"
Set-Content $PthFile.FullName -Value $PthContent -NoNewline
Write-Host "  已修改: $($PthFile.Name)"

# ── Step 3: Install pip + dependencies ──
Write-Host "`n[3/6] 安装 pip 和项目依赖..." -ForegroundColor Yellow
$GetPipPath    = Join-Path $TempDir "get-pip.py"
$RuntimePython = Join-Path $RuntimeDir "python.exe"
$Requirements  = Join-Path $ProjectRoot "requirements.txt"

if (-not (Test-Path $GetPipPath)) {
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPipPath -UseBasicParsing
}
& $RuntimePython $GetPipPath --no-warn-script-location 2>&1 | Write-Host
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip 安装失败。"
    exit 1
}

Write-Host "  安装项目依赖..."
& $RuntimePython -m pip install --no-warn-script-location -r $Requirements 2>&1 | Write-Host
if ($LASTEXITCODE -ne 0) {
    Write-Host "  官方源失败，切换清华镜像重试..." -ForegroundColor Yellow
    & $RuntimePython -m pip install --no-warn-script-location `
        -i "https://pypi.tuna.tsinghua.edu.cn/simple" `
        -r $Requirements 2>&1 | Write-Host
    if ($LASTEXITCODE -ne 0) {
        Write-Error "依赖安装失败。"
        exit 1
    }
}

# 清理 pip/setuptools 缩减体积（运行时不需要）
Write-Host "  清理构建工具缩减体积..."
& $RuntimePython -m pip uninstall pip setuptools -y 2>&1 | Out-Null
# 清理 __pycache__
Get-ChildItem $RuntimeDir -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ── Step 4: Build stub exe ──
Write-Host "`n[4/6] 编译 WxArticleSaver.exe..." -ForegroundColor Yellow
$StubPy = Join-Path $ScriptDir "stub.py"

# 用系统 Python + PyInstaller 编译 stub（stub 无第三方依赖）
python -m pip install pyinstaller --quiet --disable-pip-version-check 2>&1 | Out-Null
python -m PyInstaller --onefile --console --clean --noconfirm `
    --name "WxArticleSaver" `
    --distpath $PortableDir `
    --workpath (Join-Path $TempDir "pyinstaller_work") `
    --specpath $TempDir `
    $StubPy 2>&1 | Write-Host

if (-not (Test-Path (Join-Path $PortableDir "WxArticleSaver.exe"))) {
    Write-Error "PyInstaller 编译失败，未生成 WxArticleSaver.exe。"
    exit 1
}

# ── Step 5: Copy project files ──
Write-Host "`n[5/6] 复制项目文件..." -ForegroundColor Yellow
$FilesToCopy = @(
    "launcher.py"
    "wx_article_saver.py"
    "manifest.json"
    "requirements.txt"
    "restore_proxy.bat"
    "restore_proxy.py"
    "remove_certificate.bat"
    "remove_certificate.py"
    "diagnose.bat"
)
foreach ($f in $FilesToCopy) {
    $src = Join-Path $ProjectRoot $f
    if (Test-Path $src) {
        Copy-Item $src -Destination $PortableDir
        Write-Host "  $f"
    }
}

# ── Step 6: Create ZIP ──
Write-Host "`n[6/6] 打包 $ZipName..." -ForegroundColor Yellow
Compress-Archive -Path $PortableDir -DestinationPath $ZipPath -Force

$SizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB, 1)

# 清理临时文件
Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " 构建完成!" -ForegroundColor Green
Write-Host " 产物: $ZipPath" -ForegroundColor Green
Write-Host " 大小: ${SizeMB} MB" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
