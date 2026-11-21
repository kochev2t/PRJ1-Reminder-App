"""Уведомления: системный toast Windows и всплывающее окно поверх всех."""

import tkinter as tk
from tkinter import ttk
from typing import Callable

from config import (
    APP_NAME,
    DATETIME_FORMAT,
    POPUP_HEIGHT,
    POPUP_WIDTH,
    parse_datetime,
)


class Notifier:
    """Показывает уведомление о сработавшем напоминании.

    По умолчанию используется собственный popup на tkinter с флагом
    «поверх всех окон» — он не зависит от внешних пакетов и работает,
    даже если главное окно свёрнуто.

    Если включить ``use_toast`` и установить ``win10toast``, будет
    показано системное уведомление Windows. При любой ошибке toast
    автоматически используется popup.
    """

    def __init__(self, root: tk.Tk, use_toast: bool = False) -> None:
        self.root = root
        self.use_toast = use_toast
        self._toaster = None
        self._popup_index = 0
        if use_toast:
            self._toaster = self._create_toaster()

    @staticmethod
    def _create_toaster():
        try:
            from win10toast import ToastNotifier

            return ToastNotifier()
        except Exception:
            return None

    @property
    def toast_available(self) -> bool:
        return self._toaster is not None

    def set_use_toast(self, enabled: bool) -> bool:
        """Включить/выключить системные toast-уведомления."""
        self.use_toast = enabled
        if enabled and self._toaster is None:
            self._toaster = self._create_toaster()
        return self.toast_available

    def notify(
        self,
        reminder: dict,
        on_done: Callable[[int], None],
        on_cancel: Callable[[int], None],
    ) -> None:
        title = reminder["title"]
        description = reminder.get("description") or ""

        if self.use_toast and self._toaster is not None:
            try:
                self._toaster.show_toast(
                    f"{APP_NAME}: {title}",
                    description or "Напоминание сработало.",
                    duration=10,
                    threaded=True,
                )
                return
            except Exception:
                # Неполадки с toast не должны ломать приложение.
                pass

        self._show_popup(reminder, on_done, on_cancel)

    # ------------------------------------------------------------------
    # Всплывающее окно поверх всех окон
    # ------------------------------------------------------------------
    def _show_popup(
        self,
        reminder: dict,
        on_done: Callable[[int], None],
        on_cancel: Callable[[int], None],
    ) -> None:
        bg = "#fff8e1"
        popup = tk.Toplevel(self.root)
        popup.title("Напоминание")
        popup.resizable(False, False)
        popup.configure(bg=bg, highlightthickness=1, highlightbackground="#e0a800")
        popup.attributes("-topmost", True)

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, screen_w - POPUP_WIDTH - 24)
        stack_shift = (self._popup_index % 5) * 22
        y = max(0, screen_h - POPUP_HEIGHT - 64 - stack_shift)
        self._popup_index += 1
        popup.geometry(f"{POPUP_WIDTH}x{POPUP_HEIGHT}+{x}+{y}")

        header = tk.Label(
            popup,
            text="Напоминание",
            font=("Segoe UI", 12, "bold"),
            fg="#8a5a00",
            bg=bg,
            anchor="w",
        )
        header.pack(fill="x", padx=16, pady=(14, 4))

        title_label = tk.Label(
            popup,
            text=reminder["title"],
            font=("Segoe UI", 11, "bold"),
            wraplength=POPUP_WIDTH - 32,
            justify="left",
            anchor="w",
            bg=bg,
        )
        title_label.pack(fill="x", padx=16, pady=(0, 4))

        description = reminder.get("description") or ""
        desc_label = tk.Label(
            popup,
            text=description or "Описание не указано.",
            font=("Segoe UI", 10),
            wraplength=POPUP_WIDTH - 32,
            justify="left",
            anchor="w",
            bg=bg,
            fg="#333333" if description else "#888888",
        )
        desc_label.pack(fill="x", padx=16, pady=(0, 4))

        due_text = parse_datetime(reminder["due_at"]).strftime(DATETIME_FORMAT)
        meta = tk.Label(
            popup,
            text=f"Время: {due_text}",
            font=("Segoe UI", 9),
            fg="#666666",
            bg=bg,
            anchor="w",
        )
        meta.pack(fill="x", padx=16, pady=(0, 8))

        buttons = ttk.Frame(popup)
        buttons.pack(fill="x", padx=16, pady=(0, 14))

        def finish(action: Callable[[int], None]) -> None:
            try:
                action(reminder["id"])
            finally:
                popup.destroy()

        ttk.Button(
            buttons, text="Готово", command=lambda cb=on_done: finish(cb)
        ).pack(side="left")
        ttk.Button(
            buttons, text="Отменено", command=lambda cb=on_cancel: finish(cb)
        ).pack(side="left", padx=6)
        ttk.Button(buttons, text="Закрыть", command=popup.destroy).pack(side="right")

        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        popup.after(100, popup.lift)
