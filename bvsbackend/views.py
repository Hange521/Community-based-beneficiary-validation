import csv
from io import StringIO
from functools import wraps

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
import pandas as pd

from .forms import (
    AssignmentForm,
    BeneficiaryForm,
    BeneficiaryLocationForm,
    BeneficiaryResolutionForm,
    EmployeeCreateForm,
    GrievanceForm,
    GrievanceResolutionForm,
    LoginForm,
    ProgramForm,
    RegistryImportForm,
    VALIDATOR_GROUP,
    ValidatorDecisionForm,
)
from .models import AuditEvent, Beneficiary, Grievance, Program, ValidatorAssignment


User = get_user_model()


def role_required(role):
    def decorate(view):
        @wraps(view)
        @login_required(login_url="login")
        def guarded(request, *args, **kwargs):
            is_admin = request.user.is_staff or request.user.is_superuser
            is_validator = request.user.groups.filter(name=VALIDATOR_GROUP).exists()
            allowed = is_admin if role == "admin" else is_validator and not is_admin
            if not allowed:
                messages.error(request, "You do not have permission to access that workspace.")
                return redirect("login")
            return view(request, *args, **kwargs)

        return guarded

    return decorate


def audit(actor, action, entity_type, reference, summary):
    AuditEvent.objects.create(
        actor=actor,
        actor_label=actor.get_full_name() or actor.get_username(),
        action=action,
        entity_type=entity_type,
        entity_reference=str(reference),
        summary=summary,
    )


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect("dashboard")
        if request.user.groups.filter(name=VALIDATOR_GROUP).exists():
            return redirect("employee_dashboard")
        auth_logout(request)

    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user is not None and user.is_active:
            if user.is_staff or user.is_superuser or user.groups.filter(name=VALIDATOR_GROUP).exists():
                auth_login(request, user)
                return redirect("dashboard" if user.is_staff or user.is_superuser else "employee_dashboard")
        messages.error(request, "Check your sign-in details or ask an administrator to activate your account.")
    return render(request, "login.html", {"form": form})


@require_POST
def logout_view(request):
    auth_logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("login")


@role_required("admin")
def dashboard(request):
    beneficiaries = Beneficiary.objects.select_related("program", "created_by").prefetch_related(
        "assignments__validator"
    )
    completed_reviews = ValidatorAssignment.objects.exclude(
        decision=ValidatorAssignment.Decision.PENDING
    ).values(
        "identity_checked",
        "residency_confirmed",
        "household_details_reviewed",
    )
    review_score = pd.DataFrame.from_records(completed_reviews)
    average_review_completeness = (
        round(float(review_score.mean(axis=1).mean() * 100))
        if not review_score.empty
        else None
    )
    context = {
        "beneficiaries": beneficiaries[:12],
        "beneficiary_count": beneficiaries.count(),
        "pending_count": beneficiaries.filter(decision=Beneficiary.Decision.PENDING).count(),
        "review_count": beneficiaries.filter(decision=Beneficiary.Decision.NEEDS_REVIEW).count(),
        "approved_count": beneficiaries.filter(decision=Beneficiary.Decision.APPROVED).count(),
        "validator_count": User.objects.filter(groups__name=VALIDATOR_GROUP, is_active=True).distinct().count(),
        "program_count": Program.objects.filter(is_active=True).count(),
        "validators": User.objects.filter(groups__name=VALIDATOR_GROUP).order_by("first_name", "username").distinct(),
        "grievances": Grievance.objects.select_related("beneficiary")[:6],
        "audit_events": AuditEvent.objects.select_related("actor")[:8],
        "average_review_completeness": average_review_completeness,
        "recent_reviews": ValidatorAssignment.objects.exclude(
            decision=ValidatorAssignment.Decision.PENDING
        ).select_related("beneficiary", "validator").order_by("-reviewed_at", "-assigned_at")[:12],
    }
    return render(request, "admin/dashboard.html", context)


