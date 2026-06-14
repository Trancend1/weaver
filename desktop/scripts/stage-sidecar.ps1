param(
    [string]$Triple = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Split-Path -Parent $ScriptDir
$SourceDir = Join-Path $DesktopDir "target/sidecar/weaver"
$SourceExe = Join-Path $SourceDir "weaver.exe"
$SourceInternal = Join-Path $SourceDir "_internal"
$TargetDir = Join-Path $DesktopDir "sidecar"
$TargetExe = Join-Path $TargetDir "weaver-$Triple.exe"
$TargetInternal = Join-Path $TargetDir "_internal"

if (-not (Test-Path -LiteralPath $SourceExe)) {
    throw "Missing PyInstaller sidecar executable: $SourceExe"
}
if (-not (Test-Path -LiteralPath $SourceInternal -PathType Container)) {
    throw "Missing PyInstaller sidecar dependency directory: $SourceInternal"
}

$ResolvedTargetDir = (Resolve-Path -LiteralPath $TargetDir).Path
$ResolvedDesktopDir = (Resolve-Path -LiteralPath $DesktopDir).Path
if (-not $ResolvedTargetDir.StartsWith($ResolvedDesktopDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to stage sidecar outside desktop directory: $ResolvedTargetDir"
}

Copy-Item -LiteralPath $SourceExe -Destination $TargetExe -Force

if (Test-Path -LiteralPath $TargetInternal) {
    $ResolvedTargetInternal = (Resolve-Path -LiteralPath $TargetInternal).Path
    if (-not $ResolvedTargetInternal.StartsWith($ResolvedTargetDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove sidecar dependency directory outside staging directory: $ResolvedTargetInternal"
    }
    Remove-Item -LiteralPath $TargetInternal -Recurse -Force
}
Copy-Item -LiteralPath $SourceInternal -Destination $TargetInternal -Recurse -Force

Get-Item -LiteralPath $TargetExe | Select-Object FullName, Length, LastWriteTime
