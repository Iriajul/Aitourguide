# apps/scans/admin.py
from django.contrib import admin
from .models import Scan

@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at")
    list_filter = ("created_at",)
