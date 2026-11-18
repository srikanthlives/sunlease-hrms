"""Configurable Excel export: the column pattern, the filters, and the
promise that the preview is the file.

The riskiest thing an export can do is hand someone data they are not
allowed to see, so the sensitive-column gate gets the most attention here.
"""
import io
from datetime import date

import pytest
from openpyxl import load_workbook

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import EpisodeStatus, Permission, RoleName
from app.models.models import (
    BankAccount, Company, CostCenter, Department, Designation, Employee, EmployeeCategory,
    EmploymentEpisode, ExportTemplate, OrgAssignment, Project, Role, RolePermission, StatutoryInfo, User,
)

COLUMNS = "/api/v1/exports/columns"
PREVIEW = "/api/v1/exports/preview"
DOWNLOAD = "/api/v1/exports/download"
TEMPLATES = "/api/v1/exports/templates"


@pytest.fixture()
def world(db):
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add_all([CostCenter(company_id=company.id, name="North", code="CC-N"),
                CostCenter(company_id=company.id, name="South", code="CC-S")])
    db.add(Department(name="Operations", code="D-OPS"))
    db.add(Designation(name="Coach Captain"))
    db.add(EmployeeCategory(name="Operations Staff"))
    db.add_all([Role(name=RoleName.HR_ADMIN), Role(name=RoleName.HR_STAFF)])
    db.commit()
    north, south = db.query(CostCenter).order_by(CostCenter.id).all()
    db.add_all([Project(cost_center_id=north.id, name="North Ops", code="P-N"),
                Project(cost_center_id=south.id, name="South Ops", code="P-S")])
    db.commit()
    admin_role = db.query(Role).filter(Role.name == RoleName.HR_ADMIN).first()
    db.add(User(username="admin", hashed_password="x", role_id=admin_role.id))
    db.commit()
    admin = db.query(User).filter(User.username == "admin").first()
    # The JWT plumbing is not what these tests are about, so the signed-in
    # user is injected directly - every other dependency still runs for real.
    app.dependency_overrides[get_current_user] = lambda: admin
    yield {"db": db, "north": north, "south": south, "admin": admin,
           "dept": db.query(Department).first(),
           "p_north": db.query(Project).order_by(Project.id).first()}
    app.dependency_overrides.clear()


def employee(world, number, first, cost_center=None, status=EpisodeStatus.ACTIVE, sensitive=False):
    db = world["db"]
    cc = cost_center or world["north"]
    db.add(Employee(first_name=first, last_name="Person",
                    aadhaar="111122223333" if sensitive else None,
                    pan="ABCDE1234F" if sensitive else None))
    db.commit()
    person = db.query(Employee).filter(Employee.first_name == first).first()
    db.add(EmploymentEpisode(employee_id=person.id, employee_number=number, status=status,
                             designation_id=db.query(Designation).first().id))
    db.commit()
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == number).first()
    db.add(OrgAssignment(episode_id=episode.id, cost_center_id=cc.id, department_id=world["dept"].id,
                         project_id=None, effective_from=date(2024, 1, 1)))
    if sensitive:
        db.add(StatutoryInfo(episode_id=episode.id, uan="100200300400", esi_number="ESI-9", effective_from=date(2024, 1, 1)))
        db.add(BankAccount(episode_id=episode.id, bank_name="SBI", account_number="9876543210",
                           ifsc="SBIN0001234", effective_from=date(2024, 1, 1)))
    db.commit()
    return episode


def staff_user(world, *permissions, cost_centers=("north",)):
    """A non-admin signed in with exactly the permissions named - admins
    bypass every check, so they can't demonstrate a gate. Scoped to the
    named Cost Centers: a non-admin with NO UserCostCenterScope row sees
    nothing at all (an empty allow-list, not an unrestricted one)."""
    db = world["db"]
    role = db.query(Role).filter(Role.name == RoleName.HR_STAFF).first()
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    for code in permissions:
        db.add(RolePermission(role_id=role.id, permission_code=code))
    if not db.query(User).filter(User.username == "staff").first():
        db.add(User(username="staff", hashed_password="x", role_id=role.id))
    db.commit()
    user = db.query(User).filter(User.username == "staff").first()
    from app.models.models import UserCostCenterScope
    db.query(UserCostCenterScope).filter(UserCostCenterScope.user_id == user.id).delete()
    for name in cost_centers:
        db.add(UserCostCenterScope(user_id=user.id, cost_center_id=world[name].id))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def spec(**over):
    body = {"entity": "EMPLOYEE", "columns": ["employee_number", "first_name", "cost_center"]}
    body.update(over)
    return body


# --- the column pattern ----------------------------------------------------

