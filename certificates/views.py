from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
import logging
import re
from io import BytesIO

from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from PIL import Image
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.defaults import server_error as _default_server_error
from django.views.decorators.http import require_POST
from django.utils import timezone

from .forms import EventCreateForm
from .models import Event, Student, UpdateCampaign
from .email_tools import suggest_email, tidy_name
from .utils import (
    get_template_bytes,
    name_needs_shrink,
    parse_excel,
    render_certificate_pdf_bytes,
    send_certificate_batch,
    send_certificate_email,
    store_template_copy,
)
from .update_utils import ALLOWED_ATTACHMENT_EXTENSIONS, DAILY_LIMIT, IMAGE_EXTENSIONS, guess_content_type, rows_from_photo_emails, sent_last_24h


logger = logging.getLogger(__name__)

_DB_DOWN_NAMES = {"OperationalError", "InterfaceError"}


def _is_database_down(exc):
    """True when `exc` (or what caused it) is a database connection failure,
    e.g. the database expired, was deleted, or DATABASE_URL points nowhere."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if any(c.__name__ in _DB_DOWN_NAMES for c in type(exc).__mro__):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def server_error(request):
    """Custom 500 page. If the database can't be reached, show a friendly
    "paused" page (no database needed to draw it) instead of a raw error."""
    import sys

    exc = sys.exc_info()[1]
    if _is_database_down(exc):
        logger.error("DATABASE UNAVAILABLE - check DATABASE_URL / whether the database expired: %r", exc)
        # Rendered without a request on purpose: context processors would
        # touch the database again and fail the same way.
        html = render_to_string("certificates/maintenance.html")
        response = HttpResponse(html, status=503)
        response["Retry-After"] = "600"
        response["Cache-Control"] = "no-store"
        return response
    return _default_server_error(request)


def privacy_policy(request):
    return render(request, "certificates/privacy.html", {"last_updated": timezone.now().strftime("%B %Y")})


def robots_txt(request):
    body = "User-agent: *\nAllow: /$\nAllow: /privacy/\nAllow: /terms/\nDisallow: /\n"
    return HttpResponse(body, content_type="text/plain")


def terms_of_service(request):
    return render(request, "certificates/terms.html", {"last_updated": timezone.now().strftime("%B %Y")})


def home(request):
    if request.user.is_authenticated:
        # counts come from the same query (no extra query per card)
        events = (
            Event.objects.filter(owner=request.user)
            .annotate(n_students=Count("students", distinct=True), n_sent=Count("students", filter=Q(students__status="sent"), distinct=True))
            .order_by("-created_at")
        )
        update_campaigns = (
            UpdateCampaign.objects.filter(owner=request.user)
            .annotate(
                n_total=Count("recipients", distinct=True),
                n_sent=Count("recipients", filter=Q(recipients__status="sent"), distinct=True),
                n_pending=Count("recipients", filter=Q(recipients__status__in=["pending", "sending"]), distinct=True),
            )
            .order_by("-created_at")
        )
    else:
        events = Event.objects.none()
        update_campaigns = UpdateCampaign.objects.none()
    return render(request, "certificates/home.html", {"events": events, "update_campaigns": update_campaigns})


@login_required
def create_event(request):
    if request.method == "POST":
        is_quick_send = request.POST.get("participant-mode") == "quick-send"
        form = EventCreateForm(request.POST, request.FILES, is_quick_send=is_quick_send)
        if form.is_valid():
            # Read the participant list FIRST (before saving anything), so a photo or an empty file
            # is rejected straight away instead of after the design image has been stored.
            rows = []
            if not is_quick_send:
                try:
                    up = form.cleaned_data["excel_file"]
                    if (up.name or "").lower().endswith(IMAGE_EXTENSIONS):
                        rows = rows_from_photo_emails(request.POST.get("photo_emails", ""))   # read from the photo in the browser
                    else:
                        rows = parse_excel(up)
                except ValueError as exc:
                    messages.error(request, str(exc))
                    return redirect("create_event")
                except Exception:  # noqa: BLE001 - unreadable file
                    rows = []
                if not rows:
                    messages.error(request, "No email found in that file. Please upload an Excel, CSV or PDF list with Name and Email columns.")
                    return redirect("create_event")
            event = form.save(commit=False)
            event.owner = request.user
            event.is_quick_send = is_quick_send
            event.save()
            try:
                store_template_copy(event)
            except Exception:  # noqa: BLE001 - the design is re-read from disk on first use
                logger.exception("Could not copy the design image into the database")
            
            # Only parse and import students if NOT in quick-send mode
            if not is_quick_send:
                good, bad, dupes, seen = [], [], [], set()
                for r in rows:
                    name = tidy_name(r["name"])
                    email = r["email"].strip()
                    shown = f"{name} {email}".strip()
                    try:
                        validate_email(email)
                    except DjangoValidationError:
                        bad.append(shown)
                        continue
                    key = (name.lower(), email.lower())
                    if not name or key in seen:
                        (dupes if name else bad).append(shown)
                        continue
                    seen.add(key)
                    good.append(Student(event=event, name=name, email=email))
                if not good:
                    event.delete()
                    messages.error(request, "No valid student rows found in that Excel sheet.")
                    return redirect("create_event")
                Student.objects.bulk_create(good)
                request.session[f"import_report_event_{event.id}"] = {
                    "loaded": len(good),
                    "bad": bad[:50], "bad_n": len(bad),
                    "dupes": dupes[:50], "dupe_n": len(dupes),
                }
                messages.success(request, f"Imported {len(good)} students. Now position the name on your certificate.")
            else:
                messages.success(request, "Event created! Now position the name on your certificate.")
            
            return redirect("position_certificate", event_id=event.id)
    else:
        form = EventCreateForm()
    return render(request, "certificates/create_event.html", {"form": form})


@login_required
def position_certificate(request, event_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)

    if request.method == "POST":
        new_design = request.FILES.get("template_image")
        if new_design:
            if new_design.size > 8 * 1024 * 1024:
                messages.error(request, "That design image is too big. Please keep it under 8 MB.")
                return redirect("position_certificate", event_id=event.id)
            try:
                Image.open(new_design).verify()
            except Exception:  # noqa: BLE001
                messages.error(request, "That file isn't a valid image. Please upload a PNG or JPG.")
                return redirect("position_certificate", event_id=event.id)
            new_design.seek(0)
            event.template_image = new_design
            event.save()
            store_template_copy(event)
        event.name_x_percent = float(request.POST.get("name_x_percent", 50))
        event.name_y_percent = float(request.POST.get("name_y_percent", 50))
        event.font_size = int(request.POST.get("font_size", 48))
        event.font_choice = request.POST.get("font_choice", "serif")
        event.font_color = request.POST.get("font_color", "#1B2A4A")
        event.text_align = request.POST.get("text_align", "center")
        event.is_configured = True
        event.save()
        messages.success(request, "Certificate layout saved.")
        return redirect("student_list", event_id=event.id)

    names = list(event.students.values_list("name", flat=True))
    longest = sorted(names, key=len, reverse=True)[:3]
    try:
        get_template_bytes(event)
        template_missing = False
    except ValueError:
        template_missing = True
    return render(
        request,
        "certificates/position_certificate.html",
        {"event": event, "longest_names": longest, "template_missing": template_missing},
    )


@login_required
def student_list(request, event_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    students = event.students.all()
    pending_to_send = students.exclude(status="sent").count()
    report = request.session.pop(f"import_report_event_{event.id}", None)
    typos = []
    for st in students.exclude(status="sent"):
        fix = suggest_email(st.email)
        if fix:
            typos.append({"id": st.id, "name": st.name, "email": st.email, "fix": fix})
    shrunk = []
    template_missing = False
    try:
        width = Image.open(BytesIO(get_template_bytes(event))).size[0]
        if event.is_configured:
            shrunk = name_needs_shrink(event, width, [st.name for st in students.exclude(status="sent")])
    except ValueError:
        template_missing = True
    except Exception:  # noqa: BLE001 - unreadable image
        shrunk = []
    shrunk = sorted(shrunk, key=lambda x: x[1])
    return render(
        request,
        "certificates/student_list.html",
        {
            "event": event,
            "students": students,
            "pending_to_send": pending_to_send,
            "extra_count": students.filter(send_extra=True).count() if event.extra_name else 0,
            "report": report,
            "typos": typos,
            "template_missing": template_missing,
            "shrunk_n": len(shrunk),
            "shrunk": [{"name": n, "pct": round(sc * 100)} for n, sc in shrunk[:10]],
        },
    )


@login_required
@require_POST
def update_message(request, event_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    event.message = request.POST.get("message", "").strip()
    event.save(update_fields=["message"])
    messages.success(request, "Message updated. It will be included in future emails for this event.")
    return redirect("student_list", event_id=event.id)


@login_required
@require_POST
def add_quick_send_student(request, event_id):
    """Add a single student in quick-send mode"""
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    
    if not event.is_quick_send:
        messages.error(request, "This event is not in quick-send mode.")
        return redirect("student_list", event_id=event.id)

    name = tidy_name(request.POST.get("name", ""))
    email = request.POST.get("email", "").strip()

    if not name:
        messages.error(request, "Name can't be empty.")
        return redirect("student_list", event_id=event.id)

    try:
        validate_email(email)
    except DjangoValidationError:
        messages.error(request, f'"{email}" doesn\'t look like a valid email address.')
        return redirect("student_list", event_id=event.id)

    # Create the student
    Student.objects.create(event=event, name=name, email=email)
    messages.success(request, f"Added {name}. Click 'Send' to generate and send their certificate.")
    return redirect("student_list", event_id=event.id)


@login_required
@require_POST
def update_student(request, event_id, student_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    student = get_object_or_404(Student, id=student_id, event=event)

    name = tidy_name(request.POST.get("name", ""))
    email = request.POST.get("email", "").strip()

    if not name:
        messages.error(request, "Name can't be empty.")
        return redirect("student_list", event_id=event.id)

    try:
        validate_email(email)
    except DjangoValidationError:
        messages.error(request, f'"{email}" doesn\'t look like a valid email address — nothing was changed.')
        return redirect("student_list", event_id=event.id)

    changed = student.name != name or student.email != email
    student.name = name
    student.email = email

    if changed and student.status in ("sent", "generated", "failed"):
        # Any existing certificate was rendered with the old name, and if this
        # was already "sent", that email went to the old address — clear it
        # out and mark pending so the corrected version gets regenerated and
        # (re)sent deliberately, instead of silently looking done.
        if student.certificate_file:
            student.certificate_file.delete(save=False)
        student.status = "pending"
        student.error_message = ""

    student.save()
    messages.success(request, f"Updated {student.name}'s details.")
    return redirect("student_list", event_id=event.id)


@login_required
@require_POST
def send_batch(request, event_id):
    """Send the next few certificates and report progress. The page calls this
    again and again until nothing is left, so no single request runs long."""
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    result = send_certificate_batch(event, request.user, start=request.POST.get("start") == "1")
    students = event.students
    result["total"] = students.count()
    result["sent_total"] = students.filter(status="sent").count()
    result["failed_total"] = students.filter(status="failed").count()
    result["used_24h"] = sent_last_24h(request.user)
    result["daily_limit"] = DAILY_LIMIT
    return JsonResponse(result)


@login_required
@require_POST
def send_one(request, event_id, student_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    student = get_object_or_404(Student, id=student_id, event=event)
    ok, err = send_certificate_email(event, student, sender=request.user)
    if ok:
        messages.success(request, f"Certificate sent to {student.name}.")
    else:
        messages.error(request, f"Failed to send to {student.name}: {err}")
    return redirect("student_list", event_id=event.id)


@login_required
@require_POST
def delete_event(request, event_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    name = event.name
    event.delete()
    messages.success(request, f'"{name}" was deleted.')
    return redirect("home")


def verify_certificate(request, cert_id):
    student = get_object_or_404(Student, cert_id=cert_id)
    return render(request, "certificates/verify.html", {"student": student, "event": student.event})


@login_required
@require_POST
def fix_student_email(request, event_id):
    """Apply the suggested spelling to one student, or to everyone flagged."""
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    only = request.POST.get("student_id")
    qs = event.students.exclude(status="sent")
    if only:
        qs = qs.filter(id=only)
    fixed = 0
    for st in qs:
        fix = suggest_email(st.email)
        if not fix:
            continue
        st.email = fix
        if st.status == "failed":
            st.status = "pending"
            st.error_message = ""
        st.save()
        fixed += 1
    if fixed:
        messages.success(request, f"Fixed {fixed} email address(es).")
    else:
        messages.info(request, "Nothing to fix.")
    return redirect("student_list", event_id=event.id)


MAX_EXTRA_BYTES = 3 * 1024 * 1024  # keeps every email small and fast


@login_required
@require_POST
def event_extra_upload(request, event_id):
    """Attach one extra file (poster, guide...) that goes with the certificate
    to the people you choose."""
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    f = request.FILES.get("extra_file")
    if not f:
        messages.error(request, "Choose a file first.")
        return redirect("student_list", event_id=event.id)
    name = re.sub(r"[^\w .()\-]", "_", f.name.replace("\\", "/").split("/")[-1]).strip()[:120] or "attachment"
    if not name.lower().endswith(ALLOWED_ATTACHMENT_EXTENSIONS):
        messages.error(request, "That file type is not allowed. Use an image, PDF, Word, PowerPoint, Excel or text file.")
        return redirect("student_list", event_id=event.id)
    if f.size > MAX_EXTRA_BYTES:
        messages.error(request, "That file is over 3 MB. Make it smaller so the emails stay fast.")
        return redirect("student_list", event_id=event.id)
    event.extra_data = f.read()
    event.extra_name = name
    event.extra_type = guess_content_type(name)
    event.save(update_fields=["extra_data", "extra_name", "extra_type"])
    event.students.update(send_extra=False)
    messages.success(request, f"Added {name}. Now tick the people who should get it, or press 'Everyone'.")
    return redirect("student_list", event_id=event.id)


@login_required
@require_POST
def event_extra_remove(request, event_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    event.extra_data = None
    event.extra_name = ""
    event.extra_type = ""
    event.save(update_fields=["extra_data", "extra_name", "extra_type"])
    event.students.update(send_extra=False)
    messages.success(request, "Extra file removed.")
    return redirect("student_list", event_id=event.id)


@login_required
@require_POST
def event_extra_assign(request, event_id):
    """Everyone / nobody, for people who have not been sent yet."""
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    if event.extra_name:
        event.students.exclude(status="sent").update(send_extra=(request.POST.get("mode") == "all"))
    return redirect("student_list", event_id=event.id)


@login_required
@require_POST
def student_toggle_extra(request, event_id, student_id):
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    student = get_object_or_404(Student, id=student_id, event=event)
    student.send_extra = request.POST.get("value") == "1"
    student.save(update_fields=["send_extra"])
    return JsonResponse({"ok": True, "send_extra": student.send_extra})


@login_required
def event_template_image(request, event_id):
    """The design image, served from the database (works after redeploys)."""
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    try:
        data = get_template_bytes(event)
    except ValueError:
        raise Http404("design image missing")
    response = HttpResponse(data, content_type=event.template_type or "image/png")
    response["Cache-Control"] = "private, max-age=3600"
    return response


@login_required
def student_certificate_pdf(request, event_id, student_id):
    """Preview a person's certificate. It is drawn on the spot, so it always
    matches the current layout and never depends on stored files."""
    event = get_object_or_404(Event, id=event_id, owner=request.user)
    student = get_object_or_404(Student, id=student_id, event=event)
    try:
        pdf = render_certificate_pdf_bytes(event, student.name)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("position_certificate", event_id=event.id)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="certificate.pdf"'
    response["Cache-Control"] = "private, no-store"
    return response
