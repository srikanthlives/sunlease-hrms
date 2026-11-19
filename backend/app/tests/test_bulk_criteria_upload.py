"""One test document, many candidates - the shared proof attachment.

The point of this feature is that a training/assessment report listing 20
attendees is ONE file, stored once, referenced by all 20 candidates. The two
things these tests pin down are therefore: the file is genuinely stored once
and shared, and removing it from one candidate never disturbs the other
nineteen.

Results are deliberately NOT set by the upload (such a report normally lists
both passes and failures), which is also asserted here.
"""
import io
import os

import pytest
from fastapi.testclient import TestClient

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import CandidateStatus, Permission, RoleName
from app.models.models import (
    Candidate, CandidateStageResult, Company, CostCenter, Department, Designation, DesignationCriteria,
    EmployeeCategory, Project, Role, RolePermission, SelectionCriteria, SharedCriteriaAttachment, User,
    UserCostCenterScope,
)
from app.services.storage import get_storage

BULK_LIST = "/api/v1/recruitment/bulk-criteria"
PREFLIGHT = "/api/v1/recruitment/bulk-criteria-preflight"
UPLOAD = "/api/v1/recruitment/candidates-bulk-stage-attachment"
DETAIL = "/api/v1/recruitment/candidates/{}"
PROOF = "/api/v1/recruitment/candidates/{}/stage-results/{}/attachment"


@pytest.fixture()
def world(db):
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add_all([
        CostCenter(company_id=company.id, name="North", code="CC-N"),
        CostCenter(company_id=company.id, name="South", code="CC-S"),
    ])
    db.add_all([Designation(name="Coach Captain"), Designation(name="Mechanic"),
                EmployeeCategory(name="Operations Staff"), Department(name="Operations", code="D-OPS")])
    db.add_all([Role(name=RoleName.HR_ADMIN), Role(name=RoleName.HR_STAFF)])
    db.commit()
    north = db.query(CostCenter).filter(CostCenter.code == "CC-N").first()
    db.add(Project(cost_center_id=north.id, name="North Ops", code="P-N"))
    db.commit()
    admin_role = db.query(Role).filter(Role.name == RoleName.HR_ADMIN).first()
    db.add(User(username="admin", hashed_password="x", role_id=admin_role.id))
    db.commit()
    admin = db.query(User).filter(User.username == "admin").first()
    app.dependency_overrides[get_current_user] = lambda: admin
    yield {
        "db": db, "admin": admin, "north": north,
        "south": db.query(CostCenter).filter(CostCenter.code == "CC-S").first(),
        "project": db.query(Project).first(),
        "designation": db.query(Designation).filter(Designation.name == "Coach Captain").first(),
        "other_designation": db.query(Designation).filter(Designation.name == "Mechanic").first(),
        "category": db.query(EmployeeCategory).first(),
    }
    app.dependency_overrides.clear()


def make_criteria(world, name="Safety Training", bulk=True, designation=None):
    db = world["db"]
    db.add(SelectionCriteria(name=name, supports_bulk_upload=bulk))
    db.commit()
    sc = db.query(SelectionCriteria).filter(SelectionCriteria.name == name).first()
    db.add(DesignationCriteria(
        designation_id=(designation or world["designation"]).id, criteria_id=sc.id,
        is_mandatory=True, sequence=1, is_active=True,
    ))
    db.commit()
    return sc


def make_candidate(world, reference, status=CandidateStatus.APPROVED, designation=None, cost_center=None):
    db = world["db"]
    db.add(Candidate(
        reference_number=reference, first_name="Devi", last_name=reference, status=status,
        applied_designation_id=(designation or world["designation"]).id,
        applied_employee_category_id=world["category"].id,
        applied_cost_center_id=(cost_center or world["north"]).id,
        applied_project_id=world["project"].id if cost_center is None else None,
    ))
    db.commit()
    return db.query(Candidate).filter(Candidate.reference_number == reference).first()


