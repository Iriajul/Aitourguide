# apps/scans/urls.py
from django.urls import path
from .views import ScanCreateView, ScanHistoryView, ScanDetailView, ScanDeleteView

urlpatterns = [
    # Upload & analyze a new scan
    path("scan/", ScanCreateView.as_view(), name="scan_create"),

    # List all scans for the logged-in user (history) with search & filter support
    path("scan/history/", ScanHistoryView.as_view(), name="scan_history"),

    # Retrieve details for a single scan by ID
    path("scan/<int:id>/", ScanDetailView.as_view(), name="scan_detail"),

    path("<int:id>/delete/", ScanDeleteView.as_view(), name="scan_delete"),
]
