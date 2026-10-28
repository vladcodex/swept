#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_gui.py — ГРАФИЧЕСКИЙ ИНТЕРФЕЙС (CustomTkinter) для Swept.

Возможности интерфейса
----------------------
    * Современный ТЁМНЫЙ дизайн (CustomTkinter).
    * Переключатель языка (Русский / English), выбор сохраняется в реестре.
    * Вкладка «Очистка»: чек-боксы категорий, кнопки «Анализ»/«Очистить»,
      переключатель «Только сканирование», прогресс-бар, статус.
    * Вкладка «Установка»: поиск программ в каталоге, наборы популярных
      приложений с выбором галочками, установка/обновление пакета,
      обновление всех пакетов.
    * Вкладка «Оптимизация»: безопасные настройки Windows по группам,
      живой ход выполнения, кнопка создания точки восстановления.
    * Вкладка «Расписание»: тихая автоматическая очистка по расписанию
      (ежедневно/еженедельно) с авто-созданием точки восстановления перед
      удалением и опциональным сухим прогоном; есть режим --silent-clean
      для автономной задачи Windows (schtasks).
    * Вкладка «Журнал»: текстовое поле с путями удаляемых файлов и итогами.
    * Индикатор прав администратора.

Запуск:  python cleaner_gui.py
Требуется:  pip install customtkinter
"""

from __future__ import annotations

import copy
import ctypes
import datetime
import math
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from collections import deque
from tkinter import messagebox

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover - подсказка при отсутствии библиотеки
    print("Не найдена библиотека CustomTkinter.")
    print("Установите её командой:  pip install customtkinter")
    sys.exit(1)

import cleaner_core as core
import cleaner_diagnose as diag
import cleaner_i18n as i18n
import cleaner_installer as inst
import cleaner_optimize as opt
import cleaner_settings as settings

# =============================================================================
# НАСТРОЙКИ ВНЕШНЕГО ВИДА
# =============================================================================

COLOR_BG = "#0c0b14"
COLOR_CARD = "#15132a"
COLOR_CARD_2 = "#1e1b38"
COLOR_ACCENT = "#3b82f6"
COLOR_ACCENT_HOVER = "#2f6fd0"
COLOR_GREEN = "#22c55e"
COLOR_GREEN_HOVER = "#1ea34c"
COLOR_RED = "#ef4444"
COLOR_WARN = "#f59e0b"
COLOR_TEXT = "#e9e6f7"
COLOR_MUTED = "#9b96b8"
COLOR_ROW_SELECTED = "#1f3b63"   # фон выбранной строки списка пакетов
COLOR_MINT = "#57ffc6"           # акцент орбиты и телеметрии
COLOR_VIOLET = "#a98bff"         # второй акцент бренда (знак, кольцо, вердикты)
COLOR_LINE = "#2a2650"           # тонкие обводки панелей

# Цвет вердикта разбора «почему тормозит»: от мятного к красному.
DIAG_VERDICT_COLORS = {
    "excellent": COLOR_MINT,
    "good": COLOR_GREEN,
    "fair": COLOR_WARN,
    "bad": COLOR_RED,
}

# Цвет причины по её важности.
DIAG_SEVERITY_COLORS = {
    "high": COLOR_RED,
    "medium": COLOR_WARN,
    "low": COLOR_MUTED,
}

# Ширина боковых рельсов новой оболочки (орбита в центре).
RAIL_LEFT = 212
RAIL_RIGHT = 252

# Минимальный размер окна — по фактической вёрстке: два рельса (212 + 252)
# и колонки модуля очистки (380 + 330). Нужен и для изменения размера за
# край окна (см. _resize_to): спросить minsize() у CustomTkinter нельзя —
# его метод принимает только аргументы и не умеет возвращать значение.
MIN_WIDTH = 1260
MIN_HEIGHT = 700

# Порядок узлов на орбите: совпадает с порядком панелей модулей.
MODULE_KEYS = ("clean", "install", "optimize", "schedule", "log", "winsxs")

MAX_LOG_LINES = 3000
# Сколько строк списка пакетов реально создаётся в интерфейсе.
MAX_RESULT_ROWS = 120


# =============================================================================
# НАСТРОЙКИ (реестр Windows: HKEY_CURRENT_USER\Software\Swept)
# =============================================================================
# Вся работа с хранилищем — в cleaner_settings. Здесь только короткие обёртки,
# чтобы интерфейс не знал, реестр это или запасной JSON-файл.

def _load_saved_language() -> str:
    """Язык из реестра ('ru', если записи ещё нет)."""
    try:
        return settings.load_language()
    except Exception:
        return "ru"


def _save_language(code: str) -> None:
    """Сразу записывает выбранный язык в реестр (ошибка не критична)."""
    try:
        settings.save_language(code)
    except Exception:
        pass


def _resource_path(name: str) -> str | None:
    """Путь к файлу, положенному рядом с программой.

    В собранном exe файлы лежат во временной папке PyInstaller (sys._MEIPASS),
    при запуске из исходников — в папке проекта. Возвращает None, если файла
    нет: иконка окна — украшение, а не условие запуска.
    """
    bases = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        bases.append(bundle)
    bases.append(os.path.dirname(os.path.abspath(__file__)))
    for base in bases:
        path = os.path.join(base, name)
        if os.path.isfile(path):
            return path
    return None


# =============================================================================
# ОКНО БЕЗ СИСТЕМНОГО ЗАГОЛОВКА
# =============================================================================
# Ширина полосы у края окна, за которую тянется размер (px). У окна без рамки
# системных граней нет, поэтому край ловится вручную.
EDGE_GRIP = 6

# Курсор Windows для каждой грани и каждого угла окна.
EDGE_CURSORS = {
    "n": "size_ns", "s": "size_ns",
    "w": "size_we", "e": "size_we",
    "nw": "size_nw_se", "se": "size_nw_se",
    "ne": "size_ne_sw", "sw": "size_ne_sw",
}


def _work_area() -> tuple[int, int, int, int] | None:
    """Рабочая область основного экрана без панели задач.

    Нужна для разворота окна: разворачивать на весь экран нельзя — окно
    заехало бы под панель задач. Если Win32 недоступен, возвращаем None,
    и вызывающий код берёт размеры экрана целиком.
    """
    try:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        spi_getworkarea = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(
                spi_getworkarea, 0, ctypes.byref(rect), 0):
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width > 200 and height > 200:
                return rect.left, rect.top, width, height
    except Exception:
        pass
    return None


def _window_hwnd(window) -> int:
    """HWND верхнего уровня окна Tk (0, если получить не удалось)."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        return int(hwnd or window.winfo_id())
    except Exception:
        return 0


# Окно выбора набора: сколько строк списка показываем до появления прокрутки,
# и примерная высота одной строки (имя + ID пакета).
MAX_VISIBLE_ROWS = 7
ROW_H = 46

# Отступы в окне выбора набора. Высота окна считается по ним, поэтому
# менять нужно здесь, а не в самой вёрстке.
PAD_WRAP = 12           # рама окна от краёв
PAD_TITLE = (12, 2)     # заголовок набора
PAD_HINT = (0, 8)       # подсказка под заголовком
PAD_LIST = (0, 8)       # список пакетов
PAD_BUTTONS = (0, 12)   # ряд кнопок внизу


