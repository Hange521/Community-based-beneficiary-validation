from django.urls import path


from . import views

urlpatterns = [
    path("", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("registry/", views.registry, name="registry"),
    path("beneficiaries/<int:beneficiary_id>/", views.beneficiary_detail, name="beneficiary_detail"),
    path("beneficiaries/<int:beneficiary_id>/location/", views.beneficiary_location_update, name="beneficiary_location_update"),
    path("beneficiaries/<int:beneficiary_id>/photo/", views.beneficiary_photo, name="beneficiary_photo"),
    path("beneficiaries/new/", views.beneficiary_create, name="beneficiary_create"),
    path("registry/import/", views.import_registry, name="import_registry"),
    path("programs/new/", views.program_create, name="program_create"),
    path("beneficiaries/<int:beneficiary_id>/assign/", views.assign_validators, name="assign_validators"),
    path("beneficiaries/<int:beneficiary_id>/resolve/", views.beneficiary_resolve, name="beneficiary_resolve"),
    path("employees/new/", views.employee_create, name="employee_create"),
    path("employees/<int:user_id>/toggle/", views.employee_toggle, name="employee_toggle"),
    path("appeals/new/", views.grievance_create, name="grievance_create"),
    path("appeals/<int:grievance_id>/", views.grievance_resolve, name="grievance_resolve"),
    path("registry/export/", views.export_registry, name="export_registry"),
    path("employee/", views.employee_dashboard, name="employee_dashboard"),
    path("employee/registry/", views.employee_registry, name="employee_registry"),
    path("employee/assignments/<int:assignment_id>/validate/", views.submit_validation, name="submit_validation"),
]