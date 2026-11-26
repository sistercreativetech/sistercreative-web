from django import forms

from apps.accounts.models import User
from apps.portfolio import services as portfolio_services
from apps.portfolio.models import Category, Project


class MemberStatusForm(forms.Form):
    status = forms.ChoiceField(choices=User.Status.choices)


class MemberQuotaForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["daily_message_quota"]
        widgets = {"daily_message_quota": forms.NumberInput(attrs={"min": 0, "max": 5000})}


class ProjectForm(forms.ModelForm):
    tags_text = forms.CharField(
        label="Teknologi / tag",
        required=False,
        max_length=300,
        help_text="Pisahkan dengan koma, contoh: n8n, Google Sheets, WhatsApp.",
    )

    class Meta:
        model = Project
        fields = [
            "title",
            "category",
            "summary",
            "description",
            "client_name",
            "year",
            "cover_image",
            "cover_alt",
            "project_url",
            "is_published",
            "is_featured",
            "order",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 8}),
            "cover_image": forms.ClearableFileInput(
                attrs={"accept": "image/jpeg,image/png,image/webp"}
            ),
            "year": forms.NumberInput(attrs={"min": 2000, "max": 2100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tags_text"].initial = portfolio_services.tags_as_text(self.instance)

    def save(self, commit=True):
        project = super().save(commit=commit)
        if commit:
            portfolio_services.set_project_tags(project, self.cleaned_data.get("tags_text", ""))
        return project


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "order"]
