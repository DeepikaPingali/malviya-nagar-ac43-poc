#!/usr/bin/env python3
"""new_pc_scaffold.py -- shared, PC-agnostic

Bootstraps a fresh pcs/<id>/ folder so onboarding a new PC doesn't start
from a blank page. Does NOT fetch the boundary or any data -- that's a
separate, deliberate step (run fetch_boundary_pc.py next, then fetch_osm.py)
so this script never makes a network call.

Usage:
    python3 new_pc_scaffold.py --id mumbai-north --display-name "Mumbai North" \\
        --state Maharashtra --shapefile-state MAHARASHTRA --shapefile-pc-name "MUMBAI NORTH"

Creates:
    pcs/<id>/config.json          -- filled in with what you passed; map_center/
                                      map_zoom are placeholders, fix after boundary.geojson
                                      exists (or just let fitBounds handle it)
    pcs/<id>/theme_colors.json    -- empty {} ; you add theme -> status_tag -> color
                                      entries as you populate each theme (see
                                      schema/themes/*.schema.json for the standard set)
    pcs/<id>/scripts/             -- empty, ready for this PC's own fetch_<source>.py scripts
    pcs/<id>/data/themes/         -- one empty scaffold FeatureCollection per standard
                                      theme (see schema/themes/), each with a _theme_note
                                      explaining it's not populated yet -- NOT fabricated
                                      placeholder data, zero features until real, sourced
                                      claims exist
    pcs/index.json                -- updated to register the new PC (only if not already there)

After running this, the real next steps are:
    1. python3 scripts/fetch_boundary_pc.py --state <STATE> --pc-name "<PC NAME>" --out-dir pcs/<id>
    2. python3 scripts/fetch_osm.py --out-dir pcs/<id>
    3. python3 scripts/build_themes_index.py --out-dir pcs/<id>
    4. Start writing pcs/<id>/scripts/fetch_<source>.py scripts and filling in the
       theme files for real, one sourced claim at a time.
"""
import argparse
import glob
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_THEMES_DIR = os.path.join(REPO_ROOT, "schema", "themes")

STANDARD_THEME_NOTES = {
    "land_housing": "Not yet populated for this PC. Land/housing claims should be sourced from this PC's local regularisation scheme (equivalent to Delhi's PM-UDAY) plus field observation.",
    "water": "Not yet populated for this PC. Water-supply claims should be sourced from the local water utility's own published plans/data, plus field observation.",
    "sanitation": "Not yet populated for this PC. Sanitation claims should be sourced from the local sewerage authority plus field observation.",
    "waterlogging": "Not yet populated for this PC. Waterlogging claims should be sourced from the local traffic police / PWD's own hotspot records where they exist.",
    "air": "Not yet populated for this PC. Air-quality claims should be sourced from CPCB/state pollution-control-board CAAQMS stations and any local point-source inventory.",
    "enforcement": "Not yet populated for this PC.",
    "roads_congestion": "Not yet populated for this PC.",
    "solid_waste": "Not yet populated for this PC.",
    "public_health": "Not yet populated for this PC.",
}


def log(msg):
    print(f"[new_pc_scaffold] {msg}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", required=True, help="kebab-case PC id, e.g. mumbai-north")
    ap.add_argument("--display-name", required=True, help="e.g. 'Mumbai North'")
    ap.add_argument("--state", required=True, help="display state name, e.g. Maharashtra")
    ap.add_argument("--shapefile-state", required=True, help="ST_NAME in the datameet/maps shapefile, ALL CAPS, e.g. MAHARASHTRA")
    ap.add_argument("--shapefile-pc-name", required=True, help="PC_NAME in the shapefile, ALL CAPS, e.g. 'MUMBAI NORTH'")
    args = ap.parse_args()

    pc_dir = os.path.join(REPO_ROOT, "pcs", args.id)
    if os.path.exists(pc_dir):
        log(f"ERROR: {pc_dir} already exists -- refusing to overwrite")
        raise SystemExit(1)

    os.makedirs(os.path.join(pc_dir, "scripts"))
    os.makedirs(os.path.join(pc_dir, "data", "themes"))

    config = {
        "id": args.id,
        "display_name": args.display_name,
        "shapefile_state": args.shapefile_state,
        "shapefile_pc_name": args.shapefile_pc_name,
        "map_center": [20.5937, 78.9629],  # placeholder: geographic center of India: fix once boundary.geojson exists
        "map_zoom": 12,
    }
    with open(os.path.join(pc_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)
    log(f"wrote {pc_dir}/config.json")

    with open(os.path.join(pc_dir, "theme_colors.json"), "w") as f:
        json.dump({}, f, indent=2)
    log(f"wrote {pc_dir}/theme_colors.json (empty -- add theme -> status_tag -> color as you populate each theme)")

    theme_names = sorted(
        os.path.basename(p)[: -len(".schema.json")]
        for p in glob.glob(os.path.join(SCHEMA_THEMES_DIR, "*.schema.json"))
    )
    for theme in theme_names:
        note = STANDARD_THEME_NOTES.get(theme, "Not yet populated for this PC.")
        scaffold = {"type": "FeatureCollection", "features": [], "_theme_note": note}
        with open(os.path.join(pc_dir, "data", "themes", f"{theme}.geojson"), "w") as f:
            json.dump(scaffold, f, indent=2)
    log(f"wrote {len(theme_names)} empty theme scaffolds: {theme_names}")

    index_path = os.path.join(REPO_ROOT, "pcs", "index.json")
    registry = {"pcs": []}
    if os.path.exists(index_path):
        with open(index_path) as f:
            registry = json.load(f)
    if not any(p["id"] == args.id for p in registry["pcs"]):
        registry["pcs"].append({"id": args.id, "display_name": args.display_name, "state": args.state})
        with open(index_path, "w") as f:
            json.dump(registry, f, indent=2)
        log(f"registered '{args.id}' in {index_path}")
    else:
        log(f"'{args.id}' already registered in {index_path}, left as-is")

    log("")
    log("Next steps:")
    log(f"  1. python3 scripts/fetch_boundary_pc.py --state {args.shapefile_state} --pc-name \"{args.shapefile_pc_name}\" --out-dir pcs/{args.id}")
    log(f"  2. python3 scripts/fetch_osm.py --out-dir pcs/{args.id}")
    log(f"  3. python3 scripts/build_themes_index.py --out-dir pcs/{args.id}")
    log(f"  4. Start writing pcs/{args.id}/scripts/fetch_<source>.py and filling in the theme files")


if __name__ == "__main__":
    main()
