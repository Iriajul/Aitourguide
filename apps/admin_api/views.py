# apps/admin_api/views.py
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.db.models import Count
from django.db import models

from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination

from apps.users.models import User
from apps.payments.models import Subscription
from apps.scans.models import Scan

RESET_COOKIE_NAME = "admin_reset_email"
RESET_COOKIE_MAX_AGE = 10 * 60  # 10 minutes
RESET_COOKIE_SAMESITE = "None" if not settings.DEBUG else "Lax"
RESET_COOKIE_SECURE = not settings.DEBUG
RESET_COOKIE_HTTPONLY = True


def _send_admin_otp_email(email: str, otp: str):
    subject = "Your Admin Password Reset Code"
    message = f"Your OTP is: {otp}. It will expire in 5 minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    try:
        send_mail(subject, message, from_email, [email], fail_silently=False)
    except Exception:
        pass


def get_cookie_domain():
    # Use localhost for development, your actual domain for production
    if settings.DEBUG:
        return "localhost"
    return ".devtunnels.ms"  # Change to your production domain when deploying


# ---------------- LOGIN (Step 1: Send OTP) ----------------
class AdminLoginView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .serializers import AdminLoginSerializer
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        # Only allow admin users
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Not permitted."}, status=403)

        # Generate and send OTP
        otp = user.set_otp(length=6, expiry_minutes=5)
        _send_admin_otp_email(user.email, otp)
        return Response({"detail": "OTP sent to email.", "email": user.email}, status=200)


# ---------------- LOGIN OTP VERIFY (Step 2: Issue Token) ----------------
class AdminLoginOTPVerifyView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")
        if not email or not otp:
            return Response({"detail": "Email and OTP required."}, status=400)
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Invalid email."}, status=400)
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Not permitted."}, status=403)
        if not user.verify_otp(otp):
            return Response({"detail": "Invalid or expired OTP."}, status=400)

        # Issue JWT token
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        return Response(
            {
                "refresh": str(refresh),
                "access": str(access),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "role": user.role,
                    "is_staff": user.is_staff,
                },
            },
            status=200,
        )


# ---------------- LOGOUT ----------------
class AdminLogoutView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        from .serializers import AdminLogoutSerializer
        serializer = AdminLogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data["refresh"]
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            return Response({"detail": "Invalid token."}, status=400)
        return Response({"detail": "Logged out successfully."}, status=200)


# ---------------- DASHBOARD (JWT Protected) ----------------
class AdminDashboardView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        from .serializers import AdminDashboardSerializer
        user = request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)
        data = {
            "message": "Welcome to admin dashboard",
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "is_staff": user.is_staff,
            },
        }
        serializer = AdminDashboardSerializer(data)
        return Response(data, status=status.HTTP_200_OK)