class PresetDialog(ctk.CTkToplevel):
    """Окно выбора программ из набора популярных приложений.

    Набор — это лишь подсказка: в окне показаны все его пакеты с галочками,
    и пользователь сам решает, что установить. Результат работы окна —
    список ``(название, ID пакета)`` в поле ``result``; если окно закрыли
    без выбора, там остаётся ``None``.
    """

    def __init__(self, master, preset: dict):
        super().__init__(master)

        self.preset = preset
        self.result = None
        self._rows = []          # [(название, ID пакета, BooleanVar), ...]

        self.title(i18n.t("presets.dialog_title", i18n.fld(preset, "title")))
        # Ширина 600: ряд кнопок (≈522 px) не должен вылезать за край.
        # Высоту считаем по реальному содержимому в _fit_size().
        self.geometry("600x520")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)
        # Окно модальное относительно главного: transient + grab_set ниже.
        self.transient(master)

        wrap = ctk.CTkFrame(self, fg_color=COLOR_CARD_2, corner_radius=12)
        wrap.pack(fill="both", expand=True, padx=PAD_WRAP, pady=PAD_WRAP)

        ctk.CTkLabel(wrap, text=i18n.fld(preset, "title"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT, anchor="w", height=22
                     ).pack(fill="x", padx=14, pady=PAD_TITLE)
        ctk.CTkLabel(wrap, text=i18n.t("presets.dialog_hint"),
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                     justify="left", anchor="w", wraplength=500, height=16
                     ).pack(fill="x", padx=14, pady=PAD_HINT)

        # Ряд кнопок упаковываем ПЕРВЫМ и снизу: так он забирает своё
        # место до того, как список попросит пространство, и не исчезает
        # даже в самом коротком наборе.
        buttons = ctk.CTkFrame(wrap, fg_color="transparent")
        buttons.pack(fill="x", side="bottom", padx=14, pady=PAD_BUTTONS)

        ctk.CTkButton(buttons, text=i18n.t("presets.select_all"),
                      width=130, height=30, fg_color=COLOR_CARD,
                      hover_color=COLOR_ACCENT,
                      command=lambda: self._set_all(True)).pack(side="left")
        ctk.CTkButton(buttons, text=i18n.t("presets.select_none"),
                      width=110, height=30, fg_color=COLOR_CARD,
                      hover_color=COLOR_ACCENT,
                      command=lambda: self._set_all(False)).pack(side="left", padx=6)

        self.install_btn = ctk.CTkButton(
            buttons, text=i18n.t("presets.install_selected", len(preset["packages"])),
            width=170, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            command=self._accept)
        self.install_btn.pack(side="right")
        ctk.CTkButton(buttons, text=i18n.t("presets.close"), width=100, height=30,
                      fg_color=COLOR_CARD, hover_color=COLOR_RED,
                      command=self.destroy).pack(side="right", padx=6)

        # Список пакетов. У CTkScrollableFrame минимальная высота около
        # 220 px — её задаёт полоса прокрутки, — поэтому короткий список
        # рисуем в обычной рамке: она обжимается по содержимому, без
        # пустого места и без лишней полосы прокрутки.
        total = len(preset["packages"])
        if total <= MAX_VISIBLE_ROWS:
            scroll = ctk.CTkFrame(wrap, fg_color=COLOR_BG, corner_radius=10)
        else:
            scroll = ctk.CTkScrollableFrame(
                wrap, height=MAX_VISIBLE_ROWS * ROW_H + 6,
                fg_color=COLOR_BG, corner_radius=10,
                scrollbar_button_color=COLOR_CARD_2,
                scrollbar_button_hover_color=COLOR_ACCENT)
        scroll.pack(fill="x", padx=14, pady=PAD_LIST)

        for name, pkg_id in preset["packages"]:
            var = tk.BooleanVar(value=True)
            self._rows.append((name, pkg_id, var))

            row = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=8)
            row.pack(fill="x", padx=2, pady=2)
            ctk.CTkCheckBox(
                row, text=name, variable=var, height=22,
                font=ctk.CTkFont(size=12), text_color=COLOR_TEXT,
                fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                checkbox_width=18, checkbox_height=18,
                command=self._refresh_count).pack(anchor="w", padx=10, pady=(4, 0))
            ctk.CTkLabel(row, text=pkg_id, font=ctk.CTkFont(size=10),
                         text_color=COLOR_MUTED, anchor="w", height=14
                         ).pack(anchor="w", padx=36, pady=(0, 4))

        self._refresh_count()
        self._fit_size()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda event: self.destroy())
        self.after(60, self._center_and_focus)

    def _fit_size(self):
        """Подгоняет высоту окна под реальное содержимое.

        Высота считается не по формуле, а по фактическим размерам
        виджетов: так окно всегда точно вмещает шапку, список и ряд
        кнопок — ничего не обрезается и ничего не болтается. Нижняя
        граница — только страховка на случай пустого списка.
        """
        self.update_idletasks()
        content = max(self.winfo_reqheight(), 1)
        height = max(220, min(content, 780))
        self.geometry("600x{}".format(height))

    # ---------------------------------------------------------- вспомогательное
    def _set_all(self, value: bool):
        """Ставит или снимает все галочки сразу."""
        for _, _, var in self._rows:
            var.set(value)
        self._refresh_count()

    def _selected(self) -> list:
        return [(name, pkg_id) for name, pkg_id, var in self._rows if var.get()]

    def _refresh_count(self):
        """Обновляет подпись кнопки установки: «Установить (3)»."""
        count = len(self._selected())
        self.install_btn.configure(
            text=i18n.t("presets.install_selected", count),
            state="normal" if count else "disabled")

    def _accept(self):
        """Запоминает выбор и закрывает окно."""
        packages = self._selected()
        if not packages:
            messagebox.showinfo(i18n.t("presets.title"),
                                i18n.t("presets.nothing_selected"))
            return
        self.result = packages
        self.destroy()

    def _center_and_focus(self):
        """Ставит окно по центру главного окна и забирает фокус."""
        try:
            self.update_idletasks()
            width, height = self.winfo_width(), self.winfo_height()
            x = self.master.winfo_rootx() + max(
                0, (self.master.winfo_width() - width) // 2)
            y = self.master.winfo_rooty() + max(
                0, (self.master.winfo_height() - height) // 3)
            self.geometry(f"+{x}+{y}")
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            # Главное окно могло закрыться — окно выбора просто убираем.
            pass


class CleanerApp(ctk.CTk):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Язык берём из реестра (HKEY_CURRENT_USER\Software\Swept\Language);
        # если записи нет — русский.
        i18n.set_language(_load_saved_language())

        self.title(i18n.t("app.title"))
        # Оболочка Orbit: два рельса и орбита между ними. Ширина подобрана так,
        # чтобы панель очистки (380 px категорий + управление) не сжималась.
        self.geometry("1360x820")
        # Минимальная ширина — по фактической вёрстке: два рельса (212 + 252)
        # и колонки модуля очистки (380 + 330). При 1180 правый рельс обрезался.
        self.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.configure(fg_color=COLOR_BG)
        self._apply_window_icon()

        # --- Обрамление окна (своя шапка вместо системного заголовка) ---
        self._frameless = True        # системный заголовок отключён
        self._maximized = False       # окно развёрнуто на рабочий стол
        self._restore_geom = None     # геометрия до разворота
        self._drag_offset = None      # смещение курсора при перетаскивании
        self._resize_edge = None      # активная грань при изменении размера
        self._resize_start = None     # геометрия на момент начала тяги за край
        self._frame_cursor = ""       # текущий курсор края окна
        self._max_btn = None          # кнопка «развернуть/восстановить»
        self._setup_frameless()

        # --- Состояние ---
        self.vars = {}
        self.browser_opt = {}          # {ключ_браузера: {подопция: BooleanVar}}
        self._browser_opt_frames = {}  # {ключ_браузера: под-панель под-опций}
        self._browser_opt_rows = {}    # {ключ_браузера: строка (для pack after=)}
        self._group_cards = {}         # {группа: карточка свёрнутого блока}
        self._group_buttons = {}       # {группа: (кнопка, заголовок, число)}
        self._group_expanded = {}      # {группа: раскрыта ли}
        self.scan_results = {}
        # Режим «только сканирование» живёт дольше одного построения панели:
        # модуль очистки создаётся лениво, а флаг нужен и до его открытия.
        self.scan_only_var = tk.BooleanVar(value=False)
        self.running = False
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.total_freed = 0
        self.installer_results = []   # результаты поиска установщика
        self.selected_pkg = None      # выбранный пакет для установки
        self.pkg_rows = []            # виджеты строк списка пакетов
        self.pkg_cells = []           # текстовые ячейки каждой строки
        self.selected_row = None      # индекс подсвеченной строки
        self._info_widgets = {}       # виджеты-подписи категорий (key -> label)
        self.pkg_header = None        # шапка таблицы пакетов (вне списка строк)
        self.installer_available = None  # None/True/False — готовность установщика (права админа)
        self.opt_vars = {}            # чек-боксы вкладки «Оптимизация»
        self.opt_os_label = None      # подпись про версию Windows
        # Разбор «почему тормозит»: последний отчёт, балл до применения
        # оптимизаций и флаг «идёт измерение». Отчёт переживает смену языка,
        # чтобы карточка не пустела при перерисовке интерфейса.
        self._diag_report = None
        self._diag_baseline = None
        self._diag_busy = False
        self._closing = False         # флаг закрытия окна
        self._admin_ok = None         # кэш проверки прав администратора
        self._admin_warned = False    # предупреждение показано только один раз
        self._tab_index = 0           # активная вкладка (для смены языка)
        self.log_box = None           # поле журнала (строится лениво)
        self._log_backlog = []        # строки, накопленные до его открытия
        self._lang_switch = None      # выпадающий список языков
        self._lang_label = None       # подпись «Язык» рядом со списком
        self._total_text = None       # текст «Освобождено…» с учётом режима
        self.winsxs_report = None     # последний отчёт DISM по хранилищу компонентов
        self.winsxs_busy = False      # идёт проверка/очистка WinSxS
        self.winsxs_cleaning = False  # идёт именно очистка (её нельзя прервать)
        self.winsxs_state = None      # подпись «Надо чистить: Да/Нет»
        self.winsxs_detail = None     # размеры и дата последней очистки
        self.winsxs_check_btn = None
        self.winsxs_clean_btn = None
        self.winsxs_progress = None

        # --- Состояние оболочки Orbit ---
        self._current_module = None   # None — открыта орбита, иначе номер модуля
        self._module_frames = []      # панели модулей внутри сцены (None — ещё не построена)
        self._module_builders = []    # строители панелей, в порядке MODULE_KEYS
        self._node_hits = []          # (x, y, r, index) для кликов по орбите
        self._orbit_progress = 0.0    # дуга прогресса вокруг ядра
        self._core_scheduled = False  # перерисовка центра уже запланирована
        self._hover_node = None       # узел орбиты под курсором (для подсветки)
        # Плавный прогресс: цель и текущее (анимированное) значение.
        self._progress_target = 0.0
        self._progress_shown = 0.0
        self._progress_anim_running = False
        self._feed_lines = deque(maxlen=7)   # короткая лента в правом рельсе
        self._feed_scheduled = False
        self._rail = {}

        # --- Состояние планировщика «тихой очистки по расписанию» ---
        self.schedule_stop_event = threading.Event()
        self.schedule_reschedule = threading.Event()
        self._scheduler_thread = None
        self.sched_vars = {}          # категории для плановой очистки (key -> BooleanVar)
        self.sched_status_label = None
        self.sched_enable_var = None
        self.sched_freq_var = None
        self.sched_weekday_var = None
        self.sched_weekday_menu = None
        self.sched_hour_var = None
        self.sched_minute_var = None
        self.sched_restore_var = None
        self.sched_dry_var = None
        self._freq_by_label = {}
        self._weekday_labels = []
        self._weekday_by_label = {}

        # --- Построение интерфейса ---
        self._build_shell()
        self._center_window()

        self.after(100, self._poll_queue)
        self.after(300, self._check_admin_warning)

        # При закрытии окна останавливаем фоновые операции и завершаем работу.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Если расписание тихой очистки включено — запускаем фоновый планировщик.
        if self._schedule_enabled():
            self._maybe_start_scheduler()

    # ============================================================== ИКОНКА
    def _apply_window_icon(self) -> None:
        """Ставит иконку окна из PNG-логотипа программы.

        Tk на Windows не читает .ico через ``tk.PhotoImage`` и игнорирует
        ``wm_iconbitmap``, поэтому используем ``iconphoto`` с PNG. Файл
        ищем рядом с программой и во временной папке собранного exe
        (``_resource_path``). Иконка — украшение; при её отсутствии просто
        ничего не делаем, запуск от этого не зависит.
        """
        # 1) .ico — самый надёжный путь для заголовка и панели задач Windows.
        ico = _resource_path("app.ico")
        if ico:
            try:
                self.iconbitmap(ico)
            except Exception:
                pass
        # 2) PNG-логотип через iconphoto. Ссылку на PhotoImage ОБЯЗАТЕЛЬНО
        # храним в атрибуте: иначе Python соберёт объект сборщиком мусора,
        # Tcl-образ исчезнет и Windows вернёт стандартную иконку Tk (синий
        # «лист») — именно это и было видно в заголовке окна.
        path = _resource_path(os.path.join("assets", "swept-logo.png"))
        if not path:
            return
        try:
            self._window_icon = tk.PhotoImage(file=path)
            self.iconphoto(True, self._window_icon)
        except Exception:
            pass

    # ==================================================== РАМКА ОКНА
    def _setup_frameless(self) -> None:
        """Убирает системный заголовок и включает свою шапку.

        У окна без рамки нет ни заголовка, ни граней, поэтому всё, что
        Windows делала сама, берём на себя: перетаскивание за шапку, кнопки
        свернуть/развернуть/закрыть (см. ``_build_header``) и изменение
        размера за край окна.
        """
        if not self._frameless:
            return
        try:
            self.overrideredirect(True)
        except tk.TclError:
            # Окно уже отображено и сменить режим нельзя — остаёмся с
            # системным заголовком: интерфейс от этого не ломается.
            self._frameless = False
            return
        self._apply_taskbar_style()
        # Движение мыши ловим на всём окне: дочерние виджеты наследуют
        # bindtag окна, поэтому обработчик видит и края, и содержимое.
        self.bind("<Motion>", self._on_frame_motion, add="+")
        self.bind("<ButtonPress-1>", self._on_frame_press, add="+")
        self.bind("<B1-Motion>", self._on_frame_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_frame_release, add="+")

    def _apply_taskbar_style(self) -> None:
        """Возвращает окну кнопку в панели задач и запись в Alt+Tab.

        Окно с ``overrideredirect`` Tk создаёт как tool-window (WS_EX_TOOLWINDOW):
        у него нет ни кнопки на панели задач, ни Alt+Tab. Флаг WS_EX_APPWINDOW
        это исправляет — окно остаётся без заголовка, но ведёт себя как
        обычное приложение.
        """
        hwnd = _window_hwnd(self)
        if not hwnd:
            return
        try:
            import ctypes
            gwl_exstyle = -20
            ws_ex_appwindow = 0x00040000
            ws_ex_toolwindow = 0x00000080
            style = ctypes.windll.user32.GetWindowLongW(hwnd, gwl_exstyle)
            style = (style | ws_ex_appwindow) & ~ws_ex_toolwindow
            ctypes.windll.user32.SetWindowLongW(hwnd, gwl_exstyle, style)
        except Exception:
            pass

    # ------------------------------------------------------------ грань окна
    def _edge_at(self, x_root: int, y_root: int):
        """Грань или угол окна под курсором (None — курсор внутри окна)."""
        x, y = self.winfo_rootx(), self.winfo_rooty()
        width, height = self.winfo_width(), self.winfo_height()
        left = x_root - x <= EDGE_GRIP
        right = x + width - x_root <= EDGE_GRIP
        top = y_root - y <= EDGE_GRIP
        bottom = y + height - y_root <= EDGE_GRIP
        vertical = "n" if top else ("s" if bottom else "")
        horizontal = "w" if left else ("e" if right else "")
        return (vertical + horizontal) or None

    def _on_frame_motion(self, event):
        """Подсказывает курсором, за какую грань сейчас можно тянуть."""
        if not self._frameless or self._maximized:
            return
        if self._drag_offset or self._resize_edge:
            return
        edge = self._edge_at(event.x_root, event.y_root)
        cursor = EDGE_CURSORS.get(edge, "")
        if cursor == self._frame_cursor:
            return
        self._frame_cursor = cursor
        try:
            self.configure(cursor=cursor)
        except Exception:
            self._frame_cursor = ""

    def _on_frame_press(self, event):
        """Начало тяги за край окна (изменение размера)."""
        if not self._frameless or self._maximized:
            return
        if self._drag_offset:
            return                       # уже тянем окно за шапку
        edge = self._edge_at(event.x_root, event.y_root)
        if not edge:
            return
        self._resize_edge = edge
        self._resize_start = (event.x_root, event.y_root,
                              self.winfo_x(), self.winfo_y(),
                              self.winfo_width(), self.winfo_height())

    def _on_frame_drag(self, event):
        if self._resize_edge:
            self._resize_to(event)
        elif self._drag_offset:
            self._move_to(event)

    def _on_frame_release(self, _event=None):
        self._resize_edge = None
        self._resize_start = None
        self._drag_offset = None

    def _move_to(self, event) -> None:
        """Двигает окно так, чтобы точка захвата осталась под курсором."""
        if not self._drag_offset or self._maximized:
            # Развёрнутое окно не двигаем: двойной клик по шапке успевает
            # начать перетаскивание и тут же разворачивает окно.
            return
        dx, dy = self._drag_offset
        self.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")

    def _resize_to(self, event) -> None:
        """Тянет ту грань, за которую взялись; противоположная на месте."""
        if not self._resize_start or not self._resize_edge:
            return
        x0, y0, win_x, win_y, win_w, win_h = self._resize_start
        dx = event.x_root - x0
        dy = event.y_root - y0
        min_w, min_h = MIN_WIDTH, MIN_HEIGHT
        left, top = win_x, win_y
        right, bottom = win_x + win_w, win_y + win_h
        if "w" in self._resize_edge:
            left = min(win_x + dx, right - min_w)
        elif "e" in self._resize_edge:
            right = max(win_x + win_w + dx, left + min_w)
        if "n" in self._resize_edge:
            top = min(win_y + dy, bottom - min_h)
        elif "s" in self._resize_edge:
            bottom = max(win_y + win_h + dy, top + min_h)
        self.geometry(f"{right - left}x{bottom - top}+{left}+{top}")

    # ------------------------------------------------- перетаскивание за шапку
    def _bind_header_drag(self, widget) -> None:
        """Вешает перетаскивание окна на элемент шапки.

        Шапка состоит из нескольких виджетов, поэтому обработчики вешаются
        на каждый: клик по названию или знаку должен двигать окно так же,
        как клик по пустому месту.
        """
        widget.bind("<ButtonPress-1>", self._on_header_press, add="+")
        widget.bind("<B1-Motion>", self._on_header_drag, add="+")
        widget.bind("<ButtonRelease-1>", self._on_frame_release, add="+")
        widget.bind("<Double-Button-1>",
                    lambda _e: self._toggle_maximize(), add="+")

    def _on_header_press(self, event):
        if not self._frameless or self._maximized:
            return
        if self._edge_at(event.x_root, event.y_root):
            return                       # это тяга за край, а не перенос
        self._drag_offset = (event.x_root - self.winfo_x(),
                             event.y_root - self.winfo_y())

    def _on_header_drag(self, event):
        if self._drag_offset:
            self._move_to(event)

    # ------------------------------------------ свернуть / развернуть / закрыть
    def _center_window(self) -> None:
        """Ставит окно по центру рабочей области при запуске.

        Окно без рамки Windows ставит «каскадом» к верхнему левому углу —
        выглядит случайно. Центр рабочей области (без панели задач) читается
        лучше и всегда гарантирует, что шапка на экране.
        """
        area = _work_area()
        if area:
            area_x, area_y, area_w, area_h = area
        else:
            area_x = area_y = 0
            area_w, area_h = self.winfo_screenwidth(), self.winfo_screenheight()
        try:
            width, height = (int(v) for v in self.geometry().split("+")[0].split("x"))
        except Exception:
            width, height = MIN_WIDTH, MIN_HEIGHT
        x = area_x + max(0, (area_w - width) // 2)
        y = area_y + max(0, (area_h - height) // 2)
        self.geometry(f"+{x}+{y}")

    def _minimize_window(self) -> None:
        """Сворачивает окно в панель задач.

        ``iconify()`` у окна с ``overrideredirect`` падает с TclError
        («override-redirect flag is set»), поэтому просим об этом Windows
        напрямую: сворачивание и восстановление из панели задач работают
        как у обычного окна, геометрия сохраняется.
        """
        hwnd = _window_hwnd(self)
        if hwnd:
            try:
                import ctypes
                ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                return
            except Exception:
                pass
        try:
            self.iconify()
        except tk.TclError:
            pass

    def _toggle_maximize(self) -> None:
        if self._maximized:
            self._restore_window()
        else:
            self._maximize_window()

    def _maximize_window(self) -> None:
        """Разворачивает окно на рабочую область (без панели задач)."""
        if self._maximized:
            return
        self._restore_geom = (self.winfo_x(), self.winfo_y(),
                              self.winfo_width(), self.winfo_height())
        area = _work_area()
        if area:
            x, y, width, height = area
        else:
            x = y = 0
            width, height = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{width}x{height}+{x}+{y}")
        self._maximized = True
        self._sync_max_button()

    def _restore_window(self) -> None:
        """Возвращает окно к размеру и месту до разворота."""
        if not self._maximized:
            return
        self._maximized = False
        if self._restore_geom:
            x, y, width, height = self._restore_geom
            self.geometry(f"{width}x{height}+{x}+{y}")
        self._sync_max_button()

    def _sync_max_button(self) -> None:
        """Перерисовывает значок кнопки: «развернуть» или «восстановить»."""
        if self._max_btn is None:
            return
        try:
            self._max_btn.configure(text="❐" if self._maximized else "□")
        except Exception:
            pass

    # ============================================================== ШАПКА
    def _build_header(self):
        """Своя шапка окна: знак, название, язык и кнопки управления.

        Системного заголовка у окна нет (``_setup_frameless``), поэтому
        шапка — единственное место, где видно название программы и где окно
        можно перетащить. Кнопки справа повторяют поведение обычного окна.
        """
        header = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=0,
                              height=52)
        header.pack(fill="x")
        header.pack_propagate(False)
        self._bind_header_drag(header)

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=(14, 0), pady=11)
        self._bind_header_drag(left)

        mark = tk.Canvas(left, width=26, height=26, bg=COLOR_CARD,
                         highlightthickness=0)
        mark.pack(side="left", padx=(0, 10))
        # Знак бренда: «S» мятного цвета в фиолетовом орбитальном кольце —
        # ровно то, что на иконке программы.
        mark.create_oval(1, 1, 25, 25, outline=COLOR_VIOLET, width=2)
        mark.create_text(13, 13, text="S", fill=COLOR_MINT,
                         font=("Segoe UI", 15, "bold"))
        self._bind_header_drag(mark)

        name = ctk.CTkLabel(left, text=i18n.t("app.name"),
                            font=ctk.CTkFont(size=15, weight="bold"),
                            text_color=COLOR_TEXT)
        name.pack(side="left")
        self._bind_header_drag(name)

        version = ctk.CTkLabel(left, text=i18n.t("app.version"),
                               font=ctk.CTkFont(size=10, weight="bold"),
                               text_color=COLOR_MINT, fg_color=COLOR_CARD_2,
                               corner_radius=8, width=52, height=20)
        version.pack(side="left", padx=(10, 0))
        self._bind_header_drag(version)

        # Кнопки окна — у самого правого края, как в обычном окне Windows.
        close_btn = self._window_button(header, "✕", self._on_close,
                                        hover=COLOR_RED, text_color=COLOR_TEXT)
        close_btn.pack(side="right", padx=(0, 10), pady=11)
        self._max_btn = self._window_button(header, "□", self._toggle_maximize)
        self._max_btn.pack(side="right", padx=(0, 2), pady=11)
        self._window_button(header, "—", self._minimize_window).pack(
            side="right", padx=(0, 2), pady=11)
        self._sync_max_button()

        self.admin_label = ctk.CTkLabel(header, text="",
                                        font=ctk.CTkFont(size=10, weight="bold"),
                                        fg_color=COLOR_CARD_2, corner_radius=8,
                                        width=86, height=22)
        self.admin_label.pack(side="right", padx=(0, 14))
        # Без прав эта плашка — кнопка перезапуска с повышением: молча
        # работать «наполовину» хуже, чем одним кликом получить права.
        self.admin_label.bind("<Button-1>", lambda _e: self._on_admin_chip())
        self._refresh_admin_label()

        # Выпадающий список языка интерфейса (Русский / English).
        # Названия пишутся эндонимами, поэтому список не «перескакивает»
        # при смене языка; выбранное значение сразу уходит в реестр.
        self._lang_label = ctk.CTkLabel(header, text=i18n.t("lang.label"),
                                        font=ctk.CTkFont(size=11),
                                        text_color=COLOR_MUTED)
        self._lang_switch = ctk.CTkComboBox(
            header,
            values=i18n.language_values(),
            command=self._on_language_change,
            height=28, width=140, font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=12),
            state="readonly",
            fg_color=COLOR_CARD_2, border_color=COLOR_LINE,
            button_color=COLOR_CARD_2, button_hover_color=COLOR_ACCENT,
            dropdown_fg_color=COLOR_CARD_2, dropdown_hover_color=COLOR_ACCENT,
            dropdown_text_color=COLOR_TEXT, text_color=COLOR_TEXT)
        # Порядок упаковки: сначала список (он у самого края), затем подпись слева.
        self._lang_switch.pack(side="right", padx=(0, 8))
        self._lang_label.pack(side="right", padx=(0, 6))
        self._sync_lang_switch()

        # Тонкая линия под шапкой: ею окно отделено от содержимого — иначе
        # шапка и фон сливаются в одно тёмное поле.
        ctk.CTkFrame(self, fg_color=COLOR_LINE, height=1,
                     corner_radius=0).pack(fill="x")

    def _window_button(self, parent, glyph: str, command,
                       hover: str = COLOR_CARD_2,
                       text_color: str = COLOR_MUTED):
        """Кнопка управления окном в шапке (свернуть/развернуть/закрыть)."""
        return ctk.CTkButton(
            parent, text=glyph, width=40, height=30, corner_radius=8,
            fg_color="transparent", hover_color=hover,
            text_color=text_color,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=command)

    # ------------------------------------------------------ смена языка
    def _sync_lang_switch(self):
        """Приводит список языков в соответствие с текущим языком."""
        if self._lang_switch is None:
            return
        try:
            self._lang_switch.set(i18n.language_name())
        except Exception:
            pass

    def _on_language_change(self, name: str):
        """Обработчик списка: 'Русский' / 'English' -> код языка."""
        code = i18n.language_code(name)
        if not code:
            self._sync_lang_switch()
            return
        self._apply_language(code)

    def _refresh_admin_label(self):
        """Показывает права администратора на текущем языке (если уже известны)."""
        if self.admin_label is None:
            return
        if self._admin_ok is None:
            self.admin_label.configure(text="")
        elif self._admin_ok:
            self.admin_label.configure(text=i18n.t("admin.chip_yes"),
                                       text_color=COLOR_GREEN)
        else:
            self.admin_label.configure(text=i18n.t("admin.chip_no"),
                                       text_color=COLOR_RED)

    def _apply_language(self, code: str):
        """
        Переключает язык: сохраняет состояние, перерисовывает окно
        и восстанавливает данные (галочки, журнал, результаты поиска).
        """
        if code == i18n.get_language() or self.running:
            self._sync_lang_switch()
            return
        state = self._capture_ui_state()
        i18n.set_language(code)
        _save_language(code)
        self._rebuild_ui(state)

    def _capture_ui_state(self) -> dict:
        """Снимок состояния интерфейса перед перерисовкой."""
        state = {
            "vars": {key: var.get() for key, var in self.vars.items()},
            "opt_vars": {key: var.get() for key, var in self.opt_vars.items()},
            "scan_only": self.scan_only_var.get(),
            "tab_index": self._tab_index,
            "module_open": self._current_module is not None,
            "results": list(self.installer_results),
            "selected_row": self.selected_row,
            "total_freed": self.total_freed,
            "total_text": self._total_text,
            "installer": self.installer_available,
            "query": "",
            "pkg_text": "",
            "log": self._log_text(),
        }
        try:
            state["query"] = self.search_entry.get()
            state["pkg_text"] = self.pkg_entry.get()
        except Exception:
            pass
        return state

    def _rebuild_ui(self, state: dict):
        """Удаляет все виджеты и строит интерфейс заново на новом языке."""
        # Какие панели пользователь уже открывал — их и восстановим, чтобы
        # после смены языка не пришлось открывать модуль заново.
        built_before = [k for k in range(len(self._module_frames))
                        if self._module_built(k)]
        for child in self.winfo_children():
            child.destroy()

        self.vars = {}
        self.browser_opt = {}
        self._browser_opt_frames = {}
        self._browser_opt_rows = {}
        self._group_cards = {}
        self._group_buttons = {}
        self._group_expanded = {}
        self.opt_vars = {}
        self._info_widgets = {}
        self.pkg_rows = []
        self.pkg_cells = []
        self.pkg_header = None
        self._lang_switch = None
        self._lang_label = None
        # Кнопка разворота пересоздаётся вместе с шапкой.
        self._max_btn = None
        self.opt_os_label = None
        self.opt_live = None
        self.opt_rows = {}
        self._opt_live_visible = False
        # Виджеты блока WinSxS пересоздаются вместе с модулем WinSxS.
        self.winsxs_state = None
        self.winsxs_detail = None
        self.winsxs_check_btn = None
        self.winsxs_clean_btn = None
        self.winsxs_progress = None
        self._rail = {}
        self.feed_labels = []
        self._feed_scheduled = False
        self._core_scheduled = False
        # Панель журнала пересоздаётся вместе с модулем; накопленные строки
        # остаются в _log_backlog и вставятся при её сборке.
        self.log_box = None
        # Список крупнейших категорий пересоздаётся вместе с модулем очистки.
        self.top_box = None
        self.top_rows = []
        self.top_empty = None
        self.top_header = None

        self.title(i18n.t("app.title"))
        self._build_shell()

        # Панели строятся лениво, поэтому перед восстановлением состояния
        # собираем те модули, чьи виджеты сейчас понадобятся: уже открывавшиеся
        # и те, чьё состояние нужно вернуть (список, выбор, галочки).
        for index in built_before:
            self._ensure_module(index)
        if state["vars"] or state["total_text"]:
            self._ensure_module(0)
        if state["query"] or state["pkg_text"] or state["results"]:
            self._ensure_module(1)
        if state["opt_vars"]:
            self._ensure_module(2)

        # Восстанавливаем состояние.
        for key, value in state["vars"].items():
            if key in self.vars:
                self.vars[key].set(value)
        for key, value in state["opt_vars"].items():
            if key in self.opt_vars:
                self.opt_vars[key].set(value)
        self.scan_only_var.set(state["scan_only"])
        self.total_freed = state["total_freed"]
        self._total_text = state["total_text"]
        self._apply_total_text()

        # Журнал переносим в накопитель: он вставится при первом открытии
        # панели (или сразу, если панель уже построена ниже).
        if state["log"]:
            self._log_backlog = state["log"].splitlines()

        if state["query"]:
            self.search_entry.insert(0, state["query"])
        if state["results"]:
            self._show_installer_results(state["results"])
            if state["selected_row"] is not None:
                self.select_package(state["selected_row"])
        if state["pkg_text"]:
            self.pkg_entry.delete(0, "end")
            self.pkg_entry.insert(0, state["pkg_text"])

        # Возвращаемся к тому же модулю (или остаёмся на орбите).
        try:
            index = int(state.get("tab_index") or 0)
            if not (0 <= index < len(self._module_frames)):
                index = 0
            self._tab_index = index
            if state.get("module_open"):
                self._select_module(index)
            else:
                self._show_orbit()
        except Exception:
            pass

        self._apply_installer_buttons(self.running)
        self._set_running(self.running)

    # ============================================================== ОБОЛОЧКА
    def _build_shell(self):
        """Каркас Orbit: шапка, два рельса с орбитой между ними, нижняя лента."""
        self._build_header()
        self._build_body()
        self._build_ribbon()
        self._show_orbit()
        self.bind("<Escape>", lambda _e: self._show_orbit())
        self._refresh_telemetry()
        self._render_top_categories()

    def _build_body(self):
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(12, 0))
        body.grid_columnconfigure(0, weight=0, minsize=RAIL_LEFT)
        body.grid_columnconfigure(1, weight=1)
        body.grid_columnconfigure(2, weight=0, minsize=RAIL_RIGHT)
        body.grid_rowconfigure(0, weight=1)
        self._build_left_rail(body)
        self._build_stage(body)
        self._build_right_rail(body)

    # ------------------------------------------------------------ левый рельс
    def _build_left_rail(self, parent):
        rail = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=14,
                            width=RAIL_LEFT)
        rail.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        rail.grid_propagate(False)

        ctk.CTkLabel(rail, text=i18n.t("rail.system").upper(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COLOR_MUTED).pack(anchor="w", padx=16, pady=(14, 12))

        self._rail["disk"] = self._rail_stat(rail, i18n.t("rail.disk"))
        self._rail["temp"] = self._rail_stat(rail, i18n.t("rail.temp"))
        self._rail["bin"] = self._rail_stat(rail, i18n.t("rail.bin"))

        ctk.CTkFrame(rail, fg_color=COLOR_LINE, height=1).pack(
            fill="x", padx=16, pady=(6, 10))

        self._rail["categories"] = self._rail_micro(rail, i18n.t("rail.categories"), "0")
        self._rail["files"] = self._rail_micro(rail, i18n.t("rail.files"), "0")
        self._rail["restore"] = self._rail_micro(rail, i18n.t("rail.restore"), "—")

        bottom = ctk.CTkFrame(rail, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=16, pady=14)
        ctk.CTkLabel(bottom, text=i18n.t("rail.total").upper(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COLOR_MUTED).pack(anchor="w")
        self._rail["total"] = ctk.CTkLabel(
            bottom, text=core.format_bytes(0),
            font=ctk.CTkFont(size=22, weight="bold"), text_color=COLOR_MINT)
        self._rail["total"].pack(anchor="w", pady=(2, 0))

    def _rail_stat(self, parent, title):
        """Строка телеметрии: подпись, значение и тонкая полоса."""
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(fill="x", padx=16, pady=(0, 12))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=title, font=ctk.CTkFont(size=11),
                     text_color=COLOR_MUTED).pack(side="left")
        value = ctk.CTkLabel(row, text="—", font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=COLOR_TEXT)
        value.pack(side="right")
        bar = ctk.CTkProgressBar(box, height=4, corner_radius=2,
                                 fg_color=COLOR_CARD_2, progress_color=COLOR_MINT)
        bar.set(0)
        bar.pack(fill="x", pady=(6, 0))
        return {"value": value, "bar": bar}

    def _rail_micro(self, parent, title, value):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=2)
        ctk.CTkLabel(row, text=title, font=ctk.CTkFont(size=11),
                     text_color=COLOR_MUTED).pack(side="left")
        val = ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=11, weight="bold"),
                           text_color=COLOR_TEXT)
        val.pack(side="right")
        return val

    def _refresh_telemetry(self):
        """Обновляет левый рельс по данным последнего сканирования."""
        rail = getattr(self, "_rail", None)
        if not rail:
            return
        try:
            drive = os.environ.get("SystemDrive", "C:") + "\\"
            usage = shutil.disk_usage(drive)
            share = usage.used / usage.total if usage.total else 0.0
            rail["disk"]["value"].configure(text="{}%".format(int(round(share * 100))))
            self._tween_bar(rail["disk"]["bar"], share)
        except Exception:
            pass

        temp_size = 0
        for key in ("temp_user", "temp_system"):
            temp_size += int((self.scan_results.get(key) or {}).get("total_size", 0))
        bin_size = int((self.scan_results.get("recycle") or {}).get("total_size", 0))
        files = sum(int((r or {}).get("total_count", 0))
                    for r in self.scan_results.values())

        for name, size in (("temp", temp_size), ("bin", bin_size)):
            if size:
                rail[name]["value"].configure(text=core.format_bytes(size))
                self._tween_bar(rail[name]["bar"], min(1.0, size / float(1024 ** 3)))
            else:
                rail[name]["value"].configure(text=core.format_bytes(0))
                self._tween_bar(rail[name]["bar"], 0)

        rail["categories"].configure(text=str(len(core.CATEGORIES)))
        rail["files"].configure(text="{:,}".format(files).replace(",", " "))
        rail["total"].configure(text=core.format_bytes(self.total_freed))

    # ------------------------------------------------------------- правый рельс
    def _build_right_rail(self, parent):
        rail = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=14,
                            width=RAIL_RIGHT)
        rail.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        rail.grid_propagate(False)

        head = ctk.CTkFrame(rail, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 10))
        ctk.CTkLabel(head, text=i18n.t("feed.title").upper(),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COLOR_MUTED).pack(side="left")
        self.feed_count = ctk.CTkLabel(head, text="0",
                                       font=ctk.CTkFont(size=10, weight="bold"),
                                       text_color=COLOR_MINT)
        self.feed_count.pack(side="right")

        self.feed_box = ctk.CTkFrame(rail, fg_color="transparent")
        self.feed_box.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        self.feed_labels = []
        for _ in range(7):
            lbl = ctk.CTkLabel(self.feed_box, text="", anchor="w", justify="left",
                               font=ctk.CTkFont(size=10), text_color=COLOR_MUTED,
                               wraplength=RAIL_RIGHT - 44)
            lbl.pack(fill="x", pady=2)
            self.feed_labels.append(lbl)
        self._render_feed()

    def _push_feed(self, line: str):
        """Кладёт строку в короткую ленту правого рельса (с ограничением частоты)."""
        if not line:
            return
        self._feed_lines.appendleft(line)
        if self._feed_scheduled:
            return
        self._feed_scheduled = True
        # Пакет строк приходит тысячами — перерисовываем ленту не чаще 8 раз/с.
        self.after(120, self._flush_feed)

    def _flush_feed(self):
        self._feed_scheduled = False
        self._render_feed()

    def _render_feed(self):
        labels = getattr(self, "feed_labels", None)
        if not labels:
            return
        lines = list(self._feed_lines)
        for i, lbl in enumerate(labels):
            text = lines[i] if i < len(lines) else ""
            lbl.configure(text=text, text_color=COLOR_TEXT if i == 0 else COLOR_MUTED)
        try:
            self.feed_count.configure(text=str(len(lines)))
        except Exception:
            pass

    # ------------------------------------------------------------------ сцена
    def _build_stage(self, parent):
        self.stage = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=14)
        self.stage.grid(row=0, column=1, sticky="nsew")
        self.stage.grid_rowconfigure(0, weight=1)
        self.stage.grid_columnconfigure(0, weight=1)

        self.orbit_view = ctk.CTkFrame(self.stage, fg_color="transparent")
        self.orbit_view.grid(row=0, column=0, sticky="nsew")
        self.orbit_canvas = tk.Canvas(self.orbit_view, bg=COLOR_CARD,
                                      highlightthickness=0, bd=0)
        self.orbit_canvas.pack(fill="both", expand=True)
        # Перерисовку при изменении размера пропускаем через тот же
        # планировщик: при перетаскивании края окна события идут потоком,
        # и рисовать на каждое — лишняя работа.
        self.orbit_canvas.bind("<Configure>", lambda _e: self._schedule_core_redraw())
        self.orbit_canvas.bind("<Button-1>", self._on_orbit_click)
        # Подсветка узла под курсором (плавная, через тот же планировщик).
        self.orbit_canvas.bind("<Motion>", self._on_orbit_motion)
        self.orbit_canvas.bind("<Leave>", lambda _e: self._set_hover_node(None))

        self.module_host = ctk.CTkFrame(self.stage, fg_color="transparent")
        self.module_host.grid(row=0, column=0, sticky="nsew")
        self.module_host.grid_rowconfigure(0, weight=1)
        self.module_host.grid_columnconfigure(0, weight=1)

        # Панели модулей строятся лениво: при старте создаётся только журнал
        # (в него пишется первая же строка про права). Остальные пять панелей
        # собираются при первом открытии — это ~1 секунда экономии на запуске.
        self._module_builders = [self._build_clean_tab, self._build_install_tab,
                                 self._build_optimize_tab, self._build_schedule_tab,
                                 self._build_log_tab, self._build_winsxs_tab]
        self._module_frames = [None] * len(self._module_builders)
        self.module_host.grid_remove()

    def _ensure_module(self, index: int):
        """Строит панель модуля при первом обращении и возвращает её."""
        if not (0 <= index < len(self._module_builders)):
            return None
        frame = self._module_frames[index]
        if frame is not None:
            return frame
        frame = ctk.CTkFrame(self.module_host, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        # Ссылку сохраняем до вызова строителя: он может обратиться к модулю
        # повторно (например, _build_winsxs_block перерисовывает отчёт).
        self._module_frames[index] = frame
        self._module_builders[index](frame)
        frame.grid_remove()
        return frame

    def _module_built(self, index: int) -> bool:
        """True, если панель модуля уже построена (панели создаются лениво)."""
        return (0 <= index < len(self._module_frames)
                and self._module_frames[index] is not None)

    # ------------------------------------------------------------- навигация
    def _select_module(self, index: int):
        """Открывает панель модуля вместо орбиты."""
        if not (0 <= index < len(self._module_frames)):
            return
        self._current_module = index
        self._tab_index = index
        # Панель собирается здесь же, при первом открытии.
        self._ensure_module(index)
        self.orbit_view.grid_remove()
        self.module_host.grid()
        for k, frame in enumerate(self._module_frames):
            if frame is None:
                continue
            if k == index:
                frame.grid()
                frame.tkraise()
                self._animate_module_in(frame, index)
            else:
                frame.grid_remove()
        try:
            self.ribbon_back.configure(state="normal")
        except Exception:
            pass
        self._update_ribbon()
        if index == 0:
            self.ribbon_actions.pack(side="right", padx=(0, 8), pady=10)
        else:
            self.ribbon_actions.pack_forget()

    def _show_orbit(self):
        """Возвращает сцену к орбите."""
        self._current_module = None
        try:
            self.module_host.grid_remove()
            self.orbit_view.grid()
            self.ribbon_back.configure(state="disabled")
            self.ribbon_actions.pack_forget()
        except Exception:
            pass
        self._update_ribbon()
        self._draw_orbit()

    def _animate_module_in(self, frame, index):
        """Короткий «въезд» панели снизу при открытии модуля (~110 мс).

        Анимируется только внешний отступ панели в сетке — это дешевле, чем
        пересобирать содержимое. Важно: grid_configure на скрытой панели снова
        её показывает, поэтому кадр прерывается, если модуль уже не текущий.
        """
        if self._closing:
            return
        try:
            frame.grid_configure(pady=(16, 0))
        except Exception:
            return
        steps = 5
        state = {"i": 0}

        def step():
            if self._closing or self._current_module != index:
                return
            try:
                if not frame.winfo_exists():
                    return
            except Exception:
                return
            state["i"] += 1
            frac = state["i"] / float(steps)
            offset = int(round(16 * (1 - frac)))
            try:
                frame.grid_configure(pady=(offset, 0))
            except Exception:
                return
            if state["i"] < steps:
                try:
                    self.after(22, step)
                except Exception:
                    pass

        self.after(22, step)

    def _update_ribbon(self):
        if self._current_module is None:
            self.ribbon_title.configure(text=i18n.t("app.name"))
            self.ribbon_sub.configure(text=i18n.t("orbit.pick"))
            return
        key = MODULE_KEYS[self._current_module]
        self.ribbon_title.configure(text=i18n.t("mod." + key))
        self.ribbon_sub.configure(text=i18n.t("mod." + key + ".sub"))

    # ---------------------------------------------------------------- орбита
    def _core_state(self):
        """Что показать в центре: подпись, значение, пояснение, подсказка."""
        files = sum(int((r or {}).get("total_count", 0))
                    for r in self.scan_results.values())
        size = sum(int((r or {}).get("total_size", 0))
                   for r in self.scan_results.values())
        if getattr(self, "running", False):
            return (i18n.t("orbit.busy"), "…", i18n.t("orbit.busy_sub"), "")
        if size > 0:
            return (i18n.t("orbit.reclaim"), core.format_bytes(size),
                    i18n.t("orbit.found").format(len(self.scan_results), files),
                    i18n.t("orbit.ready"))
        if self.scan_results:
            return (i18n.t("orbit.freed"), core.format_bytes(0),
                    i18n.t("orbit.done"), "")
        return (i18n.t("orbit.reclaim"), core.format_bytes(0),
                "", i18n.t("orbit.idle"))

    def _draw_orbit(self):
        canvas = getattr(self, "orbit_canvas", None)
        if canvas is None:
            return
        try:
            canvas.delete("all")
        except Exception:
            return
        self._node_hits = []
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 120 or height < 120:
            return

        cx, cy = width / 2.0, height / 2.0
        radius = min(width, height) * 0.315
        node_r = max(24.0, min(34.0, radius * 0.30))

        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius,
                           outline=COLOR_LINE, width=1)
        canvas.create_oval(cx - radius + 18, cy - radius + 18,
                           cx + radius - 18, cy + radius - 18,
                           outline=COLOR_CARD_2, width=1, dash=(3, 7))

        core_r = radius * 0.56
        canvas.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r,
                           fill=COLOR_CARD_2, outline=COLOR_LINE)

        if self._orbit_progress > 0.002:
            canvas.create_arc(cx - core_r - 6, cy - core_r - 6,
                              cx + core_r + 6, cy + core_r + 6,
                              start=90, extent=-359.9 * self._orbit_progress,
                              style="arc", outline=COLOR_MINT, width=3)

        label, value, sub, hint = self._core_state()
        canvas.create_text(cx, cy - core_r * 0.48, text=label.upper(),
                           fill=COLOR_MUTED, font=("Segoe UI", 8))
        canvas.create_text(cx, cy + 1, text=value, fill=COLOR_TEXT,
                           font=("Segoe UI", max(15, int(core_r * 0.36)), "bold"))
        canvas.create_text(cx, cy + core_r * 0.45, text=sub, fill=COLOR_MUTED,
                           font=("Segoe UI", 9), width=core_r * 1.7,
                           justify="center")
        if hint:
            canvas.create_text(cx, cy + core_r * 0.78, text=hint.upper(),
                               fill=COLOR_MINT, font=("Segoe UI", 7))

        for i, key in enumerate(MODULE_KEYS):
            angle = math.radians(-90 + i * 60)
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            selected = (i == self._current_module)
            hovered = (i == self._hover_node)
            # Лёгкое «раздувание» узла под курсором — живой отклик без лишних
            # кадров (перерисовка идёт через планировщик).
            r = node_r * (1.09 if hovered else 1.0)
            if selected:
                fill, outline, width = COLOR_ACCENT, COLOR_ACCENT, 2
            elif hovered:
                fill, outline, width = COLOR_CARD_2, COLOR_MINT, 2
            else:
                fill, outline, width = COLOR_CARD, COLOR_LINE, 1
            canvas.create_oval(x - r, y - r, x + r, y + r,
                               fill=fill, outline=outline, width=width)
            icon_color = (COLOR_BG if selected
                          else (COLOR_MINT if hovered else COLOR_MUTED))
            self._draw_node_icon(canvas, key, x, y, icon_color)
            label_color = COLOR_MINT if (selected or hovered) else COLOR_MUTED
            canvas.create_text(x, y + r + 12, text=i18n.t("mod." + key),
                               fill=label_color, font=("Segoe UI", 9))
            # Хит-зона — по базовому радиусу (стабильная, без «залипания»).
            self._node_hits.append((x, y, node_r, i))

    def _draw_node_icon(self, canvas, key: str, x: float, y: float, color: str):
        """Простые векторные иконки узлов — без шрифтовых символов."""
        if key == "clean":
            canvas.create_line(x - 7, y - 5, x + 7, y - 5, fill=color, width=2)
            canvas.create_line(x - 3, y - 8, x + 3, y - 8, fill=color, width=2)
            canvas.create_line(x - 5, y - 4, x - 4, y + 8, fill=color, width=2)
            canvas.create_line(x + 5, y - 4, x + 4, y + 8, fill=color, width=2)
            canvas.create_line(x - 4, y + 8, x + 4, y + 8, fill=color, width=2)
        elif key == "install":
            canvas.create_line(x, y - 9, x, y + 5, fill=color, width=2)
            canvas.create_line(x - 4, y + 1, x, y + 6, fill=color, width=2)
            canvas.create_line(x + 4, y + 1, x, y + 6, fill=color, width=2)
            canvas.create_line(x - 7, y + 9, x + 7, y + 9, fill=color, width=2)
        elif key == "optimize":
            canvas.create_polygon(x + 2, y - 10, x - 6, y + 1, x - 1, y + 1,
                                  x - 2, y + 10, x + 6, y - 2, x + 1, y - 2,
                                  fill=color, outline="")
        elif key == "schedule":
            canvas.create_oval(x - 8, y - 8, x + 8, y + 8, outline=color, width=2)
            canvas.create_line(x, y - 4, x, y, x + 4, y + 2, fill=color, width=2)
        elif key == "log":
            canvas.create_rectangle(x - 6, y - 9, x + 6, y + 9,
                                    outline=color, width=2)
            canvas.create_line(x - 3, y - 4, x + 3, y - 4, fill=color, width=1)
            canvas.create_line(x - 3, y, x + 3, y, fill=color, width=1)
            canvas.create_line(x - 3, y + 4, x + 1, y + 4, fill=color, width=1)
        elif key == "winsxs":
            canvas.create_polygon(x, y - 9, x + 8, y - 4, x, y + 1, x - 8, y - 4,
                                  outline=color, fill="", width=2)
            canvas.create_line(x - 8, y + 1, x, y + 6, x + 8, y + 1,
                               fill=color, width=2)
            canvas.create_line(x - 8, y + 6, x, y + 11, x + 8, y + 6,
                               fill=color, width=2)

    def _on_orbit_click(self, event):
        for x, y, radius, index in self._node_hits:
            if (event.x - x) ** 2 + (event.y - y) ** 2 <= (radius + 6) ** 2:
                self._select_module(index)
                return

    def _on_orbit_motion(self, event):
        """Запоминает узел под курсором — он подсвечивается при перерисовке."""
        index = None
        for x, y, radius, i in self._node_hits:
            if (event.x - x) ** 2 + (event.y - y) ** 2 <= (radius + 6) ** 2:
                index = i
                break
        self._set_hover_node(index)

    def _set_hover_node(self, index):
        """Меняет подсвеченный узел и просит перерисовать орбиту."""
        if index == self._hover_node:
            return
        self._hover_node = index
        try:
            self.orbit_canvas.configure(cursor="hand2" if index is not None else "")
        except Exception:
            pass
        self._schedule_core_redraw()

    def _refresh_core(self):
        """Перерисовывает центр сцены по текущему прогрессу."""
        bar = getattr(self, "progress", None)
        if bar is not None:
            try:
                self._orbit_progress = float(bar.get())
            except Exception:
                pass
        self._draw_orbit()

    def _set_progress(self, value: float):
        """Ставит ЦЕЛЬ прогресса; полоса и дуга плавно «догоняют» её.

        Полосы может ещё не быть — модуль очистки строится лениво, а плановая
        очистка идёт и без него; тогда анимируется только дуга орбиты.
        """
        try:
            self._progress_target = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            self._progress_target = 0.0
        if not self._progress_anim_running:
            self._progress_anim_running = True
            self.after(16, self._animate_progress)

    def _animate_progress(self):
        """Один кадр плавного прогресса (экспоненциальное приближение)."""
        if self._closing:
            self._progress_anim_running = False
            return
        diff = self._progress_target - self._progress_shown
        if abs(diff) < 0.002:
            self._progress_shown = self._progress_target
            self._apply_progress_visuals()
            self._progress_anim_running = False
            return
        # Быстро в начале, мягко в конце — без рывков при потоке сообщений
        # о прогрессе (они приходят до 20 раз в секунду).
        self._progress_shown += diff * 0.22
        self._apply_progress_visuals()
        try:
            self.after(16, self._animate_progress)
        except Exception:
            self._progress_anim_running = False

    def _apply_progress_visuals(self):
        """Переносит анимированное значение в полосу и в дугу орбиты."""
        self._orbit_progress = self._progress_shown
        bar = getattr(self, "progress", None)
        if bar is not None:
            try:
                bar.set(self._progress_shown)
            except Exception:
                pass
        self._schedule_core_redraw()

    def _tween_bar(self, bar, target, duration: int = 260):
        """Плавно доводит полосу до target (ease-out), без наложения твинов.

        Нужна для полос левого рельса и «крупнейших категорий»: мгновенный
        скачок выглядит дёшево, а плавное заполнение читается как отклик.
        """
        try:
            start = float(bar.get())
        except Exception:
            start = 0.0
        target = max(0.0, min(1.0, float(target)))
        gen = getattr(bar, "_swept_tween", 0) + 1
        bar._swept_tween = gen
        if abs(target - start) < 0.004:
            try:
                bar.set(target)
            except Exception:
                pass
            return
        frames = max(1, int(duration / 16.0))
        state = {"i": 0}

        def step():
            if self._closing or getattr(bar, "_swept_tween", 0) != gen:
                return
            state["i"] += 1
            t = state["i"] / float(frames)
            eased = 1 - (1 - t) ** 3
            try:
                bar.set(start + (target - start) * eased)
            except Exception:
                return
            if state["i"] < frames:
                try:
                    self.after(16, step)
                except Exception:
                    pass

        self.after(16, step)

    def _schedule_core_redraw(self):
        """Перерисовывает центр не чаще ~16 раз в секунду.

        Один кадр орбиты стоит около миллисекунды; при потоке сообщений
        о прогрессе перерисовка на каждое съедала бы больше времени, чем
        само удаление файлов.
        """
        if self._core_scheduled:
            return
        self._core_scheduled = True
        try:
            self.after(60, self._flush_core_redraw)
        except Exception:
            self._core_scheduled = False

    def _flush_core_redraw(self):
        self._core_scheduled = False
        if self._closing:
            return
        self._draw_orbit()

    def _apply_total_text(self):
        """Показывает накопленный итог в модуле очистки (если он уже построен)."""
        label = getattr(self, "total_label", None)
        if label is None or not self._total_text:
            return
        try:
            label.configure(text=self._total_text)
        except Exception:
            pass

    # ---------------------------------------------------------------- лента
    def _build_ribbon(self):
        ribbon = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=14)
        ribbon.pack(fill="x", padx=14, pady=(8, 12))

        self.ribbon_back = ctk.CTkButton(
            ribbon, text="← " + i18n.t("ribbon.back"), width=104, height=32,
            font=ctk.CTkFont(size=11), fg_color="transparent",
            hover_color=COLOR_CARD_2, border_width=1, border_color=COLOR_LINE,
            text_color=COLOR_MUTED, state="disabled", command=self._show_orbit)
        self.ribbon_back.pack(side="left", padx=(14, 0), pady=10)

        left = ctk.CTkFrame(ribbon, fg_color="transparent")
        left.pack(side="left", padx=(14, 0), pady=10)
        self.ribbon_title = ctk.CTkLabel(left, text="",
                                         font=ctk.CTkFont(size=15, weight="bold"),
                                         text_color=COLOR_TEXT)
        self.ribbon_title.pack(anchor="w")
        self.ribbon_sub = ctk.CTkLabel(left, text="", font=ctk.CTkFont(size=11),
                                       text_color=COLOR_MUTED)
        self.ribbon_sub.pack(anchor="w")

        # Действия модуля «Очистка» живут в ленте (как в концепте Orbit)
        # и показываются только когда этот модуль открыт.
        self.ribbon_actions = ctk.CTkFrame(ribbon, fg_color="transparent")
        self.analyze_btn = ctk.CTkButton(
            self.ribbon_actions, text=i18n.t("btn.analyze"), width=128, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self.on_analyze)
        self.analyze_btn.pack(side="left", padx=(0, 8))
        self.clean_btn = ctk.CTkButton(
            self.ribbon_actions, text=i18n.t("btn.clean"), width=128, height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            command=self.on_clean)
        self.clean_btn.pack(side="left")
        self.stop_btn = ctk.CTkButton(
            self.ribbon_actions, text=i18n.t("btn.stop"), width=86, height=34,
            font=ctk.CTkFont(size=12), fg_color=COLOR_CARD_2,
            hover_color=COLOR_RED, state="disabled", command=self.on_stop)
        self.stop_btn.pack(side="left", padx=(8, 0))

        self.status_label = ctk.CTkLabel(ribbon, text=i18n.t("status.ready"),
                                         font=ctk.CTkFont(size=11),
                                         text_color=COLOR_MUTED)
        self.status_label.pack(side="right", padx=16)

    def _on_tab_change(self):
        """Совместимость: раньше запоминала активную вкладку."""
        return

    # ================================================= ВКЛАДКА «ОЧИСТКА»
    def _build_clean_tab(self, parent):
        """Вкладка очистки: категории слева, управление справа."""
        parent.grid_columnconfigure(0, weight=1, minsize=380)
        parent.grid_columnconfigure(1, weight=0, minsize=330)
        parent.grid_rowconfigure(0, weight=1)

        # --- Левая панель: категории ---
        panel = ctk.CTkScrollableFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        panel.grid(row=0, column=0, sticky="nsew", padx=(10, 8), pady=10)

        ctk.CTkLabel(panel, text=i18n.t("clean.categories"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w", padx=6, pady=(4, 8))

        groups = {}
        for cat in core.CATEGORIES:
            groups.setdefault(cat["group"], []).append(cat)

        for group_key, cats in groups.items():
            # «Дополнительные места» занимают одну строку и раскрываются
            # по клику — иначе список категорий вырос бы вдвое.
            if group_key in core.COLLAPSED_GROUPS:
                self._build_collapsed_group(panel, group_key, cats)
                continue

            title = core.group_title(group_key)
            ctk.CTkLabel(panel, text=title.upper(),
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=COLOR_ACCENT).pack(anchor="w", padx=6, pady=(10, 4))

            card = ctk.CTkFrame(panel, fg_color=COLOR_CARD, corner_radius=10)
            card.pack(fill="x", padx=4, pady=2)

            for cat in cats:
                self._build_category_row(card, cat)

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(fill="x", padx=4, pady=(12, 6))
        ctk.CTkButton(buttons, text=i18n.t("btn.select_all"), width=120, height=30,
                      fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                      command=lambda: self._set_all(True)).pack(side="left")
        ctk.CTkButton(buttons, text=i18n.t("btn.clear_all"), width=120, height=30,
                      fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                      command=lambda: self._set_all(False)).pack(side="left", padx=8)

        # --- Правая панель: управление ---
        right = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

        ctk.CTkLabel(right, text=i18n.t("clean.control"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w", padx=14, pady=(12, 8))

        # Переключатель «Только сканирование». Переменная создаётся в __init__
        # (модуль строится лениво, а состояние нужно уже при смене языка).
        ctk.CTkSwitch(right, text=i18n.t("clean.scan_only"),
                      variable=self.scan_only_var,
                      font=ctk.CTkFont(size=12),
                      text_color=COLOR_MUTED,
                      progress_color=COLOR_ACCENT).pack(anchor="w", padx=14, pady=4)

        # Кнопки «Анализ»/«Очистить»/«Стоп» переехали в нижнюю ленту
        # (как в концепте Orbit) — здесь только подсказка об этом.
        ctk.CTkLabel(right, text=i18n.t("clean.actions_hint"),
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                     wraplength=300, justify="left").pack(
            anchor="w", padx=14, pady=(12, 8))

        # Итог.
        self.total_label = ctk.CTkLabel(
            right, text=i18n.t("clean.total_zero"),
            font=ctk.CTkFont(size=14, weight="bold"), text_color=COLOR_GREEN)
        self.total_label.pack(anchor="w", padx=14, pady=(8, 4))

        # Прогресс.
        self.progress = ctk.CTkProgressBar(right, height=12, corner_radius=6,
                                           progress_color=COLOR_ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=14, pady=(4, 12))

        # Крупнейшие категории: заполняется после анализа, чтобы в панели
        # управления не оставалось пустоты, а пользователь видел, что нашлось.
        # Список прокручиваемый и полный: раньше он обрезался пятёркой, и
        # найденные категории за её пределами просто не показывались.
        self.top_header = ctk.CTkLabel(right, text=i18n.t("clean.top").upper(),
                                       font=ctk.CTkFont(size=10, weight="bold"),
                                       text_color=COLOR_MUTED)
        self.top_header.pack(anchor="w", padx=14)
        self.top_box = ctk.CTkScrollableFrame(right, fg_color="transparent",
                                              height=250)
        self.top_box.pack(fill="x", padx=(14, 6), pady=(6, 12))
        self.top_rows = []
        self.top_empty = ctk.CTkLabel(self.top_box, text=i18n.t("clean.top_empty"),
                                      font=ctk.CTkFont(size=11),
                                      text_color=COLOR_MUTED)
        self.top_empty.pack(anchor="w")

        # Хранилище компонентов (WinSxS) — теперь отдельный модуль орбиты,
        # поэтому здесь его блок не создаётся.

    # -------------------------------------------------- строки категорий
    def _build_category_row(self, card, cat) -> None:
        """Одна строка категории: галочка, подпись с размером, при нужде ⚙."""
        var = tk.BooleanVar(value=True)
        self.vars[cat["key"]] = var
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=4)

        ctk.CTkCheckBox(row, text="{} {}".format(cat["icon"], i18n.fld(cat, "title")),
                        variable=var, font=ctk.CTkFont(size=13),
                        text_color=COLOR_TEXT, checkbox_width=20, checkbox_height=20,
                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER
                        ).pack(side="left")

        info = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=11),
                            text_color=COLOR_MUTED)
        info.pack(side="right")
        self._info_widgets[cat["key"]] = info

        # Для браузеров — шестерёнка: раскрывает раздельные настройки
        # очистки (кэш / cookie / история / пароли …), как в Wise.
        if cat["key"] in core.BROWSER_KEYS:
            gear = ctk.CTkButton(
                row, text="⚙", width=26, height=22,
                font=ctk.CTkFont(size=12),
                fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                text_color=COLOR_MUTED,
                command=lambda k=cat["key"]: self._toggle_browser_opts(k))
            gear.pack(side="right", padx=(8, 0))
            sub = ctk.CTkFrame(card, fg_color="transparent")
            sub.pack(fill="x", padx=(22, 10), pady=(0, 4))
            sub.pack_forget()  # скрыта, пока не нажмут ⚙
            self._browser_opt_frames[cat["key"]] = sub
            self._browser_opt_rows[cat["key"]] = row
            self._build_browser_opt_sub(sub, cat["key"])

    def _build_collapsed_group(self, parent, group_key: str, cats: list) -> None:
        """
        Свёрнутая группа: заголовок-кнопка со счётчиком, внутри — обычные
        строки категорий. Список в панели не растёт, а пункты доступны.
        """
        title = core.group_title(group_key).upper()
        btn = ctk.CTkButton(parent, text="▸  {} · {}".format(title, len(cats)),
                            anchor="w", height=26, corner_radius=8,
                            fg_color="transparent", hover_color=COLOR_CARD,
                            text_color=COLOR_ACCENT,
                            font=ctk.CTkFont(size=11, weight="bold"),
                            command=lambda k=group_key: self._toggle_group(k))
        btn.pack(fill="x", padx=6, pady=(12, 2))

        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10)
        for cat in cats:
            self._build_category_row(card, cat)

        self._group_cards[group_key] = card
        self._group_buttons[group_key] = (btn, title, len(cats))
        # Состояние «раскрыта» храним отдельно: winfo_ismapped() врёт, когда
        # модуль очистки ещё не открыт, и заголовок терял бы стрелку.
        self._group_expanded[group_key] = False

    def _group_text(self, group_key: str, expanded: bool) -> str:
        """Подпись заголовка свёрнутой группы: стрелка, название, число, объём."""
        entry = self._group_buttons.get(group_key)
        title = entry[1] if entry else group_key
        count = entry[2] if entry else 0
        total = 0
        for cat in core.CATEGORIES:
            if cat["group"] == group_key:
                total += int((self.scan_results.get(cat["key"]) or {}).get("total_size", 0))
        text = "{}  {} · {}".format("▾" if expanded else "▸", title, count)
        # Объём показываем только когда он есть: пустая группа не должна
        # занимать строку «0 Б».
        if total:
            text += " · " + core.format_bytes(total)
        return text

    def _toggle_group(self, group_key: str) -> None:
        """Раскрывает/сворачивает группу категорий по клику на заголовок."""
        card = self._group_cards.get(group_key)
        entry = self._group_buttons.get(group_key)
        if card is None or entry is None:
            return
        btn = entry[0]
        expanded = not self._group_expanded.get(group_key, False)
        self._group_expanded[group_key] = expanded
        if expanded:
            # after= возвращает карточку ровно под её заголовок
            # (pack_forget теряет исходную позицию в списке).
            card.pack(fill="x", padx=4, pady=2, after=btn)
        else:
            card.pack_forget()
        btn.configure(text=self._group_text(group_key, expanded))

    def _refresh_group_headers(self) -> None:
        """Обновляет подписи свёрнутых групп после анализа (объём в заголовке)."""
        for group_key in self._group_buttons:
            entry = self._group_buttons[group_key]
            try:
                entry[0].configure(text=self._group_text(
                    group_key, self._group_expanded.get(group_key, False)))
            except Exception:
                pass

    # -------------------------------------------------- настройки браузеров
    def _toggle_browser_opts(self, key: str) -> None:
        """Показывает/скрывает вложенную панель под-опций браузера."""
        frame = self._browser_opt_frames.get(key)
        if not frame:
            return
        if frame.winfo_ismapped():
            frame.pack_forget()
        else:
            # pack(after=...) возвращает панель ровно под её строкой-браузером,
            # а не в конец списка (pack_forget теряет исходную позицию).
            anchor = self._browser_opt_rows.get(key)
            if anchor is not None:
                frame.pack(fill="x", padx=(22, 10), pady=(0, 4), after=anchor)
            else:
                frame.pack(fill="x", padx=(22, 10), pady=(0, 4))

    def _build_browser_opt_sub(self, sub, key: str) -> None:
        """Строит вложенную панель раздельных под-опций очистки браузера."""
        self.browser_opt.setdefault(key, {})
        ctk.CTkLabel(sub, text=i18n.t("clean.browser_options"),
                     font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COLOR_ACCENT).pack(anchor="w", padx=2, pady=(2, 4))
        saved = settings.get_browser_options(key)
        for s in core.get_browser_suboptions(key):
            sv = tk.BooleanVar(value=s["key"] in saved)
            self.browser_opt[key][s["key"]] = sv
            cb = ctk.CTkCheckBox(
                sub, text=i18n.fld(s, "title"),
                variable=sv, font=ctk.CTkFont(size=12),
                text_color=COLOR_TEXT, checkbox_width=18, checkbox_height=18,
                fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                command=lambda k=key, sub_opt=s, v=sv: self._on_browser_opt(k, sub_opt, v))
            cb.pack(anchor="w", padx=6, pady=1)
            # Под-опции, затрагивающие личные данные, — с пометкой «осторожно».
            if core.is_browser_suboption_caution(s):
                ctk.CTkLabel(sub, text="⚠ " + i18n.t("clean.browser_caution"),
                             font=ctk.CTkFont(size=10),
                             text_color=COLOR_MUTED).pack(
                    anchor="w", padx=26, pady=(0, 2))

    def _on_browser_opt(self, key: str, sub: dict, var: tk.BooleanVar) -> None:
        """
        Сохраняет выбор под-опции и, если пользователь ВКЛЮЧАЕТ опцию,
        затрагивающую личные данные, спрашивает подтверждение. При отказе —
        возвращает галочку в исходное (выключенное) состояние.
        """
        if var.get() and core.is_browser_suboption_caution(sub):
            if not messagebox.askyesno(
                    i18n.t("dlg.browser_opt_title"),
                    i18n.t("dlg.browser_opt_text", i18n.fld(sub, "title"))):
                var.set(False)
        # Сохраняем актуальный набор и сбрасываем кэш анализа этой категории,
        # чтобы следующий «Анализ»/«Очистить» пересчитал размер под новый выбор.
        current = {sk for sk, v in self.browser_opt.get(key, {}).items() if v.get()}
        settings.set_browser_options(key, current)
        if getattr(self, "scan_results", None):
            self.scan_results.pop(key, None)

    def _browser_selected_map(self) -> dict:
        """
        Собирает {ключ_браузера: множество включённых под-опций} из текущих
        галочек интерфейса — для передачи в ядро при сканировании/очистке.
        """
        result = {}
        for key in core.BROWSER_KEYS:
            if key in self.vars:  # браузер присутствует в списке категорий
                result[key] = {sk for sk, v in self.browser_opt.get(key, {}).items()
                               if v.get()}
        return result

    def _build_winsxs_tab(self, parent):
        """Панель модуля WinSxS: заголовок с объяснением и сам блок DISM."""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        ctk.CTkLabel(head, text=i18n.t("winsxs.title"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(head, text=i18n.t("winsxs.hint"),
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                     wraplength=640, justify="left").pack(
            anchor="w", padx=14, pady=(0, 12))

        body = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self._build_winsxs_block(body, with_title=False)

        # Что именно произойдёт — коротко, перед потенциально долгой операцией.
        notes = ctk.CTkFrame(parent, fg_color="transparent")
        notes.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        for text in ("winsxs.b1", "winsxs.b2", "winsxs.b3"):
            ctk.CTkLabel(notes, text="· " + i18n.t(text),
                         font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                         anchor="w", justify="left", wraplength=620).pack(
                fill="x", padx=6, pady=1)

    def _build_winsxs_block(self, parent, with_title: bool = True):
        """Блок «Хранилище компонентов (WinSxS)»."""
        box = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10)
        box.pack(fill="x", padx=14, pady=(12, 12))

        if with_title:
            head = ctk.CTkFrame(box, fg_color="transparent")
            head.pack(fill="x", padx=12, pady=(10, 0))

            ctk.CTkLabel(head, text=i18n.t("winsxs.title"),
                         font=ctk.CTkFont(size=13, weight="bold"),
                         text_color=COLOR_TEXT).pack(side="left")

            ctk.CTkLabel(head, text=i18n.t("winsxs.sub"),
                         font=ctk.CTkFont(size=10),
                         text_color=COLOR_MUTED).pack(side="left", padx=(8, 0))

        # Главный ответ на вопрос «надо чистить или нет».
        self.winsxs_state = ctk.CTkLabel(
            box, text=i18n.t("winsxs.state_unknown"),
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_MUTED, anchor="w", justify="left")
        self.winsxs_state.pack(fill="x", padx=12, pady=(6, 0))

        self.winsxs_detail = ctk.CTkLabel(
            box, text=i18n.t("winsxs.hint"),
            font=ctk.CTkFont(size=10), text_color=COLOR_MUTED,
            anchor="w", justify="left", wraplength=520)
        self.winsxs_detail.pack(fill="x", padx=12, pady=(3, 0))

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 8))

        self.winsxs_check_btn = ctk.CTkButton(
            row, text=i18n.t("winsxs.check"), width=120, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self.on_winsxs_check)
        self.winsxs_check_btn.pack(side="left")

        self.winsxs_clean_btn = ctk.CTkButton(
            row, text=i18n.t("winsxs.clean"), width=160, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            state="disabled", command=self.on_winsxs_clean)
        self.winsxs_clean_btn.pack(side="left", padx=(8, 0))

        # Полоса прогресса DISM: показывается только во время операции,
        # чтобы в спокойном состоянии не выглядела как ещё один орган управления.
        self.winsxs_progress = ctk.CTkProgressBar(
            box, height=6, corner_radius=3, progress_color=COLOR_ACCENT)
        self.winsxs_progress.set(0)

        # Состояние могло быть получено до перерисовки интерфейса
        # (например, при смене языка) — восстанавливаем подписи.
        self._render_winsxs_report()

    # ============================================= ВКЛАДКА «УСТАНОВКА»
    def _build_install_tab(self, parent):
        """Вкладка установки программ (прямая установка, без winget).

        Слева — постоянная колонка наборов популярных программ, справа —
        поиск и найденные пакеты. Правая часть построена на grid с одной
        «резиновой» строкой (список пакетов), поэтому при любом размере окна
        верхняя и нижняя панели остаются целиком видимыми.
        """
        parent.grid_columnconfigure(0, weight=0, minsize=380)
        parent.grid_columnconfigure(1, weight=1)
        # Растягивается только строка со списком пакетов: панель поиска
        # и нижняя панель при уменьшении окна остаются целиком видимыми.
        parent.grid_rowconfigure(0, weight=0)
        parent.grid_rowconfigure(1, weight=1, minsize=110)
        parent.grid_rowconfigure(2, weight=0)

        # --- Левая колонка: наборы популярных программ (список столбиком) ---
        # Пользователь сам решает, что ставить: строка набора открывает окно
        # с галочками, а не ставит весь набор целиком.
        left = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        left.grid(row=0, column=0, rowspan=3, sticky="nsew",
                  padx=(10, 6), pady=10)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        left_head = ctk.CTkFrame(left, fg_color="transparent")
        left_head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))
        ctk.CTkLabel(left_head, text=i18n.t("presets.title"),
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLOR_TEXT, height=22).pack(anchor="w")
        ctk.CTkLabel(left_head, text=i18n.t("presets.subtitle"),
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                     justify="left", anchor="w", wraplength=330, height=16
                     ).pack(anchor="w", pady=(1, 0))

        self.presets_list = ctk.CTkScrollableFrame(
            left, fg_color=COLOR_BG, corner_radius=10,
            scrollbar_button_color=COLOR_CARD_2,
            scrollbar_button_hover_color=COLOR_ACCENT)
        self.presets_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))

        # Строка набора: название, счётчик и кнопка, ниже — какие программы внутри.
        self.preset_buttons = {}
        for preset in inst.APP_PRESETS:
            row = ctk.CTkFrame(self.presets_list, fg_color=COLOR_CARD,
                               corner_radius=8)
            row.pack(fill="x", padx=2, pady=2)
            row.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(row, text=i18n.fld(preset, "title"),
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=COLOR_TEXT, anchor="w", height=20
                         ).grid(row=0, column=0, sticky="w", padx=(10, 6),
                                pady=(4, 0))

            ctk.CTkLabel(row,
                         text=i18n.t("presets.count", len(preset["packages"])),
                         font=ctk.CTkFont(size=10), text_color=COLOR_MUTED,
                         anchor="e", height=20
                         ).grid(row=0, column=1, sticky="e",
                                padx=(0, 8), pady=(4, 0))

            button = ctk.CTkButton(
                row, text=i18n.t("presets.choose"), width=86, height=24,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                command=lambda p=preset: self.on_install_preset(p))
            button.grid(row=0, column=2, sticky="e", padx=(0, 8), pady=(4, 0))
            self.preset_buttons[preset["key"]] = button

            ctk.CTkLabel(row, text=i18n.fld(preset, "desc"),
                         font=ctk.CTkFont(size=10), text_color=COLOR_MUTED,
                         justify="left", anchor="w", wraplength=340, height=16
                         ).grid(row=1, column=0, columnspan=3, sticky="w",
                                padx=10, pady=(0, 4))

        # Быстрая установка Visual C++ Redistributable (все версии, x86 и x64).
        vc_box = ctk.CTkFrame(left, fg_color="transparent")
        vc_box.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        vc_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(vc_box, text=i18n.t("vc.label"),
                     font=ctk.CTkFont(size=10), text_color=COLOR_MUTED,
                     justify="left", anchor="w", wraplength=330, height=15
                     ).grid(row=0, column=0, sticky="w")
        self.vc_btn = ctk.CTkButton(
            vc_box, text=i18n.t("btn.install_vc"), height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self.on_install_vc)
        self.vc_btn.grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # --- Правая часть: поиск ---
        top = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        top.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(10, 6))
        top.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(top, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 6))
        head.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(head, text=i18n.t("install.title"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).grid(row=0, column=0, sticky="w")

        # Статус установщика — под заголовком: рядом с ним он не помещался
        # в узкую колонку и заголовок обрезался.
        self.installer_label = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=11))
        self.installer_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        search_row = ctk.CTkFrame(top, fg_color="transparent")
        search_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        search_row.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            search_row, placeholder_text=i18n.t("install.search_ph"),
            font=ctk.CTkFont(size=13))
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self.on_search())

        self.search_btn = ctk.CTkButton(search_row, text=i18n.t("btn.search"),
                                        width=110, height=32,
                                        font=ctk.CTkFont(size=12, weight="bold"),
                                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                                        command=self.on_search)
        self.search_btn.grid(row=0, column=1, padx=(0, 8))

        self.upgrade_all_btn = ctk.CTkButton(
            search_row, text=i18n.t("btn.upgrade_all"), width=150, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            command=self.on_upgrade_all)
        self.upgrade_all_btn.grid(row=0, column=2)

        # Проверка готовности установщика выполняется в фоне один раз за сеанс:
        # при смене языка интерфейс перерисовывается, а результат сохраняется.
        if self.installer_available is None:
            self.installer_label.configure(text=i18n.t("installer.checking"),
                                        text_color=COLOR_MUTED)
            threading.Thread(target=self._check_installer_worker, daemon=True).start()
        else:
            self._refresh_installer_label()

        # --- Средняя панель: результаты поиска (кликабельный список) ---
        mid = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        mid.grid(row=1, column=1, sticky="nsew", padx=(0, 10), pady=6)
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_rowconfigure(1, weight=1)

        title_row = ctk.CTkFrame(mid, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        ctk.CTkLabel(title_row, text=i18n.t("install.results"),
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=COLOR_TEXT).pack(side="left")
        self.results_count = ctk.CTkLabel(title_row, text="", font=ctk.CTkFont(size=11),
                                          text_color=COLOR_MUTED)
        self.results_count.pack(side="left", padx=(8, 0))

        self.results_scroll = ctk.CTkScrollableFrame(
            mid, fg_color=COLOR_BG, corner_radius=10,
            scrollbar_button_color=COLOR_CARD_2,
            scrollbar_button_hover_color=COLOR_ACCENT)
        self.results_scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        self.results_scroll.grid_columnconfigure(0, minsize=40)
        self.results_scroll.grid_columnconfigure(1, weight=3)
        self.results_scroll.grid_columnconfigure(2, weight=4)
        self.results_scroll.grid_columnconfigure(3, minsize=90)

        self._clear_results(i18n.t("install.hint"))

        # --- Нижняя панель: выбранный пакет + действия ---
        bot = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        bot.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(6, 10))
        bot.grid_columnconfigure(0, weight=1)

        row1 = ctk.CTkFrame(bot, fg_color="transparent")
        row1.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        row1.grid_columnconfigure(0, weight=1)

        self.pkg_label = ctk.CTkLabel(
            row1, text=i18n.t("pkg.not_selected"),
            font=ctk.CTkFont(size=11), text_color=COLOR_MUTED, anchor="w")
        self.pkg_label.grid(row=0, column=0, sticky="w")

        self.install_pkg_btn = ctk.CTkButton(
            row1, text=i18n.t("btn.install"), width=130, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            state="disabled", command=self.on_install_pkg)
        self.install_pkg_btn.grid(row=0, column=1, padx=(8, 6))

        self.upgrade_pkg_btn = ctk.CTkButton(
            row1, text=i18n.t("btn.upgrade"), width=130, height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            state="disabled", command=self.on_upgrade_pkg)
        self.upgrade_pkg_btn.grid(row=0, column=2)

        # Строка ручного ввода: номер из списка или ID пакета.
        row2 = ctk.CTkFrame(bot, fg_color="transparent")
        row2.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 4))
        row2.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row2, text=i18n.t("pkg.number"),
                     font=ctk.CTkFont(size=12),
                     text_color=COLOR_MUTED).grid(row=0, column=0, padx=(0, 8))

        self.pkg_entry = ctk.CTkEntry(row2, placeholder_text=i18n.t("pkg.entry_ph"),
                                      font=ctk.CTkFont(size=12))
        self.pkg_entry.grid(row=0, column=1, sticky="ew")
        self.pkg_entry.bind("<Return>", lambda e: self.on_select_pkg())

        self.select_btn = ctk.CTkButton(row2, text=i18n.t("btn.select"), width=90, height=28,
                                        font=ctk.CTkFont(size=12),
                                        fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                                        command=self.on_select_pkg)
        self.select_btn.grid(row=0, column=2, padx=(8, 0))

        self.install_status = ctk.CTkLabel(
            bot, text=i18n.t("status.ready"), font=ctk.CTkFont(size=11),
            text_color=COLOR_MUTED, anchor="w")
        self.install_status.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))

        # Панель могли открыть во время операции — сразу выставляем блокировку.
        self._apply_installer_buttons(self.running)

    # =========================================== ВКЛАДКА «ОПТИМИЗАЦИЯ»
    def _build_optimize_tab(self, parent):
        """Вкладка оптимизации Windows 10/11 (безопасные, обратимые настройки)."""
        parent.grid_columnconfigure(0, weight=0, minsize=400)
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        # --- Левая панель: список оптимизаций ---
        panel = ctk.CTkScrollableFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        panel.grid(row=0, column=0, sticky="nsew", padx=(10, 8), pady=10)

        ctk.CTkLabel(panel, text=i18n.t("opt.title"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w", padx=6, pady=(4, 8))
        ctk.CTkLabel(panel, text=i18n.t("opt.note"),
                     font=ctk.CTkFont(size=11),
                     text_color=COLOR_MUTED, justify="left", anchor="w"
                     ).pack(anchor="w", padx=6, pady=(0, 8))

        groups = {}
        for item in opt.OPTIMIZATIONS:
            groups.setdefault(item.get("group", "basics"), []).append(item)
        for group_key, items in groups.items():
            title = opt.opt_group_title(group_key)
            ctk.CTkLabel(panel, text=title.upper(),
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=COLOR_ACCENT
                         ).pack(anchor="w", padx=6, pady=(10, 4))
            for item in items:
                var = tk.BooleanVar(value=item["key"] in opt.SAFE_DEFAULT_KEYS)
                self.opt_vars[item["key"]] = var
                card = ctk.CTkFrame(panel, fg_color=COLOR_CARD, corner_radius=10)
                card.pack(fill="x", padx=4, pady=3)
                top = ctk.CTkFrame(card, fg_color="transparent")
                top.pack(fill="x", padx=10, pady=(6, 0))
                badge = i18n.t("opt.badge_admin") if item["admin"] else ""
                # Галочка без текста + отдельная подпись с переносом строк:
                # у CTkCheckBox нет wraplength, и длинные названия обрезались.
                check = ctk.CTkCheckBox(top, text="", width=20, variable=var,
                                        checkbox_width=20, checkbox_height=20,
                                        fg_color=COLOR_ACCENT,
                                        hover_color=COLOR_ACCENT_HOVER)
                check.pack(side="left", anchor="n")
                title_label = ctk.CTkLabel(
                    top, text=i18n.fld(item, "title") + badge,
                    font=ctk.CTkFont(size=13), text_color=COLOR_TEXT,
                    justify="left", anchor="w", wraplength=305)
                title_label.pack(side="left", fill="x", expand=True, padx=(6, 0))
                title_label.bind("<Button-1>",
                                 lambda event, v=var: v.set(not v.get()))
                ctk.CTkLabel(card, text=i18n.fld(item, "desc"),
                             font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                             justify="left", anchor="w", wraplength=300
                             ).pack(anchor="w", padx=12, pady=(2, 6))

        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(fill="x", padx=4, pady=(10, 6))
        ctk.CTkButton(buttons, text=i18n.t("btn.mark_safe"), width=155, height=30,
                      fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                      command=lambda: self._set_opt_defaults()).pack(side="left")
        ctk.CTkButton(buttons, text=i18n.t("btn.clear_all"), width=110, height=30,
                      fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                      command=lambda: self._set_all_opt(False)).pack(side="left", padx=6)

        # --- Правая панель: разбор системы и управление ---
        right = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

        self._build_diag_card(right)

        ctk.CTkLabel(right, text=i18n.t("opt.control"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w", padx=14, pady=(12, 8))

        info = opt.get_windows_info()
        self.opt_os_label = ctk.CTkLabel(
            right, text=i18n.t("opt.os", info["display"], info["build"],
                               info["edition"] or "—"),
            font=ctk.CTkFont(size=12), text_color=COLOR_MUTED)
        self.opt_os_label.pack(anchor="w", padx=14, pady=(0, 4))

        ctk.CTkLabel(right,
                     text=i18n.t("opt.admin_note"),
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                     justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0, 8))

        btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        btn_frame.pack(fill="x", padx=14, pady=(4, 6))
        self.opt_apply_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn.apply"), height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            command=self.on_optimize)
        self.opt_apply_btn.pack(fill="x")

        # Точка восстановления: создаётся через PowerShell Checkpoint-Computer.
        # Безопасная операция — ставим под «Применить» нейтральным цветом:
        # в одну строку две кнопки не помещались и вторая обрезалась.
        self.opt_restore_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn.restore_point"), height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
            command=self.on_create_restore_point)
        self.opt_restore_btn.pack(fill="x", pady=(8, 0))

        self.opt_status = ctk.CTkLabel(right, text=i18n.t("status.ready"),
                                       font=ctk.CTkFont(size=12),
                                       text_color=COLOR_MUTED)
        self.opt_status.pack(anchor="w", padx=14, pady=(8, 4))

        self.opt_progress = ctk.CTkProgressBar(right, height=12, corner_radius=6,
                                               progress_color=COLOR_ACCENT)
        self.opt_progress.set(0)
        self.opt_progress.pack(fill="x", padx=14, pady=(4, 8))

        # Живой список: что применяется сейчас и что получилось с каждым пунктом.
        # Показывается только во время и после прогона, чтобы не занимать место зря.
        self.opt_live = ctk.CTkScrollableFrame(right, fg_color=COLOR_CARD,
                                               corner_radius=10, height=190)
        self.opt_live_title = ctk.CTkLabel(self.opt_live,
                                           text=i18n.t("opt.live_title"),
                                           font=ctk.CTkFont(size=11, weight="bold"),
                                           text_color=COLOR_ACCENT)
        self.opt_live_title.pack(anchor="w", padx=4, pady=(2, 4))
        self.opt_rows = {}
        self._opt_live_visible = False

        # Отдельного «Совета» про запуск от администратора здесь больше нет:
        # ровно то же сказано строкой выше (opt.admin_note), а место в панели
        # нужно карточке разбора — при минимальном размере окна подсказка
        # обрезалась последней.

        # Первый разбор запускаем сами: пользователь должен увидеть вердикт,
        # не нажимая ничего. При смене языка отчёт уже есть — его перерисуем
        # в _build_diag_card, повторно измерять систему не нужно.
        if self._diag_report is None:
            self.after(350, self._run_diagnose)

    # --------------------------------------- разбор «почему тормозит»
    def _build_diag_card(self, parent):
        """Карточка разбора: балл, вердикт, причины и кнопки.

        Показывает не «найдено 1234 проблемы», а конкретные измерения:
        сколько программ в автозагрузке, сколько места на диске, сколько
        занято ОЗУ. Поэтому вердикт можно проверить, а не принять на веру.
        """
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10)
        card.pack(fill="x", padx=14, pady=(12, 4))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(head, text=i18n.t("diag.title"),
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COLOR_VIOLET).pack(side="left")
        self.diag_run_btn = ctk.CTkButton(
            head, text=i18n.t("diag.run"), width=84, height=24,
            font=ctk.CTkFont(size=11), fg_color=COLOR_CARD_2,
            hover_color=COLOR_ACCENT, command=self._run_diagnose)
        self.diag_run_btn.pack(side="right")

        score_row = ctk.CTkFrame(card, fg_color="transparent")
        score_row.pack(fill="x", padx=12, pady=(4, 0))
        self.diag_score = ctk.CTkLabel(score_row, text="—",
                                       font=ctk.CTkFont(size=26, weight="bold"),
                                       text_color=COLOR_MUTED)
        self.diag_score.pack(side="left")
        self.diag_verdict = ctk.CTkLabel(
            score_row, text=i18n.t("diag.idle"),
            font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
            justify="left", anchor="w", wraplength=260)
        self.diag_verdict.pack(side="left", padx=(8, 0), pady=(8, 0))

        self.diag_bar = ctk.CTkProgressBar(card, height=6, corner_radius=3,
                                           fg_color=COLOR_CARD_2,
                                           progress_color=COLOR_VIOLET)
        self.diag_bar.set(0)
        self.diag_bar.pack(fill="x", padx=12, pady=(6, 6))

        # Список причин пересобирается при каждом замере.
        self.diag_causes = ctk.CTkFrame(card, fg_color="transparent")
        self.diag_causes.pack(fill="x", padx=12)

        self.diag_delta = ctk.CTkLabel(card, text="",
                                       font=ctk.CTkFont(size=11, weight="bold"),
                                       text_color=COLOR_MINT, anchor="w")

        self.diag_fix_btn = ctk.CTkButton(
            card, text=i18n.t("diag.fix_none"), height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=COLOR_CARD_2, hover_color=COLOR_ACCENT, state="disabled",
            command=self._apply_diag_fixes)
        self.diag_fix_btn.pack(fill="x", padx=12, pady=(6, 10))

        if self._diag_report:
            self._render_diag(self._diag_report)

    def _run_diagnose(self):
        """Запускает измерение системы в фоне."""
        if self._diag_busy or getattr(self, "diag_score", None) is None:
            return
        self._diag_busy = True
        try:
            self.diag_run_btn.configure(state="disabled")
            self.diag_verdict.configure(text=i18n.t("diag.scanning"),
                                        text_color=COLOR_MUTED)
        except Exception:
            pass
        threading.Thread(target=self._diagnose_worker, daemon=True).start()

    def _diagnose_worker(self):
        """Фоновый разбор: Tk не трогает, только кладёт отчёт в очередь."""
        try:
            report = diag.diagnose()
        except Exception as exc:  # noqa: BLE001 - разбор не должен ронять окно
            report = {"score": 0, "verdict": "bad", "causes": [], "fixes": [],
                      "metrics": {}, "ok": False, "error": repr(exc)}
        self.msg_queue.put(("diag_report", report))

    def _render_diag(self, report):
        """Перерисовывает карточку по готовому отчёту."""
        if getattr(self, "diag_score", None) is None:
            return
        self._diag_busy = False
        self._diag_report = report
        try:
            self.diag_run_btn.configure(state="normal", text=i18n.t("diag.run"))
        except Exception:
            pass

        score = int(report.get("score") or 0)
        verdict = report.get("verdict") or "bad"
        color = DIAG_VERDICT_COLORS.get(verdict, COLOR_MUTED)
        self.diag_score.configure(text=str(score), text_color=color)
        self.diag_verdict.configure(
            text=i18n.t("diag.verdict_" + verdict), text_color=color)
        # Полоса едет к баллу плавно — тем же твином, что и полосы рельса.
        try:
            self.diag_bar.configure(progress_color=color)
        except Exception:
            pass
        self._tween_bar(self.diag_bar, score / 100.0)

        for child in self.diag_causes.winfo_children():
            child.destroy()
        causes = report.get("causes") or []
        if not causes:
            ctk.CTkLabel(self.diag_causes, text=i18n.t("diag.no_causes"),
                         font=ctk.CTkFont(size=11),
                         text_color=COLOR_MINT).pack(anchor="w")
        else:
            # Больше четырёх строк карточка не читается — остальное считаем.
            for cause in causes[:4]:
                row = ctk.CTkFrame(self.diag_causes, fg_color="transparent")
                row.pack(fill="x", pady=1)
                ctk.CTkLabel(
                    row, text="•", width=10, font=ctk.CTkFont(size=12),
                    text_color=DIAG_SEVERITY_COLORS.get(
                        cause.get("severity"), COLOR_MUTED)
                ).pack(side="left", anchor="n")
                ctk.CTkLabel(
                    row, text=self._diag_cause_text(cause), anchor="w",
                    justify="left", wraplength=290,
                    font=ctk.CTkFont(size=11),
                    text_color=COLOR_TEXT if cause.get("severity") != "low"
                    else COLOR_MUTED
                ).pack(side="left", fill="x", expand=True)
            if len(causes) > 4:
                ctk.CTkLabel(self.diag_causes,
                             text=i18n.t("diag.more", n=len(causes) - 4),
                             font=ctk.CTkFont(size=11),
                             text_color=COLOR_MUTED).pack(anchor="w", padx=(16, 0))

        fixes = report.get("fixes") or []
        if fixes:
            self.diag_fix_btn.configure(text=i18n.t("diag.fix", n=len(fixes)),
                                        state="normal")
        else:
            self.diag_fix_btn.configure(text=i18n.t("diag.fix_none"),
                                        state="disabled")

        # «Было → стало» показываем только если балл реально изменился
        # после применения оптимизаций.
        baseline = self._diag_baseline
        if baseline is not None and score != baseline:
            diff = score - baseline
            self.diag_delta.configure(
                text=i18n.t("diag.delta", old=baseline, new=score,
                            sign="+" if diff > 0 else "−", diff=abs(diff)),
                # Рост — мятный, падение — предупреждающий: цвет должен
                # совпадать со знаком, а не быть всегда «хорошим».
                text_color=COLOR_MINT if diff > 0 else COLOR_WARN)
            if not self.diag_delta.winfo_ismapped():
                self.diag_delta.pack(fill="x", padx=12, pady=(0, 2),
                                     before=self.diag_fix_btn)

    def _diag_cause_text(self, cause) -> str:
        """Текст причины на текущем языке с подставленными измерениями."""
        key = cause.get("key") or ""
        value = dict(cause.get("value") or {})
        if key == "disk_low":
            value["free"] = core.format_bytes(int(value.get("free") or 0))
            value["pct"] = int(round(float(value.get("pct") or 0)))
        elif key == "ram_full":
            value["pct"] = int(value.get("pct") or 0)
        elif key == "power":
            plan = value.get("plan") or "other"
            value["plan"] = i18n.t("diag.plan_" + plan)
        return i18n.t("diag.cause_" + key, **value)

    def _apply_diag_fixes(self):
        """Отмечает галочки тех оптимизаций, которые закрывают причины.

        Ничего не применяет: пользователь видит список, проверяет его и сам
        нажимает «Применить выбранное» — как и с любым другим пунктом.
        """
        fixes = diag.fix_keys(self._diag_report or {})
        marked = 0
        for key in fixes:
            var = self.opt_vars.get(key)
            if var is not None and not var.get():
                var.set(True)
                marked += 1
        if marked:
            self.opt_status.configure(text=i18n.t("diag.marked", n=marked))
        else:
            self.opt_status.configure(text=i18n.t("diag.already"))
        self._append_log(i18n.t("log.diag_marked", marked))

    # ------------------------------------------- живой список оптимизации
    def _opt_live_show(self, keys):
        """Показывает список выбранных пунктов и сбрасывает их состояние."""
        if not getattr(self, "opt_live", None):
            return
        self.opt_live_title.configure(text=i18n.t("opt.live_title"))
        for widget in self.opt_rows.values():
            widget["row"].destroy()
        self.opt_rows = {}
        for key in keys:
            item = opt.get_optimization(key)
            title = i18n.fld(item, "title") if item else key
            row = ctk.CTkFrame(self.opt_live, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=1)
            icon = ctk.CTkLabel(row, text="•", width=18,
                                font=ctk.CTkFont(size=12), text_color=COLOR_MUTED)
            icon.pack(side="left", anchor="n", pady=(1, 0))
            text = ctk.CTkLabel(row, text=title, anchor="w", justify="left",
                                wraplength=330, font=ctk.CTkFont(size=11),
                                text_color=COLOR_MUTED)
            text.pack(side="left", fill="x", expand=True)
            self.opt_rows[key] = {"row": row, "icon": icon, "text": text,
                                  "title": title}
        if not self._opt_live_visible:
            self.opt_live.pack(fill="both", expand=True, padx=14, pady=(0, 8))
            self._opt_live_visible = True

    def _opt_live_start(self, key, index, total):
        """Помечает пункт как «применяется сейчас»."""
        entry = self.opt_rows.get(key)
        if not entry:
            return
        entry["icon"].configure(text="⏳", text_color=COLOR_ACCENT)
        entry["text"].configure(text_color=COLOR_TEXT)
        self.opt_status.configure(
            text=i18n.t("opt.applying_step", index, total, entry["title"])[:150])

    def _opt_live_done(self, key, kind, reason):
        """Ставит итоговую отметку пункта: готово / пропущено / недоступно / ошибка."""
        entry = self.opt_rows.get(key)
        if not entry:
            return
        marks = {
            "done": ("✔", COLOR_GREEN, COLOR_TEXT),
            "skipped": ("⛔", COLOR_MUTED, COLOR_MUTED),
            "unsupported": ("⛔", COLOR_MUTED, COLOR_MUTED),
            "failed": ("⚠", COLOR_RED, COLOR_RED),
        }
        icon, icon_color, text_color = marks.get(kind, ("•", COLOR_MUTED, COLOR_MUTED))
        entry["icon"].configure(text=icon, text_color=icon_color)
        entry["text"].configure(text_color=text_color)
        if kind in ("skipped", "unsupported", "failed") and reason:
            # Причину пишем прямо в строке: иначе непонятно, почему пункт не сработал.
            entry["text"].configure(
                text="{} — {}".format(entry["title"], reason[:120]))

    def _opt_live_finish(self):
        """Помечает пункты, до которых очередь не дошла (остановка пользователем)."""
        for entry in getattr(self, "opt_rows", {}).values():
            if entry["icon"].cget("text") in ("•", "⏳"):
                entry["icon"].configure(text="—", text_color=COLOR_MUTED)
                entry["text"].configure(
                    text="{} — {}".format(entry["title"],
                                          i18n.t("opt.item_stopped")),
                    text_color=COLOR_MUTED)

    def _set_opt_defaults(self):
        for key, var in self.opt_vars.items():
            var.set(key in opt.SAFE_DEFAULT_KEYS)

    def _set_all_opt(self, value: bool):
        for var in self.opt_vars.values():
            var.set(value)

    def _selected_opt_keys(self) -> list:
        return [key for key, var in self.opt_vars.items() if var.get()]

    # ================================================= ВКЛАДКА «ЖУРНАЛ»
    def _build_log_tab(self, parent):
        """Вкладка журнала операций."""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        panel = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(panel, text=i18n.t("log.title"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w", padx=14, pady=(12, 4))

        self.log_box = ctk.CTkTextbox(panel, fg_color=COLOR_BG, corner_radius=10,
                                      text_color=COLOR_TEXT, font=ctk.CTkFont(size=13),
                                      wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=14, pady=(6, 14))
        self.log_box.configure(state="disabled")

        # Всё, что успело накопиться до первого открытия журнала.
        if self._log_backlog:
            self._insert_log_text(self._log_backlog)
            self._log_backlog = []

    # ======================================================= ВСПОМОГАТЕЛЬНОЕ
    def _check_admin_warning(self):
        self._admin_ok = bool(core.is_admin())
        self._refresh_admin_label()
        if self._admin_ok:
            self._log(i18n.t("log.admin_ok"))
            return
        self._log(i18n.t("log.admin_no_1"))
        self._log(i18n.t("log.admin_no_2"))
        # Предупреждение показываем один раз за запуск (не при смене языка).
        if self._admin_warned:
            return
        self._admin_warned = True
        # Собранная программа сразу предлагает перезапуск с правами: держать
        # пользователя за руку «закройте и откройте заново» незачем.
        # Из исходников спрашивать нечего — там перезапуск делает разработчик,
        # и предупреждение остаётся просто справкой.
        if getattr(sys, "frozen", False):
            if messagebox.askyesno(i18n.t("dlg.no_admin_title"),
                                   i18n.t("dlg.no_admin_ask")):
                self._restart_elevated()
        else:
            messagebox.showwarning(i18n.t("dlg.no_admin_title"),
                                   i18n.t("dlg.no_admin_text"))

    def _on_admin_chip(self):
        """Клик по плашке прав: без прав — перезапуск с повышением."""
        if self._admin_ok:
            return
        self._restart_elevated()

    def _restart_elevated(self):
        """Перезапускает программу с правами администратора (запрос UAC)."""
        try:
            if getattr(sys, "frozen", False):
                exe = sys.executable
                params = ""
            else:
                # Из исходников: python.exe + путь к скрипту отдельным аргументом.
                exe = sys.executable
                params = '"{}"'.format(os.path.abspath(__file__))
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, params, None, 1)
            if result > 32:
                # Новая копия запущена — эта закрывается.
                self._on_close()
            else:
                # Пользователь отказался в UAC: работаем без прав, как раньше.
                self._log(i18n.t("log.admin_no_2"))
        except Exception as exc:
            self._log(i18n.t("log.error") + repr(exc))

    def _log(self, text: str):
        self.msg_queue.put(("log", text))

    def _insert_log_text(self, lines: list):
        """Вставляет строки в текстовое поле журнала (если оно уже создано)."""
        box = getattr(self, "log_box", None)
        if box is None:
            return
        text = "\n".join(lines) + "\n"
        try:
            box.configure(state="normal")
            box.insert("end", text)
            line_count = int(box.index("end-1c").split(".")[0])
            if line_count > MAX_LOG_LINES:
                box.delete("1.0", "{}.0".format(line_count - MAX_LOG_LINES))
            box.see("end")
            box.configure(state="disabled")
        except Exception:
            # Окно уже закрыто/уничтожено — молча пропускаем.
            pass

    def _append_log_lines(self, lines: list):
        """Вставляет пачку строк журнала одной операцией.

        Раньше каждая строка вставлялась отдельно, с прокруткой и проверкой
        длины: около 1 мс на строку, то есть 7 секунд на 6000 файлов. Одна
        вставка той же пачки занимает сотые доли секунды.

        Панель журнала строится лениво, поэтому до её первого открытия
        строки копятся в списке и вставляются разом при сборке.
        """
        if not lines:
            return
        if getattr(self, "log_box", None) is None:
            self._log_backlog.extend(lines)
            if len(self._log_backlog) > MAX_LOG_LINES:
                del self._log_backlog[:len(self._log_backlog) - MAX_LOG_LINES]
        else:
            self._insert_log_text(lines)
        # Короткая лента в правом рельсе: последние строки, без путей-простыней.
        for line in lines[-7:]:
            short = line.strip()
            if len(short) > 74:
                short = short[:71] + "…"
            self._push_feed(short)

    def _log_text(self) -> str:
        """Весь журнал строкой: из поля, а если оно ещё не создано — из накопителя."""
        box = getattr(self, "log_box", None)
        if box is None:
            return "\n".join(self._log_backlog)
        try:
            return box.get("1.0", "end-1c")
        except Exception:
            return "\n".join(self._log_backlog)

    def _append_log(self, text: str):
        self._append_log_lines([text])

    def _set_all(self, value: bool):
        for var in self.vars.values():
            var.set(value)

    def _selected_keys(self) -> list:
        return [key for key, var in self.vars.items() if var.get()]

    def _set_running(self, state: bool):
        self.running = state
        normal_or_disabled = "disabled" if state else "normal"
        self.analyze_btn.configure(state=normal_or_disabled)
        self.clean_btn.configure(state=normal_or_disabled)
        self.stop_btn.configure(state="normal" if state else "disabled")
        # Пока идёт любая операция, вкладка «Установка» тоже блокируется.
        self._apply_installer_buttons(state)
        self._set_lang_switch_enabled(not state)
        # Блок WinSxS зависит и от общей занятости, и от своей собственной.
        self._render_winsxs_report()
        # Список крупнейших категорий актуален и до, и после операции.
        self._render_top_categories()
        # Центр сцены и левый рельс показывают то же состояние.
        self._refresh_core()
        self._refresh_telemetry()

    def _set_lang_switch_enabled(self, enabled: bool):
        """Блокирует переключатель языка на время операций."""
        if self._lang_switch is None:
            return
        try:
            # Список языков только для чтения: пользователь выбирает из него,
            # но не может вписать произвольный текст.
            self._lang_switch.configure(state="readonly" if enabled else "disabled")
        except Exception:
            pass

    def _update_category_info(self, key: str, text: str):
        widget = self._info_widgets.get(key)
        if widget is not None:
            widget.configure(text=text)

    def _top_row(self):
        """Создаёт одну строку списка и возвращает её части для переиспользования."""
        row = ctk.CTkFrame(self.top_box, fg_color="transparent")
        row.grid_columnconfigure(0, weight=1)
        title = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=11),
                             text_color=COLOR_TEXT, anchor="w")
        title.grid(row=0, column=0, sticky="w")
        value = ctk.CTkLabel(row, text="", font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=COLOR_MINT, anchor="e")
        value.grid(row=0, column=1, sticky="e", padx=(8, 0))
        bar = ctk.CTkProgressBar(row, height=4, corner_radius=2,
                                 fg_color=COLOR_LINE, progress_color=COLOR_ACCENT)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        return {"frame": row, "title": title, "value": value, "bar": bar}

    def _render_top_categories(self):
        """Все категории с найденным мусором, по убыванию объёма.

        Строки создаются один раз и дальше только обновляются: пересборка
        строк стоила ~30 мс, а вызывается этот метод на каждый старт
        и финиш операции. Список полный (прокручивается), а не «топ-5»:
        иначе найденные категории за пределами пятёрки не были видны.
        """
        box = getattr(self, "top_box", None)
        if box is None or getattr(self, "top_empty", None) is None:
            return

        items = [(key, int((res or {}).get("total_size") or 0))
                 for key, res in self.scan_results.items()]
        items = [item for item in items if item[1] > 0]
        items.sort(key=lambda item: item[1], reverse=True)

        if not items:
            # Пусто — показываем спокойную подсказку вместо пустоты.
            for row in self.top_rows:
                row["frame"].pack_forget()
            self._set_top_header(0)
            if not self.top_empty.winfo_manager():
                self.top_empty.pack(anchor="w")
            return

        if self.top_empty.winfo_manager():
            self.top_empty.pack_forget()
        self._set_top_header(len(items))

        while len(self.top_rows) < len(items):
            self.top_rows.append(self._top_row())

        heaviest = items[0][1] or 1
        for index, row in enumerate(self.top_rows):
            if index >= len(items):
                row["frame"].pack_forget()
                continue
            key, size = items[index]
            title = core.category_title(key)
            if len(title) > 34:
                # Обрезаем по границе слова: «(%TEMP%)» в конце рвать некрасиво.
                cut = title[:34]
                space = cut.rfind(" ")
                if space >= 18:
                    cut = cut[:space]
                title = cut.rstrip(" ,;·—(") + "…"
            row["title"].configure(text=title)
            row["value"].configure(text=core.format_bytes(size))
            share = min(1.0, size / float(heaviest))
            # Анимируем только верх списка: два десятка полос, ползущих
            # одновременно, заметно подтормаживают перерисовку.
            if index < 5:
                self._tween_bar(row["bar"], share)
            else:
                try:
                    row["bar"].set(share)
                except Exception:
                    pass
            row["frame"].pack(fill="x", pady=(0, 6))

    def _set_top_header(self, count: int):
        """Заголовок списка: «КРУПНЕЙШИЕ КАТЕГОРИИ · 9» (число найденных)."""
        label = getattr(self, "top_header", None)
        if label is None:
            return
        base = i18n.t("clean.top").upper()
        try:
            label.configure(text="{} · {}".format(base, count) if count else base)
        except Exception:
            pass

    # ================================================== ОБРАБОТКА ОЧЕРЕДИ
    def _poll_queue(self):
        # Подряд идущие строки журнала копим и вставляем одной пачкой: построчная
        # вставка с прокруткой стоит около 1 мс на строку, и очистка на несколько
        # тысяч файлов замораживала окно на десятки секунд.
        pending = []
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                if msg[0] == "log":
                    pending.append(msg[1])
                    continue
                if pending:
                    self._append_log_lines(pending)
                    pending = []
                try:
                    self._handle_message(msg)
                except Exception as exc:
                    # Ошибка в обработке одного сообщения не должна «ронять»
                    # обработчик очереди и терять остальные сообщения пачки.
                    self._append_log(i18n.t("log.ui_error") + repr(exc))
        except queue.Empty:
            pass
        finally:
            if pending:
                self._append_log_lines(pending)
            if not self._closing:
                self.after(100, self._poll_queue)

    def _handle_message(self, msg):
        """Обрабатывает одно сообщение от фонового воркера (в UI-потоке)."""
        kind = msg[0]
        if kind == "log":
            self._append_log(msg[1])
        elif kind == "status":
            self.status_label.configure(text=msg[1])
        elif kind == "progress":
            done, total = msg[1], msg[2]
            self._set_progress(0 if not total else done / total)
        elif kind == "progress_reset":
            self._set_progress(0)
        elif kind == "category":
            self._update_category_info(msg[1], msg[2])
        elif kind == "results_update":
            # Воркер прислал новые результаты скана — вливаем в главном потоке.
            self.scan_results.update(msg[1])
            # В заголовке свёрнутой группы показываем её суммарный объём,
            # чтобы её не приходилось раскрывать ради цифры.
            self._refresh_group_headers()
        elif kind == "results_clear":
            # После реальной очистки сбрасываем устаревшие результаты.
            for key in msg[1]:
                self.scan_results.pop(key, None)
            self._refresh_group_headers()
        elif kind == "freed_delta":
            # Накопление реально освобождённого места за сессию.
            self.total_freed += msg[1]
            self._total_text = i18n.t("clean.total_session",
                                      core.format_bytes(self.total_freed))
            self._apply_total_text()
        elif kind == "simulated_size":
            self._total_text = i18n.t("clean.total_sim", core.format_bytes(msg[1]))
            self._apply_total_text()
        elif kind == "done":
            self._set_running(False)
            self.status_label.configure(text=msg[1])
            if msg[2]:
                messagebox.showinfo(i18n.t("dlg.ok"), msg[2])
        elif kind == "installer_available":
            self.installer_available = bool(msg[1])
            self._refresh_installer_label()
        elif kind == "installer_log":
            # Подробный вывод установщика — в общий журнал, а в вкладке
            # «Установка» показываем последнюю строку как статус.
            self._append_log(msg[1])
            line = (msg[1] or "").strip()
            if line and self._module_built(1):
                self.install_status.configure(text=line[:150])
        elif kind == "installer_status":
            if self._module_built(1):
                self.install_status.configure(text=(msg[1] or "")[:150])
        elif kind == "installer_results":
            self._show_installer_results(msg[1])
        elif kind == "installer_done":
            self._set_installer_running(False)
            self.status_label.configure(text=msg[1])
            if msg[2]:
                messagebox.showinfo(i18n.t("dlg.ok"), msg[2])
        elif kind == "opt_status":
            self.opt_status.configure(text=(msg[1] or "")[:150])
        elif kind == "opt_item_start":
            self._opt_live_start(msg[1], msg[2], msg[3])
        elif kind == "opt_item_done":
            self._opt_live_done(msg[1], msg[2], msg[3])
        elif kind == "opt_progress":
            done, total = msg[1], msg[2]
            self.opt_progress.set(0 if not total else done / total)
        elif kind == "opt_done":
            self._set_running(False)
            self.status_label.configure(text=i18n.t("status.opt_done"))
            self.opt_status.configure(text=i18n.t("status.done"))
            self._opt_live_finish()
            # Запоминаем балл до правок и меряем заново: карточка покажет
            # «было → стало», то есть реальный эффект, а не обещание.
            if getattr(self, "_diag_report", None):
                self._diag_baseline = int(self._diag_report.get("score") or 0)
                self.after(200, self._run_diagnose)
            if msg[1]:
                messagebox.showinfo(i18n.t("dlg.optimization"), msg[1])
        elif kind == "diag_report":
            report = msg[1] or {}
            self._render_diag(report)
            # Разбор пишем в журнал: это след, по которому видно, что
            # программа нашла и с каким баллом.
            self._append_log(i18n.t("log.diag_report",
                                    report.get("score", 0),
                                    len(report.get("causes") or [])))
        elif kind == "restore_point_done":
            self._set_running(False)
            self.status_label.configure(text=i18n.t("status.restore_done"))
            self.opt_status.configure(text=i18n.t("status.done"))
            if msg[1]:
                messagebox.showinfo(i18n.t("dlg.restore_done"), msg[1])
        elif kind == "winsxs_progress":
            if self.winsxs_progress is not None:
                self.winsxs_progress.set(msg[1])
        elif kind == "winsxs_report":
            self.winsxs_report = msg[1]
            self._render_winsxs_report()
            recommended = (msg[1] or {}).get("recommended")
            if recommended is not None:
                self._append_log(i18n.t(
                    "log.winsxs_recommended",
                    i18n.t("winsxs.need_yes") if recommended
                    else i18n.t("winsxs.need_no")))
        elif kind == "winsxs_cleaned":
            result = msg[1] or {}
            if result.get("ok"):
                self._append_log(i18n.t("log.winsxs_clean_done"))
                self.status_label.configure(text=i18n.t("log.winsxs_clean_done"))
                # После очистки прежний отчёт устарел — просим проверить снова.
                self.winsxs_report = None
                self._render_winsxs_report()
                messagebox.showinfo(i18n.t("dlg.winsxs_title"),
                                    i18n.t("log.winsxs_clean_done"))
            else:
                self._append_log(i18n.t("log.winsxs_failed",
                                        result.get("code")))
                messagebox.showwarning(i18n.t("dlg.winsxs_title"),
                                       i18n.t("winsxs.fail_generic"))
        elif kind == "winsxs_done":
            self._set_winsxs_busy(False)
            self._set_running(False)
        elif kind == "sched_trigger":
            # Планировщик (фоновый поток) просит запустить очистку.
            self._run_scheduled_clean()
        elif kind == "sched_running":
            # Тихая плановая очистка: как _set_running, но БЕЗ всплывающих окон.
            self._set_running(msg[1])
        elif kind == "sched_status":
            if self.sched_status_label is not None:
                self.sched_status_label.configure(text=msg[1])

    def _check_installer_worker(self):
        """Фоновая проверка готовности безопасного установщика (не блокирует UI)."""
        try:
            available = inst.is_installer_available()
        except Exception:
            available = False
        self.msg_queue.put(("installer_available", available))

    def _refresh_installer_label(self):
        """Показывает статус установщика на текущем языке (None — ещё проверяется)."""
        label = getattr(self, "installer_label", None)
        if label is None:
            # Модуль «Установка» ещё не открывали — подпись появится при сборке.
            return
        if self.installer_available is None:
            label.configure(text=i18n.t("installer.checking"),
                            text_color=COLOR_MUTED)
        elif self.installer_available:
            label.configure(text=i18n.t("installer.ok"), text_color=COLOR_GREEN)
        else:
            label.configure(text=i18n.t("installer.missing"), text_color=COLOR_RED)

    def _on_close(self):
        """Закрытие окна: останавливаем фоновые операции и завершаем работу."""
        if self.winsxs_cleaning:
            # DISM-очистку нельзя прервать: процесс продолжит работу уже
            # без окна программы, поэтому предупреждаем отдельно.
            if not messagebox.askyesno(i18n.t("dlg.winsxs_title"),
                                       i18n.t("dlg.winsxs_close")):
                return
        elif self.running:
            # Закрытие во время очистки/установки обрывает операцию на середине:
            # спрашиваем подтверждение, чтобы это не было неожиданностью.
            if not messagebox.askyesno(i18n.t("dlg.close_title"),
                                       i18n.t("dlg.close_text")):
                return
        self._closing = True
        if self.running:
            self.stop_event.set()
        # Останавливаем фоновый планировщик тихой очистки.
        try:
            self.schedule_stop_event.set()
        except Exception:
            pass
        self.destroy()

    # ------------------------------------------- список найденных пакетов
    @staticmethod
    def _short(text: str, limit: int) -> str:
        """Обрезает слишком длинный текст, добавляя многоточие."""
        text = text or ""
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _build_result_header(self):
        """Строит строку-заголовок таблицы пакетов (row 0 в той же сетке).

        Заголовок лежит в том же контейнере, что и строки данных, поэтому
        колонки всегда совпадают и не «уезжают» из-за скроллбара.
        """
        if self.pkg_header is not None:
            self.pkg_header.destroy()
        header = ctk.CTkFrame(self.results_scroll, fg_color=COLOR_CARD_2, corner_radius=8)
        header.grid(row=0, column=0, columnspan=4, sticky="ew", padx=2, pady=(0, 4))
        header.grid_columnconfigure(0, minsize=40)
        header.grid_columnconfigure(1, weight=3)
        header.grid_columnconfigure(2, weight=4)
        header.grid_columnconfigure(3, minsize=90)
        cells = (
            (i18n.t("install.col_num"), 40, (10, 0)),
            (i18n.t("install.col_name"), 0, (4, 10)),
            (i18n.t("install.col_id"), 0, (0, 10)),
            (i18n.t("install.col_version"), 90, (0, 10)),
        )
        for col, (text, width, padx) in enumerate(cells):
            ctk.CTkLabel(header, text=text, width=width, anchor="w",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=COLOR_ACCENT).grid(row=0, column=col,
                                                       sticky="w", padx=padx)
        self.pkg_header = header

    def _clear_results(self, hint: str = ""):
        """Удаляет строки списка и (необязательно) показывает подсказку."""
        for widget in self.pkg_rows:
            widget.destroy()
        self.pkg_rows = []
        self.pkg_cells = []
        if self.pkg_header is not None:
            self.pkg_header.destroy()
            self.pkg_header = None
        if hint:
            label = ctk.CTkLabel(self.results_scroll, text=hint,
                                 font=ctk.CTkFont(size=12),
                                 text_color=COLOR_MUTED, justify="left", anchor="w")
            label.grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=14)
            self.pkg_rows.append(label)
            return
        self._build_result_header()

    def _paint_row(self, index: int, selected: bool):
        """Перекрашивает строку списка (фон и цвет текста)."""
        if not (0 <= index < len(self.pkg_cells)):
            return
        row = self.pkg_rows[index]
        if not isinstance(row, ctk.CTkFrame):
            return
        row.configure(fg_color=COLOR_ROW_SELECTED if selected else COLOR_CARD)
        # На тёмно-синем фоне серый текст нечитаем — делаем его светлым.
        if selected:
            colors = ("#dbeafe", "#ffffff", "#dbeafe", "#dbeafe")
        else:
            colors = (COLOR_MUTED, COLOR_TEXT, COLOR_MUTED, COLOR_MUTED)
        for cell, color in zip(self.pkg_cells[index], colors):
            cell.configure(text_color=color)

    def _show_installer_results(self, results: list):
        """Строит кликабельный список найденных пакетов."""
        # Панель «Установка» строится лениво — список живёт внутри неё.
        self._ensure_module(1)
        self.installer_results = results
        self.selected_pkg = None
        self.selected_row = None
        self.pkg_label.configure(text=i18n.t("pkg.not_selected"),
                                 text_color=COLOR_MUTED)
        self.results_count.configure(
            text=i18n.t("install.count", len(results)) if results else "")

        if not results:
            self._clear_results(i18n.t("install.no_results"))
            self.install_status.configure(text=i18n.t("pkg.nothing_found"))
            self._apply_installer_buttons(self.running)
            return

        self._clear_results()
        # Список виджетов ограничиваем: каталог на общий запрос может вернуть
        # сотни строк, и создание тысяч элементов «подвешивает» окно.
        # Полный список остаётся в self.installer_results — выбор по номеру
        # и по ID работает для всех найденных пакетов.
        visible = results[:MAX_RESULT_ROWS]
        for index, item in enumerate(visible):
            row = ctk.CTkFrame(self.results_scroll, fg_color=COLOR_CARD, corner_radius=8)
            # row 0 занят шапкой таблицы, строки данных начинаются с row 1.
            row.grid(row=index + 1, column=0, columnspan=4, sticky="ew", padx=2, pady=1)
            row.grid_columnconfigure(0, minsize=40)
            row.grid_columnconfigure(1, weight=3)
            row.grid_columnconfigure(2, weight=4)
            row.grid_columnconfigure(3, minsize=90)

            cells = []
            cells.append(ctk.CTkLabel(row, text=str(index + 1), width=40, anchor="w",
                                      font=ctk.CTkFont(size=12), text_color=COLOR_MUTED))
            cells.append(ctk.CTkLabel(row, text=self._short(item["name"], 48), anchor="w",
                                      font=ctk.CTkFont(size=12, weight="bold"),
                                      text_color=COLOR_TEXT))
            cells.append(ctk.CTkLabel(row, text=self._short(item["id"], 46), anchor="w",
                                      font=ctk.CTkFont(family="Consolas", size=11),
                                      text_color=COLOR_MUTED))
            cells.append(ctk.CTkLabel(row, text=item["version"] or "—", width=90, anchor="w",
                                      font=ctk.CTkFont(size=11), text_color=COLOR_MUTED))

            cells[0].grid(row=0, column=0, sticky="w", padx=(10, 0), pady=6)
            cells[1].grid(row=0, column=1, sticky="w", padx=(4, 10))
            cells[2].grid(row=0, column=2, sticky="w", padx=(0, 10))
            cells[3].grid(row=0, column=3, sticky="w", padx=(0, 10))

            # Клик по любому элементу строки выбирает пакет.
            for widget in [row] + cells:
                widget.bind("<Button-1>",
                            lambda event, i=index: self.select_package(i))

            self.pkg_rows.append(row)
            self.pkg_cells.append(cells)

        self.install_status.configure(
            text=i18n.t("install.found", len(results)))
        if len(results) > len(visible):
            self.results_count.configure(
                text=i18n.t("install.truncated", len(visible), len(results)))
        self._apply_installer_buttons(self.running)

    def select_package(self, index: int):
        """Выбирает пакет по индексу в списке результатов."""
        if not (0 <= index < len(self.installer_results)):
            return
        self._ensure_module(1)
        pkg = self.installer_results[index]
        self.selected_pkg = pkg
        self.selected_row = index

        for i in range(len(self.pkg_cells)):
            self._paint_row(i, i == index)

        self.pkg_label.configure(
            text=i18n.t("pkg.selected", self._short(pkg["name"], 40), pkg["id"]),
            text_color=COLOR_TEXT)
        self.pkg_entry.delete(0, "end")
        self.pkg_entry.insert(0, pkg["id"])
        self.install_status.configure(text=i18n.t("pkg.chosen"))
        self._apply_installer_buttons(self.running)
        self.status_label.configure(text=i18n.t("pkg.selected_status", pkg["id"]))

    def on_select_pkg(self):
        """Выбирает пакет по номеру из списка или по ID, введённому вручную."""
        text = self.pkg_entry.get().strip()
        if not text:
            messagebox.showinfo(i18n.t("dlg.pkg_select_title"),
                                i18n.t("dlg.pkg_select_text"))
            return

        # 1) Число — берём пакет по номеру из результатов поиска.
        if text.isdigit():
            index = int(text)
            if 1 <= index <= len(self.installer_results):
                self.select_package(index - 1)
                return
            messagebox.showwarning(
                i18n.t("dlg.bad_number_title"),
                i18n.t("dlg.bad_number_text", len(self.installer_results),
                       len(self.installer_results)))
            return

        # 2) Иначе ищем по ID среди найденных (без учёта регистра).
        lowered = text.lower()
        for index, item in enumerate(self.installer_results):
            if item["id"].lower() == lowered:
                self.select_package(index)
                return

        # 3) Не нашли — считаем введённое значение ID пакета (ручной ввод).
        # ID проверяем до сохранения: он попадёт в аргументы установщика, поэтому
        # не должен содержать пробелов, кавычек и начинаться с дефиса.
        if not inst.is_valid_package_id(text):
            messagebox.showwarning(
                i18n.t("dlg.pkg_select_title"),
                i18n.t("inst.bad_id", self._short(text, 60)))
            return

        self.selected_pkg = {"name": text, "id": text, "version": "",
                             "source": i18n.t("pkg.source_manual")}
        self.selected_row = None
        self._ensure_module(1)
        for i in range(len(self.pkg_cells)):
            self._paint_row(i, False)
        self.pkg_label.configure(text=i18n.t("pkg.manual", text), text_color=COLOR_TEXT)
        self.install_status.configure(text=i18n.t("pkg.manual_set", text))
        self._apply_installer_buttons(self.running)

    def _apply_installer_buttons(self, busy: bool):
        """Включает/выключает кнопки вкладки «Установка» по состоянию busy."""
        # Панели строятся лениво: если «Установку» ещё не открывали, кнопок
        # нет — их состояние выставится при сборке панели.
        if not self._module_built(1):
            return
        self.search_btn.configure(state="disabled" if busy else "normal")
        self.upgrade_all_btn.configure(state="disabled" if busy else "normal")
        self.vc_btn.configure(state="disabled" if busy else "normal")
        for button in getattr(self, "preset_buttons", {}).values():
            button.configure(state="disabled" if busy else "normal")
        if self._module_built(2):
            if getattr(self, "opt_apply_btn", None):
                self.opt_apply_btn.configure(state="disabled" if busy else "normal")
            if getattr(self, "opt_restore_btn", None):
                self.opt_restore_btn.configure(state="disabled" if busy else "normal")
        self.select_btn.configure(state="disabled" if busy else "normal")
        can_act = (not busy) and bool(self.selected_pkg)
        self.install_pkg_btn.configure(state="normal" if can_act else "disabled")
        self.upgrade_pkg_btn.configure(state="normal" if can_act else "disabled")

    def _set_installer_running(self, state: bool):
        self.running = state
        self._apply_installer_buttons(state)
        # Блокируем и вкладку «Очистка», чтобы интерфейс оставался целостным.
        if state:
            self.analyze_btn.configure(state="disabled")
            self.clean_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
        else:
            self.analyze_btn.configure(state="normal")
            self.clean_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

    # ================================================ ХРАНИЛИЩЕ КОМПОНЕНТОВ
    def _render_winsxs_report(self):
        """Перерисовывает блок WinSxS по сохранённому отчёту DISM."""
        if self.winsxs_state is None:
            return
        busy = self.running or self.winsxs_busy
        report = self.winsxs_report

        if not report:
            self.winsxs_state.configure(text=i18n.t("winsxs.state_unknown"),
                                        text_color=COLOR_MUTED)
            self.winsxs_detail.configure(text=i18n.t("winsxs.hint"),
                                         text_color=COLOR_MUTED)
            self.winsxs_check_btn.configure(text=i18n.t("winsxs.check"),
                                            state="disabled" if busy else "normal")
            self.winsxs_clean_btn.configure(state="disabled")
            return

        if not report.get("ok"):
            reason = report.get("reason") or ""
            if reason == "stopped":
                # Пользователь сам остановил проверку — это не ошибка.
                self.winsxs_state.configure(text=i18n.t("winsxs.state_unknown"),
                                            text_color=COLOR_MUTED)
                self.winsxs_detail.configure(text=i18n.t("winsxs.stopped"),
                                             text_color=COLOR_MUTED)
                self.winsxs_check_btn.configure(text=i18n.t("winsxs.check"),
                                                state="disabled" if busy else "normal")
                self.winsxs_clean_btn.configure(state="disabled")
                return
            if reason == "no_admin":
                detail = i18n.t("winsxs.fail_admin")
            elif reason == "unparsed":
                detail = i18n.t("winsxs.fail_unparsed")
            else:
                detail = i18n.t("winsxs.fail_generic")
            self.winsxs_state.configure(text=i18n.t("winsxs.state_fail"),
                                        text_color=COLOR_RED)
            self.winsxs_detail.configure(text=detail, text_color=COLOR_MUTED)
            self.winsxs_check_btn.configure(text=i18n.t("winsxs.check"),
                                            state="disabled" if busy else "normal")
            self.winsxs_clean_btn.configure(state="disabled")
            return

        recommended = report.get("recommended")
        if recommended is True:
            self.winsxs_state.configure(text=i18n.t("winsxs.state_yes"),
                                        text_color=COLOR_WARN)
        elif recommended is False:
            self.winsxs_state.configure(text=i18n.t("winsxs.state_no"),
                                        text_color=COLOR_GREEN)
        else:
            self.winsxs_state.configure(text=i18n.t("winsxs.state_unknown"),
                                        text_color=COLOR_MUTED)

        parts = []
        if report.get("actual"):
            if recommended is True:
                parts.append(i18n.t("winsxs.detail",
                                    core.format_bytes(report["actual"]),
                                    core.format_bytes(report.get("reclaimable") or 0)))
            else:
                # DISM сказал «нет» — не обещаем освобождение, которого не будет:
                # рядом с «чистить не надо» цифра «освободится» только путает.
                parts.append(i18n.t("winsxs.detail_no",
                                    core.format_bytes(report["actual"])))
        if report.get("packages") is not None:
            parts.append(i18n.t("winsxs.detail_pkgs", report["packages"]))
        if report.get("last_cleanup"):
            parts.append(i18n.t("winsxs.last", report["last_cleanup"]))
        self.winsxs_detail.configure(
            text=" · ".join(parts) if parts else i18n.t("winsxs.hint"),
            text_color=COLOR_MUTED)

        self.winsxs_check_btn.configure(text=i18n.t("winsxs.recheck"),
                                        state="disabled" if busy else "normal")
        self.winsxs_clean_btn.configure(
            state="normal" if (recommended is True and not busy) else "disabled")

    def _set_winsxs_busy(self, state: bool):
        """Блокирует блок WinSxS на время операции DISM."""
        self.winsxs_busy = state
        if state:
            if self.winsxs_progress is not None:
                self.winsxs_progress.pack(fill="x", padx=12, pady=(0, 10))
        else:
            self.winsxs_cleaning = False
            if self.winsxs_progress is not None:
                self.winsxs_progress.set(0)
                self.winsxs_progress.pack_forget()
        self._render_winsxs_report()

    def on_winsxs_check(self):
        """Проверка хранилища компонентов официальной командой DISM."""
        if self.running or self.winsxs_busy:
            return
        if not core.is_admin():
            messagebox.showwarning(i18n.t("dlg.winsxs_title"),
                                   i18n.t("winsxs.fail_admin"))
            return
        # Старый отчёт больше не актуален — иначе на экране висел бы
        # прежний ответ «Да/Нет» во время новой проверки.
        self.winsxs_report = None
        # Флаг остановки мог остаться поднятым с прошлого раза — иначе новая
        # проверка оборвалась бы на первом же шаге.
        self.stop_event.clear()
        self._set_running(True)
        self._set_winsxs_busy(True)
        # Проверку прерывать безопасно: она ничего не меняет.
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text=i18n.t("winsxs.checking"))
        self._append_log("")
        self._append_log(i18n.t("log.winsxs_start"))
        threading.Thread(target=self._winsxs_check_worker, daemon=True).start()

    def _winsxs_check_worker(self):
        def log(text):
            line = (text or "").strip()
            if not line or line.startswith("["):
                return          # прогресс-бар DISM в журнал не пишем
            self.msg_queue.put(("log", line))

        def progress(value):
            self.msg_queue.put(("winsxs_progress", value))

        try:
            report = core.analyze_component_store(
                on_line=log, on_progress=progress, stop_event=self.stop_event)
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            report = {"ok": False, "reason": "failed", "output": ""}
        self.msg_queue.put(("winsxs_report", report))
        self.msg_queue.put(("winsxs_done", False))

    def on_winsxs_clean(self):
        """Очистка хранилища компонентов официальной командой DISM."""
        if self.running or self.winsxs_busy:
            return
        if not core.is_admin():
            messagebox.showwarning(i18n.t("dlg.winsxs_title"),
                                   i18n.t("winsxs.fail_admin"))
            return
        # Очистку запускаем только по свежему вердикту DISM «Да».
        # Кнопка и так заблокирована, но проверка защищает от устаревшего отчёта.
        if (self.winsxs_report or {}).get("recommended") is not True:
            return
        reclaim = (self.winsxs_report or {}).get("reclaimable") or 0
        if not messagebox.askyesno(
                i18n.t("dlg.winsxs_title"),
                i18n.t("dlg.winsxs_text", core.format_bytes(reclaim))):
            return
        # Снимаем флаг прошлой остановки: иначе очистка откажется стартовать.
        self.stop_event.clear()
        self._set_running(True)
        self._set_winsxs_busy(True)
        self.winsxs_cleaning = True
        # Очистку прерывать нельзя — кнопка «Стоп» блокируется.
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text=i18n.t("winsxs.cleaning"))
        self._append_log("")
        self._append_log(i18n.t("log.winsxs_clean_start"))
        threading.Thread(target=self._winsxs_clean_worker, daemon=True).start()

    def _winsxs_clean_worker(self):
        def log(text):
            line = (text or "").strip()
            if not line or line.startswith("["):
                return
            self.msg_queue.put(("log", line))

        def progress(value):
            self.msg_queue.put(("winsxs_progress", value))

        try:
            result = core.cleanup_component_store(
                on_line=log, on_progress=progress)
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            result = {"ok": False, "reason": "failed", "code": -1, "output": ""}
        self.msg_queue.put(("winsxs_cleaned", result))
        self.msg_queue.put(("winsxs_done", True))

    # ============================================================== ДЕЙСТВИЯ (clean)
    def on_stop(self):
        self.stop_event.set()
        self.status_label.configure(text=i18n.t("status.stopping"))
        self._append_log(i18n.t("log.stop_requested"))

    def on_analyze(self):
        if self.running:
            return
        keys = self._selected_keys()
        if not keys:
            messagebox.showinfo(i18n.t("dlg.no_categories_title"),
                                i18n.t("dlg.no_categories_text"))
            return
        self._start_clean_worker(mode="scan", keys=keys,
                                 selected_map=self._browser_selected_map())

    def on_clean(self):
        if self.running:
            return
        keys = self._selected_keys()
        if not keys:
            messagebox.showinfo(i18n.t("dlg.no_categories_title"),
                                i18n.t("dlg.no_categories_text"))
            return
        # Если выбраны категории браузеров и они сейчас запущены — спрашиваем,
        # закрыть их перед очисткой (иначе их кэш/куки заняты и будут пропущены).
        browser_keys = [key for key in keys if key in core.BROWSER_KEYS]
        if browser_keys:
            running = core.get_running_browsers(browser_keys)
            if running:
                names = ", ".join(i18n.fld(core.BROWSERS[k], "title") for k in running)
                if messagebox.askyesno(
                        i18n.t("dlg.browser_running_title"),
                        i18n.t("dlg.browser_running_text", names)):
                    self._append_log(i18n.t("log.browsers_closing", names))
                    closed = core.close_browsers(running)
                    if closed:
                        self._append_log(i18n.t("log.browsers_closed", names))
                    else:
                        self._append_log(i18n.t("log.browsers_close_failed", names))
        dry_run = self.scan_only_var.get()
        if not dry_run:
            if not messagebox.askyesno(
                    i18n.t("dlg.confirm_clean_title"),
                    i18n.t("dlg.confirm_clean_text")):
                return
        self._start_clean_worker(mode="clean", keys=keys, dry_run=dry_run,
                                 selected_map=self._browser_selected_map())

    def _start_clean_worker(self, mode: str, keys: list, dry_run: bool = True,
                            selected_map=None):
        self._set_running(True)
        self.stop_event.clear()
        self._set_progress(0)
        # Переиспользуем результаты уже проведённого анализа (только для очистки)
        # глубокой копией — чтобы удаление не меняло сохранённые результаты скана.
        reusable = {}
        if mode == "clean":
            reusable = {key: copy.deepcopy(self.scan_results[key])
                        for key in keys if key in self.scan_results}
        thread = threading.Thread(
            target=self._clean_worker,
            args=(mode, keys, dry_run, reusable, selected_map),
            daemon=True,
        )
        thread.start()

    def _clean_worker(self, mode: str, keys: list, dry_run: bool, results: dict,
                     selected_map=None):
        def log(text):
            self.msg_queue.put(("log", text))
        def status(text):
            self.msg_queue.put(("status", text))
        def on_progress(done, total):
            self.msg_queue.put(("progress", done, total))

        try:
            # Сканируем только те категории, которых ещё нет в результатах
            # (для «Анализа» — все, для «Очистки» — только недостающие).
            missing = [key for key in keys if key not in results]
            if missing:
                status(i18n.t("status.scanning"))
                log("")
                log(i18n.t("log.scan_header"))
                scanned = core.scan_categories(missing, on_log=log, on_status=status,
                                               stop_event=self.stop_event,
                                               selected_map=selected_map)
                results.update(scanned)
                # Общий словарь обновляем В ГЛАВНОМ ПОТОКЕ через очередь:
                # воркер не должен мутировать scan_results, пока UI его читает
                # (иначе «dictionary changed size during iteration»).
                self.msg_queue.put(("results_update", scanned))
                for key, res in results.items():
                    self.msg_queue.put(("category", key,
                                        "{} | {}".format(core.format_bytes(res["total_size"]),
                                                         res["total_count"])))
                log(i18n.t("log.scan_total",
                           core.format_bytes(sum(r["total_size"] for r in results.values()))))

            if mode == "scan":
                grand_size = sum(r["total_size"] for r in results.values())
                total_count = sum(r["total_count"] for r in results.values())
                self.msg_queue.put(("done",
                                    i18n.t("log.analysis_status",
                                           core.format_bytes(grand_size)),
                                    i18n.t("log.analysis_text", total_count,
                                           core.format_bytes(grand_size))))
                return

            # Проверка запущенных браузеров выполняется в фоне (в воркере),
            # чтобы не «замораживать» интерфейс. Это только предупреждение в журнал.
            browser_keys = [key for key in keys if key in core.BROWSER_KEYS]
            if browser_keys:
                running = core.get_running_browsers(browser_keys)
                if running:
                    names = ", ".join(i18n.fld(core.BROWSERS[k], "title") for k in running)
                    log("")
                    log(i18n.t("log.browsers_busy", names))

            status(i18n.t("status.cleaning"))
            log("")
            log(i18n.t("log.clean_header",
                       i18n.t("log.mode_sim") if dry_run else i18n.t("log.mode_real")))
            summary = core.clean_categories(
                results, dry_run=dry_run, on_log=log, on_status=status,
                on_progress=on_progress, stop_event=self.stop_event)
            if dry_run:
                self.msg_queue.put(("simulated_size", summary["freed"]))
            else:
                self.msg_queue.put(("freed_delta", summary["freed"]))
                # После реальной очистки сохранённые результаты скана устарели:
                # если их не сбросить, повторная «Очистка» возьмёт старый список
                # файлов, которых уже нет, и покажет «освобождено 0 Б».
                if not self.stop_event.is_set():
                    for key in list(results.keys()):
                        self.msg_queue.put(("category", key, "{} | 0".format(
                            core.format_bytes(0))))
                    # Сброс устаревших результатов — тоже в главном потоке.
                    self.msg_queue.put(("results_clear", list(results.keys())))
            result_text = i18n.t(
                "log.clean_result",
                i18n.t("log.sim_done") if dry_run else i18n.t("log.clean_done"),
                summary["removed"], summary["skipped"], summary["errors"],
                core.format_bytes(summary["freed"]))
            log("")
            log(i18n.t("log.result_header"))
            log(result_text)
            self.msg_queue.put(("done", i18n.t("status.done"), result_text))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("done", i18n.t("log.finished_error"),
                                i18n.t("log.error_text", exc)))
        finally:
            self.msg_queue.put(("progress_reset",))

    # ============================================================== ДЕЙСТВИЯ (installer)
    def on_search(self):
        if self.running:
            return
        self._ensure_module(1)
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showinfo(i18n.t("dlg.empty_query_title"),
                                i18n.t("dlg.empty_query_text"))
            return
        if self.installer_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.installer_title"),
                i18n.t("dlg.installer_text"))
            return
        self._set_installer_running(True)
        self.selected_pkg = None
        self.selected_row = None
        self.pkg_entry.delete(0, "end")
        self.pkg_label.configure(text=i18n.t("pkg.not_selected"),
                                 text_color=COLOR_MUTED)
        self.install_status.configure(text=i18n.t("pkg.searching", query))
        self.results_count.configure(text="")
        self._clear_results(i18n.t("pkg.searching", query))

        thread = threading.Thread(
            target=self._search_worker,
            args=(query,),
            daemon=True,
        )
        thread.start()

    def _search_worker(self, query: str):
        def log(text):
            self.msg_queue.put(("installer_log", text))
        try:
            results = inst.search_packages(query, on_log=log)
            self.msg_queue.put(("installer_results", results))
            self.msg_queue.put(("installer_done", i18n.t("log.search_done"), ""))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("installer_done", i18n.t("log.search_error"), str(exc)))

    def on_install_preset(self, preset: dict):
        """Открывает выбор программ набора и ставит только отмеченные.

        Список наборов — это подсказка «что обычно нужно», поэтому ставить
        весь набор целиком нельзя: сначала пользователь отмечает галочками
        нужные программы, и только они попадают в установщик.
        """
        if self.running:
            return
        if self.installer_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.installer_title"),
                i18n.t("dlg.installer_text"))
            return

        dialog = PresetDialog(self, preset)
        self.wait_window(dialog)          # ждём закрытия окна выбора
        packages = dialog.result
        if not packages:
            return

        title = i18n.fld(preset, "title")
        self._set_installer_running(True)
        self.install_status.configure(text=i18n.t("pkg.installing_set", title))
        self.results_count.configure(text="")
        self._clear_results(i18n.t("install.preset_hint", title))
        thread = threading.Thread(
            target=self._install_preset_worker,
            args=(preset, packages),
            daemon=True,
        )
        thread.start()

    def _install_preset_worker(self, preset: dict, packages: list):
        """Фоновая установка отмеченных программ набора."""
        def log(text):
            self.msg_queue.put(("installer_log", text))
        try:
            log("")
            log(i18n.t("log.preset_header", i18n.fld(preset, "title")))
            ok, msg = inst.install_packages(packages, on_log=log)
            log("")
            log(i18n.t("log.result_prefix",
                       i18n.t("log.preset_all_ok") if ok
                       else i18n.t("log.preset_partial")))
            log(msg[:3000])
            text = (i18n.t("msg.preset_done", len(packages)) if ok
                    else i18n.t("msg.preset_partial"))
            self.msg_queue.put(("installer_done",
                                i18n.t("status.done") if ok else i18n.t("dlg.error"),
                                text))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("installer_done", i18n.t("dlg.error"), str(exc)))

    def on_install_pkg(self):
        if self.running or not self.selected_pkg:
            return
        pkg_id = self.selected_pkg["id"]
        if not messagebox.askyesno(i18n.t("dlg.confirm"),
                                   i18n.t("dlg.install_pkg_text", pkg_id)):
            return
        self._set_installer_running(True)
        thread = threading.Thread(
            target=self._install_worker,
            args=(pkg_id, False),
            daemon=True,
        )
        thread.start()

    def on_upgrade_pkg(self):
        if self.running or not self.selected_pkg:
            return
        pkg_id = self.selected_pkg["id"]
        if not messagebox.askyesno(i18n.t("dlg.confirm"),
                                   i18n.t("dlg.upgrade_pkg_text", pkg_id)):
            return
        self._set_installer_running(True)
        thread = threading.Thread(
            target=self._install_worker,
            args=(pkg_id, True),
            daemon=True,
        )
        thread.start()

    def on_upgrade_all(self):
        if self.running:
            return
        if self.installer_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.installer_title"),
                i18n.t("dlg.installer_text"))
            return
        if not messagebox.askyesno(i18n.t("dlg.confirm"),
                                   i18n.t("dlg.upgrade_all_text")):
            return
        self._set_installer_running(True)
        self.install_status.configure(text=i18n.t("pkg.upgrading_all"))
        self.results_count.configure(text="")
        self._clear_results(i18n.t("install.upgrading_all_hint"))
        thread = threading.Thread(
            target=self._upgrade_all_worker,
            daemon=True,
        )
        thread.start()

    def _install_worker(self, pkg_id: str, is_upgrade: bool):
        def log(text):
            self.msg_queue.put(("installer_log", text))
        try:
            log("")
            if is_upgrade:
                log(i18n.t("log.upgrade_header"))
                self.msg_queue.put(("installer_status",
                                    i18n.t("pkg.updating", pkg_id)))
                ok, msg = inst.upgrade_package(pkg_id, on_log=log)
            else:
                log(i18n.t("log.install_header"))
                self.msg_queue.put(("installer_status",
                                    i18n.t("pkg.installing", pkg_id)))
                ok, msg = inst.install_package(pkg_id, on_log=log)
            log("")
            log(i18n.t("log.result_prefix",
                       i18n.t("log.success") if ok else i18n.t("log.failure")))
            log(msg[:3000])
            if ok:
                text = i18n.t("msg.upgrade_done") if is_upgrade else i18n.t("msg.install_done")
            else:
                text = i18n.t("msg.upgrade_error") if is_upgrade else i18n.t("msg.install_error")
            self.msg_queue.put(("installer_done",
                                i18n.t("status.done") if ok else i18n.t("dlg.error"),
                                text))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("installer_done", i18n.t("dlg.error"), str(exc)))

    def _upgrade_all_worker(self):
        def log(text):
            self.msg_queue.put(("installer_log", text))
        try:
            log("")
            log(i18n.t("log.upgrade_all_header"))
            ok, msg = inst.upgrade_all(on_log=log)
            no_updates = inst.is_no_updates(msg)
            log("")
            if no_updates:
                log(i18n.t("log.result_prefix", i18n.t("log.no_updates")))
            else:
                log(i18n.t("log.result_prefix",
                           i18n.t("log.success") if ok else i18n.t("log.failure")))
            log(msg[:3000])
            if no_updates:
                text = i18n.t("msg.no_updates")
            elif ok:
                text = i18n.t("msg.upgrade_done")
            else:
                text = i18n.t("msg.upgrade_error")
            self.msg_queue.put(("installer_done",
                                i18n.t("status.done") if ok else i18n.t("dlg.error"),
                                text))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("installer_done", i18n.t("dlg.error"), str(exc)))

    def on_install_vc(self):
        """Устанавливает ВСЕ Visual C++ Redistributable (2005–2022, x86 и x64)."""
        if self.running:
            return
        if self.installer_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.installer_title"),
                i18n.t("dlg.installer_text"))
            return
        count = len(inst.VC_REDIST_PACKAGES)
        if not messagebox.askyesno(
                i18n.t("dlg.confirm"),
                i18n.t("dlg.vc_text", count)):
            return
        self._set_installer_running(True)
        self.install_status.configure(text=i18n.t("pkg.installing_vc"))
        self._clear_results(i18n.t("install.vc_hint"))
        thread = threading.Thread(target=self._install_vc_worker, daemon=True)
        thread.start()

    def _install_vc_worker(self):
        def log(text):
            self.msg_queue.put(("installer_log", text))
        try:
            log("")
            log(i18n.t("log.vc_header"))
            ok, msg = inst.install_packages(inst.VC_REDIST_PACKAGES, on_log=log)
            log("")
            log(i18n.t("log.result_prefix",
                       i18n.t("log.vc_all_ok") if ok else i18n.t("log.vc_partial")))
            log(msg[:3000])
            text = i18n.t("msg.vc_done") if ok else i18n.t("msg.vc_partial")
            self.msg_queue.put(("installer_done",
                                i18n.t("status.done") if ok else i18n.t("dlg.error"),
                                text))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("installer_done", i18n.t("dlg.error"), str(exc)))

    # ============================================================== ДЕЙСТВИЯ (optimize)
    def on_optimize(self):
        """Применяет выбранные оптимизации Windows."""
        if self.running:
            return
        keys = self._selected_opt_keys()
        if not keys:
            messagebox.showinfo(i18n.t("dlg.no_items_title"),
                                i18n.t("dlg.no_items_text"))
            return
        # Отдельное подтверждение для отключения гибернации.
        if "hibernate" in keys:
            if not messagebox.askyesno(
                    i18n.t("dlg.hibernate_title"),
                    i18n.t("dlg.hibernate_text")):
                keys.remove("hibernate")
                if not keys:
                    return
        # Отдельное подтверждение для удаления встроенных приложений.
        if "debloat_apps" in keys:
            if not messagebox.askyesno(
                    i18n.t("dlg.debloat_title"),
                    i18n.t("dlg.debloat_text")):
                keys.remove("debloat_apps")
                if not keys:
                    return
        self._set_running(True)
        self.stop_event.clear()
        self.opt_status.configure(text=i18n.t("opt.running"))
        self.opt_progress.set(0)
        self._opt_live_show(keys)
        thread = threading.Thread(
            target=self._optimize_worker, args=(keys,), daemon=True)
        thread.start()

    def on_create_restore_point(self):
        """Создаёт точку восстановления системы через PowerShell."""
        if self.running:
            return
        self._set_running(True)
        self.opt_status.configure(text=i18n.t("opt.restore_running"))
        thread = threading.Thread(target=self._restore_worker, daemon=True)
        thread.start()

    def _restore_worker(self):
        """Фоновое создание точки восстановления."""
        def log(text):
            self.msg_queue.put(("log", text))
        try:
            log("")
            ok, rmsg = opt.create_system_restore_point()
            if ok:
                log(i18n.t("log.restore_ok"))
            else:
                log(i18n.t("log.restore_fail", rmsg) if rmsg
                    else i18n.t("log.restore_no_admin"))
            self.msg_queue.put(("restore_point_done",
                                i18n.t("dlg.restore_done")))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("restore_point_done",
                                i18n.t("log.error_text", exc)))

    def _optimize_worker(self, keys):
        def log(text):
            self.msg_queue.put(("log", text))
        def status(text):
            self.msg_queue.put(("opt_status", text))
        def on_progress(done, total):
            self.msg_queue.put(("opt_progress", done, total))
        def on_item_start(key, index, total):
            self.msg_queue.put(("opt_item_start", key, index, total))
        def on_item_done(key, kind, reason):
            self.msg_queue.put(("opt_item_done", key, kind, reason))
        try:
            log("")
            log(i18n.t("log.opt_header"))
            info = opt.get_windows_info()
            log(i18n.t("opt.os", info["display"], info["build"],
                       info["edition"] or "—"))
            # Логика применения — в cleaner_optimize, чтобы интерфейс и CLI
            # не расходились в том, что считается пропуском, а что ошибкой.
            stats = opt.apply_optimizations(
                keys, on_log=log, on_status=status,
                stop_event=self.stop_event, on_progress=on_progress,
                on_item_start=on_item_start, on_item_done=on_item_done)
            result_text = opt.result_summary(stats)
            log("")
            log(i18n.t("log.result_header"))
            log(result_text)
            self.msg_queue.put(("opt_done", result_text))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("opt_done", i18n.t("log.error_text", exc)))

    # ============================ ВКЛАДКА «РАСПИСАНИЕ» (тихая очистка)
    def _build_schedule_tab(self, parent):
        """Вкладка «Расписание»: тихая автоматическая очистка по расписанию."""
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(parent, fg_color=COLOR_CARD_2,
                                        corner_radius=10)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(scroll, text=i18n.t("sched.title"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w", padx=6, pady=(4, 6))
        ctk.CTkLabel(scroll, text=i18n.t("sched.subtitle"),
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                     justify="left", anchor="w", wraplength=720
                     ).pack(anchor="w", padx=6, pady=(0, 8))

        # --- Включение планировщика ---
        self.sched_enable_var = tk.BooleanVar(value=self._schedule_enabled())
        ctk.CTkSwitch(scroll, text=i18n.t("sched.enable"),
                      variable=self.sched_enable_var,
                      font=ctk.CTkFont(size=13), text_color=COLOR_TEXT,
                      progress_color=COLOR_ACCENT,
                      command=self._on_schedule_enabled
                      ).pack(anchor="w", padx=6, pady=(4, 10))

        # --- Карточка настроек ---
        cfg = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        cfg.pack(fill="x", padx=4, pady=6)
        cfg.grid_columnconfigure(1, weight=1)

        # Частота
        ctk.CTkLabel(cfg, text=i18n.t("sched.freq"),
                     font=ctk.CTkFont(size=12), text_color=COLOR_TEXT
                     ).grid(row=0, column=0, sticky="w", padx=10, pady=6)
        self._freq_by_label = {i18n.t("sched.daily"): "daily",
                               i18n.t("sched.weekly"): "weekly"}
        self.sched_freq_var = tk.StringVar(
            value=i18n.t("sched." + self._schedule_setting("Freq", "daily")))
        freq = ctk.CTkSegmentedButton(cfg, values=list(self._freq_by_label.keys()),
                                      variable=self.sched_freq_var,
                                      command=self._on_schedule_freq_changed)
        freq.grid(row=0, column=1, sticky="w", padx=10, pady=6)

        # Время
        ctk.CTkLabel(cfg, text=i18n.t("sched.time"),
                     font=ctk.CTkFont(size=12), text_color=COLOR_TEXT
                     ).grid(row=1, column=0, sticky="w", padx=10, pady=6)
        time_box = ctk.CTkFrame(cfg, fg_color="transparent")
        time_box.grid(row=1, column=1, sticky="w", padx=10, pady=6)
        hours = ["{:02d}".format(h) for h in range(24)]
        minutes = ["00", "15", "30", "45"]
        self.sched_hour_var = tk.StringVar(
            value=self._schedule_setting("Hour", "3").zfill(2))
        self.sched_minute_var = tk.StringVar(
            value=self._schedule_setting("Minute", "0").zfill(2))
        ctk.CTkOptionMenu(time_box, values=hours, variable=self.sched_hour_var,
                          width=70,
                          command=lambda *_: self._on_schedule_setting_changed()
                          ).pack(side="left")
        ctk.CTkLabel(time_box, text=":", text_color=COLOR_TEXT
                     ).pack(side="left", padx=2)
        ctk.CTkOptionMenu(time_box, values=minutes, variable=self.sched_minute_var,
                          width=70,
                          command=lambda *_: self._on_schedule_setting_changed()
                          ).pack(side="left")

        # День недели (только для еженедельно)
        ctk.CTkLabel(cfg, text=i18n.t("sched.weekday"),
                     font=ctk.CTkFont(size=12), text_color=COLOR_TEXT
                     ).grid(row=2, column=0, sticky="w", padx=10, pady=6)
        self._weekday_labels = [i18n.t("sched.mon"), i18n.t("sched.tue"),
                                i18n.t("sched.wed"), i18n.t("sched.thu"),
                                i18n.t("sched.fri"), i18n.t("sched.sat"),
                                i18n.t("sched.sun")]
        self._weekday_by_label = {lab: i for i, lab in enumerate(self._weekday_labels)}
        wd_index = int(self._schedule_setting("Weekday", "6"))
        self.sched_weekday_var = tk.StringVar(value=self._weekday_labels[wd_index])
        self.sched_weekday_menu = ctk.CTkOptionMenu(
            cfg, values=self._weekday_labels, variable=self.sched_weekday_var,
            width=120, command=lambda *_: self._on_schedule_setting_changed())
        self.sched_weekday_menu.grid(row=2, column=1, sticky="w", padx=10, pady=6)

        # Переключатели: точка восстановления и сухой прогон
        self.sched_restore_var = tk.BooleanVar(
            value=self._schedule_setting("Restore", "1") == "1")
        ctk.CTkSwitch(cfg, text=i18n.t("sched.restore"),
                      variable=self.sched_restore_var,
                      font=ctk.CTkFont(size=12), text_color=COLOR_TEXT,
                      progress_color=COLOR_ACCENT,
                      command=lambda: self._on_schedule_setting_changed()
                      ).grid(row=3, column=0, columnspan=2, sticky="w",
                             padx=10, pady=4)
        self.sched_dry_var = tk.BooleanVar(
            value=self._schedule_setting("Dry", "0") == "1")
        ctk.CTkSwitch(cfg, text=i18n.t("sched.dry"), variable=self.sched_dry_var,
                      font=ctk.CTkFont(size=12), text_color=COLOR_TEXT,
                      progress_color=COLOR_ACCENT,
                      command=lambda: self._on_schedule_setting_changed()
                      ).grid(row=4, column=0, columnspan=2, sticky="w",
                             padx=10, pady=(4, 8))

        # --- Категории ---
        cat_card = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        cat_card.pack(fill="x", padx=4, pady=(4, 6))
        ctk.CTkLabel(cat_card, text=i18n.t("sched.categories"),
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=COLOR_TEXT
                     ).pack(anchor="w", padx=10, pady=(8, 4))

        saved = (self._schedule_setting("Categories", "") or "").split(",")
        saved_set = set(s for s in saved if s)
        # Список категорий, которые существовали на момент сохранения выбора.
        # Нужен, чтобы отличить «пользователь снял галочку» от «категория
        # появилась в новой версии»: вторые включаем, первые уважаем.
        known_set = set(k for k in
                        (self._schedule_setting("CategoriesAll", "") or "").split(",")
                        if k)
        self.sched_vars = {}
        groups = {}
        for cat in core.CATEGORIES:
            groups.setdefault(cat["group"], []).append(cat)
        for group_key, cats in groups.items():
            ctk.CTkLabel(cat_card, text=core.group_title(group_key).upper(),
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=COLOR_ACCENT
                         ).pack(anchor="w", padx=12, pady=(8, 2))
            for cat in cats:
                if known_set:
                    # Новые категории (которых не было в сохранённом списке)
                    # включены по умолчанию — как и на вкладке «Очистка».
                    default = (cat["key"] in saved_set) or (cat["key"] not in known_set)
                else:
                    # Старые настройки без списка известных ключей: не рискуем
                    # включать то, что пользователь мог осознанно отключить.
                    default = (cat["key"] in saved_set) if saved_set else True
                var = tk.BooleanVar(value=default)
                self.sched_vars[cat["key"]] = var
                ctk.CTkCheckBox(cat_card,
                                text="{} {}".format(cat["icon"],
                                                    i18n.fld(cat, "title")),
                                variable=var, font=ctk.CTkFont(size=12),
                                text_color=COLOR_TEXT, checkbox_width=18,
                                checkbox_height=18, fg_color=COLOR_ACCENT,
                                hover_color=COLOR_ACCENT_HOVER,
                                command=self._on_sched_cat_toggle
                                ).pack(anchor="w", padx=14, pady=2)

        cat_btns = ctk.CTkFrame(cat_card, fg_color="transparent")
        cat_btns.pack(fill="x", padx=10, pady=(6, 8))
        ctk.CTkButton(cat_btns, text=i18n.t("sched.select_all"), width=120,
                      height=28, fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                      command=lambda: self._set_sched_all(True)
                      ).pack(side="left")
        ctk.CTkButton(cat_btns, text=i18n.t("sched.clear_all"), width=120,
                      height=28, fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                      command=lambda: self._set_sched_all(False)
                      ).pack(side="left", padx=8)

        # --- Кнопки действий ---
        act = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        act.pack(fill="x", padx=4, pady=(4, 6))
        action_btns = ctk.CTkFrame(act, fg_color="transparent")
        action_btns.pack(fill="x", padx=10, pady=10)
        ctk.CTkButton(action_btns, text=i18n.t("sched.run_now"), width=140,
                      height=34, font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
                      command=self._run_scheduled_clean
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(action_btns, text=i18n.t("sched.save"), width=140,
                      height=34, font=ctk.CTkFont(size=12, weight="bold"),
                      fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                      command=self._persist_schedule
                      ).pack(side="left", padx=(0, 8))

        # Вторая строка: регистрация/удаление автономной задачи Windows.
        task_btns = ctk.CTkFrame(act, fg_color="transparent")
        task_btns.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(task_btns, text=i18n.t("sched.register_task"), width=210,
                      height=34, font=ctk.CTkFont(size=12),
                      fg_color=COLOR_CARD, hover_color=COLOR_ACCENT,
                      command=self._on_register_task
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(task_btns, text=i18n.t("sched.unregister_task"), width=210,
                      height=34, font=ctk.CTkFont(size=12),
                      fg_color=COLOR_CARD, hover_color=COLOR_RED,
                      command=self._on_unregister_task
                      ).pack(side="left")
        ctk.CTkLabel(act, text=i18n.t("sched.register_hint"),
                     font=ctk.CTkFont(size=10), text_color=COLOR_MUTED,
                     justify="left", anchor="w", wraplength=720
                     ).pack(anchor="w", padx=10, pady=(0, 10))

        # --- Статус следующего запуска ---
        self.sched_status_label = ctk.CTkLabel(
            scroll, text="", font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ACCENT)
        self.sched_status_label.pack(anchor="w", padx=6, pady=(2, 10))

        # Первичное состояние контролов и статуса.
        self._on_schedule_freq_changed()
        self._update_schedule_status()

    # --------------------------------------------------- хранилище расписания
    def _schedule_setting(self, name, default=""):
        return settings.get_settings().get("Schedule." + name, default)

    def _save_schedule_setting(self, name, value):
        settings.get_settings().set("Schedule." + name, value)

    def _schedule_enabled(self):
        return self._schedule_setting("Enabled", "0") == "1"

    # ----------------------------------------------------- обработчики контролов
    def _on_schedule_enabled(self, *_):
        enabled = self.sched_enable_var.get()
        self._save_schedule_setting("Enabled", "1" if enabled else "0")
        self._update_schedule_status()
        self.schedule_reschedule.set()
        if enabled:
            self._log(i18n.t("sched.enabled"))
            self._maybe_start_scheduler()
        else:
            self._log(i18n.t("sched.disabled"))

    def _on_schedule_freq_changed(self, *_):
        """Переключает доступность выбора дня недели (только для еженедельно)."""
        is_weekly = self._freq_by_label.get(self.sched_freq_var.get()) == "weekly"
        try:
            self.sched_weekday_menu.configure(
                state="normal" if is_weekly else "disabled")
        except Exception:
            pass
        self._persist_schedule()

    def _on_schedule_setting_changed(self, *_):
        self._persist_schedule()

    def _on_sched_cat_toggle(self):
        self._persist_schedule()

    def _set_sched_all(self, value):
        for var in self.sched_vars.values():
            var.set(value)
        self._persist_schedule()

    def _persist_schedule(self):
        """Сохраняет все настройки расписания в реестр/JSON."""
        try:
            self._save_schedule_setting(
                "Enabled", "1" if self.sched_enable_var.get() else "0")
            self._save_schedule_setting(
                "Freq", self._freq_by_label.get(self.sched_freq_var.get(), "daily"))
            self._save_schedule_setting(
                "Weekday", str(self._weekday_by_label.get(
                    self.sched_weekday_var.get(), 6)))
            self._save_schedule_setting("Hour", self.sched_hour_var.get())
            self._save_schedule_setting("Minute", self.sched_minute_var.get())
            self._save_schedule_setting(
                "Restore", "1" if self.sched_restore_var.get() else "0")
            self._save_schedule_setting(
                "Dry", "1" if self.sched_dry_var.get() else "0")
            keys = [k for k, v in self.sched_vars.items() if v.get()]
            self._save_schedule_setting("Categories", ",".join(keys))
            # Полный список категорий на этот момент — чтобы в следующей
            # версии отличить новые пункты от отключённых вручную.
            self._save_schedule_setting("CategoriesAll",
                                        ",".join(self.sched_vars.keys()))
            self.schedule_reschedule.set()
            self._update_schedule_status()
        except Exception as exc:
            self._log(i18n.t("log.error") + repr(exc))

    def _update_schedule_status(self):
        if self.sched_status_label is None:
            return
        when = self._next_run_dt()
        if when is None:
            self.sched_status_label.configure(text=i18n.t("sched.next_off"))
        else:
            self.sched_status_label.configure(
                text=i18n.t("sched.next", when.strftime("%Y-%m-%d %H:%M")))

    # ----------------------------------------------------------- логика планировщика
    def _next_run_dt(self):
        """Возвращает datetime следующего запуска или None, если выключено."""
        if not self._schedule_enabled():
            return None
        freq = self._schedule_setting("Freq", "daily")
        try:
            hour = int(self._schedule_setting("Hour", "3"))
            minute = int(self._schedule_setting("Minute", "0"))
        except ValueError:
            hour, minute = 3, 0
        now = datetime.datetime.now()
        today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if freq == "weekly":
            try:
                wd = int(self._schedule_setting("Weekday", "6"))
            except ValueError:
                wd = 6
            days_ahead = (wd - now.weekday()) % 7
            cand = today + datetime.timedelta(days=days_ahead)
            if cand <= now:
                cand += datetime.timedelta(days=7)
            return cand
        cand = today
        if cand <= now:
            cand += datetime.timedelta(days=1)
        return cand

    def _maybe_start_scheduler(self):
        if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
            self.schedule_stop_event.clear()
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop, daemon=True)
            self._scheduler_thread.start()

    def _scheduler_loop(self):
        """Фоновый цикл: ждёт наступления времени и запускает тихую очистку."""
        while not self.schedule_stop_event.is_set():
            when = self._next_run_dt()
            if when is None:
                # Расписание выключено — ждём, пока не включат (reschedule разбудит).
                self.schedule_stop_event.wait(5)
                continue
            delay = (when - datetime.datetime.now()).total_seconds()
            if delay <= 0:
                delay = 0.5
            # Спим кусками по ~1с, реагируя на стоп или изменение расписания.
            slept = 0.0
            while (slept < delay and not self.schedule_stop_event.is_set()
                   and not self.schedule_reschedule.is_set()):
                chunk = min(1.0, delay - slept)
                self.schedule_stop_event.wait(chunk)
                slept += chunk
            if self.schedule_stop_event.is_set():
                break
            if self.schedule_reschedule.is_set():
                self.schedule_reschedule.clear()
                continue
            # Время пришло — запускаем, если ничего другого не выполняется.
            if not self.running and self._schedule_enabled():
                # Из фонового потока НЕ трогаем Tk: просим главный поток
                # запустить очистку (он прочитает галочки и стартует воркер).
                self.msg_queue.put(("sched_trigger",))

    def _run_scheduled_clean(self):
        """Запускает тихую очистку (кнопка «Запустить сейчас» или планировщик).

        Всегда вызывается в ГЛАВНОМ потоке: галочки Tk читаем здесь и передаём
        в воркер значениями — фоновый поток не должен обращаться к Tk.
        """
        if self.running:
            self._log(i18n.t("sched.busy"))
            return
        s = settings.get_settings()
        if self.sched_vars:
            keys = [k for k, v in self.sched_vars.items() if v.get()]
        else:
            # Вкладка «Расписание» ещё не открывалась — берём сохранённый выбор.
            saved = s.get("Schedule.Categories", "") or ""
            keys = [k for k in saved.split(",") if k] or [c["key"] for c in core.CATEGORIES]
        if self.sched_restore_var is not None:
            make_restore = bool(self.sched_restore_var.get())
        else:
            make_restore = s.get("Schedule.Restore", "1") == "1"
        if self.sched_dry_var is not None:
            dry = bool(self.sched_dry_var.get())
        else:
            dry = s.get("Schedule.Dry", "0") == "1"
        thread = threading.Thread(target=self._scheduled_clean_worker,
                                  args=(keys, make_restore, dry), daemon=True)
        thread.start()

    def _scheduled_clean_worker(self, keys, make_restore, dry):
        """Фоновый воркер тихой очистки: точка восстановления + очистка.

        keys/make_restore/dry переданы значениями из главного потока —
        к Tk-переменным отсюда не обращаемся.
        """
        def log(text):
            self.msg_queue.put(("log", text))
        def status(text):
            self.msg_queue.put(("status", text))
        def on_progress(done, total):
            self.msg_queue.put(("progress", done, total))
        try:
            self.msg_queue.put(("sched_running", True))
            log("")
            log(i18n.t("sched.header"))
            run_scheduled_cleanup(
                keys,
                make_restore=make_restore,
                dry_run_first=dry,
                on_log=log, on_status=status, on_progress=on_progress,
                stop_event=self.stop_event)
            log(i18n.t("sched.finished"))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
        finally:
            self.msg_queue.put(("progress_reset",))
            self.msg_queue.put(("sched_running", False))

    # --------------------------------------- регистрация автономной задачи Windows
    def _on_register_task(self):
        """Регистрирует задачу планировщика Windows (PowerShell Register-ScheduledTask).

        PowerShell принимает исполняемый файл и аргументы РАЗДЕЛЬНО
        (-Execute/-Argument), поэтому путь с пробелами («win11 cleaner»)
        не ломает разбор аргументов (в отличие от schtasks /TR).
        """
        if self.running:
            return
        try:
            if getattr(sys, "frozen", False):
                execute = sys.executable
                argument = "--silent-clean"
            else:
                execute = sys.executable
                argument = '"{}" --silent-clean'.format(os.path.abspath(__file__))
            freq = self._schedule_setting("Freq", "daily")
            hour = self._schedule_setting("Hour", "3").zfill(2)
            minute = self._schedule_setting("Minute", "0").zfill(2)
            at = "{}:{}".format(hour, minute)
            if freq == "weekly":
                wd = int(self._schedule_setting("Weekday", "6"))
                days = ["Monday", "Tuesday", "Wednesday", "Thursday",
                        "Friday", "Saturday", "Sunday"]
                trigger = ('New-ScheduledTaskTrigger -Weekly -DaysOfWeek {} -At "{}"'
                           .format(days[wd], at))
            else:
                trigger = 'New-ScheduledTaskTrigger -Daily -At "{}"'.format(at)
            ps = (
                '$action = New-ScheduledTaskAction -Execute {exe} -Argument {arg}\n'
                '$trigger = {trig}\n'
                'Register-ScheduledTask -TaskName {name} -Action $action '
                '-Trigger $trigger -RunLevel Highest -Force | Out-Null\n'
            ).format(exe=_ps_quote(execute), arg=_ps_quote(argument),
                     trig=trigger, name=_ps_quote(SCHED_TASK_NAME))
            code, out = _run_task_ps1(ps)
            if code == 0:
                msg = i18n.t("sched.registered", SCHED_TASK_NAME)
                self._log(msg)
                messagebox.showinfo(i18n.t("dlg.ok"), msg)
            else:
                msg = i18n.t("sched.register_failed", (out or "").strip()[:300])
                self._log(msg)
                messagebox.showwarning(i18n.t("dlg.no_admin_title"), msg)
        except Exception as exc:
            self._log(i18n.t("log.error") + repr(exc))

    def _on_unregister_task(self):
        """Удаляет задачу планировщика Windows (PowerShell Unregister-ScheduledTask).

        Симметрично регистрации: та же константа имени задачи, тот же механизм,
        поэтому гарантированно удаляет именно ту задачу, что создаёт регистрация.
        """
        if self.running:
            return
        try:
            ps = 'Unregister-ScheduledTask -TaskName {} -Confirm:$false\n'.format(
                _ps_quote(SCHED_TASK_NAME))
            code, out = _run_task_ps1(ps)
            text = (out or "").strip().lower()
            # «Задачи и так нет» — для пользователя это успех (уже удалена).
            gone = any(s in text for s in (
                "does not exist", "не существует", "не найдена",
                "cannot find", "could not find", "no instance", "no task"))
            if code == 0 or gone:
                msg = i18n.t("sched.unregistered", SCHED_TASK_NAME)
                self._log(msg)
                messagebox.showinfo(i18n.t("dlg.ok"), msg)
            else:
                msg = i18n.t("sched.unregister_failed", (out or "").strip()[:300])
                self._log(msg)
                messagebox.showwarning(i18n.t("dlg.no_admin_title"), msg)
        except Exception as exc:
            self._log(i18n.t("log.error") + repr(exc))


# =============================================================================
# ТОЧКА ВХОДА
# =============================================================================

# =============================================================================
# ТИХАЯ ОЧИСТКА ПО РАСПИСАНИЮ — ОРКЕСТРАЦИЯ (общий код для GUI и CLI)
# =============================================================================
def run_scheduled_cleanup(keys, *, make_restore=True, dry_run_first=False,
                          on_log=None, on_status=None, on_progress=None,
                          stop_event=None, selected_map=None):
    """Выполняет тихую очистку: точка восстановления + (сухой прогон) + удаление.

    Используется и воркером вкладки «Расписание», и фоновой задачей Windows
    (--silent-clean), поэтому не зависит от GUI.
    `selected_map` — выбор под-опций браузеров (по умолчанию берётся из
    сохранённых настроек; None → умолчание ядра, т.е. только кэш).
    """
    on_log = on_log or (lambda text: None)
    on_status = on_status or (lambda text: None)
    on_progress = on_progress or (lambda done, total: None)
    stop_event = stop_event or threading.Event()

    if selected_map is None:
        selected_map = {key: settings.get_browser_options(key)
                        for key in keys if key in core.BROWSER_KEYS}

    if not keys:
        on_log(i18n.t("sched.no_categories"))
        return None

    if make_restore:
        on_log("")
        on_log(i18n.t("sched.restore_creating"))
        ok, rmsg = opt.create_system_restore_point(i18n.t("sched.restore_desc"))
        if ok:
            on_log(i18n.t("log.restore_ok"))
        else:
            on_log(i18n.t("log.restore_fail", rmsg) if rmsg
                   else i18n.t("log.restore_no_admin"))

    if dry_run_first:
        on_status(i18n.t("status.scanning"))
        on_log("")
        on_log(i18n.t("sched.dry_header"))
        scanned = core.scan_categories(keys, on_log=on_log, on_status=on_status,
                                      stop_event=stop_event,
                                      selected_map=selected_map)
        tot = sum(r["total_size"] for r in scanned.values())
        on_log(i18n.t("log.scan_total", core.format_bytes(tot)))
        on_status(i18n.t("status.cleaning"))
        on_log("")
        on_log(i18n.t("log.clean_header", i18n.t("log.mode_real")))
        summary = core.clean_categories(scanned, dry_run=False, on_log=on_log,
                                        on_status=on_status, on_progress=on_progress,
                                        stop_event=stop_event)
    else:
        on_status(i18n.t("status.scanning"))
        on_log("")
        on_log(i18n.t("log.scan_header"))
        scanned = core.scan_categories(keys, on_log=on_log, on_status=on_status,
                                      stop_event=stop_event,
                                      selected_map=selected_map)
        on_status(i18n.t("status.cleaning"))
        on_log("")
        on_log(i18n.t("log.clean_header", i18n.t("log.mode_real")))
        summary = core.clean_categories(scanned, dry_run=False, on_log=on_log,
                                        on_status=on_status, on_progress=on_progress,
                                        stop_event=stop_event)

    on_log("")
    on_log(i18n.t("log.result_header"))
    result_text = i18n.t("log.clean_result",
                         i18n.t("log.clean_done"),
                         summary["removed"], summary["skipped"],
                         summary["errors"], core.format_bytes(summary["freed"]))
    on_log(result_text)
    return summary


SCHED_TASK_NAME = "SweptQuietCleanup"


def _run_task_ps1(ps_body: str):
    """Пишет PowerShell-скрипт во временный .ps1, выполняет и удаляет его.

    Возвращает (код_возврата, вывод). Через файл — чтобы не экранировать
    кавычки пути с пробелами («win11 cleaner») прямо в командной строке.
    Используется и для регистрации, и для удаления задачи (симметрично).
    """
    fd, ps_path = tempfile.mkstemp(suffix=".ps1", prefix="swept_task_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write('$ErrorActionPreference = "Stop"\n' + ps_body)
        return _run_cmd('powershell -NoProfile -ExecutionPolicy Bypass -File "{}"'
                        .format(ps_path))
    finally:
        try:
            os.remove(ps_path)
        except Exception:
            pass


def _ps_quote(s: str) -> str:
    """Обёртка строки в одинарные кавычки PowerShell (с экранированием ')."""
    return "'" + str(s).replace("'", "''") + "'"


def _decode_output(raw: bytes) -> str:
    """Декодирует вывод консольной команды с запасными кодировками Windows.

    На русской/локализованной Windows консольные утилиты (schtasks и др.)
    печатают в OEM-кодировке (cp866), ANSI — cp1251. Вариант subprocess с
    text=True и UTF-8 роняет внутренний reader-поток на не-UTF-8 байтах
    (исключение не ловится try/except вокруг run), поэтому захватываем
    байты и декодируем вручную с запасными кодировками.
    """
    for enc in ("utf-8", "cp866", "cp1251", "mbcs"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _run_cmd(cmd: str):
    """Запускает внешнюю команду и возвращает (код_возврата, вывод)."""
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, timeout=90)
        raw = (proc.stdout or b"") + (proc.stderr or b"")
        return proc.returncode, _decode_output(raw)
    except Exception as exc:  # pragma: no cover - исключение запуска
        return -1, str(exc)


def _silent_clean_headless() -> int:
    """Фоновый режим для задачи Windows: читает расписание и чистит молча."""
    i18n.set_language(_load_saved_language())
    s = settings.get_settings()
    saved = s.get("Schedule.Categories", "") or ""
    keys = [k for k in saved.split(",") if k] or [c["key"] for c in core.CATEGORIES]
    make_restore = s.get("Schedule.Restore", "1") == "1"
    dry = s.get("Schedule.Dry", "0") == "1"

    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base, "swept_silent_clean.log")

    def on_log(text):
        line = text if text.endswith("\n") else text + "\n"
        try:
            sys.stdout.write(line)
        except Exception:
            pass
        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception:
            pass

    on_log(i18n.t("sched.header"))
    try:
        run_scheduled_cleanup(keys, make_restore=make_restore, dry_run_first=dry,
                              on_log=on_log)
        on_log(i18n.t("sched.finished"))
        return 0
    except Exception as exc:
        on_log(i18n.t("log.error") + repr(exc))
        return 1


def main():
    # Фоновый режим для автономной задачи Windows (schtasks): без окна, только лог.
    if "--silent-clean" in sys.argv[1:]:
        sys.exit(_silent_clean_headless())

    app = CleanerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
