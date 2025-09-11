from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class Subscription(models.Model):
    PLAN_CHOICES = [
        ("free", "Free Plan"),
        ("boost", "Boosted"),
    ]

    # Basic subscription info
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscription")
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, default="free")
    plan_name = models.CharField(max_length=50, blank=True, null=True)
    plan_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    plan_duration = models.DurationField(blank=True, null=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    # Dashboard metrics
    last_payment_date = models.DateTimeField(blank=True, null=True)
    total_boosted_hours = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)      # Add this for churn/active stats
    is_renewed = models.BooleanField(default=False)    # Add this for renewal stats

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"

    def __str__(self):
        return f"{self.user.username} - {self.plan_type} ({self.plan_name})"

    # Subscription logic
    def is_active_subscription(self) -> bool:
        """
        Return True if subscription is active.
        - Free plan is always active
        - Boost plan is active only if end_time is in the future
        """
        if self.plan_type == "boost" and self.end_time:
            return timezone.now() < self.end_time
        return self.plan_type == "free"

    def current_plan(self) -> str:
        """
        Return effective plan type.
        - Auto-downgrade boost to free if expired
        """
        if self.plan_type == "boost" and self.end_time and timezone.now() >= self.end_time:
            # auto reset
            self.plan_type = "free"
            self.plan_name = None
            self.plan_price = None
            self.plan_duration = None
            self.end_time = None
            self.is_active = False
            self.save(update_fields=[
                "plan_type", "plan_name", "plan_price", "plan_duration", "end_time", "is_active"
            ])
            return "free"
        return self.plan_type

    def time_remaining(self) -> dict:
        """
        Return remaining time for boost plan.
        If expired, reset to free and return zeros.
        """
        if self.plan_type == "boost" and self.end_time:
            remaining = self.end_time - timezone.now()
            if remaining.total_seconds() <= 0:
                # expired → reset
                self.plan_type = "free"
                self.plan_name = None
                self.plan_price = None
                self.plan_duration = None
                self.end_time = None
                self.is_active = False
                self.save(update_fields=[
                    "plan_type", "plan_name", "plan_price", "plan_duration", "end_time", "is_active"
                ])
                return {"days": 0, "hours": 0, "minutes": 0}

            return {
                "days": remaining.days,
                "hours": remaining.seconds // 3600,
                "minutes": (remaining.seconds % 3600) // 60,
            }
        return {"days": 0, "hours": 0, "minutes": 0}

    # Helper to create/update boost plan
    def activate_boost_plan(self, plan_name: str, price: float, duration: timedelta):
        """
        Activate a Boost plan for this user and update User's premium fields.
        """
        now = timezone.now()
        self.plan_type = "boost"
        self.plan_name = plan_name
        self.plan_price = price
        self.plan_duration = duration
        self.start_time = now
        self.end_time = now + duration
        self.is_active = True
        self.is_renewed = False
        self.last_payment_date = now
        self.save(update_fields=[
            "plan_type", "plan_name", "plan_price", "plan_duration", "start_time", "end_time", "is_active", "is_renewed", "last_payment_date"
        ])
        # Update user premium status dynamically
        self.user.recalc_premium_status()

    def renew(self, duration: timedelta):
        """
        Renew the boost plan for this user.
        """
        now = timezone.now()
        self.start_time = now
        self.end_time = now + duration
        self.is_active = True
        self.is_renewed = True
        self.last_payment_date = now
        self.save(update_fields=[
            "start_time", "end_time", "is_active", "is_renewed", "last_payment_date"
        ])
        self.user.recalc_premium_status()

    def deactivate(self):
        """
        Deactivate the subscription (for churn).
        """
        self.is_active = False
        self.save(update_fields=["is_active"])
        self.user.recalc_premium_status()

    # Boost usage helper
    def add_boost_usage(self, hours: float):
        """
        Add hours to total boosted usage.
        """
        self.total_boosted_hours += hours
        self.save(update_fields=["total_boosted_hours"])