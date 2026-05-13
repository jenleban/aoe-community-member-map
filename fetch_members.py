import requests
import json
import time
import os
import re
import random

MIGHTY_API_TOKEN = os.environ["MIGHTY_API_TOKEN"]
NETWORK_ID = "14221297"
BASE_URL = f"https://api.mn.co/admin/v1/networks/{NETWORK_ID}"
HEADERS = {
    "Authorization": f"Bearer {MIGHTY_API_TOKEN}",
    "User-Agent": "curl/7.88.1"
}

geocode_cache = {}

# ─── US States ───────────────────────────────────────────────────────────────

US_STATE_NAMES = [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine',
    'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi',
    'Missouri', 'Montana', 'Nebraska', 'Nevada', 'New Hampshire',
    'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota',
    'Ohio', 'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island',
    'South Carolina', 'South Dakota', 'Tennessee', 'Texas', 'Utah',
    'Vermont', 'Virginia', 'Washington', 'West Virginia', 'Wisconsin', 'Wyoming'
]

# Note: 'IN' (Indiana) intentionally excluded - too often matched as preposition "in"
US_STATE_ABBREVS = [
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA',
    'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM',
    'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD',
    'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
]

# ─── Timezone → Approximate Coordinates ──────────────────────────────────────

TIMEZONE_COORDS = {
    "America/New_York":       (39.0, -76.0),
    "America/Chicago":        (41.0, -89.0),
    "America/Denver":         (39.5, -105.0),
    "America/Phoenix":        (34.0, -112.0),
    "America/Los_Angeles":    (36.0, -119.0),
    "America/Anchorage":      (61.2, -149.9),
    "Pacific/Honolulu":       (21.3, -157.8),
    "America/Toronto":        (43.7, -79.4),
    "America/Vancouver":      (49.3, -123.1),
    "America/Halifax":        (44.6, -63.6),
    "America/St_Johns":       (47.6, -52.7),
    "America/Winnipeg":       (49.9, -97.1),
    "America/Edmonton":       (53.5, -113.5),
    "America/Regina":         (50.4, -104.6),
    "Europe/London":          (51.5, -0.1),
    "Europe/Dublin":          (53.3, -6.3),
    "Europe/Paris":           (48.9, 2.3),
    "Europe/Berlin":          (52.5, 13.4),
    "Europe/Rome":            (41.9, 12.5),
    "Europe/Madrid":          (40.4, -3.7),
    "Europe/Amsterdam":       (52.4, 4.9),
    "Europe/Brussels":        (50.8, 4.4),
    "Europe/Zurich":          (47.4, 8.5),
    "Europe/Stockholm":       (59.3, 18.1),
    "Europe/Oslo":            (59.9, 10.7),
    "Europe/Copenhagen":      (55.7, 12.6),
    "Europe/Helsinki":        (60.2, 24.9),
    "Europe/Warsaw":          (52.2, 21.0),
    "Europe/Prague":          (50.1, 14.4),
    "Europe/Vienna":          (48.2, 16.4),
    "Europe/Athens":          (37.9, 23.7),
    "Europe/Lisbon":          (38.7, -9.1),
    "Australia/Sydney":       (-33.9, 151.2),
    "Australia/Melbourne":    (-37.8, 145.0),
    "Australia/Brisbane":     (-27.5, 153.0),
    "Australia/Perth":        (-31.9, 115.9),
    "Australia/Adelaide":     (-34.9, 138.6),
    "Pacific/Auckland":       (-36.9, 174.8),
    "Asia/Tokyo":             (35.7, 139.7),
    "Asia/Seoul":             (37.6, 127.0),
    "Asia/Shanghai":          (31.2, 121.5),
    "Asia/Hong_Kong":         (22.3, 114.2),
    "Asia/Singapore":         (1.3, 103.8),
    "Asia/Kolkata":           (20.6, 78.9),
    "Asia/Dubai":             (25.2, 55.3),
    "Asia/Bangkok":           (13.8, 100.5),
    "Asia/Jakarta":           (-6.2, 106.8),
    "Africa/Johannesburg":    (-26.2, 28.0),
    "Africa/Cairo":           (30.1, 31.2),
    "Africa/Lagos":           (6.5, 3.4),
    "America/Sao_Paulo":      (-23.5, -46.6),
    "America/Argentina/Buenos_Aires": (-34.6, -58.4),
    "America/Bogota":         (4.7, -74.1),
    "America/Lima":           (-12.0, -77.0),
    "America/Santiago":       (-33.5, -70.6),
    "America/Mexico_City":    (19.4, -99.1),
}

# ─── Bio Location Extraction ──────────────────────────────────────────────────