@role_required("admin")
def registry(request):
    beneficiaries = Beneficiary.objects.select_related("program").prefetch_related("assignments")
    query = request.GET.get("q", "").strip()
    decision = request.GET.get("decision", "").strip()

    if query:
        beneficiaries = beneficiaries.filter(
            Q(full_name__icontains=query)
            | Q(beneficiary_id__icontains=query)
            | Q(barangay__icontains=query)
            | Q(purok__icontains=query)
            | Q(program__name__icontains=query)
        )
    if decision in Beneficiary.Decision.values:
        beneficiaries = beneficiaries.filter(decision=decision)
    else:
        decision = ""

    page = Paginator(beneficiaries, 20).get_page(request.GET.get("page"))
    mapped_beneficiaries = beneficiaries.filter(
        registration_latitude__isnull=False,
        registration_longitude__isnull=False,
    )
    map_points = [
        {
            "latitude": float(beneficiary.registration_latitude),
            "longitude": float(beneficiary.registration_longitude),
            "beneficiary_id": beneficiary.beneficiary_id,
            "barangay": beneficiary.barangay,
            "purok": beneficiary.purok,
        }
        for beneficiary in mapped_beneficiaries.order_by("-created_at")[:300]
    ]
    return render(request, "admin/registry.html", {
        "page": page,
        "beneficiaries": page.object_list,
        "query": query,
        "selected_decision": decision,
        "decision_choices": Beneficiary.Decision.choices,
        "result_count": page.paginator.count,
        "map_points": map_points,
        "map_point_count": len(map_points),
        "map_point_total": mapped_beneficiaries.count(),
    })


@role_required("admin")
def beneficiary_detail(request, beneficiary_id):
    beneficiary = get_object_or_404(
        Beneficiary.objects.select_related("program", "created_by").prefetch_related(
            "assignments__validator"
        ),
        pk=beneficiary_id,
    )
    return render(request, "admin/beneficiary_detail.html", {
        "beneficiary": beneficiary,
        "assignments": beneficiary.assignments.all(),
        "location_form": BeneficiaryLocationForm(instance=beneficiary),
    })


@role_required("admin")
@require_POST
def beneficiary_location_update(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, pk=beneficiary_id)
    if not beneficiary.consent_recorded:
        messages.error(request, "Recorded consent is required before saving a location pin.")
        return redirect("beneficiary_detail", beneficiary_id=beneficiary.pk)
    form = BeneficiaryLocationForm(request.POST, instance=beneficiary)
    if form.is_valid():
        beneficiary = form.save(commit=False)
        beneficiary.save(update_fields=["registration_latitude", "registration_longitude", "updated_at"])
        audit(request.user, "beneficiary_location_updated", "beneficiary", beneficiary.beneficiary_id, "A registration map pin was updated with recorded consent.")
        messages.success(request, "The registration map pin was updated.")
    else:
        messages.error(request, "Choose a complete map location before saving.")
    return redirect("beneficiary_detail", beneficiary_id=beneficiary.pk)


@role_required("admin")
def beneficiary_photo(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, pk=beneficiary_id)
    if not beneficiary.photo:
        raise Http404("No photo is available for this record.")
    return FileResponse(beneficiary.photo.open("rb"), filename=beneficiary.photo.name.rsplit("/", 1)[-1])


@role_required("admin")
def program_create(request):
    form = ProgramForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        program = form.save()
        audit(request.user, "program_created", "program", program.pk, "A program eligibility rule set was created.")
        messages.success(request, f"Eligibility rules for {program.name} were saved.")
        return redirect("dashboard")
    return render(request, "admin/form.html", {"form": form, "title": "Add program and eligibility rules", "submit_label": "Save program"})


@role_required("admin")
def beneficiary_create(request):
    form = BeneficiaryForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            beneficiary = form.save(commit=False)
            beneficiary.created_by = request.user
            beneficiary.save()
            validators = form.cleaned_data["validators"]
            for validator in validators:
                ValidatorAssignment.objects.create(
                    beneficiary=beneficiary,
                    validator=validator,
                    assigned_by=request.user,
                )
            duplicate_found = beneficiary.duplicate_candidates().exists()
            eligibility_issues = beneficiary.eligibility_issues()
            if duplicate_found or eligibility_issues:
                beneficiary.decision = Beneficiary.Decision.NEEDS_REVIEW
                beneficiary.save(update_fields=["decision", "updated_at"])
            audit(
                request.user,
                "beneficiary_registered",
                "beneficiary",
                beneficiary.beneficiary_id,
                "A beneficiary record was added to the validation registry.",
            )
            for validator in validators:
                audit(
                    request.user,
                    "validator_assigned",
                    "beneficiary",
                    beneficiary.beneficiary_id,
                    f"A validation assignment was created for {validator.get_username()}.",
                )
        if duplicate_found:
            messages.warning(request, "A possible duplicate was found. The record is saved for committee review.")
        elif eligibility_issues:
            messages.warning(request, "Eligibility rules flagged this record for committee review.")
        else:
            messages.success(request, f"Beneficiary {beneficiary.beneficiary_id} was added.")
        return redirect("dashboard")
    return render(request, "admin/form.html", {"form": form, "title": "Register beneficiary", "submit_label": "Save beneficiary"})


