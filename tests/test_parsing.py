"""Разбор строк из вывода Windows: размеры, проценты, да/нет.

Эти функции работают с текстом, который приходит из DISM и реестра на
русской и английской Windows, поэтому проверяются обе локали и мусор.
"""

from __future__ import annotations

import cleaner_core as core

GIB = 1024 ** 3


class TestParseSize:
    def test_gigabytes(self):
        assert core._parse_size("13.91 GB") == int(13.91 * GIB)

    def test_comma_decimal_separator(self):
        assert core._parse_size("1,5 GB") == core._parse_size("1.5 GB")

    def test_cyrillic_units(self):
        assert core._parse_size("1,5 ГБ") == core._parse_size("1.5 GB")

    def test_bytes(self):
        assert core._parse_size("0 B") == 0
        assert core._parse_size("512 Б") == 512

    def test_negative_is_not_a_size(self):
        """Минус не входит в шаблон: без проверки он терялся и "-5 GB"
        становилось положительными 5 ГБ."""
        assert core._parse_size("-5 GB") is None
        assert core._parse_size("- 5 GB") is None
        assert core._parse_size("−5 GB") is None

    def test_range_is_rejected(self):
        assert core._parse_size("5-10 GB") is None

    def test_no_size_in_string(self):
        assert core._parse_size("") is None
        assert core._parse_size("abc") is None
        assert core._parse_size(None) is None

    def test_real_dism_line(self):
        line = "Backups and Disabled Features : 1.42 GB"
        assert core._parse_size(line) == int(1.42 * GIB)

    def test_unit_must_end_the_token(self):
        """'GB' внутри слова не должно считаться единицей."""
        assert core._parse_size("12 GByte") is None


class TestProgressFromLine:
    def test_bracket_bar(self):
        assert core._progress_from_line("[==========  25.0% ==========]") == 0.25

    def test_full_bar(self):
        assert core._progress_from_line("[==========================100.0%]") == 1.0

    def test_comma_percent(self):
        assert core._progress_from_line("[=====  25,0% =====]") == 0.25

    def test_needs_bracket(self):
        """Строка без '[' — не прогресс-бар, даже если в ней есть процент."""
        assert core._progress_from_line("100.0%") is None
        assert core._progress_from_line("done 50%") is None


class TestYesNo:
    def test_russian_and_english(self):
        assert core._yes_no("Да") is True
        assert core._yes_no("Yes") is True
        assert core._yes_no("Нет") is False
        assert core._yes_no("No") is False

    def test_unknown(self):
        assert core._yes_no("maybe") is None
        assert core._yes_no("") is None
        assert core._yes_no(None) is None


class TestFormatBytes:
    def test_zero_and_none(self):
        assert core.format_bytes(0) == core.format_bytes(None)

    def test_scales(self):
        assert core.format_bytes(1536).startswith("1.50")
        assert core.format_bytes(GIB).startswith("1.00")

    def test_negative_keeps_sign(self):
        assert core.format_bytes(-1024).startswith("-1.00")
