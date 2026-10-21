#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_installer.py — МОДУЛЬ УСТАНОВКИ И ОБНОВЛЕНИЯ ПРОГРАММ через winget.

Назначение
----------
Обёртка над Windows Package Manager (winget) для поиска, установки и
обновления программ. Все операции выполняются с флагами автоматического
принятия лицензий, чтобы не блокировать интерфейс диалогами.

Возможности
-----------
    * Поиск пакетов по ключевому слову (winget search).
    * Установка нового пакета (winget install).
    * Обновление существующего пакета (winget upgrade).
    * Обновление ВСЕХ пакетов (winget upgrade --all).
    * Список доступных обновлений (winget upgrade).
    * Проверка наличия winget в системе.
    * Режим симуляции (dry-run): показывает команду, но не выполняет её.

Особенность разбора вывода winget
---------------------------------
winget не умеет выводить JSON для search/list/upgrade, а его таблица
ЛОКАЛИЗОВАНА (заголовки «Имя / ИД / Версия») и «расползается» на длинных
именах: колонки сдвигаются, и разбор по фиксированным позициям ломается.
Поэтому здесь используется структурный разбор: в строке ищется пара
«ID пакета + версия» (ID — токен без пробелов с точкой, версия — токен,
начинающийся с цифры). Такой разбор не зависит от языка и ширины колонок.

Безопасность
------------
    * winget запускается в пользовательском контексте (без обхода UAC).
      Большинство программ ставятся в user scope.
    * Для системных пакетов winget сам покажет запрос UAC.
    * Все ошибки перехватываются и возвращаются как текст.

Автор: WorkBuddy AI
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess

import cleaner_i18n as i18n

# Флаг для subprocess: не показывать чёрное окно консоли (Windows).
CREATE_NO_WINDOW = 0x08000000

# --- Регулярные выражения для структурного разбора таблицы winget -----------
# ID пакета: без пробелов, обязательно содержит точку.
# Примеры: 7zip.7zip, Microsoft.VisualStudioCode, Python.Python.3.12
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*\.[A-Za-z0-9._+-]+$")

# Версия: начинается с цифры. Примеры: 26.04, 7.0.1843.0, 1.2.3-beta
_VERSION_RE = re.compile(r"^\d+(?:\.\d+)*(?:[-+_][A-Za-z0-9._-]+)?$")

# Общие флаги, чтобы winget не ждал ввода пользователя.
_NON_INTERACTIVE = ["--accept-source-agreements", "--disable-interactivity"]

# Префикс сообщения «обновлять нечего». Интерфейс по нему отличает
# «всё уже обновлено» от реального успешного обновления.
# Текст зависит от языка, поэтому сравнение идёт через is_no_updates().
NO_UPDATES = "Нет пакетов для обновления."
NO_UPDATES_EN = "Nothing to update."


def no_updates_text() -> str:
    """Текст «обновлять нечего» на текущем языке интерфейса."""
    return i18n.pick(NO_UPDATES, NO_UPDATES_EN)


def is_no_updates(message: str) -> bool:
    """Проверяет, что сообщение означает «обновлять нечего» (ru или en)."""
    if not message:
        return False
    return message.startswith(NO_UPDATES) or message.startswith(NO_UPDATES_EN)

# Набор Visual C++ Redistributable (Microsoft.VCRedist.*) — официальные пакеты
# Microsoft, все поддерживаемые версии, обе архитектуры (x86 и x64).
# Каждый элемент: (понятное имя, ID пакета в winget).
VC_REDIST_PACKAGES = [
    ("VC++ 2005 (x86)", "Microsoft.VCRedist.2005.x86"),
    ("VC++ 2005 (x64)", "Microsoft.VCRedist.2005.x64"),
    ("VC++ 2008 (x86)", "Microsoft.VCRedist.2008.x86"),
    ("VC++ 2008 (x64)", "Microsoft.VCRedist.2008.x64"),
    ("VC++ 2010 (x86)", "Microsoft.VCRedist.2010.x86"),
    ("VC++ 2010 (x64)", "Microsoft.VCRedist.2010.x64"),
    ("VC++ 2012 (x86)", "Microsoft.VCRedist.2012.x86"),
    ("VC++ 2012 (x64)", "Microsoft.VCRedist.2012.x64"),
    ("VC++ 2013 (x86)", "Microsoft.VCRedist.2013.x86"),
    ("VC++ 2013 (x64)", "Microsoft.VCRedist.2013.x64"),
    ("VC++ 2015-2022 (x86)", "Microsoft.VCRedist.2015+.x86"),
    ("VC++ 2015-2022 (x64)", "Microsoft.VCRedist.2015+.x64"),
]

