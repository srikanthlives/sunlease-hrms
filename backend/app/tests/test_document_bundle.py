"""Bulk document download: one merged PDF per person, zipped for several.

The documents here are real files written through the real storage backend
(conftest points HRMS_UPLOAD_DIR at a temp directory), so the image-to-PDF
conversion and the zip packaging are exercised rather than mocked.
"""
import io
import zipfile
from datetime import date

import pytest
from PIL import Image

from app.core.deps import get_current_user
from app.main import app
from app.models.enums import Permission, RoleName
from app.models.models import (
    Candidate, CandidateDocument, Company, CostCenter, Designation, DocumentMeta, DocumentType,
    Department, Employee, EmployeeCategory, EmploymentEpisode, OrgAssignment, Role, RolePermission, User,
)
from app.services import document_bundle_service
from app.services.storage import get_storage

PREFLIGHT = "/api/v1/exports/documents/preflight"
DOWNLOAD = "/api/v1/exports/documents/download"


@pytest.fixture()
def world(db):
    db.add(Company(name="Sunlease"))
    db.commit()
    company = db.query(Company).first()
    db.add_all([CostCenter(company_id=company.id, name="North", code="CC-N"),
                CostCenter(company_id=company.id, name="South", code="CC-S")])
    db.add_all([Designation(name="Coach Captain"), EmployeeCategory(name="Operations Staff"),
                Department(name="Operations", code="D-OPS")])
    db.add_all([DocumentType(name="Aadhaar"), DocumentType(name="PAN"), DocumentType(name="Photo")])
    db.add_all([Role(name=RoleName.HR_ADMIN), Role(name=RoleName.HR_STAFF)])
    db.commit()
    north, south = db.query(CostCenter).order_by(CostCenter.id).all()
    admin_role = db.query(Role).filter(Role.name == RoleName.HR_ADMIN).first()
    db.add(User(username="admin", hashed_password="x", role_id=admin_role.id))
    db.commit()
    admin = db.query(User).filter(User.username == "admin").first()
    aadhaar, pan, photo = db.query(DocumentType).order_by(DocumentType.id).all()
    # The JWT plumbing is not what these tests are about, so the signed-in
    # user is injected directly - every other dependency still runs for real.
    app.dependency_overrides[get_current_user] = lambda: admin
    yield {"db": db, "north": north, "south": south, "admin": admin, "dept": db.query(Department).first(),
           "aadhaar": aadhaar, "pan": pan, "photo": photo}
    app.dependency_overrides.clear()


