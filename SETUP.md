**Backend**

> bash
> cd backend
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> python seed.py          # creates DB + admin/payroll/employee demo logins
> uvicorn app.main:app --reload --port 8000

**Frontend**
> bash
> cd frontend
> npm install
> npm run dev
> Then visit http://localhost:5173 and log in with admin / admin123 (or payroll/payroll123, or asha.rao/employee123 for the employee view).
>A  few things worth knowing about how it works:

Templates (/templates, admin-only) — build a template by adding components as Fixed, % of another component, or a Formula (e.g. BASIC + HRA + CONV). Mark a component Variable if it needs a monthly manual value, like your Performance Bonus example — it stores a default_value (2000) that gets overridden per employee/month when someone uploads 1500.
Monthly Variable Upload (/variable-upload) — this is exactly your override flow: Excel columns employee_code | component_code | value | remarks, and it only accepts values for components already flagged Variable on that employee's template.
Ad-hoc Entries (/adhoc) — one-off deductions like the uniform charge on resignation, added directly to a specific month without touching the template.
Run Payroll resolves all formulas (multi-pass, so component order doesn't matter), applies attendance proration, layers in overrides and ad-hoc entries, then stores the payslip.
Role checks are enforced server-side in app/deps.py, not just hidden in the UI.

I couldn't npm install/pip install in this sandbox (no network access here), so I verified the payroll math logic standalone and checked all Python files compile cleanly — but I'd recommend a quick smoke-test on your machine after install. Sample Excel files for both upload types are in sample_data/, and the README covers formula syntax, Excel formats, and things to harden before production (secret key, CORS, etc).