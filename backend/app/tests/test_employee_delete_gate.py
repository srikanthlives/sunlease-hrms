"""Deleting an employee record is HR_ADMIN/SUPER_ADMIN only.

It used to share the `employee.create` permission with HR_STAFF. Deleting a
person is irreversible and leaves nothing behind to review, so it is not
day-to-day data entry - HR_STAFF abandoning a draft leaves it as a DRAFT for
an admin to clear.
"""
from datetime import date

import pytest

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import EpisodeStatus, Permission, RoleName
from app.models.models import (
    Company, CostCenter, Department, Employee, EmploymentEpisode, OrgAssignment, Role, RolePermission,
    User, UserCostCenterScope,
)


@pytest.fixture()
def world(db):
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add(CostCenter(company_id=company.id, name="North", code="CC-N"))
    db.add(Department(name="Operations", code="D-OPS"))
    for name in (RoleName.HR_ADMIN, RoleName.SUPER_ADMIN, RoleName.HR_STAFF, RoleName.APPROVER):
        db.add(Role(name=name))
    db.commit()
    yield {"db": db, "north": db.query(CostCenter).first(), "dept": db.query(Department).first()}
    app.dependency_overrides.clear()


def sign_in(world, role_name, *permissions):
    db = world["db"]
    role = db.query(Role).filter(Role.name == role_name).first()
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    for code in permissions:
        db.add(RolePermission(role_id=role.id, permission_code=code))
    username = f"user-{role_name}"
    if not db.query(User).filter(User.username == username).first():
        db.add(User(username=username, hashed_password="x", role_id=role.id))
    db.commit()
    user = db.query(User).filter(User.username == username).first()
    db.query(UserCostCenterScope).filter(UserCostCenterScope.user_id == user.id).delete()
    db.add(UserCostCenterScope(user_id=user.id, cost_center_id=world["north"].id))
    db.commit()
    # The JWT plumbing is not what these tests are about, so the signed-in
    # user is injected directly - every other dependency still runs for real.
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def draft(world, number="DRAFT-1", status=EpisodeStatus.DRAFT):
    db = world["db"]
    db.add(Employee(first_name=number, last_name="Person"))
    db.commit()
    person = db.query(Employee).filter(Employee.first_name == number).first()
    db.add(EmploymentEpisode(employee_id=person.id, employee_number=number, status=status))
    db.commit()
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == number).first()
    db.add(OrgAssignment(episode_id=episode.id, cost_center_id=world["north"].id,
                         department_id=world["dept"].id, effective_from=date(2024, 1, 1)))
    db.commit()
    return episode


def url(episode):
    return f"/api/v1/employees/{episode.id}"


@pytest.mark.parametrize("role", [RoleName.HR_ADMIN, RoleName.SUPER_ADMIN])
def test_an_admin_can_delete_a_draft(client, world, role):
    episode = draft(world)
    sign_in(world, role)
    assert client.delete(url(episode)).status_code == 200
    assert world["db"].query(EmploymentEpisode).count() == 0


def test_hr_staff_cannot_delete_a_draft_even_with_employee_create(client, world):
    """employee.create is exactly the permission this used to be gated on."""
    episode = draft(world)
    sign_in(world, RoleName.HR_STAFF, Permission.EMPLOYEE_CREATE, Permission.EMPLOYEE_EDIT,
            Permission.EMPLOYEE_VIEW, Permission.EMPLOYEE_SEPARATE)

    r = client.delete(url(episode))
    assert r.status_code == 403, r.text
    assert world["db"].query(EmploymentEpisode).count() == 1       # still there


def test_an_approver_cannot_delete_a_draft(client, world):
    episode = draft(world)
    sign_in(world, RoleName.APPROVER, Permission.EMPLOYEE_VIEW, Permission.EMPLOYEE_APPROVE)
    assert client.delete(url(episode)).status_code == 403
    assert world["db"].query(EmploymentEpisode).count() == 1


@pytest.mark.parametrize("status", [EpisodeStatus.ACTIVE, EpisodeStatus.PENDING_APPROVAL,
                                    EpisodeStatus.SEPARATED, EpisodeStatus.NOTICE_PERIOD])
def test_even_an_admin_cannot_delete_anything_but_a_draft(client, world, status):
    """The DRAFT-only rule is unchanged - the role gate narrowed on top of
    it, it did not replace it."""
    episode = draft(world, number=f"E-{status}", status=status)
    sign_in(world, RoleName.HR_ADMIN)

    r = client.delete(url(episode))
    assert r.status_code == 400, r.text
    assert "Only DRAFT employees can be deleted" in r.json()["detail"]
    assert world["db"].query(EmploymentEpisode).count() == 1
