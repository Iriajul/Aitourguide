# apps/users/models.py
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.utils.crypto import get_random_string
from django.apps import apps
import cloudinary.uploader


class CustomUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")  # ensure role is admin

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, username, password, **extra_fields)


class User(AbstractUser):
    # remove unwanted AbstractUser fields
    first_name = None
    last_name = None

    ROLE_CHOICES = (
        ("guest", "Guest"),
        ("registered", "Registered"),
        ("premium", "Premium"),
        ("admin", "Admin"),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="registered")
    email = models.EmailField(unique=True)

    # Profile picture fields
    profile_picture_url = models.URLField(blank=True, null=True)
    profile_picture_public_id = models.CharField(max_length=255, blank=True, null=True)

    free_scans_used = models.PositiveIntegerField(default=0)

    # OTP fields
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_expiry = models.DateTimeField(blank=True, null=True)

    # -----------------------------
    # Dashboard / Engagement metrics
    # -----------------------------
    last_login_time = models.DateTimeField(blank=True, null=True)
    last_activity_time = models.DateTimeField(blank=True, null=True)  # Update on API calls
    total_searches = models.PositiveIntegerField(default=0)  # Track searches
    total_scans = models.PositiveIntegerField(default=0)     # Total scans
    total_premium_days = models.FloatField(default=0)  # Track subscription days as fractional
    is_active_premium = models.BooleanField(default=False)  # Quick flag for premium users

    # Ban field
    ban_expiry = models.DateTimeField(blank=True, null=True)

    # Use email for authentication
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    objects = CustomUserManager()  # custom manager

    def __str__(self):
        return f"{self.username} ({self.role})"

    # -----------------------------
    # OTP Methods
    # -----------------------------
    def set_otp(self, length=4, expiry_minutes=5):
        self.otp_code = get_random_string(length=length, allowed_chars="0123456789")
        self.otp_expiry = timezone.now() + timedelta(minutes=expiry_minutes)
        self.save(update_fields=["otp_code", "otp_expiry"])
        return self.otp_code

    def verify_otp(self, otp):
        if self.otp_code != otp:
            return False
        if self.otp_expiry < timezone.now():
            return False
        return True

    def clear_otp(self):
        self.otp_code = None
        self.otp_expiry = None
        self.save(update_fields=["otp_code", "otp_expiry"])

    # -----------------------------
    # Profile Picture Methods
    # -----------------------------
    @property
    def get_profile_picture(self):
        """Return the latest profile picture URL"""
        return self.profile_picture_url

    def update_profile_picture(self, new_file):
        """
        Upload new profile picture to Cloudinary.
        Delete old picture if exists.
        """
        if self.profile_picture_public_id:
            try:
                cloudinary.uploader.destroy(self.profile_picture_public_id)
            except Exception as e:
                print(f"⚠️ Failed to delete old image: {e}")

        result = cloudinary.uploader.upload(
            new_file,
            folder=f"user_profiles/{self.pk}",
            public_id=f"{int(timezone.now().timestamp())}",
            overwrite=True,
            resource_type="image",
        )

        self.profile_picture_url = result.get("secure_url")
        self.profile_picture_public_id = result.get("public_id")
        self.save(update_fields=["profile_picture_url", "profile_picture_public_id"])
        return self.profile_picture_url

    # -----------------------------
    # Dashboard helpers
    # -----------------------------
    def increment_searches(self, count=1):
        self.total_searches += count
        self.save(update_fields=["total_searches"])

    def increment_scans(self, count=1):
        self.total_scans += count
        self.save(update_fields=["total_scans"])

    def update_last_activity(self):
        self.last_activity_time = timezone.now()
        self.save(update_fields=["last_activity_time"])

    # -----------------------------
    # Premium / Subscription helpers
    # -----------------------------
    def recalc_premium_status(self):
        """
        Recalculate user's premium status dynamically based on Subscription.
        Updates:
        - is_active_premium
        - total_premium_days (fractional)
        """
        Subscription = apps.get_model('payments', 'Subscription')  # late import to avoid circular import

        try:
            sub = Subscription.objects.get(user=self)
        except Subscription.DoesNotExist:
            sub = None

        if sub and sub.plan_type == "boost" and sub.end_time and timezone.now() < sub.end_time:
            self.is_active_premium = True
            delta = sub.end_time - sub.start_time
            total_days = delta.total_seconds() / (24 * 3600)  # convert seconds to fractional days
            self.total_premium_days = round(total_days, 4)  # keep precision for small durations
        else:
            self.is_active_premium = False
            self.total_premium_days = 0

        self.save(update_fields=["is_active_premium", "total_premium_days"])

    def set_subscription_duration(self, duration_str):
        """
        Set subscription duration for the user without payment (admin privilege).
        duration_str: '1h', '6h', '12h', '24h', '2d', '5d', '7d', '10d', 'lifetime'
        """
        Subscription = apps.get_model('payments', 'Subscription')
        now = timezone.now()
        try:
            sub, created = Subscription.objects.get_or_create(user=self)
            if duration_str == "lifetime":
                sub.activate_boost_plan("Lifetime Boost", 0.0, None)  # No end time for lifetime
            else:
                hours = {
                    '1h': 1, '6h': 6, '12h': 12, '24h': 24,
                    '2d': 48, '5d': 120, '7d': 168, '10d': 240
                }[duration_str]
                duration = timedelta(hours=hours)
                sub.activate_boost_plan(f"{hours}h Boost", 0.0, duration)  # Price set to 0 for admin
            self.recalc_premium_status()
        except Exception as e:
            raise ValueError(f"Invalid duration or subscription error: {e}")

    def set_ban_duration(self, duration_str):
        """
        Set ban duration for the user.
        duration_str: '1h', '6h', '12h', '24h', '2d', '5d', '7d', '10d'
        """
        hours = {
            '1h': 1, '6h': 6, '12h': 12, '24h': 24,
            '2d': 48, '5d': 120, '7d': 168, '10d': 240
        }
        if duration_str not in hours:
            raise ValueError("Invalid ban duration")
        self.ban_expiry = timezone.now() + timedelta(hours=hours[duration_str])
        self.is_active = False
        self.save(update_fields=["ban_expiry", "is_active"])

    def unban(self):
        """
        Unban the user by clearing ban_expiry and setting is_active to True.
        """
        self.ban_expiry = None
        self.is_active = True
        self.save(update_fields=["ban_expiry", "is_active"])