# ---------------------------------------------------------------------------
# ПЛИТКИ БЫСТРОЙ УСТАНОВКИ: наборы популярных программ
# ---------------------------------------------------------------------------
# Каждый набор — карточка на вкладке «Установка»: одно нажатие ставит все
# программы из набора через winget. Все ID проверены командой
# `winget show --id <ID> --exact`, чтобы плитка не вела в пустоту.
# Формат элемента: ключ, названия (ru/en), подпись (ru/en), список (имя, ID).
APP_PRESETS = [
    {
        "key": "office",
        "title": "Офис и документы",
        "title_en": "Office and documents",
        "desc": "LibreOffice, ONLYOFFICE, Acrobat Reader, SumatraPDF",
        "desc_en": "LibreOffice, ONLYOFFICE, Acrobat Reader, SumatraPDF",
        "packages": [
            ("LibreOffice", "TheDocumentFoundation.LibreOffice"),
            ("ONLYOFFICE", "ONLYOFFICE.DesktopEditors"),
            ("Adobe Acrobat Reader", "Adobe.Acrobat.Reader.64-bit"),
            ("SumatraPDF", "SumatraPDF.SumatraPDF"),
        ],
    },
    {
        "key": "viewers",
        "title": "Просмотр и печать",
        "title_en": "Viewers and printing",
        "desc": "Foxit Reader, SumatraPDF, LibreOffice",
        "desc_en": "Foxit Reader, SumatraPDF, LibreOffice",
        "packages": [
            ("Foxit Reader", "Foxit.FoxitReader"),
            ("SumatraPDF", "SumatraPDF.SumatraPDF"),
            ("LibreOffice", "TheDocumentFoundation.LibreOffice"),
        ],
    },
    {
        "key": "browsers",
        "title": "Браузеры",
        "title_en": "Browsers",
        "desc": "Chrome, Firefox, Яндекс Браузер, Opera",
        "desc_en": "Chrome, Firefox, Yandex Browser, Opera",
        "packages": [
            ("Google Chrome", "Google.Chrome"),
            ("Mozilla Firefox", "Mozilla.Firefox"),
            ("Yandex Browser", "Yandex.Browser"),
            ("Opera", "Opera.Opera"),
        ],
    },
    {
        "key": "archivers",
        "title": "Архиваторы",
        "title_en": "Archivers",
        "desc": "7-Zip, WinRAR, NanaZip",
        "desc_en": "7-Zip, WinRAR, NanaZip",
        "packages": [
            ("7-Zip", "7zip.7zip"),
            ("WinRAR", "RARLab.WinRAR"),
            ("NanaZip", "M2Team.NanaZip"),
        ],
    },
    {
        "key": "media",
        "title": "Медиа и кодеки",
        "title_en": "Media and codecs",
        "desc": "VLC, K-Lite Basic, Spotify",
        "desc_en": "VLC, K-Lite Basic, Spotify",
        "packages": [
            ("VLC media player", "VideoLAN.VLC"),
            ("K-Lite Codec Pack Basic", "CodecGuide.K-LiteCodecPack.Basic"),
            ("Spotify", "Spotify.Spotify"),
        ],
    },
    {
        "key": "chat",
        "title": "Связь и звонки",
        "title_en": "Chat and calls",
        "desc": "Telegram, Discord, Zoom, Slack",
        "desc_en": "Telegram, Discord, Zoom, Slack",
        "packages": [
            ("Telegram", "Telegram.TelegramDesktop"),
            ("Discord", "Discord.Discord"),
            ("Zoom", "Zoom.Zoom"),
            ("Slack", "SlackTechnologies.Slack"),
        ],
    },
    {
        "key": "utils",
        "title": "Полезные утилиты",
        "title_en": "Handy utilities",
        "desc": "Everything, PowerToys, Notepad++, qBittorrent",
        "desc_en": "Everything, PowerToys, Notepad++, qBittorrent",
        "packages": [
            ("Everything", "voidtools.Everything"),
            ("Microsoft PowerToys", "Microsoft.PowerToys"),
            ("Notepad++", "Notepad++.Notepad++"),
            ("qBittorrent", "qBittorrent.qBittorrent"),
        ],
    },
]


