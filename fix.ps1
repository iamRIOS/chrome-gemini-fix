<#Requires -Version 5.1>
<#
.SYNOPSIS
  One-click fix for Gemini in Chrome on Windows ("Ask Gemini" missing or unavailable in region).
.DESCRIPTION
  Backs up Local State + Preferences, patches region/eligibility to US/en-US,
  deletes the Variations seed files (server config, not user data), patches
  Chrome shortcuts so the fix persists, and relaunches Chrome with Glic flags.
  Never touches history, cookies, passwords, bookmarks or sessions.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File fix.ps1
  fix.ps1 -Yes   # close Chrome automatically
#>
param([switch]$Yes, [switch]$NoLaunch, [switch]$Check)

$ErrorActionPreference = "Stop"
$TARGET_COUNTRY = "us"
$APP_LOCALE = "en-US"
$ACCEPT_LANGS = "en-US,en"
$ENABLE = "Glic,GlicRollout,GlicContextMenu,GlicLiveMode,GlicVoice"
$DISABLE = "GlicTieredRollout,GlicTieredRolloutV2,GlicUserStatusCheck,GlicUseSessionCountryForFiltering"
$LABS = @("glic@1", "glic-side-panel@1", "glic-actor@1", "glic-pre-warming@1", "glic-entrypoint-variations@1")
$SEEDS = @("Variations", "VariationsSeedV2", "VariationsSafeSeedV2")
$FLAGS = "--disable-variations-seed-fetch --variations-override-country=$TARGET_COUNTRY --enable-features=$ENABLE --disable-features=$DISABLE --lang=en-US"

