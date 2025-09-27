#apps/admin_api/serializers.py
from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.models import User
from apps.scans.models import Scan
from django.utils.timesince import timesince
from django.utils import timezone
from apps.payments.models import Payment, Subscription, SubscriptionPlan
from pytz import timezone as pytz_timezone
import stripe
from django.conf import settings
from cloudinary.uploader import upload
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

stripe.api_key = settings.STRIPE_SECRET_KEY

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
# Admin Profile Serializer
# -----------------------------


class AdminProfileSerializer(serializers.ModelSerializer):
    profile_picture_url = serializers.SerializerMethodField()  # Read-only for GET
    profile_picture_input = serializers.ImageField(max_length=None, allow_empty_file=False, required=False, write_only=True)  # Writable for PUT

    class Meta:
        model = User
        fields = ['username', 'email', 'profile_picture_url', 'profile_picture_input']
        read_only_fields = ['email', 'profile_picture_url']  # email and output URL are read-only

    def get_profile_picture_url(self, obj):
        return obj.profile_picture_url  # Dynamically fetch the URL from the model

    def update(self, instance, validated_data):
        instance.username = validated_data.get('username', instance.username)
        
        if 'profile_picture_input' in validated_data:
            file_obj = validated_data.get('profile_picture_input')
            if file_obj:
                if isinstance(file_obj, (TemporaryUploadedFile, InMemoryUploadedFile)):
                    try:
                        instance.update_profile_picture(file_obj)
                        instance.refresh_from_db(fields=['profile_picture_url', 'profile_picture_public_id'])
                    except Exception as e:
                        raise serializers.ValidationError(f"Failed to upload profile picture: {str(e)}")
                else:
                    raise serializers.ValidationError("Unsupported file type or missing file.")
            else:
                raise serializers.ValidationError("Invalid file format or missing file.")
        
        instance.save()
        return instance
    
# -----------------------------
# Admin Password Change Serializer
# -----------------------------
class AdminPasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, min_length=8, required=True)
    confirm_password = serializers.CharField(write_only=True, min_length=8, required=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError("New password and confirm password do not match.")
        return data

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value    

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
# Admin Analytics Serializers
# -----------------------------
class ReturningUsersItemSerializer(serializers.Serializer):
    label = serializers.CharField()
    count = serializers.IntegerField()

class ReturningUsersSerializer(serializers.Serializer):
    weekly = serializers.ListField(child=ReturningUsersItemSerializer(), allow_empty=True)
    monthly = serializers.ListField(child=ReturningUsersItemSerializer(), allow_empty=True)
    yearly = serializers.ListField(child=ReturningUsersItemSerializer(), allow_empty=True)

class RevenueGrowthItemSerializer(serializers.Serializer):
    month = serializers.CharField()
    total = serializers.FloatField()

class RevenueGrowthSerializer(serializers.Serializer):
    revenue_growth = serializers.ListField(child=RevenueGrowthItemSerializer())
    total_revenue = serializers.FloatField()

class RevenueLeaderboardItemSerializer(serializers.Serializer):
    username = serializers.CharField()
    avatar_url = serializers.CharField(allow_null=True)
    revenue = serializers.FloatField()

class RevenueLeaderboardSerializer(serializers.Serializer):
    top_users = serializers.ListField(child=RevenueLeaderboardItemSerializer())
    average_revenue_per_user = serializers.FloatField()
    growth_percentage = serializers.FloatField()

class UserStatusDistributionSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    free_count = serializers.IntegerField()
    premium_count = serializers.IntegerField()
    free_percentage = serializers.FloatField()
    premium_percentage = serializers.FloatField()

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

# -----------------------------
# Payment Record Serializers
# -----------------------------
class PaymentRecordSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()
    subscription_name = serializers.SerializerMethodField()
    activate_time = serializers.SerializerMethodField()
    expire_time = serializers.SerializerMethodField()
    last_active = serializers.SerializerMethodField()
    action = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'user', 'subscription_name', 'activate_time', 'expire_time',
            'amount', 'last_active', 'action'
        ]

    def get_user(self, obj):
        return {
            'username': obj.user.username if obj.user else None,
            'avatar': obj.user.profile_picture_url if obj.user and obj.user.profile_picture_url else None
        }

    def get_subscription_name(self, obj):
        if obj.subscription and obj.subscription.plan:
            return obj.subscription.plan.name
        return None

    def get_activate_time(self, obj):
        if obj.subscription and obj.subscription.start_time:
            user_timezone = self._get_user_timezone()
            return timezone.localtime(obj.subscription.start_time, user_timezone).strftime("%b %d, %Y %I:%M %p")
        return None

    def get_expire_time(self, obj):
        if obj.subscription and obj.subscription.end_time:
            user_timezone = self._get_user_timezone()
            return timezone.localtime(obj.subscription.end_time, user_timezone).strftime("%b %d, %Y %I:%M %p")
        return None

    def get_last_active(self, obj):
        if obj.payment_date:
            user_timezone = self._get_user_timezone()
            current_time = timezone.localtime(timezone.now(), user_timezone)
            time_diff = current_time - timezone.localtime(obj.payment_date, user_timezone)
            total_minutes = int(time_diff.total_seconds() / 60)

            if total_minutes < 1:
                return "just now"
            elif total_minutes < 60:
                return f"{total_minutes} minute{'s' if total_minutes > 1 else ''} ago"
            elif total_minutes < 1440:  # 24 hours
                hours = total_minutes // 60
                minutes = total_minutes % 60
                if minutes == 0:
                    return f"{hours} hour{'s' if hours > 1 else ''} ago"
                return f"{hours} hour{'s' if hours > 1 else ''}, {minutes} minute{'s' if minutes > 1 else ''} ago"
            else:
                days = total_minutes // 1440
                return f"{days} day{'s' if days > 1 else ''} ago"
        return None

    def get_action(self, obj):
        actions = {"delete": obj.id}
        if obj.subscription:
            actions["pause_play"] = "play" if not obj.subscription.is_paused else "pause"  # Corrected logic
        return actions

    def _get_user_timezone(self):
        request = self.context.get('request')
        if request and request.headers.get('X-Timezone'):
            try:
                return pytz_timezone(request.headers['X-Timezone'])
            except (KeyError, ValueError):
                pass
        return timezone.get_current_timezone()  # Fallback to default timezone

class PaymentRecordUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['status', 'refunded', 'notes']

    def validate_status(self, value):
        if value not in ['pending', 'completed', 'refunded', 'cancelled']:
            raise serializers.ValidationError("Invalid status.")
        return value

class PaymentRecordToggleSerializer(serializers.ModelSerializer):
    action = serializers.CharField()
    new_end_time = serializers.DateTimeField(required=False)

    class Meta:
        model = Subscription
        fields = ['action', 'new_end_time']

# -----------------------------
# Subscription Plan Serializers
# -----------------------------
class SubscriptionPlanSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'duration', 'price', 'status', 'is_paused', 'currency', 'description', 'stripe_price_id']

    def get_duration(self, obj):
        if obj.duration is None:
            return "Lifetime"
        days = obj.duration.days
        hours = obj.duration.seconds // 3600
        minutes = (obj.duration.seconds % 3600) // 60
        parts = []
        if days > 0: parts.append(f"{days} Day{'s' if days > 1 else ''}")
        if hours > 0: parts.append(f"{hours} Hour{'s' if hours > 1 else ''}")
        if minutes > 0: parts.append(f"{minutes} Minute{'s' if minutes > 1 else ''}")
        return " ".join(parts) if parts else "Lifetime"

    def get_price(self, obj):
        return f"${int(obj.price)} {obj.currency.upper()}"

    def get_status(self, obj):
        return 'Inactive' if obj.is_paused else 'Active'

class SubscriptionPlanCreateSerializer(serializers.ModelSerializer):
    duration = serializers.CharField()  # Changed to CharField for custom validation
    currency = serializers.ChoiceField(choices=['hkd', 'usd', 'eur'])  # Added multiple currency options

    class Meta:
        model = SubscriptionPlan
        fields = ['name', 'duration', 'price', 'currency', 'description']

    def validate_duration(self, value):
        # Split the input (e.g., "9 0 0" into days, hours, minutes)
        try:
            parts = value.split()
            if len(parts) != 3:
                raise ValueError("Duration must be in 'DD HH MM' format.")
            days, hours, minutes = map(int, parts)
            if days < 0 or hours < 0 or minutes < 0 or minutes >= 60:
                raise ValueError("Invalid duration values. Minutes must be 0-59.")
            # Convert to timedelta
            from datetime import timedelta
            return timedelta(days=days, hours=hours, minutes=minutes)
        except (ValueError, TypeError):
            raise serializers.ValidationError("Duration has wrong format. Use 'DD HH MM' format (e.g., '0 9 0' for 9 hours).")

    def create(self, validated_data):
        # Create Stripe product and price
        product = stripe.Product.create(
            name=validated_data['name'],
            description=validated_data.get('description', '')
        )
        price = stripe.Price.create(
            product=product.id,
            unit_amount=int(validated_data['price'] * 100),  # Convert to cents
            currency=validated_data.get('currency', 'hkd'),  # Use selected currency
        )
        validated_data['stripe_price_id'] = price.id
        validated_data['is_paused'] = False  # Default to active
        return super().create(validated_data)

# -----------------------------
# Popular Plans Serializer
# -----------------------------
class PopularPlanSerializer(serializers.Serializer):
    name = serializers.CharField()
    percentage = serializers.CharField()  # e.g., "98%"
    description = serializers.CharField()
    icon = serializers.CharField()  # e.g., "lifetime" or "10days"
    subscriber_count = serializers.IntegerField()  # Optional: Raw count

class PopularPlansSerializer(serializers.Serializer):
    most_popular = PopularPlanSerializer(many=True)  # Top 2 plans        

# -----------------------------
# User Earnings Serializer
# -----------------------------
class UserEarningsSerializer(serializers.Serializer):
    user = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email")
    subscription = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()
    purchase_date = serializers.SerializerMethodField()
    card = serializers.CharField(source="card_type", default="Unknown")
    status = serializers.SerializerMethodField()

    def get_user(self, obj):
        return {
            "avatar": obj.user.profile_picture_url,
            "name": obj.user.username
        }

    def get_subscription(self, obj):
        if obj.subscription:
            days = obj.subscription.plan_duration.days if obj.subscription.plan_duration else 0
            hours = (obj.subscription.plan_duration.seconds // 3600) if obj.subscription.plan_duration else 0
            duration = f"{days} Day" if days > 0 else f"{hours} Hour" if hours > 0 else "Lifetime"
            return f"{obj.subscription.plan_name} ({duration})"
        return "N/A"

    def get_total_spent(self, obj):
        return f"${obj.amount:.2f} HK" if obj.amount else "$0.00 HK"

    def get_purchase_date(self, obj):
        return obj.payment_date.date() if obj.payment_date else None

    def get_status(self, obj):
        return {"text": "Active", "badge": "green"} if obj.user.is_active else {"text": "Inactive", "badge": "gray"}