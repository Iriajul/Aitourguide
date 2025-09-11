# apps/scans/views.py
import time
from io import BytesIO
import json
import cloudinary.uploader
from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta

from .models import Scan
from .serializers import ScanSerializer
from .utils import process_landmark, get_location_from_coords
from apps.payments.models import Subscription

# Constants
FREE_SCAN_LIMIT = 3
FREE_SCAN_DELAY = 25  # seconds


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
                {"detail": "Authentication required. Please log in.", "signup_required": True},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Uploaded image & optional coordinates
        image = request.FILES.get("image")
        latitude = request.data.get("latitude")
        longitude = request.data.get("longitude")
        language = request.data.get("language", "English")  # Default to English if no language provided
        source = request.data.get("source", "camera")  # Default to "camera" if not provided
        if not image:
            return Response({"detail": "No image uploaded"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            latitude = float(latitude) if latitude else None
            longitude = float(longitude) if longitude else None
            if source not in ["camera", "gallery"]:
                return Response({"detail": "Invalid source. Use 'camera' or 'gallery'"}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError:
            return Response({"detail": "Invalid latitude or longitude"}, status=status.HTTP_400_BAD_REQUEST)

        # Subscription check
        subscription = getattr(user, "subscription", None)
        effective_plan = subscription.current_plan() if subscription else "free"

        # Free scans logic
        if effective_plan == "free":
            if user.free_scans_used >= FREE_SCAN_LIMIT:
                return Response(
                    {"detail": "Free scans limit reached. Please purchase Boost."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            time.sleep(FREE_SCAN_DELAY)
            user.free_scans_used += 1
            user.save(update_fields=["free_scans_used"])

        # Track start time
        scan_start_time = timezone.now()

        # Convert uploaded image to BytesIO
        image_bytes = BytesIO()
        for chunk in image.chunks():
            image_bytes.write(chunk)
        image_bytes.seek(0)

        # Run AI process with selected language
        analysis = process_landmark(image_bytes, latitude=latitude, longitude=longitude, language=language)
        if not analysis:
            return Response({"detail": "AI processing failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

        # Track end time + precise duration in minutes
        scan_end_time = timezone.now()
        duration_seconds = (scan_end_time - scan_start_time).total_seconds()
        duration_minutes = round(duration_seconds / 60, 2)  # stores fractions of a minute

        # Save scan with dynamic values
        scan = Scan.objects.create(
            user=user,
            image_url=image_url,
            result_text=json.dumps(analysis, ensure_ascii=False, indent=2),
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            is_boosted=(effective_plan != "free"),
            scan_duration_minutes=duration_minutes,
            processed=True,
            engagement_score=len(analysis.get("famous_for", [])) * 2.5,
            source=source  # Save the source (camera or gallery)
        )

        # Update user stats dynamically
        user.increment_scans()
        user.update_last_activity()

        serializer = ScanSerializer(scan)
        return Response({"scan": serializer.data, "analysis": analysis}, status=status.HTTP_201_CREATED)


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