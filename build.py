#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
build.py — сборка Swept в один .exe (PyInstaller).

Всё пишется ТОЛЬКО внутри папки проекта:
    dist\Swept.exe           — готовый файл
    .build\work\             — временные файлы PyInstaller
    .build\version_info.txt   — ресурс версии (генерируется)

Примеры:
    python build.py                  # обычная сборка (exe просит права админа)
    python build.py --no-admin       # без UAC-запроса
    python build.py --onedir         # папка вместо одного файла (быстрее старт)
    python build.py --console        # с консолью (для отладки)
    python build.py --test           # пробная сборка без UAC в .build\test
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(BASE, ".build")
APP_NAME = "Swept"
VERSION = (1, 1, 2, 0)
ICON = os.path.join(BASE, "app.ico")
ENTRY = os.path.join(BASE, "cleaner_gui.py")

VERSION_INFO_TEMPLATE = """VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={filevers},
    prodvers={prodvers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
        StringStruct('CompanyName', 'Swept'),
        StringStruct('FileDescription', 'Swept — безопасная очистка Windows 10/11'),
        StringStruct('FileVersion', '{ver_str}'),
        StringStruct('InternalName', 'cleaner_gui'),
        StringStruct('LegalCopyright', 'Freeware'),
        StringStruct('OriginalFilename', '{exe_name}.exe'),
        StringStruct('ProductName', 'Swept'),
        StringStruct('ProductVersion', '{ver_str}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [1049, 1200])])
  ]
)
"""


def write_version_info(exe_name: str) -> str:
    """Создаёт .build/version_info.txt и возвращает путь к нему."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    path = os.path.join(BUILD_DIR, "version_info.txt")
    ver_str = ".".join(str(part) for part in VERSION)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(VERSION_INFO_TEMPLATE.format(
            filevers=VERSION, prodvers=VERSION, ver_str=ver_str, exe_name=exe_name))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка Swept в exe")
    parser.add_argument("--no-admin", action="store_true",
                        help="не запрашивать права администратора при запуске")
    parser.add_argument("--onedir", action="store_true",
                        help="собрать папку вместо одного файла")
    parser.add_argument("--console", action="store_true",
                        help="показать консольное окно (отладка)")
    parser.add_argument("--test", action="store_true",
                        help="пробная сборка без UAC в .build\\test")
    parser.add_argument("--name", default=APP_NAME, help="имя exe")
    args = parser.parse_args()

    if not os.path.isfile(ENTRY):
        print("Не найден входной файл: " + ENTRY)
        return 1

    name = args.name
    dist = os.path.join(BASE, "dist")
    work = os.path.join(BUILD_DIR, "work")
    spec_dir = BUILD_DIR
    if args.test:
        name = name + " (test)"
        dist = os.path.join(BUILD_DIR, "test")
        work = os.path.join(BUILD_DIR, "work_test")
        spec_dir = os.path.join(BUILD_DIR, "test")

    version_file = write_version_info(name)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onedir" if args.onedir else "--onefile",
        "--console" if args.console else "--windowed",
        "--name", name,
        "--distpath", dist,
        "--workpath", work,
        "--specpath", spec_dir,
        "--collect-all", "customtkinter",
        "--exclude-module", "tkinter.test",
        "--exclude-module", "unittest",
        "--exclude-module", "pydoc_data",
    ]
    if os.path.isfile(ICON):
        cmd += ["--icon", ICON]
    if os.path.isfile(version_file):
        cmd += ["--version-file", version_file]
    if not (args.no_admin or args.test):
        cmd += ["--uac-admin"]
    cmd.append(ENTRY)

    print("Сборка: " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=BASE)
    if result.returncode != 0:
        print("\n[ОШИБКА] PyInstaller завершился с кодом {}".format(result.returncode))
        return result.returncode

    exe_path = os.path.join(dist, name + ".exe")
    if args.onedir:
        exe_path = os.path.join(dist, name, name + ".exe")
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("\nГотово: {}  ({:.1f} МБ)".format(exe_path, size_mb))
        return 0
    print("\n[ОШИБКА] exe не найден после сборки: " + exe_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
