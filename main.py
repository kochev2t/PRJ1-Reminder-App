"""Точка входа приложения-напоминалки."""

import tkinter as tk

from config import APP_NAME
from database import Database
from gui import ReminderApp


def main() -> None:
    # Схема БД проверяется/создаётся в конструкторе Database.
    db = Database()
    root = tk.Tk()
    root.title(APP_NAME)
    ReminderApp(root, db)
    root.mainloop()


if __name__ == "__main__":
    main()
