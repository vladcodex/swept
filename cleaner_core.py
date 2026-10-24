#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_core.py — МОДУЛЬ ЛОГИКИ безопасной очистки системы Windows 10/11.

Назначение
----------
Здесь собрана вся "бизнес-логика": поиск мусора, подсчёт объёма, безопасное
удаление и очистка Корзины. Модуль НЕ зависит от графической библиотеки,
поэтому его можно использовать:
    * как библиотеку — `import cleaner_core`;
    * как самостоятельный скрипт — `python cleaner_core.py --help`.

Логические разделы (модули) внутри файла
----------------------------------------
    1. БЕЗОПАСНОСТЬ      — права администратора, белый/чёрный списки путей.
    2. УТИЛИТЫ           — форматирование размеров, нормализация путей.
    3. ОКРУЖЕНИЕ         — определение путей %TEMP%, %LOCALAPPDATA% и т.д.
    8. БРАУЗЕРЫ          — проверка запущенных процессов, поиск профилей.
                           (вынесены вверх: нужны и очистке, и интерфейсу)
    4. ЦЕЛИ ОЧИСТКИ      — построение безопасных путей по категориям.
    5. СКАНИРОВАНИЕ      — подсчёт файлов и объёма БЕЗ удаления.
    6. ОЧИСТКА           — удаление с перехватом блокировок (try-except).
    7. КОРЗИНА           — очистка через ctypes (SHEmptyRecycleBinW).
    9. CLI               — запуск логики из командной строки.

Номера разделов соответствуют заголовкам в файле, а не порядку строк:
раздел 8 (браузеры) намеренно расположен перед разделом 4.

Гарантии безопасности
---------------------
    * Удаление разрешено ТОЛЬКО внутри "белого списка" (ALLOWED-наборы),
      который строится из фактических целей выбранной категории.
    * Критические области Windows ("чёрный список": System32, WinSxS,
      загрузчик, pagefile.sys и т.п.) не затрагиваются НИКОГДА.
    * Любая ошибка доступа/блокировки перехватывается и пропускается —
      программа не падает из-за занятого файла.
    * Есть режим "только сканирование" (dry_run) — ничего не удаляется.

Автор: WorkBuddy AI
"""

from __future__ import annotations

import argparse
import ctypes
import fnmatch
import os
import platform
import re
import stat
import subprocess
import sys
import time
from ctypes import wintypes
from functools import lru_cache

import cleaner_i18n as i18n

# =============================================================================
# 1. БЕЗОПАСНОСТЬ
# =============================================================================

# Признак того, что мы действительно работаем в Windows.
IS_WINDOWS = (os.name == "nt")

# Флаг для subprocess: не показывать чёрное окно консоли (Windows).
CREATE_NO_WINDOW = 0x08000000

# --- Флаги Windows API для работы с Корзиной -------------------------------
SHERB_NOCONFIRMATION = 0x00000001   # не спрашивать подтверждение
SHERB_NOPROGRESSUI = 0x00000002     # не показывать прогресс
SHERB_NOSOUND = 0x00000004          # без звука

# --- ЧЁРНЫЙ СПИСОК: сюда не заходим НИКОГДА --------------------------------
# Пути НЕ хардкодятся под диск C: — они собираются из переменных среды,
# иначе на системе, установленной на другой диск, защита бы не сработала.
PROTECTED_WINDOWS_SUBDIRS = [
    "System32", "SysWOW64", "WinSxS", "Boot", "Fonts", "assembly",
    "Microsoft.NET", "servicing", "CSC", "System",
]

# Имена каталогов, которые запрещены на ЛЮБОМ диске.
PROTECTED_DIR_NAMES = {"$recycle.bin", "system volume information"}


@lru_cache(maxsize=1)
def _protected_paths() -> tuple:
    """
    Нормализованный список защищённых каталогов (строится из среды).

    Список зависит только от переменных окружения, которые за время работы
    программы не меняются, поэтому он кешируется: иначе он пересобирался бы
    на каждый удаляемый файл (около 28 мкс на ровном месте).
    """
    env = get_env_paths()
    windir = env.get("windir") or r"C:\Windows"
    program_files = os.environ.get("ProgramFiles") or r"C:\Program Files"
    program_files_x86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    program_data = env.get("programdata") or r"C:\ProgramData"

    roots = [os.path.join(windir, sub) for sub in PROTECTED_WINDOWS_SUBDIRS]
    roots += [
        program_files,
        program_files_x86,
        os.path.join(program_data, "Microsoft", "Windows", "Start Menu"),
        os.path.join(program_data, "Microsoft", "Windows", "SystemData"),
    ]
    return tuple(_norm(root) for root in roots)


@lru_cache(maxsize=1)
def _protected_exceptions() -> tuple:
    """Нормализованный список разрешённых подпапок внутри защищённых зон (кеш)."""
    env = get_env_paths()
    windir = env.get("windir") or r"C:\Windows"
    steam_root = os.path.join(env["programfiles_x86"], "Steam")

    paths = [
        os.path.join(windir, "System32", "LogFiles"),
        os.path.join(windir, "System32", "winevt", "Logs"),
    ]
    # Игровые лаунчеры: разрешаем чистить ТОЛЬКО конкретные кэш/логи/temp-папки
    # Steam, которые лежат внутри защищённой зоны "Program Files (x86)".
    # Белый список (get_jobs) ограничивает очистку этими же каталогами,
    # поэтому игры, сохранения и метаданные не затрагиваются.
    paths += [os.path.join(steam_root, sub) for sub in
              ("appcache", "cache", "logs", "tmp", os.path.join("steamapps", "downloading"))]
    return tuple(_norm(path) for path in paths)


def reset_protection_cache() -> None:
    """
    Сбрасывает кеш списков защиты.

    Нужен только тестам и сценариям, которые меняют переменные окружения
    на лету; в обычной работе вызывать не требуется.
    """
    _protected_paths.cache_clear()
    _protected_exceptions.cache_clear()


# --- Критические ФАЙЛЫ, которые нельзя удалять ни при каких условиях ------
PROTECTED_FILES = {
    "pagefile.sys", "hiberfil.sys", "swapfile.sys",
    "bootmgr", "bootnxt", "ntldr", "ntdetect.com", "boot.ini",
    "ntuser.dat", "bcd", "bcd.log",
}


def _norm(path: str) -> str:
    """Нормализует путь: абсолютный, нижний регистр, без хвостового слэша."""
    try:
        p = os.path.abspath(path)
    except Exception:
        p = path
    p = p.replace("/", os.sep).lower()
    # убираем хвостовой разделитель, но не превращаем "c:\" в "c:"
    while len(p) > 3 and p.endswith(os.sep):
        p = p[:-1]
    return p


def is_protected(path: str) -> bool:
    """
    True, если путь находится в защищённой (чёрной) зоне.
    Учитывает исключения (подпапки, которые чистить можно).
    """
    p = _norm(path)

    # 1) Исключения проверяем первыми — они "перебивают" запрет.
    for exc in _protected_exceptions():
        if p == exc or p.startswith(exc + os.sep):
            return False

    # 2) Критические файлы по имени.
    name = os.path.basename(p)
    if name in PROTECTED_FILES:
        return True

    # 3) Служебные каталоги на любом диске ($Recycle.Bin, System Volume Information).
    parts = [part for part in p.split(os.sep) if part]
    if any(part in PROTECTED_DIR_NAMES for part in parts):
        return True

    # 4) Запрещённые каталоги (Windows, Program Files, ProgramData...).
    for pr in _protected_paths():
        if p == pr or p.startswith(pr + os.sep):
            return True

    return False


def is_admin() -> bool:
    """Проверяет, запущена ли программа с правами администратора."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def get_os_name() -> str:
    """Человекочитаемое имя ОС (для строки состояния GUI)."""
    try:
        return "{} {}".format(platform.system(), platform.release()).strip()
    except Exception:
        return "Windows"


