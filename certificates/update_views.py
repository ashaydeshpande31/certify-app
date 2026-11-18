"""Views for the "Send Updates" section: write one message, upload a
Name/Email list, optionally attach a poster/photos, and mail everyone."""

import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import UpdateAttachment, UpdateCampaign, UpdateRecipient
from .update_utils import (
    ALLOWED_ATTACHMENT_EXTENSIONS,
    MAX_ATTACHMENTS,
    MAX_RECIPIENTS,
    MAX_TOTAL_ATTACHMENT_BYTES,
    clean_subject,
    guess_content_type,
    send_update_batch,
)
from .utils import parse_excel

LIST_EXTENSIONS = (".xlsx", ".xls", ".csv", ".pdf")


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
        key = email.lower()
        if key in seen:
            skipped_dupe += 1
            continue
        seen.add(key)
        good.append({"name": name or email.split("@")[0], "email": email})
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
    attach_files = [f for f in request.FILES.getlist("attachments") if f and f.name]
    context.update({"subject": subject, "message": message})

    errors = []
    if not subject:
        errors.append("Please add a subject line.")
    if not message:
        errors.append("Please write the message you want people to receive.")
    if not list_file:
        errors.append("Please upload a file with your recipients' names and emails.")
    elif not list_file.name.lower().endswith(LIST_EXTENSIONS):
        errors.append("The recipient list must be a .xlsx, .xls, .csv or .pdf file.")

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
            rows = parse_excel(list_file)
        except ValueError as exc:
            errors.append(str(exc))
        except Exception:  # noqa: BLE001 - corrupt / unreadable file
            errors.append("We couldn't read that file. Please upload a valid .xlsx, .xls, .csv or .pdf list.")

    recipients, skipped_bad, skipped_dupe = _clean_recipients(rows)
    if list_file and not errors:
        if not recipients:
            errors.append("No valid Name + Email rows were found in that file.")
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
    return render(
        request,
        "certificates/update_detail.html",
        {
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
    if not subject or not message:
        messages.error(request, "Subject and message can't be empty — nothing was changed.")
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
    UpdateRecipient.objects.create(campaign=campaign, name=name or email.split("@")[0], email=email)
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
    return JsonResponse(result)


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
