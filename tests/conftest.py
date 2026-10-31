#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Общие фикстуры для тестов Swept.

Главная идея: ни один тест не должен зависеть от реального профиля той машины,
где он запущен. Поэтому переменные окружения (USERPROFILE, SystemRoot,
ProgramFiles, ...) подменяются на временный каталог, а кеш списков защиты
сбрасывается до и после теста.

Благодаря этому тесты одинаково проходят и на рабочей машине разработчика,
и на чистом раннере GitHub Actions, и не могут случайно задеть настоящие
файлы: всё, с чем они работают, лежит в tmp_path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Тесты импортируют модули проекта напрямую из корня репозитория.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cleaner_core  # noqa: E402  (после правки sys.path)


class FakeSystem:
    """Временная «система»: набор путей, похожий на настоящий Windows."""

    def __init__(self, root: Path):
        self.root = root
        self.home = root / "home"
        self.local = self.home / "AppData" / "Local"
        self.roaming = self.home / "AppData" / "Roaming"
        self.temp = self.local / "Temp"
        self.windir = root / "Windows"
        self.system32 = self.windir / "System32"
        self.program_files = root / "Program Files"
        self.program_files_x86 = root / "Program Files (x86)"
        self.programdata = root / "ProgramData"
        self.steam = self.program_files_x86 / "Steam"

    def make_dirs(self) -> None:
        for path in (
            self.temp,
            self.roaming,
            self.system32,
            self.program_files,
            self.steam,
            self.programdata,
        ):
            path.mkdir(parents=True, exist_ok=True)


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """Подменяет переменные окружения на временную систему."""
    system = FakeSystem(tmp_path / "sys")
    system.make_dirs()

    monkeypatch.setenv("USERPROFILE", str(system.home))
    monkeypatch.setenv("LOCALAPPDATA", str(system.local))
    monkeypatch.setenv("APPDATA", str(system.roaming))
    monkeypatch.setenv("TEMP", str(system.temp))
    monkeypatch.setenv("TMP", str(system.temp))
    monkeypatch.setenv("SystemRoot", str(system.windir))
    monkeypatch.setenv("windir", str(system.windir))
    monkeypatch.setenv("ProgramFiles", str(system.program_files))
    monkeypatch.setenv("ProgramFiles(x86)", str(system.program_files_x86))
    monkeypatch.setenv("ProgramData", str(system.programdata))
    # Портативный режим выключен: иначе Settings пойдёт мимо реестра.
    monkeypatch.delenv("SWEPT_PORTABLE", raising=False)

    cleaner_core.reset_protection_cache()
    try:
        yield system
    finally:
        cleaner_core.reset_protection_cache()


@pytest.fixture
def cache_dir(fake_env):
    """Существующий каталог внутри %LOCALAPPDATA% — типичная цель очистки."""
    path = fake_env.local / "AppDataCache" / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def allowed(cache_dir):
    """Белый список ровно из одного каталога."""
    normalized = cleaner_core._norm(str(cache_dir))
    return {
        "dirs": {normalized},
        "files": set(),
        "real_dirs": {normalized: cleaner_core._real_norm(str(cache_dir))},
    }


def make_junction(link: Path, target: Path) -> bool:
    """
    Создаёт junction. Возвращает False, если среда этого не позволяет.

    Junction, в отличие от символьной ссылки, не требует ни прав
    администратора, ни включённого режима разработчика, поэтому он доступен
    и на раннере CI, и на обычной машине.
    """
    if os.name != "nt":
        return False
    try:
        os.system(
            'cmd /c mklink /J "{}" "{}" >nul 2>&1'.format(link, target))
    except OSError:
        return False
    return link.exists()
