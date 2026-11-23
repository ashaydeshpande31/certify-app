import uuid
from django.conf import settings
from django.db import models


class Event(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200)
    organizer = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    template_image = models.ImageField(upload_to="templates/")
    # A copy of the design image kept in the database. Render's disk is wiped on
    # every deploy, so the file above can disappear; this copy never does.
    template_data = models.BinaryField(null=True, blank=True)
    # optional extra file (poster, guide...) sent together with the certificate to chosen people
    extra_data = models.BinaryField(null=True, blank=True)
    extra_name = models.CharField(max_length=200, blank=True, default="")
    extra_type = models.CharField(max_length=100, blank=True, default="")
    template_type = models.CharField(max_length=60, blank=True, default="")
    excel_file = models.FileField(upload_to="excels/", blank=True, null=True)

    message = models.TextField(
        blank=True,
        help_text='A personal note included in the certificate email, e.g. "Thanks for attending!"',
    )

    name_x_percent = models.FloatField(default=50.0)
    name_y_percent = models.FloatField(default=50.0)
    font_size = models.PositiveIntegerField(default=48)
    font_choice = models.CharField(
        max_length=30,
        default="serif",
        choices=[("serif", "Serif (Elegant)"), ("sans", "Sans (Modern)"), ("script", "Script (Handwritten)")],
    )
    font_color = models.CharField(max_length=7, default="#1B2A4A")
    text_align = models.CharField(
        max_length=10, default="center", choices=[("left", "Left"), ("center", "Center"), ("right", "Right")]
    )

    is_configured = models.BooleanField(default=False)
    is_quick_send = models.BooleanField(default=False, help_text="True if this event uses quick-send mode (add one person at a time)")

    def __str__(self):
        return self.name

    @property
    def total_students(self):
        return self.students.count()

    @property
    def sent_count(self):
        return self.students.filter(status="sent").count()


class Student(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("generated", "Generated"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="students")
    name = models.CharField(max_length=200)
    email = models.EmailField()
    cert_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    certificate_file = models.FileField(upload_to="certificates/", blank=True, null=True)
    error_message = models.CharField(max_length=300, blank=True)
    send_extra = models.BooleanField(default=False, help_text="Also attach the event's extra file to this person's email.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["event", "status"], name="cert_stud_event_status_idx")]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class UpdateCampaign(models.Model):
    """A plain "send an update" mail to a list of people (no certificate).

    Used for things like hackathon announcements: one subject, one message
    exactly as the organiser typed it, an optional poster/photos, and a
    recipient list imported from a file.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="update_campaigns",
    )
    subject = models.CharField(max_length=200)
    message = models.TextField(help_text="Sent to every recipient exactly as written.")
    created_at = models.DateTimeField(auto_now_add=True)
    auto_continue = models.BooleanField(
        default=False,
        help_text="Keep sending the pending people automatically when the daily Gmail limit allows.",
    )
    auto_status = models.CharField(max_length=200, blank=True, default="")

    def __str__(self):
        return self.subject

    @property
    def total(self):
        return self.recipients.count()

    @property
    def sent_count(self):
        return self.recipients.filter(status="sent").count()

    @property
    def failed_count(self):
        return self.recipients.filter(status="failed").count()

    @property
    def pending_count(self):
        return self.recipients.filter(status__in=["pending", "sending"]).count()


class UpdateRecipient(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("sending", "Sending"),
        ("sent", "Sent"),
        ("failed", "Failed"),
    ]

    campaign = models.ForeignKey(UpdateCampaign, on_delete=models.CASCADE, related_name="recipients")
    name = models.CharField(max_length=200)
    email = models.EmailField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    error_message = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["campaign", "status"], name="cert_updrec_camp_status_idx")]

    def __str__(self):
        return f"{self.name} <{self.email}>"


class ExternalUsage(models.Model):
    """Emails the organiser says they already sent from Gmail itself today.

    Certify can only count the mails it sent, but Gmail's daily limit counts
    every mail from the account. The organiser tells us how many went out
    elsewhere, and that number counts in the 24-hour window.
    """

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="external_usage")
    count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.owner} sent {self.count} outside Certify"


class UpdateAttachment(models.Model):
    """Optional poster / photo / file attached to every mail of a campaign.

    The bytes live in the database (not on disk) so they survive Render
    redeploys, which wipe the local filesystem.
    """

    campaign = models.ForeignKey(UpdateCampaign, on_delete=models.CASCADE, related_name="attachments")
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, default="application/octet-stream")
    data = models.BinaryField()
    size = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.filename


class SenderSetting(models.Model):
    """Per-user settings. `check_email` is the address that quietly gets a copy of every
    certificate / update batch, so the organiser can see the mail really arrived.
    No row = use the Google account's own address; a row with a blank address = switched off."""

    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sender_setting")
    check_email = models.EmailField(blank=True)

    def __str__(self):
        return f"{self.owner}: {self.check_email or 'no check copy'}"
