import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
import time

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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


def _filler_activities(n):
    samples = [
        "Relax at the hotel and enjoy amenities",
        "Explore a nearby local market",
        "Try popular local snacks at a street food stall",
        "Take a short guided walking tour",
        "Visit a local museum or cultural center",
        "Enjoy a sunset viewpoint",
        "Spend time at a popular shopping area",
    ]
    out = []
    for i in range(n):
        out.append(samples[i % len(samples)])
    return out


def _log_raw_response(content, label="response"):
    try:
        ts = int(time.time())
        fname = f"ai_gen_raw_{label}_{ts}.json"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[AI_Gen] Raw model output saved to {fname}")
    except Exception as e:
        print("[AI_Gen] Failed to write raw model output:", e)


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
Please include 4-5 different hotels with varying price ranges and amenities.

Return a valid JSON object with this structure (ONLY the JSON, no other text):

{{
    "places": [
        {{
            "name": "Place Name (use real place names in {destination})",
            "time": "2-3 hours",
            "details": "Brief description",
            "location": "Google Maps URL (clickable) for the place, e.g. https://www.google.com/maps/place/...",
            "coordinates": {{"lat": 0.0, "lng": 0.0}},
            "pricing": "Entry fee info",
            "bestTime": "Best time to visit"
        }}
    ],
    "hotels": [
        {{
            "name": "Hotel Name (use real hotels in {destination})",
            "address": "Real address in {destination}",
            "location": "Google Maps URL for the hotel (clickable)",
            "coordinates": {{"lat": 0.0, "lng": 0.0}},
            "price": "Price range",
            "rating": "4.5/5",
            "amenities": [],
            "description": "Brief description"
        }}
    ],
  "transportation": ["Transportation option 1"],
      "costs": ["Accommodation: ₹X"],
  "itinerary": [{{"day": 1, "activities": ["Morning: Activity"]}}]
}}

Return ONLY the JSON object as shown above. Do not include any explanatory text.
"""

    if days_count:
        prompt += f"\nIMPORTANT: The 'itinerary' array MUST contain EXACTLY {days_count} objects. Number 'day' fields sequentially from 1 to {days_count}.\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a travel itinerary assistant that returns only JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
        )

        content = response.choices[0].message.content.strip()

        if not content.startswith("{"):
            start = content.find("{")
            end = content.rfind("}") + 1
            if start != -1 and end != -1:
                content = content[start:end]

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
                response2 = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a travel itinerary assistant that returns only JSON."},
                        {"role": "user", "content": retry_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=2000,
                )
                content2 = response2.choices[0].message.content.strip()
                if not content2.startswith("{"):
                    start = content2.find("{")
                    end = content2.rfind("}") + 1
                    if start != -1 and end != -1:
                        content2 = content2[start:end]
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

        return itinerary_data

    except json.JSONDecodeError:
        print("⚠️ GPT returned invalid JSON. Returning fallback itinerary.")
        fallback_itinerary = []
        for i in range(days_count or 1):
            activities = _filler_activities(2)
            fallback_itinerary.append({"day": i + 1, "activities": activities})
        return {
            "places": [
                {"name": "Burj Khalifa", "details": "Iconic Dubai landmark", "time": "Morning", "pricing": "₹2800", "bestTime": "Evening", "location": "https://www.google.com/maps/place/Burj+Khalifa", "coordinates": {"lat": 25.1972, "lng": 55.2744}}
            ],
            "hotels": [
                {"name": "Atlantis The Palm", "address": "Crescent Rd, The Palm Jumeirah, Dubai", "location": "https://www.google.com/maps/place/Atlantis+The+Palm+Dubai", "coordinates": {"lat": 25.1304, "lng": 55.1171},
                 "price": "₹29000/night", "rating": "4.8/5", "amenities": ["Wi-Fi", "Pool", "Beach"],
                 "description": "Luxury beachfront hotel with ocean views."}
            ],
            "transportation": ["Metro", "Taxi"],
            "costs": ["Accommodation: ₹58000", "Food: ₹20000"],
            "itinerary": fallback_itinerary,
            "error": "GPT returned invalid JSON",
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
