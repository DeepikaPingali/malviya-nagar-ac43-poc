#!/usr/bin/env python3
"""fetch_boundary_pc.py -- shared, PC-agnostic

Fetches a parliamentary constituency's boundary: all of its assembly
segments plus the PC outline, from datameet/maps (github.com/datameet/maps,
sparse-cloned on first use). Works for any Indian PC, not just New Delhi --
pass --state and --pc-name.

Usage:
    python3 fetch_boundary_pc.py --state DELHI --pc-name "NEW DELHI" --out-dir pcs/new-delhi
    python3 fetch_boundary_pc.py --state MAHARASHTRA --pc-name "MUMBAI NORTH" --out-dir pcs/mumbai-north

Writes <out-dir>/data/boundary.geojson: one feature per assembly segment
(feature_type: "assembly_constituency") plus one PC-outline feature
(feature_type: "parliamentary_constituency").

civic_body / water_distributor enrichment is OPTIONAL and PC-specific --
these are not in the source shapefile. If <out-dir>/civic_body.json exists
(a {"<AC name>": {"civic_body": ..., "water_distributor": ...}} mapping,
hand-authored the same way we did for New Delhi from field notes), it's
applied and stamped with its own _status so the front end can distinguish
"from the source shapefile" from "manually added, spot-check this." If
that config file doesn't exist, the boundary is still written -- just
without that enrichment -- rather than failing. Never guesses these values.
"""
import argparse
import json
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from lib_provenance import stamp_feature_collection, now_iso, STATUS_OK, STATUS_NEEDS_VERIFICATION

REPO_URL = "https://github.com/datameet/maps.git"


def log(msg):
    print(f"[fetch_boundary_pc] {msg}")


def ensure_clone(clone_dir):
    """Sparse-clone (or update) datameet/maps if not already present."""
    if os.path.isdir(os.path.join(clone_dir, ".git")):
        log(f"existing clone found at {clone_dir}, fetching latest master")
        subprocess.run(["git", "-C", clone_dir, "fetch", "--depth", "1", "origin", "master"], check=True)
        subprocess.run(["git", "-C", clone_dir, "checkout", "master"], check=True)
        subprocess.run(["git", "-C", clone_dir, "reset", "--hard", "origin/master"], check=True)
    else:
        log(f"sparse-cloning {REPO_URL} into {clone_dir} (assembly-constituencies/ + parliamentary-constituencies/ only)")
        os.makedirs(os.path.dirname(clone_dir), exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", "--quiet", REPO_URL, clone_dir],
            check=True,
        )
        subprocess.run(["git", "-C", clone_dir, "sparse-checkout", "init", "--cone"], check=True)
        subprocess.run(
            ["git", "-C", clone_dir, "sparse-checkout", "set", "assembly-constituencies", "parliamentary-constituencies"],
            check=True,
        )
        subprocess.run(["git", "-C", clone_dir, "checkout", "master", "--quiet"], check=True)
    sha = subprocess.run(
        ["git", "-C", clone_dir, "rev-parse", "--short", "HEAD"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    log(f"using datameet/maps @ {sha}")
    return sha


def run_ogr2ogr(shp_path, where, out_path):
    subprocess.run(
        ["ogr2ogr", "-f", "GeoJSON", "-t_srs", "EPSG:4326", "-where", where, out_path, shp_path],
        check=True,
    )
    with open(out_path) as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", required=True, help="ST_NAME in the shapefile, e.g. DELHI, MAHARASHTRA")
    ap.add_argument("--pc-name", required=True, help="PC_NAME in the shapefile, e.g. 'NEW DELHI', 'MUMBAI NORTH'")
    ap.add_argument("--out-dir", required=True, help="PC folder to write into, e.g. pcs/new-delhi")
    ap.add_argument("--expected-ac-count", type=int, default=None,
                     help="optional sanity check: fail if the AC count doesn't match")
    args = ap.parse_args()

    out_dir = os.path.abspath(args.out_dir)
    data_dir = os.path.join(out_dir, "data")
    raw_dir = os.path.join(data_dir, "raw")
    clone_dir = os.path.join(raw_dir, "datameet-maps")
    ac_shp = os.path.join(clone_dir, "assembly-constituencies", "India_AC.shp")
    pc_shp = os.path.join(clone_dir, "parliamentary-constituencies", "india_pc_2019.shp")
    out_final = os.path.join(data_dir, "boundary.geojson")
    civic_body_config_path = os.path.join(out_dir, "civic_body.json")

    os.makedirs(raw_dir, exist_ok=True)
    sha = ensure_clone(clone_dir)
    source_label = (
        f"datameet/maps assembly-constituencies/India_AC.shp + "
        f"parliamentary-constituencies/india_pc_2019.shp (github.com/datameet/maps) @ {sha}"
    )
    fetched_at = now_iso()

    log(f"extracting all AC segments of {args.pc_name} ({args.state}) from {ac_shp}")
    ac_gj = run_ogr2ogr(
        ac_shp, f"ST_NAME = '{args.state}' AND PC_NAME = '{args.pc_name}'",
        os.path.join(raw_dir, "boundary_ac_extracted.geojson"),
    )
    if not ac_gj["features"]:
        log("ERROR: 0 AC features matched -- check --state/--pc-name spelling against the shapefile (ST_NAME/PC_NAME are ALL CAPS)")
        sys.exit(1)
    if args.expected_ac_count is not None and len(ac_gj["features"]) != args.expected_ac_count:
        log(f"ERROR: expected {args.expected_ac_count} AC features, got {len(ac_gj['features'])} -- refusing to guess, check the filter")
        sys.exit(1)
    log(f"got {len(ac_gj['features'])} AC features")

    log(f"extracting {args.pc_name} PC outline from {pc_shp}")
    pc_gj = run_ogr2ogr(
        pc_shp, f"ST_NAME = '{args.state}' AND PC_NAME = '{args.pc_name}'",
        os.path.join(raw_dir, "boundary_pc_extracted.geojson"),
    )
    if len(pc_gj["features"]) != 1:
        log(f"ERROR: expected 1 PC feature, got {len(pc_gj['features'])}")
        sys.exit(1)
    log("got 1 PC outline feature")

    civic_body_map, water_distributor_map = {}, {}
    civic_body_note = None
    if os.path.exists(civic_body_config_path):
        with open(civic_body_config_path) as f:
            cfg = json.load(f)
        for ac_name, info in cfg.items():
            civic_body_map[ac_name] = info.get("civic_body")
            water_distributor_map[ac_name] = info.get("water_distributor")
        civic_body_note = (
            f"civic_body / water_distributor are not from the source shapefile -- manually "
            f"assigned in {os.path.basename(civic_body_config_path)} from field notes on which "
            f"body governs/distributes water in each segment. Geometry provenance is the "
            f"shapefile; these two fields should be spot-checked, not treated as surveyed."
        )
        log(f"applying civic_body enrichment from {civic_body_config_path}")
    else:
        log(f"no {civic_body_config_path} found -- writing boundary without civic_body/water_distributor enrichment")

    features = []
    for feat in ac_gj["features"]:
        props = feat["properties"]
        # shapefile suffixes reserved-category segments, e.g. "Karol Bagh (SC)" --
        # strip that before matching against civic_body.json's plain names.
        ac_name = props.get("AC_NAME", "")
        lookup_name = ac_name.split(" (")[0].strip()
        props["feature_type"] = "assembly_constituency"
        if civic_body_map:
            if lookup_name not in civic_body_map:
                log(f"ERROR: {civic_body_config_path} exists but has no entry for AC_NAME='{ac_name}' (lookup_name='{lookup_name}') -- refusing to guess. Add it or remove the config file.")
                sys.exit(1)
            props["civic_body"] = civic_body_map[lookup_name]
            props["water_distributor"] = water_distributor_map.get(lookup_name)
            props["_civic_body_note"] = civic_body_note
        features.append(feat)

    pc_feat = pc_gj["features"][0]
    pc_feat["properties"]["feature_type"] = "parliamentary_constituency"
    features.append(pc_feat)

    out_gj = {"type": "FeatureCollection", "features": features}
    note = f"{len(features) - 1} assembly segments + 1 PC outline for {args.pc_name}."
    if civic_body_note:
        note += " " + civic_body_note
    stamp_feature_collection(
        out_gj,
        source=source_label,
        status=STATUS_NEEDS_VERIFICATION if civic_body_map else STATUS_OK,
        fetched_at=fetched_at,
        note=note,
    )

    with open(out_final, "w") as f:
        json.dump(out_gj, f, indent=2)
    log(f"wrote {out_final} ({len(features)} features: {len(features) - 1} AC + 1 PC)")


if __name__ == "__main__":
    main()
