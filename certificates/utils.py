import base64
import csv
import functools
import os
import re
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from io import BytesIO, StringIO

import openpyxl
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont

import time
from email.header import Header
from django.utils import timezone

from .models import Student

FONT_PATHS = {
    "serif": {
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    },
    "sans": {
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    },
    # DejaVu has no script/handwritten face on this system; fall back to
    # serif-bold which still reads as "formal" on a certificate.
    "script": {
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    },
}


def _parse_pdf_table(rows_2d):
    """Given a list of table rows (each a list of cell strings/None), find
    Name/Email columns and return student dicts. Shared logic with the
    xlsx/csv path below."""
    if not rows_2d:
        return None
    header = [str(c).strip().lower() if c else "" for c in rows_2d[0]]
    name_idx = next((i for i, h in enumerate(header) if "name" in h), None)
    email_idx = next((i for i, h in enumerate(header) if "email" in h or "gmail" in h or "mail" in h), None)
    if name_idx is None or email_idx is None:
        return None

    students = []
    for row in rows_2d[1:]:
        if row is None or all((c is None or str(c).strip() == "") for c in row):
            continue
        if len(row) <= max(name_idx, email_idx):
            continue
        name, email = row[name_idx], row[email_idx]
        if not name or not email:
            continue
        students.append({"name": str(name).strip(), "email": str(email).strip()})
    return students


def _parse_pdf_freetext(text):
    """Fallback for PDFs with no real table structure: find one email per
    line and treat the rest of that line as the name. Handles common
    exported formats like 'Ashay Deshpande - ashay@gmail.com' or
    'Ashay Deshpande, ashay@gmail.com' or tab/space separated pairs."""
    email_re = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    students = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = email_re.search(line)
        if not match:
            continue
        email = match.group(0)
        name = (line[: match.start()] + line[match.end() :]).strip(" -,|\t")
        name = re.sub(r"\s{2,}", " ", name).strip()
        if not name:
            continue  # can't safely guess a name — skip rather than mislabel
        students.append({"name": name, "email": email})
    return students


def parse_pdf(pdf_field):
    """Read an uploaded PDF and return a list of {'name', 'email'} dicts.

    Only works for PDFs with real, selectable text (e.g. a spreadsheet or
    form-response list exported/printed to PDF) — NOT scanned images or
    photos of a printed page, which have no extractable text at all.
    """
    import pdfplumber

    pdf_field.seek(0)
    all_students = []
    has_any_text = False

    with pdfplumber.open(BytesIO(pdf_field.read())) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                has_any_text = True

            for table in page.extract_tables() or []:
                parsed = _parse_pdf_table(table)
                if parsed:
                    all_students.extend(parsed)

            if not all_students:
                all_students.extend(_parse_pdf_freetext(page_text))

    if not has_any_text:
        raise ValueError(
            "This PDF doesn't contain any readable text — it looks like a scanned "
            "image or a photo saved as a PDF, which we can't read automatically. "
            "Please upload a .xlsx, .xls, or .csv file instead, or a PDF exported "
            "directly from a spreadsheet (not a photo)."
        )

    if not all_students:
        raise ValueError(
            "Couldn't find any Name/Email pairs in this PDF. Please make sure it has "
            "a 'Name' and 'Email' column (if it's a table), or one name and email per "
            "line, or upload a .xlsx, .xls, or .csv file instead."
        )

    return all_students


