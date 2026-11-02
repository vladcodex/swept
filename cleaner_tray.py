#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
r"""
cleaner_tray.py — ИКОНКА В ОБЛАСТИ УВЕДОМЛЕНИЙ (СИСТЕМНЫЙ ТРЕЙ) БЕЗ ЗАВИСИМОСТЕЙ.

Почему ctypes, а не готовая библиотека
-------------------------------------
`pystray` и `pywin32` — это ещё две зависимости в сборке, каждая со своим
поведением в PyInstaller/Nuitka и своим размером. Задача же узкая: одна
иконка, одно меню, одна подсказка. Всё это есть в shell32/user32, и вызов
через ctypes не тянет за собой ничего.

Как это работает
----------------
    * Создаётся скрытое окно-«приёмник» (HWND_MESSAGE) со своей оконной
      процедурой. Иконка трея присылает события именно ему.
    * `Shell_NotifyIconW` добавляет иконку, меняет подсказку и убирает её.
    * Насос сообщений крутится в отдельном потоке: он не мешает Tk-циклу
      и не требует, чтобы главное окно было открыто.
    * Меню собирается заново на каждый клик — поэтому смена языка
      интерфейса не требует пересоздавать иконку.

Важное про потоки
-----------------
Колбэк `on_action` вызывается в потоке трея. Интерфейс не должен трогать
из него Tk напрямую: правильный путь — положить событие в свою очередь
и обработать его в главном потоке (так и сделано в cleaner_gui).

Если что-то не поддерживается (не Windows, нет shell32, отказ
Shell_NotifyIcon), модуль не бросает исключение: `start()` возвращает False,
и приложение просто работает без трея.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from ctypes import wintypes

IS_WINDOWS = (os.name == "nt")

# --- константы Win32 (значения фиксированы API, не меняются) ----------------
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_NULL = 0x0000
WM_APP = 0x8000
WM_TRAY = WM_APP + 20          # наше собственное сообщение от иконки

WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2

NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10

NIIF_INFO = 0x01
NIIF_NOSOUND = 0x10

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
LR_DEFAULTSIZE = 0x0040

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_GRAYED = 0x0001

TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020

SW_HIDE = 0
SW_RESTORE = 9

IDI_APPLICATION = 32512

# Идентификаторы пунктов меню.
ID_OPEN = 1001
ID_CLEAN = 1002
ID_HIDE = 1003
ID_QUIT = 1004

# Сколько символов помещается в подсказку и в текст всплывающего уведомления.
TIP_MAX = 127
INFO_MAX = 255
INFO_TITLE_MAX = 63


if IS_WINDOWS:  # pragma: no branch - на других платформах модуль просто не работает
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        """Описание класса окна (winuser.h)."""
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class GUID(ctypes.Structure):
        """GUID нужен только для выравнивания NOTIFYICONDATAW под x64."""
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        """Структура иконки трея. Порядок полей строго по winuser.h."""
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", GUID),
            ("hBalloonIcon", wintypes.HICON),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    def _declare_prototypes() -> None:
        """
        Явные прототипы всех используемых функций.

        Без них ctypes считает аргументы 32-битными int — и на x64 дескриптор
        окна (64 бита) обрезается, а вызов уходит «в никуда» или в чужое окно.
        Это не теория: именно так падает трей, написанный «по памяти».
        """
        _user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
        _user32.RegisterClassW.restype = wintypes.ATOM
        _user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
        _user32.CreateWindowExW.restype = wintypes.HWND
        _user32.DestroyWindow.argtypes = [wintypes.HWND]
        _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM]
        _user32.DefWindowProcW.restype = ctypes.c_void_p
        _user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
        _user32.RegisterWindowMessageW.restype = wintypes.UINT
        _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                         wintypes.WPARAM, wintypes.LPARAM]
        _user32.PostQuitMessage.argtypes = [ctypes.c_int]
        _user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                        wintypes.UINT, wintypes.UINT]
        _user32.GetMessageW.restype = ctypes.c_int
        _user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        _user32.DispatchMessageW.restype = ctypes.c_void_p
        _user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        _user32.LoadIconW.restype = wintypes.HICON
        _user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR,
                                       wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                       wintypes.UINT]
        _user32.LoadImageW.restype = wintypes.HICON
        _user32.CreatePopupMenu.restype = wintypes.HMENU
        _user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT,
                                        ctypes.c_size_t, wintypes.LPCWSTR]
        _user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT,
                                           ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, wintypes.HWND,
                                           wintypes.LPVOID]
        _user32.TrackPopupMenu.restype = wintypes.BOOL
        _user32.DestroyMenu.argtypes = [wintypes.HMENU]
        _user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
        _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        _user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        _user32.FindWindowW.restype = wintypes.HWND
        _shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                               ctypes.POINTER(NOTIFYICONDATAW)]
        _shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        _kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    _declare_prototypes()
else:  # pragma: no cover - не Windows
    WNDPROC = WNDCLASSW = GUID = NOTIFYICONDATAW = POINT = None


class TrayIcon:
    """
    Иконка в трее с меню и всплывающими уведомлениями.

    Использование:
        tray = TrayIcon(tooltip="Swept", icon_path=ico,
                        labels={"open": "Открыть", ...}, on_action=handler)
        if tray.start():
            tray.set_tooltip("Swept · свободно 12.3 ГБ")
        ...
        tray.stop()
    """

    def __init__(self, tooltip: str = "Swept", icon_path: str = "",
                 labels: dict | None = None, on_action=None):
        self.tooltip = tooltip
        self.icon_path = icon_path or ""
        self.labels = dict(labels or {})
        self.on_action = on_action

        self._hwnd = None
        self._hicon = None
        self._thread = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._nid = None
        self._wndproc = None      # ссылку держим: иначе колбэк соберёт GC
        self._class = None
        self._class_name = "SweptTrayWindow"
        self._taskbar_msg = 0

    # ------------------------------------------------------------- запуск
    def start(self, timeout: float = 2.0) -> bool:
        """
        Создаёт иконку и запускает поток сообщений.

        True — иконка появилась. False — трей недоступен, приложение
        продолжает работать без него (это не ошибка).
        """
        if not IS_WINDOWS or self._running:
            return False
        try:
            self._thread = threading.Thread(target=self._run, name="swept-tray",
                                            daemon=True)
            self._thread.start()
            # Ждём готовности окна, чтобы set_tooltip() сразу после start()
            # не попал в пустоту.
            self._ready.wait(timeout)
            return self._running
        except Exception:
            return False

    def stop(self) -> None:
        """Убирает иконку и останавливает поток. Безопасно вызывать дважды."""
        if not IS_WINDOWS or not self._hwnd:
            self._running = False
            return
        try:
            _user32.PostMessageW(wintypes.HWND(self._hwnd), WM_CLOSE, 0, 0)
        except Exception:
            pass
        self._running = False

    # ------------------------------------------------------------ свойства
    def set_labels(self, labels: dict) -> None:
        """Меняет подписи меню (при смене языка интерфейса)."""
        self.labels = dict(labels or {})

    def set_tooltip(self, text: str) -> None:
        """Меняет всплывающую подсказку иконки."""
        text = (text or "Swept")[:TIP_MAX]
        if text == self.tooltip:
            return
        self.tooltip = text
        self._modify(tip=text)

    def notify(self, title: str, text: str) -> None:
        """Показывает всплывающее уведомление рядом с иконкой."""
        if not self._running:
            return
        with self._lock:
            if self._nid is None:
                return
            self._nid.uFlags = NIF_INFO
            self._nid.szInfo = (text or "")[:INFO_MAX]
            self._nid.szInfoTitle = (title or "")[:INFO_TITLE_MAX]
            self._nid.dwInfoFlags = NIIF_INFO | NIIF_NOSOUND
            self._nid.uTimeoutOrVersion = 10000
            try:
                _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            except Exception:
                pass
            finally:
                # Флаг сбрасываем: иначе следующая правка подсказки снова
                # покажет это же уведомление.
                self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP

    # ------------------------------------------------------------- внутреннее
    def _modify(self, tip: str | None = None, icon=None) -> None:
        """Обновляет подсказку и/или иконку уже добавленной иконки трея."""
        if not self._running:
            return
        with self._lock:
            if self._nid is None:
                return
            self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            if tip is not None:
                self._nid.szTip = tip
            if icon is not None:
                self._nid.hIcon = icon
            try:
                _shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            except Exception:
                pass

    def _load_icon(self):
        """Иконка из файла .ico, иначе стандартная иконка приложения."""
        if self.icon_path and os.path.isfile(self.icon_path):
            handle = _user32.LoadImageW(None, self.icon_path, IMAGE_ICON,
                                        0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if handle:
                return handle
        # IDI_APPLICATION — не строка, а число, упакованное в указатель
        # (MAKEINTRESOURCE), поэтому передаётся как c_void_p, а не LPCWSTR.
        return _user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))

    def _menu(self):
        """Собирает меню заново: подписи могли смениться вместе с языком."""
        menu = _user32.CreatePopupMenu()
        if not menu:
            return None
        labels = self.labels
        _user32.AppendMenuW(menu, MF_STRING, ID_OPEN,
                            labels.get("open", "Open"))
        _user32.AppendMenuW(menu, MF_STRING, ID_CLEAN,
                            labels.get("clean", "Clean"))
        _user32.AppendMenuW(menu, MF_STRING, ID_HIDE,
                            labels.get("hide", "Minimize"))
        _user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        _user32.AppendMenuW(menu, MF_STRING, ID_QUIT,
                            labels.get("quit", "Quit"))
        return menu

    def _show_menu(self) -> None:
        """Показывает контекстное меню у курсора."""
        menu = self._menu()
        if not menu:
            return
        point = POINT()
        _user32.GetCursorPos(ctypes.byref(point))
        # Классический трюк Windows: без SetForegroundWindow меню не закроется
        # по клику вне его, а PostMessage(WM_NULL) «дотягивает» очередь.
        _user32.SetForegroundWindow(wintypes.HWND(self._hwnd))
        _user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_BOTTOMALIGN,
                               point.x, point.y, 0, wintypes.HWND(self._hwnd),
                               None)
        _user32.PostMessageW(wintypes.HWND(self._hwnd), WM_NULL, 0, 0)
        _user32.DestroyMenu(menu)

    def _emit(self, action: str) -> None:
        """Отдаёт событие наружу. Ошибка обработчика не должна убить трей."""
        if not self.on_action:
            return
        try:
            self.on_action(action)
        except Exception:
            pass

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """Оконная процедура скрытого окна: события иконки и меню."""
        try:
            if msg == WM_TRAY:
                event = int(lparam) & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._emit("open")
                elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu()
                return 0
            if msg == WM_COMMAND:
                command = int(wparam) & 0xFFFF
                if command == ID_OPEN:
                    self._emit("open")
                elif command == ID_CLEAN:
                    self._emit("clean")
                elif command == ID_HIDE:
                    self._emit("hide")
                elif command == ID_QUIT:
                    self._emit("quit")
                return 0
            if msg == self._taskbar_msg and self._taskbar_msg:
                # Проводник перезапустился (например, после обновления) —
                # иконку нужно добавить заново, иначе она исчезнет.
                self._add_icon()
                return 0
            if msg == WM_CLOSE:
                _user32.DestroyWindow(wintypes.HWND(hwnd))
                return 0
            if msg == WM_DESTROY:
                self._remove_icon()
                _user32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return _user32.DefWindowProcW(wintypes.HWND(hwnd), msg, wparam, lparam)

    def _add_icon(self) -> bool:
        """Добавляет иконку в трей (или обновляет, если она уже есть)."""
        if self._nid is None:
            return False
        with self._lock:
            self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            self._nid.szTip = self.tooltip[:TIP_MAX]
            self._nid.hIcon = self._hicon
            try:
                return bool(_shell32.Shell_NotifyIconW(
                    NIM_ADD, ctypes.byref(self._nid)))
            except Exception:
                return False

    def _remove_icon(self) -> None:
        """Убирает иконку из трея."""
        if self._nid is None:
            return
        with self._lock:
            try:
                _shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
            except Exception:
                pass

    def _run(self) -> None:
        """Поток трея: регистрация окна, иконка, насос сообщений."""
        try:
            self._class = WNDCLASSW()
            self._class.lpfnWndProc = WNDPROC(self._wnd_proc)
            self._class.hInstance = _kernel32.GetModuleHandleW(None)
            self._class.lpszClassName = self._class_name
            if not _user32.RegisterClassW(ctypes.byref(self._class)):
                # Класс мог остаться от предыдущего запуска в этом процессе.
                if ctypes.get_last_error() != 1410:      # ERROR_CLASS_ALREADY_EXISTS
                    self._ready.set()
                    return

            self._taskbar_msg = _user32.RegisterWindowMessageW("TaskbarCreated")
            hwnd = _user32.CreateWindowExW(
                0, self._class_name, "Swept", 0, 0, 0, 0, 0,
                ctypes.c_void_p(-3),        # HWND_MESSAGE: окно без интерфейса
                None, self._class.hInstance, None)
            if not hwnd:
                self._ready.set()
                return
            self._hwnd = hwnd

            self._hicon = self._load_icon()
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = hwnd
            nid.uID = 1
            nid.uCallbackMessage = WM_TRAY
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.hIcon = self._hicon
            nid.szTip = self.tooltip[:TIP_MAX]
            self._nid = nid

            self._running = self._add_icon()
            self._ready.set()
            if not self._running:
                # Иконки нет — окно и поток больше не нужны.
                _user32.DestroyWindow(wintypes.HWND(hwnd))
                return

            message = wintypes.MSG()
            while True:
                result = _user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result in (0, -1):       # WM_QUIT или ошибка
                    break
                _user32.TranslateMessage(ctypes.byref(message))
                _user32.DispatchMessageW(ctypes.byref(message))
        except Exception:
            pass
        finally:
            self._running = False
            self._ready.set()


def available() -> bool:
    """True, если трей в принципе доступен на этой системе."""
    if not IS_WINDOWS:
        return False
    try:
        return bool(_shell32 and _user32)
    except Exception:
        return False


if __name__ == "__main__":  # pragma: no cover - ручная проверка иконки
    def _handler(action: str) -> None:
        print("tray action:", action)
        if action == "quit":
            tray.stop()

    tray = TrayIcon(tooltip="Swept — проверка трея",
                    icon_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "app.ico"),
                    labels={"open": "Открыть", "clean": "Очистить",
                            "hide": "Свернуть", "quit": "Выход"},
                    on_action=_handler)
    if not tray.start():
        print("Трей недоступен")
        sys.exit(1)
    print("Иконка добавлена. Кликните по ней; выход — из меню.")
    try:
        threading.Event().wait(120)
    except KeyboardInterrupt:
        tray.stop()
