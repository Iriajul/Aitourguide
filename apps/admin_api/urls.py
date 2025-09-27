# apps/admin_api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
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
    ManageUserDeleteView,
    ReturningUsersView,
    RevenueGrowthView,
    RevenueLeaderboardView,
    UserStatusDistributionView,
    PaymentRecordView,
    PaymentRecordDeleteView,
    PaymentRecordToggleView,
    SubscriptionPlanViewSet,
    PopularPlansView,
    UserEarningsView,
    AdminProfileView,
    AdminPasswordChangeView,
    SubscriptionPlansAllView,
)
from rest_framework_simplejwt.views import TokenRefreshView

# Initialize the router
router = DefaultRouter()
router.register(r'subscription-plans', SubscriptionPlanViewSet, basename='subscription-plans')  # Added this line

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
    path('manage-users/<int:id>/delete/', ManageUserDeleteView.as_view(), name='manage-user-delete'),
    path('returning-users/', ReturningUsersView.as_view(), name='returning-users'),
    path('revenue-growth/', RevenueGrowthView.as_view(), name='revenue-growth'),
    path('revenue-leaderboard/', RevenueLeaderboardView.as_view(), name='revenue-leaderboard'),
    path('user-status-distribution/', UserStatusDistributionView.as_view(), name='user-status-distribution'),
    path('payment-records/', PaymentRecordView.as_view(), name='payment-records'),
    path('payment-records/<int:id>/', PaymentRecordDeleteView.as_view(), name='payment-record-delete'),
    path('payment-records/<int:id>/toggle/', PaymentRecordToggleView.as_view(), name='payment-record-toggle'),
    path('most-popular-plans/', PopularPlansView.as_view(), name='most-popular-plans'),
    path('user-earnings/', UserEarningsView.as_view(), name='user-earnings'),
    path('profile/', AdminProfileView.as_view(), name='admin-profile'),
    path('password-change/', AdminPasswordChangeView.as_view(), name='admin-password-change'),
    path('subscription-plans/all/', SubscriptionPlansAllView.as_view(), name='subscription-plans-all'),
    # Include router URLs for SubscriptionPlanViewSet
    path('', include(router.urls)),  # Added this line
]