def extract_location_from_bio(bio):
    """
    Try to extract a geocodeable location string from a member's bio.
    Returns a location string like 'Tampa, FL' or 'Montana', or None.
    """
    if not bio or bio.strip() in ('', ' '):
        return None

    # Strip emojis and non-ASCII characters, normalize whitespace
    bio_clean = re.sub(r'[^\x00-\x7F]+', ' ', bio)
    bio_clean = re.sub(r'\s+', ' ', bio_clean).strip()

    if not bio_clean:
        return None

    abbrev_str = '|'.join(US_STATE_ABBREVS)

    # Pattern 1: "City, XX" — explicit city + 2-letter state abbreviation
    # e.g. "Art teacher in Joliet, IL" or "High School Teacher, Belmont, CA"
    city_abbrev = re.compile(
        r'\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),\s*(' + abbrev_str + r')\b'
    )
    match = city_abbrev.search(bio_clean)
    if match:
        return f"{match.group(1)}, {match.group(2)}"

    # Pattern 2: "in [City] [State abbrev]" — city + abbreviation after "in"
    # e.g. "teaching in Tampa FL"
    in_city_abbrev = re.compile(
        r'\bin\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),?\s+(' + abbrev_str + r')\b'
    )
    match = in_city_abbrev.search(bio_clean)
    if match:
        return f"{match.group(1)}, {match.group(2)}"

    # Pattern 3: "in [Full State Name]"
    # e.g. "art teacher in Montana" or "teaching in Kentucky"
    # Sort by length descending so "New York" matches before "York"
    for state in sorted(US_STATE_NAMES, key=len, reverse=True):
        pattern = re.compile(r'\bin\s+' + re.escape(state) + r'\b', re.IGNORECASE)
        if pattern.search(bio_clean):
            return state

    # Pattern 4: "suburbs of [City]" or "area of [City]"
    # e.g. "teacher in the suburbs of Chicago"
    suburbs_match = re.compile(
        r'\bsuburbs?\s+of\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\b',
        re.IGNORECASE
    )
    match = suburbs_match.search(bio_clean)
    if match:
        return match.group(1)

    # Pattern 5: "from [City, State]" or "from [State]"
    from_match = re.compile(
        r'\bfrom\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?),?\s*(' + abbrev_str + r')\b'
    )
    match = from_match.search(bio_clean)
    if match:
        return f"{match.group(1)}, {match.group(2)}"

    return None


# ─── Geocoding ────────────────────────────────────────────────────────────────

def jitter(coord, amount=1.5):
    return coord + random.uniform(-amount, amount)

def geocode_city(location):
    if not location:
        return None
    if location in geocode_cache:
        return geocode_cache[location]
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": "AOEU-MemberMap/1.0 (jenniferleban@theartofeducation.edu)"}
        )
        data = resp.json()
        result = {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])} if data else None
        geocode_cache[location] = result
        time.sleep(1)
        return result
    except Exception as e:
        print(f"Geocoding failed for '{location}': {e}")
        return None

def coords_from_timezone(tz):
    if not tz:
        return None
    coords = TIMEZONE_COORDS.get(tz)
    if coords:
        return {"lat": jitter(coords[0]), "lng": jitter(coords[1])}
    prefix = tz.split("/")[0]
    fallbacks = {
        "America":   (39.5, -98.4),
        "Europe":    (50.0, 10.0),
        "Asia":      (34.0, 100.0),
        "Africa":    (0.0, 20.0),
        "Pacific":   (-20.0, 170.0),
        "Australia": (-25.0, 134.0),
    }
    if prefix in fallbacks:
        c = fallbacks[prefix]
        return {"lat": jitter(c[0], 3.0), "lng": jitter(c[1], 5.0)}
    return None


# ─── Fetch Members ────────────────────────────────────────────────────────────

def fetch_all_members():
    members = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE_URL}/members",
            headers=HEADERS,
            params={"page": page, "per_page": 100}
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("items", [])
        if not batch:
            break
        members.extend(batch)
        print(f"  Fetched page {page} ({len(batch)} members)...")
        if not data.get("links", {}).get("next"):
            break
        page += 1
    return members


# ─── Build Map Data ───────────────────────────────────────────────────────────

def build_map_data():
    print("Fetching members from Mighty Networks...")
    raw_members = fetch_all_members()
    print(f"\nTotal members fetched: {len(raw_members)}")
    print("Geocoding locations...\n")

    map_members = []
    placed_by_location  = 0
    placed_by_bio       = 0
    placed_by_timezone  = 0
    skipped             = 0

    for m in raw_members:
        location  = (m.get("location") or "").strip()
        bio       = m.get("bio") or ""
        tz        = m.get("time_zone", "")
        full_name = f"{m.get('first_name', '')} {m.get('last_name', '')}".strip()

        coords        = None
        display_loc   = location   # what shows in the popup
        location_source = None

        # ── 1. Try explicit profile location first ──
        if location:
            coords = geocode_city(location)
            if coords:
                location_source = "location"
                placed_by_location += 1

        # ── 2. Try extracting location from bio ──
        if not coords:
            bio_location = extract_location_from_bio(bio)
            if bio_location:
                coords = geocode_city(bio_location)
                if coords:
                    location_source = "bio"
                    display_loc = bio_location
                    placed_by_bio += 1

        # ── 3. Fall back to timezone approximation ──
        if not coords:
            coords = coords_from_timezone(tz)
            if coords:
                location_source = "timezone"
                display_loc = ""
                placed_by_timezone += 1
            else:
                skipped += 1

        if coords:
            map_members.append({
                "name":         full_name or "Unknown",
                "location":     display_loc,
                "profile_url":  m.get("permalink", f"https://community.theartofeducation.edu/members/{m.get('id')}"),
                "avatar":       m.get("avatar", ""),
                "bio":          bio,
                "lat":          coords["lat"],
                "lng":          coords["lng"]
            })

    print(f"✅ {len(map_members)} members placed on map")
    print(f"   📍 {placed_by_location} placed by profile location (exact)")
    print(f"   📝 {placed_by_bio} placed by bio location (extracted)")
    print(f"   🌍 {placed_by_timezone} placed by timezone (approximate)")
    print(f"⚠️  {skipped} members skipped (no location, bio, or timezone)")

    with open("members.json", "w") as f:
        json.dump(map_members, f, indent=2)
    print("💾 Saved to members.json")


if __name__ == "__main__":
    build_map_data()
