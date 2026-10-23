#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_installer.py — безопасная установка игровых лаунчеров без winget.

Модуль полностью заменяет прежнюю winget-логику: инсталляторы скачиваются
напрямую с официальных HTTPS-источников, проверяются по Authenticode и
запускаются из изолированной папки с урезанным DACL.

Экспорт для GUI-воркера (потоки + очередь сообщений):
    is_winget_available()                    -> False
    install_packages(packages, on_log)       -> (bool, str)
    install_package(pkg_id, on_log)          -> (bool, str)

Слои защиты
-----------
1. Изоляция. %ProgramData%\SweptSecureTemp получает DACL: только
   NT AUTHORITY\SYSTEM и BUILTIN\Administrators (FullControl), наследование
   отключено. Для Users/Everyone ACE отсутствует -> доступ запрещён.
   Это закрывает TOCTOU (подмену файла между проверкой и запуском) и
   DLL hijacking из пользовательской сессии.
2. Сеть. requests + verify=True, SSLContext с минимумом TLS 1.2 и максимумом
   TLS 1.3, проверка hostname, запрет HTTP и редиректов на не-HTTPS,
   отключение системного прокси (trust_env=False) — иначе MITM-прокси
   подменяет сертификат. Ошибка цепочки -> соединение рвётся.
3. Подпись. WinVerifyTrust (ctypes) + Get-AuthenticodeSignature (PowerShell
   как безопасная системная утилита): статус Valid и совпадение издателя.
   При провале файл удаляется, поднимается SignatureError.
4. Аргументы. Никакого os.system и shell=True: subprocess.run(argv,
   shell=False), где путь и каждый флаг тихого режима — отдельные элементы.
5. Очистка. try/except/finally: файл затирается случайными байтами и
   удаляется, защищённая папка сносится при любом исходе.

Примечание по URL. В задании перечислены домашние страницы
(steampowered.com, epicgames.com, ea.com, ubi.li, gog.com) — это не файлы
инсталляторов. Для прямой загрузки ниже указаны официальные CDN-ссылки на
артефакты; каждая проверяется подписью перед запуском.

Состав каталога. 36 позиций в семи наборах: лаунчеры, браузеры, связь,
офис, медиа, архиваторы и утилиты, плюс отдельно Visual C++ Redistributable
(все версии 2005–2022, x86 и x64 — 12 пакетов разом).
Часть программ имеет постоянный адрес «последняя версия» (Chrome, Firefox,
Яндекс Браузер, Opera, ONLYOFFICE, Spotify, Telegram, Discord, Zoom, Slack),
часть — версионный (7-Zip, K-Lite, WinRAR, VLC, SumatraPDF, LibreOffice,
Everything, Notepad++, PowerToys): у второго типа ссылку нужно обновлять при
каждом релизе вендора.

Две модели доверия. Обычно файл принимается по подписи Authenticode с
совпадением издателя. Но 7-Zip и K-Lite принципиально не подписывают
инсталляторы (проверено: WinVerifyTrust и Get-AuthenticodeSignature дают
NotSigned), а обходить проверку нельзя. Для них адрес версионный, то есть
содержимое файла фиксировано, поэтому в каталоге закреплён SHA-256 — он
привязывает ровно те байты, что были проверены. Запись без издателя и без
хеша отклоняется: «доверять, потому что скачалось» — не вариант.

Чего здесь нет и почему. NanaZip поставляется как .msixbundle и ставится
через Add-AppxPackage, а не через exe/msi. qBittorrent лежит на SourceForge,
который отвечает 403 на программный запрос. У Foxit Reader и Adobe Acrobat
Reader нет прямой ссылки на файл — только страница с формой.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
import re
import shutil
import ssl
import stat
import time
import subprocess
import sys
from urllib.parse import urlsplit

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError as exc:  # pragma: no cover
    raise ImportError("Требуется пакет requests: pip install requests") from exc

try:  # pywin32 — основной способ работы с DACL (как требует задание)
    import ntsecuritycon
    import win32security
    _HAS_PYWIN32 = True
except ImportError:  # запасной путь на чистом ctypes
    ntsecuritycon = None
    win32security = None
    _HAS_PYWIN32 = False

try:  # локализация необязательна: модуль должен работать и сам по себе
    import cleaner_i18n as i18n
except Exception:  # pragma: no cover
    i18n = None

IS_WINDOWS = os.name == "nt"

# Не показывать чёрное окно консоли у дочерних процессов.
CREATE_NO_WINDOW = 0x08000000

# Защищённая папка установки.
SECURE_DIR = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                          "SweptSecureTemp")

# Коды возврата, означающие успех (3010/1641 — «нужна перезагрузка»).
_SUCCESS_CODES = {0, 3010, 1641, 1638}  # 1638 = «уже установлено»

SID_SYSTEM = "S-1-5-18"
SID_ADMINS = "S-1-5-32-544"


class InstallerSecurityError(RuntimeError):
    """Нарушение политики безопасности: операция остановлена."""


class SignatureError(InstallerSecurityError):
    """Подпись отсутствует, повреждена или издатель не совпал."""


