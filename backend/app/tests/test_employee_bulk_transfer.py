"""Bulk employee transfer: the all-or-nothing contract and per-person numbers.

A Cost Center transfer is not an edit - each employee gets an exit on their
current record and a draft record in the destination. Bulk only saves opening
that dialog once per person, so these tests check that doing twenty at once
still produces exactly what doing one at a time would, and that a selection
containing anything unmovable moves nobody.
"""
from datetime import date, timedelta

import pytest

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import EpisodeStatus, Permission, RoleName
from app.models.models import (
    Company, CostCenter, Department, Employee, EmployeeTransfer, EmploymentEpisode, OrgAssignment,
    Project, Role, RolePermission, SeparationRecord, User,
)

URL = "/api/v1/employees-transfer"
PREFLIGHT = "/api/v1/employees-transfer-preflight"
JOINED = date(2024, 1, 1)
MOVE_ON = date(2026, 4, 1)


@pytest.fixture()
def world(db):
    """Two Cost Centers, each with a Project, one shared Department, and an
    HR_ADMIN signed in."""
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add_all([CostCenter(company_id=company.id, name="North", code="CC-N"),
                CostCenter(company_id=company.id, name="South", code="CC-S")])
    db.add(Department(name="Operations", code="DEPT-OPS"))
    db.add(Role(name=RoleName.HR_ADMIN))
    db.commit()
    north, south = db.query(CostCenter).order_by(CostCenter.id).all()
    db.add_all([Project(cost_center_id=north.id, name="North Ops", code="P-N"),
                Project(cost_center_id=south.id, name="South Ops", code="P-S")])
    db.commit()
    p_north, p_south = db.query(Project).order_by(Project.id).all()
    db.add(User(username="hr", hashed_password="x", role_id=db.query(Role).first().id))
    db.commit()
    user = db.query(User).first()
    # The JWT plumbing is not what these tests are about, so the signed-in
    # user is injected directly - every other dependency still runs for real.
    app.dependency_overrides[get_current_user] = lambda: user
    yield {"db": db, "north": north, "south": south, "p_north": p_north, "p_south": p_south,
           "dept": db.query(Department).first(), "user": user}
    app.dependency_overrides.clear()


def employee(world, number, cost_center=None, project=None, status=EpisodeStatus.ACTIVE, joined=JOINED):
    db = world["db"]
    cost_center = cost_center or world["north"]
    project = project or world["p_north"]
    db.add(Employee(first_name=number, last_name="Person"))
    db.commit()
    person = db.query(Employee).filter(Employee.first_name == number).first()
    db.add(EmploymentEpisode(employee_id=person.id, employee_number=number, status=status, date_of_joining=joined))
    db.commit()
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == number).first()
    db.add(OrgAssignment(episode_id=episode.id, cost_center_id=cost_center.id, project_id=project.id,
                         department_id=world["dept"].id, effective_from=joined))
    db.commit()
    return episode


def destination(world, employees, **over):
    body = {"transfer_type": "INTERNAL", "cost_center_id": world["south"].id,
            "project_id": world["p_south"].id, "department_id": world["dept"].id,
            "transfer_date": MOVE_ON.isoformat(), "remarks": "depot reshuffle",
            "employees": employees}
    body.update(over)
    return body


def test_a_selection_moves_together(client, world):
    db = world["db"]
    episodes = [employee(world, f"N-{n}") for n in (1, 2, 3)]
    picked = [{"episode_id": e.id, "employee_number": f"S-{n}"} for n, e in enumerate(episodes, start=1)]

    r = client.post(URL, json=destination(world, picked))
    assert r.status_code == 200, r.text
    assert r.json()["transferred"] == 3
    assert [e["new_employee_number"] for e in r.json()["employees"]] == ["S-1", "S-2", "S-3"]

    for old in episodes:
        db.refresh(old)
        assert old.status == EpisodeStatus.NOTICE_PERIOD              # exit started
        assert old.separation_date == MOVE_ON - timedelta(days=1)
    # One new draft record per person, in the destination, same person.
    assert db.query(EmployeeTransfer).count() == 3
    for t in db.query(EmployeeTransfer).all():
        assert t.status == "INITIATED" and t.to_cost_center_id == world["south"].id
        new = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == t.to_episode_id).first()
        assert new.status == EpisodeStatus.DRAFT
        assert new.employee_id == db.query(EmploymentEpisode).filter(
            EmploymentEpisode.id == t.from_episode_id).first().employee_id
        assert new.service_start_date == JOINED                       # INTERNAL keeps continuity


def test_a_resignation_type_batch_keeps_no_continuity(client, world):
    db = world["db"]
    e = employee(world, "N-1")
    r = client.post(URL, json=destination(
        world, [{"episode_id": e.id, "employee_number": "S-1"}], transfer_type="RESIGNATION"))
    assert r.status_code == 200, r.text
    new_id = r.json()["employees"][0]["new_episode_id"]
    assert db.query(EmploymentEpisode).filter(EmploymentEpisode.id == new_id).first().service_start_date is None
    record = db.query(SeparationRecord).filter(SeparationRecord.episode_id == e.id).first()
    assert record.full_final_status == "PENDING"                      # a real exit, settlement due


@pytest.mark.parametrize("bad_status", [EpisodeStatus.DRAFT, EpisodeStatus.SEPARATED, EpisodeStatus.NOTICE_PERIOD])
def test_one_unmovable_employee_refuses_the_whole_batch(client, world, bad_status):
    db = world["db"]
    good = employee(world, "N-1")
    bad = employee(world, "N-2", status=bad_status)

    r = client.post(URL, json=destination(world, [
        {"episode_id": good.id, "employee_number": "S-1"},
        {"episode_id": bad.id, "employee_number": "S-2"}]))
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "Nothing was transferred" in detail and "1 of 2" in detail and "N-2" in detail

    db.refresh(good)
    assert good.status == EpisodeStatus.ACTIVE                        # the good one stayed put
    assert db.query(EmployeeTransfer).count() == 0


def test_a_missing_number_refuses_the_batch(client, world):
    """A Cost Center they never served needs a number - it cannot be guessed."""
    db = world["db"]
    good = employee(world, "N-1")
    nameless = employee(world, "N-2")

    r = client.post(URL, json=destination(world, [
        {"episode_id": good.id, "employee_number": "S-1"},
        {"episode_id": nameless.id}]))
    assert r.status_code == 400
    assert "new Employee Number is required" in r.json()["detail"]
    assert db.query(EmployeeTransfer).count() == 0


def test_the_same_number_cannot_be_given_to_two_people_in_one_batch(client, world):
    a = employee(world, "N-1")
    b = employee(world, "N-2")
    r = client.post(URL, json=destination(world, [
        {"episode_id": a.id, "employee_number": "S-1"},
        {"episode_id": b.id, "employee_number": "S-1"}]))
    assert r.status_code == 400
    assert "also given to" in r.json()["detail"]


def test_a_number_already_in_use_refuses_the_batch(client, world):
    employee(world, "S-9", cost_center=world["south"], project=world["p_south"])
    mover = employee(world, "N-1")
    r = client.post(URL, json=destination(world, [{"episode_id": mover.id, "employee_number": "S-9"}]))
    assert r.status_code == 400
    assert "already in use" in r.json()["detail"]


def test_an_employee_already_in_the_destination_is_reported(client, world):
    there = employee(world, "S-1", cost_center=world["south"], project=world["p_south"])
    r = client.post(URL, json=destination(world, [{"episode_id": there.id, "employee_number": "S-2"}]))
    assert r.status_code == 400
    assert "already in this Cost Center" in r.json()["detail"]


def test_a_missing_id_refuses_the_batch(client, world):
    db = world["db"]
    good = employee(world, "N-1")
    r = client.post(URL, json=destination(world, [
        {"episode_id": good.id, "employee_number": "S-1"},
        {"episode_id": 9999, "employee_number": "S-2"}]))
    assert r.status_code == 400
    assert "employee record not found" in r.json()["detail"]
    db.refresh(good)
    assert good.status == EpisodeStatus.ACTIVE


def test_the_project_must_belong_to_the_destination_cost_center(client, world):
    e = employee(world, "N-1")
    r = client.post(URL, json=destination(
        world, [{"episode_id": e.id, "employee_number": "S-1"}], project_id=world["p_north"].id))
    assert r.status_code == 400
    assert "Project does not belong" in r.json()["detail"]


def test_a_transfer_date_on_or_before_the_joining_date_is_refused(client, world):
    e = employee(world, "N-1", joined=date(2026, 6, 1))
    r = client.post(URL, json=destination(world, [{"episode_id": e.id, "employee_number": "S-1"}]))
    assert r.status_code == 400
    assert "must be after this employee's joining date" in r.json()["detail"]


def test_an_employee_mid_transfer_cannot_be_put_in_another_batch(client, world):
    """Transferring starts an exit, so the record is no longer Active and a
    second batch cannot pick it up and open a second destination record."""
    db = world["db"]
    e = employee(world, "N-1")
    first = client.post(URL, json=destination(world, [{"episode_id": e.id, "employee_number": "S-1"}]))
    assert first.status_code == 200, first.text
    again = client.post(URL, json=destination(world, [{"episode_id": e.id, "employee_number": "S-2"}]))
    assert again.status_code == 400
    assert "only an Active employee can be transferred" in again.json()["detail"]
    assert db.query(EmployeeTransfer).count() == 1          # still just the one


def test_a_second_stint_cannot_be_transferred_while_the_first_one_is_moving(client, world):
    """The in-progress guard is per person, not per record - someone already
    mid-transfer cannot be moved again from another Active record."""
    db = world["db"]
    moving = employee(world, "N-1")
    assert client.post(URL, json=destination(
        world, [{"episode_id": moving.id, "employee_number": "S-1"}])).status_code == 200
    # A second Active record for the same person, in the source Cost Center.
    db.add(EmploymentEpisode(employee_id=moving.employee_id, employee_number="N-1B",
                             status=EpisodeStatus.ACTIVE, date_of_joining=JOINED))
    db.commit()
    other = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == "N-1B").first()
    db.add(OrgAssignment(episode_id=other.id, cost_center_id=world["north"].id, project_id=world["p_north"].id,
                         department_id=world["dept"].id, effective_from=JOINED))
    db.commit()

    r = client.post(URL, json=destination(world, [{"episode_id": other.id, "employee_number": "S-2"}]))
    assert r.status_code == 400
    assert "already in progress" in r.json()["detail"]


def test_an_empty_selection_is_rejected(client, world):
    assert client.post(URL, json=destination(world, [])).status_code == 422


def test_a_repeated_id_counts_once(client, world):
    e = employee(world, "N-1")
    r = client.post(URL, json=destination(world, [
        {"episode_id": e.id, "employee_number": "S-1"},
        {"episode_id": e.id, "employee_number": "S-1"}]))
    assert r.status_code == 200, r.text
    assert r.json()["transferred"] == 1


def test_preflight_says_who_needs_a_number_and_who_cannot_move(client, world):
    fresh = employee(world, "N-1")
    stuck = employee(world, "N-2", status=EpisodeStatus.DRAFT)

    r = client.get(PREFLIGHT, params={
        "cost_center_id": world["south"].id, "transfer_date": MOVE_ON.isoformat(),
        "episode_ids": f"{fresh.id},{stuck.id}"})
    assert r.status_code == 200, r.text
    by_id = {row["episode_id"]: row for row in r.json()["employees"]}
    assert r.json()["blocked"] == 1

    assert by_id[fresh.id]["needs_new_number"] is True
    assert by_id[fresh.id]["destination_employee_number"] is None
    assert by_id[fresh.id]["blocked_reason"] is None
    assert by_id[fresh.id]["from_cost_center"] == "North"

    assert by_id[stuck.id]["needs_new_number"] is False
    assert "Active" in by_id[stuck.id]["blocked_reason"] or "DRAFT" in by_id[stuck.id]["blocked_reason"]


def test_preflight_offers_back_the_number_someone_already_holds_there(client, world):
    """Served the destination before - the old number comes back, and no new
    one is needed (or accepted) for them."""
    db = world["db"]
    returning = employee(world, "N-1")
    # A separated earlier stint of the same person, in the destination.
    db.add(EmploymentEpisode(employee_id=returning.employee_id, employee_number="S-OLD",
                             status=EpisodeStatus.SEPARATED, date_of_joining=date(2020, 1, 1)))
    db.commit()
    old = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == "S-OLD").first()
    db.add(OrgAssignment(episode_id=old.id, cost_center_id=world["south"].id, project_id=world["p_south"].id,
                         department_id=world["dept"].id, effective_from=date(2020, 1, 1)))
    db.commit()

    r = client.get(PREFLIGHT, params={
        "cost_center_id": world["south"].id, "transfer_date": MOVE_ON.isoformat(),
        "episode_ids": str(returning.id)})
    row = r.json()["employees"][0]
    assert row["destination_employee_number"] == "S-OLD" and row["needs_new_number"] is False

    # And the transfer itself reuses it, ignoring anything typed in.
    moved = client.post(URL, json=destination(world, [{"episode_id": returning.id, "employee_number": "IGNORED"}]))
    assert moved.status_code == 200, moved.text
    assert moved.json()["employees"][0]["new_employee_number"] == "S-OLD"


def test_the_destination_cost_center_must_be_in_scope(client, world):
    """Scoping is not bypassed in bulk: a non-admin needs BOTH Cost Centers."""
    db = world["db"]
    db.add(Role(name=RoleName.HR_STAFF))
    db.commit()
    staff_role = db.query(Role).filter(Role.name == RoleName.HR_STAFF).first()
    db.add(RolePermission(role_id=staff_role.id, permission_code=Permission.EMPLOYEE_SEPARATE))
    db.add(User(username="staff", hashed_password="x", role_id=staff_role.id))
    db.commit()
    staff = db.query(User).filter(User.username == "staff").first()
    e = employee(world, "N-1")
    app.dependency_overrides[get_current_user] = lambda: staff

    # Scope the staff user to the source Cost Center only - a non-admin
    # with no UserCostCenterScope row has an empty allow-list (sees
    # nothing), so the scope has to be given explicitly for the request to
    # get far enough to be refused on the DESTINATION Cost Center.
    from app.models.models import UserCostCenterScope
    db.add(UserCostCenterScope(user_id=staff.id, cost_center_id=world["north"].id))
    db.commit()

    r = client.post(URL, json=destination(world, [{"episode_id": e.id, "employee_number": "S-1"}]))
    assert r.status_code == 403
    assert "destination Cost Center" in r.json()["detail"]
    assert db.query(EmployeeTransfer).count() == 0
