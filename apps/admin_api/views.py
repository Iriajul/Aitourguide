# apps/admin_api/views.py
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.db.models import Count, Sum, Q
from django.db import models
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, ExtractMonth
import calendar
from django.utils.dateparse import parse_date, parse_datetime

from rest_framework import status, permissions, generics, viewsets, pagination
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from apps.users.models import User
from apps.payments.models import Subscription, Payment, SubscriptionPlan
from apps.scans.models import Scan
from apps.users.permissions import IsAdminRole  # Assuming this exists
from .serializers import SubscriptionPlanSerializer, SubscriptionPlanCreateSerializer, UserEarningsSerializer, AdminProfileSerializer, AdminPasswordChangeSerializer, AdminLogoutSerializer

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


# ---------------- ADMIN PROFILE ----------------
class AdminProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    serializer_class = AdminProfileSerializer

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

# ---------------- ADMIN PASSWORD CHANGE ----------------
class AdminPasswordChangeView(generics.GenericAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    serializer_class = AdminPasswordChangeSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        # Invalidate all existing tokens for this user
        OutstandingToken.objects.filter(user=user).delete()
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)
    
# ---------------- LOGOUT ----------------
class AdminLogoutView(generics.GenericAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def post(self, request):
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
    permission_classes = [IsAdminRole]
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
    permission_classes = [IsAdminRole]
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


# ---------------- ANALYTICS ----------------
class ReturningUsersView(generics.GenericAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)

        period = request.query_params.get("period", "monthly").lower()

        now = timezone.now()
        if period == "weekly":
            start = now - timedelta(days=7)
        elif period == "yearly":
            start = now - timedelta(days=365)
        else:  # monthly
            start = now - timedelta(days=30)

        # Returning Users (no custom date range)
        returning_users = (
            User.objects.filter(scans__created_at__gte=start, scans__created_at__lte=now)
            .annotate(scan_count=Count("scans"))
            .filter(scan_count__gt=1)
        )
        if period == "weekly":
            returning_users = (
                returning_users
                .annotate(day=TruncDay("scans__created_at"))
                .values("day")
                .annotate(count=Count("id", distinct=True))
                .order_by("day")
            )
        elif period == "monthly":
            returning_users = (
                returning_users
                .annotate(week=TruncWeek("scans__created_at"))
                .values("week")
                .annotate(count=Count("id", distinct=True))
                .order_by("week")
            )
        else:  # yearly
            returning_users = (
                returning_users
                .annotate(month=TruncMonth("scans__created_at"))
                .values("month")
                .annotate(count=Count("id", distinct=True))
                .order_by("month")
            )

        # Convert to desired format
        returning_users_data = {
            "weekly": [],
            "monthly": [],
            "yearly": []
        }
        for item in returning_users:
            if period == "weekly":
                day_name = item["day"].strftime("%a")  # e.g., "Sun", "Mon"
                returning_users_data["weekly"].append({"label": day_name, "count": item["count"]})
            elif period == "monthly":
                week_num = (item["week"].day - 1) // 7 + 1  # Approximate week number (1-4)
                week_name = f"Week{week_num}"
                returning_users_data["monthly"].append({"label": week_name, "count": item["count"]})
            else:  # yearly
                month_name = calendar.month_abbr[item["month"].month]  # e.g., "Sep", "Aug"
                returning_users_data["yearly"].append({"label": month_name, "count": item["count"]})

        data = returning_users_data

        print("Data before serialization:", data)

        from .serializers import ReturningUsersSerializer
        serializer = ReturningUsersSerializer(data)
        return Response(serializer.data)

class RevenueGrowthView(generics.GenericAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)

        # Get the selected year, default to current year
        selected_year = request.query_params.get("year")
        current_year = timezone.now().year
        if selected_year:
            try:
                selected_year = int(selected_year)
                if selected_year < 2025 or selected_year > 2030:
                    return Response({"detail": "Year must be between 2025 and 2030."}, status=400)
            except ValueError:
                return Response({"detail": "Invalid year format. Use YYYY."}, status=400)
        else:
            selected_year = current_year  # Default to current running year (e.g., 2025 now, 2026 next year)

        # Generate start and end dates for the selected year
        start_date = timezone.make_aware(timezone.datetime(selected_year, 1, 1), timezone.get_current_timezone())
        end_date = timezone.make_aware(timezone.datetime(selected_year, 12, 31, 23, 59, 59), timezone.get_current_timezone())

        # Fetch revenue data for the selected year
        revenue_data = (
            Payment.objects.filter(payment_date__gte=start_date, payment_date__lte=end_date)
            .annotate(month=TruncMonth("payment_date"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month")
        )
        revenue_map = {item["month"]: float(item["total"] or 0) for item in revenue_data}

        # Generate monthly breakdown with zeros
        revenue_growth = [
            {"month": calendar.month_abbr[month], "total": revenue_map.get(timezone.make_aware(timezone.datetime(selected_year, month, 1), timezone.get_current_timezone()), 0.0)}
            for month in range(1, 13)
        ]

        # Calculate total revenue for the year
        total_revenue = float(
            Payment.objects.filter(payment_date__gte=start_date, payment_date__lte=end_date)
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        data = {
            "revenue_growth": revenue_growth,
            "total_revenue": total_revenue
        }

        print("Data before serialization:", data)

        from .serializers import RevenueGrowthSerializer
        serializer = RevenueGrowthSerializer(data)
        return Response(serializer.data)

class RevenueLeaderboardView(generics.GenericAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)

        period = request.query_params.get("period", "monthly").lower()
        leaderboard_count = int(request.query_params.get("leaderboard_count", 3))

        now = timezone.now()
        if period == "weekly":
            start = now - timedelta(days=7)
        elif period == "yearly":
            start = now - timedelta(days=365)
        else:  # monthly
            start = now - timedelta(days=30)

        print(f"Period: {period}, Start Date: {start}, Now: {now}")

        # Revenue Leaderboard
        leaderboard = (
            User.objects.annotate(
                total_revenue=Sum("payments__amount", filter=Q(payments__payment_date__gte=start, payments__payment_date__lte=now))
            )
            .filter(total_revenue__isnull=False)
            .order_by("-total_revenue")[:leaderboard_count]
            .values("username", "profile_picture_url", "total_revenue")
        )
        print("Annotated Query:", User.objects.annotate(total_revenue=Sum("payments__amount", filter=Q(payments__payment_date__gte=start, payments__payment_date__lte=now))).query)
        total_revenue = float(
            Payment.objects.filter(payment_date__gte=start, payment_date__lte=now)
            .aggregate(total=Sum("amount"))["total"] or 0
        )
        total_users = User.objects.count()
        avg_revenue_per_user = total_revenue / total_users if total_users else 0
        last_month_revenue = float(
            Payment.objects.filter(payment_date__gte=now - timedelta(days=30))
            .aggregate(total=Sum("amount"))["total"] or 0
        )
        prev_month_revenue = float(
            Payment.objects.filter(
                payment_date__gte=now - timedelta(days=60), payment_date__lt=now - timedelta(days=30)
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )
        growth_percentage = (
            ((last_month_revenue - prev_month_revenue) / prev_month_revenue * 100)
            if prev_month_revenue
            else 0
        ) if last_month_revenue or prev_month_revenue else 0

        data = {
            "top_users": [
                {"username": item["username"], "avatar_url": item["profile_picture_url"], "revenue": float(item["total_revenue"] if item["total_revenue"] is not None else 0)}
                for item in leaderboard
            ],
            "average_revenue_per_user": avg_revenue_per_user,
            "growth_percentage": growth_percentage,
        }

        print("Data before serialization:", data)

        from .serializers import RevenueLeaderboardSerializer
        serializer = RevenueLeaderboardSerializer(data)
        return Response(serializer.data)

class UserStatusDistributionView(generics.GenericAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)

        # User Status Distribution
        user_status = {
            "total": User.objects.count(),
            "free_count": User.objects.filter(is_active_premium=False).count(),
            "premium_count": User.objects.filter(is_active_premium=True).count(),
            "free_percentage": 0,
            "premium_percentage": 0,
        }
        if user_status["total"] > 0:
            user_status["free_percentage"] = round(
                (user_status["free_count"] / user_status["total"]) * 100, 2
            )
            user_status["premium_percentage"] = round(
                (user_status["premium_count"] / user_status["total"]) * 100, 2
            )

        data = user_status

        print("Data before serialization:", data)

        from .serializers import UserStatusDistributionSerializer
        serializer = UserStatusDistributionSerializer(data)
        return Response(serializer.data)


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
    page_size = 7
    page_size_query_param = "limit"
    max_page_size = 100

class UserActivityView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
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
    permission_classes = [IsAdminRole]
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


# ---------------- MANAGE USERS ----------------
class ManageUsersPagination(PageNumberPagination):
    page_size = 7
    page_size_query_param = "limit"
    max_page_size = 100

class ManageUsersView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    serializer_class = None
    pagination_class = ManageUsersPagination

    def get_queryset(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return User.objects.none()

        queryset = User.objects.all()

        # Search by username or email
        search_query = self.request.query_params.get("search", "").lower()
        if search_query:
            queryset = queryset.filter(
                models.Q(username__icontains=search_query) |
                models.Q(email__icontains=search_query)
            )

        # Filter by subscription
        subscription = self.request.query_params.get("subscription", "all").lower()
        if subscription == "premium":
            queryset = queryset.filter(is_active_premium=True)
        elif subscription == "free":
            queryset = queryset.filter(is_active_premium=False)

        # Filter by status
        status = self.request.query_params.get("status", "all").lower()
        if status == "active":
            queryset = queryset.filter(ban_expiry__isnull=True) | queryset.filter(ban_expiry__lt=timezone.now())
        elif status == "inactive":
            queryset = queryset.filter(ban_expiry__gt=timezone.now())

        # Filter by ban status
        banned = self.request.query_params.get("banned", "all").lower()
        if banned == "true":
            queryset = queryset.filter(ban_expiry__gt=timezone.now())
        elif banned == "false":
            queryset = queryset.filter(ban_expiry__isnull=True) | queryset.filter(ban_expiry__lt=timezone.now())

        return queryset.order_by("-last_activity_time")

    def list(self, request, *args, **kwargs):
        from .serializers import ManageUserSerializer
        self.serializer_class = ManageUserSerializer
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        results = serializer.data

        total_results = queryset.count()
        search_query = request.query_params.get("search", "")
        subscription_filter = request.query_params.get("subscription", "all")
        status_filter = request.query_params.get("status", "all")
        banned_filter = request.query_params.get("banned", "all")
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
        if subscription_filter != "all":
            message += f" ({subscription_filter.capitalize()} subscription)"
        if status_filter != "all":
            message += f" ({status_filter.capitalize()} users)"
        if banned_filter != "all":
            message += f" (Banned: {banned_filter.capitalize()})"

        return self.get_paginated_response({
            "message": message,
            "results": results
        })

class ManageUserSubscriptionView(generics.UpdateAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def patch(self, request, *args, **kwargs):
        from .serializers import ManageUserSubscriptionSerializer
        user = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser or request.user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)

        serializer = ManageUserSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duration = serializer.validated_data["duration"]
        user.set_subscription_duration(duration)
        return Response({"detail": f"Subscription updated to {duration} for {user.username}."}, status=200)

    def get_object(self):
        return User.objects.get(id=self.kwargs["id"])

class ManageUserBanView(generics.UpdateAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def patch(self, request, *args, **kwargs):
        from .serializers import ManageUserBanSerializer
        user = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser or request.user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)

        serializer = ManageUserBanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duration = serializer.validated_data["duration"]
        user.set_ban_duration(duration)
        return Response({"detail": f"User {user.username} banned for {duration}."}, status=200)

    def get_object(self):
        return User.objects.get(id=self.kwargs["id"])

class ManageUserUnbanView(generics.UpdateAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        if not (request.user.is_staff or user.is_superuser or request.user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)
        from .serializers import ManageUserUnbanSerializer
        serializer = ManageUserUnbanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.unban()
        return Response({"detail": f"User {user.username} unbanned."}, status=200)

    def get_object(self):
        return User.objects.get(id=self.kwargs["id"])

class ManageUserDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        if not (request.user.is_staff or request.user.is_superuser or request.user.role == "admin"):
            return Response({"detail": "Access denied."}, status=403)
        username = user.username
        user.delete()
        return Response({"detail": f"User {username} deleted."}, status=200)

    def get_object(self):
        return User.objects.get(id=self.kwargs["id"])


# ---------------- NON-PAGINATED SUBSCRIPTION PLANS FOR DROPDOWN ----------------
class SubscriptionPlansAllView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return SubscriptionPlan.objects.none()
        return SubscriptionPlan.objects.all().order_by('name')


# ---------------- PAYMENT RECORDS ----------------
class PaymentRecordPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "limit"
    max_page_size = 100

class PaymentRecordView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    serializer_class = None
    pagination_class = PaymentRecordPagination

    def get_queryset(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Payment.objects.none()

        queryset = Payment.objects.select_related('user', 'subscription__plan').all()

        # Search by username or email
        search_query = self.request.query_params.get("search", "").lower()
        if search_query:
            queryset = queryset.filter(
                Q(user__username__icontains=search_query) |
                Q(user__email__icontains=search_query)
            )

        # Filter by subscription plan name dynamically
        subscription_plan = self.request.query_params.get("subscription_plan", "").strip().lower()
        if subscription_plan and subscription_plan != "all":
            queryset = queryset.filter(subscription__plan__name__iexact=subscription_plan)

        # Filter by subscription type
        subscription_type = self.request.query_params.get("subscription", "all").lower()
        if subscription_type != "all":
            queryset = queryset.filter(subscription__plan_type=subscription_type)

        # Filter by payment status (if you have a status field)
        status = self.request.query_params.get("status", "all").lower()
        if status != "all":
            queryset = queryset.filter(status=status)

        # Filter by date range
        start_date = self.request.query_params.get("start_date")
        end_date = self.request.query_params.get("end_date")
        if start_date:
            try:
                queryset = queryset.filter(payment_date__gte=parse_date(start_date))
            except ValueError:
                pass
        if end_date:
            try:
                queryset = queryset.filter(payment_date__lte=parse_date(end_date))
            except ValueError:
                pass

        # Order by payment_date descending
        return queryset.order_by("-payment_date")

    def list(self, request, *args, **kwargs):
        from .serializers import PaymentRecordSerializer
        self.serializer_class = PaymentRecordSerializer
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        results = serializer.data

        total_results = queryset.count()
        search_query = request.query_params.get("search", "")
        subscription_plan_filter = request.query_params.get("subscription_plan", "All")
        subscription_filter = request.query_params.get("subscription", "all")
        status_filter = request.query_params.get("status", "all")
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
        if subscription_plan_filter != "All":
            message += f" (Subscription Plan: '{subscription_plan_filter}')"
        if subscription_filter != "all":
            message += f" ({subscription_filter.capitalize()} subscriptions)"
        if status_filter != "all":
            message += f" ({status_filter.capitalize()} payments)"

        return self.get_paginated_response({
            "message": message,
            "results": results
        })
    
# Payment Record Delete View
class PaymentRecordDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Payment.objects.none()
        return Payment.objects.all()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        payment_id = instance.id
        if instance.subscription:
            instance.subscription.delete()  # Delete associated subscription
        self.perform_destroy(instance)
        return Response(
            {"message": f"Payment record with id {payment_id} and associated subscription deleted successfully."},
            status=status.HTTP_200_OK
        )

# Payment Record Toggle View (Pause/Play)
class PaymentRecordToggleView(generics.UpdateAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            return Payment.objects.none()
        return Payment.objects.select_related('subscription').all()

    def patch(self, request, *args, **kwargs):
        from .serializers import PaymentRecordToggleSerializer
        instance = self.get_object()
        if not instance.subscription:
            return Response({"message": "No subscription associated with this payment."}, status=400)

        action = request.data.get("action")
        if action not in ["pause", "play"]:
            return Response({"message": "Invalid action. Use 'pause' or 'play'."}, status=400)

        subscription = instance.subscription
        current_time = timezone.now()

        if action == "pause":
            if not subscription.is_paused:
                subscription.is_paused = True
                subscription.save()
                return Response({"message": f"Subscription {subscription.id} paused successfully."}, status=200)
            return Response({"message": "Subscription is already paused."}, status=400)

        elif action == "play":
            if subscription.is_paused:
                if current_time < subscription.end_time:
                    subscription.is_paused = False
                    # Optional: Adjust end_time if admin provides new_end_time
                    new_end_time = request.data.get("new_end_time")
                    if new_end_time:
                        try:
                            subscription.end_time = parse_datetime(new_end_time)
                        except ValueError:
                            pass
                    subscription.save()
                    return Response({"message": f"Subscription {subscription.id} resumed successfully."}, status=200)
                return Response({"message": "Subscription has expired and cannot be resumed."}, status=400)
            return Response({"message": "Subscription is not paused."}, status=400)


# ---------------- SUBSCRIPTION PLAN MANAGEMENT ----------------
class SubscriptionPlanPagination(pagination.PageNumberPagination):
    page_size = 4  # Number of items per page
    page_size_query_param = 'page_size'  # Allow client to override page size
    max_page_size = 10  # Maximum page size

class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all().order_by('id')  # Explicitly order by id
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    pagination_class = SubscriptionPlanPagination  # Apply pagination

    def get_serializer_class(self):
        if self.action == 'create':
            return SubscriptionPlanCreateSerializer
        return SubscriptionPlanSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def perform_update(self, serializer):
        # Handle pause/play toggle
        instance = serializer.save()
        if 'is_paused' in serializer.validated_data:
            instance.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    

# ---------------- MOST POPULAR PLANS ----------------
class PopularPlansView(generics.GenericAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        from .serializers import PopularPlansSerializer
        from django.db.models import Count
        from django.utils import timezone

        # Get active subscriptions (boost plans that are active, not expired, and have a valid plan)
        now = timezone.now()
        active_subscriptions = Subscription.objects.filter(
            plan_type="boost",
            is_active=True,
            end_time__gt=now,
            is_paused=False,
            plan__isnull=False  # Exclude subscriptions with no plan
        ).select_related('plan')

        total_active_subscribers = active_subscriptions.count()

        if total_active_subscribers == 0:
            return Response({
                "most_popular": [],
                "total_subscribers": 0
            }, status=status.HTTP_200_OK)

        # Annotate with subscriber count per plan
        popular_plans = active_subscriptions.values('plan__id', 'plan__name', 'plan__description').annotate(
            subscriber_count=Count('id')
        ).order_by('-subscriber_count')[:2]  # Top 2 plans

        # Prepare data for serializer
        most_popular = []
        for plan_data in popular_plans:
            plan_id = plan_data['plan__id']
            plan_name = plan_data['plan__name']
            description = plan_data['plan__description'] or f"Popular plan: {plan_name}"  # Fallback if no description
            count = plan_data['subscriber_count']
            percentage = (count / total_active_subscribers * 100)

            # Icons (customize based on plan name)
            icons = {
                "Lifetime": "lifetime-icon",
                "10 days": "10days-icon",
                "24 hours": "24hours-icon",  # Added for 24 hours
                # Add more as needed
            }
            icon = icons.get(plan_name, "default-icon")

            most_popular.append({
                "name": plan_name,
                "percentage": f"{int(percentage)}%",
                "description": description,
                "icon": icon,
                "subscriber_count": count
            })

        data = {
            "most_popular": most_popular,
            "total_subscribers": total_active_subscribers
        }

        serializer = PopularPlansSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
# ---------------- USER EARNINGS ----------------
class UserEarningsPagination(PageNumberPagination):
    page_size = 4  # Number of items per page
    page_size_query_param = 'page_size'  # Allow client to override page size
    max_page_size = 10  # Maximum page size

class UserEarningsView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    authentication_classes = [JWTAuthentication]
    serializer_class = UserEarningsSerializer
    pagination_class = UserEarningsPagination

    def get_queryset(self):
        search_query = self.request.query_params.get('search', '')
        filter_status = self.request.query_params.get('status', 'all')

        queryset = Payment.objects.select_related('user', 'subscription').all()

        if search_query:
            queryset = queryset.filter(
                Q(user__username__icontains=search_query) |
                Q(user__email__icontains=search_query)
            )

        if filter_status != 'all':
            queryset = queryset.filter(user__is_active=(filter_status.lower() == 'active'))

        return queryset.order_by('-payment_date')