"""Views for the "Send Updates" section: write one message, upload a
Name/Email list, optionally attach a poster/photos, and mail everyone."""

import hmac
import os
import re
import time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Student, UpdateAttachment, UpdateCampaign, UpdateRecipient
from .update_utils import (
    ALLOWED_ATTACHMENT_EXTENSIONS,
    MAX_ATTACHMENTS,
    MAX_RECIPIENTS,
    MAX_TOTAL_ATTACHMENT_BYTES,
    clean_subject,
    guess_content_type,
    parse_recipient_file,
    send_update_batch,
    AUTO_RESERVE,
    BATCH_SIZE,
    DAILY_LIMIT,
    sent_last_24h,
)

LIST_EXTENSIONS = (".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".pdf")


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _parse_pasted(text):
    """One person per line. Accepts 'email', 'Name, email', 'Name - email',
    'Name email' or 'email, Name'. Several emails on one line also work."""
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        found = list(_EMAIL_RE.finditer(line))
        if len(found) == 1:
            m = found[0]
            name = (line[: m.start()] + " " + line[m.end():]).strip(" -,;|\t<>()")
            rows.append({"name": re.sub(r"\s{2,}", " ", name), "email": m.group(0)})
        else:
            rows.extend({"name": "", "email": m.group(0)} for m in found)
    return rows


def _clean_recipients(rows):
    """Validate emails and drop duplicates (same email twice = one mail)."""
    good, skipped_bad, skipped_dupe = [], 0, 0
    seen = set()
    for row in rows:
        name = (row.get("name") or "").strip()
        email = (row.get("email") or "").strip()
        try:
            validate_email(email)
        except DjangoValidationError:
            skipped_bad += 1
            continue
        if len(email) > 254:
            skipped_bad += 1
            continue
        key = email.lower()
        if key in seen:
            skipped_dupe += 1
            continue
        seen.add(key)
        good.append({"name": (name or email.split("@")[0])[:200], "email": email})
    return good, skipped_bad, skipped_dupe


@login_required
def update_create(request):
    context = {
        "subject": "",
        "message": "",
        "max_attachments": MAX_ATTACHMENTS,
        "max_mb": MAX_TOTAL_ATTACHMENT_BYTES // (1024 * 1024),
    }

    if request.method != "POST":
        return render(request, "certificates/update_create.html", context)

    subject = clean_subject(request.POST.get("subject", ""))
    message = request.POST.get("message", "").replace("\r\n", "\n").strip()
    list_file = request.FILES.get("recipients_file")
    pasted_text = request.POST.get("pasted_emails", "")
    attach_files = [f for f in request.FILES.getlist("attachments") if f and f.name]
    context.update({"subject": subject, "message": message, "pasted_emails": pasted_text})

    errors = []
    if not subject:
        errors.append("Please add a subject line.")
    elif len(subject) > 200:
        errors.append("The subject is too long — keep it under 200 characters.")
    if not message:
        errors.append("Please write the message you want people to receive.")
    if not list_file and not pasted_text.strip():
        errors.append("Please upload a recipient file, or type/paste at least one email address.")
    elif list_file and not list_file.name.lower().endswith(LIST_EXTENSIONS):
        errors.append("The recipient list must be an Excel, CSV, TXT or PDF file.")

    if len(attach_files) > MAX_ATTACHMENTS:
        errors.append(f"You can attach at most {MAX_ATTACHMENTS} files.")
    total_bytes = 0
    for f in attach_files:
        if not f.name.lower().endswith(ALLOWED_ATTACHMENT_EXTENSIONS):
            errors.append(f'"{f.name}" isn\'t a supported attachment type (images, PDF, Word, PowerPoint, Excel or text).')
        total_bytes += f.size
    if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
        errors.append(f"Attachments are too big together — keep them under {context['max_mb']} MB in total.")

    rows = []
    if list_file and not errors:
        try:
            rows = parse_recipient_file(list_file)
        except ValueError as exc:
            errors.append(str(exc))
        except Exception:  # noqa: BLE001 - corrupt / unreadable file
            errors.append("We couldn't read that file. Please upload a valid Excel, CSV, TXT or PDF list.")

    if not errors:
        rows = rows + _parse_pasted(pasted_text)
    recipients, skipped_bad, skipped_dupe = _clean_recipients(rows)
    if not errors:
        if not recipients:
            errors.append("No valid email addresses were found.")
        elif len(recipients) > MAX_RECIPIENTS:
            errors.append(f"That list has {len(recipients)} people — the limit per update is {MAX_RECIPIENTS}.")

    if errors:
        for e in errors:
            messages.error(request, e)
        if list_file or attach_files:
            messages.error(request, "Your subject and message were kept, but please choose your files again.")
        return render(request, "certificates/update_create.html", context)

    with transaction.atomic():
        campaign = UpdateCampaign.objects.create(owner=request.user, subject=subject, message=message)
        UpdateRecipient.objects.bulk_create(
            [UpdateRecipient(campaign=campaign, name=r["name"], email=r["email"]) for r in recipients]
        )
        for f in attach_files:
            f.seek(0)
            data = f.read()
            filename = os.path.basename(f.name)
            UpdateAttachment.objects.create(
                campaign=campaign,
                filename=filename,
                content_type=guess_content_type(filename),
                data=data,
                size=len(data),
            )

    note = f"Loaded {len(recipients)} recipient(s)."
    if skipped_dupe:
        note += f" {skipped_dupe} duplicate email(s) skipped."
    if skipped_bad:
        note += f" {skipped_bad} row(s) skipped (invalid email)."
    messages.success(request, note + " Review below, then send.")
    return redirect("update_detail", campaign_id=campaign.id)


@login_required
def update_detail(request, campaign_id):
    campaign = get_object_or_404(UpdateCampaign, id=campaign_id, owner=request.user)
    used = sent_last_24h(request.user)
    left = max(DAILY_LIMIT - used, 0)
    return render(
        request,
        "certificates/update_detail.html",
        {
            "used_24h": used,
            "daily_limit": DAILY_LIMIT,
            "quota_left": left,
            "quota_pct": min(100, round(used * 100 / DAILY_LIMIT)) if DAILY_LIMIT else 0,
            "over_quota": campaign.pending_count > left,
            "cron_ready": bool(os.environ.get("CRON_SECRET")),
            "campaign": campaign,
            "recipients": campaign.recipients.all(),
            "attachments": campaign.attachments.all(),
            "total": campaign.total,
            "sent_count": campaign.sent_count,
            "failed_count": campaign.failed_count,
            "pending_count": campaign.pending_count,
        },
    )


@login_required
@require_POST
def update_edit(request, campaign_id):
    campaign = get_object_or_404(UpdateCampaign, id=campaign_id, owner=request.user)
    subject = clean_subject(request.POST.get("subject", ""))
    message = request.POST.get("message", "").replace("\r\n", "\n").strip()
    if not subject or not message or len(subject) > 200:
        messages.error(request, "Subject and message can't be empty, and the subject must be under 200 characters — nothing was changed.")
        return redirect("update_detail", campaign_id=campaign.id)
    campaign.subject = subject
    campaign.message = message
    campaign.save(update_fields=["subject", "message"])
    messages.success(request, "Saved. People who haven't received it yet will get this version.")
    return redirect("update_detail", campaign_id=campaign.id)


@login_required
@require_POST
def update_add_recipient(request, campaign_id):
    campaign = get_object_or_404(UpdateCampaign, id=campaign_id, owner=request.user)
    name = request.POST.get("name", "").strip()
    email = request.POST.get("email", "").strip()
    try:
        validate_email(email)
    except DjangoValidationError:
        messages.error(request, f'"{email}" doesn\'t look like a valid email address.')
        return redirect("update_detail", campaign_id=campaign.id)
    if campaign.recipients.filter(email__iexact=email).exists():
        messages.error(request, f"{email} is already on this list.")
        return redirect("update_detail", campaign_id=campaign.id)
    if len(email) > 254:
        messages.error(request, "That email address is too long.")
        return redirect("update_detail", campaign_id=campaign.id)
    UpdateRecipient.objects.create(campaign=campaign, name=(name or email.split("@")[0])[:200], email=email)
    messages.success(request, f"Added {email}. Use the send button to mail the pending people.")
    return redirect("update_detail", campaign_id=campaign.id)


@login_required
@require_POST
def update_send_batch(request, campaign_id):
    """Sends one small batch and reports progress as JSON. The page calls this
    repeatedly until nothing is left — keeps every request short so Render
    never times out, even for 300+ people."""
    campaign = get_object_or_404(UpdateCampaign, id=campaign_id, owner=request.user)
    result = send_update_batch(campaign, sender=request.user)
    result["sent_total"] = campaign.sent_count
    result["failed_total"] = campaign.failed_count
    result["total"] = campaign.total
    result["used_24h"] = sent_last_24h(request.user)
    result["daily_limit"] = DAILY_LIMIT
    return JsonResponse(result)


@login_required
@require_POST
def update_toggle_auto(request, campaign_id):
    campaign = get_object_or_404(UpdateCampaign, id=campaign_id, owner=request.user)
    turn_on = request.POST.get("auto") == "on" and campaign.pending_count > 0
    campaign.auto_continue = turn_on
    campaign.auto_status = "Waiting for the next scheduled check." if turn_on else ""
    campaign.save(update_fields=["auto_continue", "auto_status"])
    if turn_on:
        messages.success(request, "Auto-continue is on. The people still waiting will be sent automatically.")
        if not os.environ.get("CRON_SECRET"):
            messages.error(request, "The scheduled link isn't set up yet, so nothing will send on its own. See \"How auto-continue works\" below.")
    else:
        messages.success(request, "Auto-continue is off.")
    return redirect("update_detail", campaign_id=campaign.id)


CRON_BUDGET_SECONDS = 22


@csrf_exempt
def cron_continue(request):
    """Called every minute by cron-job.org. Sends waiting people for every
    update that has auto-continue on, never going past the daily Gmail limit
    (minus a small reserve). Protected by the CRON_SECRET environment
    variable; with no secret set, it does nothing."""
    secret = os.environ.get("CRON_SECRET", "")
    key = request.GET.get("key", "")
    if not secret or not hmac.compare_digest(key.encode(), secret.encode()):
        return JsonResponse({"error": "forbidden"}, status=403)

    started = time.monotonic()
    results = []
    used_by_owner = {}
    campaigns = list(UpdateCampaign.objects.filter(auto_continue=True).select_related("owner").order_by("created_at"))

    for c in campaigns:
        if time.monotonic() - started > CRON_BUDGET_SECONDS:
            break
        owner = c.owner
        used = used_by_owner.get(owner.id)
        if used is None:
            used = sent_last_24h(owner)
        allowed = DAILY_LIMIT - AUTO_RESERVE - used
        sent_now = 0
        status = ""

        while allowed > 0 and time.monotonic() - started < CRON_BUDGET_SECONDS:
            time_left = CRON_BUDGET_SECONDS - (time.monotonic() - started)
            r = send_update_batch(c, owner, batch_size=min(BATCH_SIZE, allowed), budget=time_left)
            done = r["sent"] + r["failed"]
            allowed -= done
            used += done
            sent_now += r["sent"]
            if r["stop"]:
                status = r["error"]
                break
            if r["remaining"] == 0 or done == 0:
                break
        used_by_owner[owner.id] = used

        remaining = c.recipients.filter(status__in=["pending", "sending"]).count()
        if remaining == 0:
            c.auto_continue = False
            c.auto_status = "Finished. Everyone has been sent this update."
        elif status:
            c.auto_status = status[:200]
        elif allowed <= 0:
            c.auto_status = (
                f"Paused: about {used} emails sent in the last 24 hours. "
                "It continues by itself as your Gmail limit frees up."
            )[:200]
        else:
            c.auto_status = f"Sending automatically. {remaining} left."
        c.save(update_fields=["auto_continue", "auto_status"])
        results.append({"campaign": c.id, "sent": sent_now, "remaining": remaining, "status": c.auto_status})

    return JsonResponse({"ok": True, "campaigns": results})


@login_required
@require_POST
def update_reset_failed(request, campaign_id):
    """Put failed (and any stuck 'sending') people back to pending so they get
    another try."""
    campaign = get_object_or_404(UpdateCampaign, id=campaign_id, owner=request.user)
    count = campaign.recipients.filter(status__in=["failed", "sending"]).update(status="pending", error_message="")
    return JsonResponse({"reset": count, "remaining": campaign.recipients.filter(status="pending").count()})


@login_required
@require_POST
def update_delete(request, campaign_id):
    campaign = get_object_or_404(UpdateCampaign, id=campaign_id, owner=request.user)
    subject = campaign.subject
    campaign.delete()
    messages.success(request, f'"{subject}" was deleted.')
    return redirect("home")


@login_required
def delivery_search(request):
    """Powers the "Check delivery" side panel: find a person by name or email
    and say whether each update / certificate mail to them went out."""
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})

    rows = []
    updates = (
        UpdateRecipient.objects.filter(campaign__owner=request.user)
        .filter(Q(email__icontains=q) | Q(name__icontains=q))
        .select_related("campaign")
        .order_by("-updated_at")[:30]
    )
    for r in updates:
        rows.append({
            "kind": "update", "name": r.name, "email": r.email, "title": r.campaign.subject,
            "status": r.status, "error": r.error_message, "stamp": r.updated_at,
            "url": reverse("update_detail", args=[r.campaign_id]),
        })
    certs = (
        Student.objects.filter(event__owner=request.user)
        .filter(Q(email__icontains=q) | Q(name__icontains=q))
        .select_related("event")
        .order_by("-updated_at")[:30]
    )
    for s in certs:
        rows.append({
            "kind": "certificate", "name": s.name, "email": s.email, "title": s.event.name,
            "status": s.status, "error": s.error_message, "stamp": s.updated_at,
            "url": reverse("student_list", args=[s.event_id]),
        })

    rows.sort(key=lambda x: x["stamp"], reverse=True)
    rows = rows[:40]
    for x in rows:
        stamp = x.pop("stamp")
        # pending rows were never mailed, so their time means nothing
        x["when"] = stamp.isoformat() if x["status"] in ("sent", "failed", "generated") else None
    return JsonResponse({"results": rows})
