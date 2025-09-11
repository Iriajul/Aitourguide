# apps/scans/utils.py
import os
import json
import base64
from io import BytesIO
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

# Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")


# -----------------------------
# Geo helper
# -----------------------------
def get_location_from_coords(latitude, longitude):
    try:
        geolocator = Nominatim(user_agent="location_finder_app")
        location = geolocator.reverse((latitude, longitude), exactly_one=True)
        if location:
            return location.address
        return "Location not found"
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        return f"Geocoding error: {str(e)}"
    except Exception as e:
        return f"Error: {str(e)}"


# -----------------------------
# Encode image
# -----------------------------
def get_base64_encoded_image(image_input):
    if isinstance(image_input, str):
        with open(image_input, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    elif isinstance(image_input, BytesIO):
        image_input.seek(0)
        return base64.b64encode(image_input.read()).decode('utf-8')
    else:
        raise ValueError("Unsupported image input type. Must be path or BytesIO.")


# -----------------------------
# Landmark analyzer
# -----------------------------
def process_landmark(image_input, latitude=None, longitude=None, temperature=0.0):
    """
    Process the landmark image using Gemini API and return parsed JSON dict.
    """
    try:
        if isinstance(image_input, str) and not os.path.exists(image_input):
            raise FileNotFoundError(f"Image file '{image_input}' not found.")

        address = None
        if latitude is not None and longitude is not None:
            address = get_location_from_coords(latitude, longitude)
            if address.startswith("Geocoding error") or address == "Location not found":
                address = None

        base64_image = get_base64_encoded_image(image_input)
        image_data_uri = f"data:image/jpeg;base64,{base64_image}"
        location_text = f"from {address}" if address else "from an unknown location"

        # ----- FULL TEAMMATE PROMPT -----
        unified_prompt = f"""
Given image is {location_text}, a popular tourist destination.

You are an expert travel guide and architectural analyst. Your task is to analyze the provided image and generate a detailed, engaging, and factually accurate report about the prominent place or structure shown.

CRITICAL PROCESSING INSTRUCTIONS:

First, analyze the image to determine if the subject is a Historical Landmark (e.g., ancient temple, medieval castle, monument with deep historical significance) or a General Place of Interest (e.g., modern skyscraper, iconic bridge, famous commercial building, natural wonder, public square).

Based on your classification, output the report using only one of the two exact templates below.

TEMPLATE A: For a Historical Landmark
[Full Official Landmark Name]

Location: [City, Country]

Year Completed: [Year or Era] (Omit if not known or not applicable)

Materials: [Primary construction materials] (Omit if not discernible)

Architectural Style: [Predominant architectural style] (Omit if not classified)

Historical Overview:
[A concise paragraph detailing its origin, key historical events, and significant figures involved (e.g., architects, rulers). Focus on its historical narrative.]

Cultural Impact:
[A single paragraph explaining its symbolic meaning, its influence on national/regional identity, and its role in culture, arts, or collective memory.]

Famous For:

[1. Primary reason for global fame]

[2. Secondary distinct reason]

[3. Tertiary distinct reason]

TEMPLATE B: For a General Place of Interest
[Full Official Name of the Place/Structure]

Location: [City, Country]

Established: [Year] (Omit if not known)

Key Features: [Notable materials, engineering marvels, or design elements] (Omit if not discernible)

Primary Function: [E.g., Observation Tower, Transportation Hub, Commercial Center, Public Park] (Omit if not applicable)

Overview & Significance:
[A concise paragraph describing what it is, its primary purpose, and why it is significant to the city or field (e.g., engineering, urban planning, commerce).]

Visitor Experience:
[A single paragraph highlighting what visitors can see and do there, the atmosphere, and any unique experiential aspects.]

Known For:

[1. Primary claim to fame]

[2. Secondary distinct feature or fact]

[3. Tertiary distinct feature or fact]

GLOBAL OUTPUT RULES (Apply to both templates):

- Zero Repetition: Do not repeat any fact, figure, or description across different sections.
- Conciseness: Use clear, efficient, and engaging language. Avoid fluff and redundancy.
- Deduction: Base your analysis on visual cues from the image and your encyclopedic knowledge. Omit any numbered line (e.g., Year Completed, Materials) if the information cannot be reasonably inferred or is not applicable.
- Structure: Maintain the exact spacing, bolding, and section ordering as shown in the chosen template.
- **Return the output strictly as a JSON object with keys:**
  "landmark_name", "location", "year_completed", "materials", "architectural_style", "historical_overview", "cultural_impact", "famous_for"
- Do not output any text outside of JSON.
"""
        # ----- END OF PROMPT -----

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=temperature,
            google_api_key=GEMINI_API_KEY
        )

        message = HumanMessage(
            content=[
                {"type": "text", "text": unified_prompt},
                {"type": "image_url", "image_url": image_data_uri},
            ]
        )

        response = llm.invoke([message])
        return parse_response(response.content)

    except Exception as e:
        print(f"[ERROR] process_landmark: {str(e)}")
        return None


# -----------------------------
# Parse AI JSON response (handles markdown code fences)
# -----------------------------
def parse_response(response_text: str) -> dict:
    defaults = {
        "landmark_name": "Unknown",
        "location": "Unknown",
        "year_completed": "Unknown",
        "materials": "Unknown",
        "architectural_style": "Unknown",
        "historical_overview": "Unknown",
        "cultural_impact": "Unknown",
        "famous_for": []
    }
    try:
        # Strip ```json or ``` code fences
        text = response_text.strip()
        if text.startswith("```") and text.endswith("```"):
            text = "\n".join(text.splitlines()[1:-1]).strip()

        data = json.loads(text)
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
        return data
    except Exception as e:
        print(f"[ERROR] parse_response: {e}")
        return defaults