def png_bytes(colour=(200, 30, 30), size=(60, 40), mode="RGB"):
    buffer = io.BytesIO()
    Image.new(mode, size, colour if mode == "RGB" else (*colour, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def employee(world, number, first, cost_center=None):
    db = world["db"]
    db.add(Employee(first_name=first, last_name="Person"))
    db.commit()
    person = db.query(Employee).filter(Employee.first_name == first).first()
    db.add(EmploymentEpisode(employee_id=person.id, employee_number=number, status="ACTIVE",
                             designation_id=db.query(Designation).first().id))
    db.commit()
    episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.employee_number == number).first()
    db.add(OrgAssignment(episode_id=episode.id, cost_center_id=(cost_center or world["north"]).id,
                         department_id=world["dept"].id, effective_from=date(2024, 1, 1)))
    db.commit()
    return episode


def candidate(world, reference, first):
    db = world["db"]
    db.add(Candidate(reference_number=reference, first_name=first, last_name="Candidate", status="APPLIED",
                     applied_cost_center_id=world["north"].id,
                     applied_designation_id=db.query(Designation).first().id,
                     applied_employee_category_id=db.query(EmployeeCategory).first().id))
    db.commit()
    return db.query(Candidate).filter(Candidate.reference_number == reference).first()


def attach(world, owner, document_type, content, file_name="scan.png", mime="image/png"):
    """Writes a real file through the storage backend and records it."""
    db = world["db"]
    is_candidate = isinstance(owner, Candidate)
    key = f"test/{'cand' if is_candidate else 'emp'}-{owner.id}-{document_type.id}-{file_name}"
    get_storage().save(key, content)
    row = (CandidateDocument(candidate_id=owner.id) if is_candidate else DocumentMeta(episode_id=owner.id))
    row.document_type_id = document_type.id
    row.document_type = document_type.name
    row.file_name = file_name
    row.object_key = key
    row.mime_type = mime
    row.file_size = len(content)
    db.add(row)
    db.commit()
    return row


def staff_user(world, *permissions, cost_centers=("north",)):
    """A non-admin with exactly the permissions named - admins bypass every
    check, so they can't demonstrate a gate. A non-admin with NO
    UserCostCenterScope row has an empty allow-list and sees nothing, so the
    scope is always given explicitly."""
    from app.models.models import UserCostCenterScope
    db = world["db"]
    role = db.query(Role).filter(Role.name == RoleName.HR_STAFF).first()
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete()
    for code in permissions:
        db.add(RolePermission(role_id=role.id, permission_code=code))
    if not db.query(User).filter(User.username == "staff").first():
        db.add(User(username="staff", hashed_password="x", role_id=role.id))
    db.commit()
    user = db.query(User).filter(User.username == "staff").first()
    db.query(UserCostCenterScope).filter(UserCostCenterScope.user_id == user.id).delete()
    for name in cost_centers:
        db.add(UserCostCenterScope(user_id=user.id, cost_center_id=world[name].id))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def pdf_page_count(content: bytes) -> int:
    """Counts pages without a PDF library - every page object declares
    itself in the file. Enough to prove a merge happened."""
    assert content.startswith(b"%PDF-"), content[:20]
    return content.count(b"/Type /Page") - content.count(b"/Type /Pages")


# --- preflight -------------------------------------------------------------

def test_preflight_offers_only_types_someone_actually_has(client, world):
    a = employee(world, "N-1", "Asha")
    b = employee(world, "N-2", "Bhanu")
    attach(world, a, world["aadhaar"], png_bytes())
    attach(world, a, world["pan"], png_bytes())
    attach(world, b, world["aadhaar"], png_bytes())
    # Nobody has a Photo, so it must not be offered as a choice.

    r = client.post(PREFLIGHT, json={"entity": "EMPLOYEE", "ids": [a.id, b.id]})
    assert r.status_code == 200, r.text
    offered = r.json()["document_types"]
    assert [(t["name"], t["uploaded_count"], t["missing_count"]) for t in offered] == [
        ("Aadhaar", 2, 0), ("PAN", 1, 1)]
    assert [p["reference"] for p in r.json()["people"]] == ["N-1", "N-2"]
    assert r.json()["people_with_no_documents"] == []


def test_preflight_names_the_people_who_have_nothing_on_file(client, world):
    a = employee(world, "N-1", "Asha")
    empty = employee(world, "N-2", "Bhanu")
    attach(world, a, world["aadhaar"], png_bytes())

    r = client.post(PREFLIGHT, json={"entity": "EMPLOYEE", "ids": [a.id, empty.id]})
    assert r.json()["people_with_no_documents"] == ["N-2"]


def test_preflight_refuses_an_unknown_person(client, world):
    a = employee(world, "N-1", "Asha")
    r = client.post(PREFLIGHT, json={"entity": "EMPLOYEE", "ids": [a.id, 9999]})
    assert r.status_code == 400
    assert "could not be read" in r.json()["detail"] and "1 of 2" in r.json()["detail"]


def test_an_empty_selection_is_rejected(client, world):
    assert client.post(PREFLIGHT, json={"entity": "EMPLOYEE", "ids": []}).status_code == 422


# --- the download ----------------------------------------------------------

def test_one_person_downloads_as_a_bare_pdf(client, world):
    """Zipping a single file only makes it harder to open."""
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    attach(world, a, world["pan"], png_bytes())

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id, world["pan"].id]})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="N-1 - Asha Person.pdf"' in r.headers["content-disposition"]
    assert r.headers["x-bundle-people"] == "1" and r.headers["x-bundle-documents"] == "2"
    assert r.headers["x-bundle-skipped"] == "0"
    assert pdf_page_count(r.content) == 2            # both documents became pages


