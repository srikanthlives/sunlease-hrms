"""Minimal harness: a throwaway SQLite database per test, built from the models.

HRMS had no tests before this; this sets up only what the depot-export feed
needs, so it stays fast and does not depend on app/seed.py's demo data.
"""
import os
import tempfile

# Must be set before the app is imported.
_tmp = tempfile.mkdtemp()
os.environ["HRMS_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def client(db):
    return TestClient(app)
