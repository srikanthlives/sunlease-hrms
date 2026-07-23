"""
Run once to bootstrap the database with:
 - an admin user (admin / admin123)
 - a payroll processor user (payroll / payroll123)
 - a sample salary template (T-001) with common components
 - a sample employee assigned to that template, with an employee-login user

Usage:  python seed.py
"""
from app.database import Base, engine, SessionLocal
from app import models
from app.security import hash_password

Base.metadata.create_all(bind=engine)
db = SessionLocal()

try:
    if not db.query(models.User).filter_by(username="admin").first():
        db.add(models.User(
            username="admin", email="admin@example.com",
            hashed_password=hash_password("admin123"), role=models.UserRole.ADMIN,
        ))

    if not db.query(models.User).filter_by(username="payroll").first():
        db.add(models.User(
            username="payroll", email="payroll@example.com",
            hashed_password=hash_password("payroll123"), role=models.UserRole.PAYROLL_PROCESSOR,
        ))
    db.commit()

    template = db.query(models.SalaryTemplate).filter_by(template_no="T-001").first()
    if not template:
        template = models.SalaryTemplate(
            template_no="T-001", name="Standard Executive Template",
            description="Default template for executive-grade employees",
        )
        db.add(template)
        db.flush()

        components = [
            # code, name, type, calc_type, value, formula, is_variable, default_value, prorate, sequence
            ("BASIC", "Basic Pay", models.ComponentType.EARNING, models.CalculationType.FIXED, 20000, None, False, 0, True, 1),
            ("DA", "Dearness Allowance", models.ComponentType.EARNING, models.CalculationType.FIXED, 5000, None, False, 0, True, 2),
            # HRA demonstrates a PERCENTAGE component whose base is a full formula, not just a single code.
            ("HRA", "House Rent Allowance", models.ComponentType.EARNING, models.CalculationType.PERCENTAGE, 40, "BASIC + DA", False, 0, True, 3),
            ("CONV", "Conveyance Allowance", models.ComponentType.EARNING, models.CalculationType.FIXED, 1600, None, False, 0, True, 4),
            ("PERF_BONUS", "Performance Bonus", models.ComponentType.EARNING, models.CalculationType.FIXED, 0, None, True, 2000, False, 5),
            # GROSS_SALARY is a REFERENCE component: never paid, never shown on the payslip or CTC -
            # it exists purely so PF/ESIC formulas below can refer to it.
            ("GROSS_SALARY", "Gross Salary (reference only)", models.ComponentType.REFERENCE, models.CalculationType.FORMULA, 0, "BASIC + DA + HRA + CONV + PERF_BONUS", False, 0, False, 6),
            # Employee PF: 12% of (BASIC+DA), capped at a wage ceiling of 15,000.
            ("PF", "Provident Fund (Employee)", models.ComponentType.DEDUCTION, models.CalculationType.FORMULA, 0, "min(BASIC + DA, 15000) * 0.12", False, 0, False, 7),
            # Employee ESIC: 0.75% of gross salary, only if gross salary is within the ESIC wage limit.
            ("ESIC", "ESIC (Employee)", models.ComponentType.DEDUCTION, models.CalculationType.FORMULA, 0, "roundup(GROSS_SALARY * 0.0075, 1) if GROSS_SALARY <= 21000 else 0", False, 0, False, 8),
            ("PROF_TAX", "Professional Tax", models.ComponentType.DEDUCTION, models.CalculationType.FIXED, 200, None, False, 0, False, 9),
            ("UNIFORM_DEDUCTION", "Uniform Deduction", models.ComponentType.DEDUCTION, models.CalculationType.FIXED, 0, None, True, 0, False, 10),
            # Employer-side costs: never shown on the payslip, only in the CTC / cost-summary view.
            ("EMPLOYER_PF", "Provident Fund (Employer)", models.ComponentType.EMPLOYER_CONTRIBUTION, models.CalculationType.FORMULA, 0, "min(BASIC + DA, 15000) * 0.12", False, 0, False, 11),
            ("EMPLOYER_ESIC", "ESIC (Employer)", models.ComponentType.EMPLOYER_CONTRIBUTION, models.CalculationType.FORMULA, 0, "roundup(GROSS_SALARY * 0.0325, 1) if GROSS_SALARY <= 21000 else 0", False, 0, False, 12),
        ]
        for code, name, ctype, calc_type, value, formula, is_var, default_val, prorate, seq in components:
            db.add(models.SalaryComponent(
                template_id=template.id, code=code, name=name, component_type=ctype,
                calculation_type=calc_type, value=value, formula=formula, is_variable=is_var,
                default_value=default_val, prorate_by_attendance=prorate, sequence=seq,
            ))
        db.commit()

    emp = db.query(models.Employee).filter_by(employee_code="EMP001").first()
    if not emp:
        emp = models.Employee(
            employee_code="EMP001", first_name="Asha", last_name="Rao",
            email="asha.rao@example.com", phone="9999999999", department="Engineering",
            designation="Software Engineer", date_of_joining="2023-01-15",
            status=models.EmployeeStatus.ACTIVE, template_id=template.id,
            bank_name="HDFC Bank", bank_account="123456789012", ifsc="HDFC0001234",
            pan="ABCDE1234F", uan="100200300400", esi_number="3412345678000123", mediclaim_policy_no="MED-2026-00981",
        )
        db.add(emp)
        db.flush()

        db.add(models.User(
            username="asha.rao", email="asha.rao@example.com",
            hashed_password=hash_password("employee123"), role=models.UserRole.EMPLOYEE,
            employee_id=emp.id,
        ))
        db.commit()

    # Sample day-by-day attendance for July 2026 (demonstrates the attendance grid & EL accrual).
    if not db.query(models.DailyAttendance).filter_by(employee_id=emp.id).first():
        daily_pattern = {
            1: "P", 2: "P", 3: "P", 4: "2P", 5: "WO",
            6: "WO", 7: "P", 8: "HD", 9: "AB", 10: "EL", 11: "R",
        }
        for day, status in daily_pattern.items():
            db.add(models.DailyAttendance(
                employee_id=emp.id, date=f"2026-07-{day:02d}",
                status=models.AttendanceStatus(status), uploaded_by="seed",
            ))
        db.commit()

    print("Seed complete.")
    print("Login credentials:")
    print("  Admin            -> username: admin      password: admin123")
    print("  Payroll processor-> username: payroll    password: payroll123")
    print("  Employee (Asha)  -> username: asha.rao   password: employee123")
finally:
    db.close()
