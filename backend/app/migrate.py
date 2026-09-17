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
from sqlalchemy.schema import CreateTable

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


def _drop_departments_cost_center_id(target_engine: Engine, inspector, verbose: bool) -> bool:
    """One-off fixup: Department used to require a Cost Center
    (cost_center_id NOT NULL). It's now a flat, reusable label with no
    parent, but SQLite can't ALTER a column's nullability/drop it
    in-place, so a plain additive column-add wouldn't remove the stale
    NOT NULL constraint and every new Department insert would fail.
    Rebuilds the table (SQLite's standard column-drop workaround),
    preserving every existing row's id/name/code/is_active/created_at -
    zero data loss. Idempotent: only runs while the old column is still
    there."""
    if "departments" not in inspector.get_table_names():
        return False
    live_columns = {c["name"] for c in inspector.get_columns("departments")}
    if "cost_center_id" not in live_columns:
        return False

    with target_engine.begin() as conn:
        conn.execute(text(
            'CREATE TABLE "departments_new" ('
            '"id" INTEGER NOT NULL PRIMARY KEY, "name" VARCHAR(255) NOT NULL, '
            '"code" VARCHAR(50) NOT NULL UNIQUE, "is_active" BOOLEAN, "created_at" DATETIME)'
        ))
        conn.execute(text(
            'INSERT INTO "departments_new" (id, name, code, is_active, created_at) '
            'SELECT id, name, code, is_active, created_at FROM "departments"'
        ))
        conn.execute(text('DROP TABLE "departments"'))
        conn.execute(text('ALTER TABLE "departments_new" RENAME TO "departments"'))

    if verbose:
        print("Rebuilt departments table to drop the retired cost_center_id column (no data lost).")
    return True


def _tighten_candidates_employee_category_not_null(target_engine: Engine, inspector, verbose: bool) -> bool:
    """One-off fixup: applied_employee_category_id on Candidate is now
    mandatory (was optional). SQLite can't ALTER a column to add a NOT
    NULL constraint in place, so this rebuilds the candidates table with
    the model's current (correct) column definitions - via SQLAlchemy's
    own CreateTable DDL, so it always matches models.py exactly rather
    than a hand-duplicated CREATE TABLE that could drift out of sync -
    copying every existing row unchanged. Idempotent: only runs while the
    live column is still nullable. Safe because no existing candidate row
    has a null Employee Category (unlike Project, which does have one
    legacy row and so deliberately stays nullable at the DB level - see
    the comment on Candidate.applied_project_id in models.py)."""
    if "candidates" not in inspector.get_table_names():
        return False
    live_columns = {c["name"]: c for c in inspector.get_columns("candidates")}
    if "applied_employee_category_id" not in live_columns or not live_columns["applied_employee_category_id"]["nullable"]:
        return False

    table = Base.metadata.tables["candidates"]
    create_sql = str(CreateTable(table).compile(target_engine)).replace("CREATE TABLE candidates ", "CREATE TABLE candidates_new ", 1)
    column_names = ", ".join(f'"{c.name}"' for c in table.columns)

    with target_engine.begin() as conn:
        conn.execute(text(create_sql))
        conn.execute(text(f'INSERT INTO "candidates_new" ({column_names}) SELECT {column_names} FROM "candidates"'))
        conn.execute(text('DROP TABLE "candidates"'))
        conn.execute(text('ALTER TABLE "candidates_new" RENAME TO "candidates"'))

    if verbose:
        print("Rebuilt candidates table to make applied_employee_category_id required (no data lost).")
    return True


def migrate(target_engine: Engine = None, verbose: bool = True) -> dict:
    target_engine = target_engine or engine
    summary = {"tables_created": [], "columns_added": []}

    inspector = inspect(target_engine)
    _drop_departments_cost_center_id(target_engine, inspector, verbose)
    inspector = inspect(target_engine)
    _tighten_candidates_employee_category_not_null(target_engine, inspector, verbose)
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
