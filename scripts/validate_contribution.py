#!/usr/bin/env python3
"""validate_contribution.py -- shared, PC-agnostic

The CI gate (and the tool a contributor/reviewer runs locally before
opening a PR) for anything landing in pcs/<id>/data/themes/*.geojson.

Checks, per feature, in this order (stops reporting further checks on a
feature once one hard-fails, so the error list stays readable):

  1. Structural validity against schema/feature.schema.json (required
     properties present, correct types/enums) -- hard fail.
  2. status_tag exists in this PC's theme_colors.json for that theme --
     hard fail. (A genuinely new tag must be added to theme_colors.json
     in the same PR, not invented silently.)
  3. Geometry falls within this PC's boundary polygon (the PC outline
     feature in boundary.geojson) -- hard fail. Never trust a claimed
     location without checking it's actually in the constituency.
  4. Optional theme-specific structured fields (schema/themes/<theme>.
     schema.json), if present on the feature -- soft warning only, since
     these are recommended, not required.

Usage:
    python3 validate_contribution.py --pc new-delhi
    python3 validate_contribution.py --pc new-delhi --theme water
    python3 validate_contribution.py --pc new-delhi --file pcs/new-delhi/data/themes/water.geojson

Exit code 0 = no hard failures (warnings don't affect exit code).
Exit code 1 = at least one hard failure.
"""
import argparse
import glob
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(REPO_ROOT, "schema")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def point_in_ring(lon, lat, ring):
    """Standard ray-casting point-in-polygon test."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def point_in_geometry(lon, lat, geom):
    if geom["type"] == "Polygon":
        rings = geom["coordinates"]
        if not point_in_ring(lon, lat, rings[0]):
            return False
        return not any(point_in_ring(lon, lat, hole) for hole in rings[1:])
    if geom["type"] == "MultiPolygon":
        return any(point_in_geometry(lon, lat, {"type": "Polygon", "coordinates": poly}) for poly in geom["coordinates"])
    return False


# Roughly degrees-to-metres at Indian latitudes, good enough for a tolerance check.
_METRES_PER_DEG_LAT = 111_000
BOUNDARY_TOLERANCE_M = 300  # AC-level and PC-level shapefiles are digitized separately
                             # and don't perfectly nest at shared edges even when they
                             # logically should -- this tolerance absorbs that, without
                             # being loose enough to accept a point that's actually in a
                             # different part of the city (which is typically km away).


def point_to_segment_distance_m(lon, lat, x1, y1, x2, y2):
    mlat = _METRES_PER_DEG_LAT
    mlon = _METRES_PER_DEG_LAT * abs(__import__("math").cos(__import__("math").radians(lat)))
    px, py = lon * mlon, lat * mlat
    ax, ay = x1 * mlon, y1 * mlat
    bx, by = x2 * mlon, y2 * mlat
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5


def distance_to_ring_m(lon, lat, ring):
    return min(point_to_segment_distance_m(lon, lat, *ring[i], *ring[i + 1]) for i in range(len(ring) - 1))


def point_near_geometry(lon, lat, geom, tolerance_m=BOUNDARY_TOLERANCE_M):
    """True if inside, or within tolerance_m of the outer boundary -- absorbs the
    normal sliver mismatch between independently-digitized shapefile layers."""
    if point_in_geometry(lon, lat, geom):
        return True
    if geom["type"] == "Polygon":
        return distance_to_ring_m(lon, lat, geom["coordinates"][0]) <= tolerance_m
    if geom["type"] == "MultiPolygon":
        return any(distance_to_ring_m(lon, lat, poly[0]) <= tolerance_m for poly in geom["coordinates"])
    return False


def all_coords(geometry):
    """Flatten any geometry's coordinates down to a list of [lon, lat] points,
    for checking that every vertex of a line/polygon (not just its centroid)
    falls inside the PC boundary."""
    pts = []
    def rec(x):
        if isinstance(x[0], (int, float)):
            pts.append(x)
        else:
            for y in x:
                rec(y)
    rec(geometry["coordinates"])
    return pts


# --- minimal, purpose-built JSON Schema subset validator (stdlib only) -----
# Supports exactly what schema/*.json actually use: type, const, enum,
# required, properties, pattern, format:uri, minLength/maxLength,
# minimum/maximum. Not a general JSON Schema implementation.

def validate_against_schema(instance, schema, path, errors):
    if "const" in schema:
        if instance != schema["const"]:
            errors.append(f"{path}: expected constant {schema['const']!r}, got {instance!r}")
        return
    if "enum" in schema:
        if instance not in schema["enum"]:
            errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")
        return
    t = schema.get("type")
    if t == "object":
        if not isinstance(instance, dict):
            errors.append(f"{path}: expected an object, got {type(instance).__name__}")
            return
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")
        for key, subschema in schema.get("properties", {}).items():
            if key in instance:
                validate_against_schema(instance[key], subschema, f"{path}.{key}", errors)
    elif t == "string":
        if not isinstance(instance, str):
            errors.append(f"{path}: expected a string, got {type(instance).__name__}")
            return
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.match(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match required pattern {schema['pattern']}")
        if schema.get("format") == "uri" and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", instance) and instance != "no URL -- see _note":
            errors.append(f"{path}: {instance!r} doesn't look like a URL (must start with a scheme like https://, or be exactly 'no URL -- see _note')")
    elif t == "number":
        if not isinstance(instance, (int, float)) or isinstance(instance, bool):
            errors.append(f"{path}: expected a number, got {type(instance).__name__}")
            return
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} is below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} is above maximum {schema['maximum']}")
    elif t == "boolean":
        if not isinstance(instance, bool):
            errors.append(f"{path}: expected a boolean, got {type(instance).__name__}")


def validate_feature_structure(feature, base_schema):
    errors = []
    validate_against_schema(feature, base_schema, "feature", errors)
    return errors


def validate_theme_fields(props, theme_schema):
    """Soft check: only reports fields that ARE present but malformed --
    never complains about a field being absent, since these are optional."""
    warnings = []
    for key, subschema in theme_schema.get("properties", {}).items():
        if key in props:
            validate_against_schema(props[key], subschema, f"properties.{key}", warnings)
    return warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pc", required=True, help="PC id, e.g. new-delhi")
    ap.add_argument("--theme", default=None, help="only validate this one theme file")
    ap.add_argument("--file", default=None, help="only validate this one specific .geojson file")
    args = ap.parse_args()

    pc_dir = os.path.join(REPO_ROOT, "pcs", args.pc)
    themes_dir = os.path.join(pc_dir, "data", "themes")
    theme_colors_path = os.path.join(pc_dir, "theme_colors.json")
    boundary_path = os.path.join(pc_dir, "data", "boundary.geojson")

    if not os.path.isdir(pc_dir):
        print(f"ERROR: no such PC folder: {pc_dir}")
        sys.exit(1)

    base_schema = load_json(os.path.join(SCHEMA_DIR, "feature.schema.json"))
    theme_colors = load_json(theme_colors_path) if os.path.exists(theme_colors_path) else {}

    pc_polygon = None
    if os.path.exists(boundary_path):
        boundary = load_json(boundary_path)
        pc_feat = next((f for f in boundary["features"] if f["properties"].get("feature_type") == "parliamentary_constituency"), None)
        if pc_feat:
            pc_polygon = pc_feat["geometry"]
    if pc_polygon is None:
        print(f"WARNING: no PC outline found in {boundary_path} -- skipping the in-boundary geometry check entirely")

    if args.file:
        files = [args.file]
    elif args.theme:
        files = [os.path.join(themes_dir, f"{args.theme}.geojson")]
    else:
        files = sorted(glob.glob(os.path.join(themes_dir, "*.geojson")))
        files = [f for f in files if not f.endswith("index.json")]

    total_features = 0
    total_hard_fails = 0
    total_warnings = 0

    for path in files:
        if not os.path.exists(path):
            print(f"ERROR: {path} does not exist")
            total_hard_fails += 1
            continue
        theme = os.path.splitext(os.path.basename(path))[0]
        theme_schema_path = os.path.join(SCHEMA_DIR, "themes", f"{theme}.schema.json")
        theme_schema = load_json(theme_schema_path) if os.path.exists(theme_schema_path) else None
        allowed_tags = set(theme_colors.get(theme, {}).keys())

        gj = load_json(path)
        features = gj.get("features", [])
        print(f"\n=== {os.path.relpath(path, REPO_ROOT)} ({len(features)} features) ===")

        for i, feat in enumerate(features):
            total_features += 1
            fname = (feat.get("properties") or {}).get("name", f"feature[{i}]")
            struct_errors = validate_feature_structure(feat, base_schema)
            if struct_errors:
                total_hard_fails += 1
                print(f"  FAIL {fname!r}:")
                for e in struct_errors:
                    print(f"    - {e}")
                continue  # don't pile on further checks once structurally broken

            props = feat["properties"]

            if props.get("theme") != theme:
                total_hard_fails += 1
                print(f"  FAIL {fname!r}: properties.theme is {props.get('theme')!r}, expected {theme!r} (must match the filename)")
                continue

            if allowed_tags and props["status_tag"] not in allowed_tags:
                total_hard_fails += 1
                print(f"  FAIL {fname!r}: status_tag {props['status_tag']!r} is not in theme_colors.json for theme {theme!r} "
                      f"(allowed: {sorted(allowed_tags)}) -- add it there with a color, in the same PR, if it's genuinely new")
                continue

            if pc_polygon is not None:
                pts = all_coords(feat["geometry"])
                outside = [p for p in pts if not point_near_geometry(p[0], p[1], pc_polygon)]
                if outside:
                    total_hard_fails += 1
                    print(f"  FAIL {fname!r}: {len(outside)}/{len(pts)} vertex(es) fall outside this PC's boundary "
                          f"(beyond the {BOUNDARY_TOLERANCE_M}m tolerance) (e.g. {outside[0]}) -- geometry must be "
                          f"within the constituency")
                    continue

            if props["_status"] == "ok" and "_contributed_by" in props:
                print(f"  WARN {fname!r}: _status is 'ok' on a contributed feature -- confirm a reviewer actually "
                      f"independently corroborated this, rather than the contributor self-certifying it")
                total_warnings += 1

            if props["geometry_basis"] == "surveyed" and not props.get("_note"):
                print(f"  WARN {fname!r}: geometry_basis is 'surveyed' with no _note explaining the boundary source -- "
                      f"reviewer should verify this is a real boundary, not a point mislabeled")
                total_warnings += 1

            if theme_schema:
                theme_warnings = validate_theme_fields(props, theme_schema)
                for w in theme_warnings:
                    print(f"  WARN {fname!r}: {w}")
                    total_warnings += 1

            print(f"  OK   {fname!r}")

    print(f"\n{total_features} feature(s) checked, {total_hard_fails} hard failure(s), {total_warnings} warning(s)")
    sys.exit(1 if total_hard_fails else 0)


if __name__ == "__main__":
    main()
