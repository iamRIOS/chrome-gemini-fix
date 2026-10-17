# Cases — the full data behind the fix

Two real machines, same Chrome 155, same root cause, different symptoms.

## Case 1 — Linux: button missing entirely

- OS: Omarchy 4.4 (Arch), HyVland 0.56, system locale `ru_RU.UTF-8`
- Chrome `155.0.8059.84-1` from the `omarchy` pacman repo, fresh install
- Symptom: no Ask Gemini toolbar icon, no `chrome://glic` panel, no context-menu entry.
  `chrome://flags` alone changed nothing.

Fix applied (see the full step-by-step in the original guide):
system locale → `en_US.UTF-8`, launcher `~/.local/bin/google-chrome-glic`
deleting the Variations seed on every start + flags
`Glic,GlicRollout,GlicContextMenu,GlicLiveMode,GlicVoice`, desktop override
`~/.local/share/applications/google-chrome.desktop`.
Result: icon, side panel, right-click entry and Go Live voice all work.

## Case 2 — Windows: button present, “unavailable in region”

- OS: Windows 11 Pro, system locale `ru-RU`, Chrome `155.0.8059.85`
- VPN: Germany (kept as-is — the Linux case worked with it too)
- Symptom: Ask Gemini opens but answers “not available in your region”.

### Before

| Key | Value |
|---|---|
| `variations_country` | `us` (already patched by an earlier attempt) |
| `variations_permanent_consistency_country` | `["155.0.8059.85", "us"]` |
| `variations_permanent_overridden_country` | *(empty)* |
| `variations_safe_seed_permanent_consistency_country` | `us` |
| `variations_safe_seed_session_consistency_country` | **`de`** ← German IP leaked in |
| `app_locale` | *(empty)* |
| `variations_safe_seed_locale` | **`ru`** |
| `is_glic_eligible` | **`false`** |
| `browser.enabled_labs_experiments` | *(empty)* |
| `Preferences: sync.glic_rollout_eligibility` | `true` |
| `Preferences: glic.pinned_to_tabstrip` | `true` |
| `Preferences: intl.accept_languages` | `ru,ru-RU,en` |
| `Variations` / `VariationsSeedV2` / `VariationsSafeSeedV2` | 86 B / 172 B / **41636 B** ← live seed |
| Shortcut args | *(none)* — `chrome.exe` launched bare |

### After (fix verified working)

| Key | Value |
|---|---|
| `variations_country` / `overridden` / both safe-seed countries | `us` |
| `app_locale` / `variations_safe_seed_locale` | `en-US` |
| `is_glic_eligible` | `true` (survives relaunch) |
| `enabled_labs_experiments` | `glic@1, glic-side-panel@1, glic-actor@1, glic-pre-warming@1` |
| `intl.accept_languages` | `en-US,en` |
| Seeds after relaunch | 86 B / 36 B / 140 B (placeholders, fetch disabled) |
| Main process command line | `chrome.exe --disable-variations-seed-fetch --variations-override-country=us --enable-features=Glic,GlicRollout,GlicContextMenu,GlicLiveMode,GlicVoice --disable-features=GlicTieredRollout,GlicTieredRolloutV2,GlicUserStatusCheck --lang=en-US` |

### Data integrity (before = after)

`Login Data` 71680 B · `History` 101941248 B · `Bookmarks` 18044 B ·
`Web Data` 196608 B · `Default/Network/Cookies` 2588672 B. Nothing deleted
except the three `Variations*` server-config files.

## Why both symptoms share one cause

1. **Region gating** — rollout only happens for US profiles/locales; a `ru`/`de`
   value anywhere in the country/locale keys, or a bare launch without
   `--variations-override-country=us`, keeps Glic disabled.
2. **The Variations seed** — a ~39 KB server config that overrides
   `chrome://flags` and force-disables Glic. Deleting it *and* passing
   `--disable-variations-seed-fetch` is required; either alone does nothing.

Linux showed symptom A (no button at all), Windows symptom B (region error) —
same two mechanisms, same fix.
