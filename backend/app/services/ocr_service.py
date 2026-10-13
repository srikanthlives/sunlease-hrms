"""Best-effort OCR extraction for Indian identity documents (Aadhaar/PAN/
Driving Licence) - same "best-effort, not government-certified" honesty
this codebase already applies to Compliance's statement exports
(compliance_service.py). Runs entirely locally via Tesseract (no cloud
OCR API, no document image ever leaves this server) - English text only
by design (lang="eng"): any Hindi/regional-script lines on the card
(Aadhaar prints the name/address in both Hindi and English) are matched
against Latin-only line filters and dropped, per the "ignore other
languages" instruction this was built to.

Entry point: extract_document_fields(document_type_name, image_bytes,
mime_type). Returns {"kind": ..., "fields": {...}} where `fields` uses
the exact same key names as Candidate/Employee/DrivingLicenceDetail
columns (aadhaar_name, aadhaar_dob, aadhaar, present_line1/city/state/
pincode/country, pan_name, pan_dob, pan, dl_licence_number, ...) so the
frontend can merge the result straight into its form state without any
field-name translation.

Accuracy note: regex/keyword heuristics over raw OCR text from a phone
photo of a government ID card will never be 100% - this is a starting
point for the user to review and correct, not an authoritative read.
Only JPEG/PNG uploads are supported; PDF documents raise a clear error
rather than silently returning nothing.
"""
import io
import re

from PIL import Image, ImageOps
import pytesseract

from app.core.validators import AADHAAR_REGEX, PAN_REGEX

INDIAN_STATES = [
    "ANDHRA PRADESH", "ARUNACHAL PRADESH", "ASSAM", "BIHAR", "CHHATTISGARH",
    "GOA", "GUJARAT", "HARYANA", "HIMACHAL PRADESH", "JHARKHAND", "KARNATAKA",
    "KERALA", "MADHYA PRADESH", "MAHARASHTRA", "MANIPUR", "MEGHALAYA", "MIZORAM",
    "NAGALAND", "ODISHA", "PUNJAB", "RAJASTHAN", "SIKKIM", "TAMIL NADU",
    "TELANGANA", "TRIPURA", "UTTAR PRADESH", "UTTARAKHAND", "WEST BENGAL",
    "ANDAMAN AND NICOBAR ISLANDS", "CHANDIGARH",
    "DADRA AND NAGAR HAVELI AND DAMAN AND DIU", "DELHI", "JAMMU AND KASHMIR",
    "LADAKH", "LAKSHADWEEP", "PUDUCHERRY",
]

