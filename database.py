"""Слой работы с SQLite3: создание схемы и все операции с напоминаниями."""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import (
    DATETIME_FORMAT,
    DB_PATH,
    STATUSES,
    STATUS_OVERDUE,
    STATUS_PENDING,
)


class Database:
    """Небольшой репозиторий напоминаний.

    Соединение открывается на каждую операцию и закрывается в конце,
    поэтому класс безопасен для использования из одного потока GUI.
    """

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = str(db_path)
        self.init_db()

    # ------------------------------------------------------------------
    # Соединение и схема
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        """Проверить наличие таблиц и создать их при первом запуске."""
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reminders (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        title       TEXT NOT NULL,
                        description TEXT NOT NULL DEFAULT '',
                        due_at      TEXT NOT NULL,
                        status      TEXT NOT NULL DEFAULT 'Ожидает'
                            CHECK (status IN ('Ожидает', 'Готово',
                                              'Просрочено', 'Отменено')),
                        notified_at TEXT,
                        created_at  TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_reminders_status "
                    "ON reminders(status)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_reminders_due "
                    "ON reminders(due_at)"
                )
        finally:
            conn.close()

    def _run(
        self,
        sql: str,
        params: tuple = (),
        *,
        fetch: bool = False,
        one: bool = False,
        commit: bool = False,
    ):
        conn = self._connect()
        try:
            cur = conn.execute(sql, params)
            if commit:
                conn.commit()
            if one:
                row = cur.fetchone()
                return dict(row) if row is not None else None
            if fetch:
                return [dict(row) for row in cur.fetchall()]
            return cur.rowcount
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def add_reminder(self, title: str, description: str, due_at: datetime) -> int:
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    """
                    INSERT INTO reminders
                        (title, description, due_at, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        title.strip(),
                        (description or "").strip(),
                        due_at.strftime(DATETIME_FORMAT),
                        STATUS_PENDING,
                        datetime.now().strftime(DATETIME_FORMAT),
                    ),
                )
                return int(cur.lastrowid)
        finally:
            conn.close()

    def delete_reminder(self, reminder_id: int) -> bool:
        changed = self._run(
            "DELETE FROM reminders WHERE id = ?", (reminder_id,), commit=True
        )
        return changed > 0

    def set_status(self, reminder_id: int, status: str) -> bool:
        if status not in STATUSES:
            raise ValueError(f"Неизвестный статус: {status!r}")
        changed = self._run(
            "UPDATE reminders SET status = ? WHERE id = ?",
            (status, reminder_id),
            commit=True,
        )
        return changed > 0

    def get_by_id(self, reminder_id: int) -> Optional[dict]:
        return self._run(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,), one=True
        )

    def get_all(self, status: Optional[str] = None) -> list[dict]:
        """Вернуть напоминания, при необходимости отфильтрованные по статусу."""
        sql = "SELECT * FROM reminders"
        params: tuple = ()
        if status is not None:
            if status not in STATUSES:
                raise ValueError(f"Неизвестный статус: {status!r}")
            sql += " WHERE status = ?"
            params = (status,)

        # Сначала актуальные, затем просроченные, потом завершённые.
        sql += """
            ORDER BY
                CASE status
                    WHEN 'Ожидает' THEN 0
                    WHEN 'Просрочено' THEN 1
                    WHEN 'Готово' THEN 2
                    ELSE 3
                END,
                due_at ASC
        """
        return self._run(sql, params, fetch=True)

    def counts(self) -> dict[str, int]:
        rows = self._run(
            "SELECT status, COUNT(*) AS amount FROM reminders GROUP BY status",
            fetch=True,
        )
        return {row["status"]: row["amount"] for row in rows}

    # ------------------------------------------------------------------
    # Логика срабатывания и просрочки
    # ------------------------------------------------------------------
    def get_due_pending(self, now: datetime) -> list[dict]:
        """Напоминания, время которых пришло и по которым ещё не был toast/popup."""
        return self._run(
            """
            SELECT * FROM reminders
            WHERE status = ?
              AND notified_at IS NULL
              AND due_at <= ?
            ORDER BY due_at ASC
            """,
            (STATUS_PENDING, now.strftime(DATETIME_FORMAT)),
            fetch=True,
        )

    def mark_notified(self, reminder_id: int, when: datetime) -> bool:
        changed = self._run(
            """
            UPDATE reminders
            SET notified_at = ?
            WHERE id = ? AND status = ? AND notified_at IS NULL
            """,
            (when.strftime(DATETIME_FORMAT), reminder_id, STATUS_PENDING),
            commit=True,
        )
        return changed > 0

    def mark_overdue(self, now: datetime, grace_seconds: int = 0) -> int:
        """Перевести в «Просрочено» сработавшие, но не отмеченные напоминания."""
        threshold = (now - timedelta(seconds=grace_seconds)).strftime(
            DATETIME_FORMAT
        )
        return self._run(
            """
            UPDATE reminders
            SET status = ?
            WHERE status = ?
              AND notified_at IS NOT NULL
              AND due_at < ?
            """,
            (STATUS_OVERDUE, STATUS_PENDING, threshold),
            commit=True,
        )