def upload(client, criteria, candidates, content=b"report pdf bytes", filename="training-report.pdf"):
    return client.post(UPLOAD, data={
        "criteria_id": str(criteria.id),
        "candidate_ids": ",".join(str(c.id) for c in candidates),
    }, files={"file": (filename, io.BytesIO(content), "application/pdf")})


# --- configuration -------------------------------------------------------

def test_only_bulk_enabled_criteria_are_offered(world, client):
    make_criteria(world, "Safety Training", bulk=True)
    make_criteria(world, "Eye Test", bulk=False)
    names = [c["name"] for c in client.get(BULK_LIST).json()]
    assert names == ["Safety Training"]


def test_inactive_criteria_is_not_offered(world, client):
    sc = make_criteria(world, "Safety Training", bulk=True)
    sc.is_active = False
    world["db"].commit()
    assert client.get(BULK_LIST).json() == []


def test_upload_refuses_a_criteria_not_configured_for_bulk(world, client):
    sc = make_criteria(world, "Eye Test", bulk=False)
    c = make_candidate(world, "C-1")
    res = upload(client, sc, [c])
    assert res.status_code == 400
    assert "not configured for bulk upload" in res.json()["detail"]


# --- preflight -----------------------------------------------------------

def test_preflight_reports_eligible_candidates(world, client):
    sc = make_criteria(world)
    a, b = make_candidate(world, "C-1"), make_candidate(world, "C-2")
    rows = client.get(PREFLIGHT, params={"criteria_id": sc.id, "candidate_ids": f"{a.id},{b.id}"}).json()["candidates"]
    assert len(rows) == 2
    assert all(r["blocked_reason"] is None for r in rows)
    assert {r["reference_number"] for r in rows} == {"C-1", "C-2"}


def test_preflight_blocks_a_designation_that_does_not_require_the_test(world, client):
    sc = make_criteria(world)
    other = make_candidate(world, "C-2", designation=world["other_designation"])
    row = client.get(PREFLIGHT, params={"criteria_id": sc.id, "candidate_ids": str(other.id)}).json()["candidates"][0]
    assert "is not required for this candidate's designation" in row["blocked_reason"]


def test_preflight_blocks_a_candidate_who_is_not_approved(world, client):
    sc = make_criteria(world)
    applied = make_candidate(world, "C-3", status=CandidateStatus.APPLIED)
    row = client.get(PREFLIGHT, params={"criteria_id": sc.id, "candidate_ids": str(applied.id)}).json()["candidates"][0]
    assert "must be Approved" in row["blocked_reason"]


def test_preflight_surfaces_an_already_recorded_result(world, client):
    sc = make_criteria(world)
    c = make_candidate(world, "C-1")
    client.post(f"/api/v1/recruitment/candidates/{c.id}/stage-results",
                json={"criteria_id": sc.id, "result": "PASS", "tested_on": "2026-04-01", "remarks": None})
    row = client.get(PREFLIGHT, params={"criteria_id": sc.id, "candidate_ids": str(c.id)}).json()["candidates"][0]
    assert row["blocked_reason"] is None        # shown, not blocked - HR decides
    assert row["existing_result"] == "PASS"


def test_preflight_refuses_an_unknown_candidate_id(world, client):
    sc = make_criteria(world)
    c = make_candidate(world, "C-1")
    res = client.get(PREFLIGHT, params={"criteria_id": sc.id, "candidate_ids": f"{c.id},9999"})
    assert res.status_code == 400
    assert "not found" in res.json()["detail"]


# --- the upload itself ---------------------------------------------------

def test_one_file_is_stored_once_and_shared(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 6)]
    res = upload(client, sc, people)
    assert res.status_code == 200, res.text
    assert res.json()["attached_count"] == 5

    db = world["db"]
    shared = db.query(SharedCriteriaAttachment).all()
    assert len(shared) == 1                                  # ONE stored copy
    rows = db.query(CandidateStageResult).filter(CandidateStageResult.criteria_id == sc.id).all()
    assert len(rows) == 5
    assert {r.shared_attachment_id for r in rows} == {shared[0].id}
    assert all(r.attachment_object_key is None for r in rows)