def system_tool(name: str, *subdirs: str) -> str:
    """
    Полный путь к штатной утилите Windows (tasklist, powercfg, powershell...).

    Программа запускается с правами администратора, поэтому брать утилиты
    из PATH нельзя: подменённый файл в пути поиска выполнился бы с повышенными
    правами (PATH hijacking). Берём файл из системного каталога, а к короткому
    имени откатываемся только если файла там нет.
    """
    windir = os.environ.get("SystemRoot") or r"C:\Windows"
    candidate = os.path.join(windir, "System32", *subdirs, name)
    return candidate if os.path.isfile(candidate) else name


# =============================================================================
# 2. УТИЛИТЫ
# =============================================================================

def format_bytes(num) -> str:
    """Преобразует число байт в строку вида '12.34 МБ' / '1.20 ГБ'."""
    try:
        value = float(num or 0)
    except (TypeError, ValueError):
        value = 0.0
    # Единицы зависят от языка интерфейса (Б/КБ/МБ или B/KB/MB).
    byte, kb, mb, gb, tb = i18n.units()
    for unit in (byte, kb, mb, gb, tb):
        if abs(value) < 1024.0 or unit == tb:
            if unit == byte:
                return "{:.0f} {}".format(value, unit)
            return "{:.2f} {}".format(value, unit)
        value /= 1024.0
    return "{:.2f} {}".format(value, tb)


def _safe_getsize(path: str) -> int:
    """Возвращает размер файла или 0, если файл недоступен."""
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# Атрибут Windows "точка повторной обработки" (симлинк, junction, mount point).
FILE_ATTRIBUTE_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


