# import os
# import json
# import base64
# from io import BytesIO
# from dotenv import load_dotenv
# from langchain_openai import ChatOpenAI
# from langchain_core.messages import HumanMessage
# from geopy.geocoders import Nominatim
# from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# # Load environment variables
# load_dotenv()

# OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
# if not OPENAI_API_KEY:
#     raise ValueError("OPENAI_API_KEY not found in environment variables.")

# # Function to encode the image to a base64 string
# def get_base64_encoded_image(image_input):
#     if isinstance(image_input, str):
#         with open(image_input, "rb") as image_file:
#             return base64.b64encode(image_file.read()).decode('utf-8')
#     elif isinstance(image_input, BytesIO):
#         image_input.seek(0)
#         return base64.b64encode(image_input.read()).decode('utf-8')
#     else:
#         raise ValueError("Unsupported image input type. Must be path or BytesIO.")

# # -----------------------------
# # Geo helper
# # -----------------------------
# def get_location_from_coords(latitude, longitude):
#     """Get location address from coordinates. Returns None if coordinates are not provided."""
#     if latitude is None or longitude is None:
#         return None
        
#     try:
#         geolocator = Nominatim(user_agent="location_finder_app")
#         location = geolocator.reverse((latitude, longitude), exactly_one=True)
#         if location:
#             return location.address
#         return "Location not found"
#     except (GeocoderTimedOut, GeocoderServiceError) as e:
#         return f"Geocoding error: {str(e)}"
#     except Exception as e:
#         return f"Error: {str(e)}"

# # -----------------------------
# # Language-specific templates for headings
# # -----------------------------
# HEADINGS_TRANSLATION = {
#     "English": {
#         "location": "Location",
#         "year_completed": "Year Completed",
#         "materials": "Materials",
#         "architectural_style": "Architectural Style",
#         "historical_overview": "Historical Overview",
#         "cultural_impact": "Cultural Impact",
#         "famous_for": "Famous For",
#         "key_features": "Key Features",
#         "primary_function": "Primary Function",
#         "overview_and_significance": "Overview & Significance",
#         "visitor_experience": "Visitor Experience",
#         "known_for": "Known For"
#     },
#     "Chinese": {
#         "location": "位置",
#         "year_completed": "建成年份",
#         "materials": "材料",
#         "architectural_style": "建筑风格",
#         "historical_overview": "历史概述",
#         "cultural_impact": "文化影响",
#         "famous_for": "著名原因",
#         "key_features": "主要特色",
#         "primary_function": "主要功能",
#         "overview_and_significance": "概述与意义",
#         "visitor_experience": "游客体验",
#         "known_for": "著名原因"
#     },
#     "Traditional Chinese": {
#         "location": "位置",
#         "year_completed": "建成年份",
#         "materials": "材料",
#         "architectural_style": "建築風格",
#         "historical_overview": "歷史概述",
#         "cultural_impact": "文化影響",
#         "famous_for": "著名原因",
#         "key_features": "主要特色",
#         "primary_function": "主要功能",
#         "overview_and_significance": "概述與意義",
#         "visitor_experience": "遊客體驗",
#         "known_for": "著名原因"
#     }
# }

# # -----------------------------
# # Language prompt function
# # -----------------------------
# def get_language_prompt(language):
#     """Returns the appropriate prompt based on language."""
#     language_prompts = {
#         "English": "Please respond in English.",
#         "Chinese": "请用中文回答。",
#         "Traditional Chinese": "請用繁體中文回答。"
#     }
#     return language_prompts.get(language, "Please respond in English.")

# # -----------------------------
# # Landmark analyzer
# # -----------------------------
# def process_landmark(image_input, latitude=None, longitude=None, language="English", temperature=0.3):
#     """
#     Process the landmark image using OpenAI API and return parsed JSON dict.
#     """
#     try:
#         # Get the location address using latitude and longitude (if provided)
#         address = get_location_from_coords(latitude, longitude)
        
