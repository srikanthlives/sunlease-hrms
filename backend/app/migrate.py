"""
Lightweight auto-migration for SQLite.

On every startup, after Base.metadata.create_all() has created any brand-new tables,
this checks each *existing* table for columns that exist on the ORM model but are
missing from the actual database file (e.g. after pulling an update that added a new
column to an existing model, like `Payslip.ctc_total`) and adds them with `ALTER TABLE
... ADD COLUMN`.

This is NOT a replacement for a real migration tool (Alembic) in production - it only
handles simple additive changes (new nullable/defaulted columns). It CANNOT loosen an
existing column's constraints (e.g. turning a NOT NULL column into a nullable one) -
SQLite doesn't support that without rebuilding the table. If you hit that situation
(as happened when `Employee.email` was changed from required to optional), the
simplest fix for a dev database is to delete the `.db` file and re-run `seed.py`.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from .database import Base
from . import models  # noqa: F401  (ensures all model classes are registered on Base.metadata)


def run_light_migrations(engine: Engine) -> list[str]:
    applied = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand-new table - create_all() already handled it

            existing_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_cols:
                    continue

                col_type = column.type.compile(dialect=engine.dialect)
                default_clause = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    arg = column.default.arg
                    default_clause = f" DEFAULT '{arg}'" if isinstance(arg, str) else f" DEFAULT {arg}"

                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_clause}'
                conn.execute(text(ddl))
                applied.append(f"{table.name}.{column.name}")

    return applied
