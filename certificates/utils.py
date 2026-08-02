import os
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
    paths = FONT_PATHS.get(event.font_choice, FONT_PATHS["serif"])
    try:
        return ImageFont.truetype(paths["bold"], size)
    except OSError:
        return ImageFont.load_default()


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


def send_certificate_email(event, student):
    """Email the generated certificate PDF to the student. Returns (ok, error_message)."""
    generate_certificate_pdf(event, student)

    verify_url = f"{settings.SITE_URL}/verify/{student.cert_id}/"

    subject = f"Your Certificate - {event.name}"
    body = (
        f"Hi {student.name},\n\n"
        f"Congratulations! Please find attached your certificate for \"{event.name}\".\n"
        f"Feel free to download it and share it on LinkedIn.\n\n"
        f"You can verify this certificate anytime at:\n{verify_url}\n\n"
        f"Best regards,\n"
        f"{event.organizer or 'The Organizing Team'}"
    )

    try:
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[student.email],
        )
        student.certificate_file.open("rb")
        email.attach(
            f"{student.name.replace(' ', '_')}_certificate.pdf",
            student.certificate_file.read(),
            "application/pdf",
        )
        student.certificate_file.close()
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
