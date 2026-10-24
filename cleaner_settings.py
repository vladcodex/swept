#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_settings.py — ХРАНЕНИЕ НАСТРОЕК ПРОГРАММЫ В РЕЕСТРЕ WINDOWS.

Идея (как в Reg Organizer)
--------------------------
Настройки живут в ветке реестра
    HKEY_CURRENT_USER\Software\Swept
в строковом параметре `Language` (значения "ru" / "en"). Читаем при старте,
пишем сразу при смене языка — без файлов и без перезапуска.

Почему реестр, а не файл
------------------------
    * HKCU не требует прав администратора — пишет обычный пользователь;
    * настройка привязана к пользователю, а не к папке с программой
      (exe можно перенести, язык останется);
    * не остаётся мусора рядом с exe в Program Files, куда писать нельзя.

Запасные варианты
-----------------
    * Если `winreg` недоступен (не Windows, юнит-тесты) — используется
      обычный JSON-файл рядом с программой.
    * Если параметра в реестре ещё нет, но есть старый settings.json
      (версии до 1.1), значение из него переносится в реестр один раз.

Автор: WorkBuddy AI
"""

from __future__ import annotations

import json
import os
import sys

try:
    import winreg
except ImportError:  # pragma: no cover - не Windows
    winreg = None

# Ветка и параметр, где хранится язык интерфейса.
REG_PATH = r"Software\Swept"
REG_VALUE_LANGUAGE = "Language"

# Язык по умолчанию, если в реестре ничего нет.
DEFAULT_LANGUAGE = "ru"

# Допустимые коды языков (совпадают с ключами cleaner_i18n.STRINGS).
SUPPORTED_LANGUAGES = ("ru", "en")


def _json_path() -> str:
    """Путь к settings.json рядом с программой (запасной вариант хранения)."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "settings.json")


class Settings:
    """
    Настройки приложения: реестр Windows, при недоступности — JSON-файл.

    Использование:
        settings = Settings()
        settings.get_language()          # "ru" по умолчанию
        settings.set_language("en")      # сразу пишется в реестр
    """

    def __init__(self, reg_path: str = REG_PATH):
        self.reg_path = reg_path
        self._cache = {}

    # ------------------------------------------------------------------ реестр
    def _read_registry(self, name: str):
        """Читает строковый параметр из реестра. None — нет ключа/значения."""
        if winreg is None:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.reg_path,
                                0, winreg.KEY_READ) as key:
                value, kind = winreg.QueryValueEx(key, name)
        except OSError:
            # Нет ветки, нет параметра или нет доступа — считаем, что значения нет.
            return None
        if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
            return None
        return str(value)

    def _write_registry(self, name: str, value: str) -> bool:
        """Пишет строковый параметр в реестр. True — запись удалась."""
        if winreg is None:
            return False
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.reg_path,
                                    0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(value))
            return True
        except OSError:
            # Реестр недоступен (политика, урезанная система) — не падаем.
            return False

    # ------------------------------------------------------------------- файл
    def _read_file(self) -> dict:
        """Читает JSON-файл настроек (запасной вариант и миграция)."""
        try:
            with open(_json_path(), "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _write_file(self, name: str, value) -> bool:
        """Пишет значение в JSON-файл, сохраняя остальные ключи."""
        path = _json_path()
        data = self._read_file()
        data[name] = value
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    # --------------------------------------------------------------- публично
    def get(self, name: str, default: str = "") -> str:
        """Строковая настройка: сначала реестр, потом файл, потом default."""
        if name in self._cache:
            return self._cache[name]
        value = self._read_registry(name)
        if value is None:
            file_data = self._read_file()
            # В старом settings.json ключ записан строчными ("language"),
            # в реестре — "Language", поэтому ищем без учёта регистра.
            file_value = file_data.get(name)
            if file_value is None:
                file_value = file_data.get(name.lower())
            if isinstance(file_value, str) and file_value:
                # Переносим старую настройку из файла в реестр (однократно).
                if self._write_registry(name, file_value):
                    value = file_value
                else:
                    return file_value
            else:
                return default
        self._cache[name] = value
        return value

    def set(self, name: str, value: str) -> bool:
        """Сохраняет настройку: реестр, а при неудаче — файл."""
        self._cache[name] = value
        if self._write_registry(name, value):
            return True
        return self._write_file(name, value)

    # ---------------------------------------------------------------- язык
    def get_language(self) -> str:
        """
        Текущий язык интерфейса.

        Если в реестре нет записи или там неизвестный код — русский
        (значение по умолчанию, как и требует задача).
        """
        code = self.get(REG_VALUE_LANGUAGE, DEFAULT_LANGUAGE).strip().lower()
        return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    def set_language(self, code: str) -> bool:
        """Сохраняет выбранный язык в реестр. True — запись удалась."""
        code = (code or "").strip().lower()
        if code not in SUPPORTED_LANGUAGES:
            return False
        return self.set(REG_VALUE_LANGUAGE, code)


# Один общий экземпляр на всё приложение.
_settings = Settings()


def get_settings() -> Settings:
    """Экземпляр настроек (единственный на процесс)."""
    return _settings


def load_language() -> str:
    """Язык из реестра (или "ru", если записи нет)."""
    return _settings.get_language()


def save_language(code: str) -> bool:
    """Записывает язык в реестр немедленно."""
    return _settings.set_language(code)


def registry_key_path() -> str:
    """Полный путь ветки реестра — для журнала и сообщений интерфейса."""
    return "HKEY_CURRENT_USER\\" + REG_PATH


# ===========================================================================
# НАСТРОЙКИ ОЧИСТКИ БРАУЗЕРОВ (раздельные под-опции: кэш/cookie/история/…)
# ===========================================================================
# Хранятся как строка "cache,cookies,history" в параметре
# "BrowserOptions_<ключ_браузера>" (chrome/yandex/edge/firefox). Если записи
# нет — используется умолчание ядра (только кэш).
_BROWSER_OPTS_PREFIX = "BrowserOptions_"


def _parse_browser_options(text: str):
    """Разбирает逗号-разделённую строку в множество ключей. None — пусто."""
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    return set(parts) if parts else None


def get_browser_options(key: str) -> set:
    """
    Возвращает множество включённых под-опций для браузера.

    Если в хранилище ничего нет — умолчание ядра (default_browser_suboptions,
    т.е. только кэш). Невалидные ключи отбрасываются.
    """
    import cleaner_core  # локально — чтобы не было циклического импорта
    raw = _settings.get(_BROWSER_OPTS_PREFIX + key, "")
    parsed = _parse_browser_options(raw)
    if parsed is None:
        return cleaner_core.default_browser_suboptions(key)
    valid = {s["key"] for s in cleaner_core.get_browser_suboptions(key)}
    result = {k for k in parsed if k in valid}
    # Если всё отфильтровалось (битые данные) — возвращаем умолчание.
    return result if result else cleaner_core.default_browser_suboptions(key)


def set_browser_options(key: str, options) -> bool:
    """Сохраняет множество включённых под-опций браузера. True — записано."""
    value = ",".join(sorted(set(options)))
    return _settings.set(_BROWSER_OPTS_PREFIX + key, value)


if __name__ == "__main__":  # небольшая самопроверка из командной строки
    print("Ветка реестра :", registry_key_path())
    print("Язык сейчас   :", load_language())
    print("Файл настроек :", _json_path())
