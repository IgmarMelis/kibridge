# =====================================================================
#   KiBridge - uninstall from all KiCad versions on this user account.
#   Removes both the new "kibridge" install and the legacy
#   "pss_kicad_agent" install if present.
# =====================================================================

$ErrorActionPreference = "Stop"

$paths = @()
$names = @("kibridge", "pss_kicad_agent")
$bases = @(
    (Join-Path $env:APPDATA "kicad"),
    (Join-Path $env:USERPROFILE "Documents\KiCad")
)

foreach ($base in $bases) {
    if (Test-Path $base) {
        Get-ChildItem $base -Directory | ForEach-Object {
            foreach ($name in $names) {
                $candidate = Join-Path $_.FullName "scripting\plugins\$name"
                if (Test-Path $candidate) { $paths += $candidate }
            }
        }
    }
}

if ($paths.Count -eq 0) {
    Write-Host "No KiBridge install found." -ForegroundColor Yellow
    exit 0
}

foreach ($p in $paths) {
    Remove-Item -Recurse -Force $p
    Write-Host (" - removed {0}" -f $p) -ForegroundColor Green
}

Write-Host ""
Write-Host "Uninstall complete. Restart KiCad (or use" `
    "Tools -> External Plugins -> Refresh Plugins)."
