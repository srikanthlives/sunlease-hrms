"""Best-effort OCR extraction for Indian identity documents (Aadhaar/PAN/
Driving Licence) and bank passbooks - same "best-effort, not government-
certified" honesty this codebase already applies to Compliance's
statement exports (compliance_service.py). Runs entirely locally via
Tesseract (no cloud OCR API, no document image ever leaves this server) -
English text only by design (lang="eng"): any Hindi/regional-script lines
on the card (Aadhaar prints the name/address in both Hindi and English)
are matched against Latin-only line filters and dropped, per the "ignore
other languages" instruction this was built to.

Every field the extractor can find is returned, not just the ones that
map onto an existing form field - "show all the scanned data" (gender
and father's/husband's name from Aadhaar/PAN; the DL holder's own name
and the address printed on it, neither of which has anywhere to apply to
automatically since Personal Info already has its own name fields) is
included for the reviewer to see and judge, even where the frontend's
"Apply" has nothing to wire an informational-only field into.

Runs OCR twice per document - once on a plain upscaled/autocontrasted
image, once on an OpenCV adaptive-threshold "sketch" pass (CLAHE + Gaussian
blur + adaptive threshold + morphology) - and merges whichever pass found
each field, preferring the longer/more complete value when both found
something different. The sketch pass and several of the field-pattern
heuristics below (Driving Licence's controlled vehicle-class vocabulary,
its DL-number formats, PAN's ordered-name-line fallback) are adapted from
openbharatocr (github.com/essentiasoftserv/openbharatocr, Apache-2.0) -
its own PAN/Aadhaar/Driving-Licence extractors turned out to be plain
Tesseract + OpenCV + regex (no model), so rather than pulling in the
whole package - which also hard-depends on EasyOCR/PyTorch for its
(unused here) passbook parser, adding ~500MB for zero benefit to these
three document types - the useful techniques were ported directly.

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

import cv2
import numpy as np
from PIL import Image, ImageOps
import pytesseract

from app.core.validators import AADHAAR_REGEX, IFSC_REGEX, PAN_REGEX

# Header text every passbook/chequebook prints - good enough to say "this
# looks like a bank page" without needing a name dictionary, since every
# such document legally has to print the word "Bank" somewhere prominent.
# [ \t] rather than \s in both character classes - \s also matches "\n",
# so searching the whole multi-line text let this silently swallow the
# NEXT printed line too (matched against one real test as "State Bank Of
# India Branch" instead of stopping at "India"). Applied per-line below
# instead of across the whole text, for the same reason.
BANK_NAME_HINT_RE = re.compile(r"\b([A-Z][A-Za-z.&\t ]{2,40}\bBANK\b[A-Za-z.&\t ]{0,20})", re.IGNORECASE)

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

# Real-world Class-of-Vehicle codes printed on Indian Driving Licences -
# matched directly against the raw text rather than relying on a "COV"/
# "Class of Vehicle" label actually being legible, which it often isn't.
DL_VEHICLE_CLASSES = [
    "MCWG", "MCWOG", "LMV-NT", "LMV-TR", "LMV", "HMV-NT", "HMV", "TRANS-NT",
    "TRANS", "MGV", "HPMV", "HTV", "TRAILER", "M.CYL.", "FVG",
]
# Punctuation-free lookup for _decompose_vehicle_token below, longest
# first so e.g. "LMVNT" is tried before "LMV" ever gets a chance to.
_VEHICLE_CLASS_PLAIN = sorted(
    ((code.replace("-", "").replace(".", ""), code) for code in DL_VEHICLE_CLASSES),
    key=lambda pair: len(pair[0]), reverse=True,
)

# (?<!\d)/(?!\d) rather than \b at the digit ends - \b treats letters and
# digits as the same "word" class, so a label merged onto a date with no
# OCR'd space (e.g. "Valid Till09-01-2035") would otherwise hide the date
# from every regex scan entirely (no boundary between "ll" and "0").
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[\s./-](\d{1,2})[\s./-](\d{4})(?!\d)")
_AADHAAR_NUMBER_RE = re.compile(r"\b(\d{4}\s?\d{4}\s?\d{4})\b")
_PAN_NUMBER_RE = re.compile(r"\b([A-Z]{5}\s?[0-9]{4}\s?[A-Z])\b")
_PINCODE_RE = re.compile(r"\b(\d{6})\b")
# Real Indian DL number formats (e.g. "TN01 20210012345" / "TN-0120210012345").
_DL_NUMBER_RE = re.compile(r"\b([A-Z]{2}[-\s]?\d{2}[-\s]?\d{4}\d{7})\b")
# A "name-shaped" line: Latin letters/spaces/periods only, 2-40 chars, at
# least two letters - excludes pure-noise OCR fragments and non-Latin
# script lines (Hindi glyphs never match \x00-\x7f-only content).
# Trailing punctuation Tesseract loves to hallucinate onto an otherwise-
# clean line (a stray comma/quote picked up from a card border or the
# next printed character) - stripped before every name-shape check AND
# before using a line as a final value. Missing a punctuation mark here
# previously caused a real bug: "RAJESH KUMAR," (trailing comma, only
# ".:" were stripped) failed the name-shape regex and silently dropped
# out as a candidate, letting the father's name below it win instead.
_TRIM_CHARS = " .,:;'\"-"
_NAME_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z.\s]{1,39}$")
_NON_NAME_WORDS = {
    "GOVERNMENT", "OF", "INDIA", "GOVT", "UNIQUE", "IDENTIFICATION", "AUTHORITY",
    "MALE", "FEMALE", "TRANSGENDER", "DOB", "DATE", "BIRTH", "YEAR", "ADDRESS",
    "INCOME", "TAX", "DEPARTMENT", "PERMANENT", "ACCOUNT", "NUMBER", "NAME",
    "SIGNATURE", "FATHER", "FATHERS", "HUSBAND", "HUSBANDS", "ISSUE", "VALID",
    "VALIDITY", "TRANSPORT", "LICENCE", "LICENSE", "DRIVING", "AUTHORITY",
    "UNION", "REPUBLIC", "CARD", "DEPARTMENT",
}
# A label-only line ("Branch Name" / "Account Holder Name" with nothing
# else on it) leaves one of these words sitting in the "value" capture
# group instead of the regex simply not matching - treated the same as
# no match at all, falling through to the next physical line.
_LABEL_LEFTOVER_WORDS = {"NAME", "NO", "NUMBER", "HOLDER", "HOLDERS", "A/C", "AC", "ACCOUNT"}


def _is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _load_image(image_bytes: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        raise ValueError("Could not read this file as an image") from exc
    return ImageOps.exif_transpose(image).convert("RGB")


def _preprocess_plain(image: Image.Image) -> Image.Image:
    gray = image.convert("L")
    if gray.width < 1500:
        scale = 1500 / gray.width
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS)
    return ImageOps.autocontrast(gray)


def _preprocess_sketch(image: Image.Image) -> Image.Image:
    """CLAHE + adaptive threshold + morphology - a differently-biased pass
    that often recovers text the plain pass misses on low-contrast/glare
    phone photos of a laminated card (adapted from openbharatocr)."""
    arr = np.array(image)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    if gray.shape[1] < 1500:
        scale = 1500 / gray.shape[1]
        gray = cv2.resize(gray, (int(gray.shape[1] * scale), int(gray.shape[0] * scale)), interpolation=cv2.INTER_LANCZOS4)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    binary = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10)
    inverted = cv2.bitwise_not(binary)
    kernel = np.ones((2, 2), np.uint8)
    processed = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, kernel, iterations=1)

    return Image.fromarray(processed)


def _tesseract_text(image: Image.Image) -> str:
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
        cleaned = line.strip(_TRIM_CHARS)
        if not _NAME_LINE_RE.match(cleaned):
            continue
        words = [w for w in re.split(r"\s+", cleaned.upper()) if w]
        # startswith rather than == - Tesseract regularly drops the space
        # after a boilerplate word ("GOVERNMENT OF" -> "GOVERNMENTOF"),
        # which let a merged line slip past an exact-match stopword check
        # in one real test and get picked as a "name" instead of rejected.
        if not words or any(w.rstrip(".").startswith(nn) for w in words for nn in _NON_NAME_WORDS):
            continue
        # A line that's entirely Class-of-Vehicle codes (a merged "LMV
        # MCWG" -> "LMVMCWG" reads as a perfectly name-shaped line) isn't
        # a name - reuse the same decomposition used for dl_vehicle_class.
        if _decompose_vehicle_token(cleaned.replace(" ", "")):
            continue
        out.append(i)
    return out


def _extract_gender(text: str) -> str | None:
    if re.search(r"\bfemale\b", text, re.IGNORECASE):
        return "FEMALE"
    if re.search(r"\btransgender\b", text, re.IGNORECASE):
        return "OTHER"
    if re.search(r"\bmale\b", text, re.IGNORECASE):
        return "MALE"
    return None


def _extract_father_husband_name(text: str) -> str | None:
    """S/O, D/O, W/O (Son/Daughter/Wife Of) is how both Aadhaar and PAN
    print whichever parent/spouse name is on record - far more reliable
    than guessing which of several name-shaped lines is "the other one".
    Matched per physical line (not the whole multi-line text) - \\s in the
    capture group matches a literal newline too, which previously let
    this bleed straight into the NEXT printed line (one real test
    produced "Suresh Kumar\\nDob" instead of stopping at "Kumar")."""
    for line in _lines(text):
        m = re.search(r"(?:S[/.]?O|D[/.]?O|W[/.]?O)[:\s]*([A-Za-z][A-Za-z ]{1,39})$", line, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(_TRIM_CHARS)
            if candidate and _is_ascii(candidate):
                return candidate.upper()
    return None


def _decompose_vehicle_token(token: str) -> list[str]:
    """Tries to fully consume an all-caps token as a run of known Class-
    of-Vehicle codes with nothing left over (e.g. "LMVMCWG" -> LMV +
    MCWG, where Tesseract dropped the space between two codes printed
    side by side). Returns [] if any part of the token doesn't match a
    code - this is what keeps it from false-positiving on an ordinary
    word like "TRANSPORT" (TRANS matches, but the leftover "PORT" isn't
    a code, so the whole token is rejected rather than half-accepted)."""
    token = token.upper()
    i, found = 0, []
    while i < len(token):
        for plain, code in _VEHICLE_CLASS_PLAIN:
            if token.startswith(plain, i):
                found.append(code)
                i += len(plain)
                break
        else:
            return []
    return found


def _merge_fields(primary: dict, secondary: dict) -> dict:
    """Combines two extraction passes field-by-field: the plain pass
    (primary) wins whenever it found anything at all, falling back to the
    sketch pass (secondary) only when primary came up empty for that
    field. Deliberately NOT "prefer whichever is longer" - two name-shaped
    candidates (e.g. a cardholder's name vs their father's/husband's,
    both similarly short) are otherwise a coin flip, and a real PAN-card
    test caught exactly that: the sketch pass's reordered/garbled text
    produced a same-length WRONG name that length-comparison picked over
    the plain pass's correct one."""
    return {key: primary.get(key) or secondary.get(key) for key in primary}


