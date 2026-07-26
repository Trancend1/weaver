param(
    [string]$Tag
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $DesktopDir

$PyprojectPath = Join-Path $RepoRoot "pyproject.toml"
$TauriConfPath = Join-Path $DesktopDir "tauri.conf.json"
$InitPath = Join-Path $RepoRoot "src/weaver/__init__.py"

if (-not (Test-Path -LiteralPath $PyprojectPath)) {
    throw "Missing pyproject.toml: $PyprojectPath"
}
if (-not (Test-Path -LiteralPath $TauriConfPath)) {
    throw "Missing tauri.conf.json: $TauriConfPath"
}
if (-not (Test-Path -LiteralPath $InitPath)) {
    throw "Missing package __init__.py: $InitPath"
}

$PyprojectText = Get-Content -LiteralPath $PyprojectPath -Raw
$PyVersionMatch = [regex]::Match($PyprojectText, '(?m)^version = "([^"]+)"')
if (-not $PyVersionMatch.Success) {
    throw "Could not read version from pyproject.toml: $PyprojectPath"
}
$py = $PyVersionMatch.Groups[1].Value

$TauriText = Get-Content -LiteralPath $TauriConfPath -Raw
$TauriVersionMatch = [regex]::Match($TauriText, '(?m)^\s*"version":\s*"([^"]+)"')
if (-not $TauriVersionMatch.Success) {
    throw "Could not find version line in tauri.conf.json: $TauriConfPath"
}
$tauri = $TauriVersionMatch.Groups[1].Value

if ($py -ne $tauri) {
    throw "Version drift: pyproject=$py tauri=$tauri"
}

# `weaver --version` / GET /version read this literal. It drifted unnoticed
# through v0.7.1 and v0.7.2 (stuck at 0.7.0) because nothing compared it to
# pyproject; mirrored by tests/unit/test_version.py.
$InitText = Get-Content -LiteralPath $InitPath -Raw
$InitVersionMatch = [regex]::Match($InitText, '(?m)^__version__ = "([^"]+)"')
if (-not $InitVersionMatch.Success) {
    throw "Could not read __version__ from $InitPath"
}
$init = $InitVersionMatch.Groups[1].Value

if ($py -ne $init) {
    throw "Version drift: pyproject=$py __init__=$init"
}

if ($PSBoundParameters.ContainsKey('Tag') -and $Tag) {
    $tagVersion = $Tag.TrimStart('v')
    if ($py -ne $tagVersion) {
        throw "Tag mismatch: tag=$tagVersion pyproject=$py"
    }
}

Write-Host "Version OK: $py"
