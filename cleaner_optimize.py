#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_optimize.py — МОДУЛЬ БЕЗОПАСНОЙ ОПТИМИЗАЦИИ Windows 10/11.

Назначение
----------
Набор консервативных, безопасных настроек для «чистой» (голой) системы
Windows 10 и Windows 11. Цель — слегка ускорить систему и убрать рекламный
/ телеметрический «шум», НЕ ломая стабильность.

Правила безопасности модуля
---------------------------
    * Никаких удалений системных файлов, драйверов или служб.
    * Только настройки реестра (winreg) и штатные утилиты (powercfg).
    * Каждый пункт запускается в try/except — одна неудача не прерывает
      остальные.
    * Пункты, требующие прав администратора, помечены admin=True; без прав
      они пропускаются с пояснением, а не «падают».
    * Поддерживается ВСЕ версии Windows 10 и 11 (определяется по build-номеру
      из реестра: >= 22000 — Windows 11, иначе — Windows 10).
    * Перед любыми изменениями Swept создаёт точку восстановления системы
      (powershell Checkpoint-Computer), чтобы можно было откатиться штатными
      средствами Windows — «Панель управления -> Восстановление».

Модуль не зависит от GUI и может запускаться как скрипт:
    python cleaner_optimize.py --list
    python cleaner_optimize.py --apply telemetry  (требуются права админа)
"""

from __future__ import annotations

import re
import subprocess
import sys

try:
    import winreg
except ImportError:  # pragma: no cover - не Windows
    winreg = None

import cleaner_i18n as i18n
from cleaner_core import is_admin, system_tool

# Флаг: не показывать чёрное окно консоли (Windows).
CREATE_NO_WINDOW = 0x08000000

# ---------------------------------------------------------------------------
# Работа с реестром
# ---------------------------------------------------------------------------

def admin_required_message() -> str:
    """Сообщение «нужны права администратора» на текущем языке."""
    return i18n.t("opt.admin_required")


def is_admin_required(msg: str) -> bool:
    """
    Проверяет, что сообщение означает «не хватает прав администратора».

    Сравниваем с обоими вариантами (ru/en), чтобы логика не зависела
    от того, на каком языке интерфейса был получен ответ. Сообщение может
    быть составным: _write_many склеивает несколько ошибок через «; »,
    поэтому проверяем каждую часть отдельно.
    """
    if not msg:
        return False
    variants = (i18n.STRINGS["ru"]["opt.admin_required"],
                i18n.STRINGS["en"]["opt.admin_required"])
    for part in str(msg).split(";"):
        if part.strip() in variants:
            return True
    return False


def key_protected_message() -> str:
    """Сообщение «ключ реестра защищён системой» на текущем языке."""
    return i18n.t("opt.key_protected")


def is_key_protected(msg: str) -> bool:
    """
    True, если сообщение означает «ключ реестра защищён системой».

    Это не то же самое, что «нет прав администратора»: на новых сборках
    Windows часть ключей (например, Explorer\\Advanced) принадлежит SYSTEM
    и не даёт записи даже повышенному процессу. Пользователь ничего
    не может с этим сделать, поэтому пункт помечается как недоступный,
    а не как ошибка.
    """
    if not msg:
        return False
    variants = (i18n.STRINGS["ru"]["opt.key_protected"],
                i18n.STRINGS["en"]["opt.key_protected"])
    for part in str(msg).split(";"):
        if part.strip() in variants:
            return True
    return False


def _permission_message() -> str:
    """
    Пояснение при отказе в доступе к ключу реестра.

    Если прав администратора нет — так и говорим (пользователь может
    перезапустить с повышением). Если права есть, значит ключ защищён
    системой, и повышение прав не поможет.
    """
    if is_admin():
        return key_protected_message()
    return admin_required_message()


# Признаки отказа в доступе в выводе штатных утилит (powercfg и т.п.).
# Нужны, чтобы такой отказ считался «пропущено из-за прав», а не ошибкой.
_ACCESS_DENIED_MARKERS = (
    "access is denied",
    "отказано в доступе",
    "requires elevation",
    "требует повышения",
    "elevated permissions",
    "недостаточно прав",
    "administrator privileges",
    "права администратора",
)


def _denied_in_text(text: str) -> bool:
    """True, если в выводе утилиты есть признак отказа в доступе."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _ACCESS_DENIED_MARKERS)


