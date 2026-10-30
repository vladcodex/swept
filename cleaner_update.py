#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_update.py — проверка новой версии Swept на GitHub Releases.

Принципы
--------
* **Сеть трогается только по нажатию.** Никакой проверки при старте, никакой
  отправки данных: один GET-запрос к публичному GitHub API, и только когда
  пользователь сам нажал плашку в шапке окна.
* **Ничего не скачивается и не ставится автоматически.** Программа узнаёт
  номер последнего релиза и открывает страницу загрузки в браузере —
  решение всегда остаётся за пользователем.
* **Ошибка сети — это статус, а не исключение.** Интерфейс не должен падать
  из-за отсутствия интернета, лимита GitHub или кривого ответа.

Модуль не зависит от графической библиотеки, поэтому его можно запустить
как отдельный скрипт для проверки:

    python cleaner_update.py
"""

from __future__ import annotations

import re
import urllib.parse

REPO = "vladcodex/swept"
API_URL = "https://api.github.com/repos/{}/releases/latest".format(REPO)
RELEASES_URL = "https://github.com/{}/releases/latest".format(REPO)
TIMEOUT = 8

# Ответ API — это один JSON на несколько килобайт. Всё, что заметно больше,
# читать в память незачем: подменённый или сломанный ответ не должен
# превращаться в мегабайты в адресном пространстве программы.
MAX_RESPONSE_BYTES = 256 * 1024

# Ссылку из ответа открывает браузер, поэтому хост проверяется явно:
# поле html_url приходит из сети и доверять ему без проверки нельзя.
ALLOWED_HOSTS = {"github.com", "www.github.com"}

# Статусы результата проверки.
STATUS_UPDATE = "update"      # вышла версия новее текущей
STATUS_CURRENT = "current"    # установлена последняя
STATUS_ERROR = "error"        # проверить не удалось

# Запасное значение: используется, если строку версии не удалось прочитать
# из интерфейсных ресурсов. Должно совпадать с build.py (VERSION).
FALLBACK_VERSION = (1, 5, 0)


def parse_version(text) -> tuple:
    """
    Превращает строку версии в кортеж чисел.

    Понимает "v1.5.0", "1.5", "Swept 1.5.0 — new stuff", "1.5.0-beta.2":
    берутся первые три числа, всё остальное (префиксы, суффиксы, названия)
    отбрасывается. Пустая строка или текст без цифр дают пустой кортеж —
    вызывающая сторона обязана это проверить.
    """
    numbers = re.findall(r"\d+", str(text or ""))
    return tuple(int(number) for number in numbers[:3])


def _padded(version) -> tuple:
    """Дополняет кортеж нулями до трёх чисел: (1, 5) -> (1, 5, 0)."""
    return (tuple(version) + (0, 0, 0))[:3]


def is_newer(latest, current) -> bool:
    """
    True, если версия `latest` новее `current`.

    Сравнение по числам, а не по строкам: "1.10.0" новее "1.9.0", хотя
    строковое сравнение сказало бы обратное.
    """
    return _padded(parse_version(latest)) > _padded(parse_version(current))


def current_version() -> tuple:
    """
    Версия текущей сборки.

    Берётся из той же строки, что видна в шапке окна (`app.version`), —
    так номер в интерфейсе и номер, с которым сравнивается релиз, не могут
    разойтись. Если ресурсы недоступны, возвращается FALLBACK_VERSION.
    """
    try:
        from cleaner_i18n import t
        parsed = parse_version(t("app.version"))
        if parsed:
            return parsed
    except Exception:
        pass
    return FALLBACK_VERSION


def current_version_text() -> str:
    """Версия текущей сборки строкой: '1.5.0'."""
    return ".".join(str(part) for part in current_version())


def safe_url(url) -> str:
    """
    Пропускает только https-ссылку на github.com, иначе отдаёт страницу релизов.

    Значение поля html_url приходит из сетевого ответа. Открывать его без
    проверки нельзя: ShellExecuteW запускает и файлы, и чужие обработчики
    протоколов, поэтому `file:///…` или `javascript:…` из подменённого ответа
    стали бы исполняемым действием, а не ссылкой.
    """
    try:
        parts = urllib.parse.urlsplit(str(url or "").strip())
        host = (parts.hostname or "").lower()
    except ValueError:
        return RELEASES_URL
    if parts.scheme.lower() != "https" or host not in ALLOWED_HOSTS:
        return RELEASES_URL
    return urllib.parse.urlunsplit(parts)


def _fetch_latest_release() -> dict:
    """
    Запрашивает последний релиз у GitHub API. Бросает исключение при сбое.

    Используется стандартный urllib, а не requests: проверка обновлений —
    единственное место, где нужен HTTP, и тянуть ради неё зависимость
    в сборку смысла нет. Прокси берётся из системных переменных — urllib
    делает это сам.
    """
    import json
    import urllib.error
    import urllib.request

    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        # GitHub требует осмысленный User-Agent и не отдаёт ответ без него.
        "User-Agent": "Swept/{}".format(current_version_text()),
    })
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            # Редирект мог увести на http — тогда соединение уже не защищено,
            # и ответ нельзя считать доверенным.
            final_url = response.geturl() or API_URL
            if not final_url.lower().startswith("https://"):
                raise RuntimeError("GitHub redirected to a non-HTTPS address")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            # Анонимный лимит GitHub — 60 запросов в час на адрес.
            raise RuntimeError(
                "GitHub API rate limit reached (HTTP 403)") from exc
        raise RuntimeError("HTTP {} from GitHub".format(exc.code)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("network error: {}".format(exc.reason)) from exc

    if len(payload) > MAX_RESPONSE_BYTES:
        raise RuntimeError("GitHub response too large")

    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("unreadable GitHub response") from exc


def check() -> dict:
    """
    Проверяет, вышла ли версия новее текущей.

    Возвращает словарь:
        status  — "update" | "current" | "error"
        latest  — версия последнего релиза строкой ("1.5.0") или ""
        current — версия этой сборки строкой
        url     — страница релиза (открывается в браузере)
        name    — название релиза, как его написал автор
        error   — текст ошибки, если status == "error"
    """
    current = current_version_text()
    result = {
        "status": STATUS_ERROR,
        "latest": "",
        "current": current,
        "url": RELEASES_URL,
        "name": "",
        "error": "",
    }

    try:
        data = _fetch_latest_release()
    except Exception as exc:
        result["error"] = str(exc) or exc.__class__.__name__
        return result

    tag = data.get("tag_name") or data.get("name") or ""
    parsed = parse_version(tag)
    if not parsed:
        result["error"] = "no version in GitHub response"
        return result

    latest = ".".join(str(part) for part in parsed)
    result["latest"] = latest
    result["name"] = (data.get("name") or "").strip()
    result["url"] = safe_url(data.get("html_url"))
    result["status"] = (STATUS_UPDATE if is_newer(latest, current)
                        else STATUS_CURRENT)
    return result


def main() -> int:
    """Проверка из командной строки (для отладки, без интерфейса)."""
    result = check()
    print("Swept — проверка обновлений")
    print("  текущая версия: {}".format(result["current"]))
    if result["status"] == STATUS_UPDATE:
        print("  доступна новая: {}".format(result["latest"]))
        if result["name"]:
            print("  релиз: {}".format(result["name"]))
        print("  страница: {}".format(result["url"]))
        return 0
    if result["status"] == STATUS_CURRENT:
        print("  установлена последняя версия.")
        return 0
    print("  проверить не удалось: {}".format(result["error"]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
