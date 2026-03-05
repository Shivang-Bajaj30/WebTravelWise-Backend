import os
import json
import re
import requests
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
import time

# Load environment variables
load_dotenv()

# Initialize Gemini client
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Models to try (in order of preference) — auto-fallback if one is rate-limited
GEMINI_MODELS = ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-1.5-flash"]


def _parse_date(d):
    """Parse a date string into a date object.

    Supports common formats and ISO. Raises ValueError on failure.
    """
    if isinstance(d, date):
        return d
    if not isinstance(d, str):
        raise ValueError(f"Invalid date value: {d}")

    # try several common formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y", "%b %d %Y", "%d %b %Y"):
        try:
            return datetime.strptime(d, fmt).date()
        except Exception:
            pass

    # fallback to fromisoformat
    try:
        return datetime.fromisoformat(d).date()
    except Exception:
        raise ValueError(f"Unrecognized date format: {d}")

def _log_raw_response(content, label="response"):
    try:
        ts = int(time.time())
        fname = f"ai_gen_raw_{label}_{ts}.json"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[AI_Gen] Raw model output saved to {fname}")
    except Exception as e:
        print("[AI_Gen] Failed to write raw model output:", e)


def _fetch_tripadvisor_image(query):
    """Fetch a real photo via TripAdvisor Content API.
    
    Two-step: search for location → get photos for that location.
    Requires TRIPADVISOR_API_KEY in .env (free tier).
    Returns the image URL or None.
    """
    api_key = os.getenv("TRIPADVISOR_API_KEY")
    if not api_key:
        print("[AI_Gen] TRIPADVISOR_API_KEY not found in .env")
        return None

    try:
        # Step 1: Search for the location
        search_url = "https://api.content.tripadvisor.com/api/v1/location/search"
        search_params = {
            "key": api_key,
            "searchQuery": query,
            "language": "en",
        }
        search_resp = requests.get(search_url, params=search_params, timeout=8)
        if search_resp.status_code != 200:
            print(f"[AI_Gen] TripAdvisor search error {search_resp.status_code}")
            return None

        locations = search_resp.json().get("data", [])
        if not locations:
            return None

        location_id = locations[0].get("location_id")
        if not location_id:
            return None

        # Step 2: Get photos for this location
        photos_url = f"https://api.content.tripadvisor.com/api/v1/location/{location_id}/photos"
        photos_params = {
            "key": api_key,
            "language": "en",
        }
        photos_resp = requests.get(photos_url, params=photos_params, timeout=8)
        if photos_resp.status_code != 200:
            return None

        photos = photos_resp.json().get("data", [])
        if photos:
            # Get the largest available image
            images = photos[0].get("images", {})
            for size in ["large", "medium", "original", "small"]:
                if size in images and "url" in images[size]:
                    return images[size]["url"]

    except Exception as e:
        print(f"[AI_Gen] TripAdvisor image fetch failed for '{query}': {e}")
    return None


def _enrich_with_images(itinerary_data, destination=""):
    """Add real photos to places and hotels via TripAdvisor."""
    if not itinerary_data:
        return itinerary_data

    # Enrich places
    for place in itinerary_data.get("places", []):
        if not place.get("image"):
            search_query = f"{place.get('name', '')} {destination}"
            img = _fetch_tripadvisor_image(search_query)
            if img:
                place["image"] = img
                print(f"[AI_Gen] 📷 Found image for place: {place.get('name')}")
            else:
                print(f"[AI_Gen] ❌ No image found for place: {place.get('name')}")

    # Enrich hotels
    for hotel in itinerary_data.get("hotels", []):
        if not hotel.get("image"):
            search_query = f"{hotel.get('name', '')} {destination}"
            img = _fetch_tripadvisor_image(search_query)
            if img:
                hotel["image"] = img
                print(f"[AI_Gen] 📷 Found image for hotel: {hotel.get('name')}")
            else:
                print(f"[AI_Gen] ❌ No image found for hotel: {hotel.get('name')}")

    return itinerary_data


def _call_gemini(prompt, system_instruction="You are a travel itinerary assistant that returns only valid JSON."):
    """Call the Gemini API. Tries each model in GEMINI_MODELS, falling back on rate limits."""
    last_error = None

    for model in GEMINI_MODELS:
        try:
            print(f"[AI_Gen] Trying model: {model}\n\n")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,
                    max_output_tokens=8000,
                    response_mime_type="application/json",
                ),
            )
            print(f"[AI_Gen] ✅ Success with model: {model}\n\n")
            return response.text.strip()
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_rate_limit = "429" in error_str or "quota" in error_str or "resource_exhausted" in error_str or "rate" in error_str

            if is_rate_limit:
                print(f"[AI_Gen] ⚠️ {model} rate limited, trying next model...\n\n\n")
                continue  # try next model
            else:
                raise  # non-rate-limit error, raise immediately

    # All models exhausted
    raise last_error