def test_upload_does_not_set_pass_or_fail(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 4)]
    upload(client, sc, people)
    rows = world["db"].query(CandidateStageResult).all()
    assert {r.result for r in rows} == {"PENDING"}


def test_every_candidate_sees_the_shared_proof_on_their_own_record(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 4)]
    upload(client, sc, people, filename="batch-12.pdf")
    for c in people:
        status_row = client.get(DETAIL.format(c.id)).json()["criteria_status"][0]
        assert status_row["attachment_file_name"] == "batch-12.pdf"
        assert status_row["attachment_is_shared"] is True


def test_each_candidate_can_download_the_shared_proof(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 3)]
    upload(client, sc, people, content=b"the one report")
    for c in people:
        res = client.get(PROOF.format(c.id, sc.id))
        assert res.status_code == 200
        assert res.content == b"the one report"


def test_nothing_is_uploaded_if_any_candidate_is_ineligible(world, client):
    sc = make_criteria(world)
    ok = make_candidate(world, "C-1")
    bad = make_candidate(world, "C-2", designation=world["other_designation"])
    res = upload(client, sc, [ok, bad])
    assert res.status_code == 400
    assert "Nothing was uploaded" in res.json()["detail"]
    assert "C-2" in res.json()["detail"]
    db = world["db"]
    assert db.query(SharedCriteriaAttachment).count() == 0
    assert db.query(CandidateStageResult).count() == 0       # not even the eligible one


def test_a_repeated_candidate_id_is_attached_once(world, client):
    sc = make_criteria(world)
    c = make_candidate(world, "C-1")
    res = client.post(UPLOAD, data={"criteria_id": str(sc.id), "candidate_ids": f"{c.id},{c.id}"},
                      files={"file": ("r.pdf", io.BytesIO(b"x"), "application/pdf")})
    assert res.status_code == 200
    assert res.json()["attached_count"] == 1


def test_empty_file_is_refused(world, client):
    sc = make_criteria(world)
    c = make_candidate(world, "C-1")
    res = upload(client, sc, [c], content=b"")
    assert res.status_code == 400
    assert "empty" in res.json()["detail"]


def test_upload_refuses_a_candidate_outside_the_callers_cost_center_scope(world, client):
    """A bulk action that silently drops people gives no sign of who is
    missing from it, so one out-of-scope candidate refuses the batch."""
    db = world["db"]
    staff_role = db.query(Role).filter(Role.name == RoleName.HR_STAFF).first()
    db.add(User(username="staff", hashed_password="x", role_id=staff_role.id))
    db.commit()
    staff = db.query(User).filter(User.username == "staff").first()
    db.add(RolePermission(role_id=staff_role.id, permission_code=Permission.RECRUITMENT_MANAGE))
    db.add(UserCostCenterScope(user_id=staff.id, cost_center_id=world["north"].id))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: staff

    sc = make_criteria(world)
    mine = make_candidate(world, "C-1")
    theirs = make_candidate(world, "C-9", cost_center=world["south"])
    res = upload(client, sc, [mine, theirs])
    assert res.status_code == 400
    assert "C-9" in res.json()["detail"]
    assert db.query(SharedCriteriaAttachment).count() == 0


# --- removing it ---------------------------------------------------------

def test_removing_the_proof_from_one_candidate_leaves_the_others_intact(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 6)]
    upload(client, sc, people)

    res = client.delete(PROOF.format(people[0].id, sc.id))
    assert res.status_code == 200

    db = world["db"]
    assert db.query(SharedCriteriaAttachment).count() == 1    # file survives
    for c in people[1:]:
        assert client.get(PROOF.format(c.id, sc.id)).status_code == 200
    assert client.get(PROOF.format(people[0].id, sc.id)).status_code == 404