#         # Handle the case when no coordinates are provided
#         if address is None:
#             location_context = "an unknown location"
#             print("No coordinates provided. Analyzing image without location context.")
#         elif address in ["Location not found", "Geocoding error"] or "error" in address.lower():
#             location_context = "an unknown location"
#             print(f"Failed to fetch address: {address}")
#         else:
#             location_context = address

#         # Validate image file existence
#         base64_image = get_base64_encoded_image(image_input)

#         # Validate language
#         headings = HEADINGS_TRANSLATION.get(language)
#         if not headings:
#             print(f"Unsupported language: {language}. Using English as default.")
#             headings = HEADINGS_TRANSLATION["English"]
#             language = "English"

#         # Fetch language-specific prompt
#         language_prompt = get_language_prompt(language)

#         # Construct the dynamic prompt
#         unified_prompt = f"""
# {language_prompt}

# Given image is from {location_context}, analyze this landmark or place of interest. You are an expert travel guide and architectural analyst. Your task is to analyze the provided image and generate a detailed, engaging, and factually accurate report about the prominent place or structure shown.

# CRITICAL PROCESSING INSTRUCTIONS:
# First, analyze the image to determine if the subject is a Historical Landmark (e.g., ancient temple, medieval castle, monument with deep historical significance) or a General Place of Interest (e.g., modern skyscraper, iconic bridge, famous commercial building, natural wonder, public square).

# Based on your analysis, provide information about:

# **Return the output strictly as a JSON object with the following keys:**
# - "landmark_name": [Full name of the landmark/place]
# - "location": [City, Country - if determinable from image]
# - "year_completed": [Year or era if known, otherwise null]
# - "materials": [Primary construction materials if visible, otherwise null]
# - "architectural_style": [Style if applicable, otherwise null]
# - "historical_overview": [Brief historical context if it's a historical landmark]
# - "cultural_impact": [Cultural significance if applicable]
# - "famous_for": [Array of 2-3 main things it's known for]
# - "key_features": [Notable design elements or features visible]
# - "primary_function": [Main purpose/function]
# - "overview_and_significance": [General description and importance]
# - "visitor_experience": [What visitors can expect]
# - "known_for": [What it's primarily recognized for]

# IMPORTANT: 
# - If you cannot determine specific information from the image, use null for that field
# - Focus on what you can visually identify in the image
# - Provide accurate information based on visual analysis
# - Return only valid JSON, no additional text
# """

#         # Initialize the OpenAI model with correct model name
#         llm = ChatOpenAI(
#             model="gpt-4.1",  # Fixed: gpt-4.1 doesn't exist, using gpt-4o
#             temperature=temperature,
#             openai_api_key=OPENAI_API_KEY
#         )

#         # Create the message with text and image data
#         message = HumanMessage(
#             content=[
#                 {"type": "text", "text": unified_prompt},
#                 {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
#             ]
#         )

#         # Invoke the model and return the result
#         response = llm.invoke([message])

#         # Parse the AI response if it's in string format
#         print("Response:", response.content)
        
#         try:
#             # Clean the response content in case there are markdown code blocks
#             content = response.content.strip()
#             if content.startswith('```json'):
#                 content = content[7:]  # Remove ```json
#             if content.endswith('```'):
#                 content = content[:-3]  # Remove ```
#             content = content.strip()
            
#             analysis = json.loads(content)  # Parse the string response to a dictionary
            
#             # Ensure all expected keys are present with default values
#             default_analysis = {
#                 "landmark_name": None,
#                 "location": None,
#                 "year_completed": None,
#                 "materials": None,
#                 "architectural_style": None,
#                 "historical_overview": None,
#                 "cultural_impact": None,
#                 "famous_for": [],
#                 "key_features": None,
#                 "primary_function": None,
#                 "overview_and_significance": None,
#                 "visitor_experience": None,
#                 "known_for": []
#             }
            
#             # Merge with default values
#             for key in default_analysis:
#                 if key not in analysis:
#                     analysis[key] = default_analysis[key]
                    
