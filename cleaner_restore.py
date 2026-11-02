#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
r"""
cleaner_restore.py — ТОЧКИ ВОССТАНОВЛЕНИЯ WINDOWS: СПИСОК, СОЗДАНИЕ, ОТКАТ.

Зачем отдельный модуль
----------------------
Собственный откат Swept (журнал снимков в cleaner_optimize) возвращает
только то, что меняла сама программа. Точка восстановления — единственный
способ откатить всё остальное: чужие установщики, драйверы, обновления.
Поэтому в интерфейсе это две соседние секции одного диалога: «снимки
реестра» и «точки восстановления».

Правила безопасности
--------------------
    * Только штатные средства Windows: `Get-ComputerRestorePoint`,
      `Checkpoint-Computer`, `Restore-Computer`. Своей логики восстановления
      здесь нет и быть не может.
    * Никакой оболочки: команда — это список аргументов, `shell=False`.
      PowerShell берётся из `%SystemRoot%\System32` через core.system_tool,
      а не из PATH: приложение работает с правами администратора, и
      подложенный powershell.exe унаследовал бы повышение прав.
    * Номер точки восстановления проверяется как целое число перед подстановкой
      в скрипт: строка из интерфейса в команду не попадает.
    * Восстановление системы перезагружает компьютер и необратимо для
      изменений после точки — интерфейс обязан спросить подтверждение,
      а модуль только выполняет то, что подтвердили.
"""

from __future__ import annotations

import json
import subprocess

import cleaner_i18n as i18n
from cleaner_core import is_admin, system_tool

# Флаг: не показывать чёрное окно консоли.
CREATE_NO_WINDOW = 0x08000000

# Признаки того, что защита системы выключена: тогда точек нет не потому,
# что их не создавали, а потому что Windows их не создаёт вовсе. Это разные
# сообщения для пользователя, и лечатся они по-разному.
_DISABLED_MARKERS = (
    "system restore is disabled",
    "восстановление системы отключено",
    "защита системы отключена",
    "not enabled",
    "не включена",
    "0x80070422",          # служба отключена
)

_DENIED_MARKERS = (
    "access is denied",
    "access denied",
    "отказано в доступе",
    "requires elevation",
    "требует повышения",
    "повышения прав",
    "administrator",
    "администратор",
)