def test_the_stored_file_goes_only_when_the_last_reference_does(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 4)]
    upload(client, sc, people)
    object_key = world["db"].query(SharedCriteriaAttachment).first().object_key
    storage = get_storage()
    assert storage.exists(object_key)

    for c in people[:-1]:
        client.delete(PROOF.format(c.id, sc.id))
    assert storage.exists(object_key)                         # still referenced

    client.delete(PROOF.format(people[-1].id, sc.id))
    assert not storage.exists(object_key)
    assert world["db"].query(SharedCriteriaAttachment).count() == 0


def test_detaching_does_not_touch_the_recorded_result(world, client):
    sc = make_criteria(world)
    c = make_candidate(world, "C-1")
    upload(client, sc, [c])
    client.post(f"/api/v1/recruitment/candidates/{c.id}/stage-results",
                json={"criteria_id": sc.id, "result": "FAIL", "tested_on": "2026-04-01", "remarks": "retest"})
    client.delete(PROOF.format(c.id, sc.id))
    row = world["db"].query(CandidateStageResult).filter(CandidateStageResult.candidate_id == c.id).first()
    assert row.result == "FAIL"
    assert row.shared_attachment_id is None


# --- interaction with an individual upload -------------------------------

def test_an_individual_upload_supersedes_the_shared_one_for_that_candidate(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 4)]
    upload(client, sc, people)

    res = client.post(PROOF.format(people[0].id, sc.id),
                      files={"file": ("mine.pdf", io.BytesIO(b"only mine"), "application/pdf")})
    assert res.status_code == 200

    db = world["db"]
    row = db.query(CandidateStageResult).filter(CandidateStageResult.candidate_id == people[0].id).first()
    assert row.shared_attachment_id is None
    assert row.attachment_file_name == "mine.pdf"
    assert client.get(PROOF.format(people[0].id, sc.id)).content == b"only mine"
    # The other two are untouched and still share the batch report.
    assert db.query(SharedCriteriaAttachment).count() == 1
    assert client.get(PROOF.format(people[1].id, sc.id)).content == b"report pdf bytes"


def test_a_bulk_upload_replaces_an_individual_file(world, client):
    sc = make_criteria(world)
    c = make_candidate(world, "C-1")
    client.post(PROOF.format(c.id, sc.id), files={"file": ("mine.pdf", io.BytesIO(b"old"), "application/pdf")})
    db = world["db"]
    old_key = db.query(CandidateStageResult).first().attachment_object_key

    upload(client, sc, [c], content=b"the batch report")
    row = db.query(CandidateStageResult).filter(CandidateStageResult.candidate_id == c.id).first()
    assert row.attachment_object_key is None
    assert row.shared_attachment_id is not None
    assert not get_storage().exists(old_key)                  # superseded file cleaned up
    assert client.get(PROOF.format(c.id, sc.id)).content == b"the batch report"


def test_a_second_bulk_upload_releases_the_first(world, client):
    sc = make_criteria(world)
    people = [make_candidate(world, f"C-{i}") for i in range(1, 3)]
    upload(client, sc, people, content=b"first draft")
    upload(client, sc, people, content=b"corrected report")

    db = world["db"]
    assert db.query(SharedCriteriaAttachment).count() == 1    # the superseded one is gone
    for c in people:
        assert client.get(PROOF.format(c.id, sc.id)).content == b"corrected report"


# --- criteria that need no proof document at all -------------------------

CRITERIA = "/api/v1/recruitment/criteria"


def test_a_criteria_requires_a_proof_by_default(world, client):
    res = client.post(CRITERIA, json={"name": "Road Test"})
    assert res.status_code == 200, res.text
    assert res.json()["requires_attachment"] is True


def test_a_criteria_can_be_created_needing_no_proof(world, client):
    res = client.post(CRITERIA, json={"name": "Panel Interview", "requires_attachment": False})
    assert res.json()["requires_attachment"] is False


