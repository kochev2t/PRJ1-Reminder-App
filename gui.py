"""Главное окно приложения, список напоминаний и периодическая проверка времени."""

import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime, timedelta
from typing import Optional

from config import (
    APP_NAME,
    FILTER_ALL,
    INPUT_DATETIME_FORMATS,
    OVERDUE_GRACE_SECONDS,
    POLL_INTERVAL_MS,
    STATUSES,
    STATUS_CANCELLED,
    STATUS_DONE,
)
from database import Database
from notifier import Notifier


def parse_input_datetime(raw: str) -> datetime:
    """Распарсить дату, введённую пользователем в форме."""
    text = raw.strip()
    for fmt in INPUT_DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(
        "Ожидается формат ГГГГ-ММ-ДД ЧЧ:ММ, например 2026-11-22 09:30"
    )


class ReminderApp:
    """Главное окно со списком напоминаний и фоновой проверкой времени."""

    def __init__(self, root: tk.Tk, db: Optional[Database] = None) -> None:
        self.root = root
        self.db = db or Database()
        self.notifier = Notifier(root)

        self.filter_var = tk.StringVar(value=FILTER_ALL)
        self.toast_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="")

        # Поля встроенной формы добавления в шапке.
        self.new_title_var = tk.StringVar()
        self.new_desc_var = tk.StringVar()
        self.new_due_var = tk.StringVar(value=self._default_due_text())

        self._after_id: Optional[str] = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh()
        self.check_reminders()

    # ------------------------------------------------------------------
    # Интерфейс
    # ------------------------------------------------------------------
    @staticmethod
    def _default_due_text() -> str:
        return (datetime.now() + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")

    def _build_ui(self) -> None:
        self.root.title(APP_NAME)
        self.root.geometry("1020x680")
        self.root.minsize(820, 560)

        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        # Шапка: встроенная форма добавления напоминания.
        add_box = ttk.LabelFrame(
            main, text="Добавить новое напоминание", padding=(10, 8)
        )
        add_box.pack(fill="x", pady=(0, 8))
        add_box.columnconfigure(0, weight=3)
        add_box.columnconfigure(1, weight=4)
        add_box.columnconfigure(2, weight=2)
        add_box.columnconfigure(3, weight=0)

        ttk.Label(add_box, text="Заголовок").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        ttk.Label(add_box, text="Описание").grid(
            row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(add_box, text="Дата и время").grid(
            row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 4)
        )

        self.new_title_entry = ttk.Entry(
            add_box, textvariable=self.new_title_var, width=26
        )
        self.new_title_entry.grid(row=1, column=0, sticky="ew")

        self.new_desc_entry = ttk.Entry(
            add_box, textvariable=self.new_desc_var, width=36
        )
        self.new_desc_entry.grid(row=1, column=1, sticky="ew", padx=(8, 0))

        self.new_due_entry = ttk.Entry(
            add_box, textvariable=self.new_due_var, width=20
        )
        self.new_due_entry.grid(row=1, column=2, sticky="ew", padx=(8, 0))

        ttk.Button(add_box, text="Добавить", command=self.add_reminder).grid(
            row=1, column=3, sticky="ew", padx=(10, 0)
        )

        for entry in (self.new_title_entry, self.new_desc_entry, self.new_due_entry):
            entry.bind("<Return>", lambda event: self.add_reminder())

        quick = ttk.Frame(add_box)
        quick.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        ttk.Label(quick, text="Быстрый выбор времени:").pack(side="left")
        for text, minutes in (
            ("Через 1 мин", 1),
            ("Через 5 мин", 5),
            ("Через 15 мин", 15),
            ("Через 1 час", 60),
        ):
            ttk.Button(
                quick,
                text=text,
                command=lambda m=minutes: self.set_due_in(m),
            ).pack(side="left", padx=(6, 0))

        toolbar = ttk.Frame(main)
        toolbar.pack(fill="x", pady=(0, 8))

        self.btn_delete = ttk.Button(toolbar, text="Удалить", command=self.delete_reminder)
        self.btn_delete.pack(side="left", padx=(6, 0))
        self.btn_done = ttk.Button(
            toolbar, text="Готово", command=lambda: self.set_status(STATUS_DONE)
        )
        self.btn_done.pack(side="left", padx=(6, 0))
        self.btn_cancel = ttk.Button(
            toolbar, text="Отменено", command=lambda: self.set_status(STATUS_CANCELLED)
        )
        self.btn_cancel.pack(side="left", padx=(6, 0))

        ttk.Separator(toolbar, orient="vertical").pack(
            side="left", fill="y", padx=10
        )

        ttk.Label(toolbar, text="Фильтр:").pack(side="left")
        combo = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=(FILTER_ALL, *STATUSES),
            state="readonly",
            width=12,
        )
        combo.pack(side="left", padx=(5, 6))
        combo.bind("<<ComboboxSelected>>", lambda event: self.refresh())

        ttk.Button(toolbar, text="Обновить", command=self.refresh).pack(side="left")

        ttk.Checkbutton(
            toolbar,
            text="Системное уведомление (win10toast)",
            variable=self.toast_var,
            command=self._toggle_toast,
        ).pack(side="right")

        tree_frame = ttk.Frame(main)
        tree_frame.pack(fill="both", expand=True)

        columns = ("id", "title", "description", "due", "status")
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse"
        )
        headings = {
            "id": "№",
            "title": "Заголовок",
            "description": "Описание",
            "due": "Время срабатывания",
            "status": "Статус",
        }
        widths = {"id": 50, "title": 230, "description": 340, "due": 175, "status": 110}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(
                col,
                width=widths[col],
                anchor="center" if col in ("id", "due", "status") else "w",
                stretch=(col in ("title", "description")),
            )

        # Текст остаётся чёрным, цветом выделяется фон всей строки.
        status_backgrounds = {
            "Ожидает": "#d9e8ff",
            "Готово": "#d8f3dc",
            "Просрочено": "#ffd9d9",
            "Отменено": "#e8e8e8",
        }
        for status, background in status_backgrounds.items():
            self.tree.tag_configure(
                status, background=background, foreground="#000000"
            )

        scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda event: self._update_actions())

        ttk.Label(main, textvariable=self.status_var, anchor="w").pack(
            fill="x", pady=(8, 0)
        )
        self._update_actions()

    def _toggle_toast(self) -> None:
        available = self.notifier.set_use_toast(self.toast_var.get())
        if self.toast_var.get() and not available:
            messagebox.showwarning(
                APP_NAME,
                "Пакет win10toast не найден. Уведомления будут показываться "
                "всплывающим окном поверх всех окон.",
                parent=self.root,
            )

    def _selected_id(self) -> Optional[int]:
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def _update_actions(self) -> None:
        state = "normal" if self.tree.selection() else "disabled"
        self.btn_delete.configure(state=state)
        self.btn_done.configure(state=state)
        self.btn_cancel.configure(state=state)

    def refresh(self) -> None:
        status = self.filter_var.get()
        rows = self.db.get_all(None if status == FILTER_ALL else status)

        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in rows:
            description = row["description"] or ""
            if len(description) > 70:
                description = description[:67] + "..."
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["id"],
                    row["title"],
                    description,
                    row["due_at"],
                    row["status"],
                ),
                tags=(row["status"],),
            )

        counts = self.db.counts()
        parts = [
            f"Показано: {len(rows)}",
            f"Всего: {sum(counts.values())}",
            *[f"{name}: {counts.get(name, 0)}" for name in STATUSES],
        ]
        self.status_var.set("  |  ".join(parts))
        self._update_actions()

    # ------------------------------------------------------------------
    # Действия пользователя
    # ------------------------------------------------------------------
    def set_due_in(self, minutes: int) -> None:
        """Подставить в поле даты время через заданное число минут."""
        self.new_due_var.set(
            (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")
        )

    def add_reminder(self) -> None:
        title = self.new_title_var.get().strip()
        if not title:
            messagebox.showerror(
                APP_NAME, "Введите заголовок напоминания.", parent=self.root
            )
            self.new_title_entry.focus_set()
            return

        try:
            due_at = parse_input_datetime(self.new_due_var.get())
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=self.root)
            self.new_due_entry.focus_set()
            return

        description = self.new_desc_var.get().strip()
        self.db.add_reminder(title, description, due_at)

        self.new_title_var.set("")
        self.new_desc_var.set("")
        self.new_due_var.set(self._default_due_text())
        self.refresh()
        self.new_title_entry.focus_set()

    def delete_reminder(self) -> None:
        reminder_id = self._selected_id()
        if reminder_id is None:
            return
        if messagebox.askyesno(
            APP_NAME, "Удалить выбранное напоминание?", parent=self.root
        ):
            self.db.delete_reminder(reminder_id)
            self.refresh()

    def set_status(self, status: str) -> None:
        reminder_id = self._selected_id()
        if reminder_id is None:
            return
        self.db.set_status(reminder_id, status)
        self.refresh()

    def _popup_action(self, reminder_id: int, status: str) -> None:
        self.db.set_status(reminder_id, status)
        self.refresh()

    # ------------------------------------------------------------------
    # Фоновая проверка (работает также при свёрнутом окне)
    # ------------------------------------------------------------------
    def check_reminders(self) -> None:
        try:
            now = datetime.now()

            # Просроченные — те, что уже сработали, но не отмечены пользователем.
            self.db.mark_overdue(now, OVERDUE_GRACE_SECONDS)

            due_rows = self.db.get_due_pending(now)
            for row in due_rows:
                if not self.db.mark_notified(row["id"], now):
                    continue
                self.notifier.notify(
                    row,
                    on_done=lambda rid=row["id"]: self._popup_action(rid, STATUS_DONE),
                    on_cancel=lambda rid=row["id"]: self._popup_action(
                        rid, STATUS_CANCELLED
                    ),
                )
            if due_rows:
                self.refresh()
        finally:
            self._after_id = self.root.after(
                POLL_INTERVAL_MS, self.check_reminders
            )

    def on_close(self) -> None:
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
        self.root.destroy()
