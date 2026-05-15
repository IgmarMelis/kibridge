# =====================================================================
#   KiBridge - install for KiCad on Windows.
#   Repo: https://github.com/IgmarMelis/kibridge
#   Run via INSTALL.bat or directly:
#     powershell -ExecutionPolicy Bypass -File scripts\install_plugin_windows.ps1
# =====================================================================

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pluginSrc   = Join-Path $repoRoot "plugin\kibridge"
$templateSrc = Join-Path $repoRoot "workspace_template"

if (-not (Test-Path $pluginSrc)) {
    Write-Host "ERROR: plugin source not found: $pluginSrc" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $templateSrc)) {
    Write-Host "ERROR: workspace template not found: $templateSrc" -ForegroundColor Red
    exit 1
}

# Find candidate KiCad user folders.
$candidates = @()
$bases = @(
    (Join-Path $env:APPDATA "kicad"),
    (Join-Path $env:USERPROFILE "Documents\KiCad")
)
foreach ($base in $bases) {
    if (Test-Path $base) {
        Get-ChildItem $base -Directory | ForEach-Object {
            $sp = Join-Path $_.FullName "scripting\plugins"
            $candidates += [pscustomobject]@{
                Version = $_.Name; Path = $sp; Base = $base
            }
        }
    }
}

if ($candidates.Count -eq 0) {
    Write-Host ""
    Write-Host "No KiCad user folders found. Open KiCad once, then re-run." `
        -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "KiCad versions detected:" -ForegroundColor Cyan
for ($i = 0; $i -lt $candidates.Count; $i++) {
    $c = $candidates[$i]
    Write-Host ("  [{0}] KiCad {1}  ->  {2}" -f $i, $c.Version, $c.Path)
}
Write-Host ""
$choice = Read-Host "Pick the index to install into (or 'a' for all)"

$targets = @()
if ($choice -eq 'a' -or $choice -eq 'A') {
    $targets = $candidates
} else {
    $idx = [int]$choice
    if ($idx -lt 0 -or $idx -ge $candidates.Count) {
        Write-Host "Invalid choice." -ForegroundColor Red
        exit 1
    }
    $targets = @($candidates[$idx])
}

# We remove BOTH the new name and the old name (pss_kicad_agent) so users
# upgrading from 0.2.x get a clean replacement.
$legacyNames = @("pss_kicad_agent")

foreach ($t in $targets) {
    New-Item -ItemType Directory -Force -Path $t.Path | Out-Null
    $pluginDst   = Join-Path $t.Path "kibridge"
    $templateDst = Join-Path $pluginDst "workspace_template"

    Write-Host ""
    Write-Host ("Installing into KiCad {0} ..." -f $t.Version) -ForegroundColor Cyan

    # Wipe legacy installs first
    foreach ($legacy in $legacyNames) {
        $legacyPath = Join-Path $t.Path $legacy
        if (Test-Path $legacyPath) {
            Write-Host (" * Removing legacy install: {0}" -f $legacyPath) `
                -ForegroundColor Yellow
            Remove-Item -Recurse -Force $legacyPath
        }
    }

    # Wipe existing kibridge install (clean reinstall)
    if (Test-Path $pluginDst) {
        Write-Host (" * Removing existing KiBridge: {0}" -f $pluginDst) `
            -ForegroundColor Yellow
        Remove-Item -Recurse -Force $pluginDst
    }

    Copy-Item -Recurse -Force $pluginSrc   $pluginDst
    Copy-Item -Recurse -Force $templateSrc $templateDst

    Write-Host (" + Plugin   -> {0}" -f $pluginDst)   -ForegroundColor Green
    Write-Host (" + Template -> {0}" -f $templateDst) -ForegroundColor Green
}

Write-Host ""
Write-Host "Install complete." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Open KiCad PCB Editor"
Write-Host "  2. Tools -> External Plugins -> Refresh Plugins"
Write-Host "  3. Look for buttons under the 'PSS Tools' category:"
Write-Host "     - KiBridge: Inspect Board"
Write-Host "     - KiBridge: Open Workspace"
Write-Host "     - KiBridge: Apply Workspace"
Write-Host ""
