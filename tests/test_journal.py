#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Тесты журнала снимков и отката оптимизаций.

Что здесь важно проверить:
    * снимок делается ДО записи и хранит именно прежнее значение;
    * повторное применение не затирает исходный снимок (иначе откат вернёт
      пользователя в середину процесса, а не в состояние «до программы»);
    * откат удаляет значение, которого до Swept не было, и возвращает то,
      которое было;
    * битые данные в журнале не роняют приложение.
"""

from __future__ import annotations

import json
import uuid

import pytest

import cleaner_optimize as opt
import cleaner_settings as settings_mod

winreg = settings_mod.winreg

HKCU = None
if winreg is not None:
    HKCU = winreg.HKEY_CURRENT_USER


# --------------------------------------------------------------------------
# Хранилище: файл вместо реестра (как в тестах настроек)
# --------------------------------------------------------------------------
@pytest.fixture
def file_mode(tmp_path, monkeypatch):
    """Журнал пишется в JSON-файл во временном каталоге."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "_json_path", lambda: str(path))
    monkeypatch.setattr(settings_mod, "is_portable", lambda: True)
    instance = settings_mod.Settings()
    monkeypatch.setattr(settings_mod, "_settings", instance)
    # Модуль держит собственный указатель на сбор — сбрасываем между тестами.
    monkeypatch.setattr(opt, "_journal", None)
    monkeypatch.setattr(opt, "_journal_key", None)
    return instance, path


@pytest.fixture
def reg_branch():
    """Временная ветка реестра с одним значением ValueA=5."""
    if winreg is None:
        pytest.skip("реестр недоступен")
    parent = r"Software\SweptTests"
    branch = r"{}\{}".format(parent, uuid.uuid4().hex)
    with winreg.CreateKeyEx(HKCU, branch, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ValueA", 0, winreg.REG_DWORD, 5)
    try:
        yield branch
    finally:
        try:
            winreg.DeleteKey(HKCU, branch)
        except OSError:
            pass
        try:
            winreg.DeleteKey(HKCU, parent)
        except OSError:
            pass


def _read(branch: str, name: str):
    """Значение из ветки или маркер отсутствия."""
    try:
        with winreg.OpenKey(HKCU, branch, 0, winreg.KEY_READ) as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return "<absent>"


# --------------------------------------------------------------------------
# Кодирование значений
# --------------------------------------------------------------------------
class TestValueEncoding:
    def test_bytes_roundtrip(self):
        data = opt._encode_value(b"\x00\x01\xff")
        assert isinstance(data, dict) and "__bytes__" in data
        assert opt._decode_value(data) == b"\x00\x01\xff"

    def test_multistring_roundtrip(self):
        assert opt._decode_value(opt._encode_value(["a", "b"])) == ["a", "b"]

    def test_int_passthrough(self):
        assert opt._encode_value(5) == 5
        assert opt._decode_value(5) == 5


# --------------------------------------------------------------------------
# Хранение журнала
# --------------------------------------------------------------------------
class TestJournalStorage:
    def test_empty_journal(self, file_mode):
        assert opt.journal_snapshot() == {}
        assert opt.journal_has("telemetry") is False
        assert opt.journal_count("telemetry") == 0

    def test_entries_are_saved_with_timestamp(self, file_mode):
        opt._journal_begin("telemetry")
        opt._journal_add({"kind": "reg", "hive": "HKCU", "path": "X", "name": "Y",
                          "exists": False, "value": None, "type": None})
        opt._journal_end()

        snapshot = opt.journal_snapshot()
        assert snapshot["telemetry"]["count"] == 1
        assert snapshot["telemetry"]["at"]  # дата заполнена

    def test_nothing_is_saved_when_no_writes_happened(self, file_mode):
        opt._journal_begin("telemetry")
        opt._journal_end()
        assert opt.journal_snapshot() == {}

    def test_second_run_keeps_original_snapshot(self, file_mode):
        opt._journal_begin("power")
        opt._journal_add({"kind": "power", "prev": "first"})
        opt._journal_end()

        # Повторный прогон: сбор не должен даже начаться.
        opt._journal_begin("power")
        assert opt._journal is None
        opt._journal_add({"kind": "power", "prev": "second"})
        opt._journal_end()

        assert opt.journal_count("power") == 1

    def test_broken_json_is_not_fatal(self, file_mode):
        settings, _path = file_mode
        settings.set(opt.JOURNAL_SETTING, "{ это не json")
        assert opt.journal_snapshot() == {}

    def test_clear_one_key(self, file_mode):
        opt._journal_begin("a")
        opt._journal_add({"kind": "power", "prev": "x"})
        opt._journal_end()
        opt._journal_begin("b")
        opt._journal_add({"kind": "power", "prev": "y"})
        opt._journal_end()

        assert opt.journal_clear("a") is True
        assert set(opt.journal_snapshot()) == {"b"}
        assert opt.journal_clear() is True
        assert opt.journal_snapshot() == {}

    def test_meta_does_not_leak_into_snapshot(self, file_mode):
        settings, _path = file_mode
        settings.set(opt.JOURNAL_SETTING, json.dumps(
            {"__meta__": {"telemetry": "2026-01-01T00:00:00"}, "telemetry": []}))
        assert opt.journal_snapshot() == {}


# --------------------------------------------------------------------------
# Откат значений реестра
# --------------------------------------------------------------------------
class TestUndoRegistry:
    def test_previous_value_is_restored(self, file_mode, reg_branch):
        opt._journal_begin("fake")
        ok, _msg = opt._reg_write(HKCU, reg_branch, "ValueA", 0)
        assert ok is True
        opt._journal_end()
        assert _read(reg_branch, "ValueA") == 0

        restored, failed, error = opt.undo_optimization("fake")
        assert (restored, failed, error) == (1, 0, "")
        assert _read(reg_branch, "ValueA") == 5

    def test_value_absent_before_is_deleted(self, file_mode, reg_branch):
        opt._journal_begin("fake")
        ok, _msg = opt._reg_write(HKCU, reg_branch, "ValueB", 1)
        assert ok is True
        opt._journal_end()
        assert _read(reg_branch, "ValueB") == 1

        restored, _failed, _error = opt.undo_optimization("fake")
        assert restored == 1
        assert _read(reg_branch, "ValueB") == "<absent>"

    def test_snapshot_is_dropped_after_successful_undo(self, file_mode, reg_branch):
        opt._journal_begin("fake")
        opt._reg_write(HKCU, reg_branch, "ValueA", 0)
        opt._journal_end()
        opt.undo_optimization("fake")
        assert opt.journal_has("fake") is False

    def test_unknown_key_reports_nothing_to_undo(self, file_mode):
        restored, failed, message = opt.undo_optimization("no-such-key")
        assert (restored, failed) == (0, 0)
        assert message

    def test_undo_all_walks_every_snapshot(self, file_mode, reg_branch):
        opt._journal_begin("first")
        opt._reg_write(HKCU, reg_branch, "ValueA", 0)
        opt._journal_end()
        opt._journal_begin("second")
        opt._reg_write(HKCU, reg_branch, "ValueB", 1)
        opt._journal_end()

        result = opt.undo_all()
        assert result["restored"] == 2
        assert result["failed"] == 0
        assert set(result["keys"]) == {"first", "second"}
        assert _read(reg_branch, "ValueA") == 5
        assert _read(reg_branch, "ValueB") == "<absent>"

    def test_unknown_snapshot_value_is_not_guessed(self, file_mode, reg_branch):
        # exists=None — прочитать прежнее значение не удалось. Откат обязан
        # честно сказать «не смог», а не записать «наверное, ноль».
        opt._journal_begin("fake")
        opt._journal_add({"kind": "reg", "hive": "HKCU", "path": reg_branch,
                          "name": "ValueA", "exists": None,
                          "value": None, "type": None})
        opt._journal_end()

        restored, failed, error = opt.undo_optimization("fake")
        assert (restored, failed) == (0, 1)
        assert error
        assert _read(reg_branch, "ValueA") == 5
        # Запись осталась в журнале: её всё ещё можно вернуть вручную.
        assert opt.journal_has("fake") is True

    def test_bad_hive_name_is_rejected(self, file_mode, reg_branch):
        opt._journal_begin("fake")
        opt._journal_add({"kind": "reg", "hive": "NOPE", "path": reg_branch,
                          "name": "ValueA", "exists": True, "value": 0,
                          "type": 4})
        opt._journal_end()
        restored, failed, _error = opt.undo_optimization("fake")
        assert (restored, failed) == (0, 1)


# --------------------------------------------------------------------------
# Откат через штатные утилиты
# --------------------------------------------------------------------------
class TestUndoUtilities:
    def test_bad_power_guid_is_refused(self, file_mode):
        # GUID приходит из журнала, но всё равно проверяется шаблоном:
        # строка из JSON не должна попадать в командную строку.
        opt._journal_begin("fake")
        opt._journal_add({"kind": "power", "prev": "not-a-guid; calc"})
        opt._journal_end()
        restored, failed, _error = opt.undo_optimization("fake")
        assert (restored, failed) == (0, 1)

    def test_hibernate_that_was_off_needs_no_action(self, file_mode, monkeypatch):
        calls = []
        monkeypatch.setattr(opt, "_run", lambda *a, **k: calls.append(a) or (0, ""))
        opt._journal_begin("fake")
        opt._journal_add({"kind": "hibernate", "prev": False})
        opt._journal_end()
        restored, failed, _error = opt.undo_optimization("fake")
        assert (restored, failed) == (1, 0)
        assert calls == []

    def test_hibernate_that_was_on_is_reenabled(self, file_mode, monkeypatch):
        calls = []
        monkeypatch.setattr(opt, "_run", lambda cmd, **k: calls.append(cmd) or (0, ""))
        opt._journal_begin("fake")
        opt._journal_add({"kind": "hibernate", "prev": True})
        opt._journal_end()
        restored, _failed, _error = opt.undo_optimization("fake")
        assert restored == 1
        assert calls and "/h" in calls[0] and "on" in calls[0]

    def test_unknown_entry_kind_fails_cleanly(self, file_mode):
        opt._journal_begin("fake")
        opt._journal_add({"kind": "teleport"})
        opt._journal_end()
        restored, failed, error = opt.undo_optimization("fake")
        assert (restored, failed) == (0, 1)
        assert error
