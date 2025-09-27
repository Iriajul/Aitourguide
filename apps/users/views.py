from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.core.mail import send_mail
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.utils import timezone

from .models import User
from .serializers import (
    UserSignupSerializer,
    UserSerializer,
    UserLoginSerializer,
    ForgotPasswordSerializer,
    VerifyOtpSerializer,
    ResetPasswordSerializer,
    LogoutSerializer,
    EditProfileSerializer,
)
from .permissions import IsAdminRole


# -----------------------------
# Signup View
# -----------------------------
class SignupView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSignupSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Track signup activity
        user.last_activity_time = timezone.now()
        user.save(update_fields=["last_activity_time"])

        user_data = UserSerializer(user).data
        return Response(user_data, status=status.HTTP_201_CREATED)


# -----------------------------
# Me / Profile View
# -----------------------------
class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        # Update last activity
        self.request.user.update_last_activity()
        return self.request.user


# -----------------------------
# Edit Profile View
# -----------------------------
class EditProfileView(generics.UpdateAPIView):
    serializer_class = EditProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def patch(self, request, *args, **kwargs):
        instance = self.get_object()
        # Create a copy of request data and exclude profile_picture_file for serializer
        serializer_data = request.data.copy()
        if "profile_picture_file" in request.FILES:
            serializer_data.pop("profile_picture_file", None)  # Remove from serializer data
        
        # Initialize serializer without profile_picture_file
        serializer = self.get_serializer(instance, data=serializer_data, partial=True)
        serializer.is_valid(raise_exception=True)

        changed_fields = {}

        # --- Manual Password Update (if provided) ---
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")
        if old_password and new_password:
            if instance.check_password(old_password):
                instance.set_password(new_password)
                instance.save(update_fields=["password"])
                changed_fields["password"] = "updated"
            else:
                return Response({"old_password": ["Old password is incorrect."]}, status=status.HTTP_400_BAD_REQUEST)

        # --- Manual Profile Picture Update (if provided) ---
        profile_picture_file = request.FILES.get("profile_picture_file")
        if profile_picture_file:
            try:
                instance.update_profile_picture(profile_picture_file)
                changed_fields["profile_picture"] = instance.profile_picture_url or "updated"
            except Exception as e:
                return Response({"detail": f"Profile picture upload failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # --- Apply Serializer Updates for Other Fields ---
        serializer.save()  # Apply validated data excluding profile_picture_file
        original_data = EditProfileSerializer(instance).data
        for field in ["username", "free_scans_used", "total_searches", "total_scans", "total_premium_days", "is_active_premium"]:
            original_value = original_data.get(field)
            updated_value = getattr(instance, field)
            if updated_value != original_value:
                changed_fields[field] = updated_value

        # Update last activity
        instance.update_last_activity()

        # Return response based on changes
        if not changed_fields:
            return Response({"detail": "No fields updated"}, status=status.HTTP_200_OK)
        return Response(changed_fields, status=status.HTTP_200_OK)


# -----------------------------
# Admin Role Update View
# -----------------------------
class AdminUserRoleUpdateView(generics.UpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        role = request.data.get("role")
        if role not in ("guest", "registered", "premium", "admin"):
            return Response({"detail": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)

        user.role = role
        # Update premium flag dynamically
        if role == "premium":
            user.activate_premium_flag()
        elif role in ["guest", "registered"]:
            user.deactivate_premium_flag()

        user.save(update_fields=["role"])
        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


# -----------------------------
# Login View
# -----------------------------
class LoginView(generics.GenericAPIView):
    serializer_class = UserLoginSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # serializer.save() returns {"user": <User instance>, "access": <token>, "refresh": <token>}
        result = serializer.save()
        user = result["user"]  # actual User instance
        access = result["access"]
        refresh = result["refresh"]

        # Track login time + last activity
        user.last_login_time = timezone.now()
        user.update_last_activity()

        # Recalculate premium status dynamically
        user.recalc_premium_status()

        user.save(update_fields=["last_login_time", "last_activity_time", "is_active_premium", "total_premium_days"])

        # Serialize user for response
        user_data = UserSerializer(user).data

        return Response({
            "user": user_data,
            "access": access,
            "refresh": refresh
        }, status=status.HTTP_200_OK)


# -----------------------------
# OTP Flow Views
# -----------------------------
class ForgotPasswordView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Email not found."}, status=status.HTTP_404_NOT_FOUND)

        otp = user.set_otp()

        send_mail(
            subject="Your OTP for Password Reset",
            message=f"Your OTP code is {otp}. It is valid for 5 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        return Response({"detail": "OTP sent to your email.", "otp_token": str(user.pk)}, status=status.HTTP_200_OK)


class VerifyOtpView(generics.GenericAPIView):
    serializer_class = VerifyOtpSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data["otp"]
        otp_token = serializer.validated_data.get("otp_token")

        if not otp_token:
            return Response({"detail": "OTP token missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=otp_token)
        except User.DoesNotExist:
            return Response({"detail": "Invalid OTP token."}, status=status.HTTP_400_BAD_REQUEST)

        if not user.verify_otp(otp):
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "OTP verified successfully."}, status=status.HTTP_200_OK)


class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp_token = serializer.validated_data.get("otp_token")

        if not otp_token:
            return Response({"detail": "OTP token missing."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=otp_token)
        except User.DoesNotExist:
            return Response({"detail": "Invalid OTP token."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data["new_password"])
        user.clear_otp()
        user.save()

        return Response({"detail": "Password reset successfully."}, status=status.HTTP_200_OK)


# -----------------------------
# Logout View
# -----------------------------
class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh"]

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST)

        # Track logout activity
        request.user.update_last_activity()

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)