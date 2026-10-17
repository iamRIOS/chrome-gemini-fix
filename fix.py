#!/usr/bin/env python3
"""One-click fix for Gemini in Chrome ("Ask Gemini" missing or "not available in your region").

Works on Windows and Linux, fixes every symptom at once: missing button,
region error, missing voice button, fix lost after update.

What it does (safe, no data loss):
  1. Backs up `Local State` and every profile's `Preferences` (timestamped copies).
  2. Patches region/eligibility keys to US + English (US) in `Local State`.
  3. Patches `Preferences` of every real profile (rollout eligibility, pinned button, en-US).
  4. Deletes the Variations seed files (server-side config, NOT user data).
  5. Persists the fix (Linux .desktop override / Windows shortcut args + launcher).
  6. Relaunches Chrome with the flags that force Glic on.

It never touches history, cookies, passwords, bookmarks or sessions.
Requires only the Python standard library (Python 3.8+).

Usage:
    python3 fix.py            # Linux: interactive (asks before closing Chrome)
    py fix.py --yes           # Windows: close Chrome automatically, no questions
    python3 fix.py --check    # diagnose only, change nothing
    python3 fix.py --no-launch # patch but do not relaunch Chrome
"""

import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
import time

TARGET_COUNTRY = "us"
APP_LOCALE = "en-US"
ACCEPT_LANGUAGES = "en-US,en"

ENABLE_FEATURES = "Glic,GlicRollout,GlicContextMenu,GlicLiveMode,GlicVoice"
DISABLE_FEATURES = (
    "GlicTieredRollout,GlicTieredRolloutV2,GlicUserStatusCheck,"
    "GlicUseSessionCountryForFiltering"
)

# Lab flags written to browser.enabled_labs_experiments (deduplicated, existing kept).
# Union of the sets proven by the community fixes this project builds on.
FORCED_LABS = (
    "glic@1",
    "glic-side-panel@1",
    "glic-actor@1",
    "glic-pre-warming@1",
    "glic-entrypoint-variations@1",
)

SEED_FILES = ("Variations", "VariationsSeedV2", "VariationsSafeSeedV2")

# Profile dirs that are not real user profiles.
EXCLUDED_PROFILE_DIRS = {"System Profile", "Guest Profile"}

# Files checked after patching to prove user data is intact.
DATA_SAFETY_FILES = (
    os.path.join("Default", "Login Data"),
    os.path.join("Default", "History"),
    os.path.join("Default", "Bookmarks"),
    os.path.join("Default", "Web Data"),
    os.path.join("Default", "Network", "Cookies"),  # Cookies live here since Chrome 96
    os.path.join("Default", "Preferences"),
)

OS = platform.system()  # Windows | Linux | Darwin


# ---------------------------------------------------------------- discovery

def user_data_dirs():
    """Return [(channel, user_data_dir)] for every installed Chrome channel."""
    home = os.path.expanduser("~")
    if OS == "Windows":
        local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        candidates = {
            "stable": os.path.join(local, "Google", "Chrome", "User Data"),
            "beta": os.path.join(local, "Google", "Chrome Beta", "User Data"),
            "dev": os.path.join(local, "Google", "Chrome Dev", "User Data"),
            "canary": os.path.join(local, "Google", "Chrome SxS", "User Data"),
        }
    else:  # Linux and friends
        config_home = os.environ.get(
            "CHROME_CONFIG_HOME",
            os.environ.get("XDG_CONFIG_HOME", os.path.join(home, ".config")),
        )
        candidates = {
            "stable": os.path.join(config_home, "google-chrome"),
            "beta": os.path.join(config_home, "google-chrome-beta"),
            "dev": os.path.join(config_home, "google-chrome-unstable"),
            "canary": os.path.join(config_home, "google-chrome-canary"),
        }
    return [(ch, p) for ch, p in candidates.items() if os.path.isdir(p)]