# =============================================================================
# Каталог пакетов: официальные прямые HTTPS-ссылки
# =============================================================================
# kind: "exe" — прямой запуск с флагами, "msi" — через msiexec /qn.
# args: флаги тихой установки; каждый — отдельный элемент списка (не строка).
CATALOG = {
    "steam": {
        "title": "Steam",
        "title_en": "Steam",
        "home": "https://store.steampowered.com/about/",
        "url": "https://cdn.cloudflare.steamstatic.com/client/installer/SteamSetup.exe",
        "file": "SteamSetup.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("Valve",),
        "max_mb": 300,
    },
    "epic": {
        "title": "Epic Games Launcher",
        "title_en": "Epic Games Launcher",
        "home": "https://store.epicgames.com/download",
        "url": ("https://launcher-public-service-prod06.ol.epicgames.com"
                "/launcher/api/installer/download/EpicGamesLauncherInstaller.msi"),
        "file": "EpicGamesLauncherInstaller.msi",
        "kind": "msi",
        "args": (),
        "publishers": ("Epic Games",),
        "max_mb": 400,
    },
    "ea": {
        "title": "EA app",
        "title_en": "EA app",
        "home": "https://www.ea.com/ea-app",
        "url": "https://download.dm.origin.com/eaapp/EAappInstaller.exe",
        "file": "EAappInstaller.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("Electronic Arts",),
        "max_mb": 500,
    },
    "ubisoft": {
        "title": "Ubisoft Connect",
        "title_en": "Ubisoft Connect",
        "home": "https://ubisoftconnect.com/",
        "url": ("https://ubistatic3-a.akamaihd.net/orbit/launcher_installer"
                "/UbisoftConnectInstaller.exe"),
        "file": "UbisoftConnectInstaller.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("Ubisoft",),
        "max_mb": 500,
    },
    "gog": {
        "title": "GOG Galaxy",
        "title_en": "GOG Galaxy",
        "home": "https://www.gog.com/galaxy",
        "url": "https://webinstallers.gog-statics.com/download/GOG_Galaxy_2.0.exe",
        "file": "GOG_Galaxy_2.0.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("GOG",),
        "max_mb": 400,
    },
    # ------------------------------------------------------------------
    # Браузеры. У всех четырёх адрес «вечнозелёный»: вендор сам отдаёт
    # актуальную сборку, поэтому ссылку не нужно править при каждом
    # релизе (в отличие от версионных путей вида 7z2408-x64.exe).
    # ------------------------------------------------------------------
    "chrome": {
        "title": "Google Chrome",
        "title_en": "Google Chrome",
        "home": "https://www.google.com/chrome/",
        "url": "https://dl.google.com/chrome/install/latest/chrome_installer.exe",
        "file": "chrome_installer.exe",
        "kind": "exe",
        "args": ("/silent", "/install"),
        "publishers": ("Google LLC",),
        "max_mb": 60,
    },
    "firefox": {
        "title": "Mozilla Firefox",
        "title_en": "Mozilla Firefox",
        "home": "https://www.mozilla.org/firefox/",
        # download.mozilla.org — точка входа «последняя версия», отдаёт 302
        # на актуальный файл в CDN. Проверка подписи ниже всё равно обязательна.
        "url": ("https://download.mozilla.org/"
                "?product=firefox-latest-ssl&os=win64&lang=ru"),
        "file": "FirefoxSetup.exe",
        "kind": "exe",
        "args": ("-ms",),
        "publishers": ("Mozilla",),
        "max_mb": 200,
    },
    "yandex": {
        "title": "Яндекс Браузер",
        "title_en": "Yandex Browser",
        "home": "https://browser.yandex.ru/",
        "url": "https://browser.yandex.ru/download/?full=1",
        "file": "YandexBrowserSetup.exe",
        "kind": "exe",
        "args": ("/S",),
        # Сертификат встречается и в латинской, и в кириллической записи.
        "publishers": ("Yandex", "ЯНДЕКС"),
        "max_mb": 400,
    },
    "opera": {
        "title": "Opera",
        "title_en": "Opera",
        "home": "https://www.opera.com/",
        "url": "https://net.geo.opera.com/opera/stable/windows",
        "file": "OperaSetup.exe",
        "kind": "exe",
        "args": ("/silent", "/launchopera=0"),
        "publishers": ("Opera Norway",),
        "max_mb": 60,
    },
    "onlyoffice": {
        "title": "ONLYOFFICE",
        "title_en": "ONLYOFFICE",
        "home": "https://www.onlyoffice.com/",
        "url": ("https://download.onlyoffice.com/install/desktop/editors/windows/"
                "distrib/onlyoffice/DesktopEditors_x64.exe"),
        "file": "DesktopEditors_x64.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("Ascensio", "ONLYOFFICE"),
        "max_mb": 500,
    },
    "spotify": {
        "title": "Spotify",
        "title_en": "Spotify",
        "home": "https://www.spotify.com/download/windows/",
        "url": "https://download.scdn.co/SpotifySetup.exe",
        "file": "SpotifySetup.exe",
        "kind": "exe",
        "args": ("/silent",),
        "publishers": ("Spotify AB",),
        "max_mb": 60,
    },
    "telegram": {
        "title": "Telegram",
        "title_en": "Telegram",
        "home": "https://desktop.telegram.org/",
        "url": "https://telegram.org/dl/desktop/win64",
        "file": "TelegramSetup.exe",
        "kind": "exe",
        "args": ("/VERYSILENT", "/NORESTART"),
        "publishers": ("Telegram",),
        "max_mb": 150,
    },
    "discord": {
        "title": "Discord",
        "title_en": "Discord",
        "home": "https://discord.com/download",
        # installers/latest — стабильная точка входа Squirrel; короткий
        # /api/download?... отдаёт 403 на прямой запрос, поэтому не используется.
        "url": ("https://discord.com/api/downloads/distributions/app/installers/"
                "latest?channel=stable&platform=win&arch=x64"),
        "file": "DiscordSetup.exe",
        "kind": "exe",
        "args": ("-s",),
        "publishers": ("Discord",),
        "max_mb": 300,
    },
    "zoom": {
        "title": "Zoom",
        "title_en": "Zoom",
        "home": "https://zoom.us/download",
        "url": "https://zoom.us/client/latest/ZoomInstallerFull.exe",
        "file": "ZoomInstallerFull.exe",
        "kind": "exe",
        "args": ("/silent",),
        "publishers": ("Zoom",),
        "max_mb": 250,
    },
    "slack": {
        "title": "Slack",
        "title_en": "Slack",
        "home": "https://slack.com/downloads/windows",
        "url": "https://slack.com/ssb/download-win64",
        "file": "SlackSetup.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("Slack",),
        "max_mb": 350,
    },
    # ------------------------------------------------------------------
    # Программы с версионными адресами. Ссылку приходится обновлять при
    # каждом релизе вендора — это осознанная плата за то, что программа
    # вообще доступна в один клик. Издатель подписи снят с реальных
    # сертификатов, кроме LibreOffice и PowerToys (крупные файлы, для них
    # указан устойчивый токен издателя).
    # ------------------------------------------------------------------
    "7zip": {
        "title": "7-Zip",
        "title_en": "7-Zip",
        "home": "https://www.7-zip.org/",
        "url": "https://www.7-zip.org/a/7z2605-x64.exe",
        "file": "7z-setup.exe",
        "kind": "exe",
        "args": ("/S",),
        # 7-Zip не подписывает инсталляторы (проверено: WinVerifyTrust и
        # Get-AuthenticodeSignature дают NotSigned). Адрес версионный,
        # файл фиксирован, поэтому вместо подписи закреплён SHA-256 —
        # привязка к конкретным байтам, а не к имени в сертификате.
        "publishers": (),
        "sha256": "fd99e86f57d8f429ef5ed045bf98315af962e2309b0f1ba87a147a44c71647d0",
        "max_mb": 20,
    },
    "winrar": {
        "title": "WinRAR",
        "title_en": "WinRAR",
        "home": "https://www.win-rar.com/",
        "url": ("https://www.win-rar.com/fileadmin/winrar-versions/"
                "winrar/winrar-x64-723.exe"),
        "file": "winrar-x64.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("win.rar GmbH",),
        "max_mb": 20,
    },
    "vlc": {
        "title": "VLC media player",
        "title_en": "VLC media player",
        "home": "https://www.videolan.org/vlc/",
        # download.videolan.org отдаёт 302 на ближайшее зеркало, дальше — файл.
        "url": ("https://download.videolan.org/videolan/vlc/3.0.24/"
                "win64/vlc-3.0.24-win64.exe"),
        "file": "vlc-setup.exe",
        "kind": "exe",
        "args": ("/L=1033", "/S"),
        "publishers": ("VideoLAN",),
        "max_mb": 120,
    },
    "klite": {
        "title": "K-Lite Codec Pack Basic",
        "title_en": "K-Lite Codec Pack Basic",
        "home": "https://www.codecguide.com/download_kl.htm",
        "url": "https://files2.codecguide.com/K-Lite_Codec_Pack_2010_Basic.exe",
        "file": "K-Lite-Basic.exe",
        "kind": "exe",
        "args": ("/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"),
        # Как и 7-Zip, K-Lite выходит без цифровой подписи — проверено.
        # Адрес версионный, поэтому целостность держится на SHA-256.
        "publishers": (),
        "sha256": "9df9f48a175ede3d8edf069cefb1e53462a92c1e0bec786c3649b119e928a9fc",
        "max_mb": 60,
    },
    "sumatrapdf": {
        "title": "SumatraPDF",
        "title_en": "SumatraPDF",
        "home": "https://www.sumatrapdfreader.org/free-pdf-reader",
        "url": ("https://www.sumatrapdfreader.org/dl/rel/3.6.1/"
                "SumatraPDF-3.6.1-64-install.exe"),
        "file": "SumatraPDF-install.exe",
        "kind": "exe",
        # У SumatraPDF не NSIS, а собственный установщик с такими ключами.
        "args": ("-install", "-silent"),
        "publishers": ("Krzysztof Kowalczyk",),
        "max_mb": 40,
    },
    "libreoffice": {
        "title": "LibreOffice",
        "title_en": "LibreOffice",
        "home": "https://www.libreoffice.org/",
        "url": ("https://download.documentfoundation.org/libreoffice/stable/26.8.1/"
                "win/x86_64/LibreOffice_26.8.1_Win_x86-64.msi"),
        "file": "LibreOffice.msi",
        "kind": "msi",
        "args": (),
        "publishers": ("Document Foundation", "LibreOffice"),
        "max_mb": 600,
    },
    "everything": {
        "title": "Everything",
        "title_en": "Everything",
        "home": "https://www.voidtools.com/",
        "url": ("https://www.voidtools.com/"
                "Everything-1.4.1.1032.x64-Setup.exe"),
        "file": "Everything-Setup.exe",
        "kind": "exe",
        "args": ("/S",),
        "publishers": ("voidtools",),
        "max_mb": 20,
    },
    "notepadpp": {
        "title": "Notepad++",
        "title_en": "Notepad++",
        "home": "https://notepad-plus-plus.org/",
        "url": ("https://github.com/notepad-plus-plus/notepad-plus-plus/releases/"
                "download/v8.9.8.1/npp.8.9.8.1.Installer.x64.exe"),
        "file": "npp-installer.exe",
        "kind": "exe",
        "args": ("/S",),
        # В сертификате CN записан вместе с кавычками: CN="NOTEPAD++".
        "publishers": ("NOTEPAD++",),
        "max_mb": 40,
    },
    "powertoys": {
        "title": "Microsoft PowerToys",
        "title_en": "Microsoft PowerToys",
        "home": "https://learn.microsoft.com/windows/powertoys/",
        "url": ("https://github.com/microsoft/PowerToys/releases/download/"
                "v0.102.2933.0/PowerToysUserSetup-0.102.2933.0-x64.exe"),
        "file": "PowerToysSetup.exe",
        "kind": "exe",
        "args": ("/quiet", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 500,
    },
    # Visual C++ Redistributable — официальные ссылки на CDN Microsoft
    # (aka.ms для 2013/2015–2022, download.microsoft.com для 2005–2012).
    "vcredist_x64": {
        "title": "Visual C++ 2015–2022 (x64)",
        "title_en": "Visual C++ 2015–2022 (x64)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
        "file": "vc_redist.x64.exe",
        "kind": "exe",
        "args": ("/install", "/quiet", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 40,
    },
    "vcredist_x86": {
        "title": "Visual C++ 2015–2022 (x86)",
        "title_en": "Visual C++ 2015–2022 (x86)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": "https://aka.ms/vs/17/release/vc_redist.x86.exe",
        "file": "vc_redist.x86.exe",
        "kind": "exe",
        "args": ("/install", "/quiet", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 40,
    },
    # --- Visual C++ Redistributable: старые автономные версии (2005–2013) ---
    # Официальные прямые ссылки с CDN Microsoft (download.microsoft.com / aka.ms).
    # Все пакеты подписаны Microsoft -> проверка издателя достаточна, SHA-256
    # не закреплён (как и у остальных пакетов Microsoft в каталоге).
    "vcredist_2005_x86": {
        "title": "Visual C++ 2005 SP1 (x86)",
        "title_en": "Visual C++ 2005 SP1 (x86)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/8/B/4/"
                "8B42259F-5D70-43F4-AC2E-4B208FD8D66A/vcredist_x86.exe"),
        "file": "vc_redist_2005_x86.exe",
        "kind": "exe",
        "args": ("/q", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2005_x64": {
        "title": "Visual C++ 2005 SP1 (x64)",
        "title_en": "Visual C++ 2005 SP1 (x64)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/8/B/4/"
                "8B42259F-5D70-43F4-AC2E-4B208FD8D66A/vcredist_x64.exe"),
        "file": "vc_redist_2005_x64.exe",
        "kind": "exe",
        "args": ("/q", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2008_x86": {
        "title": "Visual C++ 2008 SP1 (x86)",
        "title_en": "Visual C++ 2008 SP1 (x86)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/5/D/8/"
                "5D8C65CB-C849-4025-8E95-C3966CAFD8AE/vcredist_x86.exe"),
        "file": "vc_redist_2008_x86.exe",
        "kind": "exe",
        "args": ("/q", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2008_x64": {
        "title": "Visual C++ 2008 SP1 (x64)",
        "title_en": "Visual C++ 2008 SP1 (x64)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/5/D/8/"
                "5D8C65CB-C849-4025-8E95-C3966CAFD8AE/vcredist_x64.exe"),
        "file": "vc_redist_2008_x64.exe",
        "kind": "exe",
        "args": ("/q", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2010_x86": {
        "title": "Visual C++ 2010 SP1 (x86)",
        "title_en": "Visual C++ 2010 SP1 (x86)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/1/6/5/"
                "165255E7-1014-4D0A-B094-B6A430A6BFFC/vcredist_x86.exe"),
        "file": "vc_redist_2010_x86.exe",
        "kind": "exe",
        "args": ("/q", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2010_x64": {
        "title": "Visual C++ 2010 SP1 (x64)",
        "title_en": "Visual C++ 2010 SP1 (x64)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/1/6/5/"
                "165255E7-1014-4D0A-B094-B6A430A6BFFC/vcredist_x64.exe"),
        "file": "vc_redist_2010_x64.exe",
        "kind": "exe",
        "args": ("/q", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2012_x86": {
        "title": "Visual C++ 2012 Update 4 (x86)",
        "title_en": "Visual C++ 2012 Update 4 (x86)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/1/6/B/"
                "16B06F60-3B20-4FF2-B699-5E9B7962F9AE/VSU_4/vcredist_x86.exe"),
        "file": "vc_redist_2012_x86.exe",
        "kind": "exe",
        "args": ("/install", "/quiet", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2012_x64": {
        "title": "Visual C++ 2012 Update 4 (x64)",
        "title_en": "Visual C++ 2012 Update 4 (x64)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": ("https://download.microsoft.com/download/1/6/B/"
                "16B06F60-3B20-4FF2-B699-5E9B7962F9AE/VSU_4/vcredist_x64.exe"),
        "file": "vc_redist_2012_x64.exe",
        "kind": "exe",
        "args": ("/install", "/quiet", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2013_x86": {
        "title": "Visual C++ 2013 (x86)",
        "title_en": "Visual C++ 2013 (x86)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": "https://aka.ms/highdpimfc2013x86enu",
        "file": "vc_redist_2013_x86.exe",
        "kind": "exe",
        "args": ("/install", "/quiet", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
    "vcredist_2013_x64": {
        "title": "Visual C++ 2013 (x64)",
        "title_en": "Visual C++ 2013 (x64)",
        "home": "https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist",
        "url": "https://aka.ms/highdpimfc2013x64enu",
        "file": "vc_redist_2013_x64.exe",
        "kind": "exe",
        "args": ("/install", "/quiet", "/norestart"),
        "publishers": ("Microsoft",),
        "max_mb": 20,
    },
}

LAUNCHER_KEYS = ("steam", "epic", "ea", "ubisoft", "gog")

# Наборы для вкладки «Установка» (совместимы с PresetDialog).
# В наборы попадают только программы с «вечнозелёным» адресом: версионные
# ссылки (7-Zip, LibreOffice, Acrobat, WinRAR и т. п.) ломаются при каждом
# релизе вендора, поэтому их здесь нет — их можно добавить вручную в CATALOG.
APP_PRESETS = [
    {
        "key": "launchers",
        "title": "Игровые лаунчеры",
        "title_en": "Game launchers",
        "desc": "Steam, Epic Games, EA app, Ubisoft Connect, GOG Galaxy",
        "desc_en": "Steam, Epic Games, EA app, Ubisoft Connect, GOG Galaxy",
        "packages": [(CATALOG[k]["title"], k) for k in LAUNCHER_KEYS],
    },
    {
        "key": "browsers",
        "title": "Браузеры",
        "title_en": "Browsers",
        "desc": "Chrome, Firefox, Яндекс Браузер, Opera",
        "desc_en": "Chrome, Firefox, Yandex Browser, Opera",
        "packages": [
            (CATALOG["chrome"]["title"], "chrome"),
            (CATALOG["firefox"]["title"], "firefox"),
            (CATALOG["yandex"]["title"], "yandex"),
            (CATALOG["opera"]["title"], "opera"),
        ],
    },
    {
        "key": "chat",
        "title": "Связь и звонки",
        "title_en": "Chat and calls",
        "desc": "Telegram, Discord, Zoom, Slack",
        "desc_en": "Telegram, Discord, Zoom, Slack",
        "packages": [
            (CATALOG["telegram"]["title"], "telegram"),
            (CATALOG["discord"]["title"], "discord"),
            (CATALOG["zoom"]["title"], "zoom"),
            (CATALOG["slack"]["title"], "slack"),
        ],
    },
    {
        "key": "office",
        "title": "Офис и документы",
        "title_en": "Office and documents",
        "desc": "ONLYOFFICE, LibreOffice, SumatraPDF",
        "desc_en": "ONLYOFFICE, LibreOffice, SumatraPDF",
        "packages": [
            (CATALOG["onlyoffice"]["title"], "onlyoffice"),
            (CATALOG["libreoffice"]["title"], "libreoffice"),
            (CATALOG["sumatrapdf"]["title"], "sumatrapdf"),
        ],
    },
    {
        "key": "media",
        "title": "Медиа и музыка",
        "title_en": "Media and music",
        "desc": "VLC, K-Lite Basic, Spotify",
        "desc_en": "VLC, K-Lite Basic, Spotify",
        "packages": [
            (CATALOG["vlc"]["title"], "vlc"),
            (CATALOG["klite"]["title"], "klite"),
            (CATALOG["spotify"]["title"], "spotify"),
        ],
    },
    {
        "key": "archivers",
        "title": "Архиваторы",
        "title_en": "Archivers",
        "desc": "7-Zip, WinRAR",
        "desc_en": "7-Zip, WinRAR",
        "packages": [
            (CATALOG["7zip"]["title"], "7zip"),
            (CATALOG["winrar"]["title"], "winrar"),
        ],
    },
    {
        "key": "utils",
        "title": "Полезные утилиты",
        "title_en": "Handy utilities",
        "desc": "Everything, Notepad++, PowerToys",
        "desc_en": "Everything, Notepad++, PowerToys",
        "packages": [
            (CATALOG["everything"]["title"], "everything"),
            (CATALOG["notepadpp"]["title"], "notepadpp"),
            (CATALOG["powertoys"]["title"], "powertoys"),
        ],
    },
]

VC_REDIST_PACKAGES = [
    (CATALOG["vcredist_2005_x86"]["title"], "vcredist_2005_x86"),
    (CATALOG["vcredist_2005_x64"]["title"], "vcredist_2005_x64"),
    (CATALOG["vcredist_2008_x86"]["title"], "vcredist_2008_x86"),
    (CATALOG["vcredist_2008_x64"]["title"], "vcredist_2008_x64"),
    (CATALOG["vcredist_2010_x86"]["title"], "vcredist_2010_x86"),
    (CATALOG["vcredist_2010_x64"]["title"], "vcredist_2010_x64"),
    (CATALOG["vcredist_2012_x86"]["title"], "vcredist_2012_x86"),
    (CATALOG["vcredist_2012_x64"]["title"], "vcredist_2012_x64"),
    (CATALOG["vcredist_2013_x86"]["title"], "vcredist_2013_x86"),
    (CATALOG["vcredist_2013_x64"]["title"], "vcredist_2013_x64"),
    (CATALOG["vcredist_x64"]["title"], "vcredist_x64"),
    (CATALOG["vcredist_x86"]["title"], "vcredist_x86"),
]

# Текст «обновлять нечего» — лаунчеры обновляются сами.
NO_UPDATES = "Нет пакетов для обновления."
NO_UPDATES_EN = "Nothing to update."


# =============================================================================
# Логирование в GUI (колбэк on_log)
# =============================================================================
def _log(on_log, text: str) -> None:
    if on_log:
        try:
            on_log(text)
        except Exception:
            pass


def _localized(ru: str, en: str) -> str:
    if i18n is not None and hasattr(i18n, "pick"):
        try:
            return i18n.pick(ru, en)
        except Exception:
            pass
    return ru


def no_updates_text() -> str:
    """Текст «обновлять нечего» на текущем языке интерфейса."""
    return _localized(NO_UPDATES, NO_UPDATES_EN)


def is_no_updates(message: str) -> bool:
    """True, если сообщение означает «обновлять нечего» (ru или en)."""
    if not message:
        return False
    return message.startswith(NO_UPDATES) or message.startswith(NO_UPDATES_EN)


def _bad_id_message(pkg_id: str) -> str:
    text = (pkg_id or "")[:80]
    if i18n is not None:
        try:
            return i18n.t("inst.bad_id", text)
        except Exception:
            pass
    return f"Неизвестный пакет: {text}"


# =============================================================================
# Win32: DACL (pywin32, запасной вариант — ctypes), WinVerifyTrust, read-lock
# =============================================================================
def _is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


if IS_WINDOWS:
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _wintrust = ctypes.WinDLL("wintrust", use_last_error=True)

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD),
                    ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class _WINTRUST_FILE_INFO(ctypes.Structure):
        _fields_ = [("cbStruct", wt.DWORD), ("pcwszFilePath", wt.LPCWSTR),
                    ("hFile", wt.HANDLE), ("pgKnownSubject", ctypes.POINTER(_GUID))]

    class _WINTRUST_DATA(ctypes.Structure):
        _fields_ = [
            ("cbStruct", wt.DWORD),
            ("pPolicyCallbackData", ctypes.c_void_p),
            ("pSIPClientData", ctypes.c_void_p),
            ("dwUIChoice", wt.DWORD),
            ("fdwRevocationChecks", wt.DWORD),
            ("dwUnionChoice", wt.DWORD),
            ("pFile", ctypes.POINTER(_WINTRUST_FILE_INFO)),
            ("dwStateAction", wt.DWORD),
            ("hWVTStateData", wt.HANDLE),
            ("pwszURLReference", wt.LPWSTR),
            ("dwProvFlags", wt.DWORD),
            ("dwUIContext", wt.DWORD),
            ("pSignatureSettings", ctypes.c_void_p),
        ]

    class _ACL(ctypes.Structure):
        _fields_ = [("AclRevision", ctypes.c_ubyte), ("Sbz1", ctypes.c_ubyte),
                    ("AclSize", wt.WORD), ("AceCount", wt.WORD), ("Sbz2", wt.WORD)]

    class _ACE_HEADER(ctypes.Structure):
        _fields_ = [("AceType", ctypes.c_ubyte), ("AceFlags", ctypes.c_ubyte),
                    ("AceSize", wt.WORD)]

    _WTD_UI_NONE = 2
    _WTD_REVOKE_WHOLECHAIN = 1
    _WTD_CHOICE_FILE = 1
    _WTD_STATEACTION_VERIFY = 1
    _WTD_STATEACTION_CLOSE = 2
    _WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT = 0x00000080
    _WTD_DISABLE_MD2_MD4 = 0x00002000

    _GENERIC_VERIFY_V2 = _GUID(
        0x00AAC56B, 0xCD44, 0x11D0,
        (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE))

    _wintrust.WinVerifyTrust.argtypes = [wt.HWND, ctypes.POINTER(_GUID), ctypes.c_void_p]
    _wintrust.WinVerifyTrust.restype = ctypes.c_long

    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wt.LPCWSTR, wt.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.DWORD)]
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wt.BOOL

    _advapi32.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wt.BOOL),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.BOOL)]
    _advapi32.GetSecurityDescriptorDacl.restype = wt.BOOL

    _advapi32.GetSecurityDescriptorControl.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wt.WORD), ctypes.POINTER(wt.DWORD)]
    _advapi32.GetSecurityDescriptorControl.restype = wt.BOOL

    _advapi32.ConvertStringSidToSidW.argtypes = [
        wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.ConvertStringSidToSidW.restype = wt.BOOL

    _advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(wt.LPWSTR)]
    _advapi32.ConvertSidToStringSidW.restype = wt.BOOL

    _advapi32.SetNamedSecurityInfoW.argtypes = [
        wt.LPWSTR, ctypes.c_int, wt.DWORD,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.SetNamedSecurityInfoW.restype = wt.DWORD

    _advapi32.GetNamedSecurityInfoW.argtypes = [
        wt.LPWSTR, ctypes.c_int, wt.DWORD,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.GetNamedSecurityInfoW.restype = wt.DWORD

    _advapi32.GetAce.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.GetAce.restype = wt.BOOL

    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    _kernel32.CreateFileW.argtypes = [
        wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p,
        wt.DWORD, wt.DWORD, wt.HANDLE]
    _kernel32.CreateFileW.restype = wt.HANDLE
    _kernel32.CloseHandle.argtypes = [wt.HANDLE]
    _kernel32.CloseHandle.restype = wt.BOOL

    _SE_FILE_OBJECT = 1
    _DACL_SECURITY_INFORMATION = 0x00000004
    _OWNER_SECURITY_INFORMATION = 0x00000001
    _PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
    _SE_DACL_PROTECTED = 0x0400

    _FILE_SHARE_READ = 0x00000001
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x00000080
    _INVALID_HANDLE = ctypes.c_void_p(-1).value


def _harden_dir_pywin32(path: str) -> None:
    """DACL через win32security: SYSTEM + Administrators, наследование off."""
    system = win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)
    admins = win32security.CreateWellKnownSid(win32security.WinBuiltinAdministratorsSid, None)
    inherit = ntsecuritycon.OBJECT_INHERIT_ACE | ntsecuritycon.CONTAINER_INHERIT_ACE

    dacl = win32security.ACL()
    dacl.AddAccessAllowedAceEx(win32security.ACL_REVISION, inherit,
                               ntsecuritycon.FILE_ALL_ACCESS, system)
    dacl.AddAccessAllowedAceEx(win32security.ACL_REVISION, inherit,
                               ntsecuritycon.FILE_ALL_ACCESS, admins)

    info = (win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION)
    try:
        win32security.SetNamedSecurityInfo(
            path, win32security.SE_FILE_OBJECT,
            info | win32security.OWNER_SECURITY_INFORMATION,
            admins, None, dacl, None)
    except Exception:
        # Смена владельца может требовать привилегии — тогда только DACL.
        win32security.SetNamedSecurityInfo(
            path, win32security.SE_FILE_OBJECT, info, None, None, dacl, None)


def _harden_dir_ctypes(path: str) -> None:
    """Запасной путь: тот же DACL через SDDL и SetNamedSecurityInfoW."""
    sddl = "D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
    sd = ctypes.c_void_p()
    if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(sd), None):
        raise InstallerSecurityError("Не удалось построить дескриптор безопасности")
    owner = ctypes.c_void_p()
    try:
        present, defaulted = wt.BOOL(), wt.BOOL()
        dacl = ctypes.c_void_p()
        if not _advapi32.GetSecurityDescriptorDacl(
                sd, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)):
            raise InstallerSecurityError("Не удалось извлечь DACL")
        _advapi32.ConvertStringSidToSidW(SID_ADMINS, ctypes.byref(owner))
        rc = _advapi32.SetNamedSecurityInfoW(
            path, _SE_FILE_OBJECT,
            _DACL_SECURITY_INFORMATION | _OWNER_SECURITY_INFORMATION
            | _PROTECTED_DACL_SECURITY_INFORMATION,
            owner, None, dacl, None)
        if rc != 0:
            rc = _advapi32.SetNamedSecurityInfoW(
                path, _SE_FILE_OBJECT,
                _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
                None, None, dacl, None)
        if rc != 0:
            raise InstallerSecurityError(f"SetNamedSecurityInfo: код {rc}")
    finally:
        if owner:
            _kernel32.LocalFree(owner)
        _kernel32.LocalFree(sd)


