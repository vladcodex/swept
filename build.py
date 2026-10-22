#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
build.py — builds Swept into a single .exe with PyInstaller.

Everything is written INSIDE the project folder only:
    dist\Swept.exe           — the finished file
    .build\work\             — PyInstaller temporary files
    .build\version_info.txt  — version resource (generated)

Examples:
    python build.py                  # normal build (the exe asks for admin rights)
    python build.py --no-admin       # no UAC prompt
    python build.py --onedir         # folder instead of a single file (faster start)
    python build.py --console        # keep the console window (debugging)
    python build.py --test           # trial build without UAC into .build\test
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
BUILD_DIR = os.path.join(BASE, ".build")
APP_NAME = "Swept"
VERSION = (1, 1, 3, 0)
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
        StringStruct('FileDescription', 'Swept — safe Windows 10/11 cleanup'),
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
    """Creates .build/version_info.txt and returns its path."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    path = os.path.join(BUILD_DIR, "version_info.txt")
    ver_str = ".".join(str(part) for part in VERSION)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(VERSION_INFO_TEMPLATE.format(
            filevers=VERSION, prodvers=VERSION, ver_str=ver_str, exe_name=exe_name))
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Swept into an exe")
    parser.add_argument("--no-admin", action="store_true",
                        help="do not request administrator rights on launch")
    parser.add_argument("--onefile", action="store_true",
                        help="build a single self-extracting exe instead of a folder "
                             "(NOT recommended: unpacks to %%TEMP%% at launch and reliably "
                             "trips AV false positives)")
    parser.add_argument("--onedir", action="store_true",
                        help="folder build (the default; faster startup, fewer AV flags)")
    parser.add_argument("--console", action="store_true",
                        help="show the console window (debugging)")
    parser.add_argument("--test", action="store_true",
                        help="trial build without UAC into .build\\test")
    parser.add_argument("--name", default=APP_NAME, help="exe name")
    args = parser.parse_args()

    if not os.path.isfile(ENTRY):
        print("Entry point not found: " + ENTRY)
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
        "--onefile" if args.onefile else "--onedir",
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

    print("Building: " + " ".join(cmd))
    result = subprocess.run(cmd, cwd=BASE)
    if result.returncode != 0:
        print("\n[ERROR] PyInstaller exited with code {}".format(result.returncode))
        return result.returncode

    exe_path = os.path.join(dist, name + ".exe")
    if args.onedir:
        exe_path = os.path.join(dist, name, name + ".exe")
    if os.path.isfile(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print("\nDone: {}  ({:.1f} MB)".format(exe_path, size_mb))
        return 0
    print("\n[ERROR] exe not found after build: " + exe_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