def test_the_file_has_the_chosen_columns_in_the_chosen_order(client, world):
    employee(world, "N-1", "Asha")
    columns = ["cost_center", "employee_number", "first_name"]      # deliberately not catalog order

    r = client.post(DOWNLOAD, json=spec(columns=columns))
    assert r.status_code == 200, r.text
    ws = load_workbook(io.BytesIO(r.content)).active
    assert [c.value for c in ws[1]] == ["Cost Center", "Employee No.", "First Name"]
    assert [c.value for c in ws[2]] == ["North", "N-1", "Asha"]
    assert ws.title == "Employees"
    assert ws.freeze_panes == "A2"                                  # header stays put when scrolling


def test_a_column_repeated_in_the_pattern_appears_once(client, world):
    employee(world, "N-1", "Asha")
    r = client.post(PREVIEW, json=spec(columns=["first_name", "employee_number", "first_name"]))
    assert [c["key"] for c in r.json()["columns"]] == ["first_name", "employee_number"]


def test_no_columns_is_refused(client, world):
    assert client.post(PREVIEW, json=spec(columns=[])).status_code == 422


def test_an_unknown_column_is_refused(client, world):
    r = client.post(PREVIEW, json=spec(columns=["first_name", "salary"]))
    assert r.status_code == 400
    assert "'salary' is not available" in r.json()["detail"]


# --- sorting ---------------------------------------------------------------

def test_rows_come_back_in_the_chosen_sort_order(client, world):
    for number, first in (("N-2", "Chandra"), ("N-1", "Asha"), ("N-3", "Bhanu")):
        employee(world, number, first)

    asc = client.post(PREVIEW, json=spec(sort_by="first_name", sort_dir="asc")).json()
    assert [row[1] for row in asc["rows"]] == ["Asha", "Bhanu", "Chandra"]
    desc = client.post(PREVIEW, json=spec(sort_by="first_name", sort_dir="desc")).json()
    assert [row[1] for row in desc["rows"]] == ["Chandra", "Bhanu", "Asha"]


def test_sorting_puts_blanks_last_either_way(client, world):
    """A missing value is never "smallest" - an export sorted by Separation
    Date should not open on a page of blanks."""
    employee(world, "N-1", "Asha")
    employee(world, "N-2", "Bhanu")
    db = world["db"]
    db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == "N-1").update(
        {"separation_date": date(2026, 3, 1)})
    db.commit()

    for direction in ("asc", "desc"):
        rows = client.post(PREVIEW, json=spec(
            columns=["employee_number", "separation_date"], sort_by="separation_date", sort_dir=direction)).json()["rows"]
        assert rows[0][0] == "N-1", direction
        assert rows[-1][1] is None, direction


def test_sorting_by_a_column_that_is_not_exported_is_refused(client, world):
    """Otherwise the file comes back in an order nothing in it explains."""
    employee(world, "N-1", "Asha")
    r = client.post(PREVIEW, json=spec(columns=["employee_number"], sort_by="first_name"))
    assert r.status_code == 400
    assert "must be one of the exported columns" in r.json()["detail"]


# --- filters ---------------------------------------------------------------

def test_only_the_filtered_rows_are_exported(client, world):
    employee(world, "N-1", "Asha")
    employee(world, "S-1", "Bhanu", cost_center=world["south"])

    r = client.post(PREVIEW, json=spec(filters={"cost_center": "South"}))
    assert r.json()["total"] == 1
    assert r.json()["rows"][0][0] == "S-1"


def test_the_status_filter_narrows_the_export(client, world):
    employee(world, "N-1", "Asha")
    employee(world, "N-2", "Bhanu", status=EpisodeStatus.DRAFT)

    r = client.post(PREVIEW, json=spec(filters={"status": "ACTIVE"}))
    assert [row[0] for row in r.json()["rows"]] == ["N-1"]


def test_the_search_filter_matches_name_and_number(client, world):
    employee(world, "N-1", "Asha")
    employee(world, "N-2", "Bhanu")

    assert client.post(PREVIEW, json=spec(filters={"search": "asha"})).json()["total"] == 1
    assert client.post(PREVIEW, json=spec(filters={"search": "N-2"})).json()["total"] == 1
    assert client.post(PREVIEW, json=spec(filters={"search": "nobody"})).json()["total"] == 0


def test_a_filter_key_the_entity_does_not_have_is_ignored_not_fatal(client, world):
    """The wizard sends its whole filter state, which may carry a key from
    the other entity - that must not empty the export or 400."""
    employee(world, "N-1", "Asha")
    r = client.post(PREVIEW, json=spec(filters={"interest_status": "INTERESTED"}))
    assert r.status_code == 200
    assert r.json()["total"] == 1


