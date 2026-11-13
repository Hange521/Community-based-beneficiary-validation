import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def make_beneficiary_id():
	return f"BVS-{timezone.now():%Y}-{uuid.uuid4().hex[:8].upper()}"


class Program(models.Model):
	name = models.CharField(max_length=120, unique=True)
	maximum_monthly_income = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	minimum_residency_months = models.PositiveSmallIntegerField(default=0)
	vulnerable_sector_only = models.BooleanField(default=False)
	is_active = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["name"]

	def __str__(self):
		return self.name


class Beneficiary(models.Model):
	class Vulnerability(models.TextChoices):
		NONE = "none", "No declared sector"
		OLDER_PERSON = "older_person", "Older person"
		PERSON_WITH_DISABILITY = "disability", "Person with disability"
		SOLO_PARENT = "solo_parent", "Solo parent"
		INDIGENOUS_PEOPLE = "indigenous", "Indigenous people"
		DISASTER_AFFECTED = "disaster_affected", "Disaster-affected household"

	class Decision(models.TextChoices):
		PENDING = "pending", "Pending review"
		APPROVED = "approved", "Approved"
		REJECTED = "rejected", "Rejected"
		NEEDS_REVIEW = "needs_review", "Needs committee review"

	beneficiary_id = models.CharField(max_length=24, unique=True, default=make_beneficiary_id, editable=False)
	full_name = models.CharField(max_length=160)
	birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
	household_size = models.PositiveSmallIntegerField(default=1)
	monthly_household_income = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
	residency_months = models.PositiveSmallIntegerField(default=0)
	vulnerability = models.CharField(max_length=24, choices=Vulnerability.choices, default=Vulnerability.NONE)
	barangay = models.CharField(max_length=100)
	purok = models.CharField(max_length=80)
	address_note = models.CharField(max_length=180, blank=True)
	registration_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	registration_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	contact_number = models.CharField(max_length=24, blank=True)
	photo = models.ImageField(upload_to="beneficiary_photos/", blank=True, null=True)
	consent_recorded = models.BooleanField(default=False)
	decision = models.CharField(max_length=16, choices=Decision.choices, default=Decision.PENDING)
	program = models.ForeignKey(Program, on_delete=models.PROTECT, related_name="beneficiaries", null=True, blank=True)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="registered_beneficiaries")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [models.Index(fields=["barangay", "purok"]), models.Index(fields=["decision"])]

	def __str__(self):
		return f"{self.full_name} ({self.beneficiary_id})"

	def eligibility_issues(self):
		if not self.program:
			return []
		issues = []
		if self.monthly_household_income is None and self.program.maximum_monthly_income is not None:
			issues.append("Household income is not recorded")
		elif self.program.maximum_monthly_income is not None and self.monthly_household_income > self.program.maximum_monthly_income:
			issues.append("Household income exceeds the program threshold")
		if self.residency_months < self.program.minimum_residency_months:
			issues.append("Residency is below the program minimum")
		if self.program.vulnerable_sector_only and self.vulnerability == self.Vulnerability.NONE:
			issues.append("Program requires a vulnerable-sector indicator")
		return issues

	def duplicate_candidates(self):
		return Beneficiary.objects.filter(
			full_name__iexact=self.full_name.strip(),
			barangay__iexact=self.barangay.strip(),
			purok__iexact=self.purok.strip(),
		).exclude(pk=self.pk)

	def validation_summary(self):
		assignments = self.assignments.all()
		confirmed = assignments.filter(decision=ValidatorAssignment.Decision.CONFIRMED).count()
		disputed = assignments.filter(decision=ValidatorAssignment.Decision.DISPUTED).count()
		flagged = assignments.filter(decision=ValidatorAssignment.Decision.FLAGGED).count()
		if disputed or flagged:
			return "committee_review"
		if confirmed >= 2:
			return "consensus_confirmed"
		return "awaiting_validators"


class ValidatorAssignment(models.Model):
	class VerificationMethod(models.TextChoices):
		HOUSEHOLD_VISIT = "household_visit", "Household visit"
		RESIDENT_INTERVIEW = "resident_interview", "Resident interview"
		COMMUNITY_ATTESTATION = "community_attestation", "Barangay or purok attestation"
		RECORD_REVIEW = "record_review", "Program record review"
		ASSISTED_REVIEW = "assisted_review", "Assisted community review"

	class Decision(models.TextChoices):
		PENDING = "pending", "Pending"
		CONFIRMED = "confirmed", "Confirmed"
		DISPUTED = "disputed", "Disputed"
		FLAGGED = "flagged", "Flagged for review"

	beneficiary = models.ForeignKey(Beneficiary, on_delete=models.CASCADE, related_name="assignments")
	validator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="validation_assignments")
	assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_assignments")
	decision = models.CharField(max_length=12, choices=Decision.choices, default=Decision.PENDING)
	verification_method = models.CharField(max_length=24, choices=VerificationMethod.choices, blank=True)
	identity_checked = models.BooleanField(default=False)
	residency_confirmed = models.BooleanField(default=False)
	household_details_reviewed = models.BooleanField(default=False)
	note = models.CharField(max_length=500, blank=True)
	latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
	assigned_at = models.DateTimeField(auto_now_add=True)
	reviewed_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ["decision", "assigned_at"]
		constraints = [models.UniqueConstraint(fields=["beneficiary", "validator"], name="one_validation_per_validator")]

	def __str__(self):
		return f"{self.beneficiary.beneficiary_id} assigned to {self.validator}"


class Grievance(models.Model):
	class Status(models.TextChoices):
		RECEIVED = "received", "Received"
		INVESTIGATING = "investigating", "Under investigation"
		RESOLVED = "resolved", "Resolved"

	beneficiary = models.ForeignKey(Beneficiary, on_delete=models.SET_NULL, null=True, blank=True, related_name="grievances")
	resident_name = models.CharField(max_length=160)
	contact_number = models.CharField(max_length=24, blank=True)
	reason = models.TextField(max_length=1200)
	status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
	resolution_note = models.CharField(max_length=500, blank=True)
	recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="recorded_grievances")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self):
		return f"Appeal from {self.resident_name} ({self.get_status_display()})"


class AuditEvent(models.Model):
	actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="audit_events")
	actor_label = models.CharField(max_length=150)
	action = models.CharField(max_length=40)
	entity_type = models.CharField(max_length=40)
	entity_reference = models.CharField(max_length=80)
	summary = models.CharField(max_length=300)
	occurred_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-occurred_at"]

	def __str__(self):
		return f"{self.action}: {self.entity_reference} by {self.actor_label}"

	def save(self, *args, **kwargs):
		if self.pk:
			raise ValidationError("Audit events cannot be edited.")
		return super().save(*args, **kwargs)

	def delete(self, *args, **kwargs):
		raise ValidationError("Audit events cannot be deleted.")