def _reg_write(hive, path, name, value, vtype=winreg.REG_DWORD):
    """Пишет значение в реестр. Возвращает (ok, message)."""
    try:
        with winreg.CreateKeyEx(hive, path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, name, 0, vtype, value)
        return True, ""
    except PermissionError:
        return False, _permission_message()
    except Exception as exc:
        return False, str(exc)


def _write_many(steps):
    """
    Выполняет список шагов (каждый — callable -> (ok, msg)).

    Возвращает (ok, message). Одинаковые сообщения схлопываются: иначе при
    трёх одинаковых отказах пользователь видит трижды одну и ту же причину.
    """
    errors = []
    for step in steps:
        ok, msg = step()
        if not ok and msg and msg not in errors:
            errors.append(msg)
    return (not errors), "; ".join(errors)


def _run(cmd, timeout=30):
    """Запускает команду. Возвращает (returncode, stdout)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, errors="ignore",
            creationflags=CREATE_NO_WINDOW, timeout=timeout,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except Exception as exc:
        return -1, str(exc)


def _util_result(code, out) -> tuple:
    """
    Приводит результат штатной утилиты к (ok, message).

    Отказ в доступе распознаётся по тексту вывода и превращается в
    «нужны права администратора» — тогда пункт помечается пропущенным,
    а не сломанным.
    """
    if code == 0:
        return True, ""
    text = (out or "").strip()
    if _denied_in_text(text):
        return False, admin_required_message()
    return False, text[:200]


# ---------------------------------------------------------------------------
# Определение версии Windows
# ---------------------------------------------------------------------------

def get_windows_info() -> dict:
    """Возвращает сведения об ОС: {'build','display','edition','major','minor'}."""
    info = {"major": 10, "minor": 0, "build": 0,
            "display": "Windows 10", "edition": ""}
    if winreg is None:
        info["display"] = "Не Windows"
        return info
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            cv, _ = winreg.QueryValueEx(key, "CurrentVersion")
            b, _ = winreg.QueryValueEx(key, "CurrentBuildNumber")
            info["major"], info["minor"] = (cv.split(".") + ["0", "0"])[:2]
            info["build"] = int(b or 0)
            try:
                info["edition"], _ = winreg.QueryValueEx(key, "EditionID")
            except OSError:
                pass
        # build >= 22000 => Windows 11; иначе — Windows 10.
        info["display"] = "Windows 11" if info["build"] >= 22000 else "Windows 10"
    except Exception:
        import platform
        info["display"] = "{} {}".format(platform.system(), platform.release())
    return info


# ---------------------------------------------------------------------------
# Применяемые оптимизации
# ---------------------------------------------------------------------------

# Пути реестра (константы для читаемости).
_HKLM_POL_DATA = r"SOFTWARE\Policies\Microsoft\Windows\DataCollection"
_HKCU_CURRENT = r"Software\Microsoft\Windows\CurrentVersion"


def _opt_telemetry():
    """(admin) Отключить телеметрию и диагностических данные."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_LOCAL_MACHINE, _HKLM_POL_DATA, "AllowTelemetry", 0),
        lambda: _reg_write(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection",
                           "AllowTelemetry", 0),
        lambda: _reg_write(winreg.HKEY_LOCAL_MACHINE, _HKLM_POL_DATA,
                           "MaxTelemetryAllowed", 0),
    ])


def _opt_advertising():
    """(user) Отключить рекламный ID, советы и предложения."""
    cdm = _HKCU_CURRENT + r"\ContentDeliveryManager"
    return _write_many([
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\AdvertisingInfo", "Enabled", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER, cdm, "SoftLandingEnabled", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER, cdm,
                           "SystemPaneSuggestionsEnabled", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER, cdm,
                           "SubscribedContent-338389Enabled", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER, cdm,
                           "SubscribedContent-310093Enabled", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER, cdm,
                           "RotatingLockScreenEnabled", 0),
    ])