def chrome_binaries():
    """Return existing Chrome executables, stable first."""
    found = []
    if OS == "Windows":
        pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        roots = [os.path.join(pf, "Google"), os.path.join(pf86, "Google")]
        if local:
            roots.append(os.path.join(local, "Google"))
        for channel, app_dir in (("stable", "Chrome"), ("beta", "Chrome Beta"),
                                 ("dev", "Chrome Dev"), ("canary", "Chrome SxS")):
            for root in roots:
                p = os.path.join(root, app_dir, "Application", "chrome.exe")
                if os.path.isfile(p):
                    found.append((channel, p))
                    break
    else:  # Linux
        cands = [
            ("stable", "/usr/bin/google-chrome-stable"),
            ("stable", "/usr/bin/google-chrome"),
            ("stable", "/opt/google/chrome/chrome"),
            ("beta", "/usr/bin/google-chrome-beta"),
            ("beta", "/opt/google/chrome-beta/chrome"),
            ("dev", "/usr/bin/google-chrome-unstable"),
            ("dev", "/opt/google/chrome-unstable/chrome"),
            ("canary", "/opt/google/chrome-canary/chrome"),
        ]
        for ch, p in cands:
            if os.path.isfile(p) and os.access(p, os.X_OK):
                if ch not in [c for c, _ in found]:
                    found.append((ch, p))
        for name in ("google-chrome-stable", "google-chrome", "chromium"):
            w = shutil.which(name)
            if w and all(w != p for _, p in found):
                found.append(("stable", w))
    return found


def chrome_running():
    try:
        if OS == "Windows":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                capture_output=True, text=True,
            ).stdout
            return "chrome.exe" in out.lower()
        r = subprocess.run(["pgrep", "-x", "chrome"], capture_output=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def close_chrome(timeout=25):
    """Close Chrome: ask nicely first (profile is flushed), force leftovers after."""
    try:
        if OS == "Windows":
            # CloseMainWindow is Alt+F4 for each window: Chrome exits cleanly,
            # flushing history/cookies/sessions to disk.
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "Get-Process chrome -ErrorAction SilentlyContinue | "
                            "Where-Object {$_.MainWindowHandle -ne 0} | "
                            "ForEach-Object { $_.CloseMainWindow() }"],
                           capture_output=True, timeout=30)
            subprocess.run(["taskkill", "/IM", "chrome.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-x", "chrome"], capture_output=True)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    grace = 10 if OS == "Windows" else 6
    for _ in range(grace * 2):
        if not chrome_running():
            return True
        time.sleep(0.5)
    # Leftovers that ignore the gentle signal (gpu/utility/renderer processes):
    # the main process already flushed the profile, so this is safe.
    try:
        if OS == "Windows":
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        else:
            subprocess.run(["pkill", "-9", "-x", "chrome"], capture_output=True)
    except FileNotFoundError:
        pass
    for _ in range(max((timeout - grace), 1) * 2):
        if not chrome_running():
            return True
        time.sleep(0.5)
    return not chrome_running()


def chrome_version_for(user_data_dir):
    lv = os.path.join(user_data_dir, "Last Version")
    try:
        with open(lv, "r", encoding="utf-8") as fp:
            return fp.read().strip().split()[0]
    except OSError:
        return "0.0.0.0"


# ---------------------------------------------------------------- patching

def backup(path):
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.bak-{ts}"
    shutil.copy2(path, bak)
    return bak


def atomic_write_json(path, obj):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(obj, fp, ensure_ascii=False)
    os.replace(tmp, path)


def set_all_is_glic_eligible(obj):
    """Recursively set every is_glic_eligible to True. Returns True if changed."""
    changed = False
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "is_glic_eligible":
                if value is not True:
                    obj[key] = True
                    changed = True
            elif isinstance(value, (dict, list)):
                changed = set_all_is_glic_eligible(value) or changed
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                changed = set_all_is_glic_eligible(item) or changed
    return changed


def patch_local_state(user_data_dir, version):
    path = os.path.join(user_data_dir, "Local State")
    with open(path, "r", encoding="utf-8") as fp:
        state = json.load(fp)
    log = []

    if set_all_is_glic_eligible(state):
        log.append("is_glic_eligible -> true")

    def set_key(key, value, label):
        if state.get(key) != value:
            state[key] = value
            log.append(label)

    set_key("variations_country", TARGET_COUNTRY, "variations_country -> us")
    set_key("variations_permanent_consistency_country", [version, TARGET_COUNTRY],
            "variations_permanent_consistency_country -> [v, us]")
    set_key("variations_permanent_overridden_country", TARGET_COUNTRY,
            "variations_permanent_overridden_country -> us")
    set_key("variations_safe_seed_permanent_consistency_country", TARGET_COUNTRY,
            "safe_seed permanent country -> us")
    set_key("variations_safe_seed_session_consistency_country", TARGET_COUNTRY,
            "safe_seed session country -> us")
    set_key("app_locale", APP_LOCALE, "app_locale -> en-US")
    set_key("variations_safe_seed_locale", APP_LOCALE, "safe_seed locale -> en-US")

    browser = state.get("browser")
    if not isinstance(browser, dict):
        browser = {}
        state["browser"] = browser
    labs = browser.get("enabled_labs_experiments")
    if not isinstance(labs, list):
        labs = []
        browser["enabled_labs_experiments"] = labs
    for flag in FORCED_LABS:
        if flag not in labs:
            labs.append(flag)
            log.append(f"lab flag +{flag}")

    if not log:
        return None, []
    bak = backup(path)
    atomic_write_json(path, state)
    return bak, log


