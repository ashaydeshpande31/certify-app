from django import forms
from .models import Event


class EventCreateForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ["name", "organizer", "template_image", "excel_file", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. HackNova 2026 - Participation Certificate"}),
            "organizer": forms.TextInput(attrs={"placeholder": "e.g. College Tech Council (optional)"}),
            "excel_file": forms.ClearableFileInput(attrs={"accept": ".xlsx,.xls,.csv,.pdf"}),
            "message": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "e.g. Thanks so much for attending HackNova 2026 — it was great having you there!",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The model allows this field to be blank (so we can safely roll back
        # an Event if parsing fails), but a new event always needs a list.
        self.fields["excel_file"].required = True

    def clean_excel_file(self):
        excel_file = self.cleaned_data.get("excel_file")
        if not excel_file:
            raise forms.ValidationError("Please upload a participant list (.xlsx, .xls, .csv, or .pdf).")
        name = excel_file.name.lower()
        if not name.endswith((".xlsx", ".xls", ".csv", ".pdf")):
            raise forms.ValidationError(
                "That file doesn't look like a spreadsheet or PDF. Please upload a .xlsx, .xls, .csv, or .pdf file."
            )
        return excel_file


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
