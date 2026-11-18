"""Bulk document download: many people x many document types -> one PDF each.

Each selected person gets ONE merged PDF containing the document types that
were ticked, in the order they were ticked, and the PDFs are returned as a
.zip - except for a single person, who is served their PDF directly, since
zipping one file only makes it harder to open.

Images are converted to PDF pages with Pillow. Already-PDF uploads are
concatenated with pypdf. Anything else (a .docx, a .txt) cannot become a
page and is reported in the bundle's `_skipped.txt` rather than failing the
whole download - one odd upload among two hundred documents should not cost
someone the other hundred and ninety-nine.

pypdf is listed in requirements.txt. If it is genuinely missing from the
running environment, this module still produces every image-only person's
PDF and reports each PDF upload as skipped, saying so - the same
report-don't-fail rule, applied to the dependency itself.
"""
import io
import zipfile
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from PIL import Image
from sqlalchemy.orm import Session

from app.models.models import (
    Candidate, CandidateDocument, DocumentMeta, DocumentType, EmploymentEpisode, User,
)
from app.services import document_service, employee_service, permission_service

try:                                      # see the module docstring
    from pypdf import PdfWriter
    PDF_MERGE_AVAILABLE = True
except ImportError:                       # pragma: no cover - environment-dependent
    PdfWriter = None
    PDF_MERGE_AVAILABLE = False

EMPLOYEE = "EMPLOYEE"
CANDIDATE = "CANDIDATE"
ENTITIES = (EMPLOYEE, CANDIDATE)

PDF_MIME = "application/pdf"
ZIP_MIME = "application/zip"
MAX_PEOPLE = 200            # a guardrail, not a policy: one request, one response
NO_PDF_SUPPORT_REASON = (
    "is a PDF, and PDF merging is unavailable in this deployment (the pypdf package is not installed)"
)


@dataclass
class Person:
    """One selected person and the documents they actually have."""
    id: int                                  # episode_id or candidate_id
    name: str                                # for the file name
    reference: str                           # employee number / candidate reference
    documents: dict[int, object] = field(default_factory=dict)   # document_type_id -> document row


def check_entity(entity: str) -> str:
    if entity not in ENTITIES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Entity must be one of {', '.join(ENTITIES)}")
    return entity


def _safe(value: str) -> str:
    """A file name that survives every OS and zip tool - no separators, no
    reserved characters, no trailing dots/spaces."""
    cleaned = "".join("-" if ch in '\\/:*?"<>|' else ch for ch in (value or "")).strip(" .")
    return cleaned[:80] or "unnamed"


def collect_people(db: Session, user: User, entity: str, ids: list[int]) -> list[Person]:
    """The selected people, each with their uploaded documents keyed by
    document type. Refuses the whole request if any id is unknown or out of
    the caller's Cost Center scope - a bulk download that silently drops
    people gives no sign of who is missing from it."""
    check_entity(entity)
    unique = list(dict.fromkeys(ids))
    if not unique:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select at least one person")
    if len(unique) > MAX_PEOPLE:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{len(unique)} selected - download at most {MAX_PEOPLE} people at a time",
        )

    people, missing = [], []
    for person_id in unique:
        if entity == EMPLOYEE:
            episode = db.query(EmploymentEpisode).filter(EmploymentEpisode.id == person_id).first()
            if not episode:
                missing.append(str(person_id))
                continue
            if not permission_service.can_see_cost_center(db, user, employee_service.home_cost_center_id(db, episode.id)):
                missing.append(episode.employee_number or str(person_id))
                continue
            people.append(Person(
                id=episode.id,
                name=f"{episode.employee.first_name} {episode.employee.last_name}".strip(),
                reference=episode.employee_number or f"episode-{episode.id}",
                documents={d.document_type_id: d for d in episode.documents if d.document_type_id},
            ))
        else:
            candidate = db.query(Candidate).filter(Candidate.id == person_id).first()
            if not candidate:
                missing.append(str(person_id))
                continue
            if not permission_service.can_see_cost_center(db, user, candidate.applied_cost_center_id):
                missing.append(candidate.reference_number or str(person_id))
                continue
            people.append(Person(
                id=candidate.id,
                name=f"{candidate.first_name} {candidate.last_name}".strip(),
                reference=candidate.reference_number or f"candidate-{candidate.id}",
                documents={d.document_type_id: d for d in candidate.documents if d.document_type_id},
            ))

    if missing:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Nothing was downloaded. {len(missing)} of {len(unique)} could not be read "
            f"(not found, or outside your Cost Center scope): {', '.join(missing[:5])}"
            + (f" and {len(missing) - 5} more" if len(missing) > 5 else ""),
        )
    return people


