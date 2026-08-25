param(
    [string]$PythonVersion = "3.12"
)

$ScriptDir = $PSScriptRoot
$BuildPy   = Join-Path $ScriptDir "build-windows.py"

py -3.12 $BuildPy
if ($LASTEXITCODE -eq 0) {
    exit 0
}

Write-Host "Python 3.12 via 'py -3.12' was unavailable or the build failed." -ForegroundColor Yellow
Write-Host "Trying 'python' only if it is Python 3.12..." -ForegroundColor Yellow
python $BuildPy
exit $LASTEXITCODE
