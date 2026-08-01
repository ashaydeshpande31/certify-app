from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import EventCreateForm
from .models import Event, Student
from .utils import parse_excel, generate_certificate_pdf, send_certificate_email


def home(request):
    events = Event.objects.all().order_by("-created_at")
    return render(request, "certificates/home.html", {"events": events})


def create_event(request):
    if request.method == "POST":
        form = EventCreateForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save()
            try:
                rows = parse_excel(event.excel_file)
            except ValueError as exc:
                event.delete()
                messages.error(request, str(exc))
                return redirect("create_event")

            if not rows:
                event.delete()
                messages.error(request, "No valid student rows found in that Excel sheet.")
                return redirect("create_event")

            Student.objects.bulk_create(
                [Student(event=event, name=r["name"], email=r["email"]) for r in rows]
            )
            messages.success(request, f"Imported {len(rows)} students. Now position the name on your certificate.")
            return redirect("position_certificate", event_id=event.id)
    else:
        form = EventCreateForm()
    return render(request, "certificates/create_event.html", {"form": form})


def position_certificate(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    if request.method == "POST":
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

    return render(request, "certificates/position_certificate.html", {"event": event})


def student_list(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    students = event.students.all()
    return render(request, "certificates/student_list.html", {"event": event, "students": students})


@require_POST
def generate_all(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    count = 0
    for student in event.students.exclude(status="sent"):
        generate_certificate_pdf(event, student)
        count += 1
    messages.success(request, f"Generated {count} certificate(s). Review below, then send.")
    return redirect("student_list", event_id=event.id)


@require_POST
def send_all(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    sent, failed = 0, 0
    for student in event.students.exclude(status="sent"):
        ok, _ = send_certificate_email(event, student)
        if ok:
            sent += 1
        else:
            failed += 1
    if sent:
        messages.success(request, f"Emailed {sent} certificate(s) successfully.")
    if failed:
        messages.error(request, f"{failed} email(s) failed to send. Check the status column below.")
    return redirect("student_list", event_id=event.id)


@require_POST
def send_one(request, event_id, student_id):
    event = get_object_or_404(Event, id=event_id)
    student = get_object_or_404(Student, id=student_id, event=event)
    ok, err = send_certificate_email(event, student)
    if ok:
        messages.success(request, f"Certificate sent to {student.name}.")
    else:
        messages.error(request, f"Failed to send to {student.name}: {err}")
    return redirect("student_list", event_id=event.id)


def verify_certificate(request, cert_id):
    student = get_object_or_404(Student, cert_id=cert_id)
    return render(request, "certificates/verify.html", {"student": student, "event": student.event})
