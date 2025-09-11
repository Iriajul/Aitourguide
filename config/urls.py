# config/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/users/", include("apps.users.urls")),
    path("api/scans/", include("apps.scans.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/admin_panel/", include("apps.admin_panel.urls")),
    path("admin-api/", include("apps.admin_api.urls")),

]