def _opt_power():
    """(admin) Включить схему «Высокая производительность» электропитания."""
    high_perf = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    powercfg = system_tool("powercfg.exe")
    code, _out = _run([powercfg, "/list"])
    if code != 0:
        return False, i18n.t("opt.power_list_fail")
    if high_perf.lower() in _out.lower():
        code2, out2 = _run([powercfg, "/setactive", high_perf])
    else:
        code2, out2 = _run([powercfg, "/duplicatescheme", high_perf])
        if code2 == 0:
            m = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27})", out2.lower())
            _run([powercfg, "/setactive", m.group(1) if m else high_perf])
    return _util_result(code2, out2)


def _opt_hibernate():
    """(admin) Отключить гибернацию, освободив место (обратимо: powercfg /h on)."""
    code, out = _run([system_tool("powercfg.exe"), "/h", "off"])
    return _util_result(code, out)


def _opt_background():
    """(user) Запретить работу фоновых приложений."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\BackgroundAccessApplications",
                           "GlobalUserDisabled", 1),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\Search",
                           "BackgroundAppGlobalToggle", 0),
    ])


def _opt_gamedvr():
    """(user) Отключить запись/оверлей Game DVR."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           r"System\GameConfigStore", "GameDVR_Enabled", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\GameDVR", "AppCaptureEnabled", 0),
    ])


def _opt_startup_delay():
    """(user) Убрать задержку при запуске программ из автозагрузки."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\Explorer\Serialize",
                           "StartupDelayInMSec", 0),
    ])


def _opt_visualfx():
    """(user) Визуальные эффекты -> «лучшее быстродействие» (обратимо)."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\Explorer\VisualEffects",
                           "VisualFXSetting", 2),
    ])


# Заголовки групп оптимизаций.
OPT_GROUP_TITLES = {
    "basics": "Базовые настройки",
    "debloat": "Полный деблоат (голая Windows)",
}

# То же на английском.
OPT_GROUP_TITLES_EN = {
    "basics": "Basic settings",
    "debloat": "Full debloat (bare Windows)",
}


def opt_group_title(key: str) -> str:
    """Название группы оптимизаций с учётом текущего языка."""
    return i18n.pick(OPT_GROUP_TITLES.get(key, key), OPT_GROUP_TITLES_EN.get(key, ""))

# Список встроенных приложений (UWP), которые безопасно удалить у текущего
# пользователя. Если приложение не установлено — шаг просто пропускается.
# Системные и нужные приложения (Проводник, Параметры, Store и т.п.)
# не затрагиваются. Вернуть приложения можно из Microsoft Store.
BLOAT_APPS = [
    ("Microsoft.BingWeather", "Погода"),
    ("Microsoft.BingNews", "Новости"),
    ("Microsoft.BingSports", "Спорт"),
    ("Microsoft.BingFinance", "Финансы"),
    ("Microsoft.GetHelp", "Получить справку"),
    ("Microsoft.MicrosoftSolitaireCollection", "Коллекция пасьянсов"),
    ("Microsoft.MicrosoftOfficeHub", "Центр Office"),
    ("Microsoft.People", "Люди"),
    ("Microsoft.SkypeApp", "Skype"),
    ("Microsoft.WindowsFeedbackHub", "Центр отзывов"),
    ("Microsoft.WindowsMaps", "Карты"),
    ("Microsoft.ZuneMusic", "Groove Музыка"),
    ("Microsoft.ZuneVideo", "Фильмы и ТВ"),
    ("king.com.CandyCrushSaga", "Candy Crush"),
]


