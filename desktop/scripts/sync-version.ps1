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
$Version = $PyVersionMatch.Groups[1].Value

$TauriText = Get-Content -LiteralPath $TauriConfPath -Raw
$TauriVersionPattern = '(?m)^(\s*"version":\s*")[^"]+(",?\s*)$'
if (-not [regex]::IsMatch($TauriText, $TauriVersionPattern)) {
    throw "Could not find version line in tauri.conf.json: $TauriConfPath"
}
$NewTauriText = [regex]::Replace($TauriText, $TauriVersionPattern, "`${1}$Version`${2}")

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($TauriConfPath, $NewTauriText, $Utf8NoBom)

Write-Host "Synced desktop version -> $Version"
