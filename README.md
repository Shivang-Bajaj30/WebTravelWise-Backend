# TravelWise - Backend

Flask backend for TravelWise. Provides user auth, trip storage, and AI-powered itinerary generation with robust fallback logic so the API always returns a complete itinerary for any requested date range.

This README explains how to set up and run the backend, the AI itinerary behaviour (chunking, normalization, fallbacks), and integration notes for the frontend.

---

## Features
- User signup & login (see `app.py`, `models/User.py`).
- AI itinerary generation (`AI_Gen.py`) with:
  - Date parsing and inclusive day counting.
  - Automatic chunking for long trips (7-day chunks by default).
  - Retry logic and raw-response logging for debugging.
  - Deterministic fallback/padding so the returned itinerary always contains exactly the requested number of day entries.
  - Response metadata to notify the frontend if any days were auto-generated or if a fallback was used (`warning`, `source`, `error`).

---

## Getting started

Prerequisites
- Python 3.10+ (or a supported 3.x runtime).
- pip
- an OpenAI API key (if you want real AI-generated itineraries).

Recommended quick setup (Windows / cmd.exe):

1. Create a virtual environment and activate it:

```cmd
python -m venv .venv
.venv\Scripts\activate
```

2. Install dependencies (create a `requirements.txt` if not present). Example packages used in this repo:

```cmd
pip install flask flask_sqlalchemy python-dotenv openai werkzeug
```

3. Create a `.env` file in the project root and add required variables. Example:

```
FLASK_ENV=development
OPENAI_API_KEY=sk-...
# your DB connection string or other secrets used by msconfig.py
```

4. Run the app:

```cmd
python app.py
```

The server will start on `http://127.0.0.1:5000` by default.

---

## Important files
- `app.py` — Flask app and routes (signup, login, generate_itinerary, etc.).
- `AI_Gen.py` — produces the itinerary JSON using the OpenAI client and includes chunking, normalization, and fallback logic.
- `models/User.py`, `models/Trips.py` — SQLAlchemy models for users and saved trips.
- `.env` — environment variables (not checked in).

---

## AI itinerary behavior (how it guarantees full itineraries)

The backend implements several measures so the API always returns a full itinerary array matching the requested date range:

1. Date parsing & inclusive day count
   - `AI_Gen._parse_date()` accepts common date formats and ISO dates and computes inclusive day count (end - start + 1).

2. Chunking for long trips
   - If the requested duration > 7 days, the backend splits the range into 7-day chunks and generates each chunk separately. Chunks are merged and re-numbered so frontend receives a single combined itinerary.

3. Model prompt & retries
   - Prompts explicitly instruct the model to return EXACTLY N day objects.
   - If the model returns the wrong number of days, the backend retries once with a stricter prompt.

4. Normalization & deterministic filler days
   - If the model still returns fewer days, the backend pads the itinerary with deterministic, varied filler activities (not a single "Sample activity").
   - If the model returns invalid JSON, the raw content is saved to a timestamped file (`ai_gen_raw_invalid_json_<ts>.json`) and the backend returns a realistic fallback itinerary.

5. Response metadata (for the frontend)
   - Responses include optional fields so the frontend can display notices:
     - `warning` — short human-readable note (e.g., "Model returned 5 days but 10 were requested. Normalizing...").
     - `source` — one of `ai` (normal), `partial` (we normalized or padded), `fallback` (fallback generated), `error` (server error).
     - `error` — present when JSON invalid or server exceptions happen.

Frontend integration note: show a small banner/notice if `warning` exists or if `source` !== `ai` (for example: "Note: Some days were auto-generated because the AI response was incomplete.").

---

## API endpoints (examples)

1. Health

GET /

2. Signup

POST /signup
Request body (JSON): { "name": "...", "email": "...", "password": "..." }

3. Login

POST /login
Request body (JSON): { "email": "...", "password": "..." }

4. Generate itinerary

POST /generate_itinerary
Request body example:

```json
{
  "destination": "Dubai",
  "travelers": 2,
  "startDate": "2025-11-01",
  "endDate": "2025-11-08",
  "preferences": "family-friendly, moderate budget"
}
```

Response (example keys):

```
{
  "places": [...],
  "hotels": [...],
  "transportation": [...],
  "costs": [...],
  "itinerary": [ {"day": 1, "activities": [...]}, ... ],
  "warning": "Model returned 5 days but 8 were requested...",   // optional
  "source": "partial",                                       // optional
  "error": "..."                                             // optional
}
```

The itinerary array is guaranteed to contain exactly the requested number of day objects. If any part was auto-generated or fallback, check `warning`/`source` fields.

---

## Troubleshooting

- If you get invalid JSON or truncated itineraries:
  - Check your `OPENAI_API_KEY` and your plan's token limits (`max_tokens`); long trips produce larger outputs.
  - Check the repo root for `ai_gen_raw_invalid_json_*` files — they contain the raw model output used for debugging.

- If you want very detailed per-day content for extremely long trips (30+ days):
  - Consider increasing the chunk size (currently 7) or customizing the prompt to reduce per-day verbosity.
  - The backend guarantees a full itinerary by padding or generating filler days; if you prefer always to rely on the model only, increase `max_tokens` and run multiple retries.

---