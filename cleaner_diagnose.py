#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
r"""
cleaner_diagnose.py — разбор «почему компьютер тормозит».

Зачем это нужно
---------------
Чек-лист оптимизаций отвечает на вопрос «что можно сделать». Этот модуль
отвечает на другой: «что именно мешает прямо сейчас». Он ничего не меняет —
только измеряет машину и объясняет причины.

Отличие от «оптимизаторов» с кнопкой «ускорить»: каждая причина несёт
конкретное число (сколько программ в автозагрузке, сколько места на диске,
сколько занято ОЗУ), поэтому вердикт можно проверить глазами. Балл 0..100 —
не «оценка Windows», а сумма штрафов за найденные причины: 100 — ничего
не найдено, 0 — всё сразу.

Публичное API
-------------
    collect_metrics()  -> dict   измерения (медленная часть, ~1 с)
    analyze(metrics)   -> dict   чистая логика: score / verdict / causes
    diagnose()         -> dict   collect_metrics + analyze
    fix_keys(report)   -> list   какие галочки оптимизации отметить

analyze() не трогает систему — её можно проверять на синтетических данных.
"""

from __future__ import annotations

import os
import shutil
import subprocess

try:
    import winreg
except ImportError:  # не Windows — модуль просто не найдёт причин
    winreg = None

CREATE_NO_WINDOW = 0x08000000

# ---------------------------------------------------------------------------
# Пороги и веса
# ---------------------------------------------------------------------------
# Сколько баллов снимается за каждую причину. «Железные» причины весят
# больше косметических: автозагрузка и забитый диск действительно тормозят
# систему, а тени под окнами — почти нет.
WEIGHTS = {
    "startup_many": 15,
    "disk_low": 15,
    "disk_hdd": 12,
    "ram_low": 10,
    "ram_full": 10,
    "telemetry": 3,
    "gamedvr": 3,
    "background": 3,
    "power": 3,
    "visualfx": 2,
}

# Уровень важности — для сортировки и цвета в интерфейсе.
SEVERITY = {
    "startup_many": "high",
    "disk_low": "high",
    "disk_hdd": "medium",
    "ram_low": "medium",
    "ram_full": "medium",
    "telemetry": "low",
    "gamedvr": "low",
    "background": "low",
    "power": "low",
    "visualfx": "low",
}

# Границы «нормально / плохо».
STARTUP_MEDIUM = 8        # программ в автозагрузке
STARTUP_HIGH = 12
DISK_LOW_PCT = 15.0       # свободного места, %
DISK_MEDIUM_PCT = 10.0
DISK_HIGH_PCT = 5.0
RAM_MIN_BYTES = 8 * 1024 ** 3    # 8 ГБ — минимум для Windows 11
RAM_FULL_PCT = 88.0       # занято ОЗУ, %

# Порог вердикта: сверху вниз.
VERDICTS = ((88, "excellent"), (70, "good"), (50, "fair"), (0, "bad"))

