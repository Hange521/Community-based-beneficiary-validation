from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .models import Beneficiary, Grievance, Program, ValidatorAssignment


User = get_user_model()
VALIDATOR_GROUP = "Validator"


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    
class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = ["name", "maximum_monthly_income", "minimum_residency_months", "vulnerable_sector_only", "is_active"]
        widgets = {"maximum_monthly_income": forms.NumberInput(attrs={"step": "0.01", "min": "0"})}


class RegistryImportForm(forms.Form):
    file = forms.FileField(label="Beneficiary CSV file")

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if not uploaded_file.name.lower().endswith(".csv"):
            raise forms.ValidationError("Choose a CSV file.")
        if uploaded_file.size > 2_000_000:
            raise forms.ValidationError("The CSV file must be 2 MB or smaller.")
        return uploaded_file


class BeneficiaryForm(forms.ModelForm):
    validators = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text="Assign up to three validators for independent community review.",
    )

    class Meta:
        model = Beneficiary
        fields = [
            "full_name",
            "birth_year",
            "household_size",
            "monthly_household_income",
            "residency_months",
            "vulnerability",
            "program",
            "barangay",
            "purok",
            "address_note",
            "registration_latitude",
            "registration_longitude",
            "contact_number",
            "photo",
            "consent_recorded",
        ]
        widgets = {
            "monthly_household_income": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
            "birth_year": forms.NumberInput(attrs={"min": "1900", "max": "2026"}),
            "residency_months": forms.NumberInput(attrs={"min": "0"}),
            "photo": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "registration_latitude": forms.HiddenInput(),
            "registration_longitude": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["validators"].queryset = User.objects.filter(
            is_active=True, groups__name=VALIDATOR_GROUP
        ).order_by("first_name", "username").distinct()
        self.fields["program"].queryset = Program.objects.filter(is_active=True)
        self.fields["photo"].help_text = "Optional image, up to 5 MB. Record consent before attaching a photo."

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > 5 * 1024 * 1024:
            raise forms.ValidationError("The photo must be 5 MB or smaller.")
        return photo

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("photo") and not cleaned_data.get("consent_recorded"):
            self.add_error("photo", "Record consent before attaching a photo.")
        latitude = cleaned_data.get("registration_latitude")
        longitude = cleaned_data.get("registration_longitude")
        if bool(latitude) != bool(longitude):
            self.add_error("registration_latitude", "Select a complete map location.")
        if (latitude or longitude) and not cleaned_data.get("consent_recorded"):
            self.add_error("registration_latitude", "Record consent before saving a location pin.")
        return cleaned_data

    def clean_validators(self):
        validators = self.cleaned_data["validators"]
        if validators.count() > 3:
            raise forms.ValidationError("Assign no more than three validators to one record.")
        return validators


class BeneficiaryLocationForm(forms.ModelForm):
    class Meta:
        model = Beneficiary
        fields = ["registration_latitude", "registration_longitude"]
        widgets = {
            "registration_latitude": forms.HiddenInput(),
            "registration_longitude": forms.HiddenInput(),
        }

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get("registration_latitude")
        longitude = cleaned_data.get("registration_longitude")
        if bool(latitude) != bool(longitude):
            self.add_error("registration_latitude", "Select a complete map location.")
        return cleaned_data


class EmployeeCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    password = forms.CharField(min_length=10, widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("That username is already in use.")
        return username


class AssignmentForm(forms.Form):
    validators = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Up to three validators may be assigned to each beneficiary.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["validators"].queryset = User.objects.filter(
            is_active=True, groups__name=VALIDATOR_GROUP
        ).order_by("first_name", "username").distinct()

    def clean_validators(self):
        validators = self.cleaned_data["validators"]
        if validators.count() > 3:
            raise forms.ValidationError("Assign no more than three validators to one record.")
        return validators


class ValidatorDecisionForm(forms.ModelForm):
    class Meta:
        model = ValidatorAssignment
        fields = [
            "decision",
            "verification_method",
            "identity_checked",
            "residency_confirmed",
            "household_details_reviewed",
            "note",
            "latitude",
            "longitude",
        ]
        widgets = {
            "decision": forms.RadioSelect(
                choices=[
                    (ValidatorAssignment.Decision.CONFIRMED, "Confirm household"),
                    (ValidatorAssignment.Decision.DISPUTED, "Dispute details"),
                    (ValidatorAssignment.Decision.FLAGGED, "Flag for committee"),
                ]
            ),
            "verification_method": forms.Select(),
            "note": forms.Textarea(attrs={"rows": 2, "maxlength": 500}),
            "latitude": forms.HiddenInput(),
            "longitude": forms.HiddenInput(),
        }

    def clean_decision(self):
        decision = self.cleaned_data["decision"]
        if decision == ValidatorAssignment.Decision.PENDING:
            raise forms.ValidationError("Choose a validation outcome.")
        return decision

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get("decision")
        if decision == ValidatorAssignment.Decision.CONFIRMED:
            required_checks = {
                "identity_checked": "Confirm the resident's identity",
                "residency_confirmed": "Confirm residency in this community",
                "household_details_reviewed": "Review the household details",
            }
            for field, label in required_checks.items():
                if not cleaned_data.get(field):
                    self.add_error(field, f"{label} before confirming the household.")
            if not cleaned_data.get("verification_method"):
                self.add_error("verification_method", "Choose how the community validation was completed.")
        return cleaned_data


class GrievanceForm(forms.ModelForm):
    class Meta:
        model = Grievance
        fields = ["beneficiary", "resident_name", "contact_number", "reason"]
        widgets = {"reason": forms.Textarea(attrs={"rows": 3, "maxlength": 1200})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["beneficiary"].queryset = Beneficiary.objects.order_by("full_name")
        self.fields["beneficiary"].required = False


class GrievanceResolutionForm(forms.ModelForm):
    class Meta:
        model = Grievance
        fields = ["status", "resolution_note"]
        widgets = {"resolution_note": forms.Textarea(attrs={"rows": 2, "maxlength": 500})}


class BeneficiaryResolutionForm(forms.ModelForm):
    class Meta:
        model = Beneficiary
        fields = ["decision"]
        widgets = {"decision": forms.Select(choices=[
            (Beneficiary.Decision.APPROVED, "Approve"),
            (Beneficiary.Decision.REJECTED, "Reject"),
            (Beneficiary.Decision.NEEDS_REVIEW, "Needs committee review"),
        ])}