# ---------------- ADMIN OVERVIEW ----------------
class AdminOverviewView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)

        now = timezone.now()

        # Get period from query param (weekly, monthly, yearly)
        period = request.query_params.get("period", "weekly").lower()
        if period == "weekly":
            start_date = now - timedelta(days=7)
            prev_start_date = now - timedelta(days=14)
            prev_end_date = now - timedelta(days=7)
            days_in_period = 7
        elif period == "monthly":
            start_date = now - timedelta(days=30)
            prev_start_date = now - timedelta(days=60)
            prev_end_date = now - timedelta(days=30)
            days_in_period = 30
        elif period == "yearly":
            start_date = now - timedelta(days=365)
            prev_start_date = now - timedelta(days=730)
            prev_end_date = now - timedelta(days=365)
            days_in_period = 365
        else:
            return Response(
                {"detail": "Invalid period. Use weekly, monthly, or yearly."},
                status=400,
            )

        # ---------------- Users Metrics ----------------
        total_users = User.objects.count()
        new_users = User.objects.filter(date_joined__gte=start_date).count()
        inactive_users = User.objects.filter(is_active=False).count()

        # Premium users (active boost)
        premium_users = Subscription.objects.filter(plan_type="boost", is_active=True, end_time__gt=now).count()

        # Previous period metrics
        prev_new_users = User.objects.filter(date_joined__range=[prev_start_date, prev_end_date]).count()
        prev_total_users = User.objects.filter(date_joined__lte=prev_end_date).count()
        prev_premium_users = Subscription.objects.filter(plan_type="boost", is_active=True, end_time__gt=prev_end_date).count()
        prev_inactive_users = User.objects.filter(is_active=False, last_activity_time__lte=prev_end_date).count()

        # Calculate percentage changes and boolean indicators for users
        new_users_change = ((new_users - prev_new_users) / prev_new_users * 100) if prev_new_users else 0
        total_users_change = ((total_users - prev_total_users) / prev_total_users * 100) if prev_total_users else 0
        premium_users_change = ((premium_users - prev_premium_users) / prev_premium_users * 100) if prev_premium_users else 0
        inactive_users_change = ((inactive_users - prev_inactive_users) / prev_inactive_users * 100) if prev_inactive_users else 0
        is_new_users_increase = new_users_change > 0
        is_total_users_increase = total_users_change > 0
        is_premium_users_increase = premium_users_change > 0
        is_inactive_users_increase = inactive_users_change > 0

        # Engagement stats (dynamic calculation only - no fallback)
        daily_active_users = User.objects.filter(last_activity_time__gte=start_date).count()
        daily_avg_active_user = round(daily_active_users / days_in_period, 2) if days_in_period else daily_active_users
        engagement_rate = round((daily_avg_active_user / total_users) * 100, 2) if total_users else 0.0

        # Boosting stats (current and previous period)
        total_boosted_hours = Subscription.objects.filter(plan_type="boost").aggregate(
            total=models.Sum("total_boosted_hours")
        )["total"] or 0.0
        boosting_engagement_rate = round((total_boosted_hours / (total_users * 24)) * 100, 2) if total_users else 0
        prev_total_boosted_hours = Subscription.objects.filter(
            plan_type="boost", start_time__range=[prev_start_date, prev_end_date]
        ).aggregate(total=models.Sum("total_boosted_hours"))["total"] or 0.0
        prev_boosting_engagement_rate = round((prev_total_boosted_hours / (prev_total_users * 24)) * 100, 2) if prev_total_users else 0
        boosting_engagement_change = ((boosting_engagement_rate - prev_boosting_engagement_rate) / prev_boosting_engagement_rate * 100) if prev_boosting_engagement_rate else 0
        is_boosting_increase = boosting_engagement_change > 0

        # Search activity (current and previous period)
        total_searches = Scan.objects.count()
        period_searches = Scan.objects.filter(created_at__gte=start_date).count()
        search_engagement_rate = round((total_searches / total_users) * 100, 2) if total_users else 0
        prev_period_searches = Scan.objects.filter(created_at__range=[prev_start_date, prev_end_date]).count()
        prev_search_engagement_rate = round((prev_period_searches / prev_total_users) * 100, 2) if prev_total_users else 0
        search_engagement_change = ((search_engagement_rate - prev_search_engagement_rate) / prev_search_engagement_rate * 100) if prev_search_engagement_rate else 0
        is_search_increase = search_engagement_change > 0

        # Premium insights
        active_premium_user = premium_users
        renewal_rate = Subscription.objects.filter(plan_type="boost", is_renewed=True, end_time__gt=now).count()
        churn_rate = Subscription.objects.filter(plan_type="boost", is_active=False).count()

        # Search frequency per user
        search_frequency = []
        for user_obj in User.objects.all():
            search_count = Scan.objects.filter(user=user_obj).count()
            status = "premium" if getattr(user_obj, "is_active_premium", False) else "free"
            search_frequency.append({
                "name": user_obj.username,
                "status": status,
                "search_history": search_count
            })

        overview = {
            "total_users": total_users,
            "new_users": new_users,
            "premium_users": premium_users,
            "inactive_users": inactive_users,
            "new_users_change": f"↑ {abs(new_users_change):.0f}%" if new_users_change > 0 else f"↓ {abs(new_users_change):.0f}%" if new_users_change < 0 else "0%",
            "total_users_change": f"↑ {abs(total_users_change):.0f}%" if total_users_change > 0 else f"↓ {abs(total_users_change):.0f}%" if total_users_change < 0 else "0%",
            "premium_users_change": f"↑ {abs(premium_users_change):.0f}%" if premium_users_change > 0 else f"↓ {abs(premium_users_change):.0f}%" if premium_users_change < 0 else "0%",
            "inactive_users_change": f"↑ {abs(inactive_users_change):.0f}%" if inactive_users_change > 0 else f"↓ {abs(inactive_users_change):.0f}%" if inactive_users_change < 0 else "0%",
            "is_new_users_increase": is_new_users_increase,
            "is_total_users_increase": is_total_users_increase,
            "is_premium_users_increase": is_premium_users_increase,
            "is_inactive_users_increase": is_inactive_users_increase,
            "engagement_stats": {
                "daily_avg_active_user": daily_avg_active_user,
                "engagement_rate": engagement_rate
            },
            "boosting_stats": {
                "total_boosted_hours": total_boosted_hours,
                "boosting_engagement_rate": boosting_engagement_rate,
                "boosting_engagement_change": f"↑ {abs(boosting_engagement_change):.1f}%" if boosting_engagement_change > 0 else f"↓ {abs(boosting_engagement_change):.1f}%" if boosting_engagement_change < 0 else "0%",
                "is_boosting_increase": is_boosting_increase
            },
            "search_activity": {
                "total_searches": total_searches,
                "search_engagement_rate": search_engagement_rate,
                "search_engagement_change": f"↑ {abs(search_engagement_change):.1f}%" if search_engagement_change > 0 else f"↓ {abs(search_engagement_change):.1f}%" if search_engagement_change < 0 else "0%",
                "is_search_increase": is_search_increase
            },
            "premium_insights": {
                "active_premium_user": active_premium_user,
                "renewal_rate": renewal_rate,
                "churn_rate": churn_rate,   
            },
            "search_frequency": search_frequency
        }

        return Response({
            "greeting": f"Good morning {user.username}",
            "period": period,
            "overview": overview
        })


