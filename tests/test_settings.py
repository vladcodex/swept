#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Тесты хранилища настроек.

Проверяются оба пути — реестр и файл, — а также поведение при отказе записи.
Последнее важно: интерфейс показывает «сохранено» только тогда, когда запись
действительно удалась.
"""

from __future__ import annotations

import json
import uuid

import pytest

import cleaner_core as core
import cleaner_settings as settings_mod


# --------------------------------------------------------------------------
# Режим файла (портативная сборка)
# --------------------------------------------------------------------------
@pytest.fixture
def file_mode(tmp_path, monkeypatch):
    """Настройки пишутся в JSON рядом с программой, реестр не трогается."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_json_path", lambda: str(path))
    monkeypatch.setattr(settings_mod, "is_portable", lambda: True)
    instance = settings_mod.Settings()
    monkeypatch.setattr(settings_mod, "_settings", instance)
    return instance, path


class TestFileMode:
    def test_roundtrip(self, file_mode):
        settings, path = file_mode
        assert settings.set("Language", "en") is True
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8"))["Language"] == "en"
        assert settings.get("Language") == "en"

    def test_missing_value_returns_default(self, file_mode):
        settings, _path = file_mode
        assert settings.get("Language", "ru") == "ru"

    def test_write_keeps_other_keys(self, file_mode):
        settings, path = file_mode
        settings.set("Language", "en")
        settings.set("BrowserOptions_chrome", "cache,cookies")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"Language": "en", "BrowserOptions_chrome": "cache,cookies"}

    def test_broken_json_is_not_fatal(self, file_mode):
        settings, path = file_mode
        path.write_text("{ это не json", encoding="utf-8")
        assert settings.get("Language", "ru") == "ru"

    def test_failed_write_does_not_poison_cache(self, tmp_path, monkeypatch):
        # Регрессия: раньше значение попадало в кеш до записи, и get()
        # отдавал его, хотя на диск ничего не легло.
        missing_dir = tmp_path / "no-such-dir" / "settings.json"
        monkeypatch.setattr(settings_mod, "_json_path", lambda: str(missing_dir))
        monkeypatch.setattr(settings_mod, "is_portable", lambda: True)
        settings = settings_mod.Settings()

        assert settings.set("Language", "en") is False
        assert settings.get("Language", "ru") == "ru"

    def test_no_temporary_file_left_behind(self, tmp_path, monkeypatch):
        path = tmp_path / "settings.json"
        monkeypatch.setattr(settings_mod, "_json_path", lambda: str(path))
        monkeypatch.setattr(settings_mod, "is_portable", lambda: True)
        settings = settings_mod.Settings()
        settings.set("Language", "en")
        assert not (tmp_path / "settings.json.tmp").exists()


# --------------------------------------------------------------------------
# Режим реестра (обычная сборка)
# --------------------------------------------------------------------------
@pytest.fixture
def registry_settings():
    """Отдельная временная ветка реестра, которая удаляется после теста."""
    if settings_mod.winreg is None:
        pytest.skip("реестр недоступен")
    parent = r"Software\SweptTests"
    branch = r"{}\{}".format(parent, uuid.uuid4().hex)
    settings = settings_mod.Settings(reg_path=branch)
    try:
        yield settings
    finally:
        for name in ("Language", "BrowserOptions_chrome", "test"):
            try:
                with settings_mod.winreg.OpenKey(
                        settings_mod.winreg.HKEY_CURRENT_USER, branch, 0,
                        settings_mod.winreg.KEY_ALL_ACCESS) as key:
                    settings_mod.winreg.DeleteValue(key, name)
            except OSError:
                pass
        # Удаляем сначала свою ветку, затем общую родительскую: без этого
        # после прогона в реестре оставалась пустая Software\SweptTests.
        # Если родительская не пуста (параллельный прогон) — DeleteKey
        # бросит OSError, и это нормально.
        for path in (branch, parent):
            try:
                settings_mod.winreg.DeleteKey(
                    settings_mod.winreg.HKEY_CURRENT_USER, path)
            except OSError:
                pass


class TestRegistryMode:
    def test_roundtrip(self, registry_settings):
        assert registry_settings.set("test", "value") is True
        assert registry_settings.get("test") == "value"

    def test_value_survives_new_instance(self, registry_settings):
        registry_settings.set("test", "value")
        fresh = settings_mod.Settings(reg_path=registry_settings.reg_path)
        assert fresh.get("test") == "value"

    def test_cache_is_case_insensitive(self, registry_settings):
        registry_settings.set("Language", "en")
        assert registry_settings.get("language") == "en"
        assert registry_settings.get("LANGUAGE") == "en"

    def test_missing_value_returns_default(self, registry_settings):
        assert registry_settings.get("test", "fallback") == "fallback"


# --------------------------------------------------------------------------
# Язык
# --------------------------------------------------------------------------
class TestLanguage:
    def test_default_is_russian(self, file_mode):
        settings, _path = file_mode
        assert settings.get_language() == "ru"

    def test_language_is_lowercased(self, file_mode):
        settings, _path = file_mode
        assert settings.set_language("EN") is True
        assert settings.get_language() == "en"

    def test_unknown_language_is_refused(self, file_mode):
        settings, _path = file_mode
        assert settings.set_language("de") is False
        assert settings.set_language("") is False
        assert settings.set_language(None) is False

    def test_garbage_in_store_falls_back_to_russian(self, file_mode):
        settings, _path = file_mode
        settings.set("Language", "klingon")
        assert settings.get_language() == "ru"


# --------------------------------------------------------------------------
# Под-опции очистки браузеров
# --------------------------------------------------------------------------
class TestBrowserOptions:
    def test_default_is_cache_only(self, file_mode):
        assert settings_mod.get_browser_options("chrome") == {"cache"}

    def test_none_means_all_unchecked(self, file_mode):
        assert settings_mod.set_browser_options("chrome", None) is True
        assert settings_mod.get_browser_options("chrome") == set()

    def test_roundtrip(self, file_mode):
        assert settings_mod.set_browser_options(
            "chrome", {"cookies", "history"}) is True
        assert settings_mod.get_browser_options("chrome") == {"cookies", "history"}

    def test_unknown_keys_are_dropped(self, file_mode):
        settings_mod.set_browser_options("chrome", {"cookies", "nonsense"})
        assert settings_mod.get_browser_options("chrome") == {"cookies"}

    def test_all_unknown_keys_fall_back_to_default(self, file_mode):
        settings_mod.set_browser_options("chrome", {"nonsense"})
        assert settings_mod.get_browser_options("chrome") == core.default_browser_suboptions("chrome")

    def test_caution_flag_covers_everything_but_cache(self):
        for sub in core.get_browser_suboptions("chrome"):
            expected = sub["key"] != "cache"
            assert core.is_browser_suboption_caution(sub) is expected