def _opt_debloat_apps():
    """(user) Удалить безобидные встроенные приложения у текущего пользователя."""
    # Имена пакетов подставляются в текст PowerShell-скрипта, поэтому
    # пропускаем только те, что соответствуют строгому шаблону: буквы,
    # цифры, точка, дефис, подчёркивание. Никаких кавычек и пробелов.
    names = [name for name, _label in BLOAT_APPS
             if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", name)]
    if not names:
        return False, "no valid app names"
    quoted = ", ".join("'{}'".format(n) for n in names)
    script = (
        "$apps = @({quoted}); "
        "foreach ($a in $apps) {{ "
        "Get-AppxPackage -Name $a -ErrorAction SilentlyContinue | "
        "Remove-AppxPackage -ErrorAction SilentlyContinue "
        "}}"
    ).format(quoted=quoted)
    code, out = _run([system_tool("powershell.exe", "WindowsPowerShell", "v1.0"),
                      "-NoProfile", "-NonInteractive", "-Command", script],
                     timeout=300)
    return (code == 0), (out.strip()[:300] or "")


def _opt_widgets_copilot():
    """(user) Отключить виджеты и Copilot в панели задач (Win11)."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\Explorer\Advanced", "TaskbarDa", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           r"Software\Policies\Microsoft\Dsh",
                           "AllowNewsAndInterests", 0),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           r"Software\Policies\Microsoft\Windows\WindowsCopilot",
                           "TurnOffWindowsCopilot", 1),
    ])


def _opt_search_suggest():
    """(user) Отключить веб-советы и Bing-подсказки в поиске/Пуске."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           r"Software\Policies\Microsoft\Windows\Explorer",
                           "DisableSearchBoxSuggestions", 1),
        lambda: _reg_write(winreg.HKEY_CURRENT_USER,
                           _HKCU_CURRENT + r"\SearchSettings",
                           "IsDynamicSearchBoxEnabled", 0),
    ])


def _opt_wer():
    """(admin) Отключить отчёты об ошибках Windows (обратимо)."""
    return _write_many([
        lambda: _reg_write(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Windows\Windows Error Reporting",
                           "Disabled", 1),
    ])

