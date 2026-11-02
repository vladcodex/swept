# Testing

This file exists because someone asked a fair question: *what is your test plan?*
Not "is it tested" — every project says that — but what exactly is checked, how, and
what is left unchecked.

The short version: the delete path is covered by automated tests and runs in CI.
The GUI, the installer and the DISM wrapper are not. That gap is real and it is
listed below rather than hidden.

## How to run the automated part

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .
```

239 tests, about two seconds. CI runs the same two commands on `windows-latest`
with Python 3.12 and 3.13 on every push and pull request
(`.github/workflows/tests.yml`).

## What the automated tests cover

| Area | File | What is asserted |
|---|---|---|
| Blacklist | `tests/test_safety.py` | Windows subdirectories, `Program Files`, `Program Files (x86)`, `ProgramData`, Start Menu, critical files by name (`pagefile.sys`, `ntldr`, `bootmgr`…), service folders on any drive, `$Recycle.Bin` |
| Narrow exceptions | `tests/test_safety.py` | `System32\LogFiles`, `winevt\Logs`, Steam cache and `steamapps\downloading` are *allowed*; `steamapps\common` game saves are not |
| Root checks | `tests/test_safety.py` | A drive root, a single-level path, the profile, `%APPDATA%` itself are refused as cleanup roots; a real cache directory is accepted |
| Personal folders | `tests/test_safety.py` | `Documents`, `Desktop`, `Downloads`, OneDrive outside the profile are flagged sensitive |
| Reparse points | `tests/test_safety.py` | A junction is detected as a reparse point; a regular file and a missing path are not |
| Whitelist | `tests/test_delete.py` | A path enters the whitelist only through a directory the category produced, or through an explicit file job; `C:\Temp\a` is not inside `C:\Temp\ab` |
| Delete path | `tests/test_delete.py` | Garbage input, a protected file inside an allowed folder, a file outside the whitelist, a missing file, dry run, read-only files, the stop event, progress throttling, removal of emptied directories |
| Junction escape | `tests/test_delete.py` | A real junction inside the cache directory pointing at `Documents` must be refused, even though the junction itself sits inside an allowed folder |
| Settings | `tests/test_settings.py` | Registry and file storage, round trip, missing value, broken JSON, case-insensitive cache, and the regression where a failed write still left the value in the cache |
| Update check | `tests/test_version.py` | The version parser (a date in a release title is not a version), `is_newer`, the URL allowlist, and the contract that `check()` reports every failure as a status instead of raising |
| Rollback journal | `tests/test_journal.py` | A snapshot is taken *before* the write and holds the previous value; a second run never overwrites the original snapshot; undo restores an existing value, deletes one that did not exist, and refuses to guess when the old value could not be read; a `powercfg` scheme GUID from the journal is validated before use; unknown entry kinds fail cleanly |
| Restore points | `tests/test_restore.py` | JSON from PowerShell (object vs array vs empty), points sorted newest first, entries without a number dropped, restore point numbers validated as integers, "protection disabled" vs "access denied" reported separately, and `restore_to_point` refusing a bad number or a non-elevated process before any command runs |

The tests build a temporary fake system — their own `%LOCALAPPDATA%`, `%SystemRoot%`,
`Program Files` — inside `tmp_path`. They never read the real profile and cannot delete
anything outside the temporary directory.

## Does the suite actually catch anything

A green test suite proves nothing on its own, so the code was broken on purpose three
times to see whether the tests notice:

| Deliberate break | Result |
|---|---|
| `is_protected` check removed from `safe_delete_file` | 2 tests fail |
| Root check `clean_root_reason` made unconditional | 1 test fails |
| Personal-folder check on the allowed directory removed | **nothing failed at first** |

The third one was a hole in the tests, not in the code: `build_allowed` rejects such
directories earlier, so the last line of defence was never exercised.
`test_allowed_dir_inside_documents_is_refused` builds the whitelist by hand to reach it.
After that test was added, the break is caught too.

## What is checked by hand before a release

Not automated. This is the part the author runs on a real machine, and it is the weakest
part of the process — there is one person and no second pair of eyes.

1. Build with `python build.py`, run the packaged binary, not the source.
2. Analyze on a fresh Windows 11 VM, then compare the file count and size in the log
   against `%TEMP%` and `%LOCALAPPDATA%` measured in Explorer.
3. Run a full clean on that VM with a snapshot taken beforehand. Restore the snapshot and
   confirm the profile is intact.
4. Create a junction inside a temp folder pointing at `Documents`, run cleanup, confirm
   the junction is skipped and the documents are still there.
5. Install and uninstall through the installer; confirm the registry key is removed and
   no files are left in `Program Files`.
6. Check the signature: `Get-AuthenticodeSignature` on both the binary and the installer,
   and confirm the timestamp is present.
7. Run the portable build with `swept.portable` next to the exe and confirm nothing is
   written to the registry.
8. Verify the published SHA-256 against the downloaded file.
9. Apply a tweak, press `↩` on its card and confirm the previous value is back in `regedit`
   (or `python cleaner_optimize.py --journal` before and after).
10. Hide the window to the tray, double-click the icon, confirm it returns; start the exe a
    second time and confirm the second copy raises the first window instead of opening.

## What is not covered at all

Stated plainly, because this is the list that matters:

* **The GUI.** No tests. Threading between the scan worker and the widget updates is
  verified by using the program, not by assertions.
* **The tray icon.** `cleaner_tray.py` has no automated tests: it is a `ctypes` wrapper
  around `Shell_NotifyIcon`, and checking it means looking at the notification area —
  clicking the menu, hiding the window, restarting Explorer. Done by hand, per release.
* **The rollback window.** The journal itself is tested, but the dialog that drives it
  (list, per-item undo, restore point list, restore) is checked by using it.
* **An actual system restore.** `Restore-Computer` reboots the machine, so no test runs
  it. Only the argument building and the refusal paths are asserted.
* **The installer tab.** Downloading from vendor CDNs, signature and hash verification,
  silent-install argument vectors — checked by installing the programs, not by tests.
* **The DISM wrapper.** The command is an argument vector with `shell=False` and
  `ResetBase` is never passed, but nothing asserts that at runtime.
* **The 12 tweaks.** Each is applied on a VM and reverted by hand.
* **Elevation.** Whether the app behaves correctly when UAC is declined is checked
  manually and only on one machine.
* **Windows 10.** Development and testing happen on Windows 11. Windows 10 is supported
  in the sense that the code paths are the same, not in the sense that it is tested.
* **The Operations log.** Nothing asserts that a path which fails to delete still reaches
  the log, and nothing checks the 3000-line cap or the backlog behind it.

## If you find something

The most useful report is a path that gets deleted although it should not.

Open an issue with the category you had selected, and the lines from the Operations log tab.
During a clean that log writes every path it removes or refuses, with the full path, so it says
*what* happened rather than *how much*. It lives in the window: capped at 3000 lines, held in
memory, not written to a file, and there is no export button. Select the text and copy it.

That missing export is a known annoyance and the log itself has no tests.

A reproduction beats a verdict.