_DATE_RE = re.compile(r"\b(\d{1,2})[\s./-](\d{1,2})[\s./-](\d{4})\b")
_AADHAAR_NUMBER_RE = re.compile(r"\b(\d{4}\s?\d{4}\s?\d{4})\b")
_PAN_NUMBER_RE = re.compile(r"\b([A-Z]{5}\s?[0-9]{4}\s?[A-Z])\b")
_PINCODE_RE = re.compile(r"\b(\d{6})\b")
# A "name-shaped" line: Latin letters/spaces/periods only, 2-40 chars, at
# least two letters - excludes pure-noise OCR fragments and non-Latin
# script lines (Hindi glyphs never match \x00-\x7f-only content).
_NAME_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z.\s]{1,39}$")
_NON_NAME_WORDS = {
    "GOVERNMENT", "OF", "INDIA", "GOVT", "UNIQUE", "IDENTIFICATION", "AUTHORITY",
    "MALE", "FEMALE", "TRANSGENDER", "DOB", "DATE", "BIRTH", "YEAR", "ADDRESS",
    "INCOME", "TAX", "DEPARTMENT", "PERMANENT", "ACCOUNT", "NUMBER", "NAME",
    "SIGNATURE", "FATHER", "FATHERS", "HUSBAND", "HUSBANDS", "ISSUE", "VALID",
    "VALIDITY", "TRANSPORT", "LICENCE", "LICENSE", "DRIVING", "AUTHORITY",
    "UNION", "REPUBLIC",
}


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _run_ocr(image_bytes: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise ValueError("Could not read this file as an image") from exc

    image = ImageOps.exif_transpose(image).convert("L")
    # Upscale small phone-photo crops - Tesseract accuracy drops sharply
    # below ~300 DPI-equivalent text height.
    if image.width < 1500:
        scale = 1500 / image.width
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    image = ImageOps.autocontrast(image)

    try:
        return pytesseract.image_to_string(image, lang="eng")
    except pytesseract.TesseractNotFoundError as exc:
        raise ValueError("OCR is not available on this server right now") from exc


def _normalize_date(match: "re.Match") -> str | None:
    d, m, y = match.group(1), match.group(2), match.group(3)
    try:
        d, m, y = int(d), int(m), int(y)
        if m > 12 and d <= 12:
            d, m = m, d
        if not (1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100):
            return None
        return f"{y:04d}-{m:02d}-{d:02d}"
    except ValueError:
        return None


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _candidate_name_lines(lines: list[str]) -> list[int]:
    """Indices of lines that look like a plain Latin name and aren't one
    of the fixed boilerplate words every card prints (labels, headers)."""
    out = []
    for i, line in enumerate(lines):
        if not _is_ascii(line):
            continue
        cleaned = line.strip(" .:")
        if not _NAME_LINE_RE.match(cleaned):
            continue
        words = [w for w in re.split(r"\s+", cleaned.upper()) if w]
        if not words or any(w.rstrip(".") in _NON_NAME_WORDS for w in words):
            continue
        out.append(i)
    return out


def _parse_aadhaar(text: str) -> dict:
    lines = _lines(text)
    fields = {
        "aadhaar_name": None, "aadhaar_dob": None, "aadhaar": None,
        "present_line1": None, "present_city": None, "present_state": None,
        "present_pincode": None, "present_country": None,
    }

    m = _AADHAAR_NUMBER_RE.search(text)
    if m:
        digits = re.sub(r"\s", "", m.group(1))
        if AADHAAR_REGEX.match(digits):
            fields["aadhaar"] = digits

    dob_line_idx = None
    for i, line in enumerate(lines):
        if re.search(r"\bDOB\b|\bD\.?O\.?B\.?\b|date of birth|year of birth", line, re.IGNORECASE):
            dm = _DATE_RE.search(line)
            if not dm and i + 1 < len(lines):
                dm = _DATE_RE.search(lines[i + 1])
            if dm:
                fields["aadhaar_dob"] = _normalize_date(dm)
                dob_line_idx = i
                break
    if not fields["aadhaar_dob"]:
        dm = _DATE_RE.search(text)
        if dm:
            fields["aadhaar_dob"] = _normalize_date(dm)

    name_lines = _candidate_name_lines(lines)
    if name_lines:
        # Prefer the name line immediately before the DOB/gender line -
        # that's the printed layout order on every Aadhaar card.
        anchor = dob_line_idx if dob_line_idx is not None else next(
            (i for i, l in enumerate(lines) if re.search(r"\bmale\b|\bfemale\b", l, re.IGNORECASE)), None,
        )
        if anchor is not None:
            before = [i for i in name_lines if i < anchor]
            chosen = before[-1] if before else name_lines[0]
        else:
            chosen = name_lines[0]
        fields["aadhaar_name"] = lines[chosen].strip(" .:").title()

    addr_idx = next((i for i, l in enumerate(lines) if re.search(r"^address\b", l, re.IGNORECASE)), None)
    if addr_idx is not None:
        chunk_lines = []
        for line in lines[addr_idx:addr_idx + 8]:
            if re.search(r"uidai|unique identification|www\.|^\d{4}\s?\d{4}\s?\d{4}$", line, re.IGNORECASE):
                break
            chunk_lines.append(line)
            if _PINCODE_RE.search(line):
                break
        chunk = " ".join(chunk_lines)
        chunk = re.sub(r"^address\s*[:\-]?\s*", "", chunk, flags=re.IGNORECASE)
        chunk = " ".join(w for w in chunk.split() if _is_ascii(w))

        pm = _PINCODE_RE.search(chunk)
        if pm:
            fields["present_pincode"] = pm.group(1)
            chunk = chunk[:pm.start()].rstrip(", ")

        found_state = None
        for state in INDIAN_STATES:
            idx = chunk.upper().rfind(state)
            if idx != -1:
                found_state = state.title()
                chunk = chunk[:idx].rstrip(", ")
                break
        fields["present_state"] = found_state

        parts = [p.strip() for p in chunk.split(",") if p.strip()]
        if parts:
            fields["present_city"] = parts[-1].title() if len(parts) > 1 else None
            fields["present_line1"] = ", ".join(parts[:-1] if len(parts) > 1 else parts).title()
        if fields["present_line1"] or fields["present_city"] or fields["present_state"] or fields["present_pincode"]:
            fields["present_country"] = "India"

    return fields


def _parse_pan(text: str) -> dict:
    lines = _lines(text)
    fields = {"pan_name": None, "pan_dob": None, "pan": None}

    m = _PAN_NUMBER_RE.search(text)
    if m:
        candidate = re.sub(r"\s", "", m.group(1)).upper()
        if PAN_REGEX.match(candidate):
            fields["pan"] = candidate

    for i, line in enumerate(lines):
        if re.search(r"date of birth|\bdob\b", line, re.IGNORECASE):
            dm = _DATE_RE.search(line) or (_DATE_RE.search(lines[i + 1]) if i + 1 < len(lines) else None)
            if dm:
                fields["pan_dob"] = _normalize_date(dm)
            break
    if not fields["pan_dob"]:
        dm = _DATE_RE.search(text)
        if dm:
            fields["pan_dob"] = _normalize_date(dm)

    name_idx = next((i for i, l in enumerate(lines) if re.fullmatch(r"name", l.strip(" .:"), re.IGNORECASE)), None)
    if name_idx is not None and name_idx + 1 < len(lines):
        candidate = lines[name_idx + 1].strip(" .:")
        if _NAME_LINE_RE.match(candidate):
            fields["pan_name"] = candidate.title()
    if not fields["pan_name"]:
        name_lines = _candidate_name_lines(lines)
        # Father's/Husband's Name follows Name on a PAN card - if we only
        # found two name-shaped lines, the first is the cardholder's.
        if name_lines:
            fields["pan_name"] = lines[name_lines[0]].strip(" .:").title()

    return fields


def _parse_driving_licence(text: str) -> dict:
    lines = _lines(text)
    fields = {
        "dl_licence_number": None, "dl_badge_number": None, "dl_vehicle_class": None,
        "dl_issuing_authority": None, "dl_issue_date": None, "dl_expiry_date": None,
    }

    def _value_after(label_pattern: str, line: str) -> str | None:
        # label_pattern is itself an alternation (A|B|C) - must be
        # non-capture-grouped before appending the value-capture suffix,
        # or "|" (lowest precedence) only binds the suffix to the LAST
        # alternative and every other branch matches with no group(1).
        m = re.search(f"(?:{label_pattern})" + r"\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
        return m.group(1).strip(" .:") if m and m.group(1).strip(" .:") else None

    for i, line in enumerate(lines):
        if fields["dl_licence_number"] is None and re.search(r"\bDL\s*No\b|\blicen[cs]e\s*no\b|\blic\.?\s*no\b", line, re.IGNORECASE):
            val = _value_after(r"\bDL\s*No\b|\blicen[cs]e\s*no\b|\blic\.?\s*no\b", line)
            candidate = re.sub(r"\s+", "", val or "") or (re.sub(r"\s+", "", lines[i + 1]) if i + 1 < len(lines) else None)
            if candidate and re.match(r"^[A-Z0-9/-]{8,20}$", candidate.upper()):
                fields["dl_licence_number"] = candidate.upper()

        if fields["dl_badge_number"] is None and re.search(r"\bbadge\s*no\b", line, re.IGNORECASE):
            val = _value_after(r"\bbadge\s*no\b", line)
            if val:
                fields["dl_badge_number"] = re.sub(r"\s+", "", val).upper()

        if fields["dl_vehicle_class"] is None and re.search(r"\bCOV\b|class\s*of\s*vehicle|vehicle\s*class", line, re.IGNORECASE):
            val = _value_after(r"\bCOV\b|class\s*of\s*vehicle|vehicle\s*class", line)
            if val:
                fields["dl_vehicle_class"] = val.upper()[:100]

        if fields["dl_issuing_authority"] is None and re.search(r"issuing\s*authority|\bRTO\b|licensing\s*authority", line, re.IGNORECASE):
            val = _value_after(r"issuing\s*authority|\bRTO\b|licensing\s*authority", line)
            if val and _is_ascii(val):
                fields["dl_issuing_authority"] = val.title()[:255]

        if re.search(r"\bDOI\b|date\s*of\s*issue|\bissue\b", line, re.IGNORECASE):
            dm = _DATE_RE.search(line) or (_DATE_RE.search(lines[i + 1]) if i + 1 < len(lines) else None)
            if dm and not fields["dl_issue_date"]:
                fields["dl_issue_date"] = _normalize_date(dm)

        if re.search(r"valid\s*till|validity|\bDOE\b|expiry|expiry\s*date", line, re.IGNORECASE):
            dm = _DATE_RE.search(line) or (_DATE_RE.search(lines[i + 1]) if i + 1 < len(lines) else None)
            if dm and not fields["dl_expiry_date"]:
                fields["dl_expiry_date"] = _normalize_date(dm)

    # Fallback: two unlabelled dates anywhere on the card, in print order,
    # are almost always Issue then Expiry.
    if not fields["dl_issue_date"] or not fields["dl_expiry_date"]:
        all_dates = [_normalize_date(dm) for dm in _DATE_RE.finditer(text)]
        all_dates = [d for d in all_dates if d]
        if len(all_dates) >= 2:
            fields["dl_issue_date"] = fields["dl_issue_date"] or all_dates[0]
            fields["dl_expiry_date"] = fields["dl_expiry_date"] or all_dates[-1]

    return fields


def ocr_document_kind(document_type_name: str | None) -> str | None:
    name = (document_type_name or "").lower()
    if "aadhaar" in name or "aadhar" in name:
        return "AADHAAR"
    if "pan" in name:
        return "PAN"
    if "driving" in name or "licence" in name or "license" in name:
        return "DRIVING_LICENCE"
    return None


def extract_document_fields(document_type_name: str | None, image_bytes: bytes, mime_type: str | None) -> dict:
    kind = ocr_document_kind(document_type_name)
    if not kind:
        raise ValueError("OCR extraction isn't available for this document type")
    if mime_type and "pdf" in mime_type.lower():
        raise ValueError("OCR extraction only supports image uploads (JPG/PNG) - this document was uploaded as a PDF")

    text = _run_ocr(image_bytes)
    if kind == "AADHAAR":
        fields = _parse_aadhaar(text)
    elif kind == "PAN":
        fields = _parse_pan(text)
    else:
        fields = _parse_driving_licence(text)

    return {"kind": kind, "fields": fields, "extracted_count": sum(1 for v in fields.values() if v)}
