import base64
import csv
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

    excel_field.seek(0)

    if filename.endswith(".csv"):
        text = excel_field.read().decode("utf-8-sig", errors="ignore")
        reader = csv.reader(StringIO(text))
        rows = list(reader)
    else:
        wb = openpyxl.load_workbook(BytesIO(excel_field.read()), data_only=True)
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


def get_font(event, size=None):
    size = size or event.font_size
    candidates = [
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/timesbd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def render_certificate_image(event, student_name):
    """Return a PIL Image with the student's name drawn onto the event template."""
    event.template_image.open("rb")
    base = Image.open(event.template_image).convert("RGB")
    event.template_image.close()

    draw = ImageDraw.Draw(base)
    w, h = base.size

    x = w * (event.name_x_percent / 100.0)
    y = h * (event.name_y_percent / 100.0)

    font = get_font(event)
    color = hex_to_rgb(event.font_color)

    anchor = {"left": "lm", "center": "mm", "right": "rm"}[event.text_align]
    draw.text((x, y), student_name, font=font, fill=color, anchor=anchor)

    return base


def generate_certificate_pdf(event, student):
    """Render the certificate for a student and save it as a PDF on the Student."""
    img = render_certificate_image(event, student.name)

    buffer = BytesIO()
    img.save(buffer, format="PDF")
    buffer.seek(0)

    filename = f"certificate_{student.cert_id}.pdf"
    student.certificate_file.save(filename, ContentFile(buffer.read()), save=False)
    student.status = "generated"
    student.save()
    return student.certificate_file


def _build_email_body(event, student, verify_url):
    lines = [
        f"Hi {student.name},",
        "",
        f'Congratulations! Please find attached your certificate for "{event.name}".',
        "Feel free to download it and share it on LinkedIn.",
    ]
    if event.message:
        lines += ["", event.message.strip()]
    lines += [
        "",
        f"You can verify this certificate anytime at:\n{verify_url}",
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
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.token = creds.token
            token.save(update_fields=["token"])
        return build("gmail", "v1", credentials=creds, cache_discovery=False)
    except Exception:
        return None


def _send_via_gmail_api(service, student, subject, body, attachment_bytes, attachment_name):
    message = MIMEMultipart()
    message["to"] = student.email
    message["subject"] = subject
    message.attach(MIMEText(body, "plain"))

    part = MIMEBase("application", "pdf")
    part.set_payload(attachment_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={attachment_name}")
    message.attach(part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def send_certificate_email(event, student, sender=None):
    """Email the generated certificate PDF to the student.

    If `sender` is a logged-in user who has signed in with Google (and
    granted the "send email as you" permission), the certificate is sent
    from that user's own Gmail account via the Gmail API. Otherwise it
    falls back to the shared SMTP account configured via
    EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (or the console backend).

    Returns (ok, error_message).
    """
    generate_certificate_pdf(event, student)

    verify_url = f"{settings.SITE_URL}/verify/{student.cert_id}/"
    subject = f"Your Certificate - {event.name}"
    body = _build_email_body(event, student, verify_url)
    attachment_name = f"{student.name.replace(' ', '_')}_certificate.pdf"

    student.certificate_file.open("rb")
    attachment_bytes = student.certificate_file.read()
    student.certificate_file.close()

    gmail_service = _get_gmail_service(sender)

    try:
        if gmail_service is not None:
            _send_via_gmail_api(gmail_service, student, subject, body, attachment_bytes, attachment_name)
        else:
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[student.email],
            )
            email.attach(attachment_name, attachment_bytes, "application/pdf")
            email.send(fail_silently=False)

        student.status = "sent"
        student.error_message = ""
        student.save()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - want to surface any send error to the UI
        student.status = "failed"
        student.error_message = str(exc)[:300]
        student.save()
        return False, str(exc)
