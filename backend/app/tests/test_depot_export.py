import datetime as dt

from app.core.security import hash_service_token, new_service_token
from app.models.models import (
    Company, CostCenter, Designation, EmployeeCategory, Employee, EmploymentEpisode, Project,
    ServiceToken, WorkLocation,
)
from app.routers.integrations import DEPOT_SCOPE
from app.services import depot_export_service as svc

URL = "/api/v1/integrations/employees"
LEGACY_URL = "/api/v1/integrations/depot-employees"


def mint(db, scopes=DEPOT_SCOPE, revoked=False, expires_at=None):
    token = new_service_token()
    db.add(ServiceToken(name="depot-sync", token_hash=hash_service_token(token), scopes=scopes,
                        expires_at=expires_at,
                        revoked_at=dt.datetime.utcnow() if revoked else None))
    db.commit()
    return {"Authorization": f"Bearer {token}"}


def world(db):
    """One depot, the two masters the rule names, and a decoy of each."""
    db.add(Company(name="Sunlease"))
    db.commit()
    db.add(CostCenter(company_id=db.query(Company).first().id, name="Depot CC", code="CC1"))
    db.commit()
    db.add(Project(cost_center_id=db.query(CostCenter).first().id, name="Bus Ops", code="P1"))
    db.commit()
    proj = db.query(Project).first()
    db.add_all([WorkLocation(project_id=proj.id, name="Depot One", code="DEP01"),
                EmployeeCategory(name="Operations Staff"), EmployeeCategory(name="Staff"),
                Designation(name="Coach Captain"), Designation(name="HR Executive")])
    db.commit()
    return {"depot": db.query(WorkLocation).first()}


def add(db, number, first, last, category, designation, joining, status="ACTIVE",
        separation=None, depot_code="DEP01"):
    db.add(Employee(first_name=first, last_name=last))
    db.commit()
    emp = db.query(Employee).order_by(Employee.id.desc()).first()
    cat = db.query(EmployeeCategory).filter(EmployeeCategory.name == category).first()
    des = db.query(Designation).filter(Designation.name == designation).first()
    loc = db.query(WorkLocation).filter(WorkLocation.code == depot_code).first() if depot_code else None
    db.add(EmploymentEpisode(
        employee_id=emp.id, employee_number=number, employee_category_id=cat.id if cat else None,
        designation_id=des.id if des else None, work_location_id=loc.id if loc else None,
        date_of_joining=joining, separation_date=separation, status=status))
    db.commit()


def test_a_service_token_is_required_and_must_carry_the_scope(client, db):
    world(db)
    assert client.get(URL).status_code == 401                                  # no token
    assert client.get(URL, headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert client.get(URL, headers=mint(db, scopes="payroll:read")).status_code == 403
    assert client.get(URL, headers=mint(db, revoked=True)).status_code == 401   # revoked
    yesterday = dt.datetime.utcnow() - dt.timedelta(days=1)
    assert client.get(URL, headers=mint(db, expires_at=yesterday)).status_code == 401
    tomorrow = dt.datetime.utcnow() + dt.timedelta(days=1)
    assert client.get(URL, headers=mint(db, expires_at=tomorrow)).status_code == 200
    assert client.get(URL, headers=mint(db)).status_code == 200


def test_the_legacy_depot_employees_path_still_answers(client, db):
    """The feed was renamed to /employees; the old path stays until every
    deployed consumer has moved."""
    world(db)
    assert client.get(LEGACY_URL, headers=mint(db)).status_code == 200
    assert client.get(LEGACY_URL + "/rules", headers=mint(db)).status_code == 200


def test_only_operations_staff_coach_captains_are_exported(client, db):
    world(db)
    add(db, "E1", "Ravi", "Kumar", "Operations Staff", "Coach Captain", dt.date(2025, 4, 1))
    add(db, "E2", "Asha", "Rao", "Staff", "HR Executive", dt.date(2025, 4, 1))          # wrong both
    add(db, "E3", "Vijay", "Singh", "Staff", "Coach Captain", dt.date(2025, 4, 1))      # wrong category
    add(db, "E4", "Meena", "Das", "Operations Staff", "HR Executive", dt.date(2025, 4, 1))  # wrong designation
    rows = client.get(URL, headers=mint(db)).json()["employees"]
    assert [r["employee_number"] for r in rows] == ["E1"]
    assert rows[0] == {"employee_number": "E1", "full_name": "Ravi Kumar", "designation": "Coach Captain",
                       "staff_type": "DRIVER", "home_depot_code": "DEP01",
                       "start_date": "2025-04-01", "end_date": None, "status": "ACTIVE"}


def test_half_entered_records_never_reach_the_depot(client, db):
    world(db)
    for n, status in [("D1", "DRAFT"), ("D2", "PENDING_APPROVAL"), ("D3", "APPROVED")]:
        add(db, n, "X", "Y", "Operations Staff", "Coach Captain", dt.date(2025, 4, 1), status=status)
    add(db, "L1", "Live", "One", "Operations Staff", "Coach Captain", dt.date(2025, 4, 1), status="NOTICE_PERIOD")
    add(db, "S1", "Gone", "Away", "Operations Staff", "Coach Captain", dt.date(2024, 1, 1),
        status="SEPARATED", separation=dt.date(2025, 3, 31))
    rows = {r["employee_number"]: r for r in client.get(URL, headers=mint(db)).json()["employees"]}
    assert set(rows) == {"L1", "S1"}
    assert rows["L1"]["status"] == "ACTIVE"            # serving notice is still rosterable
    assert rows["S1"]["status"] == "INACTIVE" and rows["S1"]["end_date"] == "2025-03-31"


def test_a_stint_without_a_joining_date_is_skipped(client, db):
    world(db)
    add(db, "N1", "No", "Date", "Operations Staff", "Coach Captain", None)
    assert client.get(URL, headers=mint(db)).json()["employees"] == []


def test_the_rules_are_reported_so_a_renamed_master_is_visible(client, db):
    world(db)
    body = client.get(f"{URL}/rules", headers=mint(db)).json()
    assert body["rules"][0]["employee_category_exists"] is True
    assert body["rules"][0]["designation_exists"] is True
    assert "Coach Captain" in body["designations"]


def test_rules_can_be_overridden_without_a_code_change(monkeypatch):
    monkeypatch.setenv("HRMS_DEPOT_EXPORT_RULES",
                       '[{"employee_category": "Ops", "designation": "Driver", "staff_type": "DRIVER"},'
                       ' {"employee_category": "Ops", "designation": "Guard", "staff_type": "CONDUCTOR"}]')
    assert svc.staff_type_for("Ops", "Guard") == "CONDUCTOR"
    assert svc.staff_type_for("ops", "driver") == "DRIVER"      # names match case-insensitively
    assert svc.staff_type_for("Ops", "Cleaner") is None
    monkeypatch.setenv("HRMS_DEPOT_EXPORT_RULES", "{not json")
    try:
        svc.rules()
        raise AssertionError("expected a ValueError")
    except ValueError as exc:
        assert "not valid JSON" in str(exc)
