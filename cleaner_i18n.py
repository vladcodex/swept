#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 vladcodex - https://github.com/vladcodex/swept
# Text and data mining / model training reserved - see NOTICE.
r"""
cleaner_i18n.py — переключение языков интерфейса (русский / английский).

Как это устроено
----------------
    * Все тексты интерфейса собраны в словаре STRINGS по ключам;
      ключ «ru» — исходный текст, «en» — перевод.
    * Модули cleaner_core / cleaner_optimize / cleaner_installer берут
      отсюда же строки журнала и сообщения об ошибках, поэтому журнал
      тоже переключается вместе с интерфейсом.
    * Названия категорий и оптимизаций лежат в самих данных проекта
      (поля title_en / desc_en), а helper fld() выбирает нужный вариант.

Использование:
    import cleaner_i18n as i18n
    i18n.set_language("en")
    print(i18n.t("btn.clean"))          # -> "🧹  Clean"
    print(i18n.fld(item, "title"))      # title_en для en, иначе title
"""

from __future__ import annotations

# Текущий язык: "ru" или "en".
LANG = "ru"

# Названия языков для выпадающего списка. Пишутся на самом языке (эндонимы),
# поэтому список выглядит одинаково при любом текущем языке — как в Reg Organizer.
LANGUAGE_NAMES = {"ru": "Русский", "en": "English"}

# Порядок языков в выпадающем списке.
LANGUAGE_ORDER = ("ru", "en")

# Короткие подписи (использовались прежним переключателем RU/EN).
LANGUAGE_LABELS = tuple((code, code.upper()) for code in LANGUAGE_ORDER)

# Единицы измерения размера (используются в core.format_bytes).
UNITS = {
    "ru": ("Б", "КБ", "МБ", "ГБ", "ТБ"),
    "en": ("B", "KB", "MB", "GB", "TB"),
}


