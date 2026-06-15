param(
    [string]$Tag
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $DesktopDir

$PyprojectPath = Join-Path $RepoRoot "pyproject.toml"
$TauriConfPath = Join-Path $DesktopDir "tauri.conf.json"

if (-not (Test-Path -LiteralPath $PyprojectPath)) {
    throw "Missing pyproject.toml: $PyprojectPath"
}
if (-not (Test-Path -LiteralPath $TauriConfPath)) {
    throw "Missing tauri.conf.json: $TauriConfPath"
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

if ($PSBoundParameters.ContainsKey('Tag') -and $Tag) {
    $tagVersion = $Tag.TrimStart('v')
    if ($py -ne $tagVersion) {
        throw "Tag mismatch: tag=$tagVersion pyproject=$py"
    }
}

Write-Host "Version OK: $py"
