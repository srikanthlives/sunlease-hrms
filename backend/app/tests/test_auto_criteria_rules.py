"""Automatic selection criteria: a rule over one of the candidate's own date
fields decides PASS/FAIL instead of a person.

Two things carry most of the risk and most of the tests: the calendar
arithmetic (an age cap must flip on the birthday itself, not a day either
side of it), and the re-evaluation rules - a stored verdict is owned by the
rule and refreshed when the data behind it changes, EXCEPT where a human has
waived it.
"""
import datetime as dt

import pytest

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import CandidateStatus, RoleName
from app.models.models import (
    Candidate, CandidateStageResult, Company, CostCenter, Department, Designation, DesignationCriteria,
    EmployeeCategory, Project, Role, SelectionCriteria, User,
)
from app.services import criteria_rule_service as rules

CRITERIA = "/api/v1/recruitment/criteria"
DETAIL = "/api/v1/recruitment/candidates/{}"
RESULTS = "/api/v1/recruitment/candidates/{}/stage-results"
CANDIDATES = "/api/v1/recruitment/candidates"

TODAY = dt.date.today()


def years_ago(n, extra_days=0):
    try:
        base = TODAY.replace(year=TODAY.year - n)
    except ValueError:                      # 29 Feb
        base = TODAY.replace(year=TODAY.year - n, day=28)
    return base - dt.timedelta(days=extra_days)


@pytest.fixture()
def world(db):
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add(CostCenter(company_id=company.id, name="North", code="CC-N"))
    db.add_all([Designation(name="Coach Captain"), EmployeeCategory(name="Operations Staff"),
                Department(name="Operations", code="D-OPS")])
    db.add_all([Role(name=RoleName.HR_ADMIN)])
    db.commit()
    north = db.query(CostCenter).first()
    db.add(Project(cost_center_id=north.id, name="North Ops", code="P-N"))
    db.commit()
    admin_role = db.query(Role).filter(Role.name == RoleName.HR_ADMIN).first()
    db.add(User(username="admin", hashed_password="x", role_id=admin_role.id))
    db.commit()
    admin = db.query(User).filter(User.username == "admin").first()
    app.dependency_overrides[get_current_user] = lambda: admin
    yield {"db": db, "admin": admin, "north": north, "project": db.query(Project).first(),
           "designation": db.query(Designation).first(), "category": db.query(EmployeeCategory).first()}
    app.dependency_overrides.clear()


def auto_criteria(world, name="Age Limit", field="date_of_birth", measure="SINCE",
                  operator="<", value=55, unit="YEARS", mandatory=True):
    db = world["db"]
    db.add(SelectionCriteria(name=name, auto_field=field, auto_measure=measure,
                             auto_operator=operator, auto_value=value, auto_unit=unit,
                             requires_attachment=False))
    db.commit()
    sc = db.query(SelectionCriteria).filter(SelectionCriteria.name == name).first()
    db.add(DesignationCriteria(designation_id=world["designation"].id, criteria_id=sc.id,
                               is_mandatory=mandatory, sequence=1, is_active=True))
    db.commit()
    return sc


def make_candidate(world, client, reference="C-1", **fields):
    payload = {
        "first_name": "Devi", "last_name": "Candidate",
        "applied_designation_id": world["designation"].id,
        "applied_employee_category_id": world["category"].id,
        "applied_cost_center_id": world["north"].id,
        "applied_project_id": world["project"].id,
    }
    payload.update({k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in fields.items()})
    res = client.post(CANDIDATES, json=payload)
    assert res.status_code == 200, res.text
    return world["db"].query(Candidate).filter(Candidate.id == res.json()["id"]).first()


def status_row(client, candidate, index=0):
    return client.get(DETAIL.format(candidate.id)).json()["criteria_status"][index]


# --- the calendar arithmetic --------------------------------------------

def test_age_is_exact_on_the_birthday():
    assert rules.duration_between(dt.date(1971, 1, 1), dt.date(2026, 1, 1), "YEARS") == 55.0


def test_age_is_just_under_the_day_before_the_birthday():
    value = rules.duration_between(dt.date(1971, 1, 1), dt.date(2025, 12, 31), "YEARS")
    assert 54.9 < value < 55.0


def test_a_past_date_measured_forward_is_negative():
    assert rules.duration_between(dt.date(2026, 1, 1), dt.date(2025, 12, 1), "MONTHS") == -1.0


def test_month_end_is_clamped_not_overflowed():
    # 31 Jan + 1 month is 28/29 Feb, not 2/3 March.
    assert rules._add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)


def test_a_leap_day_birthday_falls_on_28_feb_in_a_common_year():
    """Falls out of the same month-end clamp as "31 Jan + 1 month = 28 Feb",
    and matches the usual convention that someone born on 29 Feb has their
    birthday on the 28th in a non-leap year rather than on 1 March."""
    assert rules.duration_between(dt.date(2024, 2, 29), dt.date(2025, 2, 28), "YEARS") == 1.0
    assert rules.duration_between(dt.date(2024, 2, 29), dt.date(2025, 2, 27), "YEARS") < 1.0