def is_reparse_point(path: str) -> bool:
    """
    True, если путь — символическая ссылка, junction или другая reparse-точка.

    Такие объекты нельзя ни обходить при сканировании, ни удалять: за ними
    может лежать что угодно (например, junction внутри %TEMP%, указывающий
    на папку с документами), и тогда «очистка временных файлов» удалила бы
    данные за пределами белого списка.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    try:
        return os.path.islink(path)
    except OSError:
        return False


def _real_norm(path: str) -> str:
    """Нормализованный путь с раскрытыми ссылками (junction/symlink)."""
    try:
        return _norm(os.path.realpath(path))
    except Exception:
        return _norm(path)


def clean_root_reason(path: str) -> str:
    """
    Причина, по которой каталог нельзя использовать как корень очистки.

    Возвращает "" если корень допустим, иначе один из кодов:
        "unsafe"   — корень диска, профиль, Windows, слишком короткий путь;
        "reparse"  — каталог сам является ссылкой/junction (за ним может
                     быть что угодно, включая личные файлы);
        "personal" — ведёт в личную папку пользователя (Документы, Загрузки...).
    """
    if not is_sane_root(path):
        return "unsafe"
    if is_reparse_point(path):
        return "reparse"
    if is_sensitive_user_path(_real_norm(path)):
        return "personal"
    return ""


def is_sane_root(path: str) -> bool:
    """
    Проверяет, что корень очистки безопасен.

    Отсекает то, что удалять нельзя ни при каких настройках среды:
        * пустой или относительный путь (иначе он превратится в текущий каталог);
        * корень диска (C:\\);
        * слишком короткий путь (C:\\Temp — это уже почти «весь диск»);
        * сам профиль пользователя, AppData, Windows, ProgramData целиком.
    """
    if not path or not os.path.isabs(path):
        return False
    p = _norm(path)
    _drive, tail = os.path.splitdrive(p)
    parts = [part for part in tail.split(os.sep) if part]
    if len(parts) < 2:
        return False
    env = get_env_paths()
    forbidden = [env.get(key) or "" for key in
                 ("userprofile", "local", "roaming", "windir", "programdata")]
    # AppData целиком (родитель Local и Roaming) — тоже слишком широко.
    if env.get("userprofile"):
        forbidden.append(os.path.join(env["userprofile"], "AppData"))
    for base in forbidden:
        if base and os.path.isabs(base) and p == _norm(base):
            return False
    return True


# Личные папки пользователя: даже если путь формально «глубокий», чистить
# их содержимое автоочисткой нельзя — там документы, а не мусор.
SENSITIVE_USER_DIRS = {
    "documents", "desktop", "downloads", "pictures", "music", "videos",
    "onedrive", "favorites", "links", "saved games", "contacts", "searches",
    "3d objects", "рабочий стол", "документы", "загрузки", "изображения",
    "музыка", "видео",
}


def is_sensitive_user_path(path: str) -> bool:
    """True, если путь лежит внутри личной папки пользователя."""
    p = _norm(path)
    profile = _norm(get_env_paths().get("userprofile") or "")
    if profile and p.startswith(profile + os.sep):
        rel = p[len(profile) + 1:]
        first = rel.split(os.sep)[0]
        if first in SENSITIVE_USER_DIRS:
            return True
    # OneDrive может быть вынесен за пределы профиля.
    return any(part == "onedrive" for part in p.split(os.sep))


# =============================================================================
# 3. ОКРУЖЕНИЕ
# =============================================================================

def get_env_paths() -> dict:
    """
    Возвращает словарь основных путей текущего пользователя.
    Значения берутся из переменных среды, поэтому функцию удобно
    тестировать, подменяя переменные (что и делается в тестах).
    """
    userprofile = os.environ.get("USERPROFILE", "")
    local = os.environ.get("LOCALAPPDATA") or os.path.join(userprofile, "AppData", "Local")
    roaming = os.environ.get("APPDATA") or os.path.join(userprofile, "AppData", "Roaming")
    windir = os.environ.get("SystemRoot") or r"C:\Windows"
    temp = os.environ.get("TEMP") or os.path.join(local, "Temp")
    programdata = os.environ.get("ProgramData") or r"C:\ProgramData"
    program_files_x86 = (os.environ.get("ProgramFiles(x86)")
                         or r"C:\Program Files (x86)")
    return {
        "userprofile": userprofile,
        "local": local,
        "roaming": roaming,
        "windir": windir,
        "temp": temp,
        "programdata": programdata,
        "programfiles_x86": program_files_x86,
    }


# =============================================================================
# 8. БРАУЗЕРЫ (описание + проверка процессов + поиск профилей)
# =============================================================================

# Описание поддерживаемых браузеров.
#   kind        — тип движка (chromium / firefox), определяет структуру профилей;
#   processes   — имена процессов (для проверки "закрыт ли браузер");
#   user_data   — функция, возвращающая каталог с профилями (для chromium).
BROWSERS = {
    "chrome": {
        "title": "Google Chrome",
        "processes": ["chrome.exe"],
        "kind": "chromium",
        "user_data": lambda env: os.path.join(env["local"], "Google", "Chrome", "User Data"),
    },
    "yandex": {
        "title": "Яндекс.Браузер",
        "title_en": "Yandex Browser",
        "processes": ["browser.exe"],
        "kind": "chromium",
        "user_data": lambda env: os.path.join(env["local"], "Yandex", "YandexBrowser", "User Data"),
    },
    "edge": {
        "title": "Microsoft Edge",
        "processes": ["msedge.exe"],
        "kind": "chromium",
        "user_data": lambda env: os.path.join(env["local"], "Microsoft", "Edge", "User Data"),
    },
    "firefox": {
        "title": "Mozilla Firefox",
        "processes": ["firefox.exe"],
        "kind": "firefox",
    },
}

# Что именно удаляем у Chromium-браузеров (относительно папки профиля).
CHROMIUM_CACHE_DIRS = ["Cache", "Code Cache", "GPUCache", "Media Cache"]
CHROMIUM_HISTORY_FILES = ["History", "History-journal", "Visited Links"]
CHROMIUM_COOKIE_FILES = [
    os.path.join("Network", "Cookies"),
    os.path.join("Network", "Cookies-journal"),
    "Cookies",
]

# Что удаляем у Firefox (кэш — в LOCALAPPDATA, история/куки — в APPDATA).
FIREFOX_CACHE_DIRS = ["cache2", "startupCache", "thumbnails"]
FIREFOX_HISTORY_FILES = ["places.sqlite", "places.sqlite-wal", "places.sqlite-shm"]
FIREFOX_COOKIE_FILES = ["cookies.sqlite", "cookies.sqlite-wal", "cookies.sqlite-shm"]


def list_running_processes() -> set:
    """
    Возвращает множество имён запущенных процессов (в нижнем регистре).
    Используется системная утилита `tasklist` (никаких сторонних библиотек).
    """
    names = set()
    if not IS_WINDOWS:
        return names
    try:
        result = subprocess.run(
            [system_tool("tasklist.exe"), "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="ignore",
            creationflags=CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # Первое поле CSV-строки — имя образа процесса.
            if line.startswith('"'):
                parts = line.split('"')
                name = parts[1] if len(parts) > 1 else ""
            else:
                name = line.split(",")[0]
            name = name.strip().lower()
            if name:
                names.add(name)
    except Exception:
        # Если tasklist недоступен — считаем, что процессов нет.
        pass
    return names


def is_browser_running(key: str, running: set | None = None) -> bool:
    """
    Проверяет, запущен ли браузер с указанным ключом.
    `running` — заранее полученный список процессов (чтобы не вызывать
    tasklist много раз подряд).
    """
    info = BROWSERS.get(key)
    if not info:
        return False
    procs = {p.lower() for p in info.get("processes", [])}
    if not procs:
        return False
    if running is None:
        running = list_running_processes()
    return bool(procs & running)


def get_running_browsers(keys=None) -> list:
    """Возвращает список ключей браузеров, которые сейчас запущены."""
    running = list_running_processes()
    result = []
    for key in BROWSERS:
        if keys is not None and key not in keys:
            continue
        if is_browser_running(key, running):
            result.append(key)
    return result


def close_browsers(keys=None) -> int:
    """
    Пытается корректно закрыть запущенные браузеры из списка `keys`.
    Сначала посылает мягкий сигнал закрытия (WM_CLOSE, taskkill без /F),
    а если процесс не завершился — принудительно (/F /T).
    Возвращает количество браузеров, которые удалось закрыть.
    """
    if not IS_WINDOWS:
        return 0
    running = get_running_browsers(keys)
    if not running:
        return 0
    closed = 0
    taskkill = system_tool("taskkill.exe")
    for key in running:
        info = BROWSERS.get(key)
        if not info:
            continue
        # 1) Мягкое закрытие — браузер может сохранить сессию/вкладки.
        for proc in info.get("processes", []):
            try:
                subprocess.run(
                    [taskkill, "/IM", proc, "/T"],
                    capture_output=True, text=True, errors="ignore",
                    creationflags=CREATE_NO_WINDOW,
                )
            except Exception:
                pass
        time.sleep(0.6)
        # 2) Если не закрылся — принудительно завершаем дерево процессов.
        if is_browser_running(key):
            for proc in info.get("processes", []):
                try:
                    subprocess.run(
                        [taskkill, "/IM", proc, "/F", "/T"],
                        capture_output=True, text=True, errors="ignore",
                        creationflags=CREATE_NO_WINDOW,
                    )
                except Exception:
                    pass
            time.sleep(0.6)
        if not is_browser_running(key):
            closed += 1
    return closed


def get_chromium_profiles(user_data_dir: str) -> list:
    """Находит папки профилей Chromium-браузера (Default, Profile 1, ...)."""
    profiles = []
    if not user_data_dir or not os.path.isdir(user_data_dir):
        return profiles
    try:
        entries = sorted(os.listdir(user_data_dir))
    except OSError:
        return profiles
    for name in entries:
        full = os.path.join(user_data_dir, name)
        if not os.path.isdir(full):
            continue
        low = name.lower()
        # Признаки профиля: имя Default / Profile N, либо наличие Preferences.
        if low == "default" or low.startswith("profile ") \
                or os.path.isfile(os.path.join(full, "Preferences")):
            profiles.append(full)
    return profiles


def get_firefox_profiles(env: dict) -> list:
    """
    Возвращает список пар (папка_в_APPDATA, папка_в_LOCALAPPDATA) для профилей
    Firefox: история/куки лежат в APPDATA, а кэш — в LOCALAPPDATA.
    """
    roam_root = os.path.join(env["roaming"], "Mozilla", "Firefox", "Profiles")
    local_root = os.path.join(env["local"], "Mozilla", "Firefox", "Profiles")
    names = set()
    for root in (roam_root, local_root):
        if os.path.isdir(root):
            try:
                for name in os.listdir(root):
                    if os.path.isdir(os.path.join(root, name)):
                        names.add(name)
            except OSError:
                pass
    return [(os.path.join(roam_root, n), os.path.join(local_root, n))
            for n in sorted(names)]


# =============================================================================
# 4. ЦЕЛИ ОЧИСТКИ (категории)
# =============================================================================

# Метаданные категорий для GUI/CLI (порядок отображения).
CATEGORIES = [
    {"key": "temp_user",    "title": "Временные файлы пользователя (%TEMP%)",
     "title_en": "User temporary files (%TEMP%)",                          "group": "quick",   "icon": "🗂"},
    {"key": "temp_system",  "title": "Системный Temp (C:\\Windows\\Temp)",
     "title_en": "System Temp (C:\\Windows\\Temp)",                        "group": "quick",   "icon": "🗂"},
    {"key": "update_cache", "title": "Кэш обновлений Windows",
     "title_en": "Windows update cache",                                   "group": "quick",   "icon": "🔄"},
    {"key": "logs_dumps",   "title": "Логи (.log) и дампы памяти (.dmp)",
     "title_en": "Logs (.log) and memory dumps (.dmp)",                    "group": "quick",   "icon": "📄"},
    {"key": "recycle",      "title": "Корзина Windows",
     "title_en": "Windows Recycle Bin",                                    "group": "quick",   "icon": "🗑"},
    {"key": "chrome",       "title": "Google Chrome",                      "group": "privacy", "icon": "🌐"},
    {"key": "yandex",       "title": "Яндекс.Браузер", "title_en": "Yandex Browser",
                                                                           "group": "privacy", "icon": "🌐"},
    {"key": "edge",         "title": "Microsoft Edge",                     "group": "privacy", "icon": "🌐"},
    {"key": "firefox",      "title": "Mozilla Firefox",                    "group": "privacy", "icon": "🦊"},

    # Игровые лаунчеры: только кэши, логи и временные данные.
    {"key": "game_steam",    "title": "Steam",                                 "group": "games",   "icon": "🎮"},
    {"key": "game_epic",     "title": "Epic Games Launcher",                   "group": "games",   "icon": "🎮"},
    {"key": "game_ubisoft",  "title": "Ubisoft Connect",                        "group": "games",   "icon": "🎮"},
    {"key": "game_ea",       "title": "EA App",                               "group": "games",   "icon": "🎮"},
    {"key": "game_battlenet","title": "Battle.net",                           "group": "games",   "icon": "🎮"},
    {"key": "game_gog",      "title": "GOG Galaxy",                            "group": "games",   "icon": "🎮"},
]

# Заголовки групп категорий.
GROUP_TITLES = {
    "quick": "Быстрая очистка",
    "privacy": "Кэш браузеров",
    "games": "Игровые лаунчеры",
}

# То же на английском (используется при переключении языка интерфейса).
GROUP_TITLES_EN = {
    "quick": "Quick cleanup",
    "privacy": "Browser cache",
    "games": "Game launchers",
}


def group_title(key: str) -> str:
    """Название группы категорий с учётом текущего языка."""
    return i18n.pick(GROUP_TITLES.get(key, key), GROUP_TITLES_EN.get(key, ""))


def category_title(key: str) -> str:
    """Название категории с учётом текущего языка."""
    cat = get_category(key)
    return i18n.fld(cat, "title") if cat else key

# Категории-браузеры (для них делаем проверку "закрыт ли браузер").
BROWSER_KEYS = {"chrome", "yandex", "edge", "firefox"}


def get_category(key: str) -> dict | None:
    """Возвращает метаданные категории по ключу."""
    for cat in CATEGORIES:
        if cat["key"] == key:
            return cat
    return None


def get_jobs(key: str) -> list:
    """
    Строит список заданий удаления для категории.

    Каждое задание — словарь с полем "type":
        * "dir"     — удалить содержимое каталога (сам каталог остаётся);
        * "glob"    — удалить файлы по маске внутри каталога (рекурсивно);
        * "file"    — удалить конкретный файл;
        * "recycle" — очистить Корзину через Windows API.
    """
    env = get_env_paths()
    jobs = []

    # ---------- БЫСТРАЯ ОЧИСТКА ----------
    if key == "temp_user":
        jobs.append({"type": "dir", "path": env["temp"], "label": "%TEMP%"})

    elif key == "temp_system":
        jobs.append({"type": "dir",
                     "path": os.path.join(env["windir"], "Temp"),
                     "label": "Windows\\Temp"})

    elif key == "update_cache":
        jobs.append({"type": "dir",
                     "path": os.path.join(env["windir"], "SoftwareDistribution", "Download"),
                     "label": "SoftwareDistribution\\Download"})

    elif key == "logs_dumps":
        # Системные папки, где лежат логи и дампы памяти.
        roots = [
            os.path.join(env["windir"], "Logs"),
            os.path.join(env["windir"], "System32", "LogFiles"),
            os.path.join(env["windir"], "Temp"),
            os.path.join(env["windir"], "Minidump"),
            os.path.join(env["local"], "CrashDumps"),
            os.path.join(env["local"], "Microsoft", "Windows", "WER"),
            os.path.join(env["programdata"], "Microsoft", "Windows", "WER"),
        ]
        for root in roots:
            jobs.append({"type": "glob", "path": root,
                         "patterns": ["*.log", "*.dmp", "*.mdmp"],
                         "label": root})

    elif key == "recycle":
        jobs.append({"type": "recycle"})

    # ---------- КЭШ БРАУЗЕРОВ ----------
    elif key in ("chrome", "yandex", "edge"):
        user_data = BROWSERS[key]["user_data"](env)
        for profile in get_chromium_profiles(user_data):
            # кэш (папки). remove_root=True — саму папку кэша тоже можно удалить
            # (браузер создаст её заново), т.к. это НЕ системный каталог.
            for cache_dir in CHROMIUM_CACHE_DIRS:
                jobs.append({"type": "dir", "path": os.path.join(profile, cache_dir),
                             "remove_root": True,
                             "label": os.path.basename(profile) + "\\" + cache_dir})
            # история (файлы)
            for fname in CHROMIUM_HISTORY_FILES:
                jobs.append({"type": "file", "path": os.path.join(profile, fname),
                             "label": os.path.basename(profile) + "\\History"})
            # cookies (файлы)
            for fname in CHROMIUM_COOKIE_FILES:
                jobs.append({"type": "file", "path": os.path.join(profile, fname),
                             "label": os.path.basename(profile) + "\\Cookies"})

    elif key == "firefox":
        for roam_prof, local_prof in get_firefox_profiles(env):
            for cache_dir in FIREFOX_CACHE_DIRS:
                jobs.append({"type": "dir", "path": os.path.join(local_prof, cache_dir),
                             "remove_root": True,
                             "label": "cache2"})
            for fname in FIREFOX_HISTORY_FILES:
                jobs.append({"type": "file", "path": os.path.join(roam_prof, fname),
                             "label": "places.sqlite"})
            for fname in FIREFOX_COOKIE_FILES:
                jobs.append({"type": "file", "path": os.path.join(roam_prof, fname),
                             "label": "cookies.sqlite"})

    # ---------- ИГРОВЫЕ ЛАУНЧЕРЫ -------------------------------------------
    # Удаляются ТОЛЬКО кэш/логи/temp и папки незавершённых загрузок.
    # Установленные игры, сохранения и метаданные (steamapps\common, *.acf,
    # depotcache) не затрагиваются. Корневые папки сохраняются (без remove_root)
    # — очищается только их содержимое.
    elif key == "game_steam":
        # Путь строится из переменной среды, а не хардкодится под диск C:
        # (см. _protected_exceptions — белый список должен совпадать с ним).
        steam_root = os.path.join(env["programfiles_x86"], "Steam")
        for sub in ("appcache", "cache", "logs", "tmp",
                    os.path.join("steamapps", "downloading")):
            jobs.append({"type": "dir",
                         "path": os.path.join(steam_root, sub),
                         "label": "Steam\\" + sub})

    elif key == "game_epic":
        epic = os.path.join(env["local"], "EpicGamesLauncher", "Saved")
        jobs.append({"type": "dir",
                     "path": os.path.join(epic, "webcache"),
                     "label": "Epic\\webcache"})
        jobs.append({"type": "dir",
                     "path": os.path.join(epic, "Logs"),
                     "label": "Epic\\Logs"})
        jobs.append({"type": "dir",
                     "path": os.path.join(env["programdata"], "Epic",
                                          "EpicGamesLauncher", "Data", "ManifestCache"),
                     "label": "Epic\\ManifestCache"})

    elif key == "game_ubisoft":
        jobs.append({"type": "dir",
                     "path": os.path.join(env["programdata"], "Ubisoft Launcher", "cache"),
                     "label": "Ubisoft\\cache"})
        jobs.append({"type": "dir",
                     "path": os.path.join(env["local"], "Ubisoft Game Launcher", "cache"),
                     "label": "Ubisoft\\cache (профиль)"})

    elif key == "game_ea":
        jobs.append({"type": "dir",
                     "path": os.path.join(env["local"], "EADesktop", "Logs"),
                     "label": "EA\\Logs"})

    elif key == "game_battlenet":
        jobs.append({"type": "dir",
                     "path": os.path.join(env["local"], "Battle.net", "Cache"),
                     "label": "Battle.net\\Cache"})

    elif key == "game_gog":
        jobs.append({"type": "dir",
                     "path": os.path.join(env["programdata"], "GOG.com", "Galaxy", "cache"),
                     "label": "GOG\\cache"})

    return jobs


def build_allowed(key: str) -> dict:
    """
    Строит БЕЛЫЙ СПИСОК для категории — то, что реально разрешено удалять.
    Возвращает {"dirs": set(), "files": set()} с нормализованными путями.
    Всё, что не попало сюда, удалить нельзя (защита от ошибок логики).

    Ненадёжные корни (пустой путь, корень диска, профиль пользователя)
    в белый список не попадают — см. is_sane_root().
    """
    dirs, files = set(), set()
    for job in get_jobs(key):
        jtype = job.get("type")
        path = job.get("path") or ""
        if jtype in ("dir", "glob"):
            if not clean_root_reason(path):
                dirs.add(_norm(path))
        elif jtype == "file":
            if path and os.path.isabs(path) and not is_reparse_point(path):
                files.add(_norm(path))
    # Реальные пути разрешённых каталогов считаем один раз: раскрытие
    # junction'ов на каждый файл стоило около 85 мкс на файл.
    real_dirs = {d: _real_norm(d) for d in dirs}
    return {"dirs": dirs, "files": files, "real_dirs": real_dirs}


def _in_allowed(path: str, allowed: dict) -> bool:
    """
    Проверяет, входит ли путь в белый список (точный файл или внутри каталога).

    Дополнительно отсекает обход через ссылки: если файл является reparse-точкой
    или реальный путь (после раскрытия junction/symlink) выходит за пределы
    разрешённого каталога, удаление запрещается.
    """
    p = _norm(path)
    if is_reparse_point(path):
        return False
    if p in allowed.get("files", set()):
        return True
    real_dirs = allowed.get("real_dirs") or {}
    for d in allowed.get("dirs", set()):
        if p == d or p.startswith(d + os.sep):
            # Ссылка внутри каталога могла увести за его пределы — сверяем
            # реальные пути, а не только строковое совпадение.
            real_path = _real_norm(path)
            real_dir = real_dirs.get(d) or _real_norm(d)
            if not (real_path == real_dir or real_path.startswith(real_dir + os.sep)):
                return False
            # Последняя линия защиты: в личных папках не удаляем ничего.
            return not is_sensitive_user_path(real_path)
    return False


# =============================================================================
# 5. СКАНИРОВАНИЕ (только чтение — ничего не удаляет)
# =============================================================================

def _collect_dir(root: str, result: dict) -> None:
    """Рекурсивно собирает файлы и подкаталоги внутри `root`.

    Обход идёт на os.scandir, а не на os.walk: у каждой записи размер и
    атрибут reparse-точки берутся из одного stat (он кэшируется в записи),
    тогда как раньше на каждый файл приходилось три системных вызова —
    lstat для проверки ссылки, stat для размера и ещё один для islink.
    На больших деревьях (кэш обновлений, C:\\Windows) это в разы меньше
    обращений к диску.
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as err:
            # Ошибка доступа к каталогу — запоминаем и идём дальше.
            result["errors"].append(
                (getattr(err, "filename", None) or current, str(err)))
            continue
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                info = None
            # Точки повторной обработки (симлинки, junction) не обходим
            # и не трогаем: за ними может быть что угодно.
            if info is not None and (
                    getattr(info, "st_file_attributes", 0)
                    & FILE_ATTRIBUTE_REPARSE_POINT):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                result["dirs"].append(entry.path)
                stack.append(entry.path)
                continue
            size = info.st_size if info is not None else 0
            result["files"].append((entry.path, size))
            result["total_size"] += size
            result["total_count"] += 1


