# Swept

**Windows 10/11 cleanup, app installer and optimizer in one dark-themed GUI.**
Bilingual interface (Русский / English), single-file `.exe`, no telemetry, no bundled offers.

Swept removes temporary files and browser traces, installs and updates software through
`winget`, and applies a set of safe, reversible Windows tweaks — all from one window with
a dry-run mode that shows exactly what would be deleted.

**[⬇ Download the latest release](https://github.com/vladcodex/swept/releases/latest)** —
one `.exe`, nothing to install.

![Swept — cleanup tab](docs/cleanup-en.png)

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

### 📦 Install and update

- Search any package in the `winget` catalogue and install it by clicking a row.
- Update a single package, or everything installed at once.
- **Popular app sets** in a column on the left: office, viewers and printing, browsers,
  archivers, media and codecs, chat and calls, handy utilities — 25 packages in total.
  A set is only a hint: **Choose** opens a list of its programs with checkboxes, so you
  install exactly what you need, not the whole bundle. Every package ID is verified
  against the winget catalogue.
- **One-click Visual C++ Redistributable bundle** — all versions 2005–2022, x86 and x64, installed in sequence.

![Install tab](docs/install-presets-ru.png)

### ⚡ Optimize

Twelve safe and reversible tweaks, in two groups:

- **Basic settings** — telemetry, advertising ID and suggestions, high-performance power plan, hibernation, background apps, Game DVR, startup delay, visual effects.
- **Full debloat** — built-in promo/game apps (Weather, News, Maps, Skype, Solitaire, Candy Crush…), taskbar widgets and Copilot, web search suggestions, Windows Error Reporting.

Every item states what it changes, whether it needs administrator rights, and how to revert it.

While the run is going, the **Progress** panel lists every selected item and marks it live:
`⏳` being applied now (with a "3 of 8" counter and the item name), `✔` done, `⛔` skipped or
unavailable — with the reason written right into the row — and `⚠` failed.

**Roll back all** (`↺`) returns every tweak to the Windows default in one go: the registry
values Swept wrote are deleted, so Windows falls back to its own settings; the power plan goes
back to *Balanced* and hibernation is switched on again. The same live list shows the rollback
step by step. Built-in apps removed by the debloat step cannot be restored automatically —
the app says so and points to Microsoft Store. From the command line it is
`python cleaner_optimize.py --revert-all`.

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
6. **No network access** except `winget` calls initiated by you, and no data collection of any kind.
7. **Links are never followed.** Junctions, symlinks and other reparse points are skipped during
   scanning and refused during deletion. A `%TEMP%` junction pointing at `Documents` would otherwise
   turn "clear temporary files" into "delete my documents" — so the real target path is checked
   against the whitelist as well, and personal folders (`Documents`, `Desktop`, `Downloads`,
   `Pictures`, OneDrive…) are refused even when they appear inside an allowed root.
8. **No `PATH` lookups for elevated tools.** The packaged app runs as administrator, so `winget`,
   `powercfg`, `tasklist` and `powershell` are resolved to their real files in
   `Program Files\WindowsApps` and `%SystemRoot%\System32` instead of being taken from `PATH`,
   where a planted executable would inherit elevation.
9. **Validated arguments.** Package IDs are matched against `[A-Za-z0-9][A-Za-z0-9._+-]*`, so a value
   from the input field can never become a `winget` switch (`--help`, `-e`) or smuggle quotes and
   spaces into the command line; search queries may not start with a dash.

Administrator rights are optional. Without them, `C:\Windows\Temp` and the update cache are
skipped; the app tells you so instead of failing silently. The packaged `.exe` requests
elevation through its manifest.

---

## Requirements

- Windows 10 or 11
- Python 3.10+ (developed and tested on 3.15) with `tkinter`
- `customtkinter` (installed from `requirements.txt`)
- `winget` (App Installer from the Microsoft Store) — only for the Install tab

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

---

## Command line

The three modules also work on their own — handy for scripts and scheduled tasks.

```bat
:: scan only, nothing is deleted
python cleaner_core.py --scan --only temp_user,chrome,recycle

:: real cleanup, no questions asked
python cleaner_core.py --clean --only recycle --yes

:: package management
python cleaner_installer.py --search 7zip
python cleaner_installer.py --install 7zip.7zip
python cleaner_installer.py --upgrade-all --dry-run

:: reversible Windows tweaks
python cleaner_optimize.py --list
python cleaner_optimize.py --apply telemetry,advertising,search_suggest
python cleaner_optimize.py --revert-all    :: restore every tweak to Windows default
```

## Project layout

| File | Purpose |
|---|---|
| `cleaner_gui.py` | CustomTkinter interface, worker threads, message queue |
| `cleaner_core.py` | Categories, scanning, safe deletion, Recycle Bin |
| `cleaner_installer.py` | `winget` wrapper: search, install, upgrade, VC++ bundle |
| `cleaner_optimize.py` | Registry and `powercfg` tweaks, Windows version detection |
| `cleaner_i18n.py` | Interface strings (RU/EN), language switching, unit formatting |
| `cleaner_settings.py` | Settings storage: `HKEY_CURRENT_USER\Software\Swept`, JSON fallback |
| `build.py` | PyInstaller wrapper with icon, version resource and manifest |

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
- The Install tab depends on `winget` output parsing, which Microsoft changes from time to time.
- The `.exe` is not code-signed, so SmartScreen may warn about an unknown publisher on first run.

## Disclaimer

Swept deletes files and changes Windows settings. It is built conservatively and tested, but
you use it at your own risk — keep backups of anything you cannot re-download. The authors
take no responsibility for data loss or system damage.

## License

[MIT](LICENSE)

---

## По-русски

**Swept** — утилита для Windows 10/11 в одном окне: очистка временных файлов и следов браузеров,
установка и обновление программ через `winget`, безопасная оптимизация системы.
Интерфейс переключается между русским и английским на лету — из выпадающего списка в шапке окна.

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
- **Установка** — поиск пакетов в `winget`, установка и обновление, набор Visual C++
  Redistributable (2005–2022, x86 и x64) одной кнопкой. Слева — колонка наборов популярных
  программ (офис, просмотр и печать, браузеры, архиваторы, медиа, связь, утилиты — 25 пакетов).
  Набор только подсказывает: кнопка «Выбрать» открывает список программ с галочками, и
  ставится ровно то, что отмечено, а не весь набор целиком.
- **Оптимизация** — 12 обратимых настроек: телеметрия, реклама, схема электропитания,
  гибернация, фоновые приложения, Game DVR, виджеты и Copilot, отчёты об ошибках и другое.
  Во время применения в панели «Ход выполнения» видно, какой пункт выполняется сейчас
  (со счётчиком «3 из 8») и чем закончился каждый: выполнено, пропущено, недоступно
  (с причиной прямо в строке) или ошибка.
- **Откат** — кнопка «Откатить всё» (`↺`) возвращает все настройки к значениям Windows:
  записанные в реестр значения удаляются, схема электропитания снова «Сбалансированная»,
  гибернация включается обратно. Ход отката показывается в том же живом списке.
  Удалённые встроенные приложения сами не возвращаются — их ставит Microsoft Store,
  о чём программа честно пишет в журнале. Из командной строки:
  `python cleaner_optimize.py --revert-all`.

Безопасность: белый список путей, жёсткий чёрный список (`System32`, `WinSxS`, `Program Files`…),
запрет на удаление системных файлов вроде `pagefile.sys`, ошибки не прерывают работу.
Ссылки и junction при сканировании не обходятся, а при удалении отклоняются; личные папки
(`Документы`, `Рабочий стол`, `Загрузки`, OneDrive) не чистятся никогда. Системные утилиты
(`winget`, `powercfg`, `tasklist`) запускаются по полному пути из защищённых каталогов, а не из
`PATH`, — подмена файла в пути поиска не даст повышенных прав. ID пакетов проверяются по шаблону,
поэтому ввод вида `--help` не превращается в ключ `winget`.

Запуск из исходников: `pip install -r requirements.txt`, затем `python cleaner_gui.py`.
Сборка exe: `python build.py` → `dist\Swept.exe`.