def _parse_aadhaar(text: str) -> dict:
    lines = _lines(text)
    fields = {
        "aadhaar_name": None, "aadhaar_dob": None, "aadhaar": None, "gender": None,
        "father_husband_name": None,
        "present_line1": None, "present_city": None, "present_state": None,
        "present_pincode": None, "present_country": None,
    }

    fields["gender"] = _extract_gender(text)
    fields["father_husband_name"] = _extract_father_husband_name(text)

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
        fields["aadhaar_name"] = lines[chosen].strip(_TRIM_CHARS).upper()

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
                found_state = state.upper()
                chunk = chunk[:idx].rstrip(", ")
                break
        fields["present_state"] = found_state

        parts = [p.strip() for p in chunk.split(",") if p.strip()]
        if parts:
            fields["present_city"] = parts[-1].upper() if len(parts) > 1 else None
            fields["present_line1"] = ", ".join(parts[:-1] if len(parts) > 1 else parts).upper()
        if fields["present_line1"] or fields["present_city"] or fields["present_state"] or fields["present_pincode"]:
            fields["present_country"] = "INDIA"

    return fields


def _parse_pan(text: str) -> dict:
    lines = _lines(text)
    fields = {"pan_name": None, "pan_dob": None, "pan": None, "father_husband_name": None}

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

    name_idx = next((i for i, l in enumerate(lines) if re.fullmatch(r"name", l.strip(_TRIM_CHARS), re.IGNORECASE)), None)
    if name_idx is not None and name_idx + 1 < len(lines):
        candidate = lines[name_idx + 1].strip(_TRIM_CHARS)
        if _NAME_LINE_RE.match(candidate):
            fields["pan_name"] = candidate.upper()

    # Real PAN card photos rarely OCR the tiny "Name"/"Father's Name"
    # labels cleanly - fall back to the first two name-shaped lines in
    # print order (Name always precedes Father's/Husband's Name on every
    # PAN layout), same ordering heuristic openbharatocr's PAN extractor
    # uses instead of relying on the label at all.
    name_lines = _candidate_name_lines(lines)
    if not fields["pan_name"] and name_lines:
        fields["pan_name"] = lines[name_lines[0]].strip(_TRIM_CHARS).upper()

    fathers_idx = next(
        (i for i, l in enumerate(lines) if re.search(r"father'?s?\s*name|husband'?s?\s*name", l, re.IGNORECASE)), None,
    )
    if fathers_idx is not None and fathers_idx + 1 < len(lines):
        candidate = lines[fathers_idx + 1].strip(_TRIM_CHARS)
        if _NAME_LINE_RE.match(candidate):
            fields["father_husband_name"] = candidate.upper()
    if not fields["father_husband_name"] and len(name_lines) > 1:
        # Name always precedes Father's/Husband's Name on a PAN card - the
        # second name-shaped line in print order, when the label itself
        # didn't survive OCR.
        fields["father_husband_name"] = lines[name_lines[1]].strip(_TRIM_CHARS).upper()

    return fields


def _parse_driving_licence(text: str) -> dict:
    lines = _lines(text)
    fields = {
        "dl_licence_number": None, "dl_badge_number": None, "dl_vehicle_class": None,
        "dl_issuing_authority": None, "dl_issue_date": None, "dl_expiry_date": None,
        # Informational only - Personal Information already has its own
        # Name fields, and nothing currently stores a DL's own address,
        # but "show all the scanned data" still means surfacing both.
        "dl_holder_name": None, "dl_address": None,
    }

    # Label-based first: a bare "NAME"/"HOLDER" line is itself a valid
    # _NAME_LINE_RE match, which means the generic ordered-candidate-line
    # fallback (used below) would wrongly reject the ENTIRE "Name RAJESH
    # KUMAR" line as non-name boilerplate (it contains the word "NAME",
    # which is in _NON_NAME_WORDS) rather than just stripping the label
    # off it and keeping the value.
    for i, line in enumerate(lines):
        m = re.search(r"\b(?:name|holder)\b\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
        candidate = m.group(1).strip(_TRIM_CHARS) if m else None
        if candidate and candidate.upper() not in _LABEL_LEFTOVER_WORDS and _NAME_LINE_RE.match(candidate):
            fields["dl_holder_name"] = candidate.upper()
            break
    if not fields["dl_holder_name"]:
        name_lines = _candidate_name_lines(lines)
        if name_lines:
            fields["dl_holder_name"] = lines[name_lines[0]].strip(_TRIM_CHARS).upper()

    addr_idx = next((i for i, l in enumerate(lines) if re.search(r"^add(?:ress)?\b", l, re.IGNORECASE)), None)
    if addr_idx is not None:
        chunk_lines = []
        for line in lines[addr_idx:addr_idx + 6]:
            if re.search(r"valid\s*till|validity|signature", line, re.IGNORECASE):
                break
            chunk_lines.append(line)
            if _PINCODE_RE.search(line):
                break
        chunk = re.sub(r"^add(?:ress)?\s*[:\-]?\s*", "", " ".join(chunk_lines), flags=re.IGNORECASE)
        chunk = " ".join(w for w in chunk.split() if _is_ascii(w))
        if chunk:
            fields["dl_address"] = chunk.upper()

    def _value_after(label_pattern: str, line: str) -> str | None:
        # label_pattern is itself an alternation (A|B|C) - must be
        # non-capture-grouped before appending the value-capture suffix,
        # or "|" (lowest precedence) only binds the suffix to the LAST
        # alternative and every other branch matches with no group(1).
        m = re.search(f"(?:{label_pattern})" + r"\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
        return m.group(1).strip(_TRIM_CHARS) if m and m.group(1).strip(_TRIM_CHARS) else None

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
                fields["dl_issuing_authority"] = val.upper()[:255]

        if re.search(r"\bDOI\b|date\s*of\s*issue|\bissue\b", line, re.IGNORECASE):
            dm = _DATE_RE.search(line) or (_DATE_RE.search(lines[i + 1]) if i + 1 < len(lines) else None)
            if dm and not fields["dl_issue_date"]:
                fields["dl_issue_date"] = _normalize_date(dm)

        if re.search(r"valid\s*till|validity|\bDOE\b|expiry|expiry\s*date", line, re.IGNORECASE):
            dm = _DATE_RE.search(line) or (_DATE_RE.search(lines[i + 1]) if i + 1 < len(lines) else None)
            if dm and not fields["dl_expiry_date"]:
                fields["dl_expiry_date"] = _normalize_date(dm)

    # Fallback: a real DL-number format matched directly, with no label
    # needed at all (labels are small print and often don't survive OCR).
    if not fields["dl_licence_number"]:
        m = _DL_NUMBER_RE.search(text.replace("\n", " "))
        if m:
            fields["dl_licence_number"] = re.sub(r"[\s-]", "", m.group(1)).upper()

    # Fallback: match against the real, fixed vocabulary of Class-of-
    # Vehicle codes directly, rather than depending on a "COV" label.
    if not fields["dl_vehicle_class"]:
        found = [code for code in DL_VEHICLE_CLASSES if re.search(rf"\b{re.escape(code)}\b", text, re.IGNORECASE)]
        if not found:
            # Tesseract sometimes drops the space between adjacent codes
            # ("LMV MCWG" -> "LMVMCWG"), which also removes the word
            # boundary the strict match above needs - try decomposing
            # each all-caps token into a run of known codes instead.
            for token in re.findall(r"[A-Z]{2,20}", text.upper()):
                found.extend(_decompose_vehicle_token(token))
        if found:
            fields["dl_vehicle_class"] = ", ".join(sorted(set(c.upper() for c in found)))

    # Fallback: two unlabelled dates anywhere on the card, in print order,
    # are almost always Issue then Expiry.
    if not fields["dl_issue_date"] or not fields["dl_expiry_date"]:
        all_dates = [_normalize_date(dm) for dm in _DATE_RE.finditer(text)]
        all_dates = [d for d in all_dates if d]
        if len(all_dates) >= 2:
            fields["dl_issue_date"] = fields["dl_issue_date"] or all_dates[0]
            fields["dl_expiry_date"] = fields["dl_expiry_date"] or all_dates[-1]

    return fields


def _parse_passbook(text: str) -> dict:
    """Bank passbook / cancelled cheque - same field names as
    schemas/employees.py::BankAccountStep so the Employee Wizard's Bank
    Information step can merge this directly, same as every other kind."""
    lines = _lines(text)
    fields = {
        "bank_name": None, "branch": None, "account_number": None,
        "ifsc": None, "account_holder_name": None, "account_type": None,
    }

    for line in lines:
        m = BANK_NAME_HINT_RE.search(line)
        if m:
            fields["bank_name"] = re.sub(r"\s+", " ", m.group(1)).strip(_TRIM_CHARS).upper()
            break

    ifsc_m = re.search(r"\b([A-Z]{4}0[A-Z0-9]{6})\b", text)
    if ifsc_m and IFSC_REGEX.match(ifsc_m.group(1)):
        fields["ifsc"] = ifsc_m.group(1)
    else:
        # The 5th character is ALWAYS a literal "0" by RBI convention -
        # Tesseract frequently reads it as the letter "O" instead (one
        # real test did exactly this: "SBINO001234"). Allow either there
        # and normalize to "0" before validating, since nothing else
        # about the 11-char IFSC format is this reliably fixed.
        loose_m = re.search(r"\b([A-Z]{4})[0O]([A-Z0-9]{6})\b", text)
        if loose_m:
            candidate = f"{loose_m.group(1)}0{loose_m.group(2)}"
            if IFSC_REGEX.match(candidate):
                fields["ifsc"] = candidate

    for i, line in enumerate(lines):
        if fields["branch"] is None and re.search(r"\bbranch\b", line, re.IGNORECASE):
            val = re.search(r"branch\s*(?:name)?\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
            captured = val.group(1).strip(_TRIM_CHARS) if val else None
            # A label-only line ("Branch Name" with nothing else on it)
            # leaves just a leftover label word in the capture group
            # instead of no match at all - fall through to the next line
            # exactly as if nothing had matched on this one.
            if captured and captured.upper() in _LABEL_LEFTOVER_WORDS:
                captured = None
            value = captured or (lines[i + 1].strip(_TRIM_CHARS) if i + 1 < len(lines) else None)
            if value and _is_ascii(value):
                fields["branch"] = value.upper()[:150]

        if fields["account_number"] is None and re.search(r"a/?c\s*no|account\s*(?:number|no)\b", line, re.IGNORECASE):
            val = re.search(r"(?:a/?c\s*no|account\s*(?:number|no))\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
            raw = (val.group(1) if val else None) or (lines[i + 1] if i + 1 < len(lines) else "")
            digits = re.sub(r"\D", "", raw)
            if 9 <= len(digits) <= 18:
                fields["account_number"] = digits

        if fields["account_holder_name"] is None and re.search(r"a/?c\s*holder|account\s*holder|holder'?s?\s*name", line, re.IGNORECASE):
            val = re.search(r"(?:a/?c\s*holder|account\s*holder|holder'?s?\s*name)\s*[:\-]?\s*(.+)$", line, re.IGNORECASE)
            captured = val.group(1).strip(_TRIM_CHARS) if val else None
            if captured and captured.upper() in _LABEL_LEFTOVER_WORDS:
                captured = None
            candidate = captured or (lines[i + 1].strip(_TRIM_CHARS) if i + 1 < len(lines) else None)
            if candidate and _NAME_LINE_RE.match(candidate):
                fields["account_holder_name"] = candidate.upper()

        if fields["account_type"] is None and re.search(r"\b(savings|current)\b", line, re.IGNORECASE):
            fields["account_type"] = "SAVINGS" if re.search(r"savings", line, re.IGNORECASE) else "CURRENT"

    if not fields["account_number"]:
        # Fallback: the longest run of 9-18 digits anywhere on the page -
        # account numbers are usually the longest digit string printed,
        # longer than any date, IFSC or pincode. (?<!\d)/(?!\d) rather
        # than \b - a real test caught Tesseract merging "No" straight
        # into the digits with no space ("No00123456789012"), and \b
        # doesn't fire between a letter and a digit (both are "word"
        # characters), hiding the number from a \b-bounded scan entirely.
        runs = re.findall(r"(?<!\d)\d{9,18}(?!\d)", text)
        if runs:
            fields["account_number"] = max(runs, key=len)

    if not fields["account_holder_name"]:
        name_lines = _candidate_name_lines(lines)
        if name_lines:
            fields["account_holder_name"] = lines[name_lines[0]].strip(_TRIM_CHARS).upper()

    return fields


_PARSERS = {
    "AADHAAR": _parse_aadhaar, "PAN": _parse_pan, "DRIVING_LICENCE": _parse_driving_licence,
    "BANK_PASSBOOK": _parse_passbook,
}


def ocr_document_kind(document_type_name: str | None) -> str | None:
    name = (document_type_name or "").lower()
    if "aadhaar" in name or "aadhar" in name:
        return "AADHAAR"
    if "pan" in name:
        return "PAN"
    if "driving" in name or "licence" in name or "license" in name:
        return "DRIVING_LICENCE"
    if "passbook" in name or "bank" in name or "cheque" in name or "check" in name:
        return "BANK_PASSBOOK"
    return None


def extract_document_fields(document_type_name: str | None, image_bytes: bytes, mime_type: str | None) -> dict:
    kind = ocr_document_kind(document_type_name)
    if not kind:
        raise ValueError("OCR extraction isn't available for this document type")
    if mime_type and "pdf" in mime_type.lower():
        raise ValueError("OCR extraction only supports image uploads (JPG/PNG) - this document was uploaded as a PDF")

    image = _load_image(image_bytes)
    parser = _PARSERS[kind]

    plain_text = _tesseract_text(_preprocess_plain(image))
    plain_fields = parser(plain_text)

    try:
        sketch_text = _tesseract_text(_preprocess_sketch(image))
        sketch_fields = parser(sketch_text)
        fields = _merge_fields(plain_fields, sketch_fields)
    except Exception:
        # The sketch pass is a best-effort second opinion - if OpenCV
        # preprocessing itself fails on an unusual image, fall back to
        # just the plain pass rather than failing the whole request.
        fields = plain_fields

    return {"kind": kind, "fields": fields, "extracted_count": sum(1 for v in fields.values() if v)}
