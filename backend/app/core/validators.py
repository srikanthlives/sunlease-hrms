"""Shared format validators for statutory identity fields (blueprint §4.1/
§10). Used as Pydantic field_validators (schemas/employees.py) and again
in bulk_import_service.py (spreadsheet rows never go through Pydantic),
so the rules can't drift between the two entry points."""
import re

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
# UIDAI: 12 digits, first digit never 0 or 1.
AADHAAR_REGEX = re.compile(r"^[2-9][0-9]{11}$")
# 4-letter bank code + "0" (reserved) + 6 alphanumeric branch code.
IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
# Indian mobile: 10 digits, first digit 6-9 (landline/STD codes not supported).
MOBILE_REGEX = re.compile(r"^[6-9][0-9]{9}$")
PINCODE_REGEX = re.compile(r"^[0-9]{6}$")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_pan(value: str) -> str:
    v = value.strip().upper()
    if not PAN_REGEX.match(v):
        raise ValueError("Invalid PAN format - expected 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F)")
    return v


def validate_aadhaar(value: str) -> str:
    v = re.sub(r"\s+", "", value.strip())
    if not AADHAAR_REGEX.match(v):
        raise ValueError("Invalid Aadhaar number - expected 12 digits")
    return v


def validate_ifsc(value: str) -> str:
    v = value.strip().upper()
    if not IFSC_REGEX.match(v):
        raise ValueError("Invalid IFSC code format - expected 4 letters + 0 + 6 alphanumeric (e.g. SBIN0001234)")
    return v


def validate_mobile(value: str) -> str:
    v = re.sub(r"\D", "", value.strip())
    if not MOBILE_REGEX.match(v):
        raise ValueError("Invalid mobile number - expected 10 digits starting with 6-9")
    return v


def validate_pincode(value: str) -> str:
    v = value.strip()
    if not PINCODE_REGEX.match(v):
        raise ValueError("Invalid pincode - expected 6 digits")
    return v


def validate_email_format(value: str) -> str:
    v = value.strip()
    if not EMAIL_REGEX.match(v):
        raise ValueError("Invalid email address format")
    return v
