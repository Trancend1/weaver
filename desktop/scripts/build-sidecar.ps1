param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $DesktopDir
$SpecPath = Join-Path $DesktopDir "sidecar/weaver-sidecar.spec"
$DistPath = Join-Path $DesktopDir "target/sidecar"
$WorkPath = Join-Path $DesktopDir "target/pyinstaller-work"
$UvCachePath = Join-Path $DesktopDir "target/uv-cache"

if (-not $env:UV_CACHE_DIR) {
    $env:UV_CACHE_DIR = $UvCachePath
}

if ($Clean) {
    Remove-Item -LiteralPath $DistPath -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $WorkPath -Recurse -Force -ErrorAction SilentlyContinue
}

Push-Location $RepoRoot
try {
    $PythonCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs/Python/Python312/python.exe"),
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    if (-not $PythonCandidates) {
        throw "No Python interpreter found for sidecar packaging."
    }
    # Force array context: when only one candidate survives the filter PowerShell
    # collapses it to a scalar string, and indexing a string returns its first
    # CHAR (e.g. "C" of "C:\...") — which uv then rejects as an interpreter name.
    $PythonExe = @($PythonCandidates)[0]
    uv run --python $PythonExe --no-managed-python --no-python-downloads --all-extras --with "pyinstaller>=6,<7" pyinstaller `
        --noconfirm `
        --clean `
        --distpath $DistPath `
        --workpath $WorkPath `
        $SpecPath
} finally {
    Pop-Location
}

$Artifact = Join-Path $DistPath "weaver/weaver.exe"
if (-not (Test-Path -LiteralPath $Artifact)) {
    throw "Expected sidecar artifact was not created: $Artifact"
}

Get-Item -LiteralPath $Artifact | Select-Object FullName, Length, LastWriteTime

& (Join-Path $ScriptDir "stage-sidecar.ps1")
