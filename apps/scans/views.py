# apps/scans/views.py
import time
from io import BytesIO
import json
import re
import cloudinary.uploader
from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
import tempfile

from .models import Scan
from .serializers import ScanSerializer
from .utils import process_landmark, get_location_from_coords
from apps.payments.models import Subscription

# Constants
FREE_SCAN_LIMIT = 3
FREE_SCAN_DELAY = 25  # seconds


def parse_ai_text(ai_text: str):
    """
    Parse raw AI text into structured JSON with multi-language support.
    Supports English, Chinese (Simplified), and Traditional Chinese.
    Returns dict with key "Historical Place" or "General Place".
    If nothing recognizable, return None.
    """
    if not ai_text or not isinstance(ai_text, str):
        return None, None

    lines = ai_text.strip().split("\n")
    if len(lines) < 2:
        return None, None

    # Detect category from first line - support multiple languages
    first_line = lines[0].strip().lower()
    if "historical" in first_line or "历史" in first_line or "歷史" in first_line:
        key = "Historical Place"
    elif "general" in first_line or "一般" in first_line:
        key = "General Place"
    else:
        key = "General Place"

    # Multi-language field name mappings
    FIELD_MAPPINGS = {
        "location": ["Location", "位置"],
        "year_completed": ["Year Completed", "建成年份"],
        "materials": ["Materials", "材料"],
        "architectural_style": ["Architectural Style", "建筑风格", "建築風格"],
        "historical_overview": ["Historical Overview", "历史概述", "歷史概述"],
        "cultural_impact": ["Cultural Impact", "文化影响", "文化影響"],
    }

    def extract_field(field_variants):
        """
        Extract field value supporting multiple language variants.
        Supports both colon (:) and Chinese colon (：) as separators.
        """
        for variant in field_variants:
            # Try both : and ：
            patterns = [
                rf"{re.escape(variant)}\s*[:：]\s*(.*)",
                rf"{re.escape(variant)}\s*[-–—]\s*(.*)",
            ]
            for pattern in patterns:
                for line in lines:
                    m = re.match(pattern, line, re.I)
                    if m:
                        value = m.group(1).strip()
                        # Filter out empty placeholders
                        if value and value not in ["-", "–", "—", "N/A", "n/a", "None", "null"]:
                            return value
        return ""

    def clean_text(text):
        """Remove any leading/trailing * and whitespace"""
        if not text:
            return ""
        cleaned = text.strip().strip("*").strip()
        # Return empty string if only contains dashes or "N/A"
        if cleaned in ["-", "–", "—", "N/A", "n/a", "None", "null"]:
            return ""
        return cleaned

    # Extract numbered list for famous_for - support both English and Chinese numbering
    famous_for = []
    for line in lines:
        # Match various list formats:
        # - English: 1. 2. 3.
        # - Bullets: • - *
        # - Chinese numbers with period
        if (re.match(r"^\d+[\.\)]\s", line.strip()) or 
            line.strip().startswith(("• ", "- ", "* ", "· "))):
            # Remove the prefix
            item = re.sub(r"^[\d\u2022\u25cf\u25e6\u00b7][\.\)]\s*", "", line.strip())
            item = item.lstrip("•-*· ").strip().strip("*")
            if item:
                famous_for.append(item)

    # Build landmark dict using multi-language field extraction
    landmark = {
        "name": clean_text(lines[1]) if len(lines) > 1 else "",
        "location": clean_text(extract_field(FIELD_MAPPINGS["location"])),
        "year_completed": clean_text(extract_field(FIELD_MAPPINGS["year_completed"])),
        "materials": clean_text(extract_field(FIELD_MAPPINGS["materials"])),
        "architectural_style": clean_text(extract_field(FIELD_MAPPINGS["architectural_style"])),
        "historical_overview": clean_text(extract_field(FIELD_MAPPINGS["historical_overview"])),
        "cultural_impact": clean_text(extract_field(FIELD_MAPPINGS["cultural_impact"])),
        "famous_for": famous_for or []
    }

    # Validate that we have SOME meaningful content
    has_content = any([
        landmark["name"],
        landmark["location"],
        landmark["historical_overview"],
        landmark["cultural_impact"],
        len(landmark["famous_for"]) > 0
    ])

    if not has_content:
        return None, None

    return {key: [landmark]}, key


class ScanCreateView(generics.GenericAPIView):
    """
    Handle image capture & AI analysis.
    Free plan: 3 scans + 25s delay
    Boost plan: unlimited while active
    """
    serializer_class = ScanSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        user = request.user

        # Guest check
        if not user.is_authenticated:
            return Response(
                {"error": {"message": "Authentication required. Please log in."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Uploaded image & optional coordinates
        image = request.FILES.get("image")
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")
        language = request.data.get("language", "English")
        source = request.data.get("source", "camera")
        if not image:
            return Response({"error": {"message": "No image uploaded"}}, status=status.HTTP_400_BAD_REQUEST)

        try:
            latitude = float(latitude) if latitude else None
            longitude = float(longitude) if longitude else None
            if source not in ["camera", "gallery"]:
                return Response({"error": {"message": "Invalid source. Use 'camera' or 'gallery'"}},
                                status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"error": {"message": "Invalid latitude or longitude"}}, status=status.HTTP_400_BAD_REQUEST)

        # Subscription check
        subscription = getattr(user, "subscription", None)
        effective_plan = subscription.current_plan() if subscription else "free"

        # Free scans logic
        if effective_plan == "free":
            if user.free_scans_used >= FREE_SCAN_LIMIT:
                return Response(
                    {"error": {"message": "Free scans limit reached. Please purchase Boost."}},
                    status=status.HTTP_403_FORBIDDEN,
                )
            time.sleep(FREE_SCAN_DELAY)
            user.free_scans_used += 1
            user.save(update_fields=["free_scans_used"])

        scan_start_time = timezone.now()

        # Convert uploaded image to BytesIO
        image_bytes = BytesIO()
        for chunk in image.chunks():
            image_bytes.write(chunk)
        image_bytes.seek(0)

        # Save BytesIO to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(image_bytes.getvalue())
            tmp_path = tmp.name

        # Run AI process
        ai_text = process_landmark(tmp_path, latitude=latitude, longitude=longitude, language=language)
        if not ai_text:
            # Retry with English fallback
            ai_text = process_landmark(tmp_path, latitude=latitude, longitude=longitude, language="English")

        structured_analysis, analysis_type = parse_ai_text(ai_text)

        if not structured_analysis:
            return Response({
                "error": {
                    "message": "The image couldn’t be clearly recognized. Please take another photo with better clarity or from a different angle."
                }
            }, status=status.HTTP_200_OK)

        # Upload to Cloudinary
        image_bytes.seek(0)
        upload_result = cloudinary.uploader.upload(
            image_bytes,
            folder=f"user_{user.id}/scans",
            resource_type="image"
        )
        image_url = upload_result.get("secure_url")

        # Human-readable location
        location_name = None
        if latitude is not None and longitude is not None:
            location_name = get_location_from_coords(latitude, longitude)

        scan_end_time = timezone.now()
        duration_seconds = (scan_end_time - scan_start_time).total_seconds()
        duration_minutes = round(duration_seconds / 60, 2)

        engagement_score = len(structured_analysis.get(analysis_type, [{}])[0].get("famous_for", [])) * 2.5

        scan = Scan.objects.create(
            user=user,
            image_url=image_url,
            result_text=json.dumps(structured_analysis, ensure_ascii=False, indent=2),
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            is_boosted=(effective_plan != "free"),
            scan_duration_minutes=duration_minutes,
            processed=True,
            engagement_score=engagement_score,
            source=source
        )

        user.increment_scans()
        user.update_last_activity()

        serializer = ScanSerializer(scan)
        return Response({"scan": serializer.data, "analysis": structured_analysis}, status=status.HTTP_201_CREATED)



class ScanHistoryView(generics.ListAPIView):
    """
    List scans for logged-in user.
    Supports search by location_name & filter by date.
    """
    serializer_class = ScanSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Scan.objects.filter(user=user)

        # Search by location_name
        search_query = self.request.query_params.get("search")
        if search_query:
            queryset = queryset.filter(location_name__icontains=search_query)

        # Filter by created_at
        filter_param = self.request.query_params.get("filter")
        if filter_param:
            filter_param = filter_param.lower()
            filter_map = {
                "last week": "week",
                "last month": "month",
                "last year": "year"
            }
            filter_param = filter_map.get(filter_param, filter_param)

            now = timezone.now()
            if filter_param == "week":
                start_date = now - timedelta(weeks=1)
            elif filter_param == "month":
                start_date = now - timedelta(days=30)
            elif filter_param == "year":
                start_date = now - timedelta(days=365)
            else:
                start_date = None

            if start_date:
                queryset = queryset.filter(created_at__gte=start_date)

        return queryset.order_by("-created_at")

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        results = []
        for scan, scan_data in zip(queryset, serializer.data):
            try:
                analysis = json.loads(scan.result_text) if scan.result_text else {}
            except json.JSONDecodeError:
                analysis = {}
            results.append({"scan": scan_data, "analysis": analysis})

        total_results = len(results)
        search_query = request.query_params.get("search")
        message = f"{total_results} result{'s' if total_results != 1 else ''} for '{search_query}'" if search_query else None

        return Response({"message": message, "results": results})


class ScanDetailView(generics.RetrieveAPIView):
    """
    Return full scan detail by scan_id (with parsed analysis).
    """
    serializer_class = ScanSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return Scan.objects.filter(user=self.request.user)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        try:
            analysis = json.loads(instance.result_text) if instance.result_text else {}
        except json.JSONDecodeError:
            analysis = {}
        return Response({"scan": serializer.data, "analysis": analysis})


class ScanDeleteView(generics.DestroyAPIView):
    """
    Delete a specific scan by id (user can only delete their own scans)
    """
    serializer_class = ScanSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return Scan.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        scan_id = instance.id
        self.perform_destroy(instance)
        return Response(
            {"message": f"Scan with id {scan_id} deleted successfully."},
            status=status.HTTP_200_OK
        )