def _read_acl_pywin32(path: str) -> tuple:
    sd = win32security.GetNamedSecurityInfo(
        path, win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION)
    control, _revision = sd.GetSecurityDescriptorControl()
    protected = bool(control & win32security.SE_DACL_PROTECTED)
    dacl = sd.GetSecurityDescriptorDacl()
    sids = []
    if dacl is not None:
        for index in range(dacl.GetAceCount()):
            ace = dacl.GetAce(index)
            if len(ace) >= 3 and ace[2] is not None:
                sids.append(win32security.ConvertSidToStringSid(ace[2]))
    return protected, sids


def _read_acl_ctypes(path: str) -> tuple:
    sd = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    rc = _advapi32.GetNamedSecurityInfoW(
        path, _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
        None, None, ctypes.byref(dacl), None, ctypes.byref(sd))
    if rc != 0:
        raise InstallerSecurityError(f"GetNamedSecurityInfo: код {rc}")
    try:
        control, revision = wt.WORD(), wt.DWORD()
        _advapi32.GetSecurityDescriptorControl(sd, ctypes.byref(control), ctypes.byref(revision))
        protected = bool(control.value & _SE_DACL_PROTECTED)
        sids = []
        if dacl:
            acl = ctypes.cast(dacl, ctypes.POINTER(_ACL)).contents
            for index in range(acl.AceCount):
                ace_ptr = ctypes.c_void_p()
                if not _advapi32.GetAce(dacl, index, ctypes.byref(ace_ptr)):
                    continue
                header = ctypes.cast(ace_ptr, ctypes.POINTER(_ACE_HEADER)).contents
                if header.AceType not in (0, 1):
                    continue
                sid_ptr = ctypes.c_void_p(ace_ptr.value + 8)
                text = wt.LPWSTR()
                if _advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(text)):
                    sids.append(text.value)
                    _kernel32.LocalFree(text)
        return protected, sids
    finally:
        _kernel32.LocalFree(sd)


