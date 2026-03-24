import requests
import json
import time
import os

MIGHTY_API_TOKEN = os.environ["MIGHTY_API_TOKEN"]
NETWORK_ID = "14221297"
BASE_URL = f"https://api.mn.co/admin/v1/networks/{NETWORK_ID}"
HEADERS = {
    "Authorization": f"Bearer {MIGHTY_API_TOKEN}",
    "User-Agent": "curl/7.88.1"
}

geocode_cache = {}

# Timezone → approximate country/region center coordinates
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

import random

def jitter(coord, amount=1.5):
    """Add a tiny random offset so pins don't stack exactly on top of each other."""
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
    """Fall back to approximate region coords based on timezone."""
    if not tz:
        return None
    coords = TIMEZONE_COORDS.get(tz)
    if coords:
        return {"lat": jitter(coords[0]), "lng": jitter(coords[1])}
    # Try continent-level fallback from timezone prefix
    prefix = tz.split("/")[0]
    fallbacks = {
        "America": (39.5, -98.4),
        "Europe":  (50.0, 10.0),
        "Asia":    (34.0, 100.0),
        "Africa":  (0.0, 20.0),
        "Pacific": (-20.0, 170.0),
        "Australia": (-25.0, 134.0),
    }
    if prefix in fallbacks:
        c = fallbacks[prefix]
        return {"lat": jitter(c[0], 3.0), "lng": jitter(c[1], 5.0)}
    return None

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

def build_map_data():
    print("Fetching members from Mighty Networks...")
    raw_members = fetch_all_members()
    print(f"\nTotal members fetched: {len(raw_members)}")
    print("Geocoding locations...")

    map_members = []
    placed_by_location = 0
    placed_by_timezone = 0
    skipped = 0

    for m in raw_members:
        location = (m.get("location") or "").strip()
        tz = m.get("time_zone", "")
        full_name = f"{m.get('first_name', '')} {m.get('last_name', '')}".strip()

        # Try exact location first
        coords = geocode_city(location) if location else None

        # Fall back to timezone if no location
        if not coords:
            coords = coords_from_timezone(tz)
            if coords:
                placed_by_timezone += 1
            else:
                skipped += 1
        else:
            placed_by_location += 1

        if coords:
            map_members.append({
                "name": full_name or "Unknown",
                "location": location,  # may be empty for timezone-placed members
                "profile_url": m.get("permalink", f"https://community.theartofeducation.edu/members/{m.get('id')}"),
                "avatar": m.get("avatar", ""),
                "bio": m.get("bio", ""),
                "lat": coords["lat"],
                "lng": coords["lng"]
            })

    print(f"\n✅ {len(map_members)} members placed on map")
    print(f"   📍 {placed_by_location} placed by exact location")
    print(f"   🌍 {placed_by_timezone} placed by timezone (approximate)")
    print(f"⚠️  {skipped} members skipped (no location or timezone)")

    with open("members.json", "w") as f:
        json.dump(map_members, f, indent=2)
    print("💾 Saved to members.json")

if __name__ == "__main__":
    build_map_data()