@role_required("admin")
def import_registry(request):
    form = RegistryImportForm(request.POST or None, request.FILES or None)
    row_errors = []
    imported_count = 0
    review_count = 0
    if request.method == "POST" and form.is_valid():
        try:
            content = form.cleaned_data["file"].read().decode("utf-8-sig")
            reader = csv.DictReader(StringIO(content))
            required_columns = {"full_name", "barangay", "purok", "consent_recorded"}
            headers = set(reader.fieldnames or [])
            missing = required_columns - headers
            if missing:
                form.add_error("file", "Missing required columns: " + ", ".join(sorted(missing)))
            else:
                for row_number, row in enumerate(reader, start=2):
                    values = {key: (value or "").strip() for key, value in row.items() if key}
                    if not any(values.values()):
                        continue
                    consent = values.get("consent_recorded", "").lower()
                    if consent not in {"1", "true", "yes", "on"}:
                        row_errors.append(f"Row {row_number}: consent_recorded must be yes/true/1.")
                        continue
                    program_name = values.get("program", "")
                    program = Program.objects.filter(name__iexact=program_name, is_active=True).first() if program_name else None
                    if program_name and program is None:
                        row_errors.append(f"Row {row_number}: active program '{program_name}' was not found.")
                        continue
                    form_data = {
                        "full_name": values.get("full_name", ""),
                        "birth_year": values.get("birth_year", ""),
                        "household_size": values.get("household_size", "") or "1",
                        "monthly_household_income": values.get("monthly_household_income", ""),
                        "residency_months": values.get("residency_months", "") or "0",
                        "vulnerability": values.get("vulnerability", "none") or "none",
                        "program": str(program.pk) if program else "",
                        "barangay": values.get("barangay", ""),
                        "purok": values.get("purok", ""),
                        "address_note": values.get("address_note", ""),
                        "contact_number": values.get("contact_number", ""),
                        "consent_recorded": "on",
                    }
                    beneficiary_form = BeneficiaryForm(form_data)
                    if not beneficiary_form.is_valid():
                        row_errors.append(f"Row {row_number}: " + "; ".join(
                            f"{field}: {', '.join(errors)}" for field, errors in beneficiary_form.errors.items()
                        ))
                        continue
                    with transaction.atomic():
                        beneficiary = beneficiary_form.save(commit=False)
                        beneficiary.created_by = request.user
                        beneficiary.save()
                        duplicate_found = beneficiary.duplicate_candidates().exists()
                        eligibility_issues = beneficiary.eligibility_issues()
                        if duplicate_found or eligibility_issues:
                            beneficiary.decision = Beneficiary.Decision.NEEDS_REVIEW
                            beneficiary.save(update_fields=["decision", "updated_at"])
                            review_count += 1
                        audit(request.user, "beneficiary_imported", "beneficiary", beneficiary.beneficiary_id, "A consented beneficiary record was imported from a draft list.")
                    imported_count += 1
        except (UnicodeDecodeError, csv.Error) as error:
            form.add_error("file", f"The CSV could not be read: {error}")
        if imported_count:
            messages.success(request, f"Imported {imported_count} beneficiary record(s); {review_count} flagged for review.")
        if row_errors:
            messages.warning(request, f"{len(row_errors)} row(s) were skipped. Review the import report below.")
    return render(request, "admin/import.html", {
        "form": form,
        "row_errors": row_errors[:30],
        "imported_count": imported_count,
        "review_count": review_count,
    })