# ---------------- FORGOT PASSWORD ----------------
class AdminPasswordForgotView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .serializers import AdminPasswordForgotSerializer
        serializer = AdminPasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
            if user.is_staff or user.is_superuser or user.role == "admin":
                otp = user.set_otp(length=6, expiry_minutes=5)
                _send_admin_otp_email(email, otp)
        except User.DoesNotExist:
            pass

        return Response({"detail": "If valid, OTP sent."}, status=200)


# ---------------- VERIFY OTP ----------------
class AdminOTPVerifyView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .serializers import AdminOTPVerifySerializer
        email = request.data.get("email")

        if not email:
            return Response({"detail": "Email is required."}, status=400)

        serializer = AdminOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data["otp"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Reset session invalid."}, status=400)

        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Not permitted."}, status=403)

        if not user.verify_otp(otp):
            return Response({"detail": "Invalid or expired code."}, status=400)

        return Response({"detail": "OTP verified. You can set a new password."}, status=200)


# ---------------- RESEND OTP ----------------
class AdminOTPResendView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"detail": "Email is required."}, status=400)

        try:
            user = User.objects.get(email=email)
            if not (user.is_staff or user.is_superuser or user.role == "admin"):
                return Response({"detail": "Not permitted."}, status=403)
            otp = user.set_otp(length=6, expiry_minutes=5)
            _send_admin_otp_email(email, otp)
        except User.DoesNotExist:
            return Response({"detail": "Reset session invalid."}, status=400)

        return Response({"detail": "A new OTP has been sent."}, status=200)


# ---------------- RESET PASSWORD ----------------
class AdminPasswordResetView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from .serializers import AdminPasswordResetSerializer
        email = request.data.get("email")
        if not email:
            return Response({"detail": "Email is required."}, status=400)

        serializer = AdminPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"detail": "Reset session invalid."}, status=400)

        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Not permitted."}, status=403)

        user.set_password(serializer.validated_data["new_password"])
        user.clear_otp()
        user.save(update_fields=["password", "otp_code", "otp_expiry"])

        return Response({"detail": "Password updated. You can go to dashboard."}, status=200)


# ---------------- USER ACTIVITY ----------------
class UserActivityPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "limit"
    max_page_size = 100

class UserActivityView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = None  # Will be set by importing serializer later
    pagination_class = UserActivityPagination

    def get_queryset(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Scan.objects.none()

        queryset = Scan.objects.all()

        # Search by username
        search_query = self.request.query_params.get("search", "").lower()
        if search_query:
            queryset = queryset.filter(user__username__icontains=search_query)

        # Filter by activity type
        activity_type = self.request.query_params.get("type", "all").lower()
        if activity_type == "clicked":
            queryset = queryset.filter(source="camera")
        elif activity_type == "upload":
            queryset = queryset.filter(source="gallery")

        return queryset.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        from .serializers import UserActivitySerializer  # Import here to avoid circular imports
        self.serializer_class = UserActivitySerializer
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        results = serializer.data

        total_results = queryset.count()
        search_query = request.query_params.get("search", "")
        type_filter = request.query_params.get("type", "all")
        paginator = self.paginator
        if hasattr(paginator, 'page'):
            page_number = paginator.page.number
            page_size = paginator.page_size
            start_idx = (page_number - 1) * page_size + 1
            end_idx = start_idx + len(results) - 1
            message = f"Showing {start_idx} to {end_idx} of {total_results} records"
        else:
            message = f"Showing {len(results)} of {total_results} records"

        if search_query:
            message += f" for '{search_query}'"
        if type_filter != "all":
            message += f" ({type_filter.capitalize()} activities)"

        return self.get_paginated_response({
            "message": message,
            "results": results
        })


class UserActivityDeleteView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Scan.objects.none()
        return Scan.objects.all()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        scan_id = instance.id
        self.perform_destroy(instance)
        return Response(
            {"message": f"Scan with id {scan_id} deleted successfully."},
            status=status.HTTP_200_OK
        )