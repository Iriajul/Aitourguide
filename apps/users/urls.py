# apps/users/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    SignupView,
    MeView,
    EditProfileView,
    AdminUserRoleUpdateView,
    LoginView,
    ForgotPasswordView,
    VerifyOtpView,
    ResetPasswordView,
    LogoutView,
)

urlpatterns = [
    # Authentication
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view(), name="login"),  # custom login view returns user info
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # User profile
    path("me/", MeView.as_view(), name="me"),
    path("edit-profile/", EditProfileView.as_view(), name="edit_profile"),

    # Admin: update user role
    path("<int:pk>/role/", AdminUserRoleUpdateView.as_view(), name="admin_update_role"),

    # Password reset / OTP flow
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("verify-otp/", VerifyOtpView.as_view(), name="verify_otp"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
]
