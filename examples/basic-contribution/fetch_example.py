#!/usr/bin/env python3
"""fetch_example.py -- A MINIMAL, COMPLETE, RUNNABLE contribution example.

This is the pattern every fetch_<source>.py script in this project follows,
stripped down to its smallest useful form. Copy this file as a starting
point for a real contribution -- don't copy example_output.geojson, its
claim text is a placeholder, not a real sourced claim.

What this script actually does:
  1. Loads the target PC's boundary polygon (so geocoding never spills
     into a neighbouring constituency).
  2. Geocodes ONE real, unambiguous landmark against that polygon via
     Overpass -- the same lib_geocode.py helper every real fetch script in
     this repo uses.
  3. Builds ONE Feature satisfying every required field in
     schema/feature.schema.json, plus a couple of the public_health
     theme's optional structured fields (schema/themes/public_health.
     schema.json).
  4. Writes it to example_output.geojson in THIS directory -- not into any
     real pcs/<id>/data/themes/ file. This script's output is a teaching
     example, never merged into live data.

Run it yourself:
    python3 fetch_example.py

Then run the validator against it directly:
    python3 ../../scripts/validate_contribution.py --pc new-delhi \\
        --file examples/basic-contribution/example_output.geojson
"""
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(THIS_DIR))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from lib_provenance import now_iso
from lib_geocode import load_pc_poly, geocode_terms_in_poly, best_match

BOUNDARY_PATH = os.path.join(REPO_ROOT, "pcs", "new-delhi", "data", "boundary.geojson")
OUT_PATH = os.path.join(THIS_DIR, "example_output.geojson")


def main():
    # Step 1+2: geocode a real, unambiguous landmark against the actual PC
    # polygon -- never a bounding box (see lib_geocode.py's docstring for
    # why: bounding boxes produce false-positive name collisions with
    # same-named places elsewhere in the city).
    poly = load_pc_poly(BOUNDARY_PATH)
    elements = geocode_terms_in_poly(["Safdarjung Hospital"], poly, batch_size=1, pause_s=0)
    match = best_match("Safdarjung Hospital", elements)
    if not match:
        print("Could not geocode 'Safdarjung Hospital' right now (Overpass may be rate-limited) -- try again in a minute.")
        sys.exit(1)
    print(f"Geocoded: {match['name']!r} at ({match['lat']}, {match['lon']})")

    # Step 3: build one Feature. Every key under "required base fields" is
    # mandatory for ANY theme, in ANY PC -- see schema/feature.schema.json.
    # The two keys under "public_health structured fields" are optional,
    # theme-specific, recommended-not-required -- see
    # schema/themes/public_health.schema.json.
    feature = {
        "type": "Feature",
        "properties": {
            # --- required base fields ---
            "name": "EXAMPLE -- Safdarjung Hospital (replace before submitting)",
            "theme": "public_health",
            "claim": "EXAMPLE CLAIM -- replace with a real, one-line, sourced statement before submitting a PR.",
            "status_tag": "facility_functional",  # must exist in the PC's theme_colors.json for this theme, or be added there in the same PR
            "confidence": "low",  # honest self-rating -- a reviewer may adjust this
            "geometry_basis": "point",  # this is a single location, not a boundary claim
            "_source": "EXAMPLE -- replace with where your claim actually comes from (a document, article, or 'Field observation by <name>, <date>')",
            "_source_url": "https://example.com/replace-with-a-real-source-url",
            "_fetched_at": now_iso(),
            "_status": "needs_verification",  # every contributed feature starts here -- never self-certify "ok"
            # --- optional public_health structured fields (schema/themes/public_health.schema.json) ---
            "facility_type": "hospital",
            "doctor_present": None,  # EXAMPLE: leave fields you don't actually know as null, don't guess
        },
        "geometry": {"type": "Point", "coordinates": [match["lon"], match["lat"]]},
    }

    out = {
        "type": "FeatureCollection",
        "features": [feature],
        "_theme_note": "This is a TEACHING EXAMPLE, not real public_health data -- see fetch_example.py and README.md in this directory.",
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
