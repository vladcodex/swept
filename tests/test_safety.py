#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Тесты чёрного списка и проверок корня очистки.

Это самый важный файл в наборе: здесь фиксируется обещание «критические
области Windows не затрагиваются никогда». Если кто-то в будущем ослабит
проверку, тест упадёт до того, как сборка попадёт к пользователю.
"""

from __future__ import annotations

import os

import pytest

import cleaner_core as core
from conftest import make_junction


# --------------------------------------------------------------------------
# _norm — нормализация пути, на которой держатся все сравнения ниже
# --------------------------------------------------------------------------
class TestNorm:
    def test_empty_input_is_not_current_directory(self):
        # os.path.abspath("") вернул бы CWD, и «пустой путь» стал бы рабочей
        # папкой программы. Это должно оставаться пустой строкой.
        assert core._norm("") == ""
        assert core._norm(None) == ""

    def test_lowercase_and_no_trailing_separator(self):
        assert core._norm("C:\\Temp\\") == "c:\\temp"

    def test_drive_root_keeps_separator(self):
        assert core._norm("C:\\") == "c:\\"

    def test_forward_slashes_become_backslashes(self):
        assert core._norm("C:/Temp/Sub") == core._norm("C:\\Temp\\Sub")

    def test_relative_path_becomes_absolute(self):
        result = core._norm("somefile.tmp")
        assert os.path.isabs(result)


# --------------------------------------------------------------------------
# is_protected — чёрный список
# --------------------------------------------------------------------------
class TestIsProtected:
    @pytest.mark.parametrize("relative", [
        "System32/ntdll.dll",
        "System32/drivers/etc/hosts",
        "SysWOW64/kernel32.dll",
        "WinSxS/amd64_component",
        "Boot/bcd",
        "Fonts/arial.ttf",
        "assembly/GAC_MSIL",
        "Microsoft.NET/Framework",
        "servicing/Packages",
    ])
    def test_windows_subdirectories_are_protected(self, fake_env, relative):
        path = fake_env.windir / relative
        assert core.is_protected(str(path)) is True

    def test_program_files_is_protected(self, fake_env):
        assert core.is_protected(str(fake_env.program_files / "SomeApp" / "a.dll"))

    def test_program_files_x86_is_protected(self, fake_env):
        assert core.is_protected(str(fake_env.program_files_x86 / "SomeApp" / "a.dll"))

    def test_start_menu_and_systemdata_are_protected(self, fake_env):
        start_menu = fake_env.programdata / "Microsoft" / "Windows" / "Start Menu"
        system_data = fake_env.programdata / "Microsoft" / "Windows" / "SystemData"
        assert core.is_protected(str(start_menu / "Programs" / "x.lnk"))
        assert core.is_protected(str(system_data / "x.db"))

    @pytest.mark.parametrize("name", [
        "pagefile.sys", "hiberfil.sys", "swapfile.sys", "bootmgr",
        "ntuser.dat", "bcd", "BOOTMGR", "PageFile.SYS",
    ])
    def test_critical_files_are_protected_regardless_of_case(self, fake_env, name):
        assert core.is_protected(str(fake_env.home / name))

    @pytest.mark.parametrize("name", ["$Recycle.Bin", "System Volume Information"])
    def test_service_folders_on_any_drive_are_protected(self, fake_env, name):
        path = fake_env.root / "D" / name / "S-1-5-21" / "$R123.tmp"
        assert core.is_protected(str(path))

    # --- исключения: то, что чистить МОЖНО, хотя оно внутри защищённой зоны

    def test_system32_logfiles_is_allowed(self, fake_env):
        assert not core.is_protected(str(fake_env.system32 / "LogFiles" / "CBS.log"))

    def test_winevt_logs_are_allowed(self, fake_env):
        assert not core.is_protected(
            str(fake_env.system32 / "winevt" / "Logs" / "System.evtx"))

    @pytest.mark.parametrize("sub", ["appcache", "cache", "logs", "tmp"])
    def test_steam_cache_folders_are_allowed(self, fake_env, sub):
        assert not core.is_protected(str(fake_env.steam / sub / "x.dat"))

    def test_steam_downloading_folder_is_allowed(self, fake_env):
        assert not core.is_protected(
            str(fake_env.steam / "steamapps" / "downloading" / "1.part"))

    def test_steam_game_saves_are_protected(self, fake_env):
        # Соседняя папка внутри той же защищённой зоны — уже нельзя.
        assert core.is_protected(
            str(fake_env.steam / "steamapps" / "common" / "Game" / "save.dat"))

    def test_temporary_folder_is_not_protected(self, fake_env):
        assert not core.is_protected(str(fake_env.temp / "a.tmp"))


# --------------------------------------------------------------------------
# is_sane_root / clean_root_reason — можно ли брать каталог за корень очистки
# --------------------------------------------------------------------------
class TestSaneRoot:
    def test_empty_and_relative_are_rejected(self, fake_env):
        assert core.is_sane_root("") is False
        assert core.is_sane_root(None) is False
        assert core.is_sane_root("Temp\\Sub") is False

    def test_drive_root_is_rejected(self, fake_env):
        assert core.is_sane_root("C:\\") is False

    def test_single_level_is_rejected(self, fake_env):
        # C:\Temp — это уже почти весь диск.
        assert core.is_sane_root("C:\\Temp") is False

    def test_two_levels_are_accepted(self, fake_env):
        assert core.is_sane_root("C:\\Temp\\Sub") is True

    @pytest.mark.parametrize("attribute", [
        "home", "local", "roaming", "windir", "programdata",
    ])
    def test_profile_and_system_roots_are_rejected(self, fake_env, attribute):
        assert core.is_sane_root(str(getattr(fake_env, attribute))) is False

    def test_appdata_itself_is_rejected(self, fake_env):
        assert core.is_sane_root(str(fake_env.home / "AppData")) is False

    def test_cache_dir_is_accepted(self, cache_dir):
        assert core.is_sane_root(str(cache_dir)) is True

    def test_reason_codes(self, fake_env, cache_dir):
        assert core.clean_root_reason("C:\\") == "unsafe"
        assert core.clean_root_reason(str(fake_env.home / "Documents" / "cache")) == "personal"
        assert core.clean_root_reason(str(cache_dir)) == ""


# --------------------------------------------------------------------------
# is_sensitive_user_path — личные папки
# --------------------------------------------------------------------------
class TestSensitiveUserPath:
    @pytest.mark.parametrize("folder", [
        "Documents", "Desktop", "Downloads", "Pictures", "Music", "Videos",
        "Favorites", "Links", "Saved Games", "Contacts", "Searches", "3D Objects",
        "Документы", "Рабочий стол", "Загрузки",
    ])
    def test_personal_folders_are_sensitive(self, fake_env, folder):
        assert core.is_sensitive_user_path(
            str(fake_env.home / folder / "file.txt")) is True

    def test_appdata_temp_is_not_sensitive(self, fake_env):
        assert not core.is_sensitive_user_path(str(fake_env.temp / "x.tmp"))

    def test_onedrive_outside_profile_is_sensitive(self, fake_env):
        assert core.is_sensitive_user_path("D:\\OneDrive\\doc.txt") is True

    def test_unrelated_path_is_not_sensitive(self, fake_env):
        assert not core.is_sensitive_user_path("D:\\Games\\cache\\x.bin")


# --------------------------------------------------------------------------
# is_reparse_point — ссылки и junction
# --------------------------------------------------------------------------
class TestReparsePoint:
    def test_regular_file_is_not_reparse(self, fake_env, tmp_path):
        target = tmp_path / "plain.txt"
        target.write_text("x", encoding="utf-8")
        assert core.is_reparse_point(str(target)) is False

    def test_missing_path_is_not_reparse(self, fake_env, tmp_path):
        assert core.is_reparse_point(str(tmp_path / "nope")) is False

    def test_junction_is_reparse(self, fake_env, tmp_path):
        target = tmp_path / "real"
        target.mkdir()
        link = tmp_path / "link"
        if not make_junction(link, target):
            pytest.skip("среда не позволяет создать junction")
        assert core.is_reparse_point(str(link)) is True
