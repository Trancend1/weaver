# Generate the opt-in update manifest (ADR 017 D3) consumed by update_check.rs.
param([Parameter(Mandatory = $true)][string]$Version, [string]$OutFile = "latest.json")
$ErrorActionPreference = "Stop"
$manifest = [ordered]@{
    version  = $Version.TrimStart("v")
    url      = "https://github.com/Trancend1/weaver/releases/latest"
    pub_date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutFile -Encoding UTF8
Write-Host "Wrote $OutFile for version $($manifest.version)"