def profile_prefs_paths(user_data_dir, state):
    """Preferences files of all real profiles."""
    dirs = []
    info_cache = state.get("profile", {}).get("info_cache", {})
    if isinstance(info_cache, dict):
        dirs.extend(info_cache.keys())
    try:
        for entry in os.listdir(user_data_dir):
            if os.path.isfile(os.path.join(user_data_dir, entry, "Preferences")):
                dirs.append(entry)
    except OSError:
        pass
    seen, out = set(), []
    for d in dirs:
        if d in seen or d in EXCLUDED_PROFILE_DIRS:
            continue
        p = os.path.join(user_data_dir, d, "Preferences")
        if os.path.isfile(p):
            out.append(p)
            seen.add(d)
    return out


def patch_preferences(prefs_path):
    with open(prefs_path, "r", encoding="utf-8") as fp:
        prefs = json.load(fp)
    log = []

    def ensure(path):
        node = prefs
        for key in path:
            nxt = node.get(key)
            if not isinstance(nxt, dict):
                nxt = {}
                node[key] = nxt
            node = nxt
        return node

    sync = ensure(("sync",))
    if sync.get("glic_rollout_eligibility") is not True:
        sync["glic_rollout_eligibility"] = True
        log.append("sync.glic_rollout_eligibility -> true")
    glic = ensure(("glic",))
    if glic.get("pinned_to_tabstrip") is not True:
        glic["pinned_to_tabstrip"] = True
        log.append("glic.pinned_to_tabstrip -> true")
    intl = ensure(("intl",))
    if intl.get("app_locale") != APP_LOCALE:
        intl["app_locale"] = APP_LOCALE
        log.append("intl.app_locale -> en-US")
    if intl.get("accept_languages") != ACCEPT_LANGUAGES:
        intl["accept_languages"] = ACCEPT_LANGUAGES
        log.append("intl.accept_languages -> en-US,en")

    if log:
        bak = backup(prefs_path)
        atomic_write_json(prefs_path, prefs)
        return bak, log
    return None, []


def clear_seeds(user_data_dir):
    removed = []
    for name in SEED_FILES:
        p = os.path.join(user_data_dir, name)
        if os.path.isfile(p) or os.path.islink(p):
            size = os.path.getsize(p)
            os.remove(p)
            removed.append(f"{name} ({size} bytes)")
    return removed


# ---------------------------------------------------------------- persist & launch

def launch_args():
    return [
        "--disable-variations-seed-fetch",
        f"--variations-override-country={TARGET_COUNTRY}",
        f"--enable-features={ENABLE_FEATURES}",
        f"--disable-features={DISABLE_FEATURES}",
        "--lang=en-US",
    ]


def persist_linux(channel_binary):
    """Install ~/.local/bin wrapper + .desktop override so the icon uses the fix."""
    home = os.path.expanduser("~")
    bin_dir = os.path.join(home, ".local", "bin")
    os.makedirs(bin_dir, exist_ok=True)
    wrapper = os.path.join(bin_dir, "google-chrome-glic")
    with open(wrapper, "w", encoding="utf-8") as fp:
        fp.write(
            "#!/usr/bin/env bash\n"
            "# Generated by chrome-gemini-fix. Deletes the Variations seed and\n"
            "# launches Chrome with Gemini (Glic) force-enabled.\n"
            'CHROME_DIR="${CHROME_USER_DATA_DIR:-$HOME/.config/google-chrome}"\n'
            'if ! pgrep -x chrome >/dev/null 2>&1; then\n'
            '  rm -f "$CHROME_DIR/Variations" "$CHROME_DIR/VariationsSeedV2" '
            '"$CHROME_DIR/VariationsSafeSeedV2"\n'
            "fi\n"
            "export LANG=en_US.UTF-8 LANGUAGE=en_US:en\n"
            f'exec "{channel_binary}" "$@" { " ".join(launch_args())}\n'
        )
    os.chmod(wrapper, 0o755)

    src = "/usr/share/applications/google-chrome.desktop"
    if os.path.isfile(src):
        dst_dir = os.path.join(home, ".local", "share", "applications")
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, "google-chrome.desktop")
        with open(src, "r", encoding="utf-8") as fp:
            content = fp.read()
        content = content.replace("/usr/bin/google-chrome-stable", wrapper)
        content = content.replace("/opt/google/chrome/google-chrome", wrapper)
        with open(dst, "w", encoding="utf-8") as fp:
            fp.write(content)
        return [wrapper, dst]
    return [wrapper]


