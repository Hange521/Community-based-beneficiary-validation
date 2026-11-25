from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "actor_label", "action", "entity_reference", "summary")
    list_filter = ("action", "occurred_at")
    search_fields = ("actor_label", "entity_reference", "summary")
    readonly_fields = (
        "actor",
        "actor_label",
        "action",
        "entity_type",
        "entity_reference",
        "summary",
        "occurred_at",
    )
    ordering = ("-occurred_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