# --- preview = file --------------------------------------------------------

def test_the_preview_is_the_first_page_of_the_file(client, world):
    for n in range(1, 31):
        employee(world, f"N-{n:02d}", f"Person{n:02d}")

    preview = client.post(PREVIEW, json=spec(sort_by="employee_number")).json()
    assert preview["total"] == 30 and preview["shown"] == 25     # capped, with the real count alongside

    ws = load_workbook(io.BytesIO(client.post(DOWNLOAD, json=spec(sort_by="employee_number")).content)).active
    file_rows = [[c.value for c in row] for row in ws.iter_rows(min_row=2)]
    assert len(file_rows) == 30
    assert file_rows[:25] == preview["rows"]                      # same rows, same order


def test_an_export_with_no_matching_rows_still_produces_a_header(client, world):
    employee(world, "N-1", "Asha")
    r = client.post(DOWNLOAD, json=spec(filters={"search": "nobody"}))
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.content)).active
    assert [c.value for c in ws[1]] == ["Employee No.", "First Name", "Cost Center"]
    assert ws.max_row == 1


def test_booleans_are_written_as_yes_no(client, world):
    employee(world, "N-1", "Asha")
    r = client.post(DOWNLOAD, json=spec(columns=["employee_number", "rejoined"]))
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws["B2"].value == "No"


# --- the sensitive-column gate --------------------------------------------

def test_sensitive_columns_are_not_even_offered_without_the_permission(client, world):
    staff_user(world, Permission.EMPLOYEE_VIEW)
    offered = client.get(COLUMNS, params={"entity": "EMPLOYEE"}).json()["columns"]
    keys = {c["key"] for c in offered}
    assert "first_name" in keys
    for hidden in ("aadhaar", "pan", "uan", "account_number", "ifsc"):
        assert hidden not in keys


def test_asking_for_a_sensitive_column_without_the_permission_is_refused(client, world):
    """Not masked to blanks - refused, so an export can never be a way
    around the profile page's field-level masking."""
    employee(world, "N-1", "Asha", sensitive=True)
    staff_user(world, Permission.EMPLOYEE_VIEW)

    for column in ("aadhaar", "pan", "uan", "account_number", "ifsc"):
        r = client.post(PREVIEW, json=spec(columns=["employee_number", column]))
        assert r.status_code == 400, column
        assert "is not available for export" in r.json()["detail"]


def test_sensitive_columns_are_written_for_a_caller_who_may_see_them(client, world):
    employee(world, "N-1", "Asha", sensitive=True)
    staff_user(world, Permission.EMPLOYEE_VIEW, Permission.EMPLOYEE_SENSITIVE_VIEW)

    columns = ["employee_number", "aadhaar", "pan", "uan", "esi_number", "bank_name", "account_number", "ifsc"]
    assert {c["key"] for c in client.get(COLUMNS, params={"entity": "EMPLOYEE"}).json()["columns"]} >= set(columns)
    ws = load_workbook(io.BytesIO(client.post(DOWNLOAD, json=spec(columns=columns)).content)).active
    assert [c.value for c in ws[2]] == [
        "N-1", "111122223333", "ABCDE1234F", "100200300400", "ESI-9", "SBI", "9876543210", "SBIN0001234"]


def test_exporting_needs_permission_to_view_the_list_at_all(client, world):
    staff_user(world, Permission.RECRUITMENT_VIEW)       # candidates yes, employees no
    assert client.post(PREVIEW, json=spec()).status_code == 403
    assert client.get(COLUMNS, params={"entity": "EMPLOYEE"}).status_code == 403
    assert client.get(COLUMNS, params={"entity": "CANDIDATE"}).status_code == 200


def test_cost_center_scope_still_applies_to_an_export(client, world):
    """The export reuses the list's own row builder, so a scoped user's file
    can only ever contain their own Cost Centers."""
    employee(world, "N-1", "Asha")
    employee(world, "S-1", "Bhanu", cost_center=world["south"])
    staff_user(world, Permission.EMPLOYEE_VIEW, cost_centers=("north",))

    rows = client.post(PREVIEW, json=spec()).json()["rows"]
    assert [row[0] for row in rows] == ["N-1"]


def test_an_unknown_entity_is_refused(client, world):
    assert client.post(PREVIEW, json=spec(entity="PAYSLIP")).status_code == 400


# --- candidates ------------------------------------------------------------