def parse_excel(excel_field):
    """Read an uploaded participant list and return a list of {'name', 'email'} dicts.

    Accepts .xlsx/.xls (openpyxl), .csv (Python's csv module), or .pdf
    (pdfplumber — text-based PDFs only, see parse_pdf). Looks for columns
    headed (case-insensitively) 'name' and 'email'/'gmail' in the first row,
    in any order/position.
    """
    filename = (getattr(excel_field, "name", "") or "").lower()

    if filename.endswith(".pdf"):
        return parse_pdf(excel_field)

    if not filename.endswith((".csv", ".xlsx", ".xlsm", ".xls")):
        return []                      # a photo or any other file: nothing to read, so "no email found"

    excel_field.seek(0)

    if filename.endswith(".csv"):
        text = excel_field.read().decode("utf-8-sig", errors="ignore")
        reader = csv.reader(StringIO(text))
        rows = list(reader)
    else:
        try:
            wb = openpyxl.load_workbook(BytesIO(excel_field.read()), data_only=True)
        except Exception:  # noqa: BLE001 - not really a spreadsheet
            return []
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))

    if not rows:
        return []

    header = [str(c).strip().lower() if c else "" for c in rows[0]]

    name_idx = next((i for i, h in enumerate(header) if "name" in h), None)
    email_idx = next((i for i, h in enumerate(header) if "email" in h or "gmail" in h or "mail" in h), None)

    if name_idx is None or email_idx is None:
        raise ValueError(
            "Couldn't find 'Name' and 'Email/Gmail' columns in the first row of your Excel sheet. "
            "Please make sure the first row has headers like 'Name' and 'Email'."
        )

    students = []
    for row in rows[1:]:
        if row is None or all((c is None or str(c).strip() == "") for c in row):
            continue
        if len(row) <= max(name_idx, email_idx):
            continue  # short/ragged row — not enough columns for name+email
        name = row[name_idx]
        email = row[email_idx]
        if not name or not email:
            continue
        students.append({"name": str(name).strip(), "email": str(email).strip()})
    return students


_FONT_CANDIDATES = (
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/timesbd.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
)


@functools.lru_cache(maxsize=1)
def _font_path():
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return ""


@functools.lru_cache(maxsize=256)
def _load_font(path, size):
    """Opening a font file is slow; do it once per size, not once per name."""
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)


def get_font(event, size=None):
    return _load_font(_font_path(), int(size or event.font_size))


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


FIT_MARGIN = 0.04  # keep names this far (share of the width) away from the edge
MIN_FIT_SCALE = 0.25  # never shrink a name below 25% of the chosen size


def max_text_width(event, image_width):
    """Widest a name may be, given where it is placed and how it is aligned."""
    x = image_width * (event.name_x_percent / 100.0)
    margin = image_width * FIT_MARGIN
    if event.text_align == "left":
        room = image_width - x - margin
    elif event.text_align == "right":
        room = x - margin
    else:
        room = 2 * (min(x, image_width - x) - margin)
    return max(room, image_width * 0.1)


def fit_font(event, text, image_width, draw):
    """Return (font, scale): the chosen font, shrunk until `text` fits."""
    limit = max_text_width(event, image_width)
    size = event.font_size
    font = get_font(event, size)
    width = draw.textlength(text, font=font)
    if width <= limit:
        return font, 1.0
    min_size = max(8, int(event.font_size * MIN_FIT_SCALE))
    while width > limit and size > min_size:
        size = max(min_size, int(size * min(0.95, limit / width)))
        font = get_font(event, size)
        width = draw.textlength(text, font=font)
    return font, size / event.font_size


def name_needs_shrink(event, image_width, names):
    """Names that will be drawn smaller than the chosen font size."""
    from PIL import Image as _Image

    draw = ImageDraw.Draw(_Image.new("RGB", (1, 1)))
    out = []
    for n in names:
        _font, scale = fit_font(event, n, image_width, draw)
        if scale < 0.999:
            out.append((n, scale))
    return out


def store_template_copy(event):
    """Keep a copy of the uploaded design in the database (the disk copy is
    lost whenever Render redeploys)."""
    event.template_image.open("rb")
    try:
        data = event.template_image.read()
    finally:
        event.template_image.close()
    img = Image.open(BytesIO(data))
    event.template_data = data
    event.template_type = Image.MIME.get(img.format, "image/png")
    event.save(update_fields=["template_data", "template_type"])


def get_template_bytes(event):
    """The design image bytes: from the database copy, else (older events)
    from the file on disk, which is then copied into the database."""
    if event.template_data:
        return bytes(event.template_data)
    try:
        store_template_copy(event)
        return bytes(event.template_data)
    except (FileNotFoundError, ValueError, OSError):
        raise ValueError(
            "The certificate design image for this event is missing (the server lost the file). "
            "Open the layout page and upload the design again."
        )


_BASE_CACHE = {"key": None, "img": None}


def _decoded_template(event):
    """The design image, decoded once and reused for every certificate of a batch
    (decoding a big PNG for each of 400 mails is what made sending slow)."""
    data = get_template_bytes(event)
    key = (event.id, len(data), data[:48], data[-48:])
    if _BASE_CACHE["key"] != key:
        _BASE_CACHE["img"] = Image.open(BytesIO(data)).convert("RGB")
        _BASE_CACHE["key"] = key
    return _BASE_CACHE["img"].copy()