def test_several_people_download_as_a_zip_of_one_pdf_each(client, world):
    a = employee(world, "N-1", "Asha")
    b = employee(world, "N-2", "Bhanu")
    for person in (a, b):
        attach(world, person, world["aadhaar"], png_bytes())

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id, b.id],
                                    "document_type_ids": [world["aadhaar"].id]})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert 'filename="hrms_employee_documents.zip"' in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        assert sorted(archive.namelist()) == ["N-1 - Asha Person.pdf", "N-2 - Bhanu Person.pdf"]
        for name in archive.namelist():
            assert archive.read(name).startswith(b"%PDF-")


def test_the_pages_follow_the_order_the_document_types_were_given(client, world):
    """The multi-select's order is the page order, so a consistent bundle
    can be produced for filing."""
    a = employee(world, "N-1", "Asha")
    # Three visibly different single-colour images, so order is checkable.
    attach(world, a, world["aadhaar"], png_bytes((255, 0, 0), size=(10, 10)), file_name="a.png")
    attach(world, a, world["pan"], png_bytes((0, 255, 0), size=(20, 20)), file_name="p.png")
    attach(world, a, world["photo"], png_bytes((0, 0, 255), size=(30, 30)), file_name="ph.png")

    names = {world["aadhaar"].id: "Aadhaar", world["pan"].id: "PAN", world["photo"].id: "Photo"}
    person = document_bundle_service.collect_people(world["db"], world["admin"], "EMPLOYEE", [a.id])[0]
    for order in ([world["photo"].id, world["aadhaar"].id, world["pan"].id],
                  [world["pan"].id, world["photo"].id]):
        pdf, skipped, included = document_bundle_service.build_person_pdf(person, order, names)
        assert included == len(order)
        # Page sizes follow the image sizes, which differ per document - so
        # the sequence of page widths proves the requested order was kept.
        widths = [round(float(w)) for w in _page_widths(pdf)]
        expected = [round(72 * {10: 10, 20: 20, 30: 30}[{world["aadhaar"].id: 10, world["pan"].id: 20, world["photo"].id: 30}[t]] / 150) for t in order]
        assert widths == expected, order


def _page_widths(pdf: bytes) -> list[float]:
    """The /MediaBox width of each page, read straight out of the file."""
    widths = []
    for chunk in pdf.split(b"/MediaBox")[1:]:
        numbers = chunk.split(b"[")[1].split(b"]")[0].split()
        widths.append(float(numbers[2]))
    return widths


def test_a_document_type_nobody_uploaded_is_reported_not_silently_dropped(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id, world["photo"].id]})
    assert r.status_code == 200, r.text
    # Something was left out, so even one person comes back zipped - with the
    # reason in the archive, where it stays with the download.
    assert r.headers["content-type"] == "application/zip"
    assert r.headers["x-bundle-skipped"] == "1"
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        assert "_skipped.txt" in archive.namelist()
        report = archive.read("_skipped.txt").decode()
        assert "Photo: not uploaded" in report and "N-1" in report


def test_a_file_that_cannot_become_a_page_is_reported(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    attach(world, a, world["pan"], b"id,name\n1,x\n", file_name="list.csv", mime="text/csv")

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id, world["pan"].id]})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        assert "not an image or PDF" in archive.read("_skipped.txt").decode()
        assert pdf_page_count(archive.read("N-1 - Asha Person.pdf")) == 1   # the Aadhaar still came through


def test_a_missing_file_on_disk_is_reported_not_a_crash(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    gone = attach(world, a, world["pan"], png_bytes())
    get_storage().delete(gone.object_key)

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id, world["pan"].id]})
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        report = archive.read("_skipped.txt").decode()
        # Said plainly - "HTTPException" would mean nothing to the operator.
        assert "the stored file is missing" in report and "HTTPException" not in report


def test_a_transparent_png_is_flattened_onto_white(client, world):
    """Otherwise it prints as a black rectangle."""
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes(mode="RGBA"), file_name="t.png")
    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id]})
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")


