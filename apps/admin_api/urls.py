# apps/admin_api/urls.py
from django.urls import path
from .views import (
    AdminLoginView,
    AdminLogoutView,
    AdminDashboardView,
    AdminPasswordForgotView,
    AdminOTPVerifyView,
    AdminOTPResendView,
    AdminPasswordResetView,
    AdminOverviewView,
    AdminLoginOTPVerifyView,
    UserActivityView,
    UserActivityDeleteView,
    ManageUsersView,
    ManageUserSubscriptionView,
    ManageUserBanView,
    ManageUserUnbanView,
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Authentication
    path("login/", AdminLoginView.as_view(), name="admin_login"),
    path("login/verify-otp/", AdminLoginOTPVerifyView.as_view(), name="admin-login-otp-verify"),
    path("logout/", AdminLogoutView.as_view(), name="admin_logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="admin_token_refresh"),

    # Dashboard (JWT-protected)
    path("dashboard/", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("overview/", AdminOverviewView.as_view(), name="admin_overview"),
    # Password & OTP flows
    path("forgot-password/", AdminPasswordForgotView.as_view(), name="admin_forgot_password"),
    path("verify-otp/", AdminOTPVerifyView.as_view(), name="admin_verify_otp"),
    path("resend-otp/", AdminOTPResendView.as_view(), name="admin_resend_otp"),
    path("reset-password/", AdminPasswordResetView.as_view(), name="admin_reset_password"),

    # User Activity
    path("user-activity/", UserActivityView.as_view(), name="user_activity"),
    path("user-activity/<int:id>/", UserActivityDeleteView.as_view(), name="user_activity_delete"),

    # Manage Users
    path("manage-users/", ManageUsersView.as_view(), name="manage_users"),
    path("manage-users/<int:id>/subscription/", ManageUserSubscriptionView.as_view(), name="manage_user_subscription"),
    path("manage-users/<int:id>/ban/", ManageUserBanView.as_view(), name="manage_user_ban"),
    path("manage-users/<int:id>/unban/", ManageUserUnbanView.as_view(), name="manage_user_unban"),
]