def render_certificate_image(event, student_name):
    """Return a PIL Image with the student's name drawn onto the event template.
    Long names shrink so they stay inside the certificate."""
    base = _decoded_template(event)

    draw = ImageDraw.Draw(base)
    w, h = base.size

    x = w * (event.name_x_percent / 100.0)
    y = h * (event.name_y_percent / 100.0)

    font, _scale = fit_font(event, student_name, w, draw)
    color = hex_to_rgb(event.font_color)

    anchor = {"left": "lm", "center": "mm", "right": "rm"}[event.text_align]
    draw.text((x, y), student_name, font=font, fill=color, anchor=anchor)

    return base


def render_certificate_pdf_bytes(event, student_name):
    """The certificate as PDF bytes, made on the spot (nothing stored on disk)."""
    img = render_certificate_image(event, student_name)
    buffer = BytesIO()
    img.save(buffer, format="PDF")
    return buffer.getvalue()


def _build_email_body(event, student, verify_url=None, subject=None):
    """Certificate email text. The body starts with a "Subject:" line so the
    reader sees it in the message too. (verify_url is kept only so older calls
    still work; the verify link is no longer put in the email.)"""
    lines = []
    if subject:
        lines += [f"Subject: {subject}", ""]
    lines += [
        f"Hi {student.name},",
        "",
        f'Congratulations! Please find attached your certificate for "{event.name}".',
        "Feel free to download it and share it on LinkedIn.",
    ]
    if event.message:
        lines += ["", event.message.strip()]
    lines += [
        "",
        "Best regards,",
        f"{event.organizer or 'The Organizing Team'}",
    ]
    return "\n".join(lines)


def _get_gmail_service(user):
    """Return an authorized Gmail API service for `user`'s Google account,
    or None if the user hasn't signed in with Google / granted Gmail access
    (in which case the caller should fall back to the shared SMTP account).
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    try:
        from allauth.socialaccount.models import SocialToken, SocialApp
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        # django-allauth / google-api-python-client not installed yet.
        return None

    token = (
        SocialToken.objects.filter(account__user=user, account__provider="google")
        .order_by("-expires_at")
        .first()
    )
    if token is None or not token.token:
        return None

    app = SocialApp.objects.filter(provider="google").first()
    client_id = app.client_id if app else os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = app.secret if app else os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

    creds = Credentials(
        token=token.token,
        refresh_token=token.token_secret or None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )

    try:
        if creds.refresh_token:
            # Always refresh: Credentials built without an expiry never report
            # "expired", so a token older than ~1 hour would 401 on every send.
            creds.refresh(Request())
            token.token = creds.token
            token.save(update_fields=["token"])
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _safe_filename(name):
    """A filename that is safe in a mail header (no newlines or slashes)."""
    cleaned = re.sub(r"[\r\n\\/:*?\"<>|]+", " ", name or "").strip()
    cleaned = re.sub(r"\s+", "_", cleaned) or "certificate"
    return cleaned[:80]


def _send_via_gmail_api(service, student, subject, body, attachment_bytes, attachment_name, extras=()):
    message = MIMEMultipart()
    message["to"] = student.email
    message["subject"] = Header(subject, "utf-8")
    message.attach(MIMEText(body, "plain", "utf-8"))

    part = MIMEBase("application", "pdf")
    part.set_payload(attachment_bytes)
    encoders.encode_base64(part)
    # RFC 2231 form so names in Marathi / Hindi / any script survive
    part.add_header("Content-Disposition", "attachment", filename=("utf-8", "", attachment_name))
    message.attach(part)

    for ex_name, ex_type, ex_data in extras:
        maintype, _, subtype = (ex_type or "application/octet-stream").partition("/")
        extra = MIMEBase(maintype or "application", subtype or "octet-stream")
        extra.set_payload(ex_data)
        encoders.encode_base64(extra)
        extra.add_header("Content-Disposition", "attachment", filename=("utf-8", "", ex_name))
        message.attach(extra)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def extras_for(event, student):
    """The event's extra file as a list, when this person is meant to get it."""
    if event.extra_data and event.extra_name and getattr(student, "send_extra", False):
        return [(event.extra_name, event.extra_type or "application/octet-stream", bytes(event.extra_data))]
    return []