def _extract_json(content):
    """Extract JSON from a string that might contain markdown fences, thinking text, or extra content."""
    # Strip any control characters except newlines/tabs
    content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)

    # Remove markdown code fences if present (handles ```json and ```)
    fence_pattern = re.compile(r'```(?:json)?\s*\n?(.*?)\n?```', re.DOTALL)
    fence_match = fence_pattern.search(content)
    if fence_match:
        content = fence_match.group(1).strip()

    # If still not starting with {, try to find the outermost JSON object
    if not content.startswith("{"):
        start = content.find("{")
        end = content.rfind("}") + 1
        if start != -1 and end > start:
            content = content[start:end]

    # Attempt to repair truncated JSON (missing closing brackets)
    # Count unmatched braces/brackets
    open_braces = content.count("{") - content.count("}")
    open_brackets = content.count("[") - content.count("]")

    if open_braces > 0 or open_brackets > 0:
        # Truncate to last complete value (remove trailing partial content)
        # Find the last complete line that ends with a comma, bracket, or brace
        last_good = max(content.rfind(',\n'), content.rfind('\n'))
        if last_good > len(content) // 2:  # only truncate if we have most of the content
            content = content[:last_good]
        # Close any remaining open brackets/braces
        content += "]" * max(0, open_brackets)
        content += "}" * max(0, open_braces)

    return content.strip()


def _generate_itinerary_chunk(destination, travelers, start_date, end_date, preferences, budget=None, travel_with=None):
    """Generate itinerary for a single chunk (<=7 days)."""
    warning = None
    source = "ai"
    try:
        sd = _parse_date(start_date)
        ed = _parse_date(end_date)
        days_count = (ed - sd).days + 1
        if days_count <= 0:
            days_count = 1
    except Exception:
        days_count = None

    travel_with_display = travel_with or preferences or "travelers' preferences"
    budget_display = budget or "unspecified"

    prompt = f"""
Create a {days_count}-day travel itinerary for {travelers} people visiting {destination} on a {budget_display} budget, tailored for {travel_with_display}.
Use real, famous places and hotels that actually exist in {destination}.
Include 4-5 hotels with varying price ranges. Keep descriptions short (1 sentence max).
Do NOT include any Google Maps URLs. Only include coordinates.

Return a valid JSON object with this exact structure:

{{
    "places": [
        {{
            "name": "Real place name",
            "time": "2-3 hours",
            "details": "One sentence description",
            "coordinates": {{"lat": 0.0, "lng": 0.0}},
            "pricing": "Entry fee",
            "bestTime": "Best time to visit"
        }}
    ],
    "hotels": [
        {{
            "name": "Real hotel name",
            "address": "Short address",
            "coordinates": {{"lat": 0.0, "lng": 0.0}},
            "price": "Price range per night",
            "rating": "4.5/5",
            "amenities": ["WiFi", "Pool"],
            "description": "One sentence"
        }}
    ],
    "transportation": ["Option 1", "Option 2"],
    "costs": ["Accommodation: ₹X", "Food: ₹Y"],
    "itinerary": [{{"day": 1, "activities": ["Morning: Activity", "Afternoon: Activity"]}}]
}}
"""

    if days_count:
        prompt += f"\nIMPORTANT: The 'itinerary' array MUST contain EXACTLY {days_count} objects. Number 'day' fields sequentially from 1 to {days_count}.\n"

    try:
        content = _call_gemini(prompt)
        content = _extract_json(content)

        try:
            itinerary_data = json.loads(content)
        except Exception:
            _log_raw_response(content, label="invalid_json")
            raise

        # Validate days_count and retry once if needed
        if days_count and "itinerary" in itinerary_data:
            if len(itinerary_data["itinerary"]) != days_count:
                orig_len = len(itinerary_data["itinerary"])
                warning = f"Model returned {orig_len} days but {days_count} were requested. Normalizing (truncate/pad)."
                source = "partial"
                retry_prompt = prompt + f"\nYou returned {len(itinerary_data['itinerary'])} days but required {days_count}. Return EXACTLY {days_count} days now, keep same style.\n"

                content2 = _call_gemini(retry_prompt)
                content2 = _extract_json(content2)

                try:
                    itinerary_data = json.loads(content2)
                    if days_count and 'itinerary' in itinerary_data and len(itinerary_data['itinerary']) != days_count:
                        warning = f"After retry, model returned {len(itinerary_data['itinerary'])} days but {days_count} were requested. Normalizing (truncate/pad)."
                        source = "partial"
                except Exception:
                    _log_raw_response(content2, label="invalid_json_retry")
                    raise

        if warning:
            try:
                itinerary_data['warning'] = warning
                itinerary_data['source'] = source
            except Exception:
                pass

        # Enrich with real photos from Wikipedia
        # _enrich_with_images(itinerary_data, destination)

        return itinerary_data

    except json.JSONDecodeError:
        print("⚠️ Gemini returned invalid JSON. Returning fallback itinerary.")
        fallback_itinerary = []
        for i in range(days_count or 1):
            fallback_itinerary.append({"day": i + 1, "activities": ["Explore local attractions", "Try local cuisine"]})
        return {
            "places": [
                {"name": "FALLBACK DATA", "details": "FALLBACK DATA", "time": "FALLBACK DATA", "pricing": "FALLBACK DATA", "bestTime": "FALLBACK DATA", "coordinates": {"lat": 25.1972, "lng": 55.2744}}
            ],
            "hotels": [
                {"name": "FALLBACK DATA", "address": "FALLBACK DATA", "coordinates": {"lat": 25.1304, "lng": 55.1171},
                 "price": "FALLBACK DATA", "rating": "FALLBACK DATA", "amenities": ["FALLBACK DATA", "FALLBACK DATA", "FALLBACK DATA"],
                 "description": "FALLBACK DATA"}
            ],
            "transportation": ["FALLBACK DATA", "FALLBACK DATA"],
            "costs": ["FALLBACK DATA", "FALLBACK DATA"],
            "itinerary": fallback_itinerary,
            "error": "Gemini returned invalid JSON",
            "warning": "Model returned invalid JSON; returning fallback/sample itinerary.",
            "source": "fallback"
        }

    except Exception as e:
        print("AI Error:", str(e))
        return {
            "places": [],
            "hotels": [],
            "transportation": [],
            "costs": [],
            "itinerary": [{"day": i+1, "activities": ["Fallback activity"]} for i in range(days_count or 1)],
            "error": str(e),
            "warning": f"Server error: {str(e)}",
            "source": "error"
        }


def generate_itinerary(destination, travelers, start_date, end_date, preferences, budget=None, travel_with=None):
    """Wrapper: splits into 7-day chunks if needed, else calls _generate_itinerary_chunk."""
    try:
        sd = _parse_date(start_date)
        ed = _parse_date(end_date)
        days_count = (ed - sd).days + 1
        if days_count <= 0:
            days_count = 1
    except Exception:
        days_count = None

    if days_count and days_count > 7:
        all_itinerary = []
        all_places = []
        all_hotels = []
        all_transportation = set()
        all_costs = []
        chunk = 7
        chunk_start = sd
        chunk_end = min(chunk_start + timedelta(days=chunk-1), ed)
        day_num = 1
        chunk_idx = 0
        warning = None
        source = "ai"
        while chunk_start <= ed:
            chunk_days = (chunk_end - chunk_start).days + 1
            chunk_start_str = chunk_start.strftime("%Y-%m-%d")
            chunk_end_str = chunk_end.strftime("%Y-%m-%d")
            chunk_result = _generate_itinerary_chunk(
                destination,
                travelers,
                chunk_start_str,
                chunk_end_str,
                preferences,
                budget=budget,
                travel_with=travel_with,
            )
            if chunk_result.get("itinerary"):
                for i, day in enumerate(chunk_result["itinerary"]):
                    day_copy = dict(day)
                    day_copy["day"] = day_num
                    all_itinerary.append(day_copy)
                    day_num += 1
            if chunk_result.get("places"):
                all_places.extend(chunk_result["places"])
            if chunk_result.get("hotels"):
                all_hotels.extend(chunk_result["hotels"])
            if chunk_result.get("transportation"):
                all_transportation.update(chunk_result["transportation"])
            if chunk_result.get("costs"):
                all_costs.extend(chunk_result["costs"])
            if chunk_result.get("warning"):
                warning = (warning or "") + f" Chunk {chunk_idx+1}: {chunk_result['warning']}"
                source = chunk_result.get("source", source)
            chunk_idx += 1
            chunk_start = chunk_end + timedelta(days=1)
            chunk_end = min(chunk_start + timedelta(days=chunk-1), ed)
        result = {
            "places": all_places,
            "hotels": all_hotels,
            "transportation": list(all_transportation),
            "costs": all_costs,
            "itinerary": all_itinerary,
        }
        if warning:
            result["warning"] = warning
            result["source"] = source
        return result
    # Otherwise, do normal single-chunk generation
    return _generate_itinerary_chunk(destination, travelers, start_date, end_date, preferences, budget=budget, travel_with=travel_with)