#         except json.JSONDecodeError as e:
#             print(f"Error parsing AI response: {e}")
#             print(f"Raw response: {response.content}")
#             # Return a basic structure if parsing fails
#             analysis = {
#                 "landmark_name": "Unknown",
#                 "location": location_context if location_context != "an unknown location" else None,
#                 "year_completed": None,
#                 "materials": None,
#                 "architectural_style": None,
#                 "historical_overview": None,
#                 "cultural_impact": None,
#                 "famous_for": [],
#                 "key_features": None,
#                 "primary_function": None,
#                 "overview_and_significance": "Analysis failed due to response parsing error",
#                 "visitor_experience": None,
#                 "known_for": []
#             }

#         # Return the parsed AI response
#         return analysis

#     except Exception as e:
#         print(f"Failed to process landmark: {str(e)}")
#         # Return a structured error response instead of None
#         return {
#             "landmark_name": "Processing Failed",
#             "location": None,
#             "year_completed": None,
#             "materials": None,
#             "architectural_style": None,
#             "historical_overview": None,
#             "cultural_impact": None,
#             "famous_for": [],
#             "key_features": None,
#             "primary_function": None,
#             "overview_and_significance": f"Processing failed: {str(e)}",
#             "visitor_experience": None,
#             "known_for": []
#         }












# ----------------------------------------------------------------------------------------------------
# --------------------------------------- OPTIMIZED OPENAI VERSION WITH TIMING ---------------------------------------
# ----------------------------------------------------------------------------------------------------

import os
import time
from contextlib import contextmanager
from dotenv import load_dotenv
from langchain_community.chat_models import ChatOpenAI
from langchain_core.messages import HumanMessage
import base64
from functools import lru_cache
from PIL import Image
import io
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Load environment variables once
load_dotenv()
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables.")

# ------------------------------------ GEO UTILITIES ------------------------------------
def get_location_from_coords(latitude, longitude):
    """
    Convert latitude and longitude to human-readable address
    """
    try:
        # Initialize the geocoder
        geolocator = Nominatim(user_agent="location_finder_app")
        
        # Reverse geocode the coordinates
        location = geolocator.reverse((latitude, longitude), exactly_one=True)
        
        if location:
            return location.address
        else:
            return "Location not found"
            
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        return f"Geocoding error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"

# ------------------------------------ PERFORMANCE UTILITIES ------------------------------------
# Global model instance (reused across calls)
_llm_instance = None

class Timer:
    """Context manager and utility class for timing operations."""
    def __init__(self, operation_name="Operation", verbose=True):
        self.operation_name = operation_name
        self.verbose = verbose
        self.start_time = None
        self.end_time = None
        self.duration = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        if self.verbose:
            print(f"⏱️  Starting: {self.operation_name}...")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.perf_counter()
        self.duration = self.end_time - self.start_time
        if self.verbose:
            print(f"✅ Completed: {self.operation_name} - {self.duration:.3f}s")

    def get_duration(self):
        return self.duration

