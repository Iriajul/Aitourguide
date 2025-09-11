# apps/scans/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class Scan(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="scans"
    )
    # Store Cloudinary URL instead of local ImageField
    image_url = models.URLField(max_length=500, blank=True, null=True)
    result_text = models.TextField(blank=True)  # raw AI response

    # Latitude & Longitude
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="User's latitude when the scan was taken"
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True,
        help_text="User's longitude when the scan was taken"
    )

    # Human-readable location (auto-generated from latitude & longitude)
    location_name = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="Location name derived from latitude & longitude"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # Source of the scan (camera or gallery)
    SOURCE_CHOICES = (
        ("camera", "Camera"),
        ("gallery", "Gallery"),
    )
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default="camera",
        help_text="Source of the scan (camera or gallery)"
    )

    # -----------------------------
    # Dashboard / Analytics helpers
    # -----------------------------
    is_boosted = models.BooleanField(default=False)  # Flag if scan used premium boost
    scan_duration_minutes = models.DecimalField(
        max_digits=6,       # e.g., 9999.99 minutes max (adjust if needed)
        decimal_places=2,   # two decimal places for fractions of a minute
        default=Decimal('0.00'),
        help_text="Duration of scan in minutes, with decimals for seconds."
    )
    processed = models.BooleanField(default=False)  # Whether scan AI processing completed
    engagement_score = models.FloatField(default=0.0)  # Optional score for engagement metrics

    def __str__(self):
        return f"Scan {self.id} by {self.user.email}"

    class Meta:
        ordering = ["-created_at"]

    # -----------------------------
    # Dashboard helpers
    # -----------------------------
    def mark_processed(self, engagement_score: float = 0.0, boosted: bool = False):
        """
        Mark scan as processed and optionally set engagement score and boost flag
        """
        self.processed = True
        self.engagement_score = engagement_score
        self.is_boosted = boosted
        self.save(update_fields=["processed", "engagement_score", "is_boosted"])

    def set_boost_duration(self, minutes: int):
        self.scan_duration_minutes = minutes
        self.save(update_fields=["scan_duration_minutes"])