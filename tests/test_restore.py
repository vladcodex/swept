#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Тесты работы с точками восстановления.

Модуль общается с Windows через PowerShell, поэтому проверяется прежде всего
разбор ответа и защита от подстановки: номер точки обязан быть целым числом,
а «защита системы выключена» и «нет прав» — это разные сообщения, а не одна
общая ошибка.
"""

from __future__ import annotations

import pytest

import cleaner_restore as restore


# --------------------------------------------------------------------------
# Разбор ответа PowerShell
# --------------------------------------------------------------------------
class TestParsePoints:
    def test_single_object_becomes_list(self):
        # ConvertTo-Json на одном объекте отдаёт объект, а не массив.
        points = restore.parse_points_json(
            '{"seq": 5, "desc": "Swept", "time": "2026-11-02 14:00"}')
        assert points == [{"seq": 5, "desc": "Swept", "time": "2026-11-02 14:00"}]

    def test_array_is_parsed(self):
        points = restore.parse_points_json(
            '[{"seq": 3, "desc": "a", "time": "t1"},'
            ' {"seq": 9, "desc": "b", "time": "t2"}]')
        assert [p["seq"] for p in points] == [9, 3]   # новые сверху

    def test_empty_output_gives_empty_list(self):
        assert restore.parse_points_json("") == []
        assert restore.parse_points_json("   ") == []

    def test_broken_json_is_not_fatal(self):
        assert restore.parse_points_json("не json") == []

    def test_entries_without_number_are_skipped(self):
        points = restore.parse_points_json(
            '[{"desc": "no seq"}, {"seq": 0}, {"seq": 4, "desc": "ok"}]')
        assert [p["seq"] for p in points] == [4]

    def test_missing_fields_are_filled(self):
        points = restore.parse_points_json('{"seq": 2}')
        assert points == [{"seq": 2, "desc": "", "time": ""}]


# --------------------------------------------------------------------------
# Проверка номера точки
# --------------------------------------------------------------------------
class TestSequenceValidation:
    @pytest.mark.parametrize("value,expected", [
        (1, True), ("12", True), (999999, True),
        (0, False), (-3, False), ("", False), (None, False),
        ("1; calc", False), ("1 OR 1=1", False), (10 ** 7, False),
    ])
    def test_valid_sequence(self, value, expected):
        assert restore.valid_sequence(value) is expected


# --------------------------------------------------------------------------
# Распознавание ответов Windows
# --------------------------------------------------------------------------
class TestMarkerDetection:
    @pytest.mark.parametrize("text", [
        "System Restore is disabled",
        "Восстановление системы отключено",
        "The service cannot be started (0x80070422)",
    ])
    def test_disabled_is_recognised(self, text):
        assert restore.protection_disabled(text) is True

    def test_normal_text_is_not_disabled(self):
        assert restore.protection_disabled("SequenceNumber : 5") is False

    @pytest.mark.parametrize("text", [
        "Access denied", "access is denied", "Отказано в доступе.",
        "Запрошенная операция требует повышения прав.",
    ])
    def test_access_denied_is_recognised(self, text):
        assert restore.access_denied(text) is True


# --------------------------------------------------------------------------
# Список точек
# --------------------------------------------------------------------------
class TestListRestorePoints:
    def test_successful_list(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (
            0, '[{"seq": 2, "desc": "Swept", "time": "2026-11-02 14:00"}]'))
        info = restore.list_restore_points()
        assert info["ok"] is True
        assert info["disabled"] is False
        assert len(info["points"]) == 1

    def test_empty_list_is_ok(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (0, ""))
        info = restore.list_restore_points()
        assert info["ok"] is True and info["points"] == []

    def test_disabled_protection_is_reported_separately(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (
            1, "Get-ComputerRestorePoint : System Restore is disabled"))
        info = restore.list_restore_points()
        assert info["ok"] is True
        assert info["disabled"] is True
        assert info["error"] == ""

    def test_access_denied_sets_admin_flag(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (
            1, "Get-ComputerRestorePoint : Access denied"))
        info = restore.list_restore_points()
        assert info["ok"] is False
        assert info["needs_admin"] is True
        assert info["error"]

    def test_unknown_failure_keeps_message(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (1, "что-то пошло не так"))
        info = restore.list_restore_points()
        assert info["ok"] is False
        assert info["needs_admin"] is False
        assert "не так" in info["error"]


# --------------------------------------------------------------------------
# Восстановление
# --------------------------------------------------------------------------
class TestRestoreToPoint:
    def test_bad_number_never_reaches_powershell(self, monkeypatch):
        calls = []
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: calls.append(a) or (0, ""))
        ok, message = restore.restore_to_point("12; shutdown")
        assert ok is False
        assert message
        assert calls == []

    def test_requires_administrator_rights(self, monkeypatch):
        calls = []
        monkeypatch.setattr(restore, "is_admin", lambda: False)
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: calls.append(a) or (0, ""))
        ok, message = restore.restore_to_point(12)
        assert ok is False
        assert message
        assert calls == []

    def test_success(self, monkeypatch):
        seen = []

        def fake(script, timeout=0):
            seen.append(script)
            return 0, ""

        monkeypatch.setattr(restore, "is_admin", lambda: True)
        monkeypatch.setattr(restore, "_run_ps", fake)
        ok, message = restore.restore_to_point(12)
        assert (ok, message) == (True, "")
        assert "Restore-Computer" in seen[0]
        assert "-RestorePoint 12" in seen[0]

    def test_failure_returns_reason(self, monkeypatch):
        monkeypatch.setattr(restore, "is_admin", lambda: True)
        monkeypatch.setattr(restore, "_run_ps",
                            lambda *a, **k: (1, "Restore-Computer : отказ"))
        ok, message = restore.restore_to_point(12)
        assert ok is False
        assert message


# --------------------------------------------------------------------------
# Состояние защиты системы
# --------------------------------------------------------------------------
class TestProtectionEnabled:
    def test_disabled(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (1, "not enabled"))
        info = restore.protection_enabled()
        assert info["enabled"] is False
        assert info["count"] == 0

    def test_enabled_with_points(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (
            0, '[{"seq": 1}, {"seq": 2}]'))
        info = restore.protection_enabled()
        assert info["enabled"] is True
        assert info["count"] == 2

    def test_unknown_on_failure(self, monkeypatch):
        monkeypatch.setattr(restore, "_run_ps", lambda *a, **k: (1, "Access denied"))
        info = restore.protection_enabled()
        assert info["enabled"] is None
        assert info["needs_admin"] is True


# --------------------------------------------------------------------------
# Подпись точки
# --------------------------------------------------------------------------
class TestDescribePoint:
    def test_contains_time_description_and_number(self):
        text = restore.describe_point(
            {"seq": 7, "desc": "Swept", "time": "2026-11-02 14:00"})
        assert "2026-11-02 14:00" in text
        assert "Swept" in text
        assert "7" in text

    def test_empty_fields_do_not_crash(self):
        assert restore.describe_point({})