class PerformanceTracker:
    """Track and report performance metrics for landmark processing."""
    def __init__(self):
        self.metrics = {}
        self.total_start_time = None

    def start_total_timer(self):
        self.total_start_time = time.perf_counter()

    def add_metric(self, name, duration):
        self.metrics[name] = duration

    def print_summary(self, show_details=True):
        if self.total_start_time:
            total_time = time.perf_counter() - self.total_start_time
            self.metrics['Total Processing Time'] = total_time

        print("\n" + "="*60)
        print("🚀 PERFORMANCE SUMMARY")
        print("="*60)

        if show_details and len(self.metrics) > 1:
            for metric_name, duration in self.metrics.items():
                if metric_name != 'Total Processing Time':
                    percentage = (duration / self.metrics.get('Total Processing Time', 1)) * 100
                    print(f"  {metric_name:<25}: {duration:>8.3f}s ({percentage:>5.1f}%)")
            print("-" * 60)

        total = self.metrics.get('Total Processing Time', 0)
        print(f"  {'TOTAL TIME':<25}: {total:>8.3f}s")

        if show_details and len(self.metrics) > 3:
            self._print_insights()

        print("="*60)

    def _print_insights(self):
        print("\n💡 PERFORMANCE INSIGHTS:")
        api_time = self.metrics.get('API Request', 0)
        image_time = self.metrics.get('Image Processing', 0)
        geo_time = self.metrics.get('Geocoding', 0)
        total_time = self.metrics.get('Total Processing Time', 1)

        if api_time > total_time * 0.6:
            print("  • API request is the main bottleneck (>60% of time)")
            print("    → Consider using a faster model or reducing prompt length")

        if image_time > total_time * 0.2:
            print("  • Image processing is slow (>20% of time)")
            print("    → Try reducing image size or quality further")

        if geo_time > total_time * 0.3:
            print("  • Geocoding is taking significant time (>30%)")
            print("    → Consider caching coordinates or using a faster geocoding service")

        if total_time < 3:
            print("  • ⚡ Excellent performance! (<3s total)")
        elif total_time < 6:
            print("  • ✅ Good performance (3-6s total)")
        elif total_time < 10:
            print("  • ⚠️  Moderate performance (6-10s total)")
        else:
            print("  • 🐌 Slow performance (>10s total) - optimization needed")

# ------------------------------------ LLM UTILITIES ------------------------------------
def get_llm_instance(temperature=0.3):
    global _llm_instance
    if _llm_instance is None or _llm_instance.temperature != temperature:
        _llm_instance = ChatOpenAI(
            model="gpt-4o",
            temperature=temperature,
            openai_api_key=OPENAI_API_KEY,
            max_retries=1,
            request_timeout=30
        )
    return _llm_instance

def get_optimized_base64_image(image_path, max_size=(1024, 1024), quality=85, verbose=False):
    start_time = time.perf_counter()
    try:
        with Image.open(image_path) as img:
            original_size = img.size
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            buffer.seek(0)
            original_bytes = os.path.getsize(image_path)
            compressed_bytes = len(buffer.getvalue())
            compression_ratio = (1 - compressed_bytes/original_bytes) * 100
            duration = time.perf_counter() - start_time
            if verbose:
                print(f"📸 Image optimized: {original_size} → {img.size}, "
                      f"size reduced by {compression_ratio:.1f}% ({duration:.3f}s)")
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        duration = time.perf_counter() - start_time
        if verbose:
            print(f"⚠️  Image optimization failed ({duration:.3f}s), using original: {e}")
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

# ------------------------------------ HEADING & PROMPT CACHE ------------------------------------
@lru_cache(maxsize=3)
def get_headings(language):
    headings_translation = {
        "English": {
            "location": "Location", "year_completed": "Year Completed", "materials": "Materials",
            "architectural_style": "Architectural Style", "historical_overview": "Historical Overview",
            "cultural_impact": "Cultural Impact", "famous_for": "Famous For", "key_features": "Key Features",
            "primary_function": "Primary Function", "overview_and_significance": "Overview & Significance",
            "visitor_experience": "Visitor Experience", "known_for": "Known For"
        },
        "Chinese": {
            "location": "位置", "year_completed": "建成年份", "materials": "材料", "architectural_style": "建筑风格",
            "historical_overview": "历史概述", "cultural_impact": "文化影响", "famous_for": "著名原因",
            "key_features": "主要特色", "primary_function": "主要功能", "overview_and_significance": "概述与意义",
            "visitor_experience": "游客体验", "known_for": "著名原因"
        },
        "Traditional Chinese": {
            "location": "位置", "year_completed": "建成年份", "materials": "材料", "architectural_style": "建築風格",
            "historical_overview": "歷史概述", "cultural_impact": "文化影響", "famous_for": "著名原因",
            "key_features": "主要特色", "primary_function": "主要功能", "overview_and_significance": "概述與意義",
            "visitor_experience": "遊客體驗", "known_for": "著名原因"
        }
    }
    return headings_translation.get(language)

@lru_cache(maxsize=3)
def get_language_prompt(language):
    language_prompts = {
        "English": "Please respond in English.",
        "Chinese": "请用中文回答。",
        "Traditional Chinese": "請用繁體中文回答。"
    }
    return language_prompts.get(language)