def _collect_glob(root: str, patterns: list, result: dict) -> None:
    """Собирает файлы, подходящие под маски (например *.log, *.dmp)."""
    lowered = [p.lower() for p in patterns]
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            # Здесь ошибки обхода не нужны: категория «логи и дампы»
            # заведомо проходит по системным папкам с закрытым доступом.
            continue
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                info = None
            if info is not None and (
                    getattr(info, "st_file_attributes", 0)
                    & FILE_ATTRIBUTE_REPARSE_POINT):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                stack.append(entry.path)
                continue
            name = entry.name.lower()
            if not any(fnmatch.fnmatch(name, pat) for pat in lowered):
                continue
            size = info.st_size if info is not None else 0
            result["files"].append((entry.path, size))
            result["total_size"] += size
            result["total_count"] += 1


def scan_category(key: str, on_log=None, stop_event=None) -> dict:
    """
    Сканирует одну категорию БЕЗ удаления.

    Возвращает словарь:
        {
          "key": str,
          "files": [(путь, размер), ...],
          "dirs": [пустой_каталог, ...],   # кандидаты на удаление после файлов
          "total_size": int,
          "total_count": int,
          "recycle": None | {"size": int, "count": int},
          "errors": [(путь, текст_ошибки), ...],
        }
    """
    result = {
        "key": key,
        "files": [],
        "dirs": [],
        "total_size": 0,
        "total_count": 0,
        "recycle": None,
        "errors": [],
    }

    for job in get_jobs(key):
        if stop_event is not None and stop_event.is_set():
            break
        jtype = job.get("type")

        # Опасный корень (пустой путь, корень диска, профиль целиком,
        # junction/ссылка, личная папка) — не сканируем и не показываем.
        if jtype in ("dir", "glob"):
            reason = clean_root_reason(job.get("path") or "")
            if reason:
                if on_log:
                    on_log(i18n.t("core.root_" + reason, job.get("path") or "—"))
                continue
        if jtype == "file" and not os.path.isabs(job.get("path") or ""):
            continue

        if jtype == "recycle":
            # Читаем статистику Корзины (только чтение — безопасно).
            size, count = query_recycle_bin()
            result["recycle"] = {"size": size, "count": count}
            result["total_size"] += size
            result["total_count"] += count
            if on_log:
                on_log(i18n.t("core.recycle_stat", count, format_bytes(size)))

        elif jtype == "dir":
            path = job["path"]
            if os.path.isdir(path):
                _collect_dir(path, result)
                # Для кэш-папок браузеров разрешаем удалить и сам каталог,
                # если он опустеет (remove_root=True). Для системных Temp —
                # корень НЕ удаляем (Windows рассчитывает на его существование).
                if job.get("remove_root"):
                    result["dirs"].append(path)
            else:
                if on_log:
                    on_log(i18n.t("core.no_folder", path))

        elif jtype == "glob":
            path = job["path"]
            if os.path.isdir(path):
                _collect_glob(path, job["patterns"], result)

        elif jtype == "file":
            path = job["path"]
            if os.path.isfile(path):
                size = _safe_getsize(path)
                result["files"].append((path, size))
                result["total_size"] += size
                result["total_count"] += 1

    return result