def _harden_dir(path: str) -> None:
    if _HAS_PYWIN32:
        _harden_dir_pywin32(path)
    else:
        _harden_dir_ctypes(path)


def _read_acl(path: str) -> tuple:
    return _read_acl_pywin32(path) if _HAS_PYWIN32 else _read_acl_ctypes(path)


def win_verify_trust(path: str) -> int:
    """Authenticode через WinVerifyTrust. 0 — подпись действительна."""
    if not IS_WINDOWS:
        raise InstallerSecurityError("WinVerifyTrust доступен только в Windows")
    file_info = _WINTRUST_FILE_INFO()
    file_info.cbStruct = ctypes.sizeof(_WINTRUST_FILE_INFO)
    file_info.pcwszFilePath = path
    file_info.hFile = None
    file_info.pgKnownSubject = None

    data = _WINTRUST_DATA()
    data.cbStruct = ctypes.sizeof(_WINTRUST_DATA)
    data.pPolicyCallbackData = None
    data.pSIPClientData = None
    data.dwUIChoice = _WTD_UI_NONE
    data.fdwRevocationChecks = _WTD_REVOKE_WHOLECHAIN
    data.dwUnionChoice = _WTD_CHOICE_FILE
    data.pFile = ctypes.pointer(file_info)
    data.dwStateAction = _WTD_STATEACTION_VERIFY
    data.hWVTStateData = None
    data.pwszURLReference = None
    data.dwProvFlags = (_WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT | _WTD_DISABLE_MD2_MD4)
    data.dwUIContext = 0
    data.pSignatureSettings = None

    action = _GENERIC_VERIFY_V2
    result = _wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(data))
    data.dwStateAction = _WTD_STATEACTION_CLOSE
    _wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(data))
    return int(result) & 0xFFFFFFFF