# ------------------------------------ PROMPT BUILDING ------------------------------------
def build_prompt(address, language, headings, has_location=True):
    lang_prompt = get_language_prompt(language)
    if has_location and address:
        location_context = f"Analyze this landmark image from {address}."
        location_instruction = "Use the provided location context to enhance your analysis."
    else:
        location_context = "Analyze this landmark image."
        location_instruction = "Identify the landmark and its location based on visual features, architectural style, and any visible text or distinctive elements."
    return f"""{lang_prompt}

{location_context} {location_instruction}

First, carefully examine the image to identify:
- Distinctive architectural features
- Cultural or historical markers
- Any visible text, signs, or inscriptions
- Surrounding environment and context
- Architectural style and period

Then classify the image into one of three categories and respond accordingly:

1. If it is a Historical Landmark → Use the following template:
**Historical Place**
**[Name]**
{headings["location"]}: [City, Country]
{headings["year_completed"]}: [Year/Era]
{headings["architectural_style"]}: [Style]
{headings["historical_overview"]}: [2-3 sentences on history]
{headings["cultural_impact"]}: [2-3 sentences on significance]
{headings["famous_for"]}: [3 key points]

2. If it is a General Place → Use the following template:
**General Place**
**[Name]**
{headings["location"]}: [City, Country]
{headings["primary_function"]}: [Function]
{headings["overview_and_significance"]}: [2-3 sentences]
{headings["visitor_experience"]}: [2-3 sentences]
{headings["known_for"]}: [3 key points]

3. If it does not belong to either Historical Landmark or General Place:
Respond with:
"This is not either historical or general."

Instructions:
- Be confident in your identification based on visual evidence
- If you can identify the landmark, provide comprehensive details
- If the landmark is not immediately recognizable, describe what you can observe and provide general information about the architectural style or type of structure
- If it does not clearly fit either category, return the fallback response
- Be concise but informative
- Only omit details that are genuinely unknown"""