def preflight(db: Session, user: User, entity: str, ids: list[int]) -> dict:
    """What the dialog needs to offer a meaningful document multi-select:
    every document type ANY of the selected people has on file, each with a
    count, so "Aadhaar - 11 of 12" is visible before downloading rather than
    discovered afterwards in a skipped list."""
    people = collect_people(db, user, entity, ids)
    names = {t.id: t.name for t in db.query(DocumentType).all()}

    counts: dict[int, int] = {}
    for person in people:
        for document_type_id in person.documents:
            counts[document_type_id] = counts.get(document_type_id, 0) + 1

    document_types = sorted(
        ({"document_type_id": tid, "name": names.get(tid) or f"Type {tid}",
          "uploaded_count": count, "missing_count": len(people) - count}
         for tid, count in counts.items()),
        key=lambda row: row["name"],
    )
    return {
        "people": [{"id": p.id, "name": p.name, "reference": p.reference, "document_count": len(p.documents)}
                   for p in people],
        "document_types": document_types,
        "people_with_no_documents": [p.reference for p in people if not p.documents],
        "pdf_merge_available": PDF_MERGE_AVAILABLE,
    }


def _flatten(image: Image.Image) -> Image.Image:
    """An RGB copy on a white background - a transparent PNG otherwise
    prints as a black rectangle."""
    if image.mode in ("RGBA", "LA", "P"):
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.split()[-1])
        return flat
    return image.convert("RGB")


def _image_to_pdf_bytes(content: bytes) -> bytes:
    """One image -> a one-page PDF."""
    with Image.open(io.BytesIO(content)) as image:
        buffer = io.BytesIO()
        _flatten(image).save(buffer, format="PDF", resolution=150.0)
        return buffer.getvalue()


def _is_image(document) -> bool:
    if (document.mime_type or "").startswith("image/"):
        return True
    name = (document.file_name or "").lower()
    return name.endswith((".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"))


def _is_pdf(document) -> bool:
    return (document.mime_type or "") == PDF_MIME or (document.file_name or "").lower().endswith(".pdf")