def test_nothing_to_download_is_an_explained_refusal(client, world):
    """Rather than an empty zip the operator has to open to understand."""
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["photo"].id]})
    assert r.status_code == 400
    assert "nothing to download" in r.json()["detail"]
    assert "Photo: not uploaded" in r.json()["detail"]


def test_no_document_types_selected_is_rejected(client, world):
    a = employee(world, "N-1", "Asha")
    assert client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id], "document_type_ids": []}).status_code == 422


def test_an_unknown_document_type_is_refused(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id, 9999]})
    assert r.status_code == 400
    assert "Unknown document type" in r.json()["detail"]


def test_a_repeated_person_or_type_counts_once(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id, a.id],
                                    "document_type_ids": [world["aadhaar"].id, world["aadhaar"].id]})
    assert r.status_code == 200
    assert r.headers["x-bundle-people"] == "1" and r.headers["x-bundle-documents"] == "1"
    assert pdf_page_count(r.content) == 1


def test_two_people_whose_names_collide_after_truncation_both_survive_the_zip(client, world):
    """File names are capped at 80 characters, and candidate references are
    long paths that can be identical up to the cap - the second one must not
    silently overwrite the first inside the archive."""
    shared = "COMP1/VRITTI-GCM-MOBILITY-ANDHRA-PRADESH/VISAKHAPATNAM-GAJUWAKA-DEPOT/OPERATIONS"
    first = candidate(world, f"{shared}/001", "Devi")
    second = candidate(world, f"{shared}/002", "Devi")
    for person in (first, second):
        attach(world, person, world["aadhaar"], png_bytes())

    r = client.post(DOWNLOAD, json={"entity": "CANDIDATE", "ids": [first.id, second.id],
                                    "document_type_ids": [world["aadhaar"].id]})
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        names = archive.namelist()
        assert len(names) == 2, names                  # neither was lost
        assert len(set(names)) == 2, names
        for name in names:
            assert archive.read(name).startswith(b"%PDF-")


def test_a_reference_with_slashes_does_not_create_folders_in_the_zip(client, world):
    """Candidate references contain slashes - they must not become paths."""
    c = candidate(world, "COMP1/GC-SMART-PY/STAFF/001", "Devi")
    other = candidate(world, "COMP1/GC-SMART-PY/STAFF/002", "Eshan")
    for person in (c, other):
        attach(world, person, world["aadhaar"], png_bytes())

    r = client.post(DOWNLOAD, json={"entity": "CANDIDATE", "ids": [c.id, other.id],
                                    "document_type_ids": [world["aadhaar"].id]})
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        for name in archive.namelist():
            assert "/" not in name, name


def test_too_many_people_at_once_is_refused(client, world):
    a = employee(world, "N-1", "Asha")
    ids = [a.id] + list(range(10_000, 10_000 + document_bundle_service.MAX_PEOPLE))
    r = client.post(PREFLIGHT, json={"entity": "EMPLOYEE", "ids": ids})
    assert r.status_code == 400
    assert "at most" in r.json()["detail"]


# --- candidates ------------------------------------------------------------

def test_candidate_documents_download_the_same_way(client, world):
    c = candidate(world, "C-1", "Devi")
    attach(world, c, world["aadhaar"], png_bytes())
    attach(world, c, world["pan"], png_bytes())

    offered = client.post(PREFLIGHT, json={"entity": "CANDIDATE", "ids": [c.id]}).json()
    assert [t["name"] for t in offered["document_types"]] == ["Aadhaar", "PAN"]

    r = client.post(DOWNLOAD, json={"entity": "CANDIDATE", "ids": [c.id],
                                    "document_type_ids": [world["aadhaar"].id, world["pan"].id]})
    assert r.status_code == 200, r.text
    assert 'filename="C-1 - Devi Candidate.pdf"' in r.headers["content-disposition"]
    assert pdf_page_count(r.content) == 2


def test_an_unknown_entity_is_refused(client, world):
    assert client.post(PREFLIGHT, json={"entity": "PAYSLIP", "ids": [1]}).status_code == 400


# --- permissions and scope -------------------------------------------------

