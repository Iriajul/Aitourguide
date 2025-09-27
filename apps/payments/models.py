from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.dispatch import receiver
from django.db.models.signals import post_save

User = get_user_model()

class SubscriptionPlan(models.Model):
    """
    Represents a global subscription plan template (e.g., "1 Hour Boost").
    Managed in the admin dashboard's "All subscription plans" section.
    """
    name = models.CharField(max_length=50, unique=True)  # Unique plan names
    duration = models.DurationField(null=True, blank=True)  # Null for lifetime
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_paused = models.BooleanField(default=False)  # True when paused, False when active
    stripe_price_id = models.CharField(max_length=255, blank=True, null=True)  # Store Stripe price ID
    currency = models.CharField(max_length=3, default="HKD")  # e.g., "HKD"
    description = models.TextField(blank=True, null=True)  # Optional for popularity

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.is_paused:
            self.is_active = False  # "Inactive" status
        else:
            self.is_active = True  # "Active" status
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        Subscription.objects.filter(plan=self, end_time__lt=timezone.now()).update(plan=None)
        if self.stripe_price_id:
            from django.conf import settings
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY
            try:
                stripe.Price.modify(self.stripe_price_id, active=False)
            except stripe.error.StripeError:
                pass
        super().delete(*args, **kwargs)

    @property
    def status(self):
        return 'Inactive' if self.is_paused else 'Active'

class Subscription(models.Model):
    PLAN_CHOICES = [
        ("free", "Free Plan"),
        ("boost", "Boosted"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscription")
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES, default="free")
    plan_name = models.CharField(max_length=50, blank=True, null=True)
    plan_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    plan_duration = models.DurationField(blank=True, null=True)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_paused = models.BooleanField(default=False)  # User-specific pause/play
    is_active = models.BooleanField(default=True)  # User-specific status
    is_renewed = models.BooleanField(default=False)  # For renewal stats
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)  # Link to plan template

    last_payment_date = models.DateTimeField(blank=True, null=True)
    total_boosted_hours = models.FloatField(default=0.0)

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"

    def __str__(self):
        return f"{self.user.username} - {self.plan_type} ({self.plan_name})"

    def is_active_subscription(self) -> bool:
        if self.plan_type == "boost" and self.end_time:
            if timezone.now() >= self.end_time:
                return False
            return not (self.is_paused or (self.plan and self.plan.is_paused))
        return self.plan_type == "free"

    def current_plan(self) -> str:
        if self.plan_type == "boost" and self.end_time and timezone.now() >= self.end_time:
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
        elif self.plan_type == "boost" and self.is_paused and not self.is_active_subscription():
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
        elif self.plan_type == "boost" and self.plan and self.plan.is_paused and not self.is_active_subscription():
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
        if self.plan_type == "boost" and self.end_time:
            remaining = self.end_time - timezone.now()
            if remaining.total_seconds() <= 0 or self.is_paused or (self.plan and self.plan.is_paused):
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

    def activate_boost_plan(self, plan_name: str, price: float, duration: timedelta):
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
        self.plan = SubscriptionPlan.objects.filter(name=plan_name).first()
        self.is_paused = False  # Reset pause on activation
        self.save(update_fields=[
            "plan_type", "plan_name", "plan_price", "plan_duration", "start_time", "end_time",
            "is_active", "is_renewed", "last_payment_date", "plan", "is_paused"
        ])
        self.user.recalc_premium_status()
        if price > 0:
            Payment.objects.create(user=self.user, amount=price, payment_date=now, subscription=self)

    def renew(self, duration: timedelta):
        now = timezone.now()
        self.start_time = now
        self.end_time = now + duration
        self.is_active = True
        self.is_renewed = True
        self.last_payment_date = now
        self.is_paused = False  # Reset pause on renewal
        if self.plan and self.plan.is_paused:
            raise ValueError("Cannot renew a paused plan.")
        self.save(update_fields=[
            "start_time", "end_time", "is_active", "is_renewed", "last_payment_date", "is_paused"
        ])
        self.user.recalc_premium_status()

    def pause(self):
        self.is_paused = True
        self.is_active = False
        self.save(update_fields=["is_paused", "is_active"])
        self.user.recalc_premium_status()

    def play(self):
        self.is_paused = False
        self.is_active = True
        self.save(update_fields=["is_paused", "is_active"])
        self.user.recalc_premium_status()

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=["is_active"])
        self.user.recalc_premium_status()

    def add_boost_usage(self, hours: float):
        self.total_boosted_hours += hours
        self.save(update_fields=["total_boosted_hours"])

class Payment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(default=timezone.now)
    stripe_payment_id = models.CharField(max_length=255, blank=True, null=True)
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    card_type = models.CharField(max_length=50, blank=True, null=True)  # e.g., "Visa", "Mastercard"

    def __str__(self):
        return f"{self.user.username} - ${self.amount} on {self.payment_date}"

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

@receiver(post_save, sender=Subscription)
def update_user_premium_status(sender, instance, **kwargs):
    user = instance.user
    print(f"Signal triggered for user: {user.username} - Subscription: {instance.plan_name}")
    # Check all subscriptions for the user and update expired ones
    subscriptions = Subscription.objects.filter(user=user, plan_type="boost", end_time__lt=timezone.now())
    for sub in subscriptions:
        if sub.is_active:
            sub.is_active = False
            sub.plan_type = "free"
            sub.plan_name = None
            sub.plan_price = None
            sub.plan_duration = None
            sub.end_time = None
            sub.save(update_fields=[
                "is_active", "plan_type", "plan_name", "plan_price", "plan_duration", "end_time"
            ])
    # Check the latest active subscription beyond current time
    active_subscription = Subscription.objects.filter(
        user=user,
        end_time__gt=timezone.now(),
        is_active=True,
        is_paused=False
    ).exclude(plan__is_paused=True).order_by('-end_time').first()
    # Set is_active_premium based on active subscription
    user.is_active_premium = bool(active_subscription)
    if active_subscription:
        delta = active_subscription.end_time - active_subscription.start_time
        total_days = delta.total_seconds() / (24 * 3600)
        user.total_premium_days = round(total_days, 4)
    else:
        user.total_premium_days = 0
    user.save(update_fields=["is_active_premium", "total_premium_days"])