@role_required("admin")
def employee_create(request):
    form = EmployeeCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        employee = User.objects.create_user(
            username=form.cleaned_data["username"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        validator_group, _ = Group.objects.get_or_create(name=VALIDATOR_GROUP)
        employee.groups.add(validator_group)
        audit(request.user, "validator_created", "user", employee.username, "A validator account was created.")
        messages.success(request, f"Validator account for {employee.get_full_name()} was created.")
        return redirect("dashboard")
    return render(request, "admin/form.html", {"form": form, "title": "Add employee / validator", "submit_label": "Create account", "is_employee_form": True})


@role_required("admin")
@require_POST
def employee_toggle(request, user_id):
    employee = get_object_or_404(User, pk=user_id, groups__name=VALIDATOR_GROUP)
    employee.is_active = not employee.is_active
    employee.save(update_fields=["is_active"])
    action = "validator_activated" if employee.is_active else "validator_deactivated"
    audit(request.user, action, "user", employee.username, "A validator account's access status was changed.")
    messages.success(request, f"{employee.get_full_name() or employee.username} is now {'active' if employee.is_active else 'inactive'}.")
    return redirect("dashboard")


@role_required("admin")
def assign_validators(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, pk=beneficiary_id)
    form = AssignmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        selected = form.cleaned_data["validators"]
        existing_ids = set(beneficiary.assignments.values_list("validator_id", flat=True))
        all_ids = existing_ids | set(selected.values_list("id", flat=True))
        if len(all_ids) > 3:
            form.add_error("validators", "A beneficiary may have no more than three distinct validators.")
        else:
            for validator in selected:
                assignment, created = ValidatorAssignment.objects.get_or_create(
                    beneficiary=beneficiary,
                    validator=validator,
                    defaults={"assigned_by": request.user},
                )
                if created:
                    audit(request.user, "validator_assigned", "beneficiary", beneficiary.beneficiary_id, f"A validation assignment was created for {validator.get_username()}.")
            messages.success(request, "Validator assignments were updated.")
            return redirect("dashboard")
    return render(request, "admin/form.html", {
        "form": form,
        "title": f"Assign validators · {beneficiary.beneficiary_id}",
        "submit_label": "Save assignments",
        "beneficiary": beneficiary,
    })


@role_required("admin")
def beneficiary_resolve(request, beneficiary_id):
    beneficiary = get_object_or_404(Beneficiary, pk=beneficiary_id)
    form = BeneficiaryResolutionForm(request.POST or None, instance=beneficiary)
    if request.method == "POST" and form.is_valid():
        previous = beneficiary.decision
        updated = form.save()
        audit(
            request.user,
            "beneficiary_decision_set",
            "beneficiary",
            beneficiary.beneficiary_id,
            f"Final decision changed from {previous} to {updated.decision} by an administrator.",
        )
        messages.success(request, "The committee decision was recorded.")
        return redirect("dashboard")
    return render(request, "admin/form.html", {
        "form": form,
        "title": f"Resolve beneficiary · {beneficiary.beneficiary_id}",
        "submit_label": "Record decision",
        "beneficiary": beneficiary,
    })


@role_required("admin")
def grievance_resolve(request, grievance_id):
    grievance = get_object_or_404(Grievance, pk=grievance_id)
    form = GrievanceResolutionForm(request.POST or None, instance=grievance)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit(request.user, "grievance_updated", "grievance", grievance.pk, "An appeal status or resolution note was updated.")
        messages.success(request, "The appeal record was updated.")
        return redirect("dashboard")
    return render(request, "admin/form.html", {"form": form, "title": "Update appeal", "submit_label": "Save appeal update", "grievance": grievance})


@login_required(login_url="login")
def grievance_create(request):
    is_admin = request.user.is_staff or request.user.is_superuser
    is_validator = request.user.groups.filter(name=VALIDATOR_GROUP).exists()
    if not is_admin and not is_validator:
        return redirect("login")
    form = GrievanceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        grievance = form.save(commit=False)
        grievance.recorded_by = request.user
        grievance.save()
        audit(request.user, "grievance_received", "grievance", grievance.pk, "A resident appeal was recorded.")
        messages.success(request, "The appeal was recorded for follow-up.")
        return redirect("dashboard" if is_admin else "employee_dashboard")
    return render(request, "admin/form.html", {"form": form, "title": "Record a resident appeal", "submit_label": "Submit appeal"})


@role_required("employee")
def employee_dashboard(request):
    assignments = ValidatorAssignment.objects.filter(validator=request.user).select_related(
        "beneficiary", "beneficiary__program"
    )
    return render(request, "employee/dashboard.html", {
        "assignments": assignments,
        "pending_count": assignments.filter(decision=ValidatorAssignment.Decision.PENDING).count(),
        "completed_count": assignments.exclude(decision=ValidatorAssignment.Decision.PENDING).count(),
    })


@role_required("employee")
def employee_registry(request):
    assignments = ValidatorAssignment.objects.filter(validator=request.user).select_related(
        "beneficiary", "beneficiary__program"
    )
    query = request.GET.get("q", "").strip()
    decision = request.GET.get("decision", "").strip()
    if query:
        assignments = assignments.filter(
            Q(beneficiary__full_name__icontains=query)
            | Q(beneficiary__beneficiary_id__icontains=query)
            | Q(beneficiary__barangay__icontains=query)
            | Q(beneficiary__purok__icontains=query)
            | Q(beneficiary__program__name__icontains=query)
        )
    if decision in ValidatorAssignment.Decision.values:
        assignments = assignments.filter(decision=decision)
    else:
        decision = ""
    return render(request, "employee/registry.html", {
        "assignments": assignments,
        "query": query,
        "selected_decision": decision,
        "decision_choices": ValidatorAssignment.Decision.choices,
        "result_count": assignments.count(),
    })


@role_required("employee")
def submit_validation(request, assignment_id):
    assignment = get_object_or_404(ValidatorAssignment, pk=assignment_id, validator=request.user)
    form = ValidatorDecisionForm(request.POST or None, instance=assignment)
    if request.method == "POST" and form.is_valid():
        previous = assignment.decision
        with transaction.atomic():
            assignment = form.save(commit=False)
            assignment.reviewed_at = timezone.now()
            assignment.save()
            beneficiary = assignment.beneficiary
            previous_final = beneficiary.decision
            summary = beneficiary.validation_summary()
            if summary == "consensus_confirmed":
                if beneficiary.eligibility_issues() or beneficiary.duplicate_candidates().exists():
                    beneficiary.decision = Beneficiary.Decision.NEEDS_REVIEW
                else:
                    beneficiary.decision = Beneficiary.Decision.APPROVED
            elif summary == "committee_review":
                beneficiary.decision = Beneficiary.Decision.NEEDS_REVIEW
            elif beneficiary.decision != Beneficiary.Decision.REJECTED:
                beneficiary.decision = Beneficiary.Decision.PENDING
            beneficiary.save(update_fields=["decision", "updated_at"])
            audit(
                request.user,
                "validation_submitted",
                "beneficiary",
                beneficiary.beneficiary_id,
                f"A validator submitted {assignment.decision} using {assignment.verification_method or 'no method'} (previously {previous}); identity={assignment.identity_checked}, residency={assignment.residency_confirmed}, household_details={assignment.household_details_reviewed}.",
            )
            if previous_final != beneficiary.decision:
                audit(request.user, "consensus_updated", "beneficiary", beneficiary.beneficiary_id, f"Validation workflow status changed to {beneficiary.decision}.")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True, "decision": assignment.decision, "workflow_status": beneficiary.decision})
        messages.success(request, "Your validation was saved and added to the audit trail.")
    else:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
        messages.error(request, "Please choose a validation outcome and review the form errors.")
    return redirect("employee_dashboard")


@role_required("admin")
def export_registry(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="beneficiary-registry.csv"'
    writer = csv.writer(response)
    writer.writerow(["Beneficiary ID", "Name", "Barangay", "Purok", "Program", "Decision", "Household size"])
    for beneficiary in Beneficiary.objects.select_related("program").iterator():
        writer.writerow([
            beneficiary.beneficiary_id,
            beneficiary.full_name,
            beneficiary.barangay,
            beneficiary.purok,
            beneficiary.program.name if beneficiary.program else "",
            beneficiary.get_decision_display(),
            beneficiary.household_size,
        ])
    audit(request.user, "registry_exported", "registry", "all", "The administrator exported the beneficiary registry.")
    return response