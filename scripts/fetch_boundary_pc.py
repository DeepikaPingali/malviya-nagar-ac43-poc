#!/usr/bin/env python3
"""fetch_boundary_pc.py

Expands data/boundary.geojson from a single assembly constituency (Malviya
Nagar, AC-43) to the full New Delhi parliamentary constituency: all 10
assembly segments plus the PC outline.

Same source as the original single-AC boundary.geojson (datameet/maps,
sparse-cloned at data/raw/datameet-maps) -- just widened to also pull in
parliamentary-constituencies/ and to drop the AC_NAME filter in favour of
PC_NO=4 (matches all 10 segments of this PC in one query).

civic_body / water_distributor are NOT from the shapefile -- they're
manually assigned from public-domain administrative knowledge (which body
governs each segment) and are stamped with their own _status so the front
end can distinguish "this came from the source shapefile" from "this was
added by us and should be spot-checked."
"""
import json
import os
import subprocess
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
from lib_provenance import stamp_feature_collection, now_iso, STATUS_OK, STATUS_NEEDS_VERIFICATION

RAW_DIR = os.path.join(ROOT_DIR, "data", "raw")
DATA_DIR = os.path.join(ROOT_DIR, "data")
CLONE_DIR = os.path.join(RAW_DIR, "datameet-maps")
AC_SHP = os.path.join(CLONE_DIR, "assembly-constituencies", "India_AC.shp")
PC_SHP = os.path.join(CLONE_DIR, "parliamentary-constituencies", "india_pc_2019.shp")

OUT_FINAL = os.path.join(DATA_DIR, "boundary.geojson")

# Manually assigned -- not from the shapefile. Source: user-provided field
# notes (NDMC in the New Delhi/Lutyens segment, Cantonment Board in Delhi
# Cantt, MCD everywhere else in this PC) -- kept here, not fabricated by us.
CIVIC_BODY = {
    "Karol Bagh": "MCD", "Patel Nagar": "MCD", "Moti Nagar": "MCD",
    "Rajinder Nagar": "MCD", "Kasturba Nagar": "MCD", "Malviya Nagar": "MCD",
    "R.K. Puram": "MCD", "Greater Kailash": "MCD",
    "Delhi Cantt": "Cantonment Board",
    "New Delhi": "NDMC",
}
WATER_DISTRIBUTOR = {
    "Delhi Cantt": "Cantonment Board (buys DJB bulk supply; not a DJB distribution zone)",
    "New Delhi": "NDMC (buys DJB bulk supply; not a DJB distribution zone)",
}
DEFAULT_WATER_DISTRIBUTOR = "DJB (direct distribution)"

CIVIC_BODY_NOTE = (
    "civic_body / water_distributor are not from the source shapefile -- manually "
    "assigned from field notes on which body governs/distributes water in each "
    "segment. Geometry provenance is the shapefile; these two fields should be "
    "spot-checked, not treated as surveyed."
)


def log(msg):
    print(f"[fetch_boundary_pc] {msg}")


def run_ogr2ogr(shp_path, where, out_path):
    subprocess.run(
        ["ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-where", where, out_path, shp_path],
        check=True,
    )
    with open(out_path) as f:
        return json.load(f)


def commit_sha():
    return subprocess.run(
        ["git", "-C", CLONE_DIR, "rev-parse", "--short", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def main():
    for required in (AC_SHP, PC_SHP):
        if not os.path.exists(required):
            log(f"ERROR: expected shapefile not found at {required}")
            log("run: git -C data/raw/datameet-maps sparse-checkout set assembly-constituencies parliamentary-constituencies")
            sys.exit(1)

    sha = commit_sha()
    source_label = f"datameet/maps assembly-constituencies/India_AC.shp + parliamentary-constituencies/india_pc_2019.shp (github.com/datameet/maps) @ {sha}"
    fetched_at = now_iso()

    log(f"extracting all 10 AC segments of New Delhi PC (PC_NO=4) from {AC_SHP}")
    ac_gj = run_ogr2ogr(AC_SHP, "ST_NAME = 'DELHI' AND PC_NO = 4", os.path.join(RAW_DIR, "boundary_ac_extracted.geojson"))
    if len(ac_gj["features"]) != 10:
        log(f"ERROR: expected 10 AC features, got {len(ac_gj['features'])} -- refusing to guess, check the filter")
        sys.exit(1)
    log(f"got {len(ac_gj['features'])} AC features")

    log(f"extracting New Delhi PC outline from {PC_SHP}")
    pc_gj = run_ogr2ogr(PC_SHP, "ST_NAME = 'DELHI' AND PC_NAME = 'NEW DELHI'", os.path.join(RAW_DIR, "boundary_pc_extracted.geojson"))
    if len(pc_gj["features"]) != 1:
        log(f"ERROR: expected 1 PC feature, got {len(pc_gj['features'])}")
        sys.exit(1)
    log("got 1 PC outline feature")

    features = []
    for feat in ac_gj["features"]:
        props = feat["properties"]
        # shapefile suffixes reserved-category segments, e.g. "Karol Bagh (SC)" --
        # strip that before matching against the plain names in CIVIC_BODY.
        ac_name = props.get("AC_NAME", "")
        lookup_name = ac_name.split(" (")[0].strip()
        if lookup_name not in CIVIC_BODY:
            log(f"ERROR: no civic_body mapping for AC_NAME='{ac_name}' (lookup_name='{lookup_name}') -- refusing to guess")
            sys.exit(1)
        props["feature_type"] = "assembly_constituency"
        props["civic_body"] = CIVIC_BODY[lookup_name]
        props["water_distributor"] = WATER_DISTRIBUTOR.get(lookup_name, DEFAULT_WATER_DISTRIBUTOR)
        props["_civic_body_note"] = CIVIC_BODY_NOTE
        features.append(feat)

    pc_feat = pc_gj["features"][0]
    pc_feat["properties"]["feature_type"] = "parliamentary_constituency"
    features.append(pc_feat)

    out_gj = {"type": "FeatureCollection", "features": features}
    stamp_feature_collection(
        out_gj,
        source=source_label,
        status=STATUS_NEEDS_VERIFICATION,  # civic_body/water_distributor enrichment isn't from the source
        fetched_at=fetched_at,
        note="Expanded from single-AC (Malviya Nagar) to all 10 segments of the New Delhi PC + PC outline. " + CIVIC_BODY_NOTE,
    )

    with open(OUT_FINAL, "w") as f:
        json.dump(out_gj, f, indent=2)
    log(f"wrote {OUT_FINAL} ({len(features)} features: 10 AC + 1 PC)")


if __name__ == "__main__":
    main()