# ID пакета winget: буквы, цифры, точка, дефис, плюс, подчёркивание.
# Проверка нужна, чтобы значение из поля ввода не могло стать флагом winget
# (например, "--help") и не содержало пробелов/кавычек.
_PKG_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")


def is_valid_package_id(pkg_id: str) -> bool:
    """True, если строка похожа на корректный ID пакета winget."""
    return bool(pkg_id) and bool(_PKG_ID_RE.match(pkg_id))


def _bad_id_message(pkg_id: str) -> str:
    """Локализованное сообщение о некорректном ID пакета."""
    return i18n.t("inst.bad_id", (pkg_id or "")[:80])


def is_valid_query(query: str) -> bool:
    """
    True, если поисковый запрос безопасно передавать в winget.

    Запрос не должен начинаться с дефиса (иначе winget примет его за флаг),
    не должен содержать переводов строк и быть разумной длины.
    """
    text = (query or "").strip()
    if not text or len(text) > 128:
        return False
    if text.startswith("-"):
        return False
    return not any(ch in text for ch in "\r\n\t")


# --- Поиск winget в доверенном месте ---------------------------------------
# Программа работает с правами администратора, поэтому запускать winget
# «по имени» нельзя: подменённый winget.exe в PATH выполнился бы с повышенными
# правами. Ищем настоящий файл в защищённом каталоге WindowsApps.
_APPINSTALLER_RE = re.compile(
    r"^Microsoft\.DesktopAppInstaller_(\d+(?:\.\d+)+)_(x64|arm64|x86)_", re.IGNORECASE)

_WINGET_CACHE = None   # None — ещё не искали, "" — не найден


def _installed_winget_entries() -> list:
    """Список (версия, архитектура, путь) установленных копий App Installer."""
    base = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "WindowsApps")
    entries = []
    try:
        names = os.listdir(base)
    except OSError:
        return entries
    for name in names:
        match = _APPINSTALLER_RE.match(name)
        if not match:
            continue
        exe = os.path.join(base, name, "winget.exe")
        if os.path.isfile(exe):
            version = tuple(int(part) for part in match.group(1).split("."))
            entries.append((version, match.group(2).lower(), exe))
    entries.sort(reverse=True)
    return entries


def _trusted_roots() -> list:
    """Каталоги, из которых допустимо запускать winget."""
    roots = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                "SystemRoot", "LOCALAPPDATA"):
        base = os.environ.get(key) or ""
        if base:
            try:
                roots.append(os.path.normcase(os.path.realpath(base)))
            except OSError:
                continue
    return roots


def _is_trusted_exe(path: str) -> bool:
    """True, если файл лежит внутри доверенного системного каталога."""
    try:
        real = os.path.normcase(os.path.realpath(path))
    except OSError:
        return False
    return any(real.startswith(root + os.sep) for root in _trusted_roots())


def find_winget() -> str:
    """
    Путь к настоящему winget.exe ("" — не найден).

    Приоритет: защищённый каталог App Installer в Program Files\\WindowsApps,
    затем Store-алиас / PATH — но только из доверенных каталогов.
    """
    global _WINGET_CACHE
    if _WINGET_CACHE is not None:
        return _WINGET_CACHE

    arch = {"amd64": "x64", "x86": "x86", "arm64": "arm64"}.get(
        (platform.machine() or "").lower(), "")
    entries = _installed_winget_entries()
    for _version, entry_arch, exe in entries:
        if arch and entry_arch == arch:
            _WINGET_CACHE = exe
            return exe
    if entries:
        _WINGET_CACHE = entries[0][2]
        return _WINGET_CACHE

    candidate = shutil.which("winget")
    if candidate and _is_trusted_exe(candidate):
        _WINGET_CACHE = candidate
        return candidate

    _WINGET_CACHE = ""
    return ""


def winget_command() -> list:
    """Командная строка для запуска winget (полный путь либо имя)."""
    path = find_winget()
    return [path] if path else ["winget"]


def is_winget_available() -> bool:
    """Проверяет, установлен ли winget в системе."""
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            winget_command() + ["--version"],
            capture_output=True, text=True, errors="ignore",
            creationflags=CREATE_NO_WINDOW, timeout=10,
        )
        return result.returncode == 0 and "v" in result.stdout
    except Exception:
        return False


def _run_winget(args: list, timeout: int = 300) -> tuple:
    """
    Запускает winget с указанными аргументами.

    Возвращает (success: bool, stdout: str, stderr: str).
    """
    cmd = winget_command() + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, errors="ignore",
            creationflags=CREATE_NO_WINDOW, timeout=timeout,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", i18n.t("inst.timeout", timeout)
    except FileNotFoundError:
        return False, "", i18n.t("inst.no_winget")
    except Exception as exc:
        return False, "", str(exc)


def _find_header(lines: list) -> tuple:
    """
    Ищет строку-заголовок таблицы winget.

    Возвращает (индекс_строки, позиция_колонки_ID) или (-1, -1).
    Позиция колонки нужна, чтобы отличать настоящий ID пакета от похожего
    на ID фрагмента названия (например, «Node.js 10» в имени программы).
    """
    for index, line in enumerate(lines[:20]):
        has_id = ("Id" in line) or ("ИД" in line)
        has_version = ("Version" in line) or ("Версия" in line)
        if has_id and has_version:
            position = line.find("Id")
            if position < 0:
                position = line.find("ИД")
            return index, position
    return -1, -1


def _is_numeric_publisher(pkg_id: str) -> bool:
    """
    True, если «издательская» часть ID — просто число.
    Отсекает ложные срабатывания вида «1.0» или «10.24.1» (это версии,
    а не идентификаторы пакетов).
    """
    first = pkg_id.split(".", 1)[0]
    return first.isdigit()


def _parse_table_line(line: str, id_col: int = -1) -> dict | None:
    """
    Разбирает одну строку таблицы winget.

    Возвращает {"name", "id", "version", "extra"} или None, если строка
    не похожа на запись пакета (заголовок, разделитель и т.п.).

    Логика:
      1. Находим все токены и их позиции в строке.
      2. Оставляем только пары «ID + версия» (ID — токен с точкой и без
         пробелов, версия — токен, начинающийся с цифры).
      3. Если известна позиция колонки ID из заголовка, выбираем пару,
         ближайшую к ней. Это устойчиво к «расползанию» длинных имён
         и к локализации вывода winget.
    """
    tokens = [(m.start(), m.group()) for m in re.finditer(r"\S+", line)]
    if len(tokens) < 2:
        return None

    candidates = []
    for index in range(len(tokens) - 1):
        position, token = tokens[index]
        if not _ID_RE.match(token):
            continue
        if not _VERSION_RE.match(tokens[index + 1][1]):
            continue
        if _is_numeric_publisher(token):
            continue
        candidates.append((index, position))

    if not candidates:
        # Резервный вариант: ID распознан, а версия нестандартная («Unknown»).
        for index, (position, token) in enumerate(tokens):
            if index > 0 and _ID_RE.match(token) and not _is_numeric_publisher(token):
                name = line[:position].strip() or token
                return {"name": name, "id": token, "version": "",
                        "extra": [t for _, t in tokens[index + 1:]]}
        return None

    if id_col is not None and id_col >= 0:
        # Ближайший к колонке ID кандидат — настоящий идентификатор.
        chosen = min(candidates, key=lambda item: abs(item[1] - id_col))
    else:
        chosen = candidates[0]

    index, position = chosen
    name = line[:position].strip() or tokens[index][1]
    return {
        "name": name,
        "id": tokens[index][1],
        "version": tokens[index + 1][1],
        "extra": [t for _, t in tokens[index + 2:]],
    }


def search_packages(query: str, on_log=None) -> list:
    """
    Ищет пакеты по запросу через `winget search`.

    Возвращает список словарей:
        [{"name": str, "id": str, "version": str, "source": str}, ...]
    """
    if on_log:
        on_log("Поиск: '{}'...".format(query))

    if not is_valid_query(query):
        if on_log:
            on_log(i18n.t("inst.bad_query", (query or "")[:80]))
        return []

    ok, out, err = _run_winget(["search", query] + _NON_INTERACTIVE)
    combined = (out or "") + "\n" + (err or "")

    # winget сообщает об отсутствии результатов отдельной строкой.
    if "No package found" in combined or "Не найдено" in combined:
        return []
    if not ok and not out:
        if on_log:
            on_log("Ошибка поиска: " + (err or "").strip()[:500])
        return []

    lines = (out or "").splitlines()
    _header_index, id_col = _find_header(lines)

    results = []
    seen = set()
    for line in lines:
        parsed = _parse_table_line(line, id_col)
        if not parsed:
            continue
        if parsed["id"] in seen:
            continue
        seen.add(parsed["id"])
        extra = parsed["extra"]
        results.append({
            "name": parsed["name"],
            "id": parsed["id"],
            "version": parsed["version"],
            "source": extra[-1] if extra else "",
        })
    return results


def list_upgradable(on_log=None) -> list:
    """
    Возвращает список пакетов, для которых есть обновления.

    Формат: [{"name": str, "id": str, "current": str, "available": str}, ...]
    """
    if on_log:
        on_log("Проверка доступных обновлений...")

    ok, out, err = _run_winget(["upgrade"] + _NON_INTERACTIVE, timeout=120)
    if not out:
        return []

    lines = out.splitlines()
    _header_index, id_col = _find_header(lines)

    results = []
    seen = set()
    for line in lines:
        parsed = _parse_table_line(line, id_col)
        if not parsed or parsed["id"] in seen:
            continue
        seen.add(parsed["id"])
        # «Available» — первая версия после текущей в остатке строки.
        available = ""
        for token in parsed["extra"]:
            if _VERSION_RE.match(token):
                available = token
                break
        results.append({
            "name": parsed["name"],
            "id": parsed["id"],
            "current": parsed["version"],
            "available": available,
        })
    return results


def install_package(pkg_id: str, on_log=None, dry_run: bool = False) -> tuple:
    """
    Устанавливает пакет по ID.

    Возвращает (success: bool, message: str).
    """
    if not is_valid_package_id(pkg_id):
        return False, _bad_id_message(pkg_id)

    args = [
        "install", "--id", pkg_id,
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    ]
    if dry_run:
        return True, i18n.t("inst.simulation", " ".join(args))

    if on_log:
        on_log(i18n.t("inst.log_install", pkg_id))
    ok, out, err = _run_winget(args, timeout=900)
    text = (out + "\n" + err).strip()
    if ok:
        return True, text

    # Иногда winget возвращает ненулевой код, хотя пакет уже установлен.
    lowered = text.lower()
    if ("already installed" in lowered or "уже установлен" in lowered
            or "no applicable upgrade found" in lowered):
        return True, text
    return False, text


def install_packages(pkg_list, on_log=None, dry_run: bool = False) -> tuple:
    """
    Последовательно устанавливает несколько пакетов (например, набор VC++).

    pkg_list — список пар (название, ID_пакета).
    Возвращает (success: bool, message: str).
    """
    overall = True
    parts = []
    for label, pkg_id in pkg_list:
        if on_log:
            on_log("")
            on_log(i18n.t("inst.log_item", label, pkg_id))
        ok, msg = install_package(pkg_id, on_log=on_log, dry_run=dry_run)
        parts.append("{}: {}".format(label, i18n.t("inst.status_ok") if ok
                                     else i18n.t("inst.status_error")))
        overall = overall and ok
    return overall, "\n".join(parts)


def upgrade_package(pkg_id: str, on_log=None, dry_run: bool = False) -> tuple:
    """
    Обновляет пакет по ID.

    Возвращает (success: bool, message: str).
    """
    if not is_valid_package_id(pkg_id):
        return False, _bad_id_message(pkg_id)

    args = [
        "upgrade", "--id", pkg_id,
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    ]
    if dry_run:
        return True, i18n.t("inst.simulation", " ".join(args))

    if on_log:
        on_log(i18n.t("inst.log_upgrade", pkg_id))
    ok, out, err = _run_winget(args, timeout=900)
    text = (out + "\n" + err).strip()
    if ok:
        return True, text
    if "No applicable upgrade found" in text:
        return True, i18n.t("inst.latest") + text
    return False, text


def _unknown_versions_note(text: str) -> str:
    """
    Пояснение про пакеты, версию которых winget не смог определить.
    Такие пакеты `upgrade --all` молча пропускает — иначе пользователь
    видит «обновлений нет» и не понимает, почему.
    """
    match = re.search(r"(?:Несколько|Several)\s*\((\d+)\)", text)
    if not match:
        return ""
    return i18n.t("inst.undetermined", match.group(1))


def upgrade_all(on_log=None, dry_run: bool = False) -> tuple:
    """
    Обновляет ВСЕ пакеты через `winget upgrade --all`.

    Возвращает (success: bool, message: str).
    Если обновлять нечего, сообщение начинается с константы NO_UPDATES —
    интерфейс по этому признаку показывает «Обновлений не найдено»
    вместо «УСПЕХ».
    """
    args = [
        "upgrade", "--all",
        "--accept-source-agreements",
        "--accept-package-agreements",
        "--disable-interactivity",
    ]
    if dry_run:
        return True, i18n.t("inst.simulation", " ".join(args))

    if on_log:
        on_log(i18n.t("inst.log_upgrade_all"))
    ok, out, err = _run_winget(args, timeout=3600)
    text = (out + "\n" + err).strip()
    lowered = text.lower()

    # winget возвращает код 0 и при «обновлять нечего» — проверяем текст,
    # иначе пользователь видит «УСПЕХ» без единого обновления.
    no_updates_markers = (
        "no installed package found",
        "no applicable upgrade",
        "no packages found",
        "no available upgrade",
        "не найдены установленные пакеты",
        "не найдено доступных обновлений",
        "нет доступных обновлений",
        "не найдено применимых обновлений",
    )
    if any(marker in lowered for marker in no_updates_markers):
        note = _unknown_versions_note(text)
        message = no_updates_text() + ("\n" + note if note else "")
        return True, message + "\n" + text
    if ok:
        return True, text
    return False, text


# =============================================================================
# CLI (для самостоятельного запуска)
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Установка программ через winget")
    parser.add_argument("--search", metavar="QUERY", help="поиск пакета")
    parser.add_argument("--install", metavar="ID", help="установить пакет по ID")
    parser.add_argument("--upgrade", metavar="ID", help="обновить пакет по ID")
    parser.add_argument("--upgrade-all", action="store_true", help="обновить все пакеты")
    parser.add_argument("--list-upgradable", action="store_true", help="список доступных обновлений")
    parser.add_argument("--dry-run", action="store_true", help="только показать команду")
    args = parser.parse_args()

    if not is_winget_available():
        print("[ОШИБКА] winget не найден. Установите App Installer из Microsoft Store.")
        raise SystemExit(1)

    def log(text):
        print(text)

    if args.search:
        results = search_packages(args.search, on_log=log)
        print("\nНайдено пакетов:", len(results))
        for r in results[:20]:
            print("  {:<35} | {:<40} | {}".format(r["name"][:35], r["id"], r["version"]))
    elif args.install:
        ok, msg = install_package(args.install, on_log=log, dry_run=args.dry_run)
        print("\n" + ("УСПЕХ" if ok else "ОШИБКА"))
        print(msg[:2000])
    elif args.upgrade:
        ok, msg = upgrade_package(args.upgrade, on_log=log, dry_run=args.dry_run)
        print("\n" + ("УСПЕХ" if ok else "ОШИБКА"))
        print(msg[:2000])
    elif args.upgrade_all:
        ok, msg = upgrade_all(on_log=log, dry_run=args.dry_run)
        print("\n" + ("ОБНОВЛЕНИЙ НЕ ТРЕБУЕТСЯ" if is_no_updates(msg)
                      else ("УСПЕХ" if ok else "ОШИБКА")))
        print(msg[:2000])
    elif args.list_upgradable:
        results = list_upgradable(on_log=log)
        print("\nДоступно обновлений:", len(results))
        for r in results[:30]:
            print("  {:<30} | {} -> {}".format(r["name"][:30], r["current"], r["available"]))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