def test_existing_criteria_rows_still_count_as_requiring_a_proof(world, client):
    """migrate.py adds the column as NULL on rows that predate it, so NULL
    must read as "required" - every criteria behaved that way before the
    flag existed."""
    db = world["db"]
    db.add(SelectionCriteria(name="Legacy Test"))
    db.commit()
    legacy = db.query(SelectionCriteria).filter(SelectionCriteria.name == "Legacy Test").first()
    legacy.requires_attachment = None
    db.commit()
    row = next(c for c in client.get(CRITERIA).json() if c["name"] == "Legacy Test")
    assert row["requires_attachment"] is True


def test_no_proof_needed_clears_bulk_upload(world, client):
    """The bulk upload exists only to file a proof, so the combination is
    impossible rather than merely odd - the impossible half is cleared
    instead of the save being rejected."""
    res = client.post(CRITERIA, json={
        "name": "Panel Interview", "requires_attachment": False, "supports_bulk_upload": True,
    })
    assert res.json()["supports_bulk_upload"] is False
    assert client.get(BULK_LIST).json() == []


def test_turning_off_the_proof_requirement_also_turns_off_bulk_upload(world, client):
    sc = make_criteria(world, "Safety Training", bulk=True)
    res = client.put(f"{CRITERIA}/{sc.id}", json={
        "name": "Safety Training", "requires_attachment": False, "supports_bulk_upload": True, "is_active": True,
    })
    assert res.json()["requires_attachment"] is False
    assert res.json()["supports_bulk_upload"] is False


def test_criteria_status_carries_the_flag_to_the_candidate_page(world, client):
    db = world["db"]
    db.add(SelectionCriteria(name="Panel Interview", requires_attachment=False))
    db.commit()
    sc = db.query(SelectionCriteria).filter(SelectionCriteria.name == "Panel Interview").first()
    db.add(DesignationCriteria(designation_id=world["designation"].id, criteria_id=sc.id,
                               is_mandatory=True, sequence=1, is_active=True))
    db.commit()
    c = make_candidate(world, "C-1")
    row = client.get(DETAIL.format(c.id)).json()["criteria_status"][0]
    assert row["requires_attachment"] is False


def test_a_result_can_still_be_recorded_with_no_proof(world, client):
    db = world["db"]
    db.add(SelectionCriteria(name="Panel Interview", requires_attachment=False))
    db.commit()
    sc = db.query(SelectionCriteria).filter(SelectionCriteria.name == "Panel Interview").first()
    db.add(DesignationCriteria(designation_id=world["designation"].id, criteria_id=sc.id,
                               is_mandatory=True, sequence=1, is_active=True))
    db.commit()
    c = make_candidate(world, "C-1")
    res = client.post(f"/api/v1/recruitment/candidates/{c.id}/stage-results",
                      json={"criteria_id": sc.id, "result": "PASS", "tested_on": "2026-04-01", "remarks": None})
    assert res.status_code == 200
    assert res.json()["criteria_status"][0]["result"] == "PASS"


def test_a_proof_may_still_be_attached_when_none_is_required(world, client):
    """The flag stops the UI asking; it never blocks a document that does
    turn up."""
    db = world["db"]
    db.add(SelectionCriteria(name="Panel Interview", requires_attachment=False))
    db.commit()
    sc = db.query(SelectionCriteria).filter(SelectionCriteria.name == "Panel Interview").first()
    db.add(DesignationCriteria(designation_id=world["designation"].id, criteria_id=sc.id,
                               is_mandatory=True, sequence=1, is_active=True))
    db.commit()
    c = make_candidate(world, "C-1")
    res = client.post(PROOF.format(c.id, sc.id),
                      files={"file": ("notes.pdf", io.BytesIO(b"interview notes"), "application/pdf")})
    assert res.status_code == 200
    assert client.get(PROOF.format(c.id, sc.id)).content == b"interview notes"
