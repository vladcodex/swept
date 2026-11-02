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

Build the portable archive from a *non-portable* `dist\Swept\` plus the marker, so the installed
copy never ends up in portable mode:

```bat
mkdir .build\portable_stage
xcopy /E /I dist\Swept .build\portable_stage\Swept
copy LICENSE .build\portable_stage\Swept\
copy README.md .build\portable_stage\Swept\
echo portable> .build\portable_stage\Swept\swept.portable
:: then zip the Swept folder itself, so the archive root is Swept\
```

The two `copy` lines are not optional. The installer puts `LICENSE` and `README.md` next to the
program, and the MIT licence requires the notice to travel with every copy — the archive is a
copy. Release 1.5.1 shipped without them, which is the kind of detail someone auditing a
self-signed binary will notice first.

## Sign the binaries

Both `dist\Swept\Swept.exe` and `dist\Swept-Setup-<version>.exe` carry an Authenticode signature
with a DigiCert timestamp. The certificate is a **file**, not something installed on the machine
that runs the build or the app:

| File | Purpose |
| --- | --- |
| `.build\signing\Vladcodex.pfx` | private key + certificate (PKCS#12) |
| `.build\signing\Vladcodex.cer` | public certificate, for inspection |
| `.build\signing\pfx-password.txt` | password for the `.pfx` |

None of these files are kept in the repository — create them when you need to sign:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File .build\make_signing_cert.ps1
```

The script mints the certificate, exports the two files and then **removes it from the Windows
certificate store again** (`Cert:\CurrentUser\My` and the `CA` copy Windows makes on its own), so
afterwards the files are the only copy. Delete the `.pfx` and nothing is left on the machine.

`.build\` is gitignored, so none of this is committed, and none of it is shipped: the installer
packages `dist\Swept\*` only, and nothing in the app or in `setup.iss` touches a certificate
store. The signing script loads the key with `EphemeralKeySet`, so it stays in memory for the
duration of the run — `Cert:\CurrentUser\*` is never written.

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File .build\sign.ps1
```

Sign **after** building and **before** zipping, so the archive contains the signed exe. The
signature is self-signed (`CN=Vladcodex`), which means the signature verifies as present and
timestamped but the chain is untrusted: UAC and SmartScreen still say "Unknown publisher". For
real distribution trust, replace the `.pfx` with a trusted OSS code-signing certificate and point
`$pfxPath` in `sign.ps1` at it.

`sign.ps1` signs `dist\Swept\Swept.exe` and the installer **for the current version**:
it reads `VERSION` from `build.py` and looks for `dist\Swept-Setup-<version>.exe`. If that file is
not there yet, it says so and signs the app exe only — it never falls back to "the newest
`Swept-Setup-*.exe` in the folder". That fallback was the old behaviour and it was a trap: with a
previous release's installer still in `dist\`, the script silently re-signed that file and left the
new one unsigned, rewriting the bytes of an already published artifact. The order is:

```bat
build.py            :: dist\Swept\
sign.ps1            :: the app exe
ISCC setup.iss      :: dist\Swept-Setup-<version>.exe
sign.ps1            :: the installer
```

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

### Machine-readable output

`cleaner_core.py` can answer a script instead of a human:

```bat
:: JSON on stdout, no progress lines (requires --yes together with --clean)
python cleaner_core.py --only temp_user --json

:: report next to the log: .json, .html or .txt is chosen by extension
python cleaner_core.py --clean --only temp_user,recycle --yes --report report.html

:: only the summary, one line per category
python cleaner_core.py --scan --quiet
```

Exit codes are part of the contract, so a scheduled task can tell "nothing to do" from "some files
could not be deleted":

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | The run failed (scan or cleanup raised an error) |
| 2 | Bad arguments (unknown category, report directory does not exist, `--json --clean` without `--yes`) |
| 3 | Cleanup finished, but some files were refused (access errors). Locked files counted as *skipped* are normal and do not set this code |
| 4 | Cancelled by the user at the confirmation prompt |

### Rolling back tweaks

Every registry value and every `powercfg` call made by the optimize module is journalled with its
previous value before it is changed, so it can be undone without a system restore:

```bat
:: what can be undone, and how many values each item holds
python cleaner_optimize.py --journal

:: undo one item or everything
python cleaner_optimize.py --undo telemetry
python cleaner_optimize.py --undo-all
```

The journal lives in the settings store (`HKCU\Software\Swept\TweakJournal`, or `settings.json` in
the portable build) and is capped at 64 items. Re-applying an item never overwrites its original
snapshot: undoing always returns the machine to the state it had before Swept touched it, not to a
half-applied state.

### Restore points

```bat
:: list the points Windows has created (needs administrator rights)
python cleaner_restore.py
```

`cleaner_restore.py` only wraps the built-in cmdlets (`Get-ComputerRestorePoint`,
`Checkpoint-Computer`, `Restore-Computer`); it has no restore logic of its own, and the restore point
number is validated as an integer before it is put anywhere near a command line.

## Tests

The suite covers the parts that must not break: the whitelist, the blacklist, the reparse-point
escape, the settings store and the update check. It does not need the GUI library and does not touch
the real system — every test runs against a temporary fake `%LOCALAPPDATA%`, `%SystemRoot%` and
`Program Files`.

```bat
pip install -r requirements-dev.txt
python -m pytest          :: all tests
python -m pytest -k delete :: only the delete path
python -m ruff check .    :: lint
```

Both commands are what CI runs on every push (`.github/workflows/tests.yml`), so a local run that
passes means the same thing it means on GitHub.

Two notes when adding tests:

- Use the `fake_env` fixture from `tests/conftest.py` instead of the real environment, and call
  `cleaner_core.reset_protection_cache()` if you change `USERPROFILE` / `SystemRoot` yourself —
  otherwise the cached protection lists still describe the old paths.
- Never point a test at a real folder. Everything a test creates belongs in `tmp_path`.

## Project layout

| File | Purpose |
|---|---|
| `cleaner_gui.py` | CustomTkinter interface, worker threads, message queue |
| `cleaner_core.py` | Categories, scanning, safe deletion, Recycle Bin |
| `cleaner_installer.py` | Hardened direct installer: pinned HTTPS sources, signature or hash check, isolated staging folder, silent launch |
| `cleaner_optimize.py` | Registry and `powercfg` tweaks, Windows version detection, registry snapshot journal and per-item undo |
| `cleaner_restore.py` | Windows restore points: list, create, restore (wraps the built-in cmdlets only) |
| `cleaner_tray.py` | Tray icon and menu via `ctypes`/`Shell_NotifyIcon` — no extra dependency |
| `cleaner_i18n.py` | Interface strings (RU/EN), language switching, unit formatting |
| `cleaner_settings.py` | Settings storage: `HKEY_CURRENT_USER\Software\Swept`, JSON fallback |
| `build.py` | PyInstaller wrapper with icon, version resource and manifest |
| `installer/setup.iss` | Optional Inno Setup script — a classic Windows installer |
| `tests/` | pytest suite for the safety model, settings and update check |
| `ruff.toml`, `pytest.ini` | Lint and test configuration |
| `requirements-dev.txt` | Test and lint dependencies (not shipped in the build) |

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