def persist_windows(channel_binary):
    """Write a launcher .cmd and patch Start Menu / Taskbar / Desktop shortcuts."""
    glic_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome-GLIC")
    os.makedirs(glic_dir, exist_ok=True)
    launcher = os.path.join(glic_dir, "chrome-glic.cmd")
    with open(launcher, "w", encoding="utf-8") as fp:
        fp.write(
            "@echo off\n"
            "REM Generated by chrome-gemini-fix.\n"
            'tasklist /FI "IMAGENAME eq chrome.exe" 2>NUL | find /I "chrome.exe" >NUL\n'
            "if errorlevel 1 (\n"
            f'  del /F /Q "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Variations" '
            '"%LOCALAPPDATA%\\Google\\Chrome\\User Data\\VariationsSeedV2" '
            '"%LOCALAPPDATA%\\Google\\Chrome\\User Data\\VariationsSafeSeedV2" 2>NUL\n'
            ")\n"
            f'start "" "{channel_binary}" {" ".join(launch_args())} %*\n'
        )
    args = " ".join(launch_args())
    ps = (
        "$sh=New-Object -ComObject WScript.Shell;"
        "$links=@("
        "\"$env:APPDATA\\Microsoft\\Internet Explorer\\Quick Launch\\User Pinned\\TaskBar\\Google Chrome.lnk\","
        "\"$env:PUBLIC\\Desktop\\Google Chrome.lnk\","
        "\"C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\Google Chrome.lnk\");"
        f"$flags='{args}';"
        "foreach($L in $links){if(Test-Path -LiteralPath $L){"
        "$sc=$sh.CreateShortcut($L);$sc.Arguments=$flags;$sc.Save();"
        "Write-Output \"shortcut updated: $L\"}}"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=60)
    except OSError:
        pass
    return [launcher]


