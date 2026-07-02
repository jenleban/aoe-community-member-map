import requests
import json
import time
import os
import re
import random

MIGHTY_API_TOKEN = os.environ["MIGHTY_API_TOKEN"]
NETWORK_ID = "14221297"
BASE_URL = "https://api.mn.co/admin/v1/networks/" + NETWORK_ID
HEADERS = {
    "Authorization": "Bearer " + MIGHTY_API_TOKEN,
    "User-Agent": "curl/7.88.1"
}
geocode_cache = {}

US_STATE_NAMES = [
    'Alabama','Alaska','Arizona','Arkansas','California','Colorado',
    'Connecticut','Delaware','Florida','Georgia','Hawaii','Idaho',
    'Illinois','Iowa','Kansas','Kentucky','Louisiana','Maine',
    'Maryland','Massachusetts','Michigan','Minnesota','Mississippi',
    'Missouri','Montana','Nebraska','Nevada','New Hampshire',
    'New Jersey','New Mexico','New York','North Carolina','North Dakota',
    'Ohio','Oklahoma','Oregon','Pennsylvania','Rhode Island',
    'South Carolina','South Dakota','Tennessee','Texas','Utah',
    'Vermont','Virginia','Washington','West Virginia','Wisconsin','Wyoming'
]

STATE_CENTERS = {
    "AL":(32.779,-86.829),"AK":(64.069,-153.369),"AZ":(34.274,-111.660),
    "AR":(34.894,-92.443),"CA":(37.184,-119.470),"CO":(38.997,-105.548),
    "CT":(41.622,-72.727),"DE":(38.990,-75.505),"FL":(28.630,-82.450),
    "GA":(32.642,-83.443),"HI":(20.293,-156.374),"ID":(44.351,-114.613),
    "IL":(40.042,-89.197),"IN":(39.894,-86.282),"IA":(42.075,-93.496),
    "KS":(38.494,-98.380),"KY":(37.535,-85.302),"LA":(31.069,-91.997),
    "ME":(45.370,-69.243),"MD":(39.055,-76.791),"MA":(42.260,-71.808),
    "MI":(44.347,-85.410),"MN":(46.281,-94.305),"MS":(32.736,-89.668),
    "MO":(38.357,-92.458),"MT":(46.880,-110.363),"NE":(41.538,-99.795),
    "NV":(39.329,-116.631),"NH":(43.681,-71.581),"NJ":(40.191,-74.673),
    "NM":(34.407,-106.113),"NY":(42.954,-75.527),"NC":(35.556,-79.388),
    "ND":(47.450,-100.466),"OH":(40.286,-82.794),"OK":(35.589,-97.494),
    "OR":(43.934,-120.558),"PA":(40.878,-77.800),"RI":(41.676,-71.556),
    "SC":(33.917,-80.896),"SD":(44.444,-100.226),"TN":(35.858,-86.351),
    "TX":(31.476,-99.331),"UT":(39.321,-111.094),"VT":(44.069,-72.666),
    "VA":(37.522,-78.854),"WA":(47.383,-120.447),"WV":(38.641,-80.623),
    "WI":(44.624,-89.994),"WY":(42.996,-107.551),"DC":(38.907,-77.037),
}

TIMEZONE_CENTERS = {
    "America/New_York":(40.7128,-74.0060),
    "America/Chicago":(41.8781,-87.6298),
    "America/Denver":(39.7392,-104.9903),
    "America/Los_Angeles":(34.0522,-118.2437),
    "America/Phoenix":(33.4484,-112.0740),
    "America/Anchorage":(61.2181,-149.9003),
    "Pacific/Honolulu":(21.3069,-157.8583),
    "America/Indiana/Indianapolis":(39.7684,-86.1581),
    "America/Detroit":(42.3314,-83.0458),
    "America/Kentucky/Louisville":(38.2527,-85.7585),
    "America/Toronto":(43.6532,-79.3832),
    "America/Vancouver":(49.2827,-123.1207),
    "America/Edmonton":(53.5461,-113.4938),
    "America/Winnipeg":(49.8951,-97.1384),
    "America/Halifax":(44.6488,-63.5752),
    "Europe/London":(51.5074,-0.1278),
    "Europe/Paris":(48.8566,2.3522),
    "Australia/Sydney":(-33.8688,151.2093),
    "Asia/Tokyo":(35.6762,139.6503),
}

def load_state_lookup(path="state_lookup.json"):
    if not os.path.exists(path):
        print("  Warning: state_lookup.json not found")
        return {}
    with open(path) as f:
        data = json.load(f)
    print("  Loaded state lookup: " + str(len(data)) + " member -> state mappings")
    return data

