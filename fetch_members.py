#!/usr/bin/env python3
"""
fetch_members.py  — AOEU Community Member Map
Updated: adds State/Region supplementary geocoding (step 3 of 5)
         sourced from state_lookup.json (generated from BigQuery/Google Sheet col_11)

Geocoding priority order:
  1. location field    — exact city/state from MN profile
  2. bio extraction    — regex patterns in member bio
  3. state lookup  NEW — state code from state_lookup.json (BigQuery-sourced)
  4. timezone fallback — approximate center of member's timezone zone
  5. skip              — if none of the above yield a location
"""

import json
import math
import os
import random
import re
import time
import requests

# ── credentials ──────────────────────────────────────────────────────────────
API_TOKEN = os.environ["MIGHTY_API_TOKEN"]
NETWORK_ID = "14221297"
BASE_URL = f"https://api.mn.co/admin/v1/networks/{NETWORK_ID}"
HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}",
    "User-Agent": "curl/7.88.1",   # REQUIRED — without this, API returns 403
}

# ── geocoding service ─────────────────────────────────────────────────────────
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "aoeu-community-map/1.0 (jenniferleban@theartofeducation.edu)"}

# ── US state center coordinates (geographic centers) ─────────────────────────
# Used for state-level geocoding (step 3) with small random jitter (±0.8°)
# to avoid stacking members from the same state on one point.
STATE_CENTERS = {
    "AL": (32.779,  -86.829), "AK": (64.069, -153.369), "AZ": (34.274, -111.660),
    "AR": (34.894,  -92.443), "CA": (37.184, -119.470), "CO": (38.997, -105.548),
    "CT": (41.622,  -72.727), "DE": (38.990,  -75.505), "FL": (28.630,  -82.450),
    "GA": (32.642,  -83.443), "HI": (20.293, -156.374), "ID": (44.351, -114.613),
    "IL": (40.042,  -89.197), "IN": (39.894,  -86.282), "IA": (42.075,  -93.496),
    "KS": (38.494,  -98.380), "KY": (37.535,  -85.302), "LA": (31.069,  -91.997),
    "ME": (45.370,  -69.243), "MD": (39.055,  -76.791), "MA": (42.260,  -71.808),
    "MI": (44.347,  -85.410), "MN": (46.281,  -94.305), "MS": (32.736,  -89.668),
    "MO": (38.357,  -92.458), "MT": (46.880, -110.363), "NE": (41.538,  -99.795),
    "NV": (39.329, -116.631), "NH": (43.681,  -71.581), "NJ": (40.191,  -74.673),
    "NM": (34.407, -106.113), "NY": (42.954,  -75.527), "NC": (35.556,  -79.388),
    "ND": (47.450, -100.466), "OH": (40.286,  -82.794), "OK": (35.589,  -97.494),
    "OR": (43.934, -120.558), "PA": (40.878,  -77.800), "RI": (41.676,  -71.556),
    "SC": (33.917,  -80.896), "SD": (44.444, -100.226), "TN": (35.858,  -86.351),
    "TX": (31.476,  -99.331), "UT": (39.321, -111.094), "VT": (44.069,  -72.666),
    "VA": (37.522,  -78.854), "WA": (47.383, -120.447), "WV": (38.641,  -80.623),
    "WI": (44.624,  -89.994), "WY": (42.996, -107.551), "DC": (38.907,  -77.037),
}

# ── timezone → approximate center coordinates (existing fallback) ─────────────
TIMEZONE_CENTERS = {
    "America/New_York":          (40.7128, -74.0060),
    "America/Chicago":           (41.8781, -87.6298),
    "America/Denver":            (39.7392, -104.9903),
    "America/Los_Angeles":       (34.0522, -118.2437),
    "America/Phoenix":           (33.4484, -112.0740),
    "America/Anchorage":         (61.2181, -149.9003),
    "Pacific/Honolulu":          (21.3069, -157.8583),
    "America/Indiana/Indianapolis": (39.7684, -86.1581),
    "America/Detroit":           (42.3314, -83.0458),
    "America/Kentucky/Louisville":  (38.2527, -85.7585),
    "America/Toronto":           (43.6532, -79.3832),
    "America/Vancouver":         (49.2827, -123.1207),
    "America/Edmonton":          (53.5461, -113.4938),
    "America/Winnipeg":          (49.8951, -97.1384),
    "America/Halifax":           (44.6488, -63.5752),
    "Europe/London":             (51.5074,  -0.1278),
    "Europe/Paris":              (48.8566,   2.3522),
    "Australia/Sydney":          (-33.8688, 151.2093),
    "Asia/Tokyo":                (35.6762, 139.6503),
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def api_get(url):
    resp = requests.get(url, headers=HEADERS, timeout=30)
    print(f"  API status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  API error: {resp.text[:500]}")
        return {}
    return resp.json()


def nominatim_geocode(query):
    """Geocode a free-text location string using Nominatim. Returns (lat, lng) or None."""
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers=NOMINATIM_HEADERS)
    try:
        with urllib.request.urlopen(req) as resp:
            results = json.loads(resp.read().decode())
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    time.sleep(1)  # rate limit: 1 req/sec per Nominatim ToS
    return None


def jitter(lat, lng, spread=0.8):
    """Add small random offset so nearby members don't stack exactly."""
    return (
        lat + random.uniform(-spread, spread),
        lng + random.uniform(-spread, spread),
    )


def geocode_by_state(state_code):
    """Return jittered state-center coordinates for a 2-letter US state code."""
    center = STATE_CENTERS.get(state_code.upper())
    if center:
        return jitter(center[0], center[1], spread=0.8)
    return None


def extract_location_from_bio(bio):
    """
    Scan bio text for location patterns. Returns the best location string or None.
    Patterns (in priority order):
      - "City, ST"  (standard US format)
      - "in City, State"
      - "in State"
      - "suburbs of City"
      - "from City, ST"
    """
    if not bio:
        return None
    patterns = [
        r'\b([A-Z][a-zA-Z .]+),\s*([A-Z]{2})\b',        # City, ST
        r'\bin\s+([A-Z][a-zA-Z ]+),\s+([A-Za-z]+)\b',    # in City, State
        r'\bfrom\s+([A-Z][a-zA-Z ]+),\s*([A-Z]{2})\b',   # from City, ST
        r'\bsuburbs?\s+of\s+([A-Z][a-zA-Z ]+)\b',        # suburbs of City
        r'\bin\s+([A-Z][a-zA-Z]{3,})\b',                  # in State
    ]
    for pat in patterns:
        m = re.search(pat, bio)
        if m:
            return " ".join(m.groups())
    return None


def geocode_by_timezone(tz):
    """Return jittered timezone-center coordinates, or None."""
    center = TIMEZONE_CENTERS.get(tz)
    if center:
        return jitter(center[0], center[1], spread=2.0)   # wider jitter for timezone fallback
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Load supplementary state lookup  (BigQuery / Google Sheet col_11 source)
# ─────────────────────────────────────────────────────────────────────────────

def load_state_lookup(path="state_lookup.json"):
    """
    Load member_id → state_code mapping from state_lookup.json.
    Returns an empty dict if the file doesn't exist (graceful degradation).
    Generated by generate_state_lookup.py from the Members Import Google Sheet (col_11).
    """
    if not os.path.exists(path):
        print(f"  ⚠️  {path} not found — state-level geocoding will be skipped.")
        print("     Run generate_state_lookup.py to create it.")
        return {}
    with open(path) as f:
        data = json.load(f)
    print(f"  ✅ Loaded state lookup: {len(data):,} member → state mappings")
    return data


# ─────────────────────────────────────────────────────────────────────────────
# Fetch all members from Mighty Networks API
# ─────────────────────────────────────────────────────────────────────────────

