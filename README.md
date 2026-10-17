<div align="center">

# ✨ chrome-gemini-fix

**One command brings back Ask Gemini in Chrome.**

Missing button · “Not available in your region” · No voice mode — fixed on Windows and Linux.

[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/iamRIOS/chrome-gemini-fix)
[![Linux](https://img.shields.io/badge/Linux-any%20distro-FCC624?style=for-the-badge&logo=linux&logoColor=black)](https://github.com/iamRIOS/chrome-gemini-fix)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Chrome](https://img.shields.io/badge/Chrome-151%2B-4285F4?style=for-the-badge&logo=googlechrome&logoColor=white)](https://www.google.com/chrome/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

*No data loss. No reinstall. No tech skills needed — copy, paste, done.*

</div>

---

## 🚀 Quick start

Copy **one line**, paste it into your terminal, hit Enter. That’s it.

**Windows** — paste into PowerShell:
```powershell
irm https://raw.githubusercontent.com/iamRIOS/chrome-gemini-fix/main/fix.py -OutFile $env:TEMP/fix.py; py $env:TEMP/fix.py --yes
```
> If `py` is not found, [install Python](https://www.python.org/downloads/) (tick “Add to PATH”) and use `python` instead of `py`.

**Linux** — paste into your terminal:
```bash
curl -fsSL https://raw.githubusercontent.com/iamRIOS/chrome-gemini-fix/main/fix.py -o /tmp/fix.py && python3 /tmp/fix.py --yes
```

Close Chrome when asked — your tabs come back on launch. After the run, open Chrome from your usual icon.

---

## ✅ What it fixes

| Symptom | Windows | Linux |
|---|---|---|
| No **Ask Gemini** button at all | ✅ | ✅ |
| *“Gemini isn’t available right now” / wrong region* | ✅ | ✅ |
| Button was there, then disappeared | ✅ | ✅ |
| No **Live / microphone** voice button | ✅ | ✅ |
| Broken again after a Chrome update | ✅ just re-run | ✅ just re-run |

Works for every profile (`Default`, `Profile 1`, …) and every channel (Stable, Beta, Dev, Canary).

## 🛡️ Your data is safe

The script **never touches** history, cookies, passwords, bookmarks, tabs or extensions.
It only edits two settings files (`Local State`, `Preferences` — timestamped backups are made first)
and deletes the `Variations*` seed files, which contain **zero user data** — just Google’s
server-side feature switches. After patching it prints a data-integrity report so you can verify.

## 🔍 Verify it worked

1. Open `chrome://version` — the **Command Line** row contains `--enable-features=Glic…`
2. Star icon **✨** top-right, right-click any text → **Ask Gemini**, `chrome://glic` opens
3. Mic / **Live** button inside the panel for voice mode

## 🆘 Still not working?

| Problem | Solution |
|---|---|
| Panel opens but says *“isn’t available”* | Sign in with a personal **18+** Google account and allow the microphone — Google can still refuse non-US IPs server-side |
| Worked, then broke | Chrome was launched bypassing the fix at least once — always use your normal icon after running the script |
| No Live button | Re-run the script and relaunch, then check `chrome://settings/ai` |
| Just diagnose, change nothing | `python3 fix.py --check` |

Full technical breakdown: [`docs/CASES.md`](docs/CASES.md).

## ↩️ Restore

Delete the launcher persistence (Linux icon override / Windows shortcut args are documented in
`docs/CASES.md`), restore the newest backups over `Local State` / `Preferences`,
and launch Chrome normally — it re-fetches a seed and stock behavior returns.

## ⚙️ How it works

Chrome ships Gemini everywhere but **region-gates** it for non-US profiles and lets a
~39 KB **Variations seed** (server-side field-trial config) override `chrome://flags`
and force-disable it. The script sets the region keys to `us`, locale to `en-US`,
marks every profile eligible, removes the seed, blocks re-fetching, and launches Chrome
with the Glic feature tree force-enabled. Details + sources in [`docs/CASES.md`](docs/CASES.md).

---

<div align="center">

MIT · Not affiliated with Google · Disabling the variations seed also opts out of all
server-side field trials — fine for a personal machine, not for managed fleets.

</div>
