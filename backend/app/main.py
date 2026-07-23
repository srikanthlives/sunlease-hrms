from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .migrate import run_light_migrations
from .routers import (
    auth, users, employees, templates, attendance, variable_uploads, adhoc, payroll,
    payments, bank_payments, compliance,
)

Base.metadata.create_all(bind=engine)
_migrated = run_light_migrations(engine)
if _migrated:
    print(f"[startup] Auto-migration added missing columns: {', '.join(_migrated)}")

app = FastAPI(title="Salary & Payroll API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The bank-payments download response reports counts/warnings via custom headers - browsers
    # hide non-standard response headers from JS unless explicitly exposed here.
    expose_headers=["Content-Disposition", "X-CC-Count", "X-ST-Count", "X-Warning-Count", "X-Warnings", "X-Skipped-No-ESI-Number"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(employees.router)
app.include_router(templates.router)
app.include_router(attendance.router)
app.include_router(variable_uploads.router)
app.include_router(adhoc.router)
app.include_router(payroll.router)
app.include_router(payments.router)
app.include_router(bank_payments.router)
app.include_router(compliance.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "Salary & Payroll API"}
