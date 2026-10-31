#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Тесты белого списка и удаления.

Проверяется главное обещание программы: удалить можно только то, что попало
в белый список категории, а всё остальное — отказ, даже если путь передан
явно и выглядит безобидно.
"""

from __future__ import annotations

import threading

import pytest

import cleaner_core as core
from conftest import make_junction


# --------------------------------------------------------------------------
# build_allowed — построение белого списка
# --------------------------------------------------------------------------
class TestBuildAllowed:
    def test_unsafe_roots_never_enter_whitelist(self, fake_env, monkeypatch):
        monkeypatch.setattr(core, "get_jobs", lambda key, selected=None: [
            {"type": "dir", "path": "C:\\"},
            {"type": "dir", "path": "C:\\Temp"},
            {"type": "dir", "path": str(fake_env.home)},
            {"type": "dir", "path": str(fake_env.home / "Documents" / "cache")},
        ])
        result = core.build_allowed("test")
        assert result["dirs"] == set()

    def test_safe_dir_enters_whitelist(self, fake_env, cache_dir, monkeypatch):
        monkeypatch.setattr(core, "get_jobs", lambda key, selected=None: [
            {"type": "dir", "path": str(cache_dir)},
        ])
        result = core.build_allowed("test")
        assert core._norm(str(cache_dir)) in result["dirs"]
        assert core._norm(str(cache_dir)) in result["real_dirs"]

    def test_file_job_requires_absolute_path(self, fake_env, monkeypatch):
        monkeypatch.setattr(core, "get_jobs", lambda key, selected=None: [
            {"type": "file", "path": "relative.log"},
            {"type": "file", "path": ""},
        ])
        assert core.build_allowed("test")["files"] == set()

    def test_file_job_with_absolute_path_enters_whitelist(
            self, fake_env, tmp_path, monkeypatch):
        target = tmp_path / "dump.dmp"
        target.write_bytes(b"x")
        monkeypatch.setattr(core, "get_jobs", lambda key, selected=None: [
            {"type": "file", "path": str(target)},
        ])
        assert core._norm(str(target)) in core.build_allowed("test")["files"]


# --------------------------------------------------------------------------
# _in_allowed — проверка принадлежности белому списку
# --------------------------------------------------------------------------
class TestInAllowed:
    def test_file_inside_allowed_dir(self, allowed, cache_dir):
        target = cache_dir / "a.tmp"
        target.write_bytes(b"x")
        assert core._in_allowed(str(target), allowed) is True

    def test_allowed_dir_itself(self, allowed, cache_dir):
        assert core._in_allowed(str(cache_dir), allowed) is True

    def test_file_outside_allowed_dir(self, allowed, tmp_path):
        outside = tmp_path / "outside.tmp"
        outside.write_bytes(b"x")
        assert core._in_allowed(str(outside), allowed) is False

    def test_similar_prefix_is_not_inside(self, allowed, cache_dir):
        # "cache2" не должен считаться содержимым "cache".
        sibling = cache_dir.parent / (cache_dir.name + "2")
        sibling.mkdir()
        target = sibling / "a.tmp"
        target.write_bytes(b"x")
        assert core._in_allowed(str(target), allowed) is False

    def test_explicitly_allowed_file(self, fake_env, tmp_path):
        target = tmp_path / "dump.dmp"
        target.write_bytes(b"x")
        whitelist = {"dirs": set(), "files": {core._norm(str(target))}, "real_dirs": {}}
        assert core._in_allowed(str(target), whitelist) is True

    def test_explicitly_allowed_file_in_documents_is_refused(self, fake_env, tmp_path):
        # Даже если файл попал в белый список по имени, личная папка его
        # не пропускает: иначе проверка каталогов обходилась бы стороной.
        documents = fake_env.home / "Documents"
        documents.mkdir(parents=True, exist_ok=True)
        target = documents / "report.docx"
        target.write_bytes(b"x")
        whitelist = {"dirs": set(), "files": {core._norm(str(target))}, "real_dirs": {}}
        assert core._in_allowed(str(target), whitelist) is False

    def test_allowed_dir_inside_documents_is_refused(self, fake_env):
        # Последняя линия защиты: даже если каталог попал в белый список
        # ошибочно (список собрали вручную или логика изменилась), личные
        # папки всё равно не удаляются.
        documents = fake_env.home / "Documents"
        documents.mkdir(parents=True, exist_ok=True)
        target = documents / "report.docx"
        target.write_bytes(b"x")
        whitelist = {
            "dirs": {core._norm(str(documents))},
            "files": set(),
            "real_dirs": {core._norm(str(documents)): core._real_norm(str(documents))},
        }
        assert core._in_allowed(str(target), whitelist) is False

    def test_junction_escape_is_refused(self, fake_env, cache_dir, tmp_path):
        # Классическая ловушка: внутри разрешённого кэша лежит junction,
        # ведущий в личную папку. Строковая проверка его пропустила бы.
        documents = fake_env.home / "Documents"
        documents.mkdir(parents=True, exist_ok=True)
        secret = documents / "secret.txt"
        secret.write_text("личное", encoding="utf-8")

        link = cache_dir / "innocent"
        if not make_junction(link, documents):
            pytest.skip("среда не позволяет создать junction")

        whitelist = {
            "dirs": {core._norm(str(cache_dir))},
            "files": set(),
            "real_dirs": {core._norm(str(cache_dir)): core._real_norm(str(cache_dir))},
        }
        assert core._in_allowed(str(link / "secret.txt"), whitelist) is False


# --------------------------------------------------------------------------
# safe_delete_file — удаление одного файла
# --------------------------------------------------------------------------
class TestSafeDeleteFile:
    @pytest.mark.parametrize("bad", ["", None, 42, b"bytes", "C:\\a\x00b.tmp"])
    def test_garbage_input_is_blocked(self, allowed, bad):
        assert core.safe_delete_file(bad, allowed) == "blocked"

    def test_protected_path_is_blocked_even_if_whitelisted(self, fake_env, cache_dir):
        # pagefile.sys внутри разрешённого каталога — всё равно отказ:
        # чёрный список проверяется раньше белого.
        target = cache_dir / "pagefile.sys"
        target.write_bytes(b"x")
        whitelist = {
            "dirs": {core._norm(str(cache_dir))},
            "files": set(),
            "real_dirs": {core._norm(str(cache_dir)): core._real_norm(str(cache_dir))},
        }
        assert core.safe_delete_file(str(target), whitelist) == "blocked"
        assert target.exists()

    def test_outside_whitelist_is_blocked(self, allowed, tmp_path):
        target = tmp_path / "keep.txt"
        target.write_bytes(b"x")
        assert core.safe_delete_file(str(target), allowed) == "blocked"
        assert target.exists()

    def test_missing_file_is_reported(self, allowed, cache_dir):
        assert core.safe_delete_file(str(cache_dir / "ghost.tmp"), allowed) == "missing"

    def test_dry_run_keeps_file(self, allowed, cache_dir):
        target = cache_dir / "a.tmp"
        target.write_bytes(b"x")
        assert core.safe_delete_file(str(target), allowed, dry_run=True) == "simulated"
        assert target.exists()

    def test_real_delete(self, allowed, cache_dir):
        target = cache_dir / "a.tmp"
        target.write_bytes(b"x")
        assert core.safe_delete_file(str(target), allowed) == "ok"
        assert not target.exists()

    def test_read_only_file_is_deleted(self, allowed, cache_dir):
        import os
        import stat as stat_module

        target = cache_dir / "locked.tmp"
        target.write_bytes(b"x")
        os.chmod(target, stat_module.S_IREAD)
        try:
            assert core.safe_delete_file(str(target), allowed) == "ok"
            assert not target.exists()
        finally:
            if target.exists():
                os.chmod(target, stat_module.S_IWRITE)


# --------------------------------------------------------------------------
# clean_scan_result — пакетная очистка и статистика
# --------------------------------------------------------------------------
class TestCleanScanResult:
    def _result(self, files, dirs=(), **extra):
        result = {
            "key": "test",
            "files": list(files),
            "dirs": list(dirs),
            "errors": [],
            "total_size": sum(size for _path, size in files),
            "total_count": len(files),
            "recycle": None,
            "selected": None,
        }
        result.update(extra)
        return result

    def test_counts_match_reality(self, allowed, cache_dir):
        keep_outside = cache_dir.parent / "outside.tmp"
        keep_outside.write_bytes(b"x")
        blocked = cache_dir / "pagefile.sys"
        blocked.write_bytes(b"x")
        good1 = cache_dir / "a.tmp"
        good1.write_bytes(b"12345")
        good2 = cache_dir / "b.tmp"
        good2.write_bytes(b"123")

        files = [
            (str(good1), 5),
            (str(blocked), 1),
            (str(keep_outside), 1),
            (str(cache_dir / "ghost.tmp"), 0),
            (str(good2), 3),
        ]
        stats = core.clean_scan_result(self._result(files), allowed=allowed)

        assert stats["removed"] == 2
        assert stats["skipped"] == 3          # blocked + outside + missing
        assert stats["errors"] == 0
        assert stats["freed"] == 8
        assert not good1.exists() and not good2.exists()
        assert blocked.exists() and keep_outside.exists()

    def test_dry_run_removes_nothing(self, allowed, cache_dir):
        target = cache_dir / "a.tmp"
        target.write_bytes(b"12345")
        stats = core.clean_scan_result(
            self._result([(str(target), 5)]), dry_run=True, allowed=allowed)
        assert stats["removed"] == 1
        assert stats["freed"] == 5
        assert target.exists()

    def test_stop_event_interrupts_early(self, allowed, cache_dir):
        created = []
        files = []
        for index in range(10):
            path = cache_dir / "f{}.tmp".format(index)
            path.write_bytes(b"x")
            created.append(path)
            files.append((str(path), 1))

        stop = threading.Event()
        stop.set()
        stats = core.clean_scan_result(
            self._result(files), allowed=allowed, stop_event=stop)
        assert stats["removed"] == 0
        assert all(path.exists() for path in created)

    def test_emptied_directories_are_removed(self, allowed, cache_dir):
        nested = cache_dir / "nested"
        nested.mkdir()
        stats = core.clean_scan_result(
            self._result([], dirs=[str(nested)]), allowed=allowed)
        assert stats["removed"] == 0
        assert not nested.exists()

    def test_progress_is_throttled_but_finishes_on_last_file(self, allowed, cache_dir):
        calls = []
        files = []
        for index in range(50):
            path = cache_dir / "p{}.tmp".format(index)
            path.write_bytes(b"x")
            files.append((str(path), 1))

        core.clean_scan_result(
            self._result(files),
            allowed=allowed,
            on_progress=lambda done, total: calls.append((done, total)),
        )
        # Сигнал не должен уходить на каждый файл, но последний обязан дойти.
        assert len(calls) < len(files)
        assert calls[-1] == (50, 50)