def fetch_all_members():
    """Paginate through the Mighty Networks members endpoint, 100 per page."""
    members = []
    url = f"{BASE_URL}/members?per_page=100"
    page = 0
    while url:
        page += 1
        data = api_get(url)
        batch = data.get("members", [])
        if not batch:
            break
        members.extend(batch)
        print(f"  Fetched page {page} ({len(batch)} members, {len(members)} total so far)")
        url = data.get("links", {}).get("next")
        time.sleep(0.5)   # be polite to the API
    return members


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=== AOEU Member Map: fetch_members.py ===\n")

    # 1. Load supplementary state lookup (BigQuery-sourced)
    print("[1/3] Loading supplementary state lookup…")
    state_lookup = load_state_lookup("state_lookup.json")

    # 2. Fetch all members from the Mighty Networks API
    print("\n[2/3] Fetching members from Mighty Networks API…")
    raw_members = fetch_all_members()
    print(f"  Total members fetched: {len(raw_members):,}")

    # 3. Geocode each member
    print("\n[3/3] Geocoding members…")
    output = []
    stats = {"location": 0, "bio": 0, "state_lookup": 0, "timezone": 0, "skipped": 0}
    geocode_cache = {}   # avoid re-geocoding identical location strings

    for m in raw_members:
        member_id  = str(m.get("id", ""))
        location   = (m.get("location") or "").strip()
        bio        = (m.get("bio") or "").strip()
        timezone   = (m.get("time_zone") or "").strip()
        name       = f"{m.get('first_name', '')} {m.get('last_name', '')}".strip()
        profile_url = m.get("permalink", "")
        avatar     = m.get("avatar", "")

        lat = lng = None
        method = None

        # ── Step 1: location field ──────────────────────────────────────────
        if location:
            if location in geocode_cache:
                lat, lng = geocode_cache[location]
                method = "location"
            else:
                coords = nominatim_geocode(location)
                if coords:
                    lat, lng = coords
                    geocode_cache[location] = coords
                    method = "location"

        # ── Step 2: bio extraction ──────────────────────────────────────────
        if lat is None:
            bio_loc = extract_location_from_bio(bio)
            if bio_loc:
                if bio_loc in geocode_cache:
                    lat, lng = geocode_cache[bio_loc]
                    method = "bio"
                else:
                    coords = nominatim_geocode(bio_loc)
                    if coords:
                        lat, lng = coords
                        geocode_cache[bio_loc] = coords
                        method = "bio"

        # ── Step 3: state lookup (NEW — BigQuery / Google Sheet col_11) ─────
        if lat is None and member_id in state_lookup:
            state_code = state_lookup[member_id]
            coords = geocode_by_state(state_code)
            if coords:
                lat, lng = coords
                method = "state_lookup"

        # ── Step 4: timezone fallback ───────────────────────────────────────
        if lat is None and timezone:
            coords = geocode_by_timezone(timezone)
            if coords:
                lat, lng = coords
                method = "timezone"

        # ── Step 5: skip ────────────────────────────────────────────────────
        if lat is None:
            stats["skipped"] += 1
            continue

        stats[method] += 1
        output.append({
            "id":          member_id,
            "name":        name,
            "location":    location or state_lookup.get(member_id, ""),
            "profile_url": profile_url,
            "avatar":      avatar,
            "bio":         bio[:300] if bio else "",
            "lat":         round(lat, 5),
            "lng":         round(lng, 5),
            "geo_method":  method,   # useful for debugging map density
        })

    # 4. Write output
    with open("members.json", "w") as f:
        json.dump(output, f, indent=2)

    # 5. Print stats
    total_placed = len(output)
    total = len(raw_members)
    print(f"\n{'='*45}")
    print(f"  Members fetched:          {total:>6,}")
    print(f"  Placed by location field: {stats['location']:>6,}")
    print(f"  Placed by bio extraction: {stats['bio']:>6,}")
    print(f"  Placed by state lookup:   {stats['state_lookup']:>6,}  ← NEW")
    print(f"  Placed by timezone:       {stats['timezone']:>6,}")
    print(f"  Skipped (no data):        {stats['skipped']:>6,}")
    print(f"  ─────────────────────────────────")
    if total > 0:
            print(f"  Total placed on map:      {total_placed:>6,}  ({total_placed/total*100:.1f}%)")
    print(f"{'='*45}")


if __name__ == "__main__":
    main()
