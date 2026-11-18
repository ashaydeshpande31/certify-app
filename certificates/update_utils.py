"""Helpers for the "Send Updates" section (plain announcement emails with an
optional poster/photos attached). Certificate sending lives in utils.py and
is not touched by anything here."""

import base64
import mimetypes
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from django.core.mail import EmailMessage
from django.conf import settings

from .utils import _get_gmail_service

# How many mails one browser request sends. Small on purpose: Render's
# gunicorn kills a request after ~30 s, and each Gmail send takes ~0.5-1 s.
BATCH_SIZE = 8

MAX_ATTACHMENTS = 10
MAX_TOTAL_ATTACHMENT_BYTES = 15 * 1024 * 1024  # Gmail's hard cap is 25 MB per mail
MAX_RECIPIENTS = 2000
ALLOWED_ATTACHMENT_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt",
)

# Words in a Gmail/Google error that mean "stop, you're out of quota" — there
# is no point trying the remaining people, they would all fail the same way.
_QUOTA_HINTS = ("ratelimit", "quota", "daily", "user-rate", "too many")


def build_update_body(campaign, recipient):
    """The mail body is the organiser's message exactly as typed. The only
    thing touched is the optional {name} placeholder, if they typed one."""
    return campaign.message.replace("{name}", recipient.name)


def clean_subject(subject):
    # A newline in a header would let someone inject extra headers.
    return " ".join((subject or "").split())


def _load_attachments(campaign):
    return [
        (a.filename, a.content_type or "application/octet-stream", bytes(a.data))
        for a in campaign.attachments.all()
    ]


def _send_via_gmail_api(service, to_email, subject, body, attachments):
    message = MIMEMultipart()
    message["to"] = to_email
    message["subject"] = Header(subject, "utf-8")
    message.attach(MIMEText(body, "plain", "utf-8"))

    for filename, content_type, data in attachments:
        maintype, _, subtype = content_type.partition("/")
        part = MIMEBase(maintype or "application", subtype or "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def _send_via_smtp(to_email, subject, body, attachments):
    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    for filename, content_type, data in attachments:
        email.attach(filename, data, content_type)
    email.send(fail_silently=False)


def is_quota_error(message):
    text = (message or "").lower()
    return any(hint in text for hint in _QUOTA_HINTS)


def send_update_batch(campaign, sender, batch_size=BATCH_SIZE):
    """Send the update to up to `batch_size` pending recipients.

    Returns a dict: sent, failed (this batch), remaining (still pending
    overall), stop (True if we hit a quota/limit error and should not keep
    going) and error (the last error text, if any).
    """
    subject = clean_subject(campaign.subject)
    attachments = _load_attachments(campaign)
    service = _get_gmail_service(sender)

    sent = failed = 0
    stop = False
    last_error = ""

    ids = list(
        campaign.recipients.filter(status="pending").values_list("id", flat=True)[:batch_size]
    )
    for rid in ids:
        # Claim the row first, so two browser tabs (or a double click) can
        # never send the same person the same mail twice.
        claimed = campaign.recipients.filter(id=rid, status="pending").update(status="sending")
        if not claimed:
            continue
        recipient = campaign.recipients.get(id=rid)
        try:
            body = build_update_body(campaign, recipient)
            if service is not None:
                _send_via_gmail_api(service, recipient.email, subject, body, attachments)
            else:
                _send_via_smtp(recipient.email, subject, body, attachments)
            recipient.status = "sent"
            recipient.error_message = ""
            recipient.save()
            sent += 1
        except Exception as exc:  # noqa: BLE001 - surface any send error in the UI
            last_error = str(exc)[:300]
            recipient.status = "failed"
            recipient.error_message = last_error
            recipient.save()
            failed += 1
            if is_quota_error(last_error):
                stop = True
                break

    return {
        "sent": sent,
        "failed": failed,
        "remaining": campaign.recipients.filter(status="pending").count(),
        "stop": stop,
        "error": last_error,
    }


def guess_content_type(filename):
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