def test_downloading_documents_needs_the_document_view_permission(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    staff_user(world, Permission.EMPLOYEE_VIEW)          # can see the list, not the documents

    body = {"entity": "EMPLOYEE", "ids": [a.id], "document_type_ids": [world["aadhaar"].id]}
    assert client.post(PREFLIGHT, json={"entity": "EMPLOYEE", "ids": [a.id]}).status_code == 403
    assert client.post(DOWNLOAD, json=body).status_code == 403


def test_a_caller_with_the_permission_can_download(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    staff_user(world, Permission.EMPLOYEE_VIEW, Permission.EMPLOYEE_DOCUMENTS_VIEW)

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id]})
    assert r.status_code == 200, r.text


def test_someone_outside_your_cost_center_scope_refuses_the_batch(client, world):
    """And refuses it rather than quietly omitting them - a download that
    silently drops people gives no sign of who is missing."""
    mine = employee(world, "N-1", "Asha")
    theirs = employee(world, "S-1", "Bhanu", cost_center=world["south"])
    for person in (mine, theirs):
        attach(world, person, world["aadhaar"], png_bytes())
    staff_user(world, Permission.EMPLOYEE_VIEW, Permission.EMPLOYEE_DOCUMENTS_VIEW, cost_centers=("north",))

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [mine.id, theirs.id],
                                    "document_type_ids": [world["aadhaar"].id]})
    assert r.status_code == 400
    assert "outside your Cost Center scope" in r.json()["detail"] and "S-1" in r.json()["detail"]


# --- the PDF-merge dependency ---------------------------------------------

@pytest.mark.skipif(not document_bundle_service.PDF_MERGE_AVAILABLE, reason="pypdf is not installed")
def test_an_uploaded_pdf_is_merged_in(client, world):
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    # A real two-page PDF, made with Pillow.
    two_pages = io.BytesIO()
    first = Image.new("RGB", (50, 50), (10, 10, 10))
    first.save(two_pages, format="PDF", save_all=True, append_images=[Image.new("RGB", (50, 50), (20, 20, 20))])
    attach(world, a, world["pan"], two_pages.getvalue(), file_name="pan.pdf", mime="application/pdf")

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id, world["pan"].id]})
    assert r.status_code == 200, r.text
    assert r.headers["x-bundle-skipped"] == "0"
    assert pdf_page_count(r.content) == 3            # 1 image page + the PDF's 2


@pytest.mark.skipif(document_bundle_service.PDF_MERGE_AVAILABLE, reason="pypdf is installed")
def test_without_pypdf_an_uploaded_pdf_is_reported_and_the_images_still_come_through(client, world):
    """The feature degrades per-document instead of failing the download."""
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes())
    attach(world, a, world["pan"], b"%PDF-1.4 fake", file_name="pan.pdf", mime="application/pdf")

    r = client.post(DOWNLOAD, json={"entity": "EMPLOYEE", "ids": [a.id],
                                    "document_type_ids": [world["aadhaar"].id, world["pan"].id]})
    assert r.status_code == 200, r.text
    with zipfile.ZipFile(io.BytesIO(r.content)) as archive:
        assert "pypdf" in archive.read("_skipped.txt").decode()
        assert pdf_page_count(archive.read("N-1 - Asha Person.pdf")) == 1


def test_images_alone_still_merge_without_pypdf(client, world):
    """Pillow writes multi-page PDFs itself, so an image-only bundle never
    depends on the merge library at all."""
    a = employee(world, "N-1", "Asha")
    attach(world, a, world["aadhaar"], png_bytes(), file_name="a.png")
    attach(world, a, world["pan"], png_bytes(), file_name="p.png")
    attach(world, a, world["photo"], png_bytes(), file_name="ph.png")

    names = {world[k].id: k for k in ("aadhaar", "pan", "photo")}
    person = document_bundle_service.collect_people(world["db"], world["admin"], "EMPLOYEE", [a.id])[0]
    pdf, skipped, included = document_bundle_service.build_person_pdf(
        person, [world["aadhaar"].id, world["pan"].id, world["photo"].id], names)
    assert skipped == [] and included == 3
    assert pdf_page_count(pdf) == 3
