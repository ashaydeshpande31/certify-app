import base64
import os
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from io import BytesIO

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


def parse_excel(excel_field):
    """Read an uploaded excel file and return a list of {'name', 'email'} dicts.

    Looks for columns headed (case-insensitively) 'name' and 'email'/'gmail'
    in the first row, in any order/position.
    """
    excel_field.seek(0)
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
        if row is None or all(c is None for c in row):
            continue
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