def build_person_pdf(person: Person, document_type_ids: list[int], names: dict[int, str]) -> tuple[bytes | None, list[str], int]:
    """One person's selected documents as a single PDF, in the order the
    types were given. Returns (pdf or None, reasons anything was left out,
    how many documents actually became pages)."""
    # Each entry is ("image" | "pdf", raw bytes). Kept in their original
    # form until the end, because the two merge paths want different
    # things: pypdf wants PDFs, and Pillow (the no-pypdf path) wants the
    # images themselves - it cannot read a PDF back.
    parts: list[tuple[str, bytes]] = []
    skipped: list[str] = []

    for document_type_id in document_type_ids:
        document = person.documents.get(document_type_id)
        label = names.get(document_type_id) or f"Type {document_type_id}"
        if not document:
            skipped.append(f"{label}: not uploaded")
            continue
        if not document.object_key:
            skipped.append(f"{label}: no stored file")
            continue
        try:
            content = document_service.read_object(document.object_key)
        except HTTPException:
            # The storage backend raises 404 for a key with no file behind
            # it - a row whose upload is gone. Said plainly, because
            # "HTTPException" means nothing to whoever is downloading.
            skipped.append(f"{label}: the stored file is missing ({document.file_name or document.object_key})")
            continue
        except Exception as exc:
            skipped.append(f"{label}: could not be read ({type(exc).__name__})")
            continue

        if _is_image(document):
            try:
                with Image.open(io.BytesIO(content)) as probe:
                    probe.verify()                   # refuse a truncated/!image file here, not mid-merge
            except Exception as exc:
                skipped.append(f"{label}: not a readable image ({type(exc).__name__})")
                continue
            parts.append(("image", content))
        elif _is_pdf(document):
            if PDF_MERGE_AVAILABLE:
                parts.append(("pdf", content))
            else:
                skipped.append(f"{label}: {NO_PDF_SUPPORT_REASON}")
        else:
            skipped.append(f"{label}: {document.file_name or 'file'} is not an image or PDF, so it cannot become a page")

    if not parts:
        return None, skipped, 0

    if not PDF_MERGE_AVAILABLE:
        # Everything here is an image (a PDF would have been skipped above),
        # so Pillow writes the multi-page file itself and the merge library
        # is never needed for an image-only bundle.
        images = [_flatten(Image.open(io.BytesIO(content))) for _, content in parts]
        buffer = io.BytesIO()
        images[0].save(buffer, format="PDF", resolution=150.0, save_all=True, append_images=images[1:])
        for image in images:
            image.close()
        return buffer.getvalue(), skipped, len(parts)

    writer = PdfWriter()
    for kind, content in parts:
        writer.append(io.BytesIO(_image_to_pdf_bytes(content) if kind == "image" else content))
    buffer = io.BytesIO()
    writer.write(buffer)
    writer.close()
    return buffer.getvalue(), skipped, len(parts)


def build_bundle(db: Session, user: User, entity: str, ids: list[int], document_type_ids: list[int]) -> dict:
    """The download itself.

    Returns {content, filename, media_type, people_included, documents_included,
    skipped}. A single person comes back as a bare PDF; two or more as a zip
    of one PDF each, plus a `_skipped.txt` whenever something was left out,
    so the gap is visible in the download rather than only on screen.
    """
    check_entity(entity)
    wanted = list(dict.fromkeys(document_type_ids))
    if not wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Select at least one document type")

    people = collect_people(db, user, entity, ids)
    names = {t.id: t.name for t in db.query(DocumentType).filter(DocumentType.id.in_(wanted)).all()}
    unknown = [str(tid) for tid in wanted if tid not in names]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown document type(s): {', '.join(unknown)}")

    built: list[tuple[Person, bytes]] = []
    skipped: list[str] = []
    documents_included = 0
    for person in people:
        pdf, reasons, included = build_person_pdf(person, wanted, names)
        label = f"{person.reference} - {person.name}" if person.name else person.reference
        skipped.extend(f"{label} -> {reason}" for reason in reasons)
        if pdf:
            built.append((person, pdf))
            documents_included += included
        else:
            skipped.append(f"{label} -> nothing to download, so no PDF was produced for them")

    if not built:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "None of the selected people have any of the selected documents on file, so there is nothing to download. "
            + ("First reasons: " + "; ".join(skipped[:3]) if skipped else ""),
        )

    prefix = "employee" if entity == EMPLOYEE else "candidate"
    if len(built) == 1 and not skipped:
        person, pdf = built[0]
        return {
            "content": pdf, "media_type": PDF_MIME,
            "filename": f"{_safe(person.reference)} - {_safe(person.name)}.pdf",
            "people_included": 1, "documents_included": documents_included, "skipped": skipped,
        }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        used: set[str] = set()
        for person, pdf in built:
            base = f"{_safe(person.reference)} - {_safe(person.name)}" if person.name else _safe(person.reference)
            name = f"{base}.pdf"
            copy = 2
            while name in used:                  # two people can share a name
                name = f"{base} ({copy}).pdf"
                copy += 1
            used.add(name)
            archive.writestr(name, pdf)
        if skipped:
            archive.writestr(
                "_skipped.txt",
                "These documents are not in this download:\n\n" + "\n".join(skipped) + "\n",
            )
    return {
        "content": buffer.getvalue(), "media_type": ZIP_MIME,
        "filename": f"hrms_{prefix}_documents.zip",
        "people_included": len(built), "documents_included": documents_included, "skipped": skipped,
    }
