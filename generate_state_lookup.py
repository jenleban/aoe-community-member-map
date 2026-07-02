#!/usr/bin/env python3
"""
generate_state_lookup.py  — AOEU Community Member Map
Reads a CSV export of the Members Import Google Sheet and writes state_lookup.json.

state_lookup.json is a supplementary geocoding source for fetch_members.py.
It maps Mighty Networks member_id → US state code (from col_11 / State/Region field),
for members who have a state in BigQuery but no location text in their MN profile.

Usage:
  1. Download the Members Import sheet as CSV (File → Download → CSV)
     OR export from BigQuery using the SQL query at the bottom of this file.
  2. Run: python3 generate_state_lookup.py members_import.csv
  3. Commit the resulting state_lookup.json to the repo.

The lookup only includes US state abbreviations (2-letter codes, e.g. "TX", "CA").
International/provincial entries are intentionally excluded — those members still fall
through to timezone-fallback geocoding, which is appropriate for non-US locations.
"""

import csv
import json
import sys
import os

# All valid US state + DC codes
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}


def extract_state_from_value(value):
    """
    Accept a state/region string and return a clean 2-letter US state code, or None.
    Handles:
      - "TX"              → "TX"
      - "  ca  "          → "CA"   (case-insensitive, strip whitespace)
      - "Chicago, IL"     → "IL"   (city, state format — extract trailing 2-letter code)
      - "Ontario"         → None   (international — skip)
    """
    if not value:
        return None
    v = value.strip()

    # Direct 2-letter match
    if len(v) == 2 and v.upper() in US_STATES:
        return v.upper()

    # "City, ST" pattern — take the trailing 2-letter code
    if "," in v:
        parts = v.rsplit(",", 1)
        candidate = parts[-1].strip()
        if len(candidate) == 2 and candidate.upper() in US_STATES:
            return candidate.upper()

    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_state_lookup.py <members_import.csv>")
        print()
        print("The CSV should be the Members Import sheet export with columns:")
        print("  member_id (col 0), ..., col_7 (location), ..., col_11 (state/region)")
        print()
        print("See the BigQuery SQL at the bottom of this file to export directly.")
        sys.exit(1)

    input_file = sys.argv[1]
    if not os.path.exists(input_file):
        print(f"Error: file not found: {input_file}")
        sys.exit(1)

    state_lookup = {}
    stats = {"total": 0, "has_location": 0, "state_added": 0, "skipped_intl": 0, "skipped_no_state": 0}

    with open(input_file, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)   # skip header row

        # Detect column indices — the sheet has dynamic column names
        # Column layout (0-indexed):
        #   0 = member_id (bigquery_import_last_updated_*)
        #   1 = created_at (col_1)
        #   2 = updated_at (col_2)
        #   3 = email (col_3)
        #   4 = first_name (col_4)
        #   5 = last_name (col_5)
        #   6 = timezone (col_6)
        #   7 = location (col_7)
        #   8 = bio (col_8)
        #   9 = col_9
        #  10 = categories (col_10)
        #  11 = state_region (col_11)
        COL_MEMBER_ID  = 0
        COL_LOCATION   = 7   # col_7
        COL_STATE_REGION = 11  # col_11

        for row in reader:
            if len(row) < 12:
                continue
            stats["total"] += 1

            member_id = row[COL_MEMBER_ID].strip()
            location  = row[COL_LOCATION].strip()    # col_7 — MN location field
            state_raw = row[COL_STATE_REGION].strip() # col_11 — BigQuery state/region

            # Skip the header row if it appears in the data (BigQuery export quirk)
            if member_id.lower().startswith("bigquery_import"):
                continue

            # Only create lookup entries for members WITHOUT a location field.
            # If col_7 is already set, fetch_members.py will geocode them via Nominatim.
            if location:
                stats["has_location"] += 1
                continue

            state = extract_state_from_value(state_raw)
            if state:
                state_lookup[member_id] = state
                stats["state_added"] += 1
            elif state_raw:
                stats["skipped_intl"] += 1   # international / province — skip
            else:
                stats["skipped_no_state"] += 1  # neither field has data

    output_file = "state_lookup.json"
    with open(output_file, "w") as f:
        json.dump(state_lookup, f, indent=2)

    print(f"\n{'='*48}")
    print(f"  Input rows processed:           {stats['total']:>6,}")
    print(f"  Members with location (skipped): {stats['has_location']:>6,}  (handled by Nominatim)")
    print(f"  State codes added to lookup:    {stats['state_added']:>6,}  ← geocodable with state centers")
    print(f"  International/provincial skip:  {stats['skipped_intl']:>6,}  (will use timezone fallback)")
    print(f"  No location data at all:        {stats['skipped_no_state']:>6,}  (will use timezone fallback)")
    print(f"  ──────────────────────────────────────────────")
    print(f"  Written to: {output_file} ✅")
    print(f"{'='*48}")
    print()
    print("Next steps:")
    print("  1. git add state_lookup.json")
    print("  2. git commit -m 'Add state lookup from BigQuery col_11 data'")
    print("  3. git push")
    print("  Then run fetch_members.py — 'Placed by state lookup' count should jump to ~4,600+")


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery SQL to export the Members Import data directly
# (Alternative to downloading from Google Sheets)
#
# Run this in the BigQuery console and download as CSV, then pass to this script.
#
# SELECT
#   member_id,
#   location AS col_7,
#   state_region AS col_11
# FROM `your_project.your_dataset.members`
# WHERE (location IS NULL OR TRIM(location) = '')
#   AND state_region IS NOT NULL AND TRIM(state_region) != ''
# ORDER BY member_id
#
# ─────────────────────────────────────────────────────────────────────────────
