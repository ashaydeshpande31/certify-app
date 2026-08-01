import uuid
from django.db import models
from cloudinary_storage.storage import MediaCloudinaryStorage, RawMediaCloudinaryStorage
class Event(models.Model):
    """One hackathon / workshop / event for which certificates are generated."""

    name = models.CharField(max_length=200)
    organizer = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

   template_image = models.ImageField(upload_to="templates/", storage=MediaCloudinaryStorage())
   excel_file = models.FileField(upload_to="excels/", blank=True, null=True, storage=RawMediaCloudinaryStorage())

    # Text placement, stored as PERCENTAGE of image width/height so it stays
    # correct regardless of the image's actual pixel dimensions.
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
    certificate_file = models.FileField(upload_to="certificates/", blank=True, null=True, storage=RawMediaCloudinaryStorage())
    error_message = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} <{self.email}>"
