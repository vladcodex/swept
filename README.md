# Swept

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6.svg)](https://github.com/vladcodex/swept)
[![Version](https://img.shields.io/badge/Version-1.1.3-brightgreen.svg)](https://github.com/vladcodex/swept/releases/latest)
[![UI](https://img.shields.io/badge/UI-%D0%A0%D0%A3%20%2F%20EN-lightgrey.svg)](https://github.com/vladcodex/swept)

**One window to clean, install and tune Windows 10/11 — safely.**

Free and open source, with a dark bilingual interface (Русский / English):

- 🧹 **Clean** — temp files, browser caches, Windows Update cache, Recycle Bin, logs, dumps
  and game-launcher junk. Analyze first, delete only what you confirm.
- 📦 **Install** — game launchers, browsers, chat apps, office, media, archivers and utilities
  (24 programs), downloaded straight from the vendor's own HTTPS CDN, verified by signature or
  pinned hash, and installed silently from an isolated folder.
- ⚡ **Optimize** — 12 safe Windows tweaks (telemetry, power plan, background apps, Game DVR,
  widgets…) with a system restore point created before any change.

No telemetry, no bundled offers, no background services — and every deleted file and
changed setting is written to the log.

**[⬇ Download the latest release](https://github.com/vladcodex/swept/releases/latest)** —
either the portable `Swept.exe` (just run it) or `Swept-Setup-1.1.3.exe` (a normal Windows
installer with a Start Menu shortcut and a proper uninstaller).

![Swept — cleanup tab](docs/cleanup-en.png)

---

## Contents

- [What it does](#what-it-does)
- [Safety model](#safety-model)
- [Requirements](#requirements)
- [Run from source](#run-from-source)
- [Build a single .exe](#build-a-single-exe)
- [Build the installer](#build-the-installer-optional)
- [Command line](#command-line)
- [Project layout](#project-layout)
- [Localization](#localization)
- [Limitations](#limitations)
- [Found a bug?](#found-a-bug)
- [Questions and ideas](#questions-and-ideas)
- [Disclaimer](#disclaimer)
- [License](#license)
- [По-русски](#по-русски)

---

## What it does

### 🧹 Cleanup

| Group | Categories |
|---|---|
| Quick cleanup | User temp (`%TEMP%`), system temp (`C:\Windows\Temp`), Windows update cache, `.log` / `.dmp` files, Recycle Bin |
| Browser cache | Chrome, Yandex Browser, Edge, Firefox — cache, history, cookies |
| Game launchers | Steam, Epic, Ubisoft Connect, EA App, Battle.net, GOG Galaxy — caches, logs, temp data |

- **Analyze first, delete later.** The Analyze button only measures; nothing is touched until you press Clean.
- **Scan-only switch.** Even the Clean button can run in simulation mode.
- **Live log** with the full path of every deleted or skipped file.
- Running browsers are detected and skipped instead of being broken mid-session.

### 📦 Install

No `winget`, no package manager, no bundled downloader — the Install tab fetches each
installer directly from the vendor's own CDN over HTTPS. Seven sets, 24 programs:

| Set | Programs |
|---|---|
| Game launchers | Steam, Epic Games Launcher, EA App, Ubisoft Connect, GOG Galaxy |
| Browsers | Google Chrome, Mozilla Firefox, Yandex Browser, Opera |
| Chat and calls | Telegram, Discord, Zoom, Slack |
| Office | ONLYOFFICE, LibreOffice, SumatraPDF |
| Media | VLC, K-Lite Codec Pack Basic, Spotify |
| Archivers | 7-Zip, WinRAR |
| Utilities | Everything, Notepad++, Microsoft PowerToys |

Plus the **Visual C++ Redistributable** 2015–2022, x64 and x86, installed in sequence.

- The **Choose** button opens the set as a list with checkboxes, so you install exactly what
  you need, not the whole set. Every entry is also reachable by typing its name in the search box.
- Every download is verified before it runs, in one of two ways. The URL is always pinned in the
  code and the TLS chain must be valid. Then either the file must carry a valid Authenticode
  signature from the expected publisher (`Google LLC`, `Mozilla`, `Yandex`, `Opera Norway`,
  `Ascensio System`, `Spotify AB`, `Telegram`, `Discord`, `Zoom`, `Slack`, `VideoLAN`,
  `win.rar GmbH`, `Krzysztof Kowalczyk`, `voidtools`, `NOTEPAD++`, `Document Foundation`,
  `Microsoft`, `Valve`, `Epic Games`, `Electronic Arts`, `Ubisoft`, `GOG`), **or** — for vendors
  who do not sign their installers at all — its SHA-256 must match the hash pinned in the
  catalog. A file that fails is deleted and the install is refused; an entry with neither a
  publisher nor a hash is rejected outright, so "it downloaded, therefore it is fine" can never
  happen.
- **7-Zip and K-Lite are the hash-pinned pair.** Both ship genuinely unsigned installers
  (`WinVerifyTrust` and `Get-AuthenticodeSignature` agree: `NotSigned`), and that check is never
  bypassed. Their URLs are version-specific, so the bytes are fixed — pinning the SHA-256 binds
  the exact artifact that was reviewed, which is a tighter guarantee than a name in a
  certificate. The trade-off is visible: a new vendor release means updating both `url` and
  `sha256`.
- The installer executes from `%ProgramData%\SweptSecureTemp`, a folder whose ACL allows only
  `SYSTEM` and `Administrators`, and is wiped in a `finally` block whatever the outcome.

**What is deliberately missing.** A program is only listed if it can actually be fetched and
verified, so the following are not in the catalog: **NanaZip** is a `.msixbundle` installed
through `Add-AppxPackage` rather than an exe; **qBittorrent** lives on SourceForge, which answers
403 to a programmatic request; **Foxit Reader** and **Adobe Acrobat Reader** have no direct file
link, only a form page.

Some entries use version-pinned URLs — 7-Zip, K-Lite, WinRAR, VLC, SumatraPDF, LibreOffice,
Everything, Notepad++, PowerToys — so their `url` (and `sha256`, where present) needs updating
when the vendor ships a new build. The rest point at a permanent "latest version" endpoint and
do not rot.

![Install tab](docs/install-presets-ru.png)

### ⚡ Optimize

Twelve safe tweaks in two groups — before any change Swept creates a system restore point:

- **Basic settings** — telemetry, advertising ID and suggestions, high-performance power plan, hibernation, background apps, Game DVR, startup delay, visual effects.
- **Full debloat** — built-in promo/game apps (Weather, News, Maps, Skype, Solitaire, Candy Crush…), taskbar widgets and Copilot, web search suggestions, Windows Error Reporting.

Every item states what it changes and whether it needs administrator rights; before applying, Swept makes a system restore point.

While the run is going, the **Progress** panel lists every selected item and marks it live:
`⏳` being applied now (with a "3 of 8" counter and the item name), `✔` done, `⛔` skipped or
unavailable — with the reason written right into the row — and `⚠` failed.

**Restore point** (`🛡`) — Swept creates a Windows system restore point (PowerShell
`Checkpoint-Computer`) **before** applying any tweak, so you can always roll back through
the standard *Control Panel → Recovery* path. There is also a dedicated **Restore point**
button to create one at any time, without applying optimizations. Built-in apps removed by
the debloat step cannot be restored automatically — the app says so and points to Microsoft Store.
From the command line: `python cleaner_optimize.py --apply telemetry`.

![Optimize tab](docs/optimize-ru.png)

---

## Safety model

Swept is built around the assumption that a cleaner must never be able to eat your system:

1. **Whitelist first.** A file is deleted only if it is inside a folder produced by the
   category's own job list — never by a free-form path.
2. **Hard blacklist.** `System32`, `WinSxS`, `Fonts`, `servicing`, `Program Files`, the Recycle Bin
   folder itself and similar locations are never entered. Narrow exceptions exist for
   `System32\LogFiles`, `winevt\Logs` and specific Steam cache folders.
3. **Protected files.** `pagefile.sys`, `hiberfil.sys`, `bootmgr`, `ntuser.dat`, `bcd` and friends
   are refused by name.
4. **Dry run by default in the CLI**, one explicit confirmation in the GUI before real deletion.
5. **Errors never stop the run** — a locked file is counted as "skipped", not as a crash.
6. **No network access** except the HTTPS downloads you explicitly start from the Install tab,
   and no data collection of any kind.
7. **Links are never followed.** Junctions, symlinks and other reparse points are skipped during
   scanning and refused during deletion. A `%TEMP%` junction pointing at `Documents` would otherwise
   turn "clear temporary files" into "delete my documents" — so the real target path is checked
   against the whitelist as well, and personal folders (`Documents`, `Desktop`, `Downloads`,
   `Pictures`, OneDrive…) are refused even when they appear inside an allowed root.
8. **No `PATH` lookups for elevated tools.** The packaged app runs as administrator, so
   `powercfg`, `tasklist`, `msiexec` and `powershell` are resolved to their real files in
   `%SystemRoot%\System32` instead of being taken from `PATH`, where a planted executable
   would inherit elevation.
9. **No shell string ever reaches the OS.** Installers are started as an argument vector with
   `shell=False`: the path and every silent-install switch are separate list elements, and the
   switches come from a hardcoded catalog rather than from anything typed by the user. There is
   no `os.system` and no `shell=True` anywhere in the module.
10. **Downloaded files are not trusted until they prove themselves.** A file is executed only
    after it passes one of two checks: `WinVerifyTrust` returns success *and* the signer's name
    matches the publisher declared for that package, or its SHA-256 matches the hash pinned in
    the catalog (the case for vendors who ship unsigned installers). An entry with neither a
    publisher nor a hash is refused, so no package can be trusted merely for having downloaded.
    The handle is opened with `FILE_SHARE_READ` and held across verification and launch, and the
    hash is recomputed from disk under that lock, so the binary cannot be swapped in between
    (TOCTOU).
11. **The staging folder is not writable by users.** `%ProgramData%\SweptSecureTemp` carries a
    protected DACL with `SYSTEM` and `Administrators` only, inheritance disabled — which also
    blocks DLL hijacking from a normal user session.

Administrator rights are optional. Without them, `C:\Windows\Temp` and the update cache are
skipped; the app tells you so instead of failing silently. The packaged `.exe` requests
elevation through its manifest.

---

## Requirements

- Windows 10 or 11
- Python 3.10+ (developed and tested on 3.15) with `tkinter`
- `customtkinter`, `requests` and `pywin32` (installed from `requirements.txt`) — the last two
  only for the Install tab: HTTPS download and the folder ACL

Administrator rights are optional. Without them the system locations (`C:\Windows\Temp`,
the update cache) are skipped and reported instead of failing silently.

## Run from source

```bat
git clone https://github.com/vladcodex/swept.git
cd swept
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python cleaner_gui.py
```

## Build a single .exe

```bat
.venv\Scripts\pip install pyinstaller
.venv\Scripts\python build.py
```

The result is `dist\Swept.exe` — one file, no console window, custom icon, version resource
and a `requireAdministrator` manifest.

Useful flags:

```bat
python build.py --no-admin    :: do not request elevation
python build.py --onedir      :: folder build, faster startup
python build.py --console     :: keep the console for debugging
```

The build environment must have `customtkinter` installed: the GUI imports it inside a
`try/except ImportError`, so PyInstaller otherwise treats it as optional and leaves it out.

### Build the installer (optional)

`dist\Swept.exe` is a portable program — it runs without being installed. If you want a
classic Windows setup with a Start Menu shortcut and an entry in *Apps & Features*,
compile the Inno Setup script (install Inno Setup 6 first from
[jrsoftware.org](https://jrsoftware.org/isdl.php)):

```bat
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer\setup.iss
```

The result is `dist\Swept-Setup-1.1.3.exe` — a bilingual (RU/EN) installer that asks for
administrator rights, installs to `Program Files`, and offers a desktop shortcut as an
optional task. It also ships `README.md` and `LICENSE` next to the program.

---

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
| `cleaner_installer.py` | Hardened direct installer: pinned HTTPS sources, Authenticode check, isolated staging folder, silent launch |
| `cleaner_optimize.py` | Registry and `powercfg` tweaks, Windows version detection |
| `cleaner_i18n.py` | Interface strings (RU/EN), language switching, unit formatting |
| `cleaner_settings.py` | Settings storage: `HKEY_CURRENT_USER\Software\Swept`, JSON fallback |
| `build.py` | PyInstaller wrapper with icon, version resource and manifest |
| `installer/setup.iss` | Optional Inno Setup script — a classic Windows installer (Start Menu shortcut, uninstaller) |

## Localization

The interface ships with Russian and English. The language is chosen from a dropdown in the
header and switches **instantly, without restarting** — every widget is rebuilt in place.

**Where the choice is stored** (Reg Organizer style): the registry, not a config file.

```
HKEY_CURRENT_USER\Software\Swept
    Language    REG_SZ    "ru" | "en"
```

- `HKCU` needs no administrator rights, and the setting follows the user, not the folder —
  move the exe anywhere and the language stays.
- On start the value is read from the registry; if it is missing, Russian is used.
- Selecting a language writes the new value immediately (`winreg`, `REG_SZ`).
- A `settings.json` written by versions before 1.1 is migrated into the registry once;
  if the registry is unavailable (policy, non-Windows), the file is used as a fallback.

To add a language:

1. Copy the `"en"` block in `cleaner_i18n.py` under a new language code and translate the values.
2. Add `title_en`-style fields (`title_xx`, `desc_xx`) to the data in `cleaner_core.py` and
   `cleaner_optimize.py`, or extend `i18n.fld()` with your suffix.
3. Add the code to `LANGUAGE_NAMES` and `LANGUAGE_ORDER` so it appears in the dropdown.
4. Add it to `SUPPORTED_LANGUAGES` in `cleaner_settings.py` so it can be stored.

## Limitations

- Registry tweaks are written directly; Windows may re-apply some of them after a feature update.
- Recent Windows 11 builds (24H2 and later) protect some shell values — for example `TaskbarDa`
  and `AllowNewsAndInterests` — at the OS level: the key ACL grants full control, yet the write is
  refused. Swept reports such an item as **unavailable on this Windows build** instead of calling it
  an error or blaming missing administrator rights.
- The Install tab ships a fixed catalog of 24 programs instead of a searchable repository: the
  list and every download URL are hardcoded on purpose, so the program can never be pointed at
  an arbitrary address. Adding a new program means adding an entry to `CATALOG` in
  `cleaner_installer.py`.
- Entries with a version-pinned URL (7-Zip, K-Lite, WinRAR, VLC, SumatraPDF, LibreOffice,
  Everything, Notepad++, PowerToys) must be updated when the vendor ships a new build. For
  7-Zip and K-Lite the pinned `sha256` must be updated together with the URL, otherwise the
  install is refused — that is the hash doing its job.
- An installer whose vendor rotates the signing certificate will be refused until the expected
  publisher string in `CATALOG` is updated — that is the intended trade-off.
- Silent switches come from the catalog. If a vendor changes one, the installer may show its own
  window instead of running quietly; the installation itself still completes.
- The `.exe` is not code-signed, so SmartScreen may warn about an unknown publisher on first run.

## Found a bug?

Please report it — that is how the program gets fixed:
**[github.com/vladcodex/swept/issues](https://github.com/vladcodex/swept/issues)**

To make a report useful, include:

- what you did and what you expected to happen,
- what actually happened instead,
- your Windows version (e.g. Windows 11 24H2) and whether Swept ran as administrator,
- the last lines of the **Log** tab (the app never sends anything anywhere — the log stays on your machine).

## Questions and ideas

For anything that is not a bug — how something works, what a setting means, a feature you
would like to see — there is
**[Discussions](https://github.com/vladcodex/swept/discussions)**:

- **Q&A** — ask how the program behaves and why.
- **Ideas** — propose a feature or an improvement.
- **General** — everything else.

Bugs belong in Issues, everything else in Discussions — that keeps the bug list clean and
the status of each report visible.

---

## Disclaimer

Swept deletes files and changes Windows settings. It is built conservatively and tested, but
you use it at your own risk — keep backups of anything you cannot re-download. The authors
take no responsibility for data loss or system damage.

## License

[MIT](LICENSE) — free to use, modify and redistribute. The app itself is free, with no
paid tier and no bundled offers.

---

## По-русски

**Swept** — бесплатная утилита с тёмным интерфейсом на двух языках (русский / English) в одном окне:

- 🧹 **Очистка** — временные файлы, кэш браузеров, кэш обновлений Windows, Корзина, логи,
  дампы и мусор игровых лаунчеров. Сначала «Анализ» — удаление только по вашему подтверждению.
- 📦 **Установка** — лаунчеры, браузеры, мессенджеры, офис, медиа, архиваторы и утилиты
  (24 программы): загрузка напрямую с официального HTTPS-CDN, проверка подписи Authenticode
  или закреплённого SHA-256 и тихая установка из изолированной папки.
- ⚡ **Оптимизация** — 12 безопасных настроек Windows (телеметрия, схема электропитания,
  фоновые приложения, Game DVR, виджеты…) с созданием точки восстановления перед изменениями.

Никакой слежки, никаких встроенных предложений и фоновых служб — один `.exe`, а каждое
удалённый файл и каждая изменённая настройка попадают в журнал.

**Нашли баг?** Напишите об этом — именно так программа и исправляется:
[github.com/vladcodex/swept/issues](https://github.com/vladcodex/swept/issues).
Чтобы отчёт был полезен, опишите: что вы делали и чего ожидали, что произошло на самом деле,
версию Windows (например, Windows 11 24H2), были ли права администратора, и последние
строки вкладки «Журнал» (программа ничего никуда не отправляет — журнал остаётся у вас).

**Вопросы и идеи** — если это не баг: как что-то работает, что означает настройка, какую
функку добавить. Для этого есть
[Discussions](https://github.com/vladcodex/swept/discussions): **Q&A** — вопросы,
**Ideas** — предложения, **General** — всё остальное. Баги — в Issues, всё прочее —
в Discussions: так список багов остаётся чистым, а статус каждого отчёта виден.

Выбранный язык хранится в реестре (как в Reg Organizer):

```
HKEY_CURRENT_USER\Software\Swept
    Language    REG_SZ    "ru" | "en"
```

Права администратора для записи не нужны, настройка привязана к пользователю: exe можно
перенести в другую папку — язык останется. При запуске значение читается из реестра,
при его отсутствии выставляется русский. Старый `settings.json` (версии до 1.1) один раз
переносится в реестр.

- **Очистка** — 15 категорий: временные файлы, кэш обновлений, логи и дампы, Корзина,
  кэш/история/куки четырёх браузеров, кэши шести игровых лаунчеров. Сначала «Анализ» —
  удаление только по отдельной кнопке, есть режим симуляции.
- **Установка** — без `winget`: инсталляторы качаются прямо с официальных адресов и
  проверяются по подписи. Семь наборов, 24 программы: игровые лаунчеры (Steam, Epic Games
  Launcher, EA App, Ubisoft Connect, GOG Galaxy), браузеры (Chrome, Firefox, Яндекс Браузер,
  Opera), связь (Telegram, Discord, Zoom, Slack), офис (ONLYOFFICE, LibreOffice, SumatraPDF),
  медиа (VLC, K-Lite Codec Pack Basic, Spotify), архиваторы (7-Zip, WinRAR),
  утилиты (Everything, Notepad++, PowerToys).
  Кнопка «Выбрать» открывает список программ с галочками — ставится ровно то, что отмечено.
  Отдельная кнопка ставит Visual C++ Redistributable (2015–2022, x86 и x64) подряд. Файл,
  не прошедший проверку, удаляется, а установка отменяется.
  **7-Zip и K-Lite** не подписывают инсталляторы вообще (проверено: и `WinVerifyTrust`, и
  `Get-AuthenticodeSignature` дают `NotSigned`), поэтому для них закреплён SHA-256 — адрес
  у них версионный, файл фиксирован, и хеш привязывает ровно проверенные байты. Запись без
  издателя и без хеша отклоняется: «скачалось — значит можно» не работает.
  В каталог не попали: NanaZip (.msixbundle ставится через `Add-AppxPackage`, а не exe),
  qBittorrent (SourceForge отвечает 403 на программный запрос), Foxit Reader и Adobe Acrobat
  Reader (нет прямой ссылки на файл, только страница с формой).
- **Оптимизация** — 12 безопасных настроек (перед изменениями создаётся точка восстановления):
  телеметрия, реклама, схема электропитания,
  гибернация, фоновые приложения, Game DVR, виджеты и Copilot, отчёты об ошибках и другое.
  Во время применения в панели «Ход выполнения» видно, какой пункт выполняется сейчас
  (со счётчиком «3 из 8») и чем закончился каждый: выполнено, пропущено, недоступно
  (с причиной прямо в строке) или ошибка.
- **Точка восстановления** — Swept создаёт точку восстановления Windows (PowerShell
  `Checkpoint-Computer`) **перед** применением любых настроек, поэтому откатить изменения
  можно штатными средствами — «Панель управления → Восстановление». Отдельная кнопка
  «🛡 Точка восстановления» создаёт её в любой момент, без применения оптимизаций.
  Удалённые встроенные приложения сами не возвращаются — их ставит Microsoft Store,
  о чём программа честно пишет в журнале. Из командной строки:
  `python cleaner_optimize.py --apply telemetry`.

Безопасность: белый список путей, жёсткий чёрный список (`System32`, `WinSxS`, `Program Files`…),
запрет на удаление системных файлов вроде `pagefile.sys`, ошибки не прерывают работу.
Ссылки и junction при сканировании не обходятся, а при удалении отклоняются; личные папки
(`Документы`, `Рабочий стол`, `Загрузки`, OneDrive) не чистятся никогда. Системные утилиты
(`powercfg`, `tasklist`, `msiexec`, `powershell`) запускаются по полному пути из `System32`,
а не из `PATH`, — подмена файла в пути поиска не даст повышенных прав. Установщики
запускаются вектором аргументов с `shell=False`, а ключи тихого режима берутся из
захардкоженного каталога, поэтому подставить свой параметр через интерфейс невозможно.
Скачанный файл исполняется только после успешного `WinVerifyTrust` с совпадением издателя
либо после совпадения SHA-256 с закреплённым в каталоге (для вендоров без подписи); запись
без издателя и без хеша отклоняется. Папка `%ProgramData%\SweptSecureTemp` доступна лишь
`SYSTEM` и `Администраторам`.

Запуск из исходников: `pip install -r requirements.txt`, затем `python cleaner_gui.py`.
Сборка exe: `python build.py` → `dist\Swept.exe`.
Установщик (Inno Setup): `ISCC.exe installer\setup.iss` → `dist\Swept-Setup-1.1.3.exe`.
