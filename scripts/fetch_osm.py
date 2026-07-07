#!/usr/bin/env python3
"""fetch_osm.py

Pulls OpenStreetMap data for the Malviya Nagar AC bounding box via the
Overpass API and writes three toggleable layers:

    data/osm_roads.geojson   -- all highway=* ways
    data/osm_metro.geojson   -- metro stations (railway=station + station=subway)
    data/osm_civic.geojson   -- man_made=water_works, power=substation, and a
                                curated set of civic/public-service amenity
                                values (hospitals, schools, police, etc. --
                                not unfiltered amenity=*, which is dominated
                                by restaurants and ATMs)

The bbox is *derived* from data/boundary.geojson (not hardcoded) so it stays
correct if the boundary is ever replaced with a more authoritative source.

Only stdlib is used (no requests/overpy available on this machine) --
urllib.request talks to the Overpass API directly and a small hand-rolled
converter turns the response into GeoJSON.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_provenance import stamp_feature_collection, now_iso, STATUS_OK, STATUS_UNAVAILABLE

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
BOUNDARY_PATH = os.path.join(DATA_DIR, "boundary.geojson")

OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]
USER_AGENT = "malviya-nagar-poc/0.1 (civic-mapping proof of concept; contact via repo issues)"
TIMEOUT_S = 90


def log(msg):
    print(f"[fetch_osm] {msg}")


def load_bbox():
    with open(BOUNDARY_PATH) as f:
        gj = json.load(f)
    coords = gj["features"][0]["geometry"]["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    # Overpass bbox order is (south, west, north, east)
    return min(lats), min(lons), max(lats), max(lons)


def run_overpass(query):
    """POST an Overpass QL query, trying each mirror in turn. Returns
    (parsed_json, endpoint_used) or (None, None) if every mirror failed."""
    for endpoint in OVERPASS_MIRRORS:
        req = urllib.request.Request(
            endpoint,
            data=f"data={urllib.parse.quote(query)}".encode("utf-8"),
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            log(f"querying {endpoint}")
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                body = resp.read()
            return json.loads(body), endpoint
        except Exception as e:
            log(f"WARNING: {endpoint} failed: {type(e).__name__}: {e}")
            time.sleep(2)
            continue
    return None, None


def element_to_feature(el, skipped_relations):
    """Convert one Overpass 'out geom' element to a GeoJSON Feature.
    Nodes -> Point. Ways -> LineString, or Polygon if the ring is closed.
    Relations are skipped (not fabricated) and counted so it's visible in
    provenance rather than silently dropping data."""
    tags = el.get("tags", {})
    props = dict(tags)
    props["_osm_type"] = el["type"]
    props["_osm_id"] = el["id"]

    if el["type"] == "node":
        geometry = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
    elif el["type"] == "way":
        geom = el.get("geometry")
        if not geom:
            return None
        ring = [[pt["lon"], pt["lat"]] for pt in geom]
        if len(ring) >= 4 and ring[0] == ring[-1]:
            geometry = {"type": "Polygon", "coordinates": [ring]}
        else:
            geometry = {"type": "LineString", "coordinates": ring}
    else:
        skipped_relations.append(el["id"])
        return None

    return {"type": "Feature", "properties": props, "geometry": geometry}


def elements_to_feature_collection(elements):
    skipped_relations = []
    features = []
    for el in elements:
        feature = element_to_feature(el, skipped_relations)
        if feature is not None:
            features.append(feature)
    return {"type": "FeatureCollection", "features": features}, skipped_relations


def fetch_layer(name, query, out_filename):
    log(f"fetching layer '{name}'")
    result, endpoint = run_overpass(query)
    fetched_at = now_iso()

    os.makedirs(RAW_DIR, exist_ok=True)
    out_path = os.path.join(DATA_DIR, out_filename)

    if result is None:
        log(f"ERROR: all Overpass mirrors failed for layer '{name}' -- writing empty layer, marked unavailable")
        empty = {"type": "FeatureCollection", "features": []}
        stamp_feature_collection(
            empty,
            source="OpenStreetMap via Overpass API (all mirrors unreachable)",
            status=STATUS_UNAVAILABLE,
            fetched_at=fetched_at,
            note="Every configured Overpass mirror failed. This layer is empty, not comprehensive -- re-run fetch_osm.py.",
        )
        with open(out_path, "w") as f:
            json.dump(empty, f, indent=2)
        return

    raw_path = os.path.join(RAW_DIR, f"osm_{name}_raw.json")
    with open(raw_path, "w") as f:
        json.dump(result, f)

    elements = result.get("elements", [])
    fc, skipped_relations = elements_to_feature_collection(elements)

    note = f"Overpass bbox query, {len(elements)} raw elements ({len(fc['features'])} node/way features kept)."
    if skipped_relations:
        note += f" {len(skipped_relations)} relation(s) skipped (multipolygon reconstruction not implemented) -- see osm_ids {skipped_relations[:10]}{'...' if len(skipped_relations) > 10 else ''}."

    stamp_feature_collection(
        fc,
        source=f"OpenStreetMap contributors via Overpass API ({endpoint})",
        status=STATUS_OK,
        fetched_at=fetched_at,
        note=note,
    )

    with open(out_path, "w") as f:
        json.dump(fc, f, indent=2)
    log(f"wrote {out_path} ({len(fc['features'])} features)")


def main():
    south, west, north, east = load_bbox()
    bbox = f"{south},{west},{north},{east}"
    log(f"AC bbox (derived from boundary.geojson): {bbox}")

    roads_query = f"""
    [out:json][timeout:60];
    (
      way["highway"]({bbox});
    );
    out geom;
    """

    metro_query = f"""
    [out:json][timeout:60];
    (
      nwr["railway"="station"]["station"="subway"]({bbox});
      nwr["station"="subway"]({bbox});
    );
    out geom;
    """

    # amenity=* is deliberately narrowed to civic/public-service values --
    # unfiltered amenity=* is dominated by restaurants, cafes, ATMs, and
    # benches, which swamp an actual "civic assets" layer.
    civic_amenity_values = "|".join([
        "hospital", "clinic", "doctors", "dentist", "pharmacy",
        "school", "college", "university", "kindergarten", "library",
        "townhall", "police", "fire_station", "courthouse", "post_office",
        "community_centre", "social_facility", "public_building",
        "marketplace", "toilets", "drinking_water", "waste_transfer_station",
        "grave_yard", "crematorium", "shelter", "ambulance_station",
    ])
    civic_query = f"""
    [out:json][timeout:60];
    (
      nwr["man_made"="water_works"]({bbox});
      nwr["power"="substation"]({bbox});
      nwr["amenity"~"^({civic_amenity_values})$"]({bbox});
    );
    out geom;
    """

    fetch_layer("roads", roads_query, "osm_roads.geojson")
    fetch_layer("metro", metro_query, "osm_metro.geojson")
    fetch_layer("civic", civic_query, "osm_civic.geojson")


if __name__ == "__main__":
    main()