# Ветки реестра автозагрузки: (ветка, путь, путь StartupApproved в той же ветке).
# Ветка записывается строкой, а не константой winreg: модуль должен
# импортироваться и на системах без winreg.
RUN_KEYS = (
    ("hkcu", r"Software\Microsoft\Windows\CurrentVersion\Run",
     r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    ("hklm", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
     r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    ("hklm", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
     r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
)

# Схемы электропитания Windows (GUID -> наш ключ).
POWER_PLANS = {
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "high",
    "381b4222-f694-41f0-9685-ff5bb260df2e": "balanced",
    "a1841308-3541-4fab-bc81-f71556f20b4a": "saver",
}

# Кэш типа диска: PowerShell отвечает ~1 с, а значение за сеанс не меняется.
_DISK_TYPE = None
_DISK_TYPE_DONE = False


# ---------------------------------------------------------------------------
# Мелкие помощники
# ---------------------------------------------------------------------------

def _run(cmd, timeout=15):
    """Запускает команду без окна консоли. Возвращает (код, вывод)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, errors="ignore",
            creationflags=CREATE_NO_WINDOW, timeout=timeout,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except Exception as exc:  # noqa: BLE001 - причина не критична для разбора
        return -1, str(exc)


def _powershell():
    """Путь к powershell.exe (в системной папке, не из PATH)."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    path = os.path.join(system_root, "System32", "WindowsPowerShell",
                        "v1.0", "powershell.exe")
    return path if os.path.isfile(path) else "powershell.exe"


def _reg_value(hive, path, name, default=None):
    """Значение из реестра или default, если ключа/значения нет."""
    if winreg is None:
        return default
    try:
        with winreg.OpenKey(hive, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def _hive(name: str):
    """Корень реестра по короткому имени ('hkcu' / 'hklm')."""
    if winreg is None:
        return None
    return winreg.HKEY_CURRENT_USER if name == "hkcu" else winreg.HKEY_LOCAL_MACHINE


def _cause(key: str, fix: str | None = None, severity: str | None = None,
           weight: int | None = None, **value) -> dict:
    """Собирает одну найденную причину.

    severity/weight можно переопределить: одна и та же причина бувает
    лёгкой и тяжёлой (диск на 14% свободен — мелочь, на 3% — беда).
    """
    return {
        "key": key,
        "severity": severity or SEVERITY.get(key, "low"),
        "weight": WEIGHTS.get(key, 0) if weight is None else weight,
        "fix": fix,
        "value": value,
    }


# ---------------------------------------------------------------------------
# Измерения
# ---------------------------------------------------------------------------

def _startup_is_enabled(hive, approved_path, name) -> bool:
    """Включена ли программа в автозагрузке (учёт состояния из Диспетчера задач).

    Windows хранит состояние в StartupApproved: первый байт чётный —
    включено, нечётный — выключено. Записи нет — программа запускается.
    """
    if winreg is None:
        return True
    try:
        with winreg.OpenKey(hive, approved_path) as key:
            data, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return True
    if isinstance(data, bytes) and data:
        return data[0] % 2 == 0
    return True


def _startup_folders() -> tuple:
    """Папки автозагрузки пользователя и общая."""
    appdata = os.environ.get("APPDATA") or ""
    programdata = os.environ.get("ProgramData") or r"C:\ProgramData"
    tail = os.path.join("Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    folders = []
    if appdata:
        folders.append(os.path.join(appdata, tail))
    folders.append(os.path.join(programdata, tail))
    return tuple(folders)


def _startup_metrics() -> dict:
    """Сколько программ стартует вместе с Windows."""
    enabled = total = 0
    if winreg is not None:
        for hive_name, run_path, approved_path in RUN_KEYS:
            hive = _hive(hive_name)
            try:
                with winreg.OpenKey(hive, run_path) as key:
                    count = winreg.QueryInfoKey(key)[1]
                    for index in range(count):
                        name = winreg.EnumValue(key, index)[0]
                        total += 1
                        if _startup_is_enabled(hive, approved_path, name):
                            enabled += 1
            except OSError:
                continue
    # Ярлыки в папках «Автозагрузка» — тоже автозагрузка.
    for folder in _startup_folders():
        try:
            for entry in os.listdir(folder):
                if entry.lower().endswith(".lnk"):
                    total += 1
                    enabled += 1
        except OSError:
            continue
    return {"startup_enabled": enabled, "startup_total": total}


def _disk_metrics() -> dict:
    """Место на системном диске."""
    drive = (os.environ.get("SystemDrive") or "C:") + "\\"
    try:
        usage = shutil.disk_usage(drive)
        return {"disk_drive": drive[:2], "disk_total": usage.total,
                "disk_free": usage.free}
    except OSError:
        return {"disk_drive": drive[:2], "disk_total": 0, "disk_free": 0}


def _ram_metrics() -> dict:
    """Физическая память: всего и свободно (GlobalMemoryStatusEx, без админа)."""
    try:
        import ctypes
        from ctypes import wintypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return {"ram_total": int(status.ullTotalPhys),
                    "ram_free": int(status.ullAvailPhys)}
    except Exception:
        pass
    return {"ram_total": 0, "ram_free": 0}


def _active_power_plan() -> str | None:
    """Активная схема электропитания: high / balanced / saver / other."""
    code, out = _run(["powercfg", "/getactivescheme"], timeout=10)
    if code != 0:
        return None
    text = (out or "").lower()
    for guid, plan in POWER_PLANS.items():
        if guid in text:
            return plan
    return "other"


def _setting_metrics() -> dict:
    """Включены ли телеметрия, Game DVR, фоновые приложения, эффекты."""
    hklm, hkcu = _hive("hklm"), _hive("hkcu")
    # Телеметрия выключена, если стоит политика AllowTelemetry=0
    # или служба DiagTrack переведена в «отключена» (Start=4).
    policy = _reg_value(hklm, r"SOFTWARE\Policies\Microsoft\Windows\DataCollection",
                        "AllowTelemetry", None)
    service_start = _reg_value(hklm,
                               r"SYSTEM\CurrentControlSet\Services\DiagTrack",
                               "Start", None)
    telemetry_off = (policy == 0) or (service_start == 4)

    base = r"Software\Microsoft\Windows\CurrentVersion"
    gamedvr = _reg_value(hkcu, r"System\GameConfigStore",
                         "GameDVR_Enabled", 1) != 0
    background = _reg_value(hkcu, base + r"\BackgroundAccessApplications",
                            "GlobalUserDisabled", 0) != 1
    visualfx = _reg_value(hkcu, base + r"\Explorer\VisualEffects",
                          "VisualFXSetting", 0) != 2
    return {"telemetry": not telemetry_off,
            "gamedvr": gamedvr,
            "background": background,
            "visualfx": visualfx}


def _disk_type() -> str | None:
    """Тип системного диска: 'ssd', 'hdd' или None (не удалось узнать).

    Определяется через Get-PhysicalDisk — это единственный надёжный способ
    без драйверов. Ответ кэшируется: за сеанс он не меняется.
    """
    global _DISK_TYPE, _DISK_TYPE_DONE
    if _DISK_TYPE_DONE:
        return _DISK_TYPE
    _DISK_TYPE_DONE = True
    letter = (os.environ.get("SystemDrive") or "C:")[:1].upper()
    # Цепочка «раздел -> диск -> физический диск»: только у физического
    # диска MediaType заполнен (у Get-Disk он часто пустой).
    script = (
        "(Get-Partition -DriveLetter " + letter +
        " -ErrorAction SilentlyContinue | Get-Disk -ErrorAction SilentlyContinue |"
        " Get-PhysicalDisk -ErrorAction SilentlyContinue).MediaType"
    )
    code, out = _run([_powershell(), "-NoProfile", "-NonInteractive",
                      "-Command", script], timeout=20)
    text = (out or "").strip().lower()
    if code == 0 and "ssd" in text:
        _DISK_TYPE = "ssd"
    elif code == 0 and "hdd" in text:
        _DISK_TYPE = "hdd"
    else:
        _DISK_TYPE = None
    return _DISK_TYPE


def collect_metrics(with_disk_type: bool = True) -> dict:
    """Собирает все измерения. Ничего не меняет и не требует админа.

    ``with_disk_type=False`` пропускает запрос к PowerShell — разбор
    становится мгновенным (нужно тестам и быстрой перерисовке).
    """
    metrics = {
        "startup_enabled": 0,
        "startup_total": 0,
        "disk_drive": "C:",
        "disk_total": 0,
        "disk_free": 0,
        "disk_type": None,
        "ram_total": 0,
        "ram_free": 0,
        "power_plan": None,
        "telemetry": None,
        "gamedvr": None,
        "background": None,
        "visualfx": None,
    }
    for part in (_startup_metrics(), _disk_metrics(), _ram_metrics(),
                 _setting_metrics()):
        try:
            metrics.update(part)
        except Exception:  # noqa: BLE001 - одно измерение не должно ломать разбор
            continue
    try:
        metrics["power_plan"] = _active_power_plan()
    except Exception:  # noqa: BLE001
        pass
    if with_disk_type:
        try:
            metrics["disk_type"] = _disk_type()
        except Exception:  # noqa: BLE001
            pass
    return metrics


# ---------------------------------------------------------------------------
# Логика разбора (без обращений к системе)
# ---------------------------------------------------------------------------

def analyze(metrics: dict) -> dict:
    """Превращает измерения в балл, вердикт и список причин.

    Функция чистая: на вход только словарь измерений, поэтому её поведение
    полностью проверяется тестами на синтетических данных.
    """
    metrics = metrics or {}
    causes = []

    startup = int(metrics.get("startup_enabled") or 0)
    if startup >= STARTUP_HIGH:
        causes.append(_cause("startup_many", n=startup, severity="high"))
    elif startup >= STARTUP_MEDIUM:
        causes.append(_cause("startup_many", n=startup, severity="medium",
                             weight=8))

    total = int(metrics.get("disk_total") or 0)
    free = int(metrics.get("disk_free") or 0)
    if total > 0:
        pct = free * 100.0 / total
        disk_value = {"drive": metrics.get("disk_drive") or "C:",
                      "free": free, "pct": pct}
        if pct < DISK_HIGH_PCT:
            causes.append(_cause("disk_low", severity="high", **disk_value))
        elif pct < DISK_MEDIUM_PCT:
            causes.append(_cause("disk_low", severity="medium", weight=9,
                                 **disk_value))
        elif pct < DISK_LOW_PCT:
            causes.append(_cause("disk_low", severity="low", weight=4,
                                 **disk_value))

    if metrics.get("disk_type") == "hdd":
        causes.append(_cause("disk_hdd"))

    ram_total = int(metrics.get("ram_total") or 0)
    ram_free = int(metrics.get("ram_free") or 0)
    if 0 < ram_total < RAM_MIN_BYTES:
        gb_value = ram_total / 1024 ** 3
        # 8.0 ГБ читается хуже, чем 8 ГБ, но 7.5 ГБ округлять нельзя.
        gb = int(round(gb_value)) if abs(gb_value - round(gb_value)) < 0.05 \
            else round(gb_value, 1)
        causes.append(_cause("ram_low", gb=gb))
    if ram_total > 0:
        used_pct = (ram_total - ram_free) * 100.0 / ram_total
        if used_pct >= RAM_FULL_PCT:
            causes.append(_cause("ram_full", pct=int(used_pct)))

    if metrics.get("telemetry"):
        causes.append(_cause("telemetry", fix="telemetry"))
    if metrics.get("gamedvr"):
        causes.append(_cause("gamedvr", fix="gamedvr"))
    if metrics.get("background"):
        causes.append(_cause("background", fix="background"))
    if metrics.get("power_plan") in ("balanced", "saver", "other"):
        causes.append(_cause("power", fix="power",
                             plan=metrics.get("power_plan")))
    if metrics.get("visualfx"):
        causes.append(_cause("visualfx", fix="visualfx"))

    # Весомые причины — сверху: пользователь читает первые строки.
    causes.sort(key=lambda item: -item["weight"])

    penalty = sum(item["weight"] for item in causes)
    score = max(0, min(100, 100 - penalty))
    verdict = "bad"
    for threshold, name in VERDICTS:
        if score >= threshold:
            verdict = name
            break

    fixes = []
    for item in causes:
        fix = item.get("fix")
        if fix and fix not in fixes:
            fixes.append(fix)

    return {
        "score": score,
        "verdict": verdict,
        "causes": causes,
        "fixes": fixes,
        "metrics": metrics,
        "ok": bool(metrics),
    }


def fix_keys(report: dict) -> list:
    """Ключи оптимизаций, которые закрывают найденные причины."""
    return list((report or {}).get("fixes") or [])


def diagnose(with_disk_type: bool = True) -> dict:
    """Полный разбор: измерения + логика."""
    return analyze(collect_metrics(with_disk_type=with_disk_type))


def main(argv=None):
    """Быстрый разбор из консоли (отладка): python cleaner_diagnose.py"""
    report = diagnose()
    print("Балл: {}/100 — {}".format(report["score"], report["verdict"]))
    for cause in report["causes"]:
        print("  • {} ({}, -{})".format(cause["key"], cause["severity"],
                                        cause["weight"]))
        if cause["value"]:
            print("    ", cause["value"])
    print("Исправления:", ", ".join(report["fixes"]) or "нет")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
