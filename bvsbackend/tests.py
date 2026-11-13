from io import BytesIO
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import VALIDATOR_GROUP
from PIL import Image

from .models import AuditEvent, Beneficiary, Grievance, Program, ValidatorAssignment


@override_settings(ALLOWED_HOSTS=["testserver"])
class ValidationWorkflowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.admin = user_model.objects.create_user(
			username="community-admin",
			password="test-admin-pass-123",
			is_staff=True,
		)
		self.validator_group = Group.objects.create(name=VALIDATOR_GROUP)
		self.validators = []
		for username in ["validator-one", "validator-two", "validator-three"]:
			validator = user_model.objects.create_user(username=username, password="test-validator-pass-123")
			validator.groups.add(self.validator_group)
			self.validators.append(validator)
		self.program = Program.objects.create(
			name="Household support",
			maximum_monthly_income="15000.00",
			minimum_residency_months=6,
		)

	def test_workspace_access_is_role_scoped(self):
		admin_client = self.client_class()
		admin_client.force_login(self.admin)
		self.assertRedirects(admin_client.get("/admin/"), reverse("dashboard"))
		admin_response = admin_client.get(reverse("dashboard"))
		self.assertEqual(admin_response.status_code, 200)
		self.assertContains(admin_response, "/static/css/app.css")
		self.assertContains(admin_response, "/static/js/app.js")
		self.assertContains(admin_response, "/static/image/civicbridge-mark.svg")
		self.assertContains(admin_response, "Sign out")
		self.assertContains(admin_response, 'action="/logout/"')
		self.assertEqual(admin_client.get(reverse("employee_dashboard")).status_code, 302)

		assigned_record = Beneficiary.objects.create(
			full_name="Assigned Household",
			barangay="San Isidro",
			purok="Purok 2",
			consent_recorded=True,
			created_by=self.admin,
		)
		restricted_record = Beneficiary.objects.create(
			full_name="Restricted Household",
			barangay="San Isidro",
			purok="Purok 3",
			consent_recorded=True,
			created_by=self.admin,
		)
		ValidatorAssignment.objects.create(
			beneficiary=assigned_record,
			validator=self.validators[0],
			assigned_by=self.admin,
		)

		employee_client = self.client_class()
		employee_client.force_login(self.validators[0])
		employee_response = employee_client.get(reverse("employee_dashboard"))
		self.assertEqual(employee_response.status_code, 200)
		self.assertContains(employee_response, "/static/js/employee.js")
		self.assertContains(employee_response, assigned_record.beneficiary_id)
		self.assertNotContains(employee_response, restricted_record.beneficiary_id)
		registry_response = employee_client.get(reverse("employee_registry"))
		self.assertEqual(registry_response.status_code, 200)
		self.assertContains(registry_response, assigned_record.beneficiary_id)
		self.assertNotContains(registry_response, restricted_record.beneficiary_id)
		self.assertEqual(employee_client.get(reverse("dashboard")).status_code, 302)
		self.assertEqual(employee_client.get(reverse("registry")).status_code, 302)

	def test_logout_requires_post_and_clears_session(self):
		self.client.force_login(self.admin)
		self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
		response = self.client.post(reverse("logout"))
		self.assertRedirects(response, reverse("login"))
		self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

	def test_registry_empty_state_offers_registration_and_import(self):
		self.client.force_login(self.admin)
		response = self.client.get(reverse("registry"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "The beneficiary registry is empty")
		self.assertContains(response, reverse("beneficiary_create"))
		self.assertContains(response, reverse("import_registry"))

	def test_registry_search_and_decision_filter_show_matching_records(self):
		self.client.force_login(self.admin)
		matched = Beneficiary.objects.create(
			full_name="Maria Sample",
			barangay="San Isidro",
			purok="Purok 2",
			decision=Beneficiary.Decision.APPROVED,
			consent_recorded=True,
			created_by=self.admin,
		)
		Beneficiary.objects.create(
			full_name="Ramon Other",
			barangay="San Isidro",
			purok="Purok 4",
			decision=Beneficiary.Decision.PENDING,
			consent_recorded=True,
			created_by=self.admin,
		)

		response = self.client.get(reverse("registry"), {"q": "Maria", "decision": Beneficiary.Decision.APPROVED})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, matched.beneficiary_id)
		self.assertContains(response, "1 record found")
		self.assertNotContains(response, "Ramon Other")

	def test_registry_map_shows_recorded_visit_locations(self):
		beneficiary = Beneficiary.objects.create(
			full_name="Mapped Resident",
			barangay="San Isidro",
			purok="Purok 2",
			consent_recorded=True,
			created_by=self.admin,
		)
		beneficiary.registration_latitude = "8.947000"
		beneficiary.registration_longitude = "125.540000"
		beneficiary.save(update_fields=["registration_latitude", "registration_longitude"])
		self.client.force_login(self.admin)
		response = self.client.get(reverse("registry"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Registration map")
		self.assertContains(response, "registryMapData")
		self.assertContains(response, beneficiary.beneficiary_id)
		self.assertContains(response, "OpenStreetMap")

	def test_beneficiary_detail_shows_registration_and_validation_information(self):
		beneficiary = Beneficiary.objects.create(
			full_name="Detail Resident",
			barangay="San Isidro",
			purok="Purok 3",
			address_note="Near the health center",
			contact_number="09123456789",
			consent_recorded=True,
			created_by=self.admin,
		)
		self.client.force_login(self.admin)
		response = self.client.get(reverse("beneficiary_detail", args=[beneficiary.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Near the health center")
		self.assertContains(response, "09123456789")
		self.assertContains(response, "Registration information")

	def test_admin_can_add_registration_pin_to_existing_consented_record(self):
		beneficiary = Beneficiary.objects.create(
			full_name="Existing Mapped Resident",
			barangay="San Isidro",
			purok="Purok 4",
			consent_recorded=True,
			created_by=self.admin,
		)
		self.client.force_login(self.admin)
		response = self.client.post(reverse("beneficiary_location_update", args=[beneficiary.pk]), {
			"registration_latitude": "8.947000",
			"registration_longitude": "125.540000",
		})
		self.assertRedirects(response, reverse("beneficiary_detail", args=[beneficiary.pk]))
		beneficiary.refresh_from_db()
		self.assertEqual(str(beneficiary.registration_latitude), "8.947000")
		self.assertEqual(str(beneficiary.registration_longitude), "125.540000")
		unconsented = Beneficiary.objects.create(
			full_name="Unconsented Resident",
			barangay="San Isidro",
			purok="Purok 5",
			created_by=self.admin,
		)
		response = self.client.post(reverse("beneficiary_location_update", args=[unconsented.pk]), {
			"registration_latitude": "8.947000",
			"registration_longitude": "125.540000",
		})
		self.assertRedirects(response, reverse("beneficiary_detail", args=[unconsented.pk]))
		unconsented.refresh_from_db()
		self.assertIsNone(unconsented.registration_latitude)
		self.assertIsNone(unconsented.registration_longitude)

	def test_appeal_reason_is_shown_on_dashboard_and_update_page(self):
		grievance = Grievance.objects.create(
			resident_name="Appealing Resident",
			reason="My household details were recorded incorrectly.",
			recorded_by=self.admin,
		)
		self.client.force_login(self.admin)
		self.assertContains(self.client.get(reverse("dashboard")), "My household details were recorded incorrectly.")
		response = self.client.get(reverse("grievance_resolve", args=[grievance.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "My household details were recorded incorrectly.")

	def test_beneficiary_photo_upload_is_private_to_administrators(self):
		image_data = BytesIO()
		Image.new("RGB", (2, 2), color="green").save(image_data, format="PNG")
		photo = SimpleUploadedFile("resident.png", image_data.getvalue(), content_type="image/png")
		with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
			self.client.force_login(self.admin)
			response = self.client.post(reverse("beneficiary_create"), {
				"full_name": "Photo Resident",
				"birth_year": "1988",
				"household_size": "3",
				"monthly_household_income": "12000",
				"residency_months": "12",
				"vulnerability": Beneficiary.Vulnerability.NONE,
				"program": "",
				"barangay": "San Isidro",
				"purok": "Purok 8",
				"address_note": "Near the market",
				"contact_number": "09123456789",
				"consent_recorded": "on",
				"photo": photo,
				"validators": [],
			})
			self.assertRedirects(response, reverse("dashboard"))
			beneficiary = Beneficiary.objects.get(full_name="Photo Resident")
			photo_response = self.client.get(reverse("beneficiary_photo", args=[beneficiary.pk]))
			self.assertEqual(photo_response.status_code, 200)
			self.assertTrue(photo_response["Content-Type"].startswith("image/png"))
			photo_response.close()
			self.assertContains(
				self.client.get(reverse("beneficiary_detail", args=[beneficiary.pk])),
				reverse("beneficiary_photo", args=[beneficiary.pk]),
			)
		self.client.force_login(self.validators[0])
		self.assertEqual(self.client.get(reverse("beneficiary_photo", args=[beneficiary.pk])).status_code, 302)

	def test_employee_cannot_access_full_registry(self):
		self.client.force_login(self.validators[0])
		self.assertEqual(self.client.get(reverse("registry")).status_code, 302)

	def test_admin_dashboard_shows_average_submitted_review_checks(self):
		beneficiary = Beneficiary.objects.create(
			full_name="Review Average Resident",
			barangay="San Isidro",
			purok="Purok 6",
			consent_recorded=True,
			created_by=self.admin,
		)
		complete_review = ValidatorAssignment.objects.create(
			beneficiary=beneficiary,
			validator=self.validators[0],
			assigned_by=self.admin,
			decision=ValidatorAssignment.Decision.CONFIRMED,
			verification_method=ValidatorAssignment.VerificationMethod.HOUSEHOLD_VISIT,
			identity_checked=True,
			residency_confirmed=True,
			household_details_reviewed=True,
		)
		partial_review = ValidatorAssignment.objects.create(
			beneficiary=beneficiary,
			validator=self.validators[1],
			assigned_by=self.admin,
			decision=ValidatorAssignment.Decision.FLAGGED,
			identity_checked=True,
		)
		ValidatorAssignment.objects.create(
			beneficiary=beneficiary,
			validator=self.validators[2],
			assigned_by=self.admin,
		)
		ValidatorAssignment.objects.filter(pk__in=[complete_review.pk, partial_review.pk]).update(reviewed_at=timezone.now())

		self.client.force_login(self.admin)
		response = self.client.get(reverse("dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context["average_review_completeness"], 67)
		self.assertContains(response, "Average review checks")
		self.assertContains(response, "Recent community reviews")
		self.assertContains(response, "audit-scroll")

	def test_admin_can_create_and_deactivate_an_employee(self):
		self.client.force_login(self.admin)
		response = self.client.post(reverse("employee_create"), {
			"username": "new-validator",
			"first_name": "Nina",
			"last_name": "Field",
			"email": "nina@example.test",
			"password": "LongTestPass-123",
		})
		self.assertRedirects(response, reverse("dashboard"))
		employee = get_user_model().objects.get(username="new-validator")
		self.assertTrue(employee.groups.filter(name=VALIDATOR_GROUP).exists())
		self.assertTrue(employee.check_password("LongTestPass-123"))

		response = self.client.post(reverse("employee_toggle", args=[employee.pk]))
		self.assertRedirects(response, reverse("dashboard"))
		employee.refresh_from_db()
		self.assertFalse(employee.is_active)
		self.assertTrue(AuditEvent.objects.filter(action="validator_deactivated", entity_reference=employee.username).exists())

	def test_csv_import_requires_consent_and_records_valid_rows(self):
		self.client.force_login(self.admin)
		csv_content = (
			"full_name,birth_year,household_size,monthly_household_income,residency_months,"
			"vulnerability,program,barangay,purok,consent_recorded\n"
			"Lina Reyes,1985,3,10000,18,none,Household support,San Isidro,Purok 4,yes\n"
			"Pio Reyes,1978,2,9000,24,none,Household support,San Isidro,Purok 5,no\n"
		)
		upload = SimpleUploadedFile("draft.csv", csv_content.encode("utf-8"), content_type="text/csv")
		response = self.client.post(reverse("import_registry"), {"file": upload})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Imported 1 beneficiary record")
		self.assertContains(response, "consent_recorded must be yes/true/1")
		self.assertTrue(Beneficiary.objects.filter(full_name="Lina Reyes", consent_recorded=True).exists())
		self.assertFalse(Beneficiary.objects.filter(full_name="Pio Reyes").exists())
		self.assertTrue(AuditEvent.objects.filter(action="beneficiary_imported").exists())

	def test_two_independent_confirmations_approve_a_eligible_record(self):
		admin_client = self.client_class()
		admin_client.force_login(self.admin)
		response = admin_client.post(reverse("beneficiary_create"), {
			"full_name": "Mila Dela Cruz",
			"birth_year": 1988,
			"household_size": 4,
			"monthly_household_income": "12000.00",
			"residency_months": 24,
			"vulnerability": Beneficiary.Vulnerability.NONE,
			"program": self.program.pk,
			"barangay": "San Isidro",
			"purok": "Purok 2",
			"address_note": "Near the community hall",
			"registration_latitude": "8.947000",
			"registration_longitude": "125.540000",
			"contact_number": "",
			"consent_recorded": "on",
			"validators": [validator.pk for validator in self.validators[:2]],
		})
		self.assertRedirects(response, reverse("dashboard"))
		beneficiary = Beneficiary.objects.get(full_name="Mila Dela Cruz")
		self.assertEqual(beneficiary.assignments.count(), 2)
		self.assertEqual(beneficiary.decision, Beneficiary.Decision.PENDING)
		self.assertEqual(str(beneficiary.registration_latitude), "8.947000")
		self.assertEqual(str(beneficiary.registration_longitude), "125.540000")

		for validator in self.validators[:2]:
			employee_client = self.client_class()
			employee_client.force_login(validator)
			assignment = ValidatorAssignment.objects.get(beneficiary=beneficiary, validator=validator)
			data = {
				"decision": ValidatorAssignment.Decision.CONFIRMED,
				"verification_method": ValidatorAssignment.VerificationMethod.HOUSEHOLD_VISIT,
				"identity_checked": "on",
				"residency_confirmed": "on",
				"household_details_reviewed": "on",
				"note": "Household confirmed in person.",
				"latitude": "",
				"longitude": "",
			}
			if validator == self.validators[0]:
				response = employee_client.post(
					reverse("submit_validation", args=[assignment.pk]),
					data,
					HTTP_X_REQUESTED_WITH="XMLHttpRequest",
				)
				self.assertEqual(response.status_code, 200)
				self.assertTrue(response.json()["ok"])
			else:
				response = employee_client.post(reverse("submit_validation", args=[assignment.pk]), data)
				self.assertRedirects(response, reverse("employee_dashboard"))

		beneficiary.refresh_from_db()
		self.assertEqual(beneficiary.decision, Beneficiary.Decision.APPROVED)
		self.assertEqual(AuditEvent.objects.filter(action="validation_submitted").count(), 2)
		self.assertTrue(AuditEvent.objects.filter(action="consensus_updated").exists())
		self.assertEqual(beneficiary.assignments.get(validator=self.validators[0]).note, "Household confirmed in person.")
		assignment = beneficiary.assignments.get(validator=self.validators[0])
		self.assertEqual(assignment.verification_method, ValidatorAssignment.VerificationMethod.HOUSEHOLD_VISIT)
		self.assertTrue(assignment.identity_checked)
		self.assertTrue(assignment.residency_confirmed)
		self.assertTrue(assignment.household_details_reviewed)

	def test_confirmation_requires_method_and_all_three_checks(self):
		beneficiary = Beneficiary.objects.create(
			full_name="Incomplete Check Resident",
			barangay="San Isidro",
			purok="Purok 7",
			consent_recorded=True,
			created_by=self.admin,
		)
		assignment = ValidatorAssignment.objects.create(
			beneficiary=beneficiary,
			validator=self.validators[0],
			assigned_by=self.admin,
		)
		self.client.force_login(self.validators[0])
		response = self.client.post(reverse("submit_validation", args=[assignment.pk]), {
			"decision": ValidatorAssignment.Decision.CONFIRMED,
			"verification_method": ValidatorAssignment.VerificationMethod.HOUSEHOLD_VISIT,
			"identity_checked": "on",
			"latitude": "",
			"longitude": "",
		})
		self.assertRedirects(response, reverse("employee_dashboard"))
		assignment.refresh_from_db()
		self.assertEqual(assignment.decision, ValidatorAssignment.Decision.PENDING)
		self.assertFalse(AuditEvent.objects.filter(action="validation_submitted").exists())

	def test_rules_mismatch_is_held_for_review_not_auto_rejected(self):
		self.client.force_login(self.admin)
		response = self.client.post(reverse("beneficiary_create"), {
			"full_name": "Noel Santos",
			"birth_year": 1976,
			"household_size": 2,
			"monthly_household_income": "22000.00",
			"residency_months": 2,
			"vulnerability": Beneficiary.Vulnerability.NONE,
			"program": self.program.pk,
			"barangay": "San Isidro",
			"purok": "Purok 5",
			"address_note": "",
			"contact_number": "",
			"consent_recorded": "on",
			"validators": [],
		})
		self.assertRedirects(response, reverse("dashboard"))
		beneficiary = Beneficiary.objects.get(full_name="Noel Santos")
		self.assertEqual(beneficiary.decision, Beneficiary.Decision.NEEDS_REVIEW)
		self.assertEqual(beneficiary.validation_summary(), "awaiting_validators")

	def test_any_dispute_overrides_two_confirmations(self):
		beneficiary = Beneficiary.objects.create(
			full_name="Amara Cruz",
			barangay="San Isidro",
			purok="Purok 1",
			consent_recorded=True,
			created_by=self.admin,
		)
		decisions = [
			ValidatorAssignment.Decision.CONFIRMED,
			ValidatorAssignment.Decision.CONFIRMED,
			ValidatorAssignment.Decision.FLAGGED,
		]
		for validator, decision in zip(self.validators, decisions):
			ValidatorAssignment.objects.create(
				beneficiary=beneficiary,
				validator=validator,
				assigned_by=self.admin,
				decision=decision,
			)
		self.assertEqual(beneficiary.validation_summary(), "committee_review")
