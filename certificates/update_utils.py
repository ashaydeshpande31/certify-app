"""Helpers for the "Send Updates" section (plain announcement emails with an
optional poster/photos attached). Certificate sending lives in utils.py and
is not touched by anything here."""

import base64
import mimetypes
import os
import time
from datetime import timedelta
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders

from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import timezone

from .models import ExternalUsage, Student, UpdateRecipient
from .name_guess import guess_name_from_email
from .utils import _get_gmail_service

# How many mails one browser request sends. Small on purpose: Render's
# gunicorn kills a request after ~30 s, and each Gmail send takes ~0.5-1 s.
BATCH_SIZE = 6

def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

# Gmail allows about 500 emails per rolling 24 hours for a normal account
# (about 2,000 for Google Workspace). Set DAILY_SEND_LIMIT in Render to change.
DAILY_LIMIT = _int_env("DAILY_SEND_LIMIT", 500)
# Auto-continue stops this many short of the limit so the organiser's own
# mail keeps working.
AUTO_RESERVE = _int_env("AUTO_CONTINUE_RESERVE", 50)
# Stop starting new sends after this many seconds so the request always
# finishes well inside Render's timeout, even with big attachments.
TIME_BUDGET_SECONDS = 15
# A row stuck in 'sending' this long means its request was cut off.
STUCK_AFTER = timedelta(minutes=3)

MAX_ATTACHMENTS = 10
MAX_TOTAL_ATTACHMENT_BYTES = 5 * 1024 * 1024  # small = fast sends, no timeouts, safe for Gmail's API
MAX_RECIPIENTS = 2000
ALLOWED_ATTACHMENT_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt",
)

# Words in a Gmail/Google error that mean "stop, you're out of quota" — there
# is no point trying the remaining people, they would all fail the same way.
_QUOTA_HINTS = ("ratelimit", "quota", "daily", "user-rate", "too many")


def build_update_body(campaign, recipient):
    """A "Subject: ..." line, a blank line, then the organiser's message exactly
    as typed. The only thing changed in the message is the optional {name}
    placeholder, if they typed one."""
    name = (recipient.name or "").strip()
    # older rows saved the raw start of the email as the name: guess a real one
    if not name or name.lower() == recipient.email.split("@")[0].lower():
        name = guess_name_from_email(recipient.email)
    message = campaign.message.replace("{name}", name or "there")
    # The mail starts with a "Subject:" line, then the message exactly as typed.
    return f"Subject: {clean_subject(campaign.subject)}\n\n{message}"


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


_AUTH_HINTS = ("invalid_grant", "invalid credentials", "unauthorized", "401", "token has been expired",
               "invalid_client", "unauthenticated", "insufficient")

QUOTA_MESSAGE = (
    "Gmail stopped sending because your Google account reached its daily limit. Mails you sent from "
    "Gmail itself, outside Certify, count toward that limit too. Nothing is lost: everyone not reached "
    "is still waiting. Press send again when room frees up (the counter at the top shows when)."
)
AUTH_MESSAGE = (
    "Your Google sign-in expired. Log out, sign in with Google again, then press send — "
    "only people still pending will be mailed."
)


def is_auth_error(message):
    text = (message or "").lower()
    return any(hint in text for hint in _AUTH_HINTS)


def _smtp_configured():
    return settings.EMAIL_BACKEND.endswith("smtp.EmailBackend")


def is_quota_error(message):
    text = (message or "").lower()
    return any(hint in text for hint in _QUOTA_HINTS)


def sent_last_24h(user):
    """How many emails this user's account has sent in the last 24 hours
    (update mails and certificate mails together — Gmail counts both)."""
    return sent_by_certify_24h(user) + outside_24h(user)


def sent_by_certify_24h(user):
    since = timezone.now() - timedelta(hours=24)
    return (
        UpdateRecipient.objects.filter(campaign__owner=user, status="sent", updated_at__gte=since).count()
        + Student.objects.filter(event__owner=user, status="sent", updated_at__gte=since).count()
    )


def outside_24h(user):
    """Mails the organiser said they sent from Gmail itself in the last 24 hours."""
    since = timezone.now() - timedelta(hours=24)
    return sum(ExternalUsage.objects.filter(owner=user, created_at__gte=since).values_list("count", flat=True))


def set_outside(user, n):
    """Replace the 'sent outside Certify' number (0 clears it)."""
    n = max(0, min(int(n), 100000))
    ExternalUsage.objects.filter(owner=user).delete()
    if n:
        ExternalUsage.objects.create(owner=user, count=n)
    return n


def note_gmail_refused(user):
    """Gmail said the daily limit is reached. Our count was too low, so the
    difference must have been sent elsewhere: remember it, so the counter is
    honest from now on. Never raises."""
    try:
        mine = sent_by_certify_24h(user)
        missing = max(DAILY_LIMIT - mine, 0)
        if missing > outside_24h(user):
            set_outside(user, missing)
    except Exception:  # noqa: BLE001
        pass


def quota_info(user):
    """Used / limit / left for the last 24 hours, plus when the oldest sent mail
    leaves the window (that is when room starts to free up)."""
    since = timezone.now() - timedelta(hours=24)
    outside = outside_24h(user)
    used = sent_by_certify_24h(user) + outside
    oldest = None
    if used:
        ext = ExternalUsage.objects.filter(owner=user, created_at__gte=since).order_by("created_at").values_list("created_at", flat=True).first()
        a = UpdateRecipient.objects.filter(campaign__owner=user, status="sent", updated_at__gte=since).order_by("updated_at").values_list("updated_at", flat=True).first()
        b = Student.objects.filter(event__owner=user, status="sent", updated_at__gte=since).order_by("updated_at").values_list("updated_at", flat=True).first()
        oldest = min(x for x in (a, b, ext) if x)
    return {
        "used": used,
        "outside": outside,
        "limit": DAILY_LIMIT,
        "left": max(DAILY_LIMIT - used, 0),
        "frees_at": (oldest + timedelta(hours=24)).isoformat() if oldest else None,
    }


def notify_owner_finished(campaign):
    """Tell the organiser (by email, from their own Gmail to their own address)
    that auto-continue has finished. Never raises: a missed notice must not
    break sending."""
    try:
        owner = campaign.owner
        to_email = (owner.email or "").strip()
        if not to_email:
            return False
        total = campaign.recipients.count()
        sent = campaign.recipients.filter(status="sent").count()
        failed = campaign.recipients.filter(status="failed").count()
        if failed:
            subject = f"{campaign.subject}: {sent} of {total} sent, {failed} failed"
        else:
            subject = f"{campaign.subject}: all {sent} sent"
        lines = [
            f'Your update "{campaign.subject}" has finished sending.',
            "",
            f"Sent: {sent} of {total}",
        ]
        if failed:
            lines += [
                f"Failed: {failed}",
                "",
                "Open the update in Certify and use \"Retry failed\" after fixing the addresses "
                "(look for red rows or the \"Possible typos\" box).",
            ]
        else:
            lines += ["", "Everyone on your list has it."]
        body = "\n".join(lines)
        service = _get_gmail_service(owner)
        if service is not None:
            _send_via_gmail_api(service, to_email, clean_subject(subject), body, [])
            return True
        if _smtp_configured():
            _send_via_smtp(to_email, clean_subject(subject), body, [])
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


def send_update_batch(campaign, sender, batch_size=BATCH_SIZE, budget=TIME_BUDGET_SECONDS):
    """Send the update to up to `batch_size` pending recipients.

    Returns a dict: sent, failed (this batch), remaining (still pending
    overall), stop (True if we hit a quota/limit error and should not keep
    going) and error (the last error text, if any).
    """
    started = time.monotonic()

    # Put back anyone whose earlier request was killed mid-send (e.g. a 502).
    campaign.recipients.filter(
        status="sending", updated_at__lt=timezone.now() - STUCK_AFTER
    ).update(status="pending")

    subject = clean_subject(campaign.subject)
    attachments = _load_attachments(campaign)
    service = _get_gmail_service(sender)

    # No Gmail access and no shared SMTP account: the old behaviour would
    # "send" to the server console and mark everyone Sent without mailing
    # anyone. Stop with a clear message instead.
    if service is None and not _smtp_configured():
        return {
            "sent": 0,
            "failed": 0,
            "remaining": campaign.recipients.filter(status="pending").count(),
            "stop": True,
            "error": AUTH_MESSAGE,
        }

    sent = failed = 0
    stop = False
    last_error = ""

    todo = campaign.recipients.filter(status="pending")
    check = get_check_email(sender)
    if check:      # your own check copy goes out first
        from django.db.models import Case, IntegerField, When

        todo = todo.annotate(_first=Case(When(email__iexact=check, then=0), default=1, output_field=IntegerField())).order_by("_first", "id")
    ids = list(todo.values_list("id", flat=True)[:batch_size])
    for rid in ids:
        if time.monotonic() - started > budget:
            break  # the page will simply ask for the next batch
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
            text = str(exc)[:300]
            if is_quota_error(text) or is_auth_error(text):
                # Not this person's fault: leave them pending so a later
                # "send" picks them up, and pause the whole run.
                recipient.status = "pending"
                recipient.error_message = ""
                recipient.save()
                stop = True
                if is_quota_error(text):
                    note_gmail_refused(campaign.owner)
                last_error = QUOTA_MESSAGE if is_quota_error(text) else AUTH_MESSAGE
                break
            last_error = text
            recipient.status = "failed"
            recipient.error_message = text
            recipient.save()
            failed += 1

    return {
        "sent": sent,
        "failed": failed,
        "remaining": campaign.recipients.filter(status="pending").count(),
        "stop": stop,
        "error": last_error,
    }


def guess_content_type(filename):
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


# ---------------------------------------------------------------------------
# Flexible recipient-file reader: any column order, headers optional.
# ---------------------------------------------------------------------------
import csv
import re
from io import BytesIO, StringIO

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_NAME_HEADERS = ("name", "full name", "fullname", "student name", "participant name", "your name")


def _looks_like_name(text):
    if not text or "@" in text or len(text) > 60:
        return False
    letters = sum(ch.isalpha() for ch in text)
    return letters >= 2 and letters / len(text) >= 0.6


def _rows_to_people(rows):
    """Find the email column (the one holding the most email addresses) and
    the name column (a 'Name' header if there is one, otherwise the most
    name-looking column) in any 2-D table. Returns [{'name','email'}]."""
    table = []
    for r in rows:
        cells = ["" if c is None else str(c).strip() for c in r]
        if any(cells):
            table.append(cells)
    if not table:
        return []

    ncols = max(len(r) for r in table)
    counts = [0] * ncols
    for r in table:
        for i, c in enumerate(r):
            if _EMAIL_RE.search(c):
                counts[i] += 1
    if max(counts) == 0:
        return []
    email_col = counts.index(max(counts))

    name_col = None
    for r in table[:5]:  # look for a header row
        for i, c in enumerate(r):
            if i != email_col and c.lower() in _NAME_HEADERS:
                name_col = i
                break
        if name_col is not None:
            break
    if name_col is None:
        for r in table[:5]:
            for i, c in enumerate(r):
                if i != email_col and "name" in c.lower() and "@" not in c:
                    name_col = i
                    break
            if name_col is not None:
                break
    if name_col is None:
        best = 0
        for i in range(ncols):
            if i == email_col:
                continue
            score = sum(
                1 for r in table
                if i < len(r) and email_col < len(r) and _EMAIL_RE.search(r[email_col]) and _looks_like_name(r[i])
            )
            if score > best:
                best, name_col = score, i

    people = []
    for r in table:
        found = _EMAIL_RE.findall(r[email_col]) if email_col < len(r) else []
        if not found:  # email sits in another column on this row
            for c in r:
                m = _EMAIL_RE.search(c)
                if m:
                    found = [m.group(0)]
                    break
        if not found:
            continue
        name = r[name_col] if name_col is not None and name_col < len(r) else ""
        if "@" in name:
            name = ""
        for email in found:
            people.append({"name": name, "email": email})
    return people


