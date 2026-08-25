from django.contrib import admin
from .models import Event, Student


class StudentInline(admin.TabularInline):
    model = Student
    extra = 0
    readonly_fields = ["cert_id", "status", "updated_at"]


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ["name", "organizer", "owner", "total_students", "sent_count", "created_at"]
    list_filter = ["owner"]
    inlines = [StudentInline]


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "event", "status", "updated_at"]
    list_filter = ["status", "event"]
    search_fields = ["name", "email"]