# Список оптимизаций для интерфейса:
#   key, title/title_en, desc/desc_en, group, admin, apply (безопасная настройка).
# Обратимость обеспечивается точкой восстановления системы, которая создаётся
# перед применением, — отдельного программного отката здесь нет.
OPTIMIZATIONS = [
    {
        "key": "telemetry",
        "group": "basics",
        "title": "Отключить телеметрию и диагностику",
        "title_en": "Disable telemetry and diagnostics",
        "desc": "Запрещает отправку диагностических данных в Microsoft. "
                "(реестр: DataCollection\\AllowTelemetry=0)",
        "desc_en": "Blocks sending diagnostic data to Microsoft. "
                   "(registry: DataCollection\\AllowTelemetry=0)",
        "admin": True,
        "apply": _opt_telemetry,
    },
    {
        "key": "advertising",
        "group": "basics",
        "title": "Отключить рекламу, советы и предложения",
        "title_en": "Disable ads, tips and suggestions",
        "desc": "Убирает рекламный ID, советы и рекламные плитки в меню "
                "Пуск/уведомлениях.",
        "desc_en": "Removes the advertising ID, tips and promotional tiles "
                   "from Start and notifications.",
        "admin": False,
        "apply": _opt_advertising,
    },
    {
        "key": "power",
        "group": "basics",
        "title": "Схема электропитания — «Высокая производительность»",
        "title_en": "Power plan — High performance",
        "desc": "Переводит электропитание в режим высокой производительности "
                "(снижает «тормоза» на десктопе).",
        "desc_en": "Switches the power plan to high performance "
                   "(reduces desktop lag).",
        "admin": True,
        "apply": _opt_power,
    },
    {
        "key": "hibernate",
        "group": "basics",
        "title": "Отключить гибернацию (освободить место)",
        "title_en": "Disable hibernation (free disk space)",
        "desc": "Освобождает место, убирая файл гибернации. Обратимо: "
                "powercfg /h on. Осторожно: отключает быстрый запуск.",
        "desc_en": "Frees space by removing the hibernation file. Reversible: "
                   "powercfg /h on. Note: turns off Fast Startup.",
        "admin": True,
        "apply": _opt_hibernate,
    },
    {
        "key": "background",
        "group": "basics",
        "title": "Отключить фоновые приложения",
        "title_en": "Disable background apps",
        "desc": "Запрещает приложениям работать в фоне (меньше нагрузки).",
        "desc_en": "Stops apps from running in the background (lower load).",
        "admin": False,
        "apply": _opt_background,
    },
    {
        "key": "gamedvr",
        "group": "basics",
        "title": "Отключить Game DVR / Game Bar",
        "title_en": "Disable Game DVR / Game Bar",
        "desc": "Отключает фоновую запись и оверлей игр (меньше нагрузки, "
                "короче задержки).",
        "desc_en": "Turns off background recording and the game overlay "
                   "(lower load, shorter delays).",
        "admin": False,
        "apply": _opt_gamedvr,
    },
    {
        "key": "startup_delay",
        "group": "basics",
        "title": "Убрать задержку автозагрузки",
        "title_en": "Remove the startup delay",
        "desc": "Программы из автозагрузки начинают запускаться сразу.",
        "desc_en": "Startup programs begin launching immediately.",
        "admin": False,
        "apply": _opt_startup_delay,
    },
    {
        "key": "visualfx",
        "group": "basics",
        "title": "Визуальные эффекты — «лучшее быстродействие»",
        "title_en": "Visual effects — best performance",
        "desc": "Отключает анимации/тени интерфейса. Обратимо через "
                "«Настройки -> Специальные возможности -> Визуальные эффекты».",
        "desc_en": "Disables interface animations and shadows. Revert via "
                   "Settings -> Accessibility -> Visual effects.",
        "admin": False,
        "apply": _opt_visualfx,
    },
    {
        "key": "debloat_apps",
        "group": "debloat",
        "title": "Удалить встроенные рекламные/игровые приложения",
        "title_en": "Remove built-in promo and game apps",
        "desc": "Удаляет у текущего пользователя безобидные предустановленные "
                "приложения (Погода, Новости, Карты, Skype, пасьянсы, Candy Crush "
                "и др.). Вернуть можно из Microsoft Store.",
        "desc_en": "Removes harmless preinstalled apps for the current user "
                   "(Weather, News, Maps, Skype, Solitaire, Candy Crush and "
                   "others). Can be reinstalled from the Microsoft Store.",
        "admin": False,
        "apply": _opt_debloat_apps,
        # Встроенные приложения удаляются безвозвратно: вернуть их можно
        # только из Microsoft Store, поэтому обратного действия нет.
    },
    {
        "key": "widgets_copilot",
        "group": "debloat",
        "title": "Отключить виджеты и Copilot в панели задач",
        "title_en": "Disable widgets and Copilot on the taskbar",
        "desc": "Убирает кнопки Виджетов и Copilot (Win11), отключает ленту новостей.",
        "desc_en": "Hides the Widgets and Copilot buttons (Win11) and turns off "
                   "the news feed.",
        "admin": False,
        "apply": _opt_widgets_copilot,
    },
    {
        "key": "search_suggest",
        "group": "debloat",
        "title": "Отключить веб-советы в поиске",
        "title_en": "Disable web suggestions in search",
        "desc": "Убирает Bing-подсказки и «поисковые новости» в меню Пуск/поиске.",
        "desc_en": "Removes Bing suggestions and search highlights from Start "
                   "and search.",
        "admin": False,
        "apply": _opt_search_suggest,
    },
    {
        "key": "wer",
        "group": "debloat",
        "title": "Отключить отчёты об ошибках Windows",
        "title_en": "Disable Windows Error Reporting",
        "desc": "Отключает отправку/появление отчётов об ошибках. Обратимо.",
        "desc_en": "Stops sending and showing error reports. Reversible.",
        "admin": True,
        "apply": _opt_wer,
    },
]

# Безопасные по умолчанию (включаются при запуске «Отметить безопасные»).
SAFE_DEFAULT_KEYS = ["telemetry", "advertising", "search_suggest",
                     "background", "gamedvr", "startup_delay",
                     "visualfx", "widgets_copilot"]


def get_optimization(key: str):
    """Возвращает пункт оптимизации по ключу (или None)."""
    for item in OPTIMIZATIONS:
        if item["key"] == key:
            return item
    return None


