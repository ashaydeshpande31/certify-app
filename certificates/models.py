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
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} <{self.email}>"
