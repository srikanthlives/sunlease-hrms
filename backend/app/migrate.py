"""Lightweight auto-migration for SQLite, mirroring sunlease-expms's
approach (no Alembic). Run any time app/models/models.py changes:

    python -m app.migrate

What it does automatically (safe, additive-only operations):
  - Creates any table that exists on a model but not yet in the database.
  - Adds any column that exists on a model but not yet on the live table.

What it deliberately does NOT do: drop/rename a column, change a column's
type/nullability, or add/remove constraints on an existing table. Handle
those by hand, or reset the dev database:

    rm -f ../data/hrms.db && python -m app.seed

Also called automatically on every app startup (see app/main.py).
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.db.session import Base, engine
import app.models  # noqa: F401  (ensures every model is registered on Base.metadata)


def _add_column_ddl(table_name: str, column) -> str:
    col_type = str(column.type)
    parts = [f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}']

    if column.default is not None and getattr(column.default, "is_scalar", False):
        parts.append(f"DEFAULT {column.default.arg!r}")
        if not column.nullable:
            parts.append("NOT NULL")
    elif not column.nullable:
        pass  # would need a default to be NOT NULL on SQLite; leave nullable

    return " ".join(parts)


def migrate(target_engine: Engine = None, verbose: bool = True) -> dict:
    target_engine = target_engine or engine
    summary = {"tables_created": [], "columns_added": []}

    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    all_tables = list(Base.metadata.tables.values())

    tables_to_create = [t for t in all_tables if t.name not in existing_tables]
    if tables_to_create:
        Base.metadata.create_all(bind=target_engine, tables=tables_to_create)
        summary["tables_created"] = [t.name for t in tables_to_create]
        inspector = inspect(target_engine)
        existing_tables = set(inspector.get_table_names())

    with target_engine.begin() as conn:
        for table in all_tables:
            if table.name not in existing_tables or table.name in summary["tables_created"]:
                continue
            live_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in live_columns:
                    continue
                conn.execute(text(_add_column_ddl(table.name, column)))
                summary["columns_added"].append((table.name, column.name))

    if verbose:
        if not summary["tables_created"] and not summary["columns_added"]:
            print("Database schema already matches the models - nothing to do.")
        else:
            if summary["tables_created"]:
                print(f"Created {len(summary['tables_created'])} new table(s):")
                for t in summary["tables_created"]:
                    print(f"  + {t}")
            if summary["columns_added"]:
                print(f"Added {len(summary['columns_added'])} new column(s):")
                for table_name, col_name in summary["columns_added"]:
                    print(f"  + {table_name}.{col_name}")
        print(
            "\nNote: this only ADDS tables/columns, never drops or renames. "
            "If a model removed a field or changed a type, handle that by "
            "hand or reset the dev DB with "
            "'rm -f ../data/hrms.db && python -m app.seed'."
        )

    return summary


if __name__ == "__main__":
    migrate()
