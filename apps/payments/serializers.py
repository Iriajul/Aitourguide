# apps/payments/serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Subscription

User = get_user_model()


class CheckoutSessionSerializer(serializers.Serializer):
    """
    Serializer for returning Stripe checkout session URL.
    """
    checkout_url = serializers.URLField()


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for exposing subscription details and dashboard metrics.
    """
    class Meta:
        model = Subscription
        fields = [
            "plan_type",
            "plan_name",
            "plan_price",
            "plan_duration",
            "start_time",
            "end_time",
            "last_payment_date",
            "total_boosted_hours",
            "is_active",
            "is_renewed",
        ]


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for returning full user profile including subscription info and profile picture.
    """
    plan_type = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()
    plan_price = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()
    can_upgrade = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    subscription = SubscriptionSerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "profile_picture",
            "plan_type",
            "plan_name",
            "plan_price",
            "time_remaining",
            "can_upgrade",
            "can_cancel",
            "subscription",  # Expose full subscription details
        )

    # -----------------------------
    # Profile Picture
    # -----------------------------
    def get_profile_picture(self, obj):
        # Always return the stored Cloudinary URL
        return obj.profile_picture_url

    # -----------------------------
    # Subscription Info
    # -----------------------------
    def get_plan_type(self, obj):
        try:
            return obj.subscription.current_plan()
        except Subscription.DoesNotExist:
            return "free"

    def get_plan_name(self, obj):
        try:
            sub = obj.subscription
            return sub.plan_name if sub.plan_type == "boost" else "Free Plan"
        except Subscription.DoesNotExist:
            return "Free Plan"

    def get_plan_price(self, obj):
        try:
            sub = obj.subscription
            if sub.plan_type == "boost" and sub.plan_price:
                return f"HK ${int(sub.plan_price)}"
            return "HK $0"
        except Subscription.DoesNotExist:
            return "HK $0"

    def get_time_remaining(self, obj):
        try:
            sub = obj.subscription
            if sub.current_plan() == "boost":
                return sub.time_remaining()
            return {"days": 0, "hours": 0, "minutes": 0}
        except Subscription.DoesNotExist:
            return {"days": 0, "hours": 0, "minutes": 0}

    def get_can_upgrade(self, obj):
        try:
            sub = obj.subscription
            if sub.current_plan() == "free":
                return True
            if sub.plan_type == "boost" and sub.is_active:
                return False
            return True
        except Subscription.DoesNotExist:
            return True

    def get_can_cancel(self, obj):
        try:
            sub = obj.subscription
            return sub.plan_type == "boost" and sub.is_active
        except Subscription.DoesNotExist:
            return False
