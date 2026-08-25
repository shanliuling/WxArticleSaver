param(
    [string]$PythonVersion = "3.12.8"
)

$ScriptDir   = $PSScriptRoot
$ProjectRoot = Split-Path -Parent $ScriptDir
$BuildPy     = Join-Path $ScriptDir "build-windows.py"

py -3 $BuildPy
if ($LASTEXITCODE -ne 0) {
    python $BuildPy
}
exit $LASTEXITCODE