# --- the three rules the user actually asked for -------------------------

def test_age_under_55_passes_a_younger_candidate(world, client):
    auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(40))
    assert status_row(client, c)["result"] == "PASS"


def test_age_under_55_fails_an_older_candidate(world, client):
    auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(56))
    row = status_row(client, c)
    assert row["result"] == "FAIL"
    assert "Date of Birth" in row["auto_reason"]
    assert "less than 55 years" in row["auto_reason"]


def test_a_licence_three_years_old_passes(world, client):
    auto_criteria(world, "Licence Seasoning", field="dl_issue_date", operator=">=", value=3)
    c = make_candidate(world, client, dl_issue_date=years_ago(4))
    assert status_row(client, c)["result"] == "PASS"


def test_a_licence_younger_than_three_years_fails(world, client):
    auto_criteria(world, "Licence Seasoning", field="dl_issue_date", operator=">=", value=3)
    c = make_candidate(world, client, dl_issue_date=years_ago(2))
    assert status_row(client, c)["result"] == "FAIL"


def test_an_unexpired_licence_passes(world, client):
    auto_criteria(world, "Licence Valid", field="dl_expiry_date", measure="UNTIL",
                  operator=">=", value=0, unit="DAYS")
    c = make_candidate(world, client, dl_expiry_date=TODAY + dt.timedelta(days=30))
    assert status_row(client, c)["result"] == "PASS"


def test_an_expired_licence_fails_and_says_so(world, client):
    auto_criteria(world, "Licence Valid", field="dl_expiry_date", measure="UNTIL",
                  operator=">=", value=0, unit="DAYS")
    c = make_candidate(world, client, dl_expiry_date=TODAY - dt.timedelta(days=10))
    row = status_row(client, c)
    assert row["result"] == "FAIL"
    assert "passed" in row["auto_reason"]


def test_a_licence_expiring_too_soon_fails_a_six_month_rule(world, client):
    auto_criteria(world, "Licence Validity", field="dl_expiry_date", measure="UNTIL",
                  operator=">=", value=6, unit="MONTHS")
    c = make_candidate(world, client, dl_expiry_date=TODAY + dt.timedelta(days=60))
    assert status_row(client, c)["result"] == "FAIL"


# --- missing data --------------------------------------------------------

def test_a_blank_date_is_pending_not_pass_or_fail(world, client):
    auto_criteria(world)
    c = make_candidate(world, client)                 # no date_of_birth
    row = status_row(client, c)
    assert row["result"] == "PENDING"
    assert "not recorded" in row["auto_reason"]


def test_a_blank_date_blocks_conversion(world, client):
    auto_criteria(world)
    c = make_candidate(world, client)
    c.status = CandidateStatus.APPROVED
    world["db"].commit()
    res = client.post(f"/api/v1/recruitment/candidates/{c.id}/convert", json={
        "employee_number": "EMP-1", "date_of_joining": "2026-04-01", "employment_type_id": None,
        "employee_category_id": world["category"].id, "work_location_id": None, "confirmation_date": None,
    })
    assert res.status_code == 400
    assert "mandatory selection criteria" in res.json()["detail"]


# --- re-evaluation -------------------------------------------------------

def test_editing_the_candidate_re_evaluates_the_rule(world, client):
    auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(56))
    assert status_row(client, c)["result"] == "FAIL"

    detail = client.get(DETAIL.format(c.id)).json()
    client.put(f"{CANDIDATES}/{c.id}", json={
        "first_name": "Devi", "last_name": "Candidate",
        "date_of_birth": years_ago(40).isoformat(),
        "applied_designation_id": world["designation"].id,
        "applied_employee_category_id": world["category"].id,
        "applied_cost_center_id": world["north"].id,
        "applied_project_id": world["project"].id,
    })
    assert status_row(client, c)["result"] == "PASS"
    assert detail["criteria_status"][0]["result"] == "FAIL"     # it really did change


def test_editing_the_rule_re_evaluates_affected_candidates(world, client):
    sc = auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(56))
    assert status_row(client, c)["result"] == "FAIL"

    res = client.put(f"{CRITERIA}/{sc.id}", json={
        "name": "Age Limit", "requires_attachment": False, "is_active": True,
        "auto_field": "date_of_birth", "auto_measure": "SINCE",
        "auto_operator": "<", "auto_value": 60, "auto_unit": "YEARS",
    })
    assert res.json()["reevaluated_candidates"] == 1
    assert status_row(client, c)["result"] == "PASS"


