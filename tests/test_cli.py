#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Тесты контракта командной строки.

Главное здесь — отмена. `--clean` без `--yes` обязан спросить подтверждение,
а вопрос может не прочитаться вовсе: служба, планировщик, `</dev/null`,
оборванный пайп. Раньше input() в этом случае выбрасывал EOFError, и вместо
«Отменено» пользователь получал трейсбек и код 1 вместо обещанного 4.
"""

from __future__ import annotations

import pytest

import cleaner_core as core


def _raiser(exc):
    """Подмена input(), которая сразу выбрасывает нужное исключение."""

    def _inner(*_args, **_kwargs):
        raise exc

    return _inner


@pytest.fixture
def no_cleaning(monkeypatch):
    """Сторож: очистка не должна начаться ни при каких условиях."""
    called = []

    def _guard(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("очистка началась без подтверждения")

    monkeypatch.setattr(core, "clean_categories", _guard)
    return called


class TestCancelConfirmation:
    def test_eof_cancels_with_code_4(self, monkeypatch, no_cleaning):
        monkeypatch.setattr("builtins.input", _raiser(EOFError()))
        assert core.main(["--clean", "--only", "recycle"]) == core.EXIT_CANCELLED
        assert no_cleaning == []

    def test_ctrl_c_cancels_with_code_4(self, monkeypatch, no_cleaning):
        monkeypatch.setattr("builtins.input", _raiser(KeyboardInterrupt()))
        assert core.main(["--clean", "--only", "recycle"]) == core.EXIT_CANCELLED
        assert no_cleaning == []

    def test_empty_answer_cancels(self, monkeypatch, no_cleaning):
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "")
        assert core.main(["--clean", "--only", "recycle"]) == core.EXIT_CANCELLED
        assert no_cleaning == []

    def test_explicit_no_cancels(self, monkeypatch, no_cleaning):
        monkeypatch.setattr("builtins.input", lambda *_a, **_k: "n")
        assert core.main(["--clean", "--only", "recycle"]) == core.EXIT_CANCELLED
        assert no_cleaning == []


class TestUsage:
    def test_json_with_clean_requires_yes(self, no_cleaning):
        """JSON в stdout должен остаться разбираемым — вопрос его сломает."""
        assert core.main(["--clean", "--json", "--only", "recycle"]) == core.EXIT_USAGE
        assert no_cleaning == []

    def test_unknown_category(self, no_cleaning):
        assert core.main(["--only", "no_such_category"]) == core.EXIT_USAGE

    def test_missing_report_dir(self, no_cleaning, tmp_path):
        target = tmp_path / "nope" / "report.json"
        assert core.main(["--only", "recycle", "--report", str(target)]) == core.EXIT_USAGE
        assert not target.exists()

    def test_version_and_list_exit_zero(self, capsys):
        assert core.main(["--version"]) == core.EXIT_OK
        assert "Swept" in capsys.readouterr().out
        assert core.main(["--list"]) == core.EXIT_OK
