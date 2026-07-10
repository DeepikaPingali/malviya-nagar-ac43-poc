#!/usr/bin/env python3
"""validate_themes.py

Checks every /data/themes/*.geojson feature for the required schema
(name, theme, claim, status_tag, confidence, geometry_basis, _source,
_source_url, _fetched_at, _status) and a valid geometry, then prints a
summary table. Run after editing or adding a theme file.
"""
import glob
import json
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT_DIR, "data", "themes")

REQUIRED = ["name", "theme", "claim", "status_tag", "confidence",
            "geometry_basis", "_source", "_source_url", "_fetched_at", "_status"]
VALID_GEOMETRY_BASIS = {"surveyed", "approximate", "point"}


def main():
    rows = []
    problems = []
    for path in sorted(glob.glob(os.path.join(THEMES_DIR, "*.geojson"))):
        theme = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            gj = json.load(f)
        features = gj.get("features", [])
        tiers = {"surveyed": 0, "approximate": 0, "point": 0}
        needs_verification = 0
        for feat in features:
            props = feat.get("properties", {})
            name = props.get("name", "<unnamed>")
            missing = [k for k in REQUIRED if not props.get(k)]
            if missing:
                problems.append(f"{theme} / {name}: missing {missing}")
            geom = feat.get("geometry")
            if not geom or "type" not in geom or "coordinates" not in geom:
                problems.append(f"{theme} / {name}: invalid/missing geometry")
            basis = props.get("geometry_basis")
            if basis not in VALID_GEOMETRY_BASIS:
                problems.append(f"{theme} / {name}: unrecognized geometry_basis '{basis}'")
            else:
                tiers[basis] += 1
            if basis == "approximate":
                problems.append(f"{theme} / {name}: geometry_basis=approximate -- REVIEW (hand-drawn, not a real boundary)")
            if not props.get("_source") or not props.get("_source_url"):
                problems.append(f"{theme} / {name}: missing _source or _source_url")
            if props.get("_status") == "needs_verification":
                needs_verification += 1
        rows.append((theme, len(features), tiers, needs_verification))

    print(f"{'theme':<16} {'features':>8} {'surveyed':>9} {'approx':>7} {'point':>6} {'needs_verif':>12}")
    for theme, n, tiers, nv in rows:
        print(f"{theme:<16} {n:>8} {tiers['surveyed']:>9} {tiers['approximate']:>7} {tiers['point']:>6} {nv:>12}")

    print()
    if problems:
        print(f"{len(problems)} item(s) flagged for review:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("No schema problems found.")


if __name__ == "__main__":
    main()