def _decode(raw: bytes) -> str:
    """
    Декодирует вывод PowerShell.

    Консоль Windows на русской системе отдаёт cp866, а сам скрипт мы просим
    писать в UTF-8 ([Console]::OutputEncoding). Поэтому сначала UTF-8,
    потом OEM-кодировка консоли, и только в крайнем случае — локаль.
    """
    if not raw:
        return ""
    for codec in ("utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _run_ps(script: str, timeout: int = 120) -> tuple:
    """
    Выполняет PowerShell-скрипт. Возвращает (код, stdout+stderr).

    Скрипт — фиксированная строка из этого модуля; пользовательские данные
    попадают в него только после проверки (номер точки — int, описание —
    очищено от кавычек).
    """
    ps = system_tool("powershell.exe", "WindowsPowerShell", "v1.0")
    # Вывод в UTF-8: иначе кириллица в описании точки приходит «кракозябрами».
    full = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; " + script
    try:
        proc = subprocess.run(
            [ps, "-NoProfile", "-NonInteractive", "-Command", full],
            capture_output=True, timeout=timeout,
            creationflags=CREATE_NO_WINDOW, shell=False,
        )
    except FileNotFoundError:
        return -1, "powershell.exe not found"
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except Exception as exc:  # pragma: no cover - сбой запуска
        return -1, str(exc)
    return proc.returncode, _decode((proc.stdout or b"") + (proc.stderr or b""))


def _text_has(text: str, markers) -> bool:
    """True, если в тексте есть хоть один из маркеров (без учёта регистра)."""
    lowered = (text or "").lower()
    return any(marker in lowered for marker in markers)


def protection_disabled(text: str) -> bool:
    """True, если ответ Windows означает «защита системы выключена»."""
    return _text_has(text, _DISABLED_MARKERS)


def access_denied(text: str) -> bool:
    """True, если ответ Windows означает отказ в доступе."""
    return _text_has(text, _DENIED_MARKERS)


# ---------------------------------------------------------------------------
# Список точек
# ---------------------------------------------------------------------------

# Скрипт отдаёт уже готовые поля: номер, описание и время в читаемом виде.
# ConvertToDateTime делает WMI-строку вида 20261102143000.000000-180
# нормальной датой — разбирать её регуляркой в Python было бы лишним риском.
_LIST_SCRIPT = (
    "$ErrorActionPreference='Stop'; "
    "Get-ComputerRestorePoint | ForEach-Object { "
    "[pscustomobject]@{ "
    "seq=[int]$_.SequenceNumber; "
    "desc=[string]$_.Description; "
    "time=$_.ConvertToDateTime($_.CreationTime).ToString('yyyy-MM-dd HH:mm') "
    "} } | ConvertTo-Json -Compress"
)


def parse_points_json(text: str) -> list:
    """
    Разбирает JSON от PowerShell в список точек.

    ConvertTo-Json на одном объекте отдаёт объект, а не массив, а на пустом
    списке — пустую строку. Оба случая обрабатываются здесь, чтобы интерфейс
    получал всегда список.
    """
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    points = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            seq = int(item.get("seq") or 0)
        except (TypeError, ValueError):
            continue
        if seq <= 0:
            continue
        points.append({
            "seq": seq,
            "desc": str(item.get("desc") or "").strip(),
            "time": str(item.get("time") or "").strip(),
        })
    # Новые сверху: пользователь почти всегда ищет последнюю точку.
    points.sort(key=lambda p: p["seq"], reverse=True)
    return points


def list_restore_points() -> dict:
    """
    Возвращает список точек восстановления.

    Результат:
        {"ok": bool, "points": [...], "error": str, "disabled": bool,
         "needs_admin": bool}
    """
    result = {"ok": False, "points": [], "error": "",
              "disabled": False, "needs_admin": False}
    code, out = _run_ps(_LIST_SCRIPT, timeout=90)
    points = parse_points_json(out)
    if code == 0:
        result.update(ok=True, points=points)
        return result
    if protection_disabled(out):
        result.update(ok=True, disabled=True, points=[])
        return result
    if access_denied(out):
        result.update(error=i18n.t("rp.no_admin"), needs_admin=True)
        return result
    result["error"] = (out or "").strip()[:300] or "Get-ComputerRestorePoint failed"
    return result


# ---------------------------------------------------------------------------
# Создание точки
# ---------------------------------------------------------------------------

def create_restore_point(desc: str = "Swept") -> tuple:
    """
    Создаёт точку восстановления.

    Реализация живёт в cleaner_optimize (она же используется кнопкой на
    вкладке оптимизации и планировщиком), здесь — тонкая обёртка, чтобы
    интерфейсу отката не приходилось знать о двух модулях.
    """
    from cleaner_optimize import create_system_restore_point
    return create_system_restore_point(desc)


# ---------------------------------------------------------------------------
# Восстановление
# ---------------------------------------------------------------------------

def valid_sequence(seq) -> bool:
    """True, если номер точки — положительное целое (защита от подстановки)."""
    try:
        return 0 < int(seq) < 1000000
    except (TypeError, ValueError):
        return False


def restore_to_point(seq) -> tuple:
    """
    Запускает восстановление системы по точке `seq`.

    Возвращает (ok, message). Windows перезагрузит компьютер — это не наша
    логика, а поведение `Restore-Computer`; интерфейс предупреждает об этом
    до вызова.

    Без прав администратора Windows откажет — сообщаем это отдельной строкой,
    а не «ошибкой -1».
    """
    if not valid_sequence(seq):
        return False, "bad restore point number"
    if not is_admin():
        return False, i18n.t("rp.no_admin")
    number = int(seq)
    script = ("$ErrorActionPreference='Stop'; "
              "Restore-Computer -RestorePoint {seq} -Confirm:$false").format(seq=number)
    code, out = _run_ps(script, timeout=300)
    if code == 0:
        return True, ""
    text = (out or "").strip()
    if access_denied(text):
        return False, i18n.t("rp.no_admin")
    if protection_disabled(text):
        return False, i18n.t("rp.disabled")
    return False, (text[:300] or "Restore-Computer failed")


def protection_enabled() -> dict:
    """
    Состояние защиты системы — для строки-подсказки в диалоге отката.

    {"enabled": True/False/None, "count": N, "error": str, "needs_admin": bool}
    enabled=None — определить не удалось (нет прав, сбой PowerShell).
    """
    info = list_restore_points()
    if info.get("disabled"):
        return {"enabled": False, "count": 0, "error": "", "needs_admin": False}
    if info.get("ok"):
        return {"enabled": True, "count": len(info.get("points") or []),
                "error": "", "needs_admin": False}
    return {"enabled": None, "count": 0, "error": info.get("error", ""),
            "needs_admin": bool(info.get("needs_admin"))}


def describe_point(point: dict) -> str:
    """Читаемая подпись точки: «2026-11-02 14:30 — Swept (точка №12)»."""
    time_text = point.get("time") or "—"
    desc = (point.get("desc") or "").strip() or "—"
    return "{} — {} ({})".format(time_text, desc,
                                 i18n.t("rp.seq", point.get("seq", 0)))


def _self_check() -> int:
    """Небольшая самопроверка из командной строки (без изменений в системе)."""
    print("PowerShell:", system_tool("powershell.exe", "WindowsPowerShell", "v1.0"))
    print("Права администратора:", "есть" if is_admin() else "нет")
    info = list_restore_points()
    if info["ok"] and info.get("disabled"):
        print(i18n.t("rp.disabled"))
        return 0
    if not info["ok"]:
        print("Ошибка:", info["error"])
        return 1
    if not info["points"]:
        print(i18n.t("rp.empty"))
        return 0
    print("Точек:", len(info["points"]))
    for point in info["points"]:
        print("  " + describe_point(point))
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())
