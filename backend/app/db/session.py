from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def atomic_session():
    """A session whose whole lifetime is ONE real database transaction, for
    all-or-nothing work (the Excel bulk uploads). Committed only if the block
    finishes without an exception; a rollback undoes everything, including
    rows an inner per-row savepoint had already "released".

    Why not the normal session: SQLite's Python driver (pysqlite) doesn't
    open a transaction before a SAVEPOINT, so the outermost savepoint
    behaves like its own transaction and releasing it COMMITs - per-row
    savepoints would save good rows even when the file is later rejected.
    Here we take over BEGIN/COMMIT on a dedicated connection instead."""
    connection = engine.connect()
    dbapi = connection.connection.dbapi_connection
    previous_isolation = dbapi.isolation_level if engine.dialect.name == "sqlite" else None
    if engine.dialect.name == "sqlite":
        dbapi.isolation_level = None  # we issue BEGIN ourselves
        connection.exec_driver_sql("BEGIN")
    session = Session(bind=connection, join_transaction_mode="create_savepoint", autocommit=False, autoflush=False)
    try:
        yield session
        session.commit()
        connection.commit()
    except Exception:
        session.close()
        connection.rollback()
        raise
    finally:
        session.close()
        if engine.dialect.name == "sqlite":
            dbapi.isolation_level = previous_isolation
        connection.close()