STRINGS = {
    "ru": {
        # ---------------------------------------------------------- общее
        "app.title": "Swept — безопасная очистка системы",
        "app.brand": "🧹  Swept",
        "app.subtitle": "Безопасная очистка Windows 10/11, удаление следов "
                        "и установка программ",
        "admin.yes": "🛡  Права администратора: ЕСТЬ",
        "admin.no": "⚠  Права администратора: НЕТ",
        "admin.chip_yes": "ADMIN",
        "admin.chip_no": "БЕЗ ПРАВ",
        "lang.label": "Язык",

        # ---------------------------------------------- проверка обновлений
        # Плашка в шапке: до нажатия — просто кнопка, сеть не трогается.
        "update.chip": "⭮ ОБНОВЛЕНИЯ",
        "update.checking": "⭮ ПРОВЕРКА…",
        "update.available": "⬆ {0}",
        "update.current": "✔ АКТУАЛЬНО",
        "update.error": "⚠ НЕТ СВЯЗИ",
        "update.log_check": "Проверка обновлений…",
        "update.log_available": "Доступна новая версия {0}. Скачать её можно "
                                "со страницы релизов в настройках.",
        "update.log_current": "Установлена последняя версия ({0}).",
        "update.log_error": "Не удалось проверить обновления: {0}",

        # ------------------------------------------------- окно настроек
        "settings.title": "Настройки",
        "settings.section_ui": "Интерфейс",
        "settings.language_hint": "Язык применяется сразу и запоминается "
                                  "между запусками.",
        "settings.section_behavior": "Поведение",
        "settings.scan_only": "Только сканировать",
        "settings.scan_only_hint": "Кнопка «Очистить» покажет, что удалила бы, "
                                   "но ничего не тронет. Настройка сохраняется.",
        "settings.section_updates": "Обновления",
        "settings.version_now": "Текущая версия: {0}",
        "settings.check_updates": "Проверить обновления",
        "settings.updates_hint": "Запрос уходит на GitHub только по нажатию — "
                                 "при запуске программа в сеть не ходит.",
        "settings.section_storage": "Где хранятся настройки",
        "settings.storage_registry": "Реестр Windows: {0}",
        "settings.storage_file": "Файл рядом с программой: {0}",
        "settings.storage_unknown": "Расположение определить не удалось.",
        "settings.section_about": "О программе",
        "settings.about_text": "Swept {0} — свободная программа для очистки "
                               "и настройки Windows 10/11. Без рекламы, "
                               "телеметрии и фоновых служб.",
        "settings.open_releases": "Страница релизов",
        "settings.license": "Лицензия MIT",
        "settings.close": "Закрыть",

        # --------------------------------------------------------- вкладки
        "tab.clean": "  🧹 Очистка  ",
        "tab.install": "  📦 Установка  ",
        "tab.optimize": "  ⚡ Оптимизация  ",
        "tab.log": "  📋 Журнал  ",
        "tab.schedule": "  ⏰ Расписание  ",

        # --- оболочка Orbit: модули, рельсы, лента ---
        "app.name": "SWEPT",
        "app.version": "v1.5.1",
        "mod.clean": "Очистка",
        "mod.clean.sub": "Категории мусора и кэшей",
        "mod.install": "Установка",
        "mod.install.sub": "Каталог программ и пакеты VC++",
        "mod.optimize": "Оптимизация",
        "mod.optimize.sub": "Безопасные твики Windows",
        "mod.schedule": "Расписание",
        "mod.schedule.sub": "Тихая очистка по расписанию",
        "mod.log": "Журнал",
        "mod.log.sub": "История всех операций",
        "mod.winsxs": "WinSxS",
        "mod.winsxs.sub": "Хранилище компонентов через DISM",
        "rail.system": "Система",
        "rail.disk": "Диск C:",
        "rail.temp": "Временные файлы",
        "rail.bin": "Корзина",
        "rail.categories": "Категорий",
        "rail.files": "Файлов к удалению",
        "rail.restore": "Точка восстановления",
        "rail.total": "Освобождено всего",
        "ribbon.back": "Модули",
        "feed.title": "Журнал",
        "orbit.pick": "Выберите модуль на орбите",
        "orbit.reclaim": "Можно освободить",
        "orbit.freed": "Освобождено",
        "orbit.idle": "Нажмите «Анализ», чтобы начать",
        "orbit.ready": "Готово · выберите «Очистить»",
        "orbit.done": "Готово · всё чисто",
        "orbit.busy": "Выполняется…",
        "orbit.busy_sub": "Это может занять время",
        "orbit.found": "{} категорий · {} файлов",
        "clean.actions_hint": "Кнопки «Анализ», «Очистить» и «Стоп» — в нижней ленте.",
        "clean.top": "Крупнейшие категории",
        "clean.top_empty": "Появятся после анализа",
        "winsxs.b1": "Удаляются только устаревшие компоненты и резервные копии обновлений.",
        "winsxs.b2": "Ключ /ResetBase не используется — последнее обновление остаётся откатываемым.",
        "winsxs.b3": "Очистку нельзя прервать: она занимает от 5 до 20 минут.",

        # ----------------------------- тихая очистка по расписанию
        "sched.title": "Тихая очистка по расписанию",
        "sched.subtitle": "Автоматическая очистка без участия пользователя:\n"
                          "сухой прогон, реальная очистка и авто-создание точки\n"
                          "восстановления перед удалением. Безопасная автоматизация.",
        "sched.enable": "Включить тихую очистку по расписанию",
        "sched.freq": "Частота:",
        "sched.daily": "Ежедневно",
        "sched.weekly": "Еженедельно",
        "sched.time": "Время (чч:мм):",
        "sched.weekday": "День недели:",
        "sched.categories": "Категории для очистки",
        "sched.select_all": "Выбрать всё",
        "sched.clear_all": "Снять всё",
        "sched.restore": "Создавать точку восстановления перед удалением",
        "sched.dry": "Сначала сухой прогон (симуляция), затем реальная очистка",
        "sched.next": "Следующий запуск: {}",
        "sched.next_off": "Расписание выключено",
        "sched.status_idle": "Ожидание расписания…",
        "sched.enabled": "Тихая очистка по расписанию включена.",
        "sched.disabled": "Тихая очистка по расписанию выключена.",
        "sched.busy": "[!] Уже выполняется операция — плановая очистка пропущена.",
        "sched.header": "===== ТИХАЯ ОЧИСТКА ПО РАСПИСАНИЮ =====",
        "sched.dry_header": "===== СУХОЙ ПРОГОН (симуляция) =====",
        "sched.restore_creating": "Создаю точку восстановления перед удалением…",
        "sched.restore_desc": "Swept scheduled cleanup",
        "sched.finished": "Тихая очистка по расписанию завершена.",
        "sched.no_categories": "[!] Не выбрана ни одна категория для тихой очистки — пропускаю.",
        "sched.run_now": "Запустить сейчас",
        "sched.save": "Сохранить расписание",
        "sched.register_task": "Зарегистрировать задачу Windows (нужен админ)",
        "sched.registered": "Задача Windows зарегистрирована: {}",
        "sched.register_failed": "Не удалось зарегистрировать задачу: {}",
        "sched.unregister_task": "Удалить задачу Windows",
        "sched.unregistered": "Задача Windows удалена: {}",
        "sched.unregister_failed": "Не удалось удалить задачу: {}",
        "sched.register_hint": "Автономная задача (schtasks) запускает Swept в фоне,\n"
                               "даже когда окно закрыто. Требует прав администратора.",
        "sched.mon": "Пн", "sched.tue": "Вт", "sched.wed": "Ср",
        "sched.thu": "Чт", "sched.fri": "Пт", "sched.sat": "Сб", "sched.sun": "Вс",

        # --------------------------------------------------------- очистка
        "clean.categories": "Категории очистки",
        "clean.control": "Управление",
        "clean.scan_only": "Только сканирование (не удалять)",
        "clean.total_zero": "Освобождено: 0 Б",
        "clean.total_session": "Освобождено (сессия): {}",
        "clean.total_sim": "Найдено (симуляция): {}",
        "clean.browser_options": "Что очищать",
        "clean.browser_caution": "Удаляет личные данные браузера",
        "dlg.browser_opt_title": "Удаление личных данных",
        "dlg.browser_opt_text": "Вы включаете «{0}». Это безвозвратно удалит "
                                "личные данные браузера (cookie, историю, пароли "
                                "и т.п.). Продолжить?",
        "dlg.warn_shader_cache_title": "Кэш шейдеров видеокарты",
        "dlg.warn_shader_cache_text":
            "«Кэш шейдеров видеокарты» — это уже скомпилированные шейдеры игр "
            "и программ, работающих через GPU.\n\n"
            "Удаление безопасно: они соберутся заново. Но первое время игры "
            "могут подтормаживать и загружаться дольше, пока шейдеры "
            "компилируются. Если место на диске не критично, эту категорию "
            "лучше не отмечать.\n\n"
            "Всё равно включить её?",
        "dlg.confirm_warn_shader_cache":
            "Вместе с остальным будет удалён кэш шейдеров видеокарты: игры "
            "соберут его заново при следующем запуске, возможны "
            "подтормаживания.",
        "btn.analyze": "🔍  Анализ",
        "btn.clean": "🧹  Очистить",
        "btn.stop": "⏹  Стоп",
        "btn.select_all": "Выбрать всё",
        "btn.clear_all": "Снять всё",

        # --------------------------------------------- хранилище компонентов
        "winsxs.title": "Хранилище компонентов (WinSxS)",
        "winsxs.sub": "официальная команда DISM",
        "winsxs.state_unknown": "Надо чистить: —",
        "winsxs.state_yes": "Надо чистить: ДА",
        "winsxs.state_no": "Надо чистить: НЕТ",
        "winsxs.state_fail": "Надо чистить: не удалось проверить",
        "winsxs.check": "Проверить",
        "winsxs.clean": "Очистить WinSxS",
        "winsxs.recheck": "Проверить снова",
        "winsxs.detail": "Хранилище: {} · освободится ≈{}",
        "winsxs.detail_no": "Хранилище: {}",
        "winsxs.detail_pkgs": "пакетов: {}",
        "winsxs.last": "последняя очистка: {}",
        "winsxs.checking": "Проверяю хранилище компонентов…",
        "winsxs.cleaning": "Очищаю хранилище компонентов (5–20 минут)…",
        "winsxs.hint": "WinSxS нельзя чистить удалением файлов — только штатной "
                       "командой DISM. Очистка безопасна: последнее обновление "
                       "остаётся откатываемым.",
        "winsxs.fail_admin": "Нужны права администратора",
        "winsxs.fail_start": "Не удалось запустить DISM",
        "winsxs.fail_timeout": "Превышено время ожидания DISM",
        "winsxs.fail_generic": "Не удалось выполнить операцию DISM",
        "winsxs.fail_unparsed": "DISM завершился, но отчёт не распознан",
        "winsxs.stopped": "Проверка остановлена",
        "winsxs.need_yes": "нужна",
        "winsxs.need_no": "не нужна",
        "dlg.winsxs_title": "Очистка WinSxS",
        "dlg.winsxs_text": "Запустить официальную очистку хранилища компонентов?\n\n"
                           "Удалятся устаревшие компоненты обновлений "
                           "(≈{}).\n"
                           "Операция занимает 5–20 минут, прерывать её нельзя.\n"
                           "Windows не будет перезагружен.",
        "dlg.winsxs_close": "Очистка хранилища компонентов уже выполняется.\n\n"
                            "Прервать её нельзя: если закрыть программу, DISM "
                            "продолжит работу в фоне.\n\n"
                            "Закрыть окно?",
        "log.winsxs_start": "Проверка хранилища компонентов (DISM)…",
        "log.winsxs_recommended": "Рекомендация DISM: очистка {}",
        "log.winsxs_clean_start": "Очистка хранилища компонентов (DISM)…",
        "log.winsxs_clean_done": "Хранилище компонентов очищено",
        "log.winsxs_failed": "Ошибка DISM (код {})",

        # ------------------------------------------------------- установка
        "install.title": "📦  Установка и обновление программ",
        "install.search_ph": "Название программы, например: 7zip, vscode, notepad++",
        "install.results": "Результаты поиска",
        "install.hint": "Здесь появятся найденные программы.\n"
                        "Введите название в поле выше и нажмите «Поиск».",
        "install.no_results": "Ничего не найдено.\n"
                              "Попробуйте другое название или введите ID пакета вручную.",
        "install.count": "— {} шт.",
        "install.found": "Найдено пакетов: {} — щёлкните нужную строку",
        "install.truncated": "— показаны {} из {} (уточните запрос)",
        "install.upgrading_all_hint": "Обновление пакетов…\n"
                                      "Подробный вывод — на вкладке «Журнал».",
        "install.vc_hint": "Установка Visual C++ Redistributable…\n"
                           "Ход установки — на вкладке «Журнал».",
        "presets.title": "Популярные программы",
        "presets.subtitle": "выберите набор и отметьте нужные программы",
        "presets.count": "{} программ",
        "presets.choose": "Выбрать",
        "presets.dialog_title": "Набор «{}»",
        "presets.dialog_hint": "Отметьте программы, которые нужно установить. "
                               "Уже установленные будут пропущены.",
        "presets.select_all": "Отметить все",
        "presets.select_none": "Снять все",
        "presets.install_selected": "Установить ({})",
        "presets.nothing_selected": "Ничего не отмечено — поставьте галочки "
                                    "или нажмите «Отмена».",
        "presets.close": "Отмена",
        "install.preset_hint": "Установка набора «{}»…\n"
                               "Ход установки — на вкладке «Журнал».",
        "pkg.installing_set": "Установка набора «{}»…",
        "log.preset_header": "--- НАБОР: {} ---",
        "log.preset_all_ok": "Все отмеченные программы установлены",
        "log.preset_partial": "Набор установлен не полностью",
        "msg.preset_done": "Установка набора завершена: отмечено программ — {}.",
        "msg.preset_partial": "Не все программы набора установились.\n"
                              "Подробности — на вкладке «Журнал».",
        "install.col_num": "№",
        "install.col_name": "Название",
        "install.col_id": "ID пакета",
        "install.col_version": "Версия",
        "btn.search": "🔍  Поиск",
        "btn.upgrade_all": "🔄  Обновить всё",
        "btn.install": "⬇  Установить",
        "btn.upgrade": "⬆  Обновить",
        "btn.select": "Выбрать",
        "btn.install_vc": "⬇  Установить всё сразу",
        "vc.label": "Visual C++ Redistributable (все версии 2005–2022, x86 и x64):",
        "installer.checking": "Проверка установщика…",
        "installer.ok": "Прямая установка доступна",
        "installer.missing": "⚠  Нужны права администратора для установки",
        "pkg.not_selected": "Пакет не выбран — щёлкните строку",
        "pkg.selected": "Выбран: {}  —  {}",
        "pkg.manual": "Выбран (вручную): {}",
        "pkg.number": "Номер или ID:",
        "pkg.entry_ph": "например: 1  или  7zip.7zip",
        "pkg.chosen": "Пакет выбран. Нажмите «Установить» или «Обновить».",
        "pkg.manual_set": "Пакет задан вручную: {}",
        "pkg.source_manual": "вручную",
        "pkg.selected_status": "Выбран пакет: {}",
        "pkg.searching": "Поиск '{}'…",
        "pkg.updating": "Обновление {}…",
        "pkg.installing": "Установка {}…",
        "pkg.upgrading_all": "Обновление всех пакетов…",
        "pkg.installing_vc": "Установка VC++ Redistributable…",
        "pkg.nothing_found": "Поиск не дал результатов",

        # ---------------------------------------------------- оптимизация
        "opt.title": "Оптимизации Windows 10/11",
        "opt.note": "Только безопасные и обратимые настройки.\n"
                    "Не удаляет файлы и не ломает систему.",
        "opt.control": "Управление",
        "opt.os": "ОС: {} (build {}) | редакция: {}",
        "opt.admin_note": "Пункты с пометкой «админ» требуют прав администратора.\n"
                          "Без админа они будут безопасно пропущены.",
        "btn.apply": "⚙  Применить выбранное",
        "btn.restore_point": "🛡  Точка восстановления",
        "btn.mark_safe": "Отметить безопасные",
        "opt.running": "Оптимизация Windows…",
        "opt.restore_running": "Создание точки восстановления…",
        "opt.restore_creating": "Создаю точку восстановления системы…",
        "opt.restore_ok": "Точка восстановления создана.",
        "opt.restore_skip": "Точка восстановления не создана: {}",
        "opt.restore_skip_no_admin": "Без прав администратора точку восстановления создать нельзя — пропускаем.",
        "opt.restore_fail": "Не удалось создать точку восстановления",

        # --------------------------------------------- разбор «почему тормозит»
        "diag.title": "РАЗБОР: ПОЧЕМУ ТОРМОЗИТ",
        "diag.run": "Разобрать",
        "diag.scanning": "Измеряю систему…",
        "diag.idle": "Измерю систему и покажу, что именно её замедляет.",
        "diag.verdict_excellent": "Отлично — всё в порядке",
        "diag.verdict_good": "Хорошо, есть мелочи",
        "diag.verdict_fair": "Есть что поправить",
        "diag.verdict_bad": "Сильно тормозит",
        "diag.no_causes": "Причин не найдено",
        "diag.more": "и ещё {n}…",
        "diag.fix": "Отметить исправления ({n})",
        "diag.fix_none": "Исправлять нечего",
        "diag.already": "Всё найденное уже отмечено — проверьте список.",
        "diag.marked": "Отмечено пунктов: {n} — проверьте список и нажмите "
                       "«Применить выбранное».",
        "diag.delta": "Было {old} → стало {new} ({sign}{diff})",
        "diag.cause_startup_many": "Автозагрузка: {n} программ",
        "diag.cause_disk_low": "Диск {drive} — свободно {free} ({pct}%)",
        "diag.cause_disk_hdd": "Системный диск — HDD",
        "diag.cause_ram_low": "ОЗУ всего {gb} ГБ",
        "diag.cause_ram_full": "ОЗУ занята на {pct}%",
        "diag.cause_telemetry": "Телеметрия и диагностика работают",
        "diag.cause_gamedvr": "Game DVR пишет в фоне",
        "diag.cause_background": "Фоновые приложения разрешены",
        "diag.cause_power": "Схема питания: {plan}",
        "diag.cause_visualfx": "Визуальные эффекты на максимум",
        "diag.plan_high": "высокая производительность",
        "diag.plan_balanced": "сбалансированная",
        "diag.plan_saver": "экономия энергии",
        "diag.plan_other": "своя",

        # ---------------------------------------------------------- журнал
        "log.title": "📋  Журнал операций",
        "status.ready": "Готово к работе",
        "status.done": "Готово",
        "status.stopping": "Останавливаю…",
        "status.scanning": "Сканирование…",
        "status.cleaning": "Очистка…",
        "status.opt_done": "Оптимизация завершена",
        "status.restore_done": "Точка восстановления создана",

        # --------------------------------------------------------- диалоги
        "dlg.ok": "Готово",
        "dlg.error": "Ошибка",
        "dlg.optimization": "Оптимизация",
        "dlg.restore_done": "Точка восстановления",
        "dlg.confirm": "Подтверждение",
        "dlg.no_admin_title": "Нет прав администратора",
        "dlg.no_admin_text": "Программа запущена без прав администратора.\n\n"
                             "Часть системных файлов (C:\\Windows\\Temp, кэш обновлений) "
                             "будет недоступна и пропущена.\n\n"
                             "Чтобы получить права, нажмите на плашку «Без прав» "
                             "в шапке окна.",
        "dlg.no_admin_ask": "Программа запущена без прав администратора.\n\n"
                            "Часть системных файлов (C:\\Windows\\Temp, кэш обновлений) "
                            "будет недоступна и пропущена.\n\n"
                            "Перезапустить с правами администратора?",
        "dlg.no_categories_title": "Нет категорий",
        "dlg.no_categories_text": "Отметьте хотя бы одну категорию.",
        "dlg.confirm_clean_title": "Подтверждение очистки",
        "dlg.confirm_clean_text": "Будет выполнено РЕАЛЬНОЕ удаление файлов в выбранных "
                                  "категориях.\n\nПродолжить?",
        "dlg.browser_running_title": "Браузеры запущены",
        "dlg.browser_running_text": "Запущены браузеры: {}.\n\nИх кэш, история и куки могут "
                                    "быть заняты работающими процессами, и очистка пропустит "
                                    "часть файлов или не сможет удалить их.\n\n"
                                    "Закрыть браузеры перед очисткой?",
        "dlg.pkg_select_title": "Выбор пакета",
        "dlg.pkg_select_text": "Введите номер из списка результатов или ID пакета.",
        "dlg.close_title": "Операция выполняется",
        "dlg.close_text": "Идёт операция. Прервать её и закрыть программу?",
        "dlg.bad_number_title": "Неверный номер",
        "dlg.bad_number_text": "В списке {} пакетов. Введите номер от 1 до {}.",
        "dlg.empty_query_title": "Пустой запрос",
        "dlg.empty_query_text": "Введите название программы для поиска.",
        "dlg.installer_title": "Установка",
        "dlg.installer_text": "Безопасный установщик ещё не готов или нет прав администратора.\n"
                           "Запустите Swept от имени администратора и попробуйте снова.",
        "dlg.install_pkg_text": "Установить '{}'?\n\n"
                                "Файл будет скачан с официального сайта, проверен по цифровой "
                                "подписи и запущен в тихом режиме.",
        "dlg.upgrade_pkg_text": "Обновить '{}'?",
        "dlg.upgrade_all_text": "Проверить обновления?\n\n"
                                "Лаунчеры обновляются автоматически при запуске — "
                                "отдельное обновление не требуется.",
        "dlg.vc_text": "Установить все Visual C++ Redistributable (2005–2022) "
                       "для x86 и x64?\n\n"
                       "Всего {} пакетов. Файлы скачиваются с сайта Microsoft, проверяются "
                       "по цифровой подписи и ставятся по очереди.\n"
                       "Ход установки — на вкладке «Журнал».",
        "dlg.no_items_title": "Нет пунктов",
        "dlg.no_items_text": "Отметьте хотя бы один пункт оптимизации.",
        "dlg.hibernate_title": "Гибернация",
        "dlg.hibernate_text": "Вы выбрали «Отключить гибернацию».\n\n"
                              "Это освободит место, но отключит быстрый запуск Windows.\n"
                              "Вернуть можно командой: powercfg /h on\n\nПродолжить?",
        "dlg.debloat_title": "Удаление приложений",
        "dlg.debloat_text": "Вы выбрали «Удалить встроенные приложения».\n\n"
                            "Будут удалены рекламные/доп. приложения (Погода, Новости, "
                            "Карты, Skype, пасьянсы, Candy Crush и т.п.) у текущего "
                            "пользователя.\n"
                            "Системные приложения и ваши данные НЕ затрагиваются.\n"
                            "Вернуть всё можно из Microsoft Store.\n\nПродолжить?",

        # ---------------------------------------------- журнал (интерфейс)
        "log.ui_error": "[ОШИБКА ИНТЕРФЕЙСА] ",
        "log.error": "[ОШИБКА] ",
        "log.admin_ok": "[i] Запущено с правами администратора — доступны все категории.",
        "log.admin_no_1": "[!] Нет прав администратора. Часть системных файлов "
                          "(Windows\\Temp, кэш обновлений) будет пропущена.",
        "log.admin_no_2": "    Для полной очистки запустите программу от имени администратора.",
        "log.stop_requested": "[!] Запрошена остановка…",
        "log.scan_header": "========== СКАНИРОВАНИЕ ==========",
        "log.clean_header": "========== ОЧИСТКА ({}) ==========",
        "log.result_header": "========== ИТОГ ==========",
        "log.mode_sim": "симуляция",
        "log.mode_real": "реальное удаление",
        "log.scan_total": "  Всего найдено: {}",
        "log.browsers_busy": "[!] Запущены браузеры: {} — их кэш/история/куки заняты "
                             "и будут пропущены.",
        "log.browsers_closing": "  ⏳ Закрываю браузеры: {}…",
        "log.browsers_closed": "  ✔ Браузеры закрыты: {}.",
        "log.browsers_close_failed": "  ⚠ Не удалось закрыть браузеры: {} — очистка "
                                     "продолжится без закрытия.",
        "log.analysis_status": "Анализ завершён: {}",
        "log.analysis_text": "Анализ завершён.\n\nНайдено: {}\nОбъём: {}",
        "log.clean_result": "{}\n"
                            "  Удалено объектов: {}\n"
                            "  Пропущено: {}\n"
                            "  Ошибок доступа: {}\n"
                            "  Освобождено: {}",
        "log.clean_done": "ОЧИСТКА ЗАВЕРШЕНА",
        "log.sim_done": "СИМУЛЯЦИЯ (файлы не удалялись)",
        "log.finished_error": "Завершено с ошибкой",
        "log.error_text": "Произошла ошибка:\n{}",
        "log.search_done": "Поиск завершён",
        "log.search_error": "Ошибка поиска",
        "log.install_header": "========== УСТАНОВКА ==========",
        "log.upgrade_header": "========== ОБНОВЛЕНИЕ ==========",
        "log.upgrade_all_header": "========== ОБНОВЛЕНИЕ ВСЕХ ПАКЕТОВ ==========",
        "log.vc_header": "========== УСТАНОВКА VC++ REDISTRIBUTABLE ==========",
        "log.result_prefix": "РЕЗУЛЬТАТ: {}",
        "log.success": "УСПЕХ",
        "log.failure": "ОШИБКА",
        "log.no_updates": "ОБНОВЛЕНИЙ НЕ ТРЕБУЕТСЯ",
        "log.vc_all_ok": "УСПЕХ — все установлены",
        "log.vc_partial": "ЧАСТИЧНО/ЕСТЬ ОШИБКИ — см. выше",
        "log.opt_header": "========== ОПТИМИЗАЦИЯ WINDOWS ==========",
        "log.opt_item": "--- {} {} ---",
        "log.opt_ok": "  ✔ выполнено",
        "log.opt_skipped": "  ⛔ пропущено (нет прав администратора)",
        "log.opt_unsupported": "  ⛔ недоступно: Windows защищает это значение реестра",
        "log.opt_failed": "  ⚠ ошибка: {}",
        "log.opt_unknown": "неизвестная",
        "log.opt_stopped": "[!] Остановлено пользователем.",
        "log.opt_result": "Оптимизация завершена:\n"
                          "  Выполнено: {}\n"
                          "  Пропущено (нет прав админа): {}\n"
                          "  Недоступно в этой сборке Windows: {}\n"
                          "  Ошибки: {}",
        "log.opt_detail": "  • {} — {}",
        "log.diag_marked": "  ✔ разбор: отмечено пунктов — {}",
        "log.diag_report": "  • разбор системы: {}/100 — причин: {}",
        "log.restore_ok": "  ✔ точка восстановления системы создана",
        "log.restore_fail": "  ⚠ не удалось создать точку восстановления: {}",
        "log.restore_no_admin": "  ⚠ нужны права администратора — точка восстановления не создана",
        "msg.install_done": "Установка завершена.",
        "msg.install_error": "Ошибка при установке.",
        "msg.upgrade_done": "Обновление завершено.",
        "msg.upgrade_error": "Ошибка при обновлении.",
        "msg.no_updates": "Обновлений не найдено — все программы уже актуальны.",
        "msg.vc_done": "Установка VC++ завершена.",
        "msg.vc_partial": "Часть пакетов не установилась — подробности в журнале.",

        # ------------------------------------------- сообщения ядра (core)
        "core.recycle_stat": "[Корзина] объектов: {}, объём: {}",
        "core.no_folder": "[пропуск] нет папки: {}",
        "core.root_unsafe": "[пропуск] небезопасный путь: {}",
        "core.root_reparse": "[пропуск] путь является ссылкой (junction/symlink): {}",
        "core.root_personal": "[пропуск] путь ведёт в личную папку пользователя: {}",
        "core.scanning": "Сканирование: {} ({}/{})",
        "core.cleaning": "Очистка: {} ({}/{})",
        "core.sim_prefix": "  ◦ (симуляция) ",
        "core.protected": "  ⛔ защищено, пропуск: {}",
        "core.busy": "  ⚠ занято/нет доступа: {}",
        "core.sim_recycle": "  ◦ (симуляция) очистка Корзины",
        "core.recycle_ok": "  ✔ Корзина очищена",
        "core.recycle_fail": "  ⚠ не удалось очистить Корзину",

        # -------------------------------------- сообщения оптимизации (opt)
        "opt.admin_required": "нужны права администратора",
        "opt.admin_suffix": " (нужны права администратора)",
        "opt.key_protected": "Windows защищает это значение реестра — изменение недоступно",
        "opt.power_list_fail": "не удалось получить список схем электропитания",
        "opt.not_windows": "[!] Модуль оптимизации работает только в Windows.",
        "opt.items_count": "Оптимизация: {} пунктов",
        "opt.live_title": "Ход выполнения",
        "opt.badge_admin": " · админ",
        "opt.applying_step": "Применяю {}/{}: {}",
        "opt.item_stopped": "не выполнялось",

        # ------------------------------------ сообщения установщика (installer)
        "inst.timeout": "Превышено время ожидания ({} сек)",
        "inst.latest": "Уже последняя версия.\n",
        "inst.log_install": "Установка '{}'...",
        "inst.log_upgrade": "Обновление '{}'...",
        "inst.log_item": "--- {} ({}) ---",
        "inst.status_ok": "ОК",
        "inst.status_error": "ОШИБКА",
        "inst.log_upgrade_all": "Обновление всех пакетов... "
                                "Это может занять несколько минут.",
        "inst.bad_id": "Некорректный ID пакета: «{}».\n"
                       "Допустимы только латиница, цифры и символы . _ + -",
        "inst.bad_query": "Некорректный поисковый запрос: «{}».\n"
                          "Запрос не должен начинаться с дефиса и быть длиннее 128 символов.",
    },

    "en": {
        # ---------------------------------------------------------- общее
        "app.title": "Swept — safe Windows cleanup",
        "app.brand": "🧹  Swept",
        "app.subtitle": "Safe cleanup of Windows 10/11, trace removal "
                        "and app installation",
        "admin.yes": "🛡  Administrator rights: YES",
        "admin.no": "⚠  Administrator rights: NO",
        "admin.chip_yes": "ADMIN",
        "admin.chip_no": "NO ADMIN",
        "lang.label": "Language",

        # ------------------------------------------------ update check
        # Header chip: a plain button until pressed — no network before that.
        "update.chip": "⭮ UPDATES",
        "update.checking": "⭮ CHECKING…",
        "update.available": "⬆ {0}",
        "update.current": "✔ UP TO DATE",
        "update.error": "⚠ NO CONNECTION",
        "update.log_check": "Checking for updates…",
        "update.log_available": "Version {0} is available. Download it from "
                                "the releases page in Settings.",
        "update.log_current": "The latest version is installed ({0}).",
        "update.log_error": "Could not check for updates: {0}",

        # ---------------------------------------------------- settings window
        "settings.title": "Settings",
        "settings.section_ui": "Interface",
        "settings.language_hint": "Applied immediately and remembered "
                                  "between runs.",
        "settings.section_behavior": "Behaviour",
        "settings.scan_only": "Scan only",
        "settings.scan_only_hint": "The Clean button will report what it would "
                                   "delete without touching anything. Saved.",
        "settings.section_updates": "Updates",
        "settings.version_now": "Current version: {0}",
        "settings.check_updates": "Check for updates",
        "settings.updates_hint": "The request goes to GitHub only when you press "
                                 "it — nothing is sent at startup.",
        "settings.section_storage": "Where settings are stored",
        "settings.storage_registry": "Windows registry: {0}",
        "settings.storage_file": "File next to the program: {0}",
        "settings.storage_unknown": "Could not determine the location.",
        "settings.section_about": "About",
        "settings.about_text": "Swept {0} — free software for cleaning and "
                               "tuning Windows 10/11. No ads, no telemetry, "
                               "no background services.",
        "settings.open_releases": "Releases page",
        "settings.license": "MIT license",
        "settings.close": "Close",

        # --------------------------------------------------------- вкладки
        "tab.clean": "  🧹 Cleanup  ",
        "tab.install": "  📦 Install  ",
        "tab.optimize": "  ⚡ Optimize  ",
        "tab.log": "  📋 Log  ",
        "tab.schedule": "  ⏰ Schedule  ",

        # --- Orbit shell: modules, rails, ribbon ---
        "app.name": "SWEPT",
        "app.version": "v1.5.1",
        "mod.clean": "Cleanup",
        "mod.clean.sub": "Junk and cache categories",
        "mod.install": "Install",
        "mod.install.sub": "App catalog and VC++ packages",
        "mod.optimize": "Optimize",
        "mod.optimize.sub": "Safe Windows tweaks",
        "mod.schedule": "Schedule",
        "mod.schedule.sub": "Silent cleanup on a schedule",
        "mod.log": "Log",
        "mod.log.sub": "History of every operation",
        "mod.winsxs": "WinSxS",
        "mod.winsxs.sub": "Component store via DISM",
        "rail.system": "System",
        "rail.disk": "Drive C:",
        "rail.temp": "Temp files",
        "rail.bin": "Recycle Bin",
        "rail.categories": "Categories",
        "rail.files": "Files to remove",
        "rail.restore": "Restore point",
        "rail.total": "Freed in total",
        "ribbon.back": "Modules",
        "feed.title": "Log",
        "orbit.pick": "Pick a module on the orbit",
        "orbit.reclaim": "Reclaimable",
        "orbit.freed": "Freed",
        "orbit.idle": "Press Analyze to start",
        "orbit.ready": "Ready · choose Clean",
        "orbit.done": "Done · all clear",
        "orbit.busy": "Working…",
        "orbit.busy_sub": "This may take a while",
        "orbit.found": "{} categories · {} files",
        "clean.actions_hint": "Analyze, Clean and Stop are in the bottom ribbon.",
        "clean.top": "Largest categories",
        "clean.top_empty": "Appear after analysis",
        "winsxs.b1": "Only outdated components and update backups are removed.",
        "winsxs.b2": "/ResetBase is never used — the latest update stays rollbackable.",
        "winsxs.b3": "Cleanup cannot be interrupted: it takes 5 to 20 minutes.",

        # ----------------------------- quiet scheduled cleanup
        "sched.title": "Quiet scheduled cleanup",
        "sched.subtitle": "Automatic cleanup with no user interaction:\n"
                          "dry run, real cleanup and an automatic restore point\n"
                          "before deletion. Safe automation.",
        "sched.enable": "Enable quiet scheduled cleanup",
        "sched.freq": "Frequency:",
        "sched.daily": "Daily",
        "sched.weekly": "Weekly",
        "sched.time": "Time (hh:mm):",
        "sched.weekday": "Weekday:",
        "sched.categories": "Categories to clean",
        "sched.select_all": "Select all",
        "sched.clear_all": "Clear all",
        "sched.restore": "Create a restore point before deletion",
        "sched.dry": "Run a dry run (simulation) first, then real cleanup",
        "sched.next": "Next run: {}",
        "sched.next_off": "Schedule is off",
        "sched.status_idle": "Waiting for the schedule…",
        "sched.enabled": "Quiet scheduled cleanup is enabled.",
        "sched.disabled": "Quiet scheduled cleanup is disabled.",
        "sched.busy": "[!] An operation is already running — scheduled cleanup skipped.",
        "sched.header": "===== QUIET SCHEDULED CLEANUP =====",
        "sched.dry_header": "===== DRY RUN (simulation) =====",
        "sched.restore_creating": "Creating a restore point before deletion…",
        "sched.restore_desc": "Swept scheduled cleanup",
        "sched.finished": "Quiet scheduled cleanup finished.",
        "sched.no_categories": "[!] No category selected for quiet cleanup — skipping.",
        "sched.run_now": "Run now",
        "sched.save": "Save schedule",
        "sched.register_task": "Register Windows task (admin required)",
        "sched.registered": "Windows task registered: {}",
        "sched.register_failed": "Failed to register task: {}",
        "sched.unregister_task": "Remove Windows task",
        "sched.unregistered": "Windows task removed: {}",
        "sched.unregister_failed": "Failed to remove task: {}",
        "sched.register_hint": "An offline task (schtasks) runs Swept in the background,\n"
                               "even with the window closed. Requires admin to register.",
        "sched.mon": "Mon", "sched.tue": "Tue", "sched.wed": "Wed",
        "sched.thu": "Thu", "sched.fri": "Fri", "sched.sat": "Sat", "sched.sun": "Sun",

        # --------------------------------------------------------- очистка
        "clean.categories": "Cleanup categories",
        "clean.control": "Controls",
        "clean.scan_only": "Scan only (do not delete)",
        "clean.total_zero": "Freed: 0 B",
        "clean.total_session": "Freed (session): {}",
        "clean.total_sim": "Found (simulation): {}",
        "clean.browser_options": "What to clean",
        "clean.browser_caution": "Removes the browser's personal data",
        "dlg.browser_opt_title": "Removing personal data",
        "dlg.browser_opt_text": "You are enabling “{0}”. This will permanently "
                                "delete the browser's personal data (cookies, "
                                "history, passwords, etc.). Continue?",
        "dlg.warn_shader_cache_title": "GPU shader cache",
        "dlg.warn_shader_cache_text":
            "The GPU shader cache holds shaders that games and GPU apps have "
            "already compiled.\n\n"
            "Deleting it is safe — they get rebuilt. But for a while games may "
            "stutter and load slower while shaders are compiled again. If you "
            "are not short on disk space, it is better to leave this category "
            "off.\n\n"
            "Enable it anyway?",
        "dlg.confirm_warn_shader_cache":
            "The GPU shader cache will be deleted along with everything else: "
            "games will rebuild it on their next launch, which can cause "
            "temporary stutter.",
        "btn.analyze": "🔍  Analyze",
        "btn.clean": "🧹  Clean",
        "btn.stop": "⏹  Stop",
        "btn.select_all": "Select all",
        "btn.clear_all": "Clear all",

        # --------------------------------------------- component store
        "winsxs.title": "Component store (WinSxS)",
        "winsxs.sub": "official DISM command",
        "winsxs.state_unknown": "Cleanup needed: —",
        "winsxs.state_yes": "Cleanup needed: YES",
        "winsxs.state_no": "Cleanup needed: NO",
        "winsxs.state_fail": "Cleanup needed: check failed",
        "winsxs.check": "Check",
        "winsxs.clean": "Clean WinSxS",
        "winsxs.recheck": "Check again",
        "winsxs.detail": "Store: {} · frees ≈{}",
        "winsxs.detail_no": "Store: {}",
        "winsxs.detail_pkgs": "packages: {}",
        "winsxs.last": "last cleanup: {}",
        "winsxs.checking": "Analyzing the component store…",
        "winsxs.cleaning": "Cleaning the component store (5–20 minutes)…",
        "winsxs.hint": "WinSxS cannot be cleaned by deleting files — only with the "
                       "official DISM command. It is safe: the latest update stays "
                       "uninstallable.",
        "winsxs.fail_admin": "Administrator rights required",
        "winsxs.fail_start": "Could not start DISM",
        "winsxs.fail_timeout": "DISM timed out",
        "winsxs.fail_generic": "DISM operation failed",
        "winsxs.fail_unparsed": "DISM finished but the report was not recognized",
        "winsxs.stopped": "Check stopped",
        "winsxs.need_yes": "required",
        "winsxs.need_no": "not required",
        "dlg.winsxs_title": "WinSxS cleanup",
        "dlg.winsxs_text": "Run the official component store cleanup?\n\n"
                           "Superseded update components will be removed "
                           "(≈{}).\n"
                           "It takes 5–20 minutes and cannot be interrupted.\n"
                           "Windows will not be restarted.",
        "dlg.winsxs_close": "The component store cleanup is already running.\n\n"
                            "It cannot be interrupted: if you close the program, "
                            "DISM keeps working in the background.\n\n"
                            "Close the window?",
        "log.winsxs_start": "Analyzing the component store (DISM)…",
        "log.winsxs_recommended": "DISM recommendation: cleanup {}",
        "log.winsxs_clean_start": "Cleaning the component store (DISM)…",
        "log.winsxs_clean_done": "Component store cleaned",
        "log.winsxs_failed": "DISM error (code {})",

        # ------------------------------------------------------- установка
        "install.title": "📦  Install and update apps",
        "install.search_ph": "App name, e.g. 7zip, vscode, notepad++",
        "install.results": "Search results",
        "install.hint": "Found packages will appear here.\n"
                        "Type a name in the field above and press Search.",
        "install.no_results": "Nothing found.\n"
                              "Try another name or enter the package ID manually.",
        "install.count": "— {} found",
        "install.found": "Packages found: {} — click the one you need",
        "install.truncated": "— showing {} of {} (narrow your query)",
        "install.upgrading_all_hint": "Updating packages…\n"
                                      "Detailed output is on the Log tab.",
        "install.vc_hint": "Installing Visual C++ Redistributable…\n"
                           "Progress is shown on the Log tab.",
        "presets.title": "Popular apps",
        "presets.subtitle": "pick a set and tick the apps you need",
        "presets.count": "{} apps",
        "presets.choose": "Choose",
        "presets.dialog_title": "Set “{}”",
        "presets.dialog_hint": "Tick the apps you want to install. "
                               "Already installed ones are skipped.",
        "presets.select_all": "Select all",
        "presets.select_none": "Clear all",
        "presets.install_selected": "Install ({})",
        "presets.nothing_selected": "Nothing is ticked — select at least one app "
                                    "or press Cancel.",
        "presets.close": "Cancel",
        "install.preset_hint": "Installing the “{}” set…\n"
                               "Progress is shown on the Log tab.",
        "pkg.installing_set": "Installing the “{}” set…",
        "log.preset_header": "--- SET: {} ---",
        "log.preset_all_ok": "All selected apps were installed",
        "log.preset_partial": "The set was installed only partially",
        "msg.preset_done": "The set is installed: {} apps selected.",
        "msg.preset_partial": "Not every app from the set was installed.\n"
                              "Details are on the Log tab.",
        "install.col_num": "No.",
        "install.col_name": "Name",
        "install.col_id": "Package ID",
        "install.col_version": "Version",
        "btn.search": "🔍  Search",
        "btn.upgrade_all": "🔄  Update all",
        "btn.install": "⬇  Install",
        "btn.upgrade": "⬆  Upgrade",
        "btn.select": "Select",
        "btn.install_vc": "⬇  Install all at once",
        "vc.label": "Visual C++ Redistributable (all versions 2005–2022, x86 and x64):",
        "installer.checking": "Checking installer…",
        "installer.ok": "Direct install available",
        "installer.missing": "⚠  Administrator rights are required for installation",
        "pkg.not_selected": "No package selected — click a row",
        "pkg.selected": "Selected: {}  —  {}",
        "pkg.manual": "Selected (manual): {}",
        "pkg.number": "Number or ID:",
        "pkg.entry_ph": "e.g. 1  or  7zip.7zip",
        "pkg.chosen": "Package selected. Press Install or Upgrade.",
        "pkg.manual_set": "Package set manually: {}",
        "pkg.source_manual": "manual",
        "pkg.selected_status": "Package selected: {}",
        "pkg.searching": "Searching '{}'…",
        "pkg.updating": "Updating {}…",
        "pkg.installing": "Installing {}…",
        "pkg.upgrading_all": "Updating all packages…",
        "pkg.installing_vc": "Installing VC++ Redistributable…",
        "pkg.nothing_found": "The search returned nothing",

        # ---------------------------------------------------- оптимизация
        "opt.title": "Windows 10/11 optimizations",
        "opt.note": "Safe and reversible settings only.\n"
                    "No files are deleted and the system stays intact.",
        "opt.control": "Controls",
        "opt.os": "OS: {} (build {}) | edition: {}",
        "opt.admin_note": "Items marked “admin” require administrator rights.\n"
                          "Without them they are skipped safely.",
        "btn.apply": "⚙  Apply selected",
        "btn.restore_point": "🛡  Restore point",
        "btn.mark_safe": "Mark safe defaults",
        "opt.running": "Optimizing Windows…",
        "opt.restore_running": "Creating restore point…",
        "opt.restore_creating": "Creating a system restore point…",
        "opt.restore_ok": "Restore point created.",
        "opt.restore_skip": "Restore point not created: {}",
        "opt.restore_skip_no_admin": "Without administrator rights a restore point cannot be created — skipping.",
        "opt.restore_fail": "Failed to create a restore point",

        # ------------------------------------------------ "why it's slow" audit
        "diag.title": "AUDIT: WHY IT'S SLOW",
        "diag.run": "Analyse",
        "diag.scanning": "Measuring the system…",
        "diag.idle": "I'll measure the system and show what slows it down.",
        "diag.verdict_excellent": "Excellent — nothing to fix",
        "diag.verdict_good": "Good, minor things only",
        "diag.verdict_fair": "Worth fixing",
        "diag.verdict_bad": "Seriously slow",
        "diag.no_causes": "No causes found",
        "diag.more": "and {n} more…",
        "diag.fix": "Tick fixes ({n})",
        "diag.fix_none": "Nothing to fix",
        "diag.already": "Everything found is already ticked — check the list.",
        "diag.marked": "Ticked {n} item(s) — review the list and press "
                       "\"Apply selected\".",
        "diag.delta": "Was {old} → now {new} ({sign}{diff})",
        "diag.cause_startup_many": "Startup: {n} programs",
        "diag.cause_disk_low": "Drive {drive} — {free} free ({pct}%)",
        "diag.cause_disk_hdd": "System drive is an HDD",
        "diag.cause_ram_low": "Only {gb} GB of RAM",
        "diag.cause_ram_full": "RAM is {pct}% full",
        "diag.cause_telemetry": "Telemetry and diagnostics are running",
        "diag.cause_gamedvr": "Game DVR records in the background",
        "diag.cause_background": "Background apps are allowed",
        "diag.cause_power": "Power plan: {plan}",
        "diag.cause_visualfx": "Visual effects are maxed out",
        "diag.plan_high": "high performance",
        "diag.plan_balanced": "balanced",
        "diag.plan_saver": "power saver",
        "diag.plan_other": "custom",

        # ---------------------------------------------------------- журнал
        "log.title": "📋  Operations log",
        "status.ready": "Ready",
        "status.done": "Done",
        "status.stopping": "Stopping…",
        "status.scanning": "Scanning…",
        "status.cleaning": "Cleaning…",
        "status.opt_done": "Optimization finished",
        "status.restore_done": "Restore point created",

        # --------------------------------------------------------- диалоги
        "dlg.ok": "Done",
        "dlg.error": "Error",
        "dlg.optimization": "Optimization",
        "dlg.restore_done": "Restore point",
        "dlg.confirm": "Confirm",
        "dlg.no_admin_title": "Administrator rights required",
        "dlg.no_admin_text": "The program is running without administrator rights.\n\n"
                             "Some system files (C:\\Windows\\Temp, update cache) will be "
                             "unavailable and skipped.\n\n"
                             "To get them, click the \"NO ADMIN\" badge in the window "
                             "header.",
        "dlg.no_admin_ask": "The program is running without administrator rights.\n\n"
                            "Some system files (C:\\Windows\\Temp, update cache) will be "
                            "unavailable and skipped.\n\n"
                            "Restart with administrator rights?",
        "dlg.no_categories_title": "No categories",
        "dlg.no_categories_text": "Select at least one category.",
        "dlg.confirm_clean_title": "Confirm cleanup",
        "dlg.confirm_clean_text": "Files in the selected categories will be ACTUALLY "
                                  "deleted.\n\nContinue?",
        "dlg.browser_running_title": "Browsers are running",
        "dlg.browser_running_text": "Browsers are running: {}.\n\nTheir cache, history and "
                                    "cookies may be locked by the running processes, so the "
                                    "cleanup will skip or fail to delete some files.\n\n"
                                    "Close the browsers before cleaning?",
        "dlg.pkg_select_title": "Select package",
        "dlg.pkg_select_text": "Enter a number from the results list or a package ID.",
        "dlg.close_title": "Operation in progress",
        "dlg.close_text": "An operation is running. Interrupt it and close the app?",
        "dlg.bad_number_title": "Invalid number",
        "dlg.bad_number_text": "The list has {} packages. Enter a number from 1 to {}.",
        "dlg.empty_query_title": "Empty query",
        "dlg.empty_query_text": "Enter an app name to search for.",
        "dlg.installer_title": "Install",
        "dlg.installer_text": "The secure installer is not ready yet, or administrator "
                           "rights are missing.\nRun Swept as administrator and try again.",
        "dlg.install_pkg_text": "Install '{}'?\n\n"
                                "The file is downloaded from the official site, checked "
                                "against its digital signature and run silently.",
        "dlg.upgrade_pkg_text": "Upgrade '{}'?",
        "dlg.upgrade_all_text": "Check for updates?\n\n"
                                "Launchers update themselves on start — a separate "
                                "upgrade is not required.",
        "dlg.vc_text": "Install all Visual C++ Redistributable (2005–2022) "
                       "for x86 and x64?\n\n"
                       "{} packages in total. Files are downloaded from Microsoft, "
                       "verified against their signatures and installed one by one.\n"
                       "Progress is shown on the Log tab.",
        "dlg.no_items_title": "No items",
        "dlg.no_items_text": "Select at least one optimization item.",
        "dlg.hibernate_title": "Hibernation",
        "dlg.hibernate_text": "You selected “Disable hibernation”.\n\n"
                              "This frees disk space but turns off Windows Fast Startup.\n"
                              "Revert with: powercfg /h on\n\nContinue?",
        "dlg.debloat_title": "App removal",
        "dlg.debloat_text": "You selected “Remove built-in apps”.\n\n"
                            "Promotional and extra apps (Weather, News, Maps, Skype, "
                            "Solitaire, Candy Crush, etc.) will be removed for the "
                            "current user.\n"
                            "System apps and your data are NOT affected.\n"
                            "Everything can be reinstalled from the Microsoft Store.\n\n"
                            "Continue?",

        # ---------------------------------------------- журнал (интерфейс)
        "log.ui_error": "[UI ERROR] ",
        "log.error": "[ERROR] ",
        "log.admin_ok": "[i] Running as administrator — all categories are available.",
        "log.admin_no_1": "[!] No administrator rights. Some system files "
                          "(Windows\\Temp, update cache) will be skipped.",
        "log.admin_no_2": "    For a full cleanup run the program as administrator.",
        "log.stop_requested": "[!] Stop requested…",
        "log.scan_header": "========== SCANNING ==========",
        "log.clean_header": "========== CLEANUP ({}) ==========",
        "log.result_header": "========== RESULT ==========",
        "log.mode_sim": "simulation",
        "log.mode_real": "actual deletion",
        "log.scan_total": "  Total found: {}",
        "log.browsers_busy": "[!] Browsers are running: {} — their cache/history/cookies "
                             "are in use and will be skipped.",
        "log.browsers_closing": "  ⏳ Closing browsers: {}…",
        "log.browsers_closed": "  ✔ Browsers closed: {}.",
        "log.browsers_close_failed": "  ⚠ Could not close the browsers: {} — cleanup will "
                                     "continue without closing them.",
        "log.analysis_status": "Analysis finished: {}",
        "log.analysis_text": "Analysis finished.\n\nFound: {}\nSize: {}",
        "log.clean_result": "{}\n"
                            "  Objects deleted: {}\n"
                            "  Skipped: {}\n"
                            "  Access errors: {}\n"
                            "  Freed: {}",
        "log.clean_done": "CLEANUP FINISHED",
        "log.sim_done": "SIMULATION (no files were deleted)",
        "log.finished_error": "Finished with errors",
        "log.error_text": "An error occurred:\n{}",
        "log.search_done": "Search finished",
        "log.search_error": "Search error",
        "log.install_header": "========== INSTALLATION ==========",
        "log.upgrade_header": "========== UPGRADE ==========",
        "log.upgrade_all_header": "========== UPDATING ALL PACKAGES ==========",
        "log.vc_header": "========== INSTALLING VC++ REDISTRIBUTABLE ==========",
        "log.result_prefix": "RESULT: {}",
        "log.success": "SUCCESS",
        "log.failure": "FAILED",
        "log.no_updates": "NO UPDATES REQUIRED",
        "log.vc_all_ok": "SUCCESS — all installed",
        "log.vc_partial": "PARTIAL / ERRORS — see above",
        "log.opt_header": "========== WINDOWS OPTIMIZATION ==========",
        "log.opt_item": "--- {} {} ---",
        "log.opt_ok": "  ✔ done",
        "log.opt_skipped": "  ⛔ skipped (no administrator rights)",
        "log.opt_unsupported": "  ⛔ unavailable: Windows protects this registry value",
        "log.opt_failed": "  ⚠ error: {}",
        "log.opt_unknown": "unknown",
        "log.opt_stopped": "[!] Stopped by the user.",
        "log.opt_result": "Optimization finished:\n"
                          "  Done: {}\n"
                          "  Skipped (no admin rights): {}\n"
                          "  Unavailable on this Windows build: {}\n"
                          "  Errors: {}",
        "log.opt_detail": "  • {} — {}",
        "log.diag_marked": "  ✔ audit: items ticked — {}",
        "log.diag_report": "  • system audit: {}/100 — causes: {}",
        "log.restore_ok": "  ✔ system restore point created",
        "log.restore_fail": "  ⚠ failed to create restore point: {}",
        "log.restore_no_admin": "  ⚠ administrator rights required — restore point not created",
        "msg.install_done": "Installation finished.",
        "msg.install_error": "Installation failed.",
        "msg.upgrade_done": "Upgrade finished.",
        "msg.upgrade_error": "Upgrade failed.",
        "msg.no_updates": "No updates found — every app is up to date.",
        "msg.vc_done": "VC++ installation finished.",
        "msg.vc_partial": "Some packages failed to install — see the log.",

        # ------------------------------------------- сообщения ядра (core)
        "core.recycle_stat": "[Recycle Bin] items: {}, size: {}",
        "core.no_folder": "[skip] no such folder: {}",
        "core.root_unsafe": "[skip] unsafe path: {}",
        "core.root_reparse": "[skip] path is a link (junction/symlink): {}",
        "core.root_personal": "[skip] path leads to a personal user folder: {}",
        "core.scanning": "Scanning: {} ({}/{})",
        "core.cleaning": "Cleaning: {} ({}/{})",
        "core.sim_prefix": "  ◦ (simulation) ",
        "core.protected": "  ⛔ protected, skipped: {}",
        "core.busy": "  ⚠ busy/no access: {}",
        "core.sim_recycle": "  ◦ (simulation) emptying the Recycle Bin",
        "core.recycle_ok": "  ✔ Recycle Bin emptied",
        "core.recycle_fail": "  ⚠ could not empty the Recycle Bin",

        # -------------------------------------- сообщения оптимизации (opt)
        "opt.admin_required": "administrator rights required",
        "opt.admin_suffix": " (administrator rights required)",
        "opt.key_protected": "Windows protects this registry value — it cannot be changed",
        "opt.power_list_fail": "could not read the power scheme list",
        "opt.not_windows": "[!] The optimization module only works on Windows.",
        "opt.items_count": "Optimization: {} items",
        "opt.live_title": "Progress",
        "opt.badge_admin": " · admin",
        "opt.applying_step": "Applying {}/{}: {}",
        "opt.item_stopped": "not applied",

        # ------------------------------------ сообщения установщика (installer)
        "inst.timeout": "Timed out ({} s)",
        "inst.latest": "Already the latest version.\n",
        "inst.log_install": "Installing '{}'...",
        "inst.log_upgrade": "Upgrading '{}'...",
        "inst.log_item": "--- {} ({}) ---",
        "inst.status_ok": "OK",
        "inst.status_error": "ERROR",
        "inst.log_upgrade_all": "Upgrading all packages... "
                                "This may take a few minutes.",
        "inst.bad_id": "Invalid package ID: \u201c{}\u201d.\n"
                       "Only Latin letters, digits and . _ + - are allowed.",
        "inst.bad_query": "Invalid search query: \u201c{}\u201d.\n"
                          "The query must not start with a dash and must be at most 128 characters.",
    },
}