# ------------------------------------ LANDMARK PROCESSING ------------------------------------
def process_landmark_with_timing(image_path, latitude=None, longitude=None, language="English", temperature=0.3, verbose=False):
    tracker = PerformanceTracker()
    tracker.start_total_timer()
    try:
        if verbose:
            print(f"\n🏛️  Processing landmark: {os.path.basename(image_path)}")
            if latitude is not None and longitude is not None:
                print(f"📍 Coordinates: ({latitude}, {longitude})")
            else:
                print(f"📍 No coordinates provided - AI will identify landmark")
            print(f"🌐 Language: {language}")

        # Step 1: Validate inputs
        with Timer("Input Validation", verbose) as validation_timer:
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file '{image_path}' not found.")
            headings = get_headings(language)
            if not headings:
                raise ValueError(f"Unsupported language: {language}")
        tracker.add_metric("Input Validation", validation_timer.get_duration())

        # Step 2: Geocoding
        address = None
        has_location = False
        if latitude is not None and longitude is not None:
            with Timer("Geocoding", verbose) as geo_timer:
                address = get_location_from_coords(latitude, longitude)
                if address not in ["Location not found", "Geocoding error"]:
                    has_location = True
                else:
                    if verbose:
                        print(f"⚠️  Warning: Could not fetch address - {address}")
                    address = f"coordinates {latitude}, {longitude}"
                    has_location = True
            tracker.add_metric("Geocoding", geo_timer.get_duration())
        else:
            if verbose:
                print("⏭️  Skipping geocoding - no coordinates provided")
            tracker.add_metric("Geocoding", 0.0)

        # Step 3: Image processing
        with Timer("Image Processing", verbose) as img_timer:
            base64_image = get_optimized_base64_image(image_path, verbose=verbose)
        tracker.add_metric("Image Processing", img_timer.get_duration())

        # Step 4: Prompt building
        with Timer("Prompt Building", verbose) as prompt_timer:
            prompt = build_prompt(address, language, headings, has_location)
        tracker.add_metric("Prompt Building", prompt_timer.get_duration())

        # Step 5: Model setup
        with Timer("Model Setup", verbose) as model_timer:
            llm = get_llm_instance(temperature)
        tracker.add_metric("Model Setup", model_timer.get_duration())

        # Step 6: API request
        with Timer("API Request", verbose) as api_timer:
            message = HumanMessage(
                content=[
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            )
            response = llm.invoke([message])
        tracker.add_metric("API Request", api_timer.get_duration())

        if verbose:
            tracker.print_summary(show_details=True)

        return response.content, tracker.metrics

    except Exception as e:
        if verbose:
            print(f"❌ Error processing landmark: {str(e)}")
            tracker.print_summary(show_details=False)
        return None, tracker.metrics

# ------------------------------------ SIMPLE FUNCTIONS ------------------------------------
def process_landmark(image_path, latitude=None, longitude=None, language="English", temperature=0.3):
    try:
        result, _ = process_landmark_with_timing(
            image_path, latitude, longitude, language, temperature, verbose=False
        )
        return result
    except Exception as e:
        print(f"Error processing landmark: {str(e)}")
        return None

def process_landmarks_batch(landmark_data_list, language="English", temperature=0.3, verbose=False):
    batch_start_time = time.perf_counter()
    results = []
    all_metrics = {}
    if verbose:
        print(f"\n🚀 Starting batch processing of {len(landmark_data_list)} landmarks...")
    llm = get_llm_instance(temperature)
    for i, landmark_data in enumerate(landmark_data_list, 1):
        if verbose:
            print(f"\n{'='*20} LANDMARK {i}/{len(landmark_data_list)} {'='*20}")
        if len(landmark_data) == 1:
            image_path = landmark_data[0]
            lat, lng = None, None
        elif len(landmark_data) == 3:
            image_path, lat, lng = landmark_data
        else:
            if verbose:
                print(f"⚠️  Invalid landmark data format for item {i}: {landmark_data}")
            results.append(None)
            continue
        result, metrics = process_landmark_with_timing(image_path, lat, lng, language, temperature, verbose)
        results.append(result)
        all_metrics[f"landmark_{i}"] = metrics

    total_batch_time = time.perf_counter() - batch_start_time
    if verbose:
        print(f"\n{'='*60}")
        print(f"📊 BATCH PROCESSING COMPLETE")
        print(f"{'='*60}")
        print(f"  Total landmarks processed: {len(landmark_data_list)}")
        print(f"  Total batch time: {total_batch_time:.3f}s")
        print(f"  Average time per landmark: {total_batch_time/len(landmark_data_list):.3f}s")
        print(f"  Successful processes: {sum(1 for r in results if r is not None)}")
        print(f"{'='*60}")
    return results, all_metrics

def time_operation(func, *args, operation_name=None, **kwargs):
    name = operation_name or func.__name__
    start_time = time.perf_counter()
    try:
        result = func(*args, **kwargs)
        duration = time.perf_counter() - start_time
        print(f"⏱️  {name}: {duration:.3f}s")
        return result, duration
    except Exception as e:
        duration = time.perf_counter() - start_time
        print(f"❌ {name} failed after {duration:.3f}s: {e}")
        return None, duration

def analyze_landmark(image_path, latitude=None, longitude=None, language="English", temperature=0.3):
    try:
        result, _ = process_landmark_with_timing(
            image_path, latitude, longitude, language=language, temperature=temperature, verbose=False
        )
        if result:
            print(result)
        else:
            print("Failed to analyze landmark.")
    except Exception as e:
        print(f"Error: {e}")

# ------------------------------------ USAGE EXAMPLE ------------------------------------
if __name__ == "__main__":
    image_path = "Media.jpg"  # Replace with your image path
    latitude = ""
    longitude = ""
    language = "English"

    if latitude is not None and longitude is not None:
        analyze_landmark(image_path, latitude, longitude, language)
    else:
        analyze_landmark(image_path, None, None, language)
