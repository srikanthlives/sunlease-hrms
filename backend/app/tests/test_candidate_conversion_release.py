"""Deleting a converted candidate's employment record must undo the
conversion on the candidate side.

Without this the candidate stays CONVERTED pointing at an episode that no
longer exists: a dead "View employee record" link, with Requalify (which
sends them back to APPLIED to redo the whole pipeline) as the only way out.
"""
from datetime import date

import pytest

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import CandidateStatus, EpisodeStatus, RoleName
from app.models.models import (
    Candidate, CandidateStageResult, Company, CostCenter, Department, Designation, DesignationCriteria,
    Employee, EmployeeCategory, EmploymentEpisode, OrgAssignment, Project, Role, SelectionCriteria, User,
)

DELETE = "/api/v1/employees/{}"
DETAIL = "/api/v1/recruitment/candidates/{}"
REVERT = "/api/v1/recruitment/candidates/{}/revert-conversion"
CONVERT = "/api/v1/recruitment/candidates/{}/convert"


@pytest.fixture()
def world(db):
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add(CostCenter(company_id=company.id, name="North", code="CC-N"))
    db.add_all([Designation(name="Coach Captain"), EmployeeCategory(name="Operations Staff"),
                Department(name="Operations", code="D-OPS")])
    db.add_all([Role(name=RoleName.HR_ADMIN), Role(name=RoleName.HR_STAFF)])
    db.commit()
    north = db.query(CostCenter).first()
    db.add(Project(cost_center_id=north.id, name="North Ops", code="P-N"))
    db.commit()
    admin_role = db.query(Role).filter(Role.name == RoleName.HR_ADMIN).first()
    db.add(User(username="admin", hashed_password="x", role_id=admin_role.id))
    db.commit()
    admin = db.query(User).filter(User.username == "admin").first()
    # The JWT plumbing is not what these tests are about, so the signed-in
    # user is injected directly - every other dependency still runs for real.
    app.dependency_overrides[get_current_user] = lambda: admin
    yield {"db": db, "north": north, "admin": admin,
           "project": db.query(Project).first(), "dept": db.query(Department).first(),
           "designation": db.query(Designation).first(), "category": db.query(EmployeeCategory).first()}
    app.dependency_overrides.clear()


def candidate(world, reference="C-1", status=CandidateStatus.APPROVED):
    db = world["db"]
    db.add(Candidate(
        reference_number=reference, first_name="Devi", last_name="Candidate", status=status,
        applied_designation_id=world["designation"].id, applied_employee_category_id=world["category"].id,
        applied_cost_center_id=world["north"].id, applied_project_id=world["project"].id,
    ))
    db.commit()
    return db.query(Candidate).filter(Candidate.reference_number == reference).first()


def convert(world, c):
    """Puts the candidate through the real conversion endpoint."""
    from fastapi.testclient import TestClient
    client = TestClient(app)
    res = client.post(CONVERT.format(c.id), json={
        "employee_number": f"EMP-{c.id}", "date_of_joining": "2026-04-01",
        "employment_type_id": None, "employee_category_id": world["category"].id,
        "work_location_id": None, "confirmation_date": None,
    })
    assert res.status_code == 200, res.text
    world["db"].refresh(c)
    return c


def criteria_for(world, mandatory=True):
    """A mandatory selection criterion for the applied designation, marked
    PASS - what conversion requires."""
    db = world["db"]
    db.add(SelectionCriteria(name="Driving Test"))
    db.commit()
    sc = db.query(SelectionCriteria).first()
    db.add(DesignationCriteria(designation_id=world["designation"].id, criteria_id=sc.id,
                               is_mandatory=mandatory, sequence=1, is_active=True))
    db.commit()
    return sc


def pass_criterion(world, c, sc):
    db = world["db"]
    db.add(CandidateStageResult(candidate_id=c.id, criteria_id=sc.id, result="PASS",
                                tested_on=date(2026, 3, 1)))
    db.commit()


def test_deleting_the_employment_record_puts_the_candidate_back_to_approved(client, world):
    db = world["db"]
    sc = criteria_for(world)
    c = candidate(world)
    pass_criterion(world, c, sc)
    convert(world, c)
    assert c.status == CandidateStatus.CONVERTED
    episode_id, employee_id = c.converted_episode_id, c.converted_employee_id
    assert episode_id and employee_id

    r = client.delete(DELETE.format(episode_id))
    assert r.status_code == 200, r.text
    assert r.json()["candidate_reverted"] == "C-1"

    db.refresh(c)
    assert c.status == CandidateStatus.APPROVED        # not APPLIED - no pipeline redo
    assert c.converted_episode_id is None             # no dangling pointer
    # That was the person's only stint, so the Employee row went too - and
    # with it any reason to keep pointing at it.
    assert db.query(Employee).filter(Employee.id == employee_id).first() is None
    assert c.converted_employee_id is None