def get_language() -> str:
    """Возвращает текущий код языка ('ru' или 'en')."""
    return LANG


def set_language(code: str) -> str:
    """Устанавливает язык. Неизвестный код игнорируется (остаётся прежний)."""
    global LANG
    if code in STRINGS:
        LANG = code
    return LANG


def t(key: str, *args, **kwargs) -> str:
    """
    Возвращает текст по ключу для текущего языка.

    Поддерживает .format(): можно передавать позиционные аргументы
    или именованные. Если ключа нет — возвращается сам ключ (чтобы
    ошибка перевода была видна, но интерфейс не падал).
    """
    text = STRINGS.get(LANG, {}).get(key)
    if text is None:
        text = STRINGS["ru"].get(key, key)
    if args or kwargs:
        try:
            return text.format(*args, **kwargs)
        except (IndexError, KeyError, ValueError):
            # Несовпадение числа аргументов или битые фигурные скобки в шаблоне
            # не должны ронять интерфейс — отдаём строку как есть.
            return text
    return text


def pick(ru_text: str, en_text: str = "") -> str:
    """Выбирает русский или английский вариант готовой строки."""
    if LANG == "en" and en_text:
        return en_text
    return ru_text


def fld(item: dict, field: str) -> str:
    """
    Возвращает поле словаря с учётом языка.

    Для английского сначала ищется поле с суффиксом _en (например
    title_en), и только если его нет — обычное поле.
    """
    if not item:
        return ""
    if LANG == "en":
        value = item.get(field + "_en")
        if value:
            return value
    return item.get(field, "") or ""


def units() -> tuple:
    """Единицы измерения размера для текущего языка."""
    return UNITS.get(LANG, UNITS["ru"])


def language_name(code: str = "") -> str:
    """Название языка для выпадающего списка ('Русский' / 'English')."""
    return LANGUAGE_NAMES.get(code or LANG, code or LANG)


def language_code(name: str) -> str:
    """
    Обратное преобразование: 'English' -> 'en'.

    Возвращает "" если название неизвестно (тогда язык не меняем).
    """
    text = (name or "").strip()
    for code in LANGUAGE_ORDER:
        if LANGUAGE_NAMES[code] == text:
            return code
    # Разрешаем также ввести код напрямую ("en"/"ru") — удобно для тестов.
    lowered = text.lower()
    return lowered if lowered in LANGUAGE_NAMES else ""


def language_values() -> list:
    """Список названий языков в порядке отображения."""
    return [LANGUAGE_NAMES[code] for code in LANGUAGE_ORDER]
