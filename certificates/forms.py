from django import forms
from .models import Event


class EventCreateForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["name", "organizer", "template_image", "excel_file"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. HackNova 2026 - Participation Certificate"}),
            "organizer": forms.TextInput(attrs={"placeholder": "e.g. College Tech Council (optional)"}),
        }


class PositionForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "name_x_percent",
            "name_y_percent",
            "font_size",
            "font_choice",
            "font_color",
            "text_align",
        ]
        widgets = {
            "name_x_percent": forms.HiddenInput(),
            "name_y_percent": forms.HiddenInput(),
        }