def scan_categories(keys, on_log=None, on_status=None, stop_event=None) -> dict:
    """Сканирует список категорий. Возвращает {key: результат_сканирования}."""
    results = {}
    total = len(keys)
    for index, key in enumerate(keys, start=1):
        if stop_event is not None and stop_event.is_set():
            break
        cat = get_category(key)
        title = i18n.fld(cat, "title") if cat else key
        if on_status:
            on_status(i18n.t("core.scanning", title, index, total))
        if on_log:
            on_log("─── {} ───".format(title))
        results[key] = scan_category(key, on_log=on_log, stop_event=stop_event)
    return results


# =============================================================================
# 6. ОЧИСТКА (удаление с перехватом ошибок)
# =============================================================================

def safe_delete_file(path: str, allowed: dict, dry_run: bool = False) -> str:
    """
    Безопасно удаляет ОДИН файл.

    Возвращает строковый статус:
        "ok"        — файл удалён;
        "simulated" — режим сканирования, файл НЕ удалён;
        "missing"   — файла уже нет;
        "blocked"   — путь защищён или не входит в белый список;
        "error"     — файл занят/нет прав (перехвачено, программа продолжает).
    """
    abspath = os.path.abspath(path)

    # 1) Чёрный список — не трогаем.
    if is_protected(abspath):
        return "blocked"
    # 2) Белый список — удаляем только разрешённое.
    if not _in_allowed(abspath, allowed):
        return "blocked"
    # 3) Файла нет — пропускаем.
    if not os.path.isfile(abspath):
        return "missing"
    # 4) Режим сканирования — ничего не удаляем.
    if dry_run:
        return "simulated"

    # Снимаем атрибут "только чтение", иначе os.remove может не сработать.
    try:
        os.chmod(abspath, stat.S_IWRITE)
    except OSError:
        pass

    try:
        os.remove(abspath)
        return "ok"
    except (OSError, PermissionError):
        # Файл занят другой программой или защищён системой — пропускаем.
        return "error"