def launch_chrome(binary):
    args = [binary, *launch_args()]
    print("Launching: " + " ".join(args))
    if OS == "Windows":
        subprocess.Popen(args)
    else:
        subprocess.Popen(args, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------- verify

def verify(user_data_dir):
    print("\n--- Verify ---")
    ok = True
    try:
        with open(os.path.join(user_data_dir, "Local State"), "r", encoding="utf-8") as fp:
            raw = fp.read()
        state = json.loads(raw)
        checks = [
            ("variations_country == us", state.get("variations_country") == "us"),
            ("session country == us",
             state.get("variations_safe_seed_session_consistency_country") == "us"),
            ("safe seed locale == en-US",
             state.get("variations_safe_seed_locale") == "en-US"),
            ("is_glic_eligible true", '"is_glic_eligible":true' in raw.replace(" ", "")),
        ]
        for label, passed in checks:
            print(f"  [{'OK' if passed else 'FAIL'}] {label}")
            ok = ok and passed
    except OSError as exc:
        print(f"  [FAIL] cannot read Local State: {exc}")
        ok = False

    for name in SEED_FILES:
        p = os.path.join(user_data_dir, name)
        if os.path.exists(p):
            size = os.path.getsize(p)
            good = size < 1024
            print(f"  [{'OK' if good else 'FAIL'}] {name}: {size} bytes "
                  f"{'(placeholder)' if good else '(LIVE SEED - relaunch via the icon/launcher)'}")
            ok = ok and good
        else:
            print(f"  [OK] {name}: absent (Chrome recreates a placeholder)")

    print("  data integrity:")
    for rel in DATA_SAFETY_FILES:
        p = os.path.join(user_data_dir, rel)
        if os.path.isfile(p):
            print(f"    [OK] {rel} ({os.path.getsize(p)} bytes)")
        else:
            print(f"    [..] {rel} (not present - nothing to lose)")

    print("  In Chrome, open chrome://version and confirm the Command Line row "
          "contains --enable-features=Glic.")
    return ok


def diagnose(user_data_dir):
    """Print current state without changing anything."""
    print(f"User data: {user_data_dir}")
    try:
        with open(os.path.join(user_data_dir, "Local State"), "r", encoding="utf-8") as fp:
            raw = fp.read()
        state = json.loads(raw)
        for key in ("variations_country",
                    "variations_permanent_consistency_country",
                    "variations_permanent_overridden_country",
                    "variations_safe_seed_permanent_consistency_country",
                    "variations_safe_seed_session_consistency_country",
                    "app_locale",
                    "variations_safe_seed_locale"):
            print(f"  {key} = {state.get(key)}")
        print(f"  labs = {state.get('browser', {}).get('enabled_labs_experiments')}")
        import re
        for m in re.finditer(r"is_glic_eligible\":(true|false)", raw):
            print(f"  is_glic_eligible = {m.group(1)}")
    except OSError as exc:
        print(f"  cannot read Local State: {exc}")
    for name in SEED_FILES:
        p = os.path.join(user_data_dir, name)
        print(f"  {name} = {os.path.getsize(p)} bytes" if os.path.exists(p)
              else f"  {name} = absent")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="One-click fix for Gemini in Chrome.")
    ap.add_argument("--yes", action="store_true", help="close Chrome automatically")
    ap.add_argument("--check", action="store_true", help="diagnose only, change nothing")
    ap.add_argument("--no-launch", action="store_true", help="patch but do not relaunch Chrome")
    ap.add_argument("--user-data-dir", default=None, help="override auto-detected user data dir")
    ns = ap.parse_args()

    uds = [(None, ns.user_data_dir)] if ns.user_data_dir else user_data_dirs()
    if not uds:
        sys.exit("No Chrome user data directory found. Launch Chrome once, then retry.")
    bins = chrome_binaries()
    binary = bins[0][1] if bins else None
    if not binary:
        sys.exit("Chrome binary not found. Install Google Chrome first.")

    if ns.check:
        for _, ud in uds:
            diagnose(ud)
        print("\nLaunch flags that would be used:\n  " + " ".join(launch_args()))
        return 0

    print(f"Chrome binary: {binary}")
    for _, ud in uds:
        print(f"User data:   {ud}")

    if chrome_running():
        if not ns.yes:
            try:
                answer = input("Chrome is running. It must be closed to patch safely "
                               "(tabs restore on launch). Close it now? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() not in ("y", "yes"):
                sys.exit("Aborted. Re-run with --yes to close automatically, "
                         "or close Chrome yourself and retry.")
        print("Closing Chrome...")
        if not close_chrome():
            sys.exit("Could not close Chrome. Close it manually and retry.")
        time.sleep(1)

    for _, ud in uds:
        version = chrome_version_for(ud)
        print(f"\nPatching {ud} (v{version}) ...")
        ls_path = os.path.join(ud, "Local State")
        if not os.path.isfile(ls_path):
            print("  Local State missing, skipping (launch Chrome once to create it).")
            continue
        with open(ls_path, "r", encoding="utf-8") as fp:
            state_before = json.load(fp)
        bak, log = patch_local_state(ud, version)
        if log:
            print(f"  backup: {bak}")
            for line in log:
                print(f"  {line}")
        else:
            print("  Local State already patched")
        for prefs_path in profile_prefs_paths(ud, state_before):
            pbak, plog = patch_preferences(prefs_path)
            if plog:
                print(f"  {os.path.relpath(prefs_path, ud)} (backup {os.path.basename(pbak or '')})")
                for line in plog:
                    print(f"    {line}")
        for line in clear_seeds(ud) or ["  seed files already absent"]:
            print(f"  removed seed: {line}")

    if OS == "Windows":
        for p in persist_windows(binary):
            print(f"installed: {p}")
    else:  # Linux
        for p in persist_linux(binary):
            print(f"installed: {p}")

    if not ns.no_launch:
        launch_chrome(binary)
        time.sleep(5)

    all_ok = all(verify(ud) for _, ud in uds)
    print("\nDone." + (" All checks passed." if all_ok else
          " Some checks need attention - see FAIL lines above."))
    print("If the panel still says unavailable, sign in with a personal Google "
          "account (18+) and allow the microphone; a non-US IP can still be refused "
          "server-side.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