def test_a_converted_candidate_is_not_rewritten_by_a_later_rule_change(world, client):
    sc = auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(40))
    c.status = CandidateStatus.CONVERTED
    world["db"].commit()
    res = client.put(f"{CRITERIA}/{sc.id}", json={
        "name": "Age Limit", "requires_attachment": False, "is_active": True,
        "auto_field": "date_of_birth", "auto_measure": "SINCE",
        "auto_operator": "<", "auto_value": 30, "auto_unit": "YEARS",
    })
    assert res.json()["reevaluated_candidates"] == 0
    row = world["db"].query(CandidateStageResult).filter(CandidateStageResult.candidate_id == c.id).first()
    assert row.result == "PASS"


def test_the_result_is_stored_not_merely_computed(world, client):
    auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(40))
    row = world["db"].query(CandidateStageResult).filter(CandidateStageResult.candidate_id == c.id).first()
    assert row is not None
    assert row.result == "PASS"
    assert row.is_auto is True
    assert row.auto_evaluated_at is not None


# --- who may overrule a rule ---------------------------------------------

def test_hr_cannot_hand_mark_an_automatic_criteria_pass(world, client):
    sc = auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(56))
    res = client.post(RESULTS.format(c.id), json={
        "criteria_id": sc.id, "result": "PASS", "tested_on": TODAY.isoformat(), "remarks": None,
    })
    assert res.status_code == 400
    assert "decided automatically" in res.json()["detail"]


def test_hr_can_still_waive_an_automatic_criteria_as_an_exception(world, client):
    sc = auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(56))
    c.status = CandidateStatus.APPROVED
    world["db"].commit()
    res = client.post(RESULTS.format(c.id), json={
        "criteria_id": sc.id, "result": "EXCEPTION", "tested_on": TODAY.isoformat(), "remarks": "board approved",
    })
    assert res.status_code == 200
    assert res.json()["criteria_status"][0]["result"] == "EXCEPTION"


def test_a_waiver_survives_the_next_re_evaluation(world, client):
    """Without this the rule would quietly undo HR's decision the next time
    anything touched the candidate."""
    sc = auto_criteria(world)
    c = make_candidate(world, client, date_of_birth=years_ago(56))
    c.status = CandidateStatus.APPROVED
    world["db"].commit()
    client.post(RESULTS.format(c.id), json={
        "criteria_id": sc.id, "result": "EXCEPTION", "tested_on": TODAY.isoformat(), "remarks": "board approved",
    })
    from app.services import recruitment_service
    recruitment_service.reevaluate_auto_criteria(world["db"], c, world["admin"])
    world["db"].commit()
    assert status_row(client, c)["result"] == "EXCEPTION"


# --- configuring a rule --------------------------------------------------

def test_a_rule_clears_the_proof_and_bulk_flags(world, client):
    """The candidate's own recorded data is the evidence - there is nothing
    to upload and nothing to share in bulk."""
    res = client.post(CRITERIA, json={
        "name": "Age Limit", "requires_attachment": True, "supports_bulk_upload": True,
        "auto_field": "date_of_birth", "auto_measure": "SINCE",
        "auto_operator": "<", "auto_value": 55, "auto_unit": "YEARS",
    })
    assert res.json()["requires_attachment"] is False
    assert res.json()["supports_bulk_upload"] is False


def test_a_criteria_with_no_field_stays_manual(world, client):
    res = client.post(CRITERIA, json={"name": "Road Test"})
    assert res.json()["is_auto"] is False
    assert res.json()["auto_rule"] is None


def test_a_half_filled_rule_is_rejected(world, client):
    res = client.post(CRITERIA, json={"name": "Age Limit", "auto_field": "date_of_birth"})
    assert res.status_code == 400


def test_an_unknown_field_is_rejected(world, client):
    res = client.post(CRITERIA, json={
        "name": "Nonsense", "auto_field": "favourite_colour", "auto_measure": "SINCE",
        "auto_operator": "<", "auto_value": 1, "auto_unit": "YEARS",
    })
    assert res.status_code == 400
    assert "Unknown field" in res.json()["detail"]


def test_leftover_rule_fields_are_cleared_when_the_field_is_removed(world, client):
    sc = auto_criteria(world)
    res = client.put(f"{CRITERIA}/{sc.id}", json={
        "name": "Age Limit", "is_active": True, "requires_attachment": True,
        "auto_field": None, "auto_measure": "SINCE", "auto_operator": "<",
        "auto_value": 55, "auto_unit": "YEARS",
    })
    assert res.json()["is_auto"] is False
    assert res.json()["auto_operator"] is None


def test_the_rule_reads_back_as_a_sentence(world, client):
    sc = auto_criteria(world)
    row = next(c for c in client.get(CRITERIA).json() if c["id"] == sc.id)
    assert row["auto_rule"] == "Time since Date of Birth must be less than 55 years"


def test_the_options_catalog_is_served(world, client):
    data = client.get("/api/v1/recruitment/criteria-rule-options").json()
    assert any(f["value"] == "dl_expiry_date" for f in data["fields"])
    assert {m["value"] for m in data["measures"]} == {"SINCE", "UNTIL"}
