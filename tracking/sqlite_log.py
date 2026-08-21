"""Адаптер журнала кликов на SQLite.

SQLite, а не PostgreSQL, на этой фазе сознательно: критерий перехода в
фазу 2 — «~100 расчётов и заметный CTR». Сотня строк в append-only журнале
не нуждается ни в сервере, ни в docker compose, ни в миграциях. Замена на
PostgreSQL — это новый класс, реализующий тот же ClickLog, и одна строка
в сборке приложения.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from tracking.click import Click

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clicks (
    click_id      TEXT PRIMARY KEY,
    offer_id      TEXT NOT NULL,
    source        TEXT NOT NULL,
    scenario_hash TEXT NOT NULL,
    position      INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clicks_offer ON clicks(offer_id);
CREATE INDEX IF NOT EXISTS idx_clicks_created ON clicks(created_at);
"""


class SqliteClickLog:
    """Журнал кликов в файле SQLite. Только вставка и подсчёт."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, isolation_level=None)

    def record(self, click: Click) -> None:
        """Вставляет клик. Повторный click_id — ошибка, а не тихий пропуск."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO clicks "
                "(click_id, offer_id, source, scenario_hash, position, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    click.click_id,
                    click.offer_id,
                    click.source,
                    click.scenario_hash,
                    click.position,
                    click.created_at.isoformat(),
                ),
            )

    def count(self) -> int:
        """Общее число записанных кликов."""
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM clicks").fetchone()
        return int(row[0])

    def count_since(self, moment: datetime) -> int:
        """Клики начиная с момента. Для недельного среза CTR."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM clicks WHERE created_at >= ?",
                (moment.isoformat(),),
            ).fetchone()
        return int(row[0])