def _lines_to_people(text):
    """Free text: one person per line, e.g. 'Name, email' or just 'email'."""
    people = []
    for line in (text or "").splitlines():
        found = list(_EMAIL_RE.finditer(line))
        if len(found) == 1:
            m = found[0]
            name = (line[: m.start()] + " " + line[m.end():]).strip(" -,;|\t<>()")
            people.append({"name": re.sub(r"\s{2,}", " ", name), "email": m.group(0)})
        else:
            people.extend({"name": "", "email": m.group(0)} for m in found)
    return people


def get_check_email(user):
    """The address that gets a copy of every send, so you can see it arrived ('' = switched off)."""
    from .models import SenderSetting

    row = SenderSetting.objects.filter(owner=user).first()
    if row is not None:
        if row.check_disabled:
            return ""
        if (row.check_email or "").strip():
            return row.check_email.strip()
    return (getattr(user, "email", "") or "").strip()


def chunk_recommended(user):
    """Show the "send 50 at a time" advice for big lists? (on unless the person switched it off)"""
    from .models import SenderSetting

    row = SenderSetting.objects.filter(owner=user).first()
    return True if row is None else row.recommend_chunks


def _check_name(user, email):
    full = ""
    try:
        full = user.get_full_name().strip()
    except Exception:  # noqa: BLE001
        pass
    return full or guess_name_from_email(email) or "Check copy"


def ensure_check_copy_student(event, user):
    """Certificates: add the organiser's check address to the list (once) if it isn't there."""
    email = get_check_email(user)
    if not email or event.students.filter(email__iexact=email).exists():
        return False
    from .models import Student

    Student.objects.create(event=event, name=_check_name(user, email), email=email)
    return True


def ensure_check_copy_update(campaign, user):
    """Updates: same idea for a mail-only campaign."""
    email = get_check_email(user)
    if not email or campaign.recipients.filter(email__iexact=email).exists():
        return False
    from .models import UpdateRecipient

    UpdateRecipient.objects.create(campaign=campaign, name=_check_name(user, email)[:200], email=email)
    return True


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")


def rows_from_photo_emails(text):
    """The browser reads a photo and posts the emails it found (one per line). Turn them into
    people, guessing a name from each address."""
    rows, seen = [], set()
    for m in _EMAIL_RE.finditer(text or ""):
        email = m.group(0).rstrip(".,;:")
        if email.lower() in seen:
            continue
        seen.add(email.lower())
        name = guess_name_from_email(email) or re.sub(r"[^A-Za-z]+", " ", email.split("@")[0]).strip().title()
        rows.append({"name": name, "email": email})
    return rows


def parse_recipient_file(upload):
    """Read .xlsx/.xlsm/.csv/.txt/.pdf and return [{'name','email'}].
    No fixed layout needed. Raises ValueError with a friendly message."""
    filename = (getattr(upload, "name", "") or "").lower()
    upload.seek(0)
    raw = upload.read()

    if filename.endswith(".pdf"):
        import pdfplumber

        people, has_text = [], False
        with pdfplumber.open(BytesIO(raw)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                has_text = has_text or bool(text.strip())
                found = []
                for table in page.extract_tables() or []:
                    found.extend(_rows_to_people(table))
                people.extend(found or _lines_to_people(text))
        if not has_text:
            raise ValueError(
                "This PDF has no readable text (it looks like a scan or photo). "
                "Please upload an Excel or CSV file, or type the emails in the box."
            )
        return people

    if not filename.endswith((".csv", ".txt", ".xlsx", ".xlsm", ".xls")):
        return []                      # a photo or any other file: nothing to read, so "no email found"

    if filename.endswith((".csv", ".txt")):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        if filename.endswith(".txt"):
            return _lines_to_people(text)
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        return _rows_to_people(list(csv.reader(StringIO(text), dialect)))

    try:
        import openpyxl

        wb = openpyxl.load_workbook(BytesIO(raw), data_only=True)
    except Exception:  # noqa: BLE001 - old .xls or corrupt file
        raise ValueError(
            "We couldn't open that spreadsheet. If it's an old .xls file, open it in Excel and "
            "save it as .xlsx or .csv, then upload again."
        )
    people = []
    for ws in wb.worksheets:
        people.extend(_rows_to_people(list(ws.iter_rows(values_only=True))))
    return people