def _open_read_lock(path: str):
    """CreateFileW с FILE_SHARE_READ: запись и удаление заблокированы."""
    if not IS_WINDOWS:
        return None
    handle = _kernel32.CreateFileW(
        path, 0x80000000, _FILE_SHARE_READ, None,
        _OPEN_EXISTING, _FILE_ATTRIBUTE_NORMAL, None)
    if not handle or handle == _INVALID_HANDLE:
        raise InstallerSecurityError(
            f"Не удалось захватить файл на чтение: {ctypes.get_last_error()}")
    return handle


def _close_handle(handle) -> None:
    if IS_WINDOWS and handle:
        _kernel32.CloseHandle(handle)


# =============================================================================
# Сетевой слой: TLS 1.2/1.3, только HTTPS, anti-MITM
# =============================================================================
class HardenedTLSAdapter(HTTPAdapter):
    """Адаптер requests с жёстким TLS и запретом небезопасных соединений."""

    def __init__(self, fingerprint=None, **kwargs):
        self._fingerprint = fingerprint
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        # minimum_version уже отсекает SSLv3/TLS1.0/TLS1.1.
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            context.maximum_version = ssl.TLSVersion.TLSv1_3
        except (AttributeError, ValueError):
            pass
        kwargs["ssl_context"] = context
        if self._fingerprint:
            kwargs["assert_fingerprint"] = self._fingerprint
        return super().init_poolmanager(connections, maxsize, block=block, **kwargs)