def test_candidates_export_their_own_columns(client, world):
    from app.models.models import Candidate
    db = world["db"]
    db.add(Candidate(reference_number="C-1", first_name="Devi", last_name="Candidate", status="APPLIED",
                     applied_cost_center_id=world["north"].id,
                     applied_designation_id=db.query(Designation).first().id,
                     applied_employee_category_id=db.query(EmployeeCategory).first().id))
    db.commit()

    catalog = client.get(COLUMNS, params={"entity": "CANDIDATE"}).json()
    assert "reference_number" in {c["key"] for c in catalog["columns"]}
    assert "employee_number" not in {c["key"] for c in catalog["columns"]}

    r = client.post(DOWNLOAD, json={"entity": "CANDIDATE",
                                    "columns": ["reference_number", "first_name", "cost_center_name"]})
    ws = load_workbook(io.BytesIO(r.content)).active
    assert ws.title == "Candidates"
    assert [c.value for c in ws[2]] == ["C-1", "Devi", "North"]


# --- saved patterns --------------------------------------------------------

def test_a_saved_pattern_keeps_its_column_order(client, world):
    body = {"name": "Payroll handover", "entity": "EMPLOYEE",
            "columns": ["cost_center", "employee_number", "first_name"], "sort_by": "employee_number"}
    created = client.post(TEMPLATES, json=body)
    assert created.status_code == 200, created.text
    assert created.json()["columns"] == ["cost_center", "employee_number", "first_name"]
    assert created.json()["owned"] is True

    listed = client.get(TEMPLATES, params={"entity": "EMPLOYEE"}).json()
    assert [t["name"] for t in listed] == ["Payroll handover"]
    assert client.get(TEMPLATES, params={"entity": "CANDIDATE"}).json() == []


def test_a_pattern_cannot_sort_by_a_column_it_does_not_contain(client, world):
    r = client.post(TEMPLATES, json={"name": "Bad", "entity": "EMPLOYEE",
                                     "columns": ["employee_number"], "sort_by": "first_name"})
    assert r.status_code == 400
    assert "must be one of the pattern's columns" in r.json()["detail"]


def test_two_patterns_of_your_own_cannot_share_a_name(client, world):
    body = {"name": "Audit list", "entity": "EMPLOYEE", "columns": ["employee_number"]}
    assert client.post(TEMPLATES, json=body).status_code == 200
    again = client.post(TEMPLATES, json=body)
    assert again.status_code == 409
    assert "already have a pattern named" in again.json()["detail"]


def test_a_pattern_can_be_renamed_recolumned_and_deleted(client, world):
    created = client.post(TEMPLATES, json={"name": "Draft", "entity": "EMPLOYEE",
                                           "columns": ["employee_number"]}).json()
    updated = client.put(f"{TEMPLATES}/{created['id']}", json={
        "name": "Final", "entity": "EMPLOYEE", "columns": ["first_name", "employee_number"],
        "sort_by": "first_name", "sort_dir": "desc"})
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Final"
    assert updated.json()["columns"] == ["first_name", "employee_number"]
    assert updated.json()["sort_dir"] == "desc"

    assert client.delete(f"{TEMPLATES}/{created['id']}").status_code == 200
    assert client.get(TEMPLATES).json() == []


def test_someone_elses_private_pattern_is_neither_listed_nor_editable(client, world):
    db = world["db"]
    mine = client.post(TEMPLATES, json={"name": "Mine", "entity": "EMPLOYEE", "columns": ["employee_number"]}).json()
    staff_user(world, Permission.EMPLOYEE_VIEW)

    assert client.get(TEMPLATES).json() == []                     # not visible
    assert client.put(f"{TEMPLATES}/{mine['id']}", json={
        "name": "Hijacked", "entity": "EMPLOYEE", "columns": ["employee_number"]}).status_code == 403
    assert client.delete(f"{TEMPLATES}/{mine['id']}").status_code == 403
    db.refresh(db.query(ExportTemplate).first())
    assert db.query(ExportTemplate).first().name == "Mine"


def test_a_shared_pattern_is_visible_to_everyone_but_only_admins_can_share(client, world):
    shared = client.post(TEMPLATES, json={"name": "Agreed layout", "entity": "EMPLOYEE",
                                          "columns": ["employee_number"], "is_shared": True})
    assert shared.status_code == 200, shared.text
    staff_user(world, Permission.EMPLOYEE_VIEW)

    listed = client.get(TEMPLATES).json()
    assert [t["name"] for t in listed] == ["Agreed layout"]
    assert listed[0]["owned"] is False                            # readable, not theirs to change

    denied = client.post(TEMPLATES, json={"name": "Mine too", "entity": "EMPLOYEE",
                                          "columns": ["employee_number"], "is_shared": True})
    assert denied.status_code == 403
    assert "Only an HR Admin can share" in denied.json()["detail"]


def test_a_missing_pattern_is_a_404(client, world):
    assert client.delete(f"{TEMPLATES}/9999").status_code == 404