def clean_scan_result(result: dict, dry_run: bool = False, on_log=None,
                      on_progress=None, stop_event=None, allowed: dict | None = None) -> dict:
    """
    Удаляет то, что было найдено при сканировании (result из scan_category).

    Возвращает статистику:
        {"removed": int, "skipped": int, "errors": int, "freed": int,
         "recycle_done": None | "ok" | "fail" | "simulated"}
    """
    key = result.get("key")
    if allowed is None:
        allowed = build_allowed(key)

    stats = {"removed": 0, "skipped": 0, "errors": 0, "freed": 0, "recycle_done": None}

    files = result.get("files", [])
    total = len(files)
    last_emit = 0.0
    for index, (path, size) in enumerate(files, start=1):
        if stop_event is not None and stop_event.is_set():
            break
        if on_progress:
            # Не чаще 20 раз в секунду. Раньше сигнал уходил на каждый файл,
            # и на категории в десятки тысяч файлов очередь сообщений росла
            # быстрее, чем интерфейс успевал её разбирать.
            now = time.monotonic()
            if index == total or now - last_emit >= 0.05:
                last_emit = now
                on_progress(index, total)

        status = safe_delete_file(path, allowed, dry_run=dry_run)
        if status == "ok":
            stats["removed"] += 1
            stats["freed"] += size
            if on_log:
                on_log("  ✔ " + path)
        elif status == "simulated":
            stats["removed"] += 1
            stats["freed"] += size
            if on_log:
                on_log(i18n.t("core.sim_prefix") + path)
        elif status == "blocked":
            stats["skipped"] += 1
            if on_log:
                on_log(i18n.t("core.protected", path))
        elif status == "missing":
            stats["skipped"] += 1
        else:  # "error"
            stats["errors"] += 1
            if on_log:
                on_log(i18n.t("core.busy", path))

    # Удаляем опустевшие каталоги (сначала самые глубокие).
    for directory in sorted(result.get("dirs", []), key=len, reverse=True):
        if stop_event is not None and stop_event.is_set():
            break
        try:
            # Ссылки и junction не трогаем: os.rmdir по ним может вести себя
            # непредсказуемо, а пользы от удаления ссылки нет.
            if is_reparse_point(directory):
                continue
            # Каталог обязан входить в белый список этой категории.
            if not _in_allowed(directory, allowed):
                continue
            if os.path.isdir(directory) and not os.listdir(directory):
                if not dry_run:
                    os.rmdir(directory)
        except OSError:
            pass

    # Очистка Корзины (Windows API).
    if result.get("recycle"):
        if dry_run:
            stats["recycle_done"] = "simulated"
            stats["freed"] += result["recycle"]["size"]
            stats["removed"] += result["recycle"]["count"]
            if on_log:
                on_log(i18n.t("core.sim_recycle"))
        else:
            ok = empty_recycle_bin()
            stats["recycle_done"] = "ok" if ok else "fail"
            if ok:
                stats["freed"] += result["recycle"]["size"]
                stats["removed"] += result["recycle"]["count"]
                if on_log:
                    on_log(i18n.t("core.recycle_ok"))
            elif on_log:
                on_log(i18n.t("core.recycle_fail"))

    return stats


def clean_categories(results: dict, dry_run: bool = False, on_log=None,
                     on_status=None, on_progress=None, stop_event=None) -> dict:
    """
    Очищает несколько категорий по заранее полученным результатам сканирования.

    Возвращает суммарную статистику + разбивку по категориям.
    """
    summary = {"removed": 0, "skipped": 0, "errors": 0, "freed": 0, "per_category": {}}
    total = len(results)
    for index, (key, result) in enumerate(results.items(), start=1):
        if stop_event is not None and stop_event.is_set():
            break
        cat = get_category(key)
        title = i18n.fld(cat, "title") if cat else key
        if on_status:
            on_status(i18n.t("core.cleaning", title, index, total))
        if on_log:
            on_log("═══ {} ═══".format(title))

        stats = clean_scan_result(
            result, dry_run=dry_run, on_log=on_log,
            on_progress=on_progress, stop_event=stop_event,
        )
        summary["per_category"][key] = stats
        summary["removed"] += stats["removed"]
        summary["skipped"] += stats["skipped"]
        summary["errors"] += stats["errors"]
        summary["freed"] += stats["freed"]

    return summary


# =============================================================================
# 7. КОРЗИНА (Windows API через ctypes)
# =============================================================================

class SHQUERYRBINFO(ctypes.Structure):
    """Структура для SHQueryRecycleBinW (размер и число объектов в Корзине)."""
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def query_recycle_bin() -> tuple:
    """
    Возвращает (размер_в_байтах, число_объектов) Корзины.
    Только чтение — ничего не удаляет.
    """
    if not IS_WINDOWS:
        return 0, 0
    info = SHQUERYRBINFO()
    info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
    try:
        result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if result == 0:
            return int(info.i64Size), int(info.i64NumItems)
    except Exception:
        pass
    return 0, 0


def empty_recycle_bin() -> bool:
    """
    Очищает Корзину Windows через SHEmptyRecycleBinW.
    Возвращает True при успехе. Ошибки перехватываются.
    """
    if not IS_WINDOWS:
        return False
    flags = SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
    try:
        # Первый параметр None => Корзина текущего пользователя на всех дисках.
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        return result == 0
    except Exception:
        return False