def send_certificate_email(event, student, sender=None, service=None):
    """Email the certificate PDF to the student.

    The PDF is rendered in memory. If `service` (a Gmail API client) is given
    it is used as is; otherwise one is built for `sender` (a user who signed
    in with Google and allowed "send email as you"). With no Gmail access it
    falls back to the shared SMTP account.

    Returns (ok, error_message).
    """
    from . import update_utils as _uu  # imported here: update_utils imports this module
    subject = _uu.clean_subject(f"Your Certificate - {event.name}")
    body = _build_email_body(event, student, None, subject=subject)
    attachment_name = _safe_filename(student.name) + "_certificate.pdf"

    try:
        attachment_bytes = render_certificate_pdf_bytes(event, student.name)
        extras = extras_for(event, student)
        gmail_service = service if service is not None else _get_gmail_service(sender)
        if gmail_service is not None:
            _send_via_gmail_api(gmail_service, student, subject, body, attachment_bytes, attachment_name, extras)
        elif _uu._smtp_configured():
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[student.email],
            )
            email.attach(attachment_name, attachment_bytes, "application/pdf")
            for ex_name, ex_type, ex_data in extras:
                email.attach(ex_name, ex_data, ex_type)
            email.send(fail_silently=False)
        else:
            raise RuntimeError(_uu.AUTH_MESSAGE)

        student.status = "sent"
        student.error_message = ""
        student.save()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - want to surface any send error to the UI
        student.status = "failed"
        student.error_message = str(exc)[:300]
        student.save()
        return False, str(exc)


def send_certificate_batch(event, sender, batch_size=None, budget=None, start=False):
    """Send certificates to up to `batch_size` people, then return so the page
    can ask for the next batch (keeps every request short, so no 502).

    `start=True` first puts earlier failures back in the queue.
    Returns: sent, failed, remaining, stop, error.
    """
    from . import update_utils as _uu  # imported here: update_utils imports this module
    batch_size = batch_size or _uu.BATCH_SIZE
    budget = budget or _uu.TIME_BUDGET_SECONDS
    started = time.monotonic()
    students = event.students

    # put back anyone whose earlier request was killed mid-send
    students.filter(status="sending", updated_at__lt=timezone.now() - _uu.STUCK_AFTER).update(status="pending")
    if start:
        students.filter(status__in=["failed", "sending"]).update(status="pending", error_message="")

    def remaining():
        return students.filter(status__in=["pending", "generated", "sending"]).count()

    service = _get_gmail_service(sender)
    if service is None and not _uu._smtp_configured():
        return {"sent": 0, "failed": 0, "remaining": remaining(), "stop": True, "error": _uu.AUTH_MESSAGE}

    sent = failed = 0
    stop = False
    last_error = ""
    todo = students.filter(status__in=["pending", "generated"])
    check = _uu.get_check_email(event.owner)
    if check:      # your own check copy goes out first, so you can see right away that mail is flowing
        from django.db.models import Case, IntegerField, When

        todo = todo.annotate(_first=Case(When(email__iexact=check, then=0), default=1, output_field=IntegerField())).order_by("_first", "name")
    ids = list(todo.values_list("id", flat=True)[:batch_size])
    for sid in ids:
        if time.monotonic() - started > budget:
            break
        # claim first so two tabs can never mail the same person twice
        if not students.filter(id=sid, status__in=["pending", "generated"]).update(status="sending"):
            continue
        student = students.get(id=sid)
        ok, err = send_certificate_email(event, student, service=service)
        if ok:
            sent += 1
            continue
        last_error = err
        if _uu.is_quota_error(err):
            students.filter(id=sid).update(status="pending", error_message="")
            _uu.note_gmail_refused(event.owner)
            last_error, stop = _uu.QUOTA_MESSAGE, True
            break
        if _uu.is_auth_error(err):
            students.filter(id=sid).update(status="pending", error_message="")
            last_error, stop = _uu.AUTH_MESSAGE, True
            break
        failed += 1

    return {"sent": sent, "failed": failed, "remaining": remaining(), "stop": stop, "error": last_error}
