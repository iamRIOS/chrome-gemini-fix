# chrome-gemini-fix — one-click fix for Gemini in Chrome

If **Ask Gemini** is missing from Chrome, or the panel says
*“Gemini isn’t available right now” / “not available in your region”*,
run one command. Your data stays untouched.

## Quick start

**Windows** (no Python needed — right-click → *Run with PowerShell*, or):
```powershell
powershell -ExecutionPolicy Bypass -File fix.ps1
```

**Linux / macOS:**
```bash
./fix.sh
# or:  python3 fix.py
```

Close Chrome when asked — your tabs restore on launch.

## What it does

- Backs up `Local State` and each profile’s `Preferences` (timestamped, next to the originals)
- Sets region to US and locale to `en-US` (`variations_country`, safe-seed countries, `app_locale`)
- Sets every `is_glic_eligible` to `true`, keeps your existing lab flags and adds the Glic ones
- Enables rollout + pins the button in every real profile (`Default`, `Profile 1`, …)
- Deletes the **Variations seed** files — Google’s server-side config that force-disables Gemini
  (they come back as ~100-byte placeholders, not the ~39 KB seed)
- Makes the fix stick: Linux icon override + launcher, Windows shortcut args + launcher
- Relaunches Chrome with Gemini force-enabled:
  `--disable-variations-seed-fetch --variations-override-country=us --enable-features=Glic,GlicRollout,GlicContextMenu,GlicLiveMode,GlicVoice --disable-features=GlicTieredRollout,GlicTieredRolloutV2,GlicUserStatusCheck,GlicUseSessionCountryForFiltering --lang=en-US`

## What it never touches

History, cookies, passwords, bookmarks, sessions, extensions. After patching it prints their
sizes so you can see for yourself. `Variations*` files contain no user data — only field-trial config.

## Verify

1. `chrome://version` → Command Line row shows `--enable-features=Glic…`
2. Star icon top-right, right-click a selection → **Ask Gemini**, `chrome://glic` opens
3. Mic / Live button in the panel for voice mode

## Troubleshooting

| Symptom | Fix |
|---|---|
| Button was there, then disappeared | Chrome was started without the launcher once and re-fetched the seed — always use the icon / `fix.sh` / `chrome-glic.cmd` |
| Panel opens, “isn’t available right now” | Server-side refusal: sign in with a personal 18+ Google account, allow the mic; a non-US IP can still be refused |
| No Live/mic button | Re-run the fix (adds `GlicLiveMode,GlicVoice`), relaunch, check `chrome://settings/ai` |
| Chrome was updated | Re-run — updates can reset profile flags; the launcher re-applies them each start |

Diagnose without changing anything: `python3 fix.py --check` (or `fix.ps1 -Check`).

## Restore

```bash
# Linux: remove the override + launcher
rm -f ~/.local/share/applications/google-chrome.desktop ~/.local/bin/google-chrome-glic
# Windows: run fix.ps1 -NoLaunch after clearing shortcut args, or simply remove the args
# from the Chrome shortcut properties. Then restore the newest backups:
cp 'Local State.bak-<timestamp>' 'Local State'
cp 'Default/Preferences.bak-<timestamp>' 'Default/Preferences'
```

Next launch re-fetches a seed and Gemini hides again — that’s the stock behavior.

## Details

- [`docs/CASES.md`](docs/CASES.md) — the two real cases behind this (Linux: missing button; Windows: region error), with before/after values down to the byte
- Based on [`Bloodcrane/chrome-gemini-linux-fix`](https://github.com/Bloodcrane/chrome-gemini-linux-fix) (seed discovery) and [`everplus/enable-chrome-ai`](https://github.com/everplus/enable-chrome-ai) (cross-platform profile patching), extended with voice flags, `en-US` locale keys, all-profile patching and Windows shortcut persistence

Disabling the variations seed opts out of *all* server-side field trials, including emergency
kill-switches. Fine for a personal machine, not for managed fleets.

MIT — not affiliated with Google.
