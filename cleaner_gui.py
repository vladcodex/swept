#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
cleaner_gui.py — ГРАФИЧЕСКИЙ ИНТЕРФЕЙС (CustomTkinter) для Swept.

Возможности интерфейса
----------------------
    * Современный ТЁМНЫЙ дизайн (CustomTkinter).
    * Вкладка «Очистка»: чек-боксы категорий, кнопки «Анализ»/«Очистить»,
      переключатель «Только сканирование», прогресс-бар, статус.
    * Вкладка «Установка»: поиск программ через winget, установка/обновление
      выбранного пакета, обновление всех пакетов.
    * Вкладка «Журнал»: текстовое поле с путями удаляемых файлов и итогами.
    * Индикатор прав администратора.

Запуск:  python cleaner_gui.py
Требуется:  pip install customtkinter
"""

from __future__ import annotations

import copy
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox

try:
    import customtkinter as ctk
except ImportError:  # pragma: no cover - подсказка при отсутствии библиотеки
    print("Не найдена библиотека CustomTkinter.")
    print("Установите её командой:  pip install customtkinter")
    sys.exit(1)

import cleaner_core as core
import cleaner_i18n as i18n
import cleaner_installer as inst
import cleaner_optimize as opt
import cleaner_settings as settings

# =============================================================================
# НАСТРОЙКИ ВНЕШНЕГО ВИДА
# =============================================================================

COLOR_BG = "#12131a"
COLOR_CARD = "#1c1e2a"
COLOR_CARD_2 = "#242736"
COLOR_ACCENT = "#3b82f6"
COLOR_ACCENT_HOVER = "#2f6fd0"
COLOR_GREEN = "#22c55e"
COLOR_GREEN_HOVER = "#1ea34c"
COLOR_RED = "#ef4444"
COLOR_TEXT = "#e5e7eb"
COLOR_MUTED = "#9ca3af"
COLOR_ROW_SELECTED = "#1f3b63"   # фон выбранной строки списка пакетов

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
        # Высота зависит от числа программ в наборе: без пустого места снизу.
        height = 170 + min(len(preset["packages"]), 6) * 46
        self.geometry("560x{}".format(height))
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)
        # Окно модальное относительно главного: transient + grab_set ниже.
        self.transient(master)

        wrap = ctk.CTkFrame(self, fg_color=COLOR_CARD_2, corner_radius=12)
        wrap.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(wrap, text=i18n.fld(preset, "title"),
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=COLOR_TEXT, anchor="w", height=22
                     ).pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(wrap, text=i18n.t("presets.dialog_hint"),
                     font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                     justify="left", anchor="w", wraplength=500, height=16
                     ).pack(fill="x", padx=14, pady=(0, 8))

        scroll = ctk.CTkScrollableFrame(
            wrap, fg_color=COLOR_BG, corner_radius=10,
            scrollbar_button_color=COLOR_CARD_2,
            scrollbar_button_hover_color=COLOR_ACCENT)
        scroll.pack(fill="both", expand=True, padx=14, pady=(0, 8))

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

        buttons = ctk.CTkFrame(wrap, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkButton(buttons, text=i18n.t("presets.select_all"),
                      width=130, height=30, fg_color=COLOR_CARD,
                      hover_color=COLOR_ACCENT,
                      command=lambda: self._set_all(True)).pack(side="left")
        ctk.CTkButton(buttons, text=i18n.t("presets.select_none"),
                      width=110, height=30, fg_color=COLOR_CARD,
                      hover_color=COLOR_ACCENT,
                      command=lambda: self._set_all(False)).pack(side="left", padx=6)

        self.install_btn = ctk.CTkButton(
            buttons, text=i18n.t("presets.install_selected", len(self._rows)),
            width=170, height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            command=self._accept)
        self.install_btn.pack(side="right")
        ctk.CTkButton(buttons, text=i18n.t("presets.close"), width=100, height=30,
                      fg_color=COLOR_CARD, hover_color=COLOR_RED,
                      command=self.destroy).pack(side="right", padx=6)

        self._refresh_count()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda event: self.destroy())
        self.after(60, self._center_and_focus)

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
        self.geometry("1060x740")
        # Минимум подобран под колонку наборов: при меньшей ширине
        # обрезаются подписи на вкладке «Установка».
        self.minsize(960, 660)
        self.configure(fg_color=COLOR_BG)

        # --- Состояние ---
        self.vars = {}
        self.scan_results = {}
        self.running = False
        self.stop_event = threading.Event()
        self.msg_queue = queue.Queue()
        self.total_freed = 0
        self.installer_results = []   # результаты поиска winget
        self.selected_pkg = None      # выбранный пакет для установки
        self.pkg_rows = []            # виджеты строк списка пакетов
        self.pkg_cells = []           # текстовые ячейки каждой строки
        self.selected_row = None      # индекс подсвеченной строки
        self._info_widgets = {}       # виджеты-подписи категорий (key -> label)
        self.pkg_header = None        # шапка таблицы пакетов (вне списка строк)
        self.winget_available = None  # None/True/False — доступность winget
        self.opt_vars = {}            # чек-боксы вкладки «Оптимизация»
        self.opt_os_label = None      # подпись про версию Windows
        self._closing = False         # флаг закрытия окна
        self._admin_ok = None         # кэш проверки прав администратора
        self._admin_warned = False    # предупреждение показано только один раз
        self._tab_index = 0           # активная вкладка (для смены языка)
        self._lang_switch = None      # выпадающий список языков
        self._lang_label = None       # подпись «Язык» рядом со списком
        self._total_text = None       # текст «Освобождено…» с учётом режима

        # --- Построение интерфейса ---
        self._build_header()
        self._build_tabs()
        self._build_footer()

        self.after(100, self._poll_queue)
        self.after(300, self._check_admin_warning)

        # При закрытии окна останавливаем фоновые операции и завершаем работу.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ============================================================== HEADER
    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12)
        header.pack(fill="x", padx=14, pady=(14, 8))

        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left", padx=16, pady=12)

        ctk.CTkLabel(left, text=i18n.t("app.brand"),
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color=COLOR_TEXT).pack(anchor="w")
        ctk.CTkLabel(left, text=i18n.t("app.subtitle"),
                     font=ctk.CTkFont(size=12),
                     text_color=COLOR_MUTED).pack(anchor="w", pady=(2, 0))

        self.admin_label = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.admin_label.pack(side="right", padx=16)
        self._refresh_admin_label()

        # Выпадающий список языка интерфейса (Русский / English).
        # Названия пишутся эндонимами, поэтому список не «перескакивает»
        # при смене языка; выбранное значение сразу уходит в реестр.
        self._lang_label = ctk.CTkLabel(header, text=i18n.t("lang.label"),
                                        font=ctk.CTkFont(size=12),
                                        text_color=COLOR_MUTED)
        self._lang_switch = ctk.CTkComboBox(
            header,
            values=i18n.language_values(),
            command=self._on_language_change,
            height=28, width=150, font=ctk.CTkFont(size=12),
            dropdown_font=ctk.CTkFont(size=12),
            state="readonly",
            fg_color=COLOR_CARD_2, border_color=COLOR_ACCENT,
            button_color=COLOR_ACCENT, button_hover_color=COLOR_ACCENT_HOVER,
            dropdown_fg_color=COLOR_CARD_2, dropdown_hover_color=COLOR_ACCENT,
            dropdown_text_color=COLOR_TEXT, text_color=COLOR_TEXT)
        # Порядок упаковки: сначала список (он у самого края), затем подпись слева.
        self._lang_switch.pack(side="right", padx=(0, 10))
        self._lang_label.pack(side="right", padx=(0, 6))
        self._sync_lang_switch()

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
            self.admin_label.configure(text=i18n.t("admin.yes"), text_color=COLOR_GREEN)
        else:
            self.admin_label.configure(text=i18n.t("admin.no"), text_color=COLOR_RED)

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
            "results": list(self.installer_results),
            "selected_row": self.selected_row,
            "total_freed": self.total_freed,
            "total_text": self._total_text,
            "winget": self.winget_available,
            "query": "",
            "pkg_text": "",
            "log": "",
        }
        try:
            state["query"] = self.search_entry.get()
            state["pkg_text"] = self.pkg_entry.get()
        except Exception:
            pass
        try:
            state["log"] = self.log_box.get("1.0", "end-1c")
        except Exception:
            pass
        return state

    def _rebuild_ui(self, state: dict):
        """Удаляет все виджеты и строит интерфейс заново на новом языке."""
        for child in self.winfo_children():
            child.destroy()

        self.vars = {}
        self.opt_vars = {}
        self._info_widgets = {}
        self.pkg_rows = []
        self.pkg_cells = []
        self.pkg_header = None
        self._lang_switch = None
        self._lang_label = None
        self.opt_os_label = None
        self.opt_live = None
        self.opt_tip = None
        self.opt_rows = {}
        self._opt_live_visible = False

        self.title(i18n.t("app.title"))
        self._build_header()
        self._build_tabs()
        self._build_footer()

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
        if self._total_text:
            self.total_label.configure(text=self._total_text)

        if state["log"]:
            try:
                self.log_box.configure(state="normal")
                self.log_box.insert("1.0", state["log"])
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
            except Exception:
                pass

        if state["query"]:
            self.search_entry.insert(0, state["query"])
        if state["results"]:
            self._show_installer_results(state["results"])
            if state["selected_row"] is not None:
                self.select_package(state["selected_row"])
        if state["pkg_text"]:
            self.pkg_entry.delete(0, "end")
            self.pkg_entry.insert(0, state["pkg_text"])

        # Возвращаемся на ту же вкладку.
        try:
            names = list(self._tab_names)
            index = state["tab_index"] if state["tab_index"] < len(names) else 0
            self.tabs.set(names[index])
            self._tab_index = index
        except Exception:
            pass

        self._apply_installer_buttons(self.running)
        self._set_running(self.running)

    # ================================================================ TABS
    def _build_tabs(self):
        """Создаёт Notebook с четырьмя вкладками."""
        self.tabs = ctk.CTkTabview(self, fg_color=COLOR_CARD, corner_radius=12,
                                   segmented_button_selected_color=COLOR_ACCENT,
                                   segmented_button_selected_hover_color=COLOR_ACCENT_HOVER,
                                   command=self._on_tab_change)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=8)

        self.tab_clean = self.tabs.add(i18n.t("tab.clean"))
        self.tab_install = self.tabs.add(i18n.t("tab.install"))
        self.tab_opt = self.tabs.add(i18n.t("tab.optimize"))
        self.tab_log = self.tabs.add(i18n.t("tab.log"))

        # Имена вкладок нужны для восстановления активной вкладки
        # после смены языка (имена меняются вместе с языком).
        self._tab_names = [i18n.t("tab.clean"), i18n.t("tab.install"),
                           i18n.t("tab.optimize"), i18n.t("tab.log")]

        self._build_clean_tab(self.tab_clean)
        self._build_install_tab(self.tab_install)
        self._build_optimize_tab(self.tab_opt)
        self._build_log_tab(self.tab_log)

    def _on_tab_change(self):
        """Запоминает активную вкладку (нужно при смене языка)."""
        try:
            name = self.tabs.get()
            if name in self._tab_names:
                self._tab_index = self._tab_names.index(name)
        except Exception:
            pass

    # ========================================================= CLEAN TAB
    def _build_clean_tab(self, parent):
        """Вкладка очистки: категории слева, управление справа."""
        parent.grid_columnconfigure(0, weight=0, minsize=380)
        parent.grid_columnconfigure(1, weight=1)
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
            title = core.group_title(group_key)
            ctk.CTkLabel(panel, text=title.upper(),
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=COLOR_ACCENT).pack(anchor="w", padx=6, pady=(10, 4))

            card = ctk.CTkFrame(panel, fg_color=COLOR_CARD, corner_radius=10)
            card.pack(fill="x", padx=4, pady=2)

            for cat in cats:
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

        # Переключатель «Только сканирование».
        self.scan_only_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(right, text=i18n.t("clean.scan_only"),
                      variable=self.scan_only_var,
                      font=ctk.CTkFont(size=12),
                      text_color=COLOR_MUTED,
                      progress_color=COLOR_ACCENT).pack(anchor="w", padx=14, pady=4)

        # Кнопки.
        btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        btn_frame.pack(fill="x", padx=14, pady=(10, 6))

        self.analyze_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn.analyze"), width=150, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self.on_analyze)
        self.analyze_btn.pack(side="left", padx=(0, 8))

        self.clean_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn.clean"), width=150, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            command=self.on_clean)
        self.clean_btn.pack(side="left")

        self.stop_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn.stop"), width=100, height=38,
            font=ctk.CTkFont(size=13),
            fg_color=COLOR_CARD, hover_color=COLOR_RED,
            state="disabled", command=self.on_stop)
        self.stop_btn.pack(side="left", padx=8)

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

    # ======================================================= INSTALL TAB
    def _build_install_tab(self, parent):
        """Вкладка установки программ через winget.

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

        self.winget_label = ctk.CTkLabel(head, text="", font=ctk.CTkFont(size=11))
        self.winget_label.grid(row=0, column=1, sticky="e")

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

        # Проверка доступности winget выполняется в фоне один раз за сеанс:
        # при смене языка интерфейс перерисовывается, а результат сохраняется.
        if self.winget_available is None:
            self.winget_label.configure(text=i18n.t("winget.checking"),
                                        text_color=COLOR_MUTED)
            threading.Thread(target=self._check_winget_worker, daemon=True).start()
        else:
            self._refresh_winget_label()

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

    # ============================================================ OPTIMIZE TAB
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

        # --- Правая панель: управление ---
        right = ctk.CTkFrame(parent, fg_color=COLOR_CARD_2, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

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
            btn_frame, text=i18n.t("btn.apply"), width=210, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_GREEN, hover_color=COLOR_GREEN_HOVER,
            command=self.on_optimize)
        self.opt_apply_btn.pack(side="left")

        # Откат: возвращает все изменённые настройки к значениям Windows.
        # Стоит рядом с «Применить», но нейтрального цвета: это не опасное
        # действие, а обратное — именно оно и делает оптимизацию обратимой.
        self.opt_revert_btn = ctk.CTkButton(
            btn_frame, text=i18n.t("btn.revert_all"), width=180, height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_CARD, hover_color=COLOR_RED,
            command=self.on_revert)
        self.opt_revert_btn.pack(side="left", padx=(8, 0))

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

        self.opt_tip = ctk.CTkLabel(right, text=i18n.t("opt.tip"),
                                    font=ctk.CTkFont(size=11), text_color=COLOR_MUTED,
                                    justify="left", anchor="w")
        self.opt_tip.pack(anchor="w", padx=14, pady=(0, 8))

    # ------------------------------------------- живой список оптимизации
    def _opt_live_show(self, keys, revert: bool = False):
        """Показывает список выбранных пунктов и сбрасывает их состояние."""
        if not getattr(self, "opt_live", None):
            return
        self.opt_live_title.configure(
            text=i18n.t("opt.live_revert_title" if revert else "opt.live_title"))
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
            self.opt_live.pack(fill="both", expand=True, padx=14, pady=(0, 8),
                               before=self.opt_tip)
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

    # ============================================================ LOG TAB
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

    # ============================================================== FOOTER
    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12)
        footer.pack(fill="x", padx=14, pady=(8, 14))

        self.status_label = ctk.CTkLabel(footer, text=i18n.t("status.ready"),
                                         font=ctk.CTkFont(size=12), text_color=COLOR_MUTED)
        self.status_label.pack(anchor="w", padx=16, pady=12)

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
        if not self._admin_warned:
            self._admin_warned = True
            messagebox.showwarning(i18n.t("dlg.no_admin_title"),
                                   i18n.t("dlg.no_admin_text"))

    def _log(self, text: str):
        self.msg_queue.put(("log", text))

    def _append_log(self, text: str):
        try:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text + "\n")
            line_count = int(self.log_box.index("end-1c").split(".")[0])
            if line_count > MAX_LOG_LINES:
                self.log_box.delete("1.0", "{}.0".format(line_count - MAX_LOG_LINES))
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        except Exception:
            # Окно уже закрыто/уничтожено — молча пропускаем.
            pass

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

    # ================================================== ОБРАБОТКА ОЧЕРЕДИ
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                try:
                    self._handle_message(msg)
                except Exception as exc:
                    # Ошибка в обработке одного сообщения не должна «ронять»
                    # обработчик очереди и терять остальные сообщения пачки.
                    self._append_log(i18n.t("log.ui_error") + repr(exc))
        except queue.Empty:
            pass
        finally:
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
            self.progress.set(0 if not total else done / total)
        elif kind == "progress_reset":
            self.progress.set(0)
        elif kind == "category":
            self._update_category_info(msg[1], msg[2])
        elif kind == "freed_delta":
            # Накопление реально освобождённого места за сессию.
            self.total_freed += msg[1]
            self._total_text = i18n.t("clean.total_session",
                                      core.format_bytes(self.total_freed))
            self.total_label.configure(text=self._total_text)
        elif kind == "simulated_size":
            self._total_text = i18n.t("clean.total_sim", core.format_bytes(msg[1]))
            self.total_label.configure(text=self._total_text)
        elif kind == "done":
            self._set_running(False)
            self.status_label.configure(text=msg[1])
            if msg[2]:
                messagebox.showinfo(i18n.t("dlg.ok"), msg[2])
        elif kind == "winget_status":
            self.winget_available = bool(msg[1])
            self._refresh_winget_label()
        elif kind == "installer_log":
            # Подробный вывод winget — в общий журнал, а в вкладке
            # «Установка» показываем последнюю строку как статус.
            self._append_log(msg[1])
            line = (msg[1] or "").strip()
            if line:
                self.install_status.configure(text=line[:150])
        elif kind == "installer_status":
            self.install_status.configure(text=msg[1][:150])
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
            if msg[1]:
                messagebox.showinfo(i18n.t("dlg.optimization"), msg[1])
        elif kind == "opt_revert_done":
            self._set_running(False)
            self.status_label.configure(text=i18n.t("status.rev_done"))
            self.opt_status.configure(text=i18n.t("status.done"))
            self._opt_live_finish()
            if msg[1]:
                messagebox.showinfo(i18n.t("dlg.revert_done"), msg[1])

    def _check_winget_worker(self):
        """Фоновая проверка доступности winget (не блокирует интерфейс)."""
        try:
            available = inst.is_winget_available()
        except Exception:
            available = False
        self.msg_queue.put(("winget_status", available))

    def _refresh_winget_label(self):
        """Показывает статус winget на текущем языке (None — ещё проверяется)."""
        if self.winget_available is None:
            self.winget_label.configure(text=i18n.t("winget.checking"),
                                        text_color=COLOR_MUTED)
        elif self.winget_available:
            self.winget_label.configure(text=i18n.t("winget.ok"), text_color=COLOR_GREEN)
        else:
            self.winget_label.configure(text=i18n.t("winget.missing"), text_color=COLOR_RED)

    def _on_close(self):
        """Закрытие окна: останавливаем фоновые операции и завершаем работу."""
        if self.running:
            # Закрытие во время очистки/установки обрывает операцию на середине:
            # спрашиваем подтверждение, чтобы это не было неожиданностью.
            if not messagebox.askyesno(i18n.t("dlg.close_title"),
                                       i18n.t("dlg.close_text")):
                return
        self._closing = True
        if self.running:
            self.stop_event.set()
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
        # Список виджетов ограничиваем: winget на общий запрос может вернуть
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
        # ID проверяем до сохранения: он попадёт в аргументы winget, поэтому
        # не должен содержать пробелов, кавычек и начинаться с дефиса.
        if not inst.is_valid_package_id(text):
            messagebox.showwarning(
                i18n.t("dlg.pkg_select_title"),
                i18n.t("inst.bad_id", self._short(text, 60)))
            return

        self.selected_pkg = {"name": text, "id": text, "version": "",
                             "source": i18n.t("pkg.source_manual")}
        self.selected_row = None
        for i in range(len(self.pkg_cells)):
            self._paint_row(i, False)
        self.pkg_label.configure(text=i18n.t("pkg.manual", text), text_color=COLOR_TEXT)
        self.install_status.configure(text=i18n.t("pkg.manual_set", text))
        self._apply_installer_buttons(self.running)

    def _apply_installer_buttons(self, busy: bool):
        """Включает/выключает кнопки вкладки «Установка» по состоянию busy."""
        self.search_btn.configure(state="disabled" if busy else "normal")
        self.upgrade_all_btn.configure(state="disabled" if busy else "normal")
        self.vc_btn.configure(state="disabled" if busy else "normal")
        for button in getattr(self, "preset_buttons", {}).values():
            button.configure(state="disabled" if busy else "normal")
        if getattr(self, "opt_apply_btn", None):
            self.opt_apply_btn.configure(state="disabled" if busy else "normal")
        if getattr(self, "opt_revert_btn", None):
            self.opt_revert_btn.configure(state="disabled" if busy else "normal")
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
        self._start_clean_worker(mode="scan", keys=keys)

    def on_clean(self):
        if self.running:
            return
        keys = self._selected_keys()
        if not keys:
            messagebox.showinfo(i18n.t("dlg.no_categories_title"),
                                i18n.t("dlg.no_categories_text"))
            return
        dry_run = self.scan_only_var.get()
        if not dry_run:
            if not messagebox.askyesno(
                    i18n.t("dlg.confirm_clean_title"),
                    i18n.t("dlg.confirm_clean_text")):
                return
        self._start_clean_worker(mode="clean", keys=keys, dry_run=dry_run)

    def _start_clean_worker(self, mode: str, keys: list, dry_run: bool = True):
        self._set_running(True)
        self.stop_event.clear()
        self.progress.set(0)
        # Переиспользуем результаты уже проведённого анализа (только для очистки)
        # глубокой копией — чтобы удаление не меняло сохранённые результаты скана.
        reusable = {}
        if mode == "clean":
            reusable = {key: copy.deepcopy(self.scan_results[key])
                        for key in keys if key in self.scan_results}
        thread = threading.Thread(
            target=self._clean_worker,
            args=(mode, keys, dry_run, reusable),
            daemon=True,
        )
        thread.start()

    def _clean_worker(self, mode: str, keys: list, dry_run: bool, results: dict):
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
                                               stop_event=self.stop_event)
                results.update(scanned)
                self.scan_results.update(scanned)
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
                        self.scan_results.pop(key, None)
                        self.msg_queue.put(("category", key, "{} | 0".format(
                            core.format_bytes(0))))
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
        query = self.search_entry.get().strip()
        if not query:
            messagebox.showinfo(i18n.t("dlg.empty_query_title"),
                                i18n.t("dlg.empty_query_text"))
            return
        if self.winget_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.winget_title"),
                i18n.t("dlg.winget_text"))
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
        нужные программы, и только они попадают в winget.
        """
        if self.running:
            return
        if self.winget_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.winget_title"),
                i18n.t("dlg.winget_text"))
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
        if self.winget_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.winget_title"),
                i18n.t("dlg.winget_text"))
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
        if self.winget_available is not True:
            messagebox.showinfo(
                i18n.t("dlg.winget_title"),
                i18n.t("dlg.winget_text"))
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

    def on_revert(self):
        """Откатывает все изменённые настройки к значениям Windows по умолчанию."""
        if self.running:
            return
        count = len(opt.REVERT_KEYS)
        if not messagebox.askyesno(i18n.t("dlg.revert_title"),
                                   i18n.t("dlg.revert_text", count)):
            return
        self._set_running(True)
        self.stop_event.clear()
        self.opt_status.configure(text=i18n.t("opt.reverting"))
        self.opt_progress.set(0)
        self._opt_live_show(opt.REVERT_KEYS, revert=True)
        thread = threading.Thread(target=self._revert_worker, daemon=True)
        thread.start()

    def _revert_worker(self):
        """Фоновый откат: та же механика прогресса, что у оптимизации."""
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
            log(i18n.t("log.rev_header"))
            stats = opt.revert_optimizations(
                on_log=log, on_status=status,
                stop_event=self.stop_event, on_progress=on_progress,
                on_item_start=on_item_start, on_item_done=on_item_done)
            result_text = opt.result_summary(stats, revert=True)
            log("")
            log(i18n.t("log.result_header"))
            log(result_text)
            self.msg_queue.put(("opt_revert_done", result_text))
        except Exception as exc:
            log(i18n.t("log.error") + repr(exc))
            self.msg_queue.put(("opt_revert_done", i18n.t("log.error_text", exc)))

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


# =============================================================================
# ТОЧКА ВХОДА
# =============================================================================

def main():
    app = CleanerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