def test_the_selection_criteria_results_survive_the_revert(client, world):
    """Which is the whole point of going back to APPROVED rather than
    APPLIED - the candidate can be converted again immediately."""
    db = world["db"]
    sc = criteria_for(world)
    c = candidate(world)
    pass_criterion(world, c, sc)
    convert(world, c)
    client.delete(DELETE.format(c.converted_episode_id))

    db.refresh(c)
    detail = client.get(DETAIL.format(c.id)).json()
    assert detail["status"] == "APPROVED"
    assert [row["result"] for row in detail["criteria_status"]] == ["PASS"]
    assert detail["all_mandatory_passed"] is True

    # And converting again works straight away.
    again = client.post(CONVERT.format(c.id), json={
        "employee_number": "EMP-AGAIN", "date_of_joining": "2026-05-01",
        "employment_type_id": None, "employee_category_id": world["category"].id,
        "work_location_id": None, "confirmation_date": None,
    })
    assert again.status_code == 200, again.text


def test_a_surviving_person_keeps_the_breadcrumb_so_a_rejoiner_is_not_duplicated(client, world):
    """If the deleted stint was not the person's only one, the Employee row
    survives - and converted_employee_id must be kept, or re-converting
    creates a duplicate person instead of reattaching."""
    db = world["db"]
    sc = criteria_for(world)
    c = candidate(world)
    pass_criterion(world, c, sc)
    convert(world, c)
    employee_id = c.converted_employee_id

    # A second, separated stint for the same person, so the Employee row
    # outlives the draft.
    db.add(EmploymentEpisode(employee_id=employee_id, employee_number="OLD-1",
                             status=EpisodeStatus.SEPARATED, date_of_joining=date(2020, 1, 1)))
    db.commit()

    r = client.delete(DELETE.format(c.converted_episode_id))
    assert r.status_code == 200, r.text
    db.refresh(c)
    assert c.status == CandidateStatus.APPROVED
    assert c.converted_episode_id is None
    assert db.query(Employee).filter(Employee.id == employee_id).first() is not None
    assert c.converted_employee_id == employee_id            # breadcrumb kept


def test_deleting_an_ordinary_draft_touches_no_candidate(client, world):
    """A draft that never came from recruitment has nothing to release."""
    db = world["db"]
    db.add(Employee(first_name="Plain", last_name="Draft"))
    db.commit()
    person = db.query(Employee).filter(Employee.first_name == "Plain").first()
    db.add(EmploymentEpisode(employee_id=person.id, employee_number="D-1", status=EpisodeStatus.DRAFT))
    db.commit()
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == "D-1").first()
    untouched = candidate(world)

    r = client.delete(DELETE.format(episode.id))
    assert r.status_code == 200, r.text
    assert r.json()["candidate_reverted"] is None
    db.refresh(untouched)
    assert untouched.status == CandidateStatus.APPROVED


# --- the detail flag the UI reads ------------------------------------------

def test_the_detail_response_says_whether_the_employment_record_still_exists(client, world):
    db = world["db"]
    sc = criteria_for(world)
    c = candidate(world)
    pass_criterion(world, c, sc)
    convert(world, c)

    assert client.get(DETAIL.format(c.id)).json()["converted_episode_exists"] is True

    # Strand it the way an older deletion did: remove the episode without
    # releasing the conversion.
    episode_id = c.converted_episode_id
    db.query(OrgAssignment).filter(OrgAssignment.episode_id == episode_id).delete()
    db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).delete()
    db.commit()

    detail = client.get(DETAIL.format(c.id)).json()
    assert detail["status"] == "CONVERTED"
    assert detail["converted_episode_id"] == episode_id
    assert detail["converted_episode_exists"] is False       # so the UI shows no link


# --- the repair action for rows broken earlier -----------------------------

def test_revert_conversion_repairs_a_stranded_candidate(client, world):
    db = world["db"]
    sc = criteria_for(world)
    c = candidate(world)
    pass_criterion(world, c, sc)
    convert(world, c)
    episode_id = c.converted_episode_id
    db.query(OrgAssignment).filter(OrgAssignment.episode_id == episode_id).delete()
    db.query(EmploymentEpisode).filter(EmploymentEpisode.id == episode_id).delete()
    db.commit()

    r = client.post(REVERT.format(c.id))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "APPROVED"
    db.refresh(c)
    assert c.converted_episode_id is None


def test_revert_conversion_refuses_while_the_employment_record_exists(client, world):
    """So it can never be used to un-convert a real employee."""
    db = world["db"]
    sc = criteria_for(world)
    c = candidate(world)
    pass_criterion(world, c, sc)
    convert(world, c)

    r = client.post(REVERT.format(c.id))
    assert r.status_code == 400, r.text
    assert "still exists" in r.json()["detail"]
    db.refresh(c)
    assert c.status == CandidateStatus.CONVERTED


def test_revert_conversion_refuses_a_candidate_that_was_never_converted(client, world):
    c = candidate(world)
    r = client.post(REVERT.format(c.id))
    assert r.status_code == 400
    assert "Only a Converted candidate" in r.json()["detail"]


def test_revert_conversion_is_admin_only(client, world):
    db = world["db"]
    sc = criteria_for(world)
    c = candidate(world)
    pass_criterion(world, c, sc)
    convert(world, c)

    staff_role = db.query(Role).filter(Role.name == RoleName.HR_STAFF).first()
    db.add(User(username="staff", hashed_password="x", role_id=staff_role.id))
    db.commit()
    staff = db.query(User).filter(User.username == "staff").first()
    app.dependency_overrides[get_current_user] = lambda: staff

    assert client.post(REVERT.format(c.id)).status_code == 403