def create_system_restore_point(desc: str = "Swept optimization") -> tuple:
    """
    Создаёт точку восстановления системы через PowerShell Checkpoint-Computer.

    Возвращает (ok, message). Требует прав администратора — без них Windows
    откажет, и мы об этом честно сообщаем (не «падаем»).
    """
    if winreg is None:
        return False, i18n.t("opt.not_windows")
    ps = system_tool("powershell.exe", "WindowsPowerShell", "v1.0")
    safe_desc = str(desc).replace('"', "'")
    script = ('Checkpoint-Computer -Description "{desc}" '
              '-RestorePointType "MODIFY_SETTINGS"').format(desc=safe_desc)
    code, out = _run([ps, "-NoProfile", "-NonInteractive", "-Command", script],
                     timeout=120)
    if code == 0:
        return True, ""
    text = (out or "").strip()
    if _denied_in_text(text):
        return False, admin_required_message()
    return False, (text[:200] or i18n.t("opt.restore_fail"))


def _ensure_restore_point(on_log=None) -> None:
    """Создаёт точку восстановления перед изменениями и логирует итог."""
    if on_log:
        on_log(i18n.t("opt.restore_creating"))
    ok, rmsg = create_system_restore_point()
    if on_log:
        if ok:
            on_log(i18n.t("opt.restore_ok"))
        else:
            on_log(i18n.t("opt.restore_skip", rmsg) if rmsg
                   else i18n.t("opt.restore_skip_no_admin"))


def apply_optimizations(keys, on_log=None, on_status=None,
                        stop_event=None, on_progress=None,
                        on_item_start=None, on_item_done=None,
                        create_restore_point: bool = True) -> dict:
    """
    Применяет выбранные оптимизации.

    keys — список ключей из OPTIMIZATIONS.
    Возвращает статистику:
        {'done': [...], 'skipped': [...], 'unsupported': [...],
         'failed': [...], 'details': [(key, kind, reason), ...]}

    Колбэки для интерфейса:
        on_progress(done, total)         — общий прогресс;
        on_item_start(key, index, total) — начинаем пункт (можно показать «3 из 8»);
        on_item_done(key, kind, reason)  — итог пункта: done/skipped/unsupported/failed.

    Разделение важно для интерфейса: «нет прав администратора» лечится
    перезапуском с повышением, «Windows защищает значение» — нет, а ошибка
    требует разбирательства. Раньше всё это сваливалось в «ошибки» или
    выдавалось за нехватку прав.
    """
    info = get_windows_info()
    if on_log:
        on_log("")
        on_log(i18n.t("opt.os", info["display"], info["build"],
                      info["edition"] or "—"))
        on_log(i18n.t("opt.items_count", len(keys)))

    items = [get_optimization(key) for key in keys]
    # Безопасность: перед изменениями создаём точку восстановления системы
    # (нужны права администратора; без них — просто предупреждаем, не падаем).
    if create_restore_point:
        _ensure_restore_point(on_log)
    return _run_items([item for item in items if item],
                      on_log=on_log, on_status=on_status,
                      stop_event=stop_event, on_progress=on_progress,
                      on_item_start=on_item_start, on_item_done=on_item_done)


