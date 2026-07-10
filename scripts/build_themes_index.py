#!/usr/bin/env python3
"""build_themes_index.py

Scans /data/themes/*.geojson and writes /data/themes/index.json, a plain
list of filenames. index.html fetches this manifest (no directory listing
is possible from a static file server) to discover theme layers, so this
script is a data step -- not a build step for the site itself -- and must
be re-run whenever a theme file is added or removed.
"""
import glob
import json
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEMES_DIR = os.path.join(ROOT_DIR, "data", "themes")


def main():
    files = sorted(
        os.path.basename(p) for p in glob.glob(os.path.join(THEMES_DIR, "*.geojson"))
    )
    out_path = os.path.join(THEMES_DIR, "index.json")
    with open(out_path, "w") as f:
        json.dump({"files": files}, f, indent=2)
    print(f"wrote {out_path}: {files}")


if __name__ == "__main__":
    main()