# =============================================================================
# 8. ХРАНИЛИЩЕ КОМПОНЕНТОВ (WinSxS) — официальные команды DISM
# =============================================================================
#
# WinSxS НЕЛЬЗЯ чистить удалением файлов: там жёсткие ссылки на системные
# компоненты, и ручное удаление ломает обновления Windows. Штатный способ —
# служебная утилита DISM:
#
#     dism /Online /Cleanup-Image /AnalyzeComponentStore   — только проверка
#     dism /Online /Cleanup-Image /StartComponentCleanup   — очистка
#
# Обе команды требуют прав администратора. Проверка занимает около минуты,
# очистка — от 5 до 20 минут. Ключ /ResetBase намеренно НЕ используется:
# без него последнее установленное обновление остаётся откатываемым.

_DISM_TIMEOUT_ANALYZE = 900      # 15 минут — с большим запасом
_DISM_TIMEOUT_CLEAN = 5400       # 90 минут: на медленных дисках бывает долго

# Прогресс-бар DISM: "[=============  17.7%  =============]"
_PROGRESS_RE = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s*%")

# Размер с единицей измерения: "13.91 GB", "114.53 MB", "8,23 ГБ".
_SIZE_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB|B|ТБ|ГБ|МБ|КБ|Б)(?![A-Za-zА-Яа-я])",
    re.IGNORECASE)

_SIZE_UNITS = {
    "B": 1, "Б": 1,
    "KB": 1024, "КБ": 1024,
    "MB": 1024 ** 2, "МБ": 1024 ** 2,
    "GB": 1024 ** 3, "ГБ": 1024 ** 3,
    "TB": 1024 ** 4, "ТБ": 1024 ** 4,
}

# Ключевые слова строк отчёта. DISM переводит подписи вместе с системой,
# поэтому ищем по смыслу, а не по позиции строки: работает и для русского,
# и для английского вывода.
_DISM_LABELS = (
    ("recommended",  ("cleanup recommended", "recommended cleanup",
                      "рекомендуется очистка")),
    ("packages",     ("reclaimable packages", "освобождаемых пакетов")),
    ("last_cleanup", ("date of last cleanup", "дата последней очистки")),
    ("actual",       ("actual size of component store",
                      "фактический размер хранилища")),
    ("explorer",     ("explorer reported size", "по данным проводника")),
    ("backups",      ("backups and disabled features", "резервные копии")),
    ("cache",        ("cache and temporary data", "кэш и временные")),
)


def _console_encoding() -> str:
    """
    Кодовая страница консоли.

    DISM — консольная программа и при перенаправлении вывода пишет в
    OEM-кодировке (866 для русской Windows), а не в UTF-8. Без этого
    русские подписи превращаются в мусор и парсер их не находит.
    """
    try:
        code_page = ctypes.windll.kernel32.GetOEMCP()
        if code_page:
            return "cp{}".format(int(code_page))
    except Exception:
        pass
    return "utf-8"


def _iter_process_lines(stream, encoding: str):
    """
    Читает вывод процесса построчно.

    Разделяем и по \\r, и по \\n: DISM перерисовывает прогресс-бар через
    возврат каретки, поэтому при чтении «по строкам» он пришёл бы одной
    огромной строкой до первого перевода строки.
    """
    buffer = b""
    while True:
        try:
            chunk = stream.read1(4096)
        except AttributeError:          # поток без read1 (обычный файл)
            chunk = stream.read(4096)
        if not chunk:
            break
        buffer += chunk
        parts = re.split(rb"[\r\n]+", buffer)
        buffer = parts.pop()
        for raw in parts:
            if raw.strip():
                yield raw.decode(encoding, "replace").rstrip()
    if buffer.strip():
        yield buffer.decode(encoding, "replace").rstrip()


def _dism_value(line: str) -> str:
    """Значение после разделителя ' : ' (DISM использует пробелы вокруг ':').

    Разделять по последнему двоеточию нельзя: в дате последней очистки
    ('2026-10-20 21:39:33') двоеточия есть и внутри значения.
    """
    if " : " in line:
        return line.split(" : ", 1)[1].strip()
    if ":" in line:
        return line.rsplit(":", 1)[1].strip()
    return ""


def _parse_size(text: str):
    """'13.91 GB' -> байты. Возвращает None, если размера в строке нет."""
    match = _SIZE_RE.search(text or "")
    if not match:
        return None
    try:
        number = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    multiplier = _SIZE_UNITS.get(match.group(2).upper())
    return int(number * multiplier) if multiplier else None


def _yes_no(text: str):
    """'Да'/'Yes' -> True, 'Нет'/'No' -> False, иначе None."""
    value = (text or "").strip().lower()
    if value.startswith(("yes", "да", "true")):
        return True
    if value.startswith(("no", "нет", "false")):
        return False
    return None


def _first_int(text: str):
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


def _progress_from_line(line: str):
    """Доля выполнения (0..1) из строки прогресс-бара DISM, иначе None."""
    stripped = line.strip()
    if not stripped.startswith("["):
        return None
    match = _PROGRESS_RE.search(stripped)
    if not match:
        return None
    try:
        percent = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    return max(0.0, min(1.0, percent / 100.0))


def parse_component_store_report(text: str) -> dict:
    """
    Разбирает текстовый отчёт DISM /AnalyzeComponentStore.

    Возвращает словарь:
        recommended — True/False/None («надо ли чистить»);
        actual      — фактический размер хранилища, байты;
        explorer    — размер «по данным проводника», байты;
        backups     — резервные копии и отключённые компоненты, байты;
        cache       — кэш и временные данные, байты;
        reclaimable — сколько примерно освободится (backups + cache);
        packages    — число освобождаемых пакетов;
        last_cleanup— дата последней очистки строкой;
        parsed      — удалось ли вытащить хоть что-то осмысленное.
    """
    report = {
        "recommended": None, "actual": None, "explorer": None,
        "backups": None, "cache": None, "reclaimable": None,
        "packages": None, "last_cleanup": None, "parsed": False,
    }
    for line in (text or "").splitlines():
        low = line.strip().lower()
        if not low or ":" not in low:
            continue
        value = _dism_value(line)
        for key, markers in _DISM_LABELS:
            if not any(marker in low for marker in markers):
                continue
            if key == "recommended":
                report["recommended"] = _yes_no(value)
            elif key == "last_cleanup":
                report["last_cleanup"] = value or None
            elif key == "packages":
                report["packages"] = _first_int(value)
            else:
                size = _parse_size(value)
                if size is not None:
                    report[key] = size
            break

    if report["backups"] is not None or report["cache"] is not None:
        report["reclaimable"] = (report["backups"] or 0) + (report["cache"] or 0)
    report["parsed"] = (report["recommended"] is not None
                        or report["actual"] is not None)
    return report


def _run_dism(args, on_line=None, on_progress=None, stop_event=None,
              timeout=_DISM_TIMEOUT_ANALYZE, allow_kill=True) -> tuple:
    """
    Запускает DISM и построчно отдаёт вывод в колбэки.

    Возвращает (код возврата, весь текст вывода, была ли остановка).
    """
    command = [system_tool("dism.exe")] + list(args)
    encoding = _console_encoding()
    collected = []
    started = time.time()

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            bufsize=-1,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception as exc:
        return -1, "{}: {}".format(i18n.t("winsxs.fail_start"), exc), False

    stopped = False
    try:
        for line in _iter_process_lines(process.stdout, encoding):
            collected.append(line)
            if on_line:
                try:
                    on_line(line)
                except Exception:
                    pass
            if on_progress:
                percent = _progress_from_line(line)
                if percent is not None:
                    try:
                        on_progress(percent)
                    except Exception:
                        pass
            if stop_event is not None and stop_event.is_set():
                stopped = True
                if allow_kill:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    break
            if time.time() - started > timeout:
                try:
                    process.kill()
                except Exception:
                    pass
                collected.append(i18n.t("winsxs.fail_timeout"))
                break
    finally:
        try:
            process.stdout.close()
        except Exception:
            pass

    try:
        code = process.wait(timeout=60)
    except Exception:
        code = -1
    return code, "\n".join(collected), stopped


