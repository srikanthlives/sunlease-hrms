"""Bulk candidate transfer: the all-or-nothing contract and the approval split."""
import pytest

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import RoleName
from app.models.models import (
    Candidate, CandidateChangeRequest, Company, CostCenter, Designation, EmployeeCategory, Project,
    Role, User,
)

URL = "/api/v1/recruitment/candidates-transfer"


@pytest.fixture()
def world(db):
    """Two Cost Centers, each with one Project, and an HR_ADMIN signed in."""
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add_all([CostCenter(company_id=company.id, name="North", code="CC-N"),
                CostCenter(company_id=company.id, name="South", code="CC-S")])
    db.add_all([Designation(name="Coach Captain"), EmployeeCategory(name="Operations Staff")])
    db.commit()
    north, south = db.query(CostCenter).order_by(CostCenter.id).all()
    db.add_all([Project(cost_center_id=north.id, name="North Ops", code="P-N"),
                Project(cost_center_id=south.id, name="South Ops", code="P-S")])
    db.add(Role(name=RoleName.HR_ADMIN))
    db.commit()
    p_north, p_south = db.query(Project).order_by(Project.id).all()
    db.add(User(username="hr", hashed_password="x", role_id=db.query(Role).first().id))
    db.commit()
    user = db.query(User).first()
    # The JWT plumbing is not what these tests are about, so the signed-in user
    # is injected directly - every other dependency still runs for real.
    app.dependency_overrides[get_current_user] = lambda: user
    yield {"db": db, "north": north, "south": south, "p_north": p_north, "p_south": p_south}
    app.dependency_overrides.clear()


def candidate(db, ref, cost_center, project, status="APPLIED"):
    db.add(Candidate(
        reference_number=ref, first_name=ref, last_name="Candidate", status=status,
        applied_designation_id=db.query(Designation).first().id,
        applied_employee_category_id=db.query(EmployeeCategory).first().id,
        applied_cost_center_id=cost_center.id, applied_project_id=project.id))
    db.commit()
    return db.query(Candidate).filter(Candidate.reference_number == ref).first()


def destination(world, ids):
    return {"candidate_ids": ids, "applied_cost_center_id": world["south"].id,
            "applied_project_id": world["p_south"].id, "remarks": "depot reshuffle"}


def test_a_selection_moves_together(client, world):
    db = world["db"]
    refs = ["C1", "C2", "C3"]
    ids = [candidate(db, r, world["north"], world["p_north"]).id for r in refs]

    r = client.post(URL, json=destination(world, ids))
    assert r.status_code == 200, r.text
    assert r.json() == {"transferred": 3, "submitted_for_approval": 0, "queued_references": []}

    for c in db.query(Candidate).all():
        db.refresh(c)
        assert (c.applied_cost_center_id, c.applied_project_id) == (world["south"].id, world["p_south"].id)
        assert c.reference_number in refs        # the reference never changes


def test_an_approved_candidate_is_queued_rather_than_overwritten(client, world):
    """Approved data must not be overwritten directly, so that move becomes a change request."""
    db = world["db"]
    plain = candidate(db, "C1", world["north"], world["p_north"])
    approved = candidate(db, "C2", world["north"], world["p_north"], status="APPROVED")

    r = client.post(URL, json=destination(world, [plain.id, approved.id]))
    assert r.status_code == 200, r.text
    assert r.json() == {"transferred": 1, "submitted_for_approval": 1, "queued_references": ["C2"]}

    db.refresh(plain)
    db.refresh(approved)
    assert plain.applied_cost_center_id == world["south"].id          # applied straight away
    assert approved.applied_cost_center_id == world["north"].id       # still where it was
    assert db.query(CandidateChangeRequest).count() == 1


@pytest.mark.parametrize("bad_status", ["CONVERTED", "REJECTED"])
def test_one_bad_candidate_refuses_the_whole_batch(client, world, bad_status):
    db = world["db"]
    good = candidate(db, "C1", world["north"], world["p_north"])
    bad = candidate(db, "C2", world["north"], world["p_north"], status=bad_status)

    r = client.post(URL, json=destination(world, [good.id, bad.id]))
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "Nothing was transferred" in detail and "1 of 2" in detail and "C2" in detail

    db.refresh(good)
    assert good.applied_cost_center_id == world["north"].id          # the good one stayed put


def test_a_candidate_already_there_is_reported_not_silently_skipped(client, world):
    db = world["db"]
    already = candidate(db, "C1", world["south"], world["p_south"])

    r = client.post(URL, json=destination(world, [already.id]))
    assert r.status_code == 400
    assert "already in this Cost Center and Project" in r.json()["detail"]


def test_a_missing_id_refuses_the_batch(client, world):
    db = world["db"]
    good = candidate(db, "C1", world["north"], world["p_north"])

    r = client.post(URL, json=destination(world, [good.id, 9999]))
    assert r.status_code == 400
    assert "candidate not found" in r.json()["detail"]
    db.refresh(good)
    assert good.applied_cost_center_id == world["north"].id


def test_the_project_must_belong_to_the_destination_cost_center(client, world):
    db = world["db"]
    c = candidate(db, "C1", world["north"], world["p_north"])

    r = client.post(URL, json={"candidate_ids": [c.id], "applied_cost_center_id": world["south"].id,
                               "applied_project_id": world["p_north"].id})
    assert r.status_code == 400
    assert "Project does not belong" in r.json()["detail"]


def test_an_empty_selection_is_rejected(client, world):
    assert client.post(URL, json=destination(world, [])).status_code == 422


def test_a_repeated_id_counts_once(client, world):
    db = world["db"]
    c = candidate(db, "C1", world["north"], world["p_north"])
    r = client.post(URL, json=destination(world, [c.id, c.id]))
    assert r.status_code == 200, r.text
    assert r.json()["transferred"] == 1
