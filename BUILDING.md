# Building and running Swept from source

Everything in this file is for developers and for scripting. If you just want to use the program,
download it from the [releases page](https://github.com/vladcodex/swept/releases/latest) — the
portable `Swept.exe` needs no Python.

## Requirements

- Windows 10 or 11
- Python 3.10+ (developed and tested on 3.15) with `tkinter`
- `customtkinter`, `requests` and `pywin32` (from `requirements.txt`) — the last two only for the
  Install tab: HTTPS download and the folder ACL

## Run from source

```bat
git clone https://github.com/vladcodex/swept.git
cd swept
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python cleaner_gui.py
```

## Build the app

```bat
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python build.py
```

The result is a folder `dist\Swept\` — `Swept.exe` plus its `_internal\` runtime, no console
window, custom icon, version resource and a `requireAdministrator` manifest.

This is an **onedir** (folder) build by design. A single-file "onefile" build unpacks itself
into `%TEMP%\_MEIxxxxx` at launch and runs from there — a drop-and-execute pattern that
reliably trips antivirus heuristics (e.g. Microsoft `Trojan.Win32/Wacast`) and gets the
binary flagged as malware. Keep the default unless you truly need one file.

```bat
python build.py --no-admin    :: do not request elevation
python build.py --onefile     :: single self-extracting exe (NOT recommended: AV false positives)
python build.py --console     :: keep the console for debugging
```

The build environment must have `customtkinter` installed: the GUI imports it inside a
`try/except ImportError`, so PyInstaller otherwise treats it as optional and leaves it out.

## Build the installer

The Inno Setup installer bundles the whole `dist\Swept\` folder into *Program Files*, creating a
Start Menu shortcut and an entry in *Apps & Features*. Compile it (install Inno Setup 6 first
from [jrsoftware.org](https://jrsoftware.org/isdl.php)):

```bat
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\setup.iss
```

The result is `dist\Swept-Setup-<version>.exe` — a bilingual (RU/EN) installer that asks for
administrator rights, installs to `Program Files`, offers a desktop shortcut as an optional task
and ships `README.md` and `LICENSE` next to the program.

## Command line

The three modules also work on their own — handy for scripts and scheduled tasks.

```bat
:: scan only, nothing is deleted
python cleaner_core.py --scan --only temp_user,chrome,recycle

:: real cleanup, no questions asked
python cleaner_core.py --clean --only recycle --yes

:: installers (download, signature check, silent install)
python cleaner_installer.py --list
python cleaner_installer.py --check steam
python cleaner_installer.py --install steam gog

:: safe Windows tweaks (a restore point is created before applying)
python cleaner_optimize.py --list
python cleaner_optimize.py --apply telemetry,advertising,search_suggest
```

## Project layout

| File | Purpose |
|---|---|
| `cleaner_gui.py` | CustomTkinter interface, worker threads, message queue |
| `cleaner_core.py` | Categories, scanning, safe deletion, Recycle Bin |
| `cleaner_installer.py` | Hardened direct installer: pinned HTTPS sources, signature or hash check, isolated staging folder, silent launch |
| `cleaner_optimize.py` | Registry and `powercfg` tweaks, Windows version detection |
| `cleaner_i18n.py` | Interface strings (RU/EN), language switching, unit formatting |
| `cleaner_settings.py` | Settings storage: `HKEY_CURRENT_USER\Software\Swept`, JSON fallback |
| `build.py` | PyInstaller wrapper with icon, version resource and manifest |
| `installer/setup.iss` | Optional Inno Setup script — a classic Windows installer |

## How the interface language is stored

The choice is kept in the registry (no administrator rights needed, and it follows the user rather
than the folder):

```
HKEY_CURRENT_USER\Software\Swept
    Language    REG_SZ    "ru" | "en"
```

Missing value means Russian. A `settings.json` written by versions before 1.1 is migrated once; if
the registry is unavailable, the file is used as a fallback.

To add a language: copy the `"en"` block in `cleaner_i18n.py`, add `title_xx` / `desc_xx` fields to
the data in `cleaner_core.py` and `cleaner_optimize.py`, then register the code in `LANGUAGE_NAMES`,
`LANGUAGE_ORDER` and `SUPPORTED_LANGUAGES`.

## Extending the catalog

The Install tab ships a fixed catalog instead of a searchable repository: the list and every
download URL are hardcoded on purpose, so the program can never be pointed at an arbitrary address.
Adding a program means adding an entry to `CATALOG` in `cleaner_installer.py` with its URL, silent
switches, and either the expected publisher or a pinned SHA-256.

Version-pinned entries (7-Zip, K-Lite, WinRAR, VLC, SumatraPDF, LibreOffice, Everything, Notepad++,
PowerToys) need their `url` updated when the vendor ships a new build — and for 7-Zip and K-Lite the
`sha256` must be updated together with it, otherwise the install is refused. That is the hash doing
its job.