$UD = Join-Path $env:LOCALAPPDATA "Google\Chrome\User Data"
$LS = Join-Path $UD "Local State"
$CHROME = "C:\Program Files\Google\Chrome\Application\chrome.exe"
if (-not (Test-Path -LiteralPath $CHROME)) { $CHROME = Join-Path $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe" }
if (-not (Test-Path -LiteralPath $CHROME)) { Write-Error "Chrome not found. Install Google Chrome first." }

function Set-GlicEligible($o) {
  if ($o -is [System.Management.Automation.PSCustomObject]) {
    foreach ($pr in $o.PSObject.Properties) {
      if ($pr.Name -eq "is_glic_eligible") { $pr.Value = $true }
      elseif ($pr.Value -is [System.Management.Automation.PSCustomObject] -or $pr.Value -is [System.Array]) { Set-GlicEligible $pr.Value }
    }
  } elseif ($o -is [System.Array]) { foreach ($it in $o) { Set-GlicEligible $it } }
}

function Backup-File($p) {
  $ts = Get-Date -Format "yyyyMMdd-HHmmss"
  $bak = "$p.bak-$ts"
  Copy-Item -LiteralPath $p -Destination $bak -Force
  return $bak
}

function Show-State {
  $j = Get-Content -LiteralPath $LS -Raw | ConvertFrom-Json
  foreach ($k in @("variations_country", "variations_permanent_consistency_country",
      "variations_permanent_overridden_country", "variations_safe_seed_permanent_consistency_country",
      "variations_safe_seed_session_consistency_country", "app_locale", "variations_safe_seed_locale")) {
    Write-Output ("  {0} = {1}" -f $k, ($j.$k -join ","))
  }
  Write-Output ("  labs = " + ($j.browser.enabled_labs_experiments -join ","))
  $raw = Get-Content -LiteralPath $LS -Raw
  foreach ($m in [regex]::Matches($raw, 'is_glic_eligible":(true|false)')) { Write-Output ("  is_glic_eligible = " + $m.Groups[1].Value) }
  foreach ($s in $SEEDS) {
    $p = Join-Path $UD $s
    if (Test-Path -LiteralPath $p) { Write-Output ("  {0} = {1} bytes" -f $s, (Get-Item -LiteralPath $p).Length) }
    else { Write-Output ("  {0} = absent" -f $s) }
  }
}

if ($Check) { Show-State; Write-Output ("`nFlags that would be used:`n  $FLAGS"); exit 0 }

Write-Output "Chrome binary: $CHROME"
Write-Output "User data:   $UD"
if (-not (Test-Path -LiteralPath $LS)) { Write-Error "Local State not found. Launch Chrome once, then retry." }

if (Get-Process chrome -ErrorAction SilentlyContinue) {
  if (-not $Yes) {
    $a = Read-Host "Chrome is running and must be closed to patch safely (tabs restore on launch). Close it now? [y/N]"
    if ($a -notin @("y", "Y", "yes", "YES")) { Write-Error "Aborted." }
  }
  Write-Output "Closing Chrome..."
  taskkill /IM chrome.exe 2>$null | Out-Null
  Start-Sleep -Seconds 4
  if (Get-Process chrome -ErrorAction SilentlyContinue) { Write-Error "Chrome is still running. Close it manually and retry." }
}

# --- Local State ---
$ver = (Get-Item -LiteralPath $CHROME).VersionInfo.FileVersion
$raw = Get-Content -LiteralPath $LS -Raw -Encoding UTF8
$j = $raw | ConvertFrom-Json
$j | Add-Member -NotePropertyName variations_country -NotePropertyValue $TARGET_COUNTRY -Force
$j | Add-Member -NotePropertyName variations_permanent_consistency_country -NotePropertyValue @($ver, $TARGET_COUNTRY) -Force
$j | Add-Member -NotePropertyName variations_permanent_overridden_country -NotePropertyValue $TARGET_COUNTRY -Force
$j | Add-Member -NotePropertyName variations_safe_seed_permanent_consistency_country -NotePropertyValue $TARGET_COUNTRY -Force
$j | Add-Member -NotePropertyName variations_safe_seed_session_consistency_country -NotePropertyValue $TARGET_COUNTRY -Force
$j | Add-Member -NotePropertyName app_locale -NotePropertyValue $APP_LOCALE -Force
$j | Add-Member -NotePropertyName variations_safe_seed_locale -NotePropertyValue $APP_LOCALE -Force
Set-GlicEligible $j
if (-not $j.browser) { $j | Add-Member -NotePropertyName browser -NotePropertyValue (New-Object PSObject) -Force }
if (-not $j.browser.enabled_labs_experiments) { $j.browser | Add-Member -NotePropertyName enabled_labs_experiments -NotePropertyValue @() -Force }
$labs = [System.Collections.ArrayList]@($j.browser.enabled_labs_experiments)
foreach ($f in $LABS) { if ($labs -notcontains $f) { [void]$labs.Add($f) } }
$j.browser.enabled_labs_experiments = $labs.ToArray()
$bakLS = Backup-File $LS
$tmp = "$LS.tmp"
$j | ConvertTo-Json -Depth 100 -Compress | Set-Content -LiteralPath $tmp -Encoding UTF8 -NoNewline
Move-Item -LiteralPath $tmp -Destination $LS -Force
Write-Output "Local State patched (backup: $bakLS)"

# --- Preferences (every real profile) ---
$infoCache = @()
if ($j.profile.info_cache) { $infoCache = @($j.profile.info_cache.PSObject.Properties.Name) }
$prefFiles = @()
foreach ($d in ($infoCache + (Get-ChildItem -LiteralPath $UD -Directory -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name))) {
  if ($d -in @("System Profile", "Guest Profile")) { continue }
  $p = Join-Path (Join-Path $UD $d) "Preferences"
  if ((Test-Path -LiteralPath $p) -and ($prefFiles -notcontains $p)) { $prefFiles += $p }
}
foreach ($pf in $prefFiles) {
  $p = Get-Content -LiteralPath $pf -Raw -Encoding UTF8 | ConvertFrom-Json
  $changed = $false
  if (-not $p.sync) { $p | Add-Member -NotePropertyName sync -NotePropertyValue (New-Object PSObject) -Force }
  if ($p.sync.glic_rollout_eligibility -ne $true) { $p.sync | Add-Member -NotePropertyName glic_rollout_eligibility -NotePropertyValue $true -Force; $changed = $true }
  if (-not $p.glic) { $p | Add-Member -NotePropertyName glic -NotePropertyValue (New-Object PSObject) -Force }
  if ($p.glic.pinned_to_tabstrip -ne $true) { $p.glic | Add-Member -NotePropertyName pinned_to_tabstrip -NotePropertyValue $true -Force; $changed = $true }
  if (-not $p.intl) { $p | Add-Member -NotePropertyName intl -NotePropertyValue (New-Object PSObject) -Force }
  if ($p.intl.app_locale -ne $APP_LOCALE) { $p.intl | Add-Member -NotePropertyName app_locale -NotePropertyValue $APP_LOCALE -Force; $changed = $true }
  if ($p.intl.accept_languages -ne $ACCEPT_LANGS) { $p.intl | Add-Member -NotePropertyName accept_languages -NotePropertyValue $ACCEPT_LANGS -Force; $changed = $true }
  if ($changed) {
    $b = Backup-File $pf
    $t = "$pf.tmp"
    $p | ConvertTo-Json -Depth 100 -Compress | Set-Content -LiteralPath $t -Encoding UTF8 -NoNewline
    Move-Item -LiteralPath $t -Destination $pf -Force
    Write-Output ("Preferences patched: {0} (backup {1})" -f $pf, (Split-Path $b -Leaf))
  }
}

# --- Seeds (server config only, safe to delete) ---
foreach ($s in $SEEDS) {
  $p = Join-Path $UD $s
  if (Test-Path -LiteralPath $p) {
    $len = (Get-Item -LiteralPath $p).Length
    Remove-Item -LiteralPath $p -Force
    Write-Output "removed seed: $s ($len bytes)"
  }
}

# --- Launcher + shortcut persistence ---
$glicDir = Join-Path $env:LOCALAPPDATA "Google\Chrome-GLIC"
New-Item -ItemType Directory -Path $glicDir -Force | Out-Null
$launcher = Join-Path $glicDir "chrome-glic.cmd"
@'
@echo off
REM Generated by chrome-gemini-fix.
tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I "chrome.exe" >NUL
if errorlevel 1 (
  del /F /Q "%LOCALAPPDATA%\Google\Chrome\User Data\Variations" "%LOCALAPPDATA%\Google\Chrome\User Data\VariationsSeedV2" "%LOCALAPPDATA%\Google\Chrome\User Data\VariationsSafeSeedV2" 2>NUL
)
start "" "CHROME_BIN_PLACEHOLDER" FLAGS_PLACEHOLDER %*
'@ -replace "CHROME_BIN_PLACEHOLDER", $CHROME -replace "FLAGS_PLACEHOLDER", $FLAGS |
  Set-Content -LiteralPath $launcher -Encoding ASCII
Write-Output "installed: $launcher"

$sh = New-Object -ComObject WScript.Shell
foreach ($L in @("$env:APPDATA\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\Google Chrome.lnk",
    "$env:PUBLIC\Desktop\Google Chrome.lnk",
    "C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk")) {
  if (Test-Path -LiteralPath $L) {
    $sc = $sh.CreateShortcut($L); $sc.Arguments = $FLAGS; $sc.Save()
    Write-Output "shortcut updated: $L"
  }
}

# --- Launch + verify ---
if (-not $NoLaunch) {
  Start-Process -FilePath $CHROME -ArgumentList ($FLAGS -split " ")
  Start-Sleep -Seconds 5
}
Write-Output "`n--- Verify ---"
Show-State
Write-Output "`nIn Chrome, open chrome://version and confirm the Command Line row contains --enable-features=Glic."
Write-Output "Done. If the panel still says unavailable, sign in with a personal Google account (18+); a non-US IP can still be refused server-side."
