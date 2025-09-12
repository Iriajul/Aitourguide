# apps/admin_api/serializers.py
from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.models import User
from apps.scans.models import Scan
from django.utils.timesince import timesince
from django.utils import timezone

# -----------------------------
# Admin Login
# -----------------------------
class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")
        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not (user.is_staff or user.is_superuser or user.role == "admin"):
            raise serializers.ValidationError("You do not have admin access.")
        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "is_staff": user.is_staff,
            },
        }

# -----------------------------
# Admin Forgot Password
# -----------------------------
class AdminPasswordForgotSerializer(serializers.Serializer):
    email = serializers.EmailField()

# -----------------------------
# Admin OTP Verify
# -----------------------------
class AdminOTPVerifySerializer(serializers.Serializer):
    otp = serializers.CharField(max_length=6)

# -----------------------------
# Admin Password Reset
# -----------------------------
class AdminPasswordResetSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=8)
    confirm_password = serializers.CharField(min_length=8)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs

# -----------------------------
# Admin Logout Serializer
# -----------------------------
class AdminLogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

# -----------------------------
# Admin Protected API Serializer (optional)
# -----------------------------
class AdminDashboardSerializer(serializers.Serializer):
    message = serializers.CharField(read_only=True)
    user = serializers.DictField(read_only=True)

# -----------------------------
# Admin Overview Serializer
# -----------------------------
class AdminOverviewSerializer(serializers.Serializer):
    # Input field to request filter type
    date_range = serializers.ChoiceField(
        choices=["weekly", "monthly", "yearly"],
        default="monthly",
        write_only=True
    )

    # High-level metrics
    total_users = serializers.IntegerField()
    new_users = serializers.IntegerField()
    premium_users = serializers.IntegerField()
    inactive_users = serializers.IntegerField()
    new_users_change = serializers.CharField()  # e.g., "↑ 12%"
    total_users_change = serializers.CharField()  # e.g., "↑ 8%"
    premium_users_change = serializers.CharField()  # e.g., "↓ 3%"
    inactive_users_change = serializers.CharField()  # e.g., "↓ 5%"
    is_new_users_increase = serializers.BooleanField()  # New boolean field
    is_total_users_increase = serializers.BooleanField()  # New boolean field
    is_premium_users_increase = serializers.BooleanField()  # New boolean field
    is_inactive_users_increase = serializers.BooleanField()  # New boolean field

    # Engagement stats
    daily_avg_active_users = serializers.IntegerField()
    engagement_rate = serializers.FloatField()

    # Boosting stats
    total_boosted_hours = serializers.IntegerField()
    boosting_engagement_rate = serializers.FloatField()
    boosting_engagement_change = serializers.CharField()  # e.g., "↑ 12.5%"
    is_boosting_increase = serializers.BooleanField()  # New boolean field

    # Search stats
    total_searches = serializers.IntegerField()
    search_engagement_rate = serializers.FloatField()
    search_engagement_change = serializers.CharField()  # e.g., "↑ 15.4%"
    is_search_increase = serializers.BooleanField()  # New boolean field

    # Premium insights
    active_premium_users = serializers.FloatField()
    renewal_rate = serializers.FloatField()
    churn_rate = serializers.FloatField()

    # Search frequency breakdown (per user)
    search_frequency = serializers.ListField()

    # Contextual meta
    last_updated = serializers.DateTimeField()

# -----------------------------
# User Activity Serializer
# -----------------------------
class UserActivitySerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    activity_type = serializers.SerializerMethodField()  # Changed to SerializerMethodField
    time = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    photo = serializers.CharField(source='image_url')
    action = serializers.SerializerMethodField()

    class Meta:
        model = Scan
        fields = [
            'id',
            'user',
            'activity_type',
            'time',
            'status',
            'photo',
            'action',
        ]

    def get_user(self, obj):
        return {
            'username': obj.user.username,
            'profile_picture_url': obj.user.profile_picture_url,
        }

    def get_time(self, obj):
        return timesince(obj.created_at) + " ago"

    def get_status(self, obj):
        return "Premium" if getattr(obj.user, 'is_active_premium', False) else "Free"

    def get_action(self, obj):
        return obj.id  # Use ID for delete action

    def get_activity_type(self, obj):
        """Map source to activity type."""
        return "Clicked" if obj.source == "camera" else "Upload"
    
    # -----------------------------
# Manage Users Serializers
# -----------------------------
class ManageUserSubscriptionSerializer(serializers.Serializer):
    duration = serializers.ChoiceField(choices=[
        '1h', '6h', '12h', '24h', '2d', '5d', '7d', '10d', 'lifetime'
    ])

class ManageUserBanSerializer(serializers.Serializer):
    duration = serializers.ChoiceField(choices=[
        '1h', '6h', '12h', '24h', '2d', '5d', '7d', '10d'
    ])

class ManageUserUnbanSerializer(serializers.Serializer):
    pass

class ManageUserSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()
    last_active = serializers.SerializerMethodField()
    actions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'user', 'status', 'subscription', 'email', 'last_active', 'actions']

    def get_user(self, obj):
        return {
            'username': obj.username,
            'avatar': obj.profile_picture_url
        }

    def get_status(self, obj):
        if obj.ban_expiry and timezone.now() < obj.ban_expiry:
            return {'text': 'Inactive', 'badge': 'red'}
        return {'text': 'Active', 'badge': 'green'}

    def get_subscription(self, obj):
        return {'text': 'Premium' if obj.is_active_premium else 'Free', 'badge': 'green'}

    def get_last_active(self, obj):
        if obj.last_activity_time:
            return timesince(obj.last_activity_time) + ' ago'
        return 'Never'

    def get_actions(self, obj):
        return {
            'edit_id': obj.id,
            'can_ban': obj.is_active,
            'can_unban': obj.ban_expiry and timezone.now() < obj.ban_expiry
        }