#!/usr/bin/env python3
"""build_themes_index.py -- shared, PC-agnostic

Scans <out-dir>/data/themes/*.geojson and writes
<out-dir>/data/themes/index.json, a plain list of filenames. index.html
fetches this manifest (no directory listing is possible from a static file
server) to discover theme layers, so this script is a data step -- not a
build step for the site itself -- and must be re-run whenever a theme file
is added or removed.

Usage: python3 build_themes_index.py --out-dir pcs/new-delhi
"""
import argparse
import glob
import json
import os


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", required=True, help="PC folder, e.g. pcs/new-delhi")
    args = ap.parse_args()

    themes_dir = os.path.join(os.path.abspath(args.out_dir), "data", "themes")
    files = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(themes_dir, "*.geojson"))
    )
    out_path = os.path.join(themes_dir, "index.json")
    with open(out_path, "w") as f:
        json.dump({"files": files}, f, indent=2)
    print(f"wrote {out_path}: {files}")


if __name__ == "__main__":
    main()