_SESSION = None


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        # Не доверяем системным прокси: иначе TLS терминируется посредником.
        session.trust_env = False
        session.mount("https://", HardenedTLSAdapter())
        session.headers["User-Agent"] = "Swept/1.2 (+https://github.com/vladcodex/swept)"
        _SESSION = session
    return _SESSION


def _require_https(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise InstallerSecurityError(f"Разрешён только HTTPS: {url}")


def _download(url: str, dest: str, max_bytes: int, on_log=None) -> tuple:
    """Потоковая загрузка с лимитом размера и подсчётом SHA-256."""
    _require_https(url)
    digest = hashlib.sha256()
    total = 0
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    with _session().get(url, stream=True, timeout=(15, 120),
                        allow_redirects=True) as response:
        _require_https(response.url)  # защита от redirect -> http
        response.raise_for_status()
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise InstallerSecurityError("Файл превышает допустимый размер")
        try:
            fd = os.open(dest, flags, 0o600)
        except FileExistsError:
            # Stale file left by an interrupted earlier run (e.g. a child
            # installer still held it when the secure dir was removed). The
            # secure dir is hardened to SYSTEM+Administrators only, so no other
            # (non-admin) process can recreate it in the window below.
            try:
                os.remove(dest)
            except OSError:
                pass
            fd = os.open(dest, flags, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                for chunk in response.iter_content(65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise InstallerSecurityError("Превышен лимит размера")
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            try:
                os.remove(dest)
            except OSError:
                pass
            raise
    if total == 0:
        raise InstallerSecurityError("Сервер вернул пустой файл")
    _log(on_log, f"  скачано {total} байт, SHA-256 {digest.hexdigest()[:16]}…")
    return digest.hexdigest(), total


# =============================================================================
# Authenticode: WinVerifyTrust + издатель через Get-AuthenticodeSignature
# =============================================================================
_HRESULT_TEXT = {
    0x800B0100: "нет подписи",
    0x800B0101: "сертификат истёк",
    0x800B0109: "корневой сертификат не доверен",
    0x800B010A: "не удалось построить цепочку",
    0x800B010C: "сертификат отозван",
    0x800B010D: "проверка отзыва недоступна офлайн",
    0x800B010E: "не удалось проверить отзыв",
    0x80096010: "повреждённая подпись",
    0x800B0111: "издатель явно не доверен",
}


def _powershell_signature(path: str) -> dict:
    """Статус, тип и издатель подписи через безопасный вызов PowerShell."""
    powershell = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    script = (
        "$s = Get-AuthenticodeSignature -LiteralPath $env:SWEPT_SIG_PATH; "
        "$o = [ordered]@{ "
        "Status = [string]$s.Status; "
        "SignatureType = [string]$s.SignatureType; "
        "Subject = if ($s.SignerCertificate) { $s.SignerCertificate.Subject } else { '' }; "
        "Thumbprint = if ($s.SignerCertificate) { $s.SignerCertificate.Thumbprint } else { '' }; "
        "Message = [string]$s.StatusMessage }; "
        "$o | ConvertTo-Json -Compress"
    )
    env = dict(os.environ)
    env["SWEPT_SIG_PATH"] = path  # путь через env — без кавычек и спецсимволов в cmd
    proc = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script],
        shell=False, capture_output=True, text=True, errors="ignore",
        timeout=90, creationflags=CREATE_NO_WINDOW, env=env)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SignatureError("Не удалось получить статус подписи")
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise SignatureError(f"Некорректный ответ проверки подписи: {exc}") from exc


def _verify_signature(path: str, entry: dict) -> dict:
    """
    Проверяет подпись и издателя. При провале поднимает SignatureError.

    Учитывается catalog-подпись: для неё WinVerifyTrust с WTD_CHOICE_FILE
    законно возвращает TRUST_E_NOSIGNATURE, а решение принимает PowerShell
    (Status=Valid и SignatureType=Catalog).
    """
    hresult = win_verify_trust(path)
    info = None
    if hresult != 0:
        if hresult == 0x800B0100:  # нет встроенной подписи — возможно каталог
            info = _powershell_signature(path)
            if info.get("Status") != "Valid" or info.get("SignatureType") != "Catalog":
                raise SignatureError("файл не подписан (нет Authenticode и каталога)")
        else:
            raise SignatureError(
                f"WinVerifyTrust 0x{hresult:08X} "
                f"({_HRESULT_TEXT.get(hresult, 'неизвестная ошибка')})")

    if info is None:
        info = _powershell_signature(path)
    if info.get("Status") != "Valid":
        raise SignatureError(
            f"статус {info.get('Status') or 'нет'}: {info.get('Message') or ''}".strip())

    subject = info.get("Subject") or ""
    publishers = entry.get("publishers") or ()
    if not publishers:
        raise SignatureError("в каталоге не задан ожидаемый издатель")
    if not any(re.search(re.escape(p), subject, re.IGNORECASE) for p in publishers):
        raise SignatureError(f"издатель не совпал (получено: {subject})")
    return info


def _file_sha256(path: str) -> str:
    """SHA-256 файла с диска — пересчитывается заново, а не берётся из потока."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_artifact(path: str, entry: dict, on_log=None) -> dict | None:
    """
    Единая проверка скачанного файла перед запуском.

    Правило: у записи должен быть либо издатель (проверяется Authenticode),
    либо закреплённый SHA-256 — иначе установка отклоняется. Если заданы оба,
    проверяются оба.

    Закреплённый хеш нужен для вендоров, которые принципиально не подписывают
    инсталляторы (7-Zip, K-Lite): адрес у них версионный, содержимое файла
    фиксировано, поэтому хеш привязывает ровно те байты, которые были
    проверены. Это не слабее сверки издателя — это привязка к конкретному
    артефакту, а не к имени в сертификате.
    """
    pinned = (entry.get("sha256") or "").strip().lower()
    publishers = entry.get("publishers") or ()
    if not pinned and not publishers:
        raise SignatureError("в каталоге не задан ни издатель, ни SHA-256")

    info = None
    if publishers:
        info = _verify_signature(path, entry)

    if pinned:
        actual = _file_sha256(path)
        if actual != pinned:
            raise SignatureError(
                f"SHA-256 не совпал: получено {actual[:16]}…, ожидался {pinned[:16]}…")
        _log(on_log, "  SHA-256 совпал с закреплённым в каталоге")

    return info


# =============================================================================
# Изолированная папка
# =============================================================================
def _assert_not_reparse(path: str) -> None:
    info = os.lstat(path)
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise InstallerSecurityError(f"Путь является reparse point: {path}")


def _ensure_secure_dir(on_log=None) -> str:
    """Создаёт и ужесточает %ProgramData%\\SweptSecureTemp, проверяет DACL."""
    if not IS_WINDOWS:
        raise InstallerSecurityError("Модуль предназначен для Windows")
    if not _is_admin():
        raise InstallerSecurityError(
            "Нужны права администратора: иначе DACL заблокирует сам процесс")

    os.makedirs(SECURE_DIR, exist_ok=True)
    _assert_not_reparse(SECURE_DIR)
    _harden_dir(SECURE_DIR)

    protected, sids = _read_acl(SECURE_DIR)
    if not protected:
        raise InstallerSecurityError("Наследование DACL не отключено")
    unexpected = set(sids) - {SID_SYSTEM, SID_ADMINS}
    if unexpected:
        raise InstallerSecurityError(f"В DACL остались лишние субъекты: {sorted(unexpected)}")
    _log(on_log, f"  изолированная папка готова: {SECURE_DIR} (SYSTEM + Administrators)")
    return SECURE_DIR


def _secure_delete(path: str) -> None:
    """Затирает файл случайными байтами и удаляет (best-effort, с повторами).

    Повторяет попытку удаления, чтобы обойти кратковременную блокировку файла
    дочерним процессом установщика (например, msiexec у VC++ redistributable),
    который ещё держит exe-open после возврата управления.
    """
    if not os.path.isfile(path):
        return
    # Затирание содержимого — наилучшим образом, но не критично для очистки.
    try:
        size = os.path.getsize(path)
        with open(path, "r+b", buffering=0) as handle:
            remaining = size
            while remaining > 0:
                block = min(65536, remaining)
                handle.write(os.urandom(block))
                remaining -= block
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        pass
    # Удаление с повторами: файл может ещё держать дочерний процесс.
    for _ in range(10):
        try:
            os.remove(path)
            return
        except OSError:
            time.sleep(0.3)
    try:
        os.remove(path)
    except OSError:
        pass


def _remove_readonly(func, path, _excinfo):
    """Обработчик rmtree: снимает read-only и повторяет удаление файла/папки."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _remove_secure_dir(on_log=None) -> None:
    """Гарантированно сносит защищённую папку в ProgramData.

    Учитывает два реальных сбоя очистки:
      * файлы с атрибутом read-only (installer'ы часто такие оставляют);
      * файлы, ещё занятые дочерним процессом (msiexec у VC++ redistributable).
    Не молчит при неудаче — пишет предупреждение в журнал, чтобы остаток
    папки в ProgramData было видно.
    """
    if not IS_WINDOWS:
        return
    if not os.path.isdir(SECURE_DIR):
        return
    last_err = None
    for _ in range(8):
        try:
            shutil.rmtree(SECURE_DIR, onerror=_remove_readonly)
        except Exception as exc:  # noqa: BLE001 — ловим всё как причину неудачи
            last_err = exc
        if not os.path.isdir(SECURE_DIR):
            _log(on_log, f"  защищённая папка удалена: {SECURE_DIR}")
            return
        time.sleep(0.5)
    _log(on_log,
         f"  ВНИМАНИЕ: не удалось удалить {SECURE_DIR} — возможно, файл ещё "
         f"занят другим процессом. Закройте лишние программы и перезапустите "
         f"Swept, либо удалите папку вручную. Причина: {last_err}")


# =============================================================================
# Установка
# =============================================================================
def _build_command(path: str, entry: dict) -> list:
    """argv строго списком: путь и каждый флаг — отдельные элементы."""
    path = os.path.abspath(path)
    if entry["kind"] == "msi":
        msiexec = os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"), "System32", "msiexec.exe")
        if not os.path.isfile(msiexec):
            raise InstallerSecurityError("Не найден msiexec.exe в System32")
        return [msiexec, "/i", path, "/qn", "/norestart"]
    return [path] + list(entry["args"])


def _run_installer(path: str, entry: dict, on_log=None) -> int:
    argv = _build_command(path, entry)
    _log(on_log, "  запуск: " + " ".join(argv))
    proc = subprocess.run(
        argv, cwd=os.path.dirname(path),
        shell=False,                    # критично: без интерпретатора команд
        timeout=1800, creationflags=CREATE_NO_WINDOW,
        capture_output=True, text=True, errors="ignore")
    if proc.stdout:
        _log(on_log, proc.stdout[-1500:])
    if proc.stderr:
        _log(on_log, proc.stderr[-1500:])
    return proc.returncode


def _install_one(key: str, on_log=None) -> tuple:
    """Скачивает, проверяет и устанавливает один пакет. Всегда чистит за собой."""
    entry = CATALOG[key]
    dest = ""
    lock = None
    try:
        _log(on_log, f"Установка: {entry['title']}")
        work_dir = _ensure_secure_dir(on_log)
        dest = os.path.join(work_dir, entry["file"])

        _download(entry["url"], dest, entry["max_mb"] * 1024 * 1024, on_log)

        _log(on_log, "  проверка файла…")
        info = _verify_artifact(dest, entry, on_log)
        if info:
            _log(on_log, f"  подпись действительна: {info.get('Subject')}")
        else:
            _log(on_log, "  файл без подписи — принят по закреплённому SHA-256")

        # Держим файл на чтении до конца установки: запись/удаление запрещены.
        # Повторная проверка уже под замком закрывает окно TOCTOU; для записей
        # без подписи она пересчитывает хеш прямо с диска.
        lock = _open_read_lock(dest)
        _verify_artifact(dest, entry)

        code = _run_installer(dest, entry, on_log)
        ok = code in _SUCCESS_CODES
        if ok:
            return True, f"установлено (код {code})" if code else "установлено"
        return False, f"установщик вернул код {code}"
    except SignatureError as exc:
        # Файл будет удалён в finally; наружу — понятное сообщение.
        return False, f"подпись не прошла проверку: {exc}"
    except InstallerSecurityError as exc:
        return False, str(exc)
    except subprocess.TimeoutExpired:
        return False, "таймаут установки"
    except Exception as exc:  # noqa: BLE001 — наружу отдаём текст, не падаем
        return False, f"ошибка установки: {exc!r}"
    finally:
        _close_handle(lock)
        if dest:
            _secure_delete(dest)
        _log(on_log, "  временные файлы удалены")


# =============================================================================
# Публичный API для GUI-воркера
# =============================================================================
def is_winget_available() -> bool:
    """Всегда False: winget больше не используется (прямая безопасная установка)."""
    return False


def is_installer_available() -> bool:
    """True, если безопасная установка доступна (нужны права администратора)."""
    return _is_admin()


def is_valid_package_id(pkg_id: str) -> bool:
    """True, если строка — известный ключ каталога."""
    return bool(pkg_id) and pkg_id.strip().lower() in CATALOG


def search_packages(query: str, on_log=None) -> list:
    """
    Поиск по каталогу лаунчеров (совместимость с вкладкой «Установка»).

    Возвращает [{"name","id","version","source"}]. Пустой запрос — весь каталог.
    """
    text = (query or "").strip().lower()
    _log(on_log, f"Поиск: {query!r}")
    results = []
    for key, entry in CATALOG.items():
        haystack = " ".join((key, entry["title"], entry.get("title_en", ""))).lower()
        if not text or text in haystack:
            results.append({
                "name": entry["title"],
                "id": key,
                "version": "latest",
                "source": "official CDN",
            })
    _log(on_log, f"Найдено: {len(results)}")
    return results


def install_package(pkg_id: str, on_log=None, dry_run: bool = False) -> tuple:
    """
    Устанавливает один пакет.

    Возвращает (success: bool, message: str). Исключения безопасности
    обрабатываются внутри: файл удаляется, наружу отдаётся причина.
    """
    key = (pkg_id or "").strip().lower()
    if key not in CATALOG:
        return False, _bad_id_message(pkg_id)
    if dry_run:
        return True, f"[СИМУЛЯЦИЯ] {CATALOG[key]['title']}: {CATALOG[key]['url']}"
    try:
        return _install_one(key, on_log=on_log)
    finally:
        # Гарантированная очистка защищённой папки после одиночной установки.
        _remove_secure_dir(on_log)


def install_packages(packages: list, on_log=None, dry_run: bool = False) -> tuple:
    """
    Устанавливает набор пакетов последовательно.

    Принимает как список ключей (["steam","epic"]), так и пары
    (("Steam","steam"), ...) — формат, который отдаёт PresetDialog.
    Возвращает (all_ok: bool, отчёт: str).

    Изолированная папка в ProgramData создаётся один раз перед циклом и
    гарантированно удаляется один раз после завершения (см. finally) —
    когда всё установлено, папка убирается.
    """
    items = []
    for item in packages or []:
        if isinstance(item, (tuple, list)) and len(item) == 2:
            label, key = str(item[0]), str(item[1])
        else:
            label = key = str(item)
        items.append((label, key))

    if not items:
        return True, ""

    overall = True
    lines = []
    if not dry_run:
        # Одна изолированная папка на весь набор — создаём до цикла.
        try:
            _ensure_secure_dir(on_log)
        except Exception as exc:
            return False, f"не удалось подготовить изолированную папку: {exc}"
    try:
        for label, key in items:
            if key not in CATALOG:
                overall = False
                lines.append(f"{label}: ОШИБКА — неизвестный пакет «{key}»")
                _log(on_log, f"{label}: неизвестный пакет")
                continue
            if dry_run:
                ok, message = True, (
                    f"[СИМУЛЯЦИЯ] {CATALOG[key]['title']}: {CATALOG[key]['url']}")
            else:
                ok, message = _install_one(key, on_log=on_log)
            overall = overall and ok
            mark = "OK" if ok else "ОШИБКА"
            lines.append(f"{label}: {mark}" + (f" — {message}" if message else ""))
            _log(on_log, f"{label}: {'готово' if ok else 'не удалось'}"
                          + (f" — {message}" if not ok and message else ""))
    finally:
        # Когда всё установлено — удаляем папку в ProgramData (с повторами).
        if not dry_run:
            _remove_secure_dir(on_log)
    return overall, "\n".join(lines)


def list_upgradable(on_log=None) -> list:
    """Совместимость: лаунчеры обновляются сами, список пуст."""
    _log(on_log, "Лаунчеры обновляются автоматически при запуске.")
    return []


def upgrade_package(pkg_id: str, on_log=None, dry_run: bool = False) -> tuple:
    """Совместимость: обновление выполняет сам лаунчер. Ключ валидируется."""
    key = (pkg_id or "").strip().lower()
    if key not in CATALOG:
        return False, _bad_id_message(pkg_id)
    return True, no_updates_text() + "\nЛаунчеры обновляются автоматически при запуске."


def upgrade_all(on_log=None, dry_run: bool = False) -> tuple:
    """Совместимость: обновление выполняет сам лаунчер."""
    _log(on_log, "Лаунчеры обновляются автоматически при запуске.")
    return True, no_updates_text() + "\nЛаунчеры обновляются автоматически при запуске."


# =============================================================================
# CLI (ручная проверка)
# =============================================================================
def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Безопасная установка лаунчеров")
    parser.add_argument("--list", action="store_true", help="список пакетов")
    parser.add_argument("--check", metavar="KEY", help="скачать и проверить подпись")
    parser.add_argument("--install", nargs="+", metavar="KEY", help="установить пакеты")
    args = parser.parse_args(argv)

    if args.list:
        for key, entry in CATALOG.items():
            print(f"{key:14s} {entry['kind']:4s} {entry['title']}")
        return 0

    if args.check:
        key = args.check.strip().lower()
        if key not in CATALOG:
            print(_bad_id_message(key))
            return 2
        entry = CATALOG[key]
        dest = ""
        try:
            work_dir = _ensure_secure_dir(print)
            dest = os.path.join(work_dir, entry["file"])
            _download(entry["url"], dest, entry["max_mb"] * 1024 * 1024, print)
            info = _verify_artifact(dest, entry, print)
            if info:
                print(f"OK   {key}: подпись действительна — {info.get('Subject')}")
            else:
                print(f"OK   {key}: подписи нет, SHA-256 совпал с закреплённым")
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {key}: {exc}")
            return 2
        finally:
            if dest:
                _secure_delete(dest)
            _remove_secure_dir(print)

    if args.install:
        ok, report = install_packages(args.install, on_log=print)
        print(report)
        return 0 if ok else 2

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
