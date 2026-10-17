# Technical notes — what the fix does and why

## The two root causes (same on Windows and Linux)

**1. Region gating.** Gemini in Chrome rolls out to US profiles/locales. A non-US value
anywhere in the profile (`variations_country`, safe-seed countries, `app_locale`,
`accept_languages`) — or a bare launch without a country override — keeps Glic disabled.
Symptoms range from *no button at all* to *“not available in your region”* depending on
which keys are affected.

**2. The Variations seed.** A ~39 KB server-side field-trial config stored next to
`Local State` (`Variations`, `VariationsSeedV2`, `VariationsSafeSeedV2`). It overrides
`chrome://flags` and force-disables Glic. Deleting it *and* launching with
`--disable-variations-seed-fetch` is required — either step alone does nothing.
After the fix the files stay as ~100-byte placeholders.

## What `fix.py` changes

**`Local State`** (backup `Local State.bak-<timestamp>` first):

| Key | Set to |
|---|---|
| `variations_country` | `us` |
| `variations_permanent_consistency_country` | `["<chrome version>", "us"]` |
| `variations_permanent_overridden_country` | `us` |
| `variations_safe_seed_permanent_consistency_country` | `us` |
| `variations_safe_seed_session_consistency_country` | `us` |
| `app_locale`, `variations_safe_seed_locale` | `en-US` |
| every `is_glic_eligible` (recursive) | `true` |
| `browser.enabled_labs_experiments` | existing flags kept + `glic`, `glic-side-panel`, `glic-actor`, `glic-pre-warming`, `glic-entrypoint-variations` |

**Every real profile’s `Preferences`** (`Default`, `Profile 1`, …; backup first):

| Key | Set to |
|---|---|
| `sync.glic_rollout_eligibility` | `true` |
| `glic.pinned_to_tabstrip` | `true` |
| `intl.app_locale` | `en-US` |
| `intl.accept_languages` | `en-US,en` |

**Launch flags** (every start goes through them):

```
--disable-variations-seed-fetch
--variations-override-country=us
--enable-features=Glic,GlicRollout,GlicContextMenu,GlicLiveMode,GlicVoice
--disable-features=GlicTieredRollout,GlicTieredRolloutV2,GlicUserStatusCheck,GlicUseSessionCountryForFiltering
--lang=en-US
```

- `Glic,GlicRollout` — the feature + rollout gate; `GlicContextMenu` — right-click entry;
  `GlicLiveMode,GlicVoice` — the Live voice button.
- The `--disable-features` list removes the tiered-rollout and account/session-country gates.
- `--lang=en-US` forces the US-English UI level Gemini Live requires, without changing the OS locale.

## Persistence per OS

- **Linux:** installs `~/.local/bin/google-chrome-glic` (deletes seeds when Chrome is closed,
  then launches with the flags) and overrides `~/.local/share/applications/google-chrome.desktop`
  so the normal icon uses it. The system `.desktop` file is untouched.
- **Windows:** writes `%LOCALAPPDATA%\Google\Chrome-GLIC\chrome-glic.cmd` and adds the flags
  to the Taskbar / Desktop / Start Menu shortcuts.

## What is never touched

History, cookies (`Default/Network/Cookies`), passwords (`Login Data`), bookmarks,
sessions, extensions. The script prints their sizes after patching as proof.
`Variations*` files hold no user data — only field-trial config.

## Server-side limits (no local fix can override these)

- Signed out → panel refuses. Sign in with a personal Google account, 18+.
- First run requires opting in; voice requires the microphone permission (`chrome://settings/ai`).
- A non-US IP can still be refused by Google’s backend even with everything patched.

## Verified configurations

- Windows 11, Chrome 155 (Stable), non-US system locale → region error fixed, seeds stay
  placeholders (86 / 36 / 140 bytes), command line verified in `chrome://version`.
- Arch-based Linux, Chrome 155 (Stable), non-US system locale → missing button, panel,
  context-menu entry and Live voice all restored.

## Sources

- https://github.com/Bloodcrane/chrome-gemini-linux-fix — seed discovery, launcher approach
- https://github.com/everplus/enable-chrome-ai — cross-platform profile patching
  (all channels/profiles, safe-seed countries, lab flags)
- `docs/user_data_dir.md` (Chromium) — profile locations per OS
- `chrome://version`, `chrome://settings/ai`, `chrome://version/?show-variations-cmd` — diagnostics
