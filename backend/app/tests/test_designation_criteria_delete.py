"""Removing a Designation Criteria requirement when candidates have already
been tested against the criteria.

The guard exists because a CandidateStageResult is keyed by candidate +
criteria and carries no link back to the requirement row that produced it:
delete the last row asking for a criteria and recorded results would stay in
the database but vanish from the UI. These tests pin down the exception - it
is not the last row, so nothing is stranded.
"""
import datetime as dt

import pytest

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import RoleName
from app.models.models import (
    Candidate, CandidateStageResult, Company, CostCenter, Department, Designation, DesignationCriteria,
    EmployeeCategory, Role, SelectionCriteria, User,
)

DELETE = "/api/v1/recruitment/designation-criteria/{}"


@pytest.fixture()
def world(db):
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add_all([CostCenter(company_id=company.id, name="North", code="CC-N"),
                CostCenter(company_id=company.id, name="South", code="CC-S")])
    db.add_all([Designation(name="Coach Captain"), EmployeeCategory(name="Operations Staff"),
                Department(name="Operations", code="D-OPS"), Role(name=RoleName.HR_ADMIN)])
    db.commit()
    admin_role = db.query(Role).filter(Role.name == RoleName.HR_ADMIN).first()
    db.add(User(username="admin", hashed_password="x", role_id=admin_role.id))
    db.add(SelectionCriteria(name="Road Test"))
    db.commit()
    admin = db.query(User).filter(User.username == "admin").first()
    app.dependency_overrides[get_current_user] = lambda: admin
    yield {
        "db": db, "admin": admin,
        "north": db.query(CostCenter).filter(CostCenter.code == "CC-N").first(),
        "south": db.query(CostCenter).filter(CostCenter.code == "CC-S").first(),
        "designation": db.query(Designation).first(),
        "category": db.query(EmployeeCategory).first(),
        "criteria": db.query(SelectionCriteria).first(),
    }
    app.dependency_overrides.clear()


def requirement(world, cost_center=None, mandatory=True):
    db = world["db"]
    row = DesignationCriteria(
        designation_id=world["designation"].id, criteria_id=world["criteria"].id,
        cost_center_id=cost_center.id if cost_center else None,
        is_mandatory=mandatory, sequence=1, is_active=True,
    )
    db.add(row)
    db.commit()
    return row


def candidate_with_result(world, cost_center, reference="C-1"):
    """A candidate in that Cost Center with a recorded result for the
    criteria - what used to make the row undeletable."""
    db = world["db"]
    db.add(Candidate(
        reference_number=reference, first_name="Devi", last_name=reference, status="APPROVED",
        applied_designation_id=world["designation"].id,
        applied_employee_category_id=world["category"].id,
        applied_cost_center_id=cost_center.id,
    ))
    db.commit()
    candidate = db.query(Candidate).filter(Candidate.reference_number == reference).first()
    db.add(CandidateStageResult(candidate_id=candidate.id, criteria_id=world["criteria"].id,
                                result="PASS", tested_on=dt.date.today()))
    db.commit()
    return candidate


# --- the case the user hit ----------------------------------------------

def test_a_cost_center_row_can_go_when_a_global_row_still_covers_it(world):
    from fastapi.testclient import TestClient
    client = TestClient(app)
    requirement(world)                                   # global
    scoped = requirement(world, world["north"], mandatory=False)
    candidate_with_result(world, world["north"])

    res = client.delete(DELETE.format(scoped.id))
    assert res.status_code == 200, res.text
    assert world["db"].query(DesignationCriteria).filter(DesignationCriteria.id == scoped.id).first() is None


def test_the_results_are_still_visible_afterwards(world):
    """The whole justification for allowing the delete."""
    from fastapi.testclient import TestClient
    client = TestClient(app)
    requirement(world)
    scoped = requirement(world, world["north"])
    candidate = candidate_with_result(world, world["north"])
    client.delete(DELETE.format(scoped.id))

    from app.services import recruitment_service
    statuses = recruitment_service.criteria_status(world["db"], candidate)
    assert [s["result"] for s in statuses] == ["PASS"]


# --- and where it must still refuse -------------------------------------

def test_the_last_row_still_cannot_be_deleted_once_results_exist(world):
    from fastapi.testclient import TestClient
    client = TestClient(app)
    row = requirement(world)
    candidate_with_result(world, world["north"])
    res = client.delete(DELETE.format(row.id))
    assert res.status_code == 400
    assert "deactivate it instead" in res.json()["detail"]


def test_an_inactive_sibling_does_not_count_as_coverage(world):
    """required_criteria filters on is_active before resolving specificity,
    so a deactivated row covers nobody."""
    from fastapi.testclient import TestClient
    client = TestClient(app)
    global_row = requirement(world)
    global_row.is_active = False
    world["db"].commit()
    scoped = requirement(world, world["north"])
    candidate_with_result(world, world["north"])
    res = client.delete(DELETE.format(scoped.id))
    assert res.status_code == 400


def test_removing_a_global_row_needs_every_tested_cost_center_covered(world):
    """Partial coverage is not coverage: North has its own row, South does
    not, so South's candidate would be the one left stranded."""
    from fastapi.testclient import TestClient
    client = TestClient(app)
    global_row = requirement(world)
    requirement(world, world["north"])
    candidate_with_result(world, world["north"], "C-N")
    candidate_with_result(world, world["south"], "C-S")

    res = client.delete(DELETE.format(global_row.id))
    assert res.status_code == 400


def test_a_global_row_can_go_when_every_tested_cost_center_has_its_own(world):
    from fastapi.testclient import TestClient
    client = TestClient(app)
    global_row = requirement(world)
    requirement(world, world["north"])
    requirement(world, world["south"])
    candidate_with_result(world, world["north"], "C-N")
    candidate_with_result(world, world["south"], "C-S")

    res = client.delete(DELETE.format(global_row.id))
    assert res.status_code == 200, res.text


def test_a_row_with_no_results_at_all_still_deletes(world):
    from fastapi.testclient import TestClient
    client = TestClient(app)
    row = requirement(world, world["north"])
    res = client.delete(DELETE.format(row.id))
    assert res.status_code == 200


def test_a_sibling_for_a_different_criteria_is_not_coverage(world):
    from fastapi.testclient import TestClient
    client = TestClient(app)
    db = world["db"]
    db.add(SelectionCriteria(name="Eye Test"))
    db.commit()
    other = db.query(SelectionCriteria).filter(SelectionCriteria.name == "Eye Test").first()
    db.add(DesignationCriteria(designation_id=world["designation"].id, criteria_id=other.id,
                               cost_center_id=None, is_mandatory=True, sequence=1, is_active=True))
    db.commit()
    scoped = requirement(world, world["north"])
    candidate_with_result(world, world["north"])
    res = client.delete(DELETE.format(scoped.id))
    assert res.status_code == 400