def geocode_location(location_str):
    if not location_str or location_str in geocode_cache:
        return geocode_cache.get(location_str)
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location_str, "format": "json", "limit": 1},
            headers={"User-Agent": "aoeu-community-map/1.0 (jenniferleban@theartofeducation.edu)"},
            timeout=10
        )
        results = resp.json()
        if results:
            coords = (float(results[0]["lat"]), float(results[0]["lon"]))
            geocode_cache[location_str] = coords
            time.sleep(1)
            return coords
    except Exception:
        pass
    return None

def jitter(lat, lng, spread=0.8):
    return (lat + random.uniform(-spread, spread),
            lng + random.uniform(-spread, spread))

def geocode_by_state(state_code):
    center = STATE_CENTERS.get(state_code.upper())
    if center:
        return jitter(center[0], center[1], spread=0.8)
    return None

def geocode_by_timezone(tz):
    center = TIMEZONE_CENTERS.get(tz)
    if center:
        return jitter(center[0], center[1], spread=2.0)
    return None

def extract_location_from_bio(bio):
    if not bio:
        return None
    m = re.search(r'\b([A-Z][a-zA-Z .]+),\s*([A-Z]{2})\b', bio)
    if m:
        return m.group(0)
    for state in US_STATE_NAMES:
        if state in bio:
            return state
    return None

def fetch_all_members():
    members = []
    url = BASE_URL + "/members?per_page=100"
    page = 0
    while url:
        page += 1
        resp = requests.get(url, headers=HEADERS, timeout=30)
        print("  Page " + str(page) + " status: " + str(resp.status_code))
        if resp.status_code != 200:
            print("  Error: " + resp.text[:500])
            break
        data = resp.json()
        if page == 1:
            print("  Response keys: " + str(list(data.keys())))
        batch = data.get("items", [])
        if not batch:
            print("  Empty batch on page " + str(page) + " -- stopping")
            break
        members.extend(batch)
        print("  Page " + str(page) + ": " + str(len(batch)) + " members (" + str(len(members)) + " total)")
        url = data.get("links", {}).get("next")
        time.sleep(0.5)
    return members

def main():
    print("=== AOEU Member Map: fetch_members.py ===\n")

    print("[1/3] Loading supplementary state lookup...")
    state_lookup = load_state_lookup("state_lookup.json")

    print("\n[2/3] Fetching members from Mighty Networks API...")
    raw_members = fetch_all_members()
    print("  Total members fetched: " + str(len(raw_members)))

    print("\n[3/3] Geocoding members...")
    output = []
    stats = {"location":0,"bio":0,"state_lookup":0,"timezone":0,"skipped":0}

    for m in raw_members:
        member_id   = str(m.get("id",""))
        location    = (m.get("location") or "").strip()
        bio         = (m.get("bio") or "").strip()
        timezone    = (m.get("time_zone") or "").strip()
        name        = (m.get("first_name","") + " " + m.get("last_name","")).strip()
        profile_url = m.get("permalink","")
        avatar      = m.get("avatar","")
        lat = lng = None
        method = None

        if location:
            coords = geocode_location(location)
            if coords:
                lat, lng = coords
                method = "location"

        if lat is None:
            bio_loc = extract_location_from_bio(bio)
            if bio_loc:
                coords = geocode_location(bio_loc)
                if coords:
                    lat, lng = coords
                    method = "bio"

        if lat is None and member_id in state_lookup:
            coords = geocode_by_state(state_lookup[member_id])
            if coords:
                lat, lng = coords
                method = "state_lookup"

        if lat is None and timezone:
            coords = geocode_by_timezone(timezone)
            if coords:
                lat, lng = coords
                method = "timezone"

        if lat is None:
            stats["skipped"] += 1
            continue

        stats[method] += 1
        output.append({
            "id":member_id,
            "name":name,
            "location":location or state_lookup.get(member_id,""),
            "profile_url":profile_url,
            "avatar":avatar,
            "bio":bio[:300] if bio else "",
            "lat":round(lat,5),
            "lng":round(lng,5),
            "geo_method":method,
        })

    with open("members.json","w") as f:
        json.dump(output, f, indent=2)

    total = len(raw_members)
    total_placed = len(output)
    print("\n" + "="*46)
    print("  Members fetched:           " + str(total))
    print("  Placed by location field:  " + str(stats["location"]))
    print("  Placed by bio extraction:  " + str(stats["bio"]))
    print("  Placed by state lookup:    " + str(stats["state_lookup"]) + "  <- NEW")
    print("  Placed by timezone:        " + str(stats["timezone"]))
    print("  Skipped (no data):         " + str(stats["skipped"]))
    print("  " + "-"*42)
    if total > 0:
        print("  Total placed: " + str(total_placed) + " (" + str(round(total_placed/total*100,1)) + "%)")
    else:
        print("  Total placed: " + str(total_placed))
    print("  members.json written")
    print("="*46)

if __name__ == "__main__":
    main()