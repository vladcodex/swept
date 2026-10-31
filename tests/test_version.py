#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
"""
Тесты проверки обновлений.

Разбор версии — место, где ошибка стоит дорого: неверно прочитанный тег
показывает пользователю «доступно обновление», которого нет. Отдельно
проверяется контракт check(): любой сбой сети или ответа обязан превращаться
в статус ошибки, а не в исключение — интерфейс не должен падать.
"""

from __future__ import annotations

import pytest

import cleaner_update as upd


class TestParseVersion:
    @pytest.mark.parametrize("text,expected", [
        ("v1.5.0", (1, 5, 0)),
        ("1.5", (1, 5)),
        ("1.5.1", (1, 5, 1)),
        ("V1.5.1", (1, 5, 1)),
        ("Swept 1.5.0 — new stuff", (1, 5, 0)),
        ("1.5.0-beta.2", (1, 5, 0)),
        ("v1.5.0.1", (1, 5, 0)),
        ("  v1.5.1  ", (1, 5, 1)),
        ("1.10.0", (1, 10, 0)),
    ])
    def test_valid_versions(self, text, expected):
        assert upd.parse_version(text) == expected

    @pytest.mark.parametrize("text", [
        "",
        None,
        "no version here",
        "Release notes",
        "2024",
        "12",
    ])
    def test_no_version_returns_empty_tuple(self, text):
        assert upd.parse_version(text) == ()

    def test_date_in_title_is_not_a_version(self):
        # Раньше здесь получалось (2024, 1, 5), и программа предлагала
        # «обновиться до 2024 года».
        assert upd.parse_version("Release 2024-01-05 v1.5.0") == (1, 5, 0)

    def test_build_number_in_title_is_skipped(self):
        assert upd.parse_version("build 2000 released, version 1.4.2") == (1, 4, 2)


class TestIsNewer:
    @pytest.mark.parametrize("latest,current,expected", [
        ("1.5.1", "1.5.0", True),
        ("1.5.0", "1.5.0", False),
        ("1.5", "1.5.0", False),
        ("1.10.0", "1.9.0", True),   # строковое сравнение соврало бы
        ("2.0.0", "1.99.99", True),
        ("1.4.9", "1.5.0", False),
    ])
    def test_comparison(self, latest, current, expected):
        assert upd.is_newer(latest, current) is expected


class TestSafeUrl:
    @pytest.mark.parametrize("url", [
        "https://github.com/vladcodex/swept/releases/tag/v1.5.1",
        "https://www.github.com/vladcodex/swept/releases",
    ])
    def test_github_https_is_kept(self, url):
        assert upd.safe_url(url) == url

    @pytest.mark.parametrize("url", [
        None,
        "",
        "http://github.com/vladcodex/swept",
        "file:///C:/Windows/System32/cmd.exe",
        "javascript:alert(1)",
        "https://evil.example.com/payload.exe",
        "https://github.com.evil.example.com/x",
        "https://notgithub.com/x",
    ])
    def test_everything_else_falls_back_to_releases_page(self, url):
        assert upd.safe_url(url) == upd.RELEASES_URL

    def test_credentials_in_url_do_not_change_host(self):
        # user@evil.com выглядел бы как github.com при наивном разборе строки.
        assert upd.safe_url("https://github.com@evil.example.com/x") == upd.RELEASES_URL


class TestCheckContract:
    """check() не бросает исключений: любой сбой — это status == "error"."""

    @pytest.mark.parametrize("payload", [[], "text", 42, None, True])
    def test_non_object_response_is_an_error(self, monkeypatch, payload):
        monkeypatch.setattr(upd, "_fetch_latest_release", lambda: payload)
        result = upd.check()
        assert result["status"] == upd.STATUS_ERROR
        assert result["error"]
        assert result["url"] == upd.RELEASES_URL

    def test_network_failure_is_an_error(self, monkeypatch):
        def boom():
            raise RuntimeError("network error: offline")

        monkeypatch.setattr(upd, "_fetch_latest_release", boom)
        result = upd.check()
        assert result["status"] == upd.STATUS_ERROR
        assert "offline" in result["error"]

    def test_response_without_version_is_an_error(self, monkeypatch):
        monkeypatch.setattr(upd, "_fetch_latest_release",
                            lambda: {"tag_name": "nightly", "name": "Nightly"})
        result = upd.check()
        assert result["status"] == upd.STATUS_ERROR
        assert result["latest"] == ""

    def test_newer_release_reports_update(self, monkeypatch):
        monkeypatch.setattr(upd, "_fetch_latest_release", lambda: {
            "tag_name": "v99.0.0",
            "name": "99.0.0",
            "html_url": "https://github.com/vladcodex/swept/releases/tag/v99.0.0",
        })
        result = upd.check()
        assert result["status"] == upd.STATUS_UPDATE
        assert result["latest"] == "99.0.0"
        assert result["url"].startswith("https://github.com/")

    def test_same_version_reports_current(self, monkeypatch):
        monkeypatch.setattr(upd, "_fetch_latest_release", lambda: {
            "tag_name": "v" + upd.current_version_text(),
            "name": upd.current_version_text(),
            "html_url": "https://github.com/vladcodex/swept/releases",
        })
        assert upd.check()["status"] == upd.STATUS_CURRENT

    def test_hostile_html_url_is_replaced(self, monkeypatch):
        monkeypatch.setattr(upd, "_fetch_latest_release", lambda: {
            "tag_name": "v99.0.0",
            "html_url": "file:///C:/Windows/System32/cmd.exe",
        })
        assert upd.check()["url"] == upd.RELEASES_URL

    def test_result_always_has_all_keys(self, monkeypatch):
        monkeypatch.setattr(upd, "_fetch_latest_release", lambda: {})
        result = upd.check()
        assert set(result) == {"status", "latest", "current", "url", "name", "error"}
