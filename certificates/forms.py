from django import forms
from .models import Event


class EventCreateForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["name", "organizer", "template_image", "excel_file", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. HackNova 2026 - Participation Certificate"}),
            "organizer": forms.TextInput(attrs={"placeholder": "e.g. College Tech Council (optional)"}),
            "message": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "e.g. Thanks so much for attending HackNova 2026 — it was great having you there!",
                }
            ),
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