def analyze_component_store(on_line=None, on_progress=None,
                            stop_event=None) -> dict:
    """
    Официальная проверка хранилища компонентов (ничего не удаляет):
        DISM /Online /Cleanup-Image /AnalyzeComponentStore

    Возвращает словарь с полями ok, reason и результатами разбора отчёта.
    reason: no_admin | not_windows | failed | unparsed | stopped.
    """
    result = {
        "ok": False, "reason": "", "code": -1, "output": "",
        "recommended": None, "actual": None, "explorer": None,
        "backups": None, "cache": None, "reclaimable": None,
        "packages": None, "last_cleanup": None, "parsed": False,
    }
    if not IS_WINDOWS:
        result["reason"] = "not_windows"
        return result
    if not is_admin():
        result["reason"] = "no_admin"
        return result

    base = ["/Online", "/Cleanup-Image", "/AnalyzeComponentStore"]
    # Сначала запускаем без /English: на русской системе журнал остаётся
    # русским, а разбор всё равно работает (подписи ищутся по смыслу).
    # Если отчёт не распознан (экзотическая локаль) — повторяем с /English,
    # который заставляет DISM печатать подписи по-английски.
    code, output, stopped = _run_dism(
        base, on_line=on_line, on_progress=on_progress,
        stop_event=stop_event, timeout=_DISM_TIMEOUT_ANALYZE)
    report = parse_component_store_report(output)

    if not report["parsed"] and code == 0 and not stopped:
        code, output, stopped = _run_dism(
            base + ["/English"], on_line=on_line, on_progress=on_progress,
            stop_event=stop_event, timeout=_DISM_TIMEOUT_ANALYZE)
        report = parse_component_store_report(output)

    result.update(report)
    result["code"] = code
    result["output"] = output
    if report["parsed"]:
        result["ok"] = True
    elif stopped:
        result["reason"] = "stopped"
    elif code != 0:
        result["reason"] = "failed"
    else:
        result["reason"] = "unparsed"
    return result


def cleanup_component_store(on_line=None, on_progress=None,
                            stop_event=None) -> dict:
    """
    Официальная очистка хранилища компонентов:
        DISM /Online /Cleanup-Image /StartComponentCleanup

    Без /ResetBase: удаляются устаревшие компоненты, но последнее
    установленное обновление остаётся откатываемым.

    Операцию нельзя прерывать на середине, поэтому stop_event проверяется
    только ДО запуска — остановка посреди работы оставила бы хранилище
    в неопределённом состоянии.
    """
    result = {"ok": False, "reason": "", "code": -1, "output": ""}
    if not IS_WINDOWS:
        result["reason"] = "not_windows"
        return result
    if not is_admin():
        result["reason"] = "no_admin"
        return result
    if stop_event is not None and stop_event.is_set():
        result["reason"] = "stopped"
        return result

    code, output, _ = _run_dism(
        ["/Online", "/Cleanup-Image", "/StartComponentCleanup"],
        on_line=on_line, on_progress=on_progress, stop_event=None,
        timeout=_DISM_TIMEOUT_CLEAN, allow_kill=False)
    result["code"] = code
    result["output"] = output
    result["ok"] = (code == 0)
    if code != 0:
        result["reason"] = "failed"
    return result


# =============================================================================
# 9. CLI — запуск логики из командной строки
# =============================================================================

def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleaner_core.py",
        description="Безопасная очистка Windows 10/11 (логика без интерфейса).",
    )
    parser.add_argument("--scan", action="store_true",
                        help="только сканировать (режим по умолчанию, ничего не удаляет)")
    parser.add_argument("--clean", action="store_true",
                        help="выполнить РЕАЛЬНУЮ очистку")
    parser.add_argument("--only", metavar="KEYS",
                        help="список категорий через запятую (по умолчанию — все)")
    parser.add_argument("--list", action="store_true",
                        help="показать список категорий и выйти")
    parser.add_argument("--yes", action="store_true",
                        help="не спрашивать подтверждение при реальной очистке")
    return parser


def _print_categories() -> None:
    print("Доступные категории:")
    for cat in CATEGORIES:
        print("  {:<12} [{}]  {}".format(
            cat["key"], group_title(cat["group"]), i18n.fld(cat, "title")))


def main(argv=None) -> int:
    """Точка входа CLI. Возвращает код выхода."""
    args = _build_arg_parser().parse_args(argv)

    if args.list:
        _print_categories()
        return 0

    if not IS_WINDOWS:
        print("[ВНИМАНИЕ] Модуль рассчитан на Windows — часть функций недоступна.")

    # Выбор категорий.
    if args.only:
        keys = [k.strip() for k in args.only.split(",") if k.strip()]
        unknown = [k for k in keys if get_category(k) is None]
        if unknown:
            print("[ОШИБКА] Неизвестные категории: " + ", ".join(unknown))
            return 2
    else:
        keys = [cat["key"] for cat in CATEGORIES]

    dry_run = not args.clean

    print("=" * 70)
    print("Swept — {}".format("СКАНИРОВАНИЕ (ничего не удаляется)" if dry_run
                                    else "ОЧИСТКА (реальное удаление)"))
    print("Права администратора: {}".format("ЕСТЬ" if is_admin() else "НЕТ (часть файлов будет пропущена)"))
    print("ОС: {} | Категорий выбрано: {}".format(get_os_name(), len(keys)))
    print("=" * 70)

    # Проверка запущенных браузеров перед очисткой.
    if not dry_run:
        running = get_running_browsers(keys)
        if running:
            print("[ВНИМАНИЕ] Запущены браузеры: " +
                  ", ".join(BROWSERS[k]["title"] for k in running))
            print("           Файлы кэша/истории/куки могут быть заняты и пропущены.")

    if not dry_run and not args.yes:
        answer = input("Продолжить реальную очистку? [y/N]: ").strip().lower()
        if answer not in ("y", "yes", "д", "да"):
            print("Отменено пользователем.")
            return 0

    def log(text):
        print(text)

    def status(text):
        print("\n>> " + text)

    results = scan_categories(keys, on_log=log, on_status=status)
    total_size = sum(r["total_size"] for r in results.values())
    total_count = sum(r["total_count"] for r in results.values())
    print("\nНайдено файлов: {} | Объём: {}".format(total_count, format_bytes(total_size)))

    if dry_run:
        print("\nРежим сканирования завершён. Для удаления добавьте --clean.")
        return 0

    summary = clean_categories(results, dry_run=False, on_log=log, on_status=status)
    print("\n" + "=" * 70)
    print("Удалено объектов: {} | Пропущено: {} | Ошибок доступа: {}".format(
        summary["removed"], summary["skipped"], summary["errors"]))
    print("Освобождено: {}".format(format_bytes(summary["freed"])))
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
