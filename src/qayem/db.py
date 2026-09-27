"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import DEFAULT_DB_PATH, db_path
from .models import Base


def get_engine(path: str | Path | None = None) -> Engine:
    path = Path(path) if path else db_path()
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        # long busy-timeout: concurrent runs (e.g. an ad-hoc parse while a
        # batch run holds the write lock) queue instead of crashing
        connect_args={"check_same_thread": False, "timeout": 1800},
    )

    @event.listens_for(engine, "connect")
    def _wal(connection, _record) -> None:
        # WAL: the read-only website never waits on a crawl's writes
        connection.execute("PRAGMA journal_mode=WAL")

    return engine


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine: Engine) -> None:
    """create_all never alters existing tables; add nullable columns introduced later."""
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in present and column.nullable:
                    kind = column.type.compile(dialect=engine.dialect)
                    connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}'))


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = sessionmaker(bind=engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["get_engine", "init_db", "session_scope", "DEFAULT_DB_PATH"]
