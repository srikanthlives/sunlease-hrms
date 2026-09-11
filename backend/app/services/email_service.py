"""Outbound email, via either of two transports:

1. HTTP mail relay (scripts/cpanel-mail-relay.php) - used whenever
   HRMS_MAIL_RELAY_URL is set. A small PHP script hosted on the SAME
   server as the mailbox, called over HTTPS (port 443, never blocked) -
   it sends the mail locally on that server instead of over a raw SMTP
   connection. This is the path to use on any platform that blocks
   outbound SMTP (confirmed on Railway - both 465 and 587 time out);
   same scheme as the sibling sunlease-expms project.
2. Direct SMTP (stdlib smtplib, no third-party mail SDK) - used whenever
   HRMS_MAIL_RELAY_URL is NOT set. Works fine for local/bare-metal dev
   and any host that doesn't block outbound SMTP.

Unlike expms's version (which is always PDF-payslip-attachment-shaped),
`attachment_bytes` here is optional - most HRMS notifications (leave
approved, change request submitted, payroll processed, etc.) are plain
text with nothing attached.

Diagnostics use plain print(..., flush=True) with an [EMAIL] prefix,
matching this app's [STARTUP]/[WARNING] convention (see migrate.py,
main.py) rather than the stdlib `logging` module, which nothing in this
codebase configures a handler/level for.
"""
import base64
import smtplib
import sys
import traceback
from email.message import EmailMessage

import requests
from fastapi import HTTPException, status

from app.core.config import settings

# Kept short and well under a typical reverse-proxy gateway timeout - a
# hung/blocked outbound connection should fail fast with a real 502 from
# OUR app (with a useful message and a log line), rather than the
# platform's own proxy timing the whole request out first.
_TIMEOUT_SECONDS = 12


def _log(msg: str):
    print(f"[EMAIL] {msg}", flush=True)


def send_email(
    *, to_email: str, subject: str, body: str,
    attachment_bytes: bytes | None = None, attachment_filename: str | None = None, attachment_mime: str = "application/pdf",
):
    """Sends a plain-text email, with an optional single attachment."""
    if settings.MAIL_RELAY_URL:
        _send_via_relay(
            to_email=to_email, subject=subject, body=body,
            attachment_bytes=attachment_bytes, attachment_filename=attachment_filename, attachment_mime=attachment_mime,
        )
    else:
        _send_via_smtp(
            to_email=to_email, subject=subject, body=body,
            attachment_bytes=attachment_bytes, attachment_filename=attachment_filename, attachment_mime=attachment_mime,
        )


def _send_via_relay(*, to_email: str, subject: str, body: str, attachment_bytes: bytes | None, attachment_filename: str | None, attachment_mime: str):
    _log(f"send requested via HTTP relay: to={to_email!r} relay={settings.MAIL_RELAY_URL!r} secret_set={bool(settings.MAIL_RELAY_SECRET)}")
    if not settings.MAIL_RELAY_SECRET:
        _log("NOT SENT - HRMS_MAIL_RELAY_URL is set but HRMS_MAIL_RELAY_SECRET is empty")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Email relay isn't fully configured - HRMS_MAIL_RELAY_SECRET is missing.")

    payload = {"to": to_email, "subject": subject, "body": body}
    if attachment_bytes is not None:
        payload["attachment_base64"] = base64.b64encode(attachment_bytes).decode("ascii")
        payload["attachment_filename"] = attachment_filename or "attachment.pdf"
        payload["attachment_mime"] = attachment_mime

    try:
        _log(f"POSTing to relay (timeout={_TIMEOUT_SECONDS}s)...")
        resp = requests.post(
            settings.MAIL_RELAY_URL,
            json=payload,
            headers={"X-Relay-Secret": settings.MAIL_RELAY_SECRET},
            timeout=_TIMEOUT_SECONDS,
        )
        _log(f"relay responded: status={resp.status_code} body={resp.text[:300]!r}")
        if resp.status_code != 200:
            detail = resp.text[:300]
            try:
                detail = resp.json().get("error", detail)
            except ValueError:
                pass
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Mail relay rejected the request ({resp.status_code}): {detail}")
        data = resp.json()
        if not data.get("success"):
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Mail relay reported failure: {data.get('error', 'unknown error')}")
        _log(f"sent successfully to {to_email} via relay")
    except requests.RequestException as exc:
        _log(f"RELAY REQUEST FAILED ({type(exc).__name__}): {exc}")
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not reach mail relay: {exc}")


def _send_via_smtp(*, to_email: str, subject: str, body: str, attachment_bytes: bytes | None, attachment_filename: str | None, attachment_mime: str):
    _log(
        f"send requested via SMTP: to={to_email!r} host={settings.SMTP_HOST!r} port={settings.SMTP_PORT} "
        f"use_ssl={settings.SMTP_USE_SSL} username_set={bool(settings.SMTP_USERNAME)} "
        f"password_set={bool(settings.SMTP_PASSWORD)} from={settings.SMTP_FROM_EMAIL!r}"
    )
    if not settings.SMTP_HOST or not settings.SMTP_FROM_EMAIL:
        _log("NOT SENT - SMTP_HOST or SMTP_FROM_EMAIL is empty in this process's config")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Email sending isn't configured on this server - set HRMS_SMTP_HOST and HRMS_SMTP_FROM_EMAIL, "
            "or HRMS_MAIL_RELAY_URL/HRMS_MAIL_RELAY_SECRET (see .env.example).",
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>" if settings.SMTP_FROM_NAME else settings.SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body)

    if attachment_bytes is not None:
        maintype, _, subtype = attachment_mime.partition("/")
        msg.add_attachment(attachment_bytes, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=attachment_filename or "attachment")

    try:
        _log(f"connecting to {settings.SMTP_HOST}:{settings.SMTP_PORT} (use_ssl={settings.SMTP_USE_SSL}, timeout={_TIMEOUT_SECONDS}s)...")
        if settings.SMTP_USE_SSL:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_TIMEOUT_SECONDS) as server:
                _log(f"connected. logging in as {settings.SMTP_USERNAME or '(no auth)'}...")
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                _log("authenticated. sending message...")
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=_TIMEOUT_SECONDS) as server:
                server.starttls()
                _log(f"connected + STARTTLS ok. logging in as {settings.SMTP_USERNAME or '(no auth)'}...")
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                _log("authenticated. sending message...")
                server.send_message(msg)
        _log(f"sent successfully to {to_email} via SMTP")
    except (smtplib.SMTPException, OSError) as exc:
        _log(f"FAILED ({type(exc).__name__}): {exc}")
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not send email: {exc}")
    except Exception as exc:  # noqa: BLE001 - last-resort: never let this hang or 500 without a clear cause
        _log(f"UNEXPECTED FAILURE ({type(exc).__name__}): {exc}")
        traceback.print_exc(file=sys.stderr)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not send email: {exc}")
