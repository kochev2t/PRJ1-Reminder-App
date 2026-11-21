"""Общие константы и утилиты приложения-напоминалки."""

from datetime import datetime
from pathlib import Path

APP_NAME = "Напоминалка Windows 11"

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "reminders.db"

STATUS_PENDING = "Ожидает"
STATUS_DONE = "Готово"
STATUS_OVERDUE = "Просрочено"
STATUS_CANCELLED = "Отменено"

STATUSES = (STATUS_PENDING, STATUS_DONE, STATUS_OVERDUE, STATUS_CANCELLED)
FILTER_ALL = "Все"

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
INPUT_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
)

# Как часто проверять базу на предмет сработавших/просроченных напоминаний.
POLL_INTERVAL_MS = 1000

# Сколько секунд после срабатывания напоминание остаётся «Ожидает»,
# прежде чем автоматически стать «Просрочено».
OVERDUE_GRACE_SECONDS = 60

POPUP_WIDTH = 400
POPUP_HEIGHT = 190


def format_datetime(value: datetime) -> str:
    """Привести datetime к строке, в которой дата хранится в БД."""
    return value.strftime(DATETIME_FORMAT)


def parse_datetime(value: str | datetime) -> datetime:
    """Прочитать дату из БД (или вернуть переданный datetime как есть)."""
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in (DATETIME_FORMAT, *INPUT_DATETIME_FORMATS):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Неверный формат даты и времени: {value!r}")