def _run_items(items, on_log=None, on_status=None, stop_event=None,
               on_progress=None, on_item_start=None, on_item_done=None) -> dict:
    """
    Общий движок применения настроек.

    Каждый пункт запускается через свой "apply", а итог классифицируется как
    done/skipped/unsupported/failed; тексты итога — из i18n. Перед вызовом
    этого движка apply_optimizations уже создаёт точку восстановления системы.

    Разделение итогов важно для интерфейса: «нет прав администратора» лечится
    перезапуском с повышением, «Windows защищает значение» — нет, а ошибка
    требует разбирательства. Раньше всё это сваливалось в «ошибки» или
    выдавалось за нехватку прав.
    """
    stats = {"done": [], "skipped": [], "unsupported": [], "failed": [], "details": []}
    if winreg is None:
        if on_log:
            on_log(i18n.t("opt.not_windows"))
        return stats

    total = len(items)
    for index, item in enumerate(items, start=1):
        key = item["key"]
        if stop_event is not None and stop_event.is_set():
            if on_log:
                on_log(i18n.t("log.opt_stopped"))
            break
        if on_progress:
            on_progress(index, total)
        if on_item_start:
            on_item_start(key, index, total)
        if on_status:
            on_status(i18n.t("opt.applying_step",
                             index, total, i18n.fld(item, "title")))
        if on_log:
            on_log("")
            on_log(i18n.t("log.opt_item",
                          i18n.fld(item, "title"),
                          i18n.t("opt.admin_suffix") if item["admin"] else ""))
        action = item["apply"]
        try:
            ok, msg = action()
        except Exception as exc:
            ok, msg = False, repr(exc)
        if ok:
            kind = "done"
            stats["done"].append(key)
            if on_log:
                on_log(i18n.t("log.opt_ok"))
        elif is_admin_required(msg):
            kind = "skipped"
            stats["skipped"].append(key)
            if on_log:
                on_log(i18n.t("log.opt_skipped"))
        elif is_key_protected(msg):
            kind = "unsupported"
            stats["unsupported"].append(key)
            if on_log:
                on_log(i18n.t("log.opt_unsupported"))
        else:
            kind = "failed"
            stats["failed"].append(key)
            if on_log:
                on_log(i18n.t("log.opt_failed",
                              (msg or i18n.t("log.opt_unknown"))[:300]))
        stats["details"].append((key, kind, msg))
        if on_item_done:
            on_item_done(key, kind, msg)

    if on_progress:
        on_progress(total, total)
    if on_status:
        on_status(i18n.t("status.done"))
    return stats


def result_summary(stats: dict) -> str:
    """
    Итоговая строка для журнала и диалога: счётчики + названия проблемных
    пунктов с причиной. Одни цифры («Пропущено: 1») ничего не объясняют.
    """
    text = i18n.t("log.opt_result",
                  len(stats.get("done", [])),
                  len(stats.get("skipped", [])),
                  len(stats.get("unsupported", [])),
                  len(stats.get("failed", [])))
    lines = []
    for key, kind, reason in stats.get("details", []):
        if kind == "done":
            continue
        item = get_optimization(key)
        title = i18n.fld(item, "title") if item else key
        lines.append(i18n.t("log.opt_detail", title,
                            (reason or i18n.t("log.opt_unknown"))[:200]))
    if lines:
        text += "\n" + "\n".join(lines)
    return text


# ---------------------------------------------------------------------------
# Командная строка
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="Безопасная оптимизация Windows 10/11 (только настройки).")
    parser.add_argument("--list", action="store_true", help="показать доступные пункты")
    parser.add_argument("--apply", metavar="KEYS",
                        help="применить пункты через запятую (например: telemetry,advertising)")
    parser.add_argument("--all", action="store_true", help="применить все пункты")
    args = parser.parse_args(argv)

    info = get_windows_info()
    print("ОС: {} (build {}) | редакция: {}".format(
        info["display"], info["build"], info["edition"] or "—"))

    if args.list:
        for item in OPTIMIZATIONS:
            print("  {:<16} [{}]  {}".format(
                item["key"], "админ" if item["admin"] else "польз.",
                item["title"]))
        return 0

    if args.apply or args.all:
        if args.all:
            keys = [i["key"] for i in OPTIMIZATIONS]
        else:
            raw = [k.strip() for k in args.apply.split(",") if k.strip()]
            unknown = [k for k in raw if get_optimization(k) is None]
            if unknown:
                print("Неизвестные пункты (пропущены): " + ", ".join(unknown))
            keys = [k for k in raw if get_optimization(k) is not None]
            if not keys:
                print("Нечего применять.")
                return 2
        res = apply_optimizations(keys)
        print("\nВыполнено: {} | Пропущено (нет прав): {} | "
              "Недоступно в этой сборке: {} | Ошибки: {}".format(
                  len(res["done"]), len(res["skipped"]),
                  len(res["unsupported"]), len(res["failed"])))
        print(result_summary(res))
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
