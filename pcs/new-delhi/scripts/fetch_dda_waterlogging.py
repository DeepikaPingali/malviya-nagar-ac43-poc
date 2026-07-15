#!/usr/bin/env python3
"""fetch_dda_waterlogging.py -- New Delhi PC only

Source: Delhi Traffic Police's own itemized waterlogging-location list,
published as Appendix III of a DDA public-consultation record. This is
the real underlying list -- not the non-public "445 hotspots" figure that
news coverage cites -- and covers all of NCT Delhi (~162 entries), most of
which are nowhere near this PC.

Method:
  1. Download the PDF, extract text (pdftotext -layout; requires poppler-
     utils -- `brew install poppler` / `apt install poppler-utils`).
  2. Parse each numbered row into a raw location description + a record ID.
  3. Clean each description down to a short core search term (strip
     "Adjacent to" / "Near" / "underpass ... near" style prefixes and
     "Marg"/"Road"/"Chowk" style suffixes) -- OSM name tags are terse,
     the raw DDA descriptions usually aren't.
  4. Batch-geocode the cleaned terms against the actual PC polygon (see
     lib_geocode.py) -- NOT a bounding box, so results outside this PC are
     excluded by construction, not by guesswork about Delhi geography.
  5. Word-boundary match back (never bare substring -- see lib_geocode's
     best_match docstring for why that matters).
  6. Write one Feature per matched term, folding all of that term's
     original DDA row descriptions + record IDs into the claim text.

Matches with a generic/ambiguous OSM name (e.g. "National Museum" for the
term "National", standing in for "Adjacent to National Stadium") are
flagged confidence: medium, _status: needs_verification -- spot-check
these before trusting them.

Usage: python3 fetch_dda_waterlogging.py
(run from this directory; writes ../data/themes/waterlogging.geojson)
"""
import json
import os
import re
import sys
import urllib.request

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PC_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, os.path.join(PC_DIR, "..", "..", "scripts"))
from lib_provenance import stamp_feature_collection, now_iso, STATUS_OK, STATUS_NEEDS_VERIFICATION
from lib_geocode import load_pc_poly, geocode_terms_in_poly, best_match

PDF_URL = "https://dda.gov.in/sites/default/files/qac/APPENDIX%20III06092018.pdf"
SOURCE_LABEL = "Delhi Traffic Police waterlogging-location list, via DDA public-consultation record Appendix III"
BOUNDARY_PATH = os.path.join(PC_DIR, "data", "boundary.geojson")
OUT_PATH = os.path.join(PC_DIR, "data", "themes", "waterlogging.geojson")

# Terms whose best OSM match is generic/ambiguous enough to need a human spot-check
# before being trusted (a landmark name that also matches something unrelated nearby).
LOW_CONFIDENCE_TERMS = {"G.T", "Modi", "National", "Ambedkar", "Ashram"}

# name -> replacement core term, for rows too mangled for the generic cleaner to handle.
OVERRIDES = {
    "Defence Colony- Water logging Found 7/7/15": "Defence Colony",
    "Jangpura- Waterlogging Found 7/7/15": "Jangpura",
    "sardar petal road near DhaulaKuanRoad": "Dhaula Kuan",
    "Ashram Chiwk": "Ashram",
    "Chowk Azad": "Azad Market",
    "Under Minto": "Minto Bridge",
    "Rahim Kahn Marg": "Rahim Khan",
    "Rahim Kahn": "Rahim Khan",
}


def log(msg):
    print(f"[fetch_dda_waterlogging] {msg}")


def download_pdf_text(url):
    tmp_pdf = "/tmp/dda_appendix3.pdf"
    log(f"downloading {url}")
    urllib.request.urlretrieve(url, tmp_pdf)
    tmp_txt = "/tmp/dda_appendix3.txt"
    os.system(f'pdftotext -layout "{tmp_pdf}" "{tmp_txt}"')
    with open(tmp_txt) as f:
        return f.read()


def parse_rows(text):
    rows = []
    for line in text.splitlines():
        m = re.match(r"\s*(\d+)\s+(.+?)\s+(\d*_?\d*)\s*$", line)
        if not m:
            continue
        num, name, wid = m.groups()
        name_clean = re.sub(r"-Waterlogging Found.*$", "", name).strip()
        rows.append({"sn": num, "name": name_clean, "id": wid})
    return rows


def clean_term(name):
    n = re.sub(r"^(Adjacent to|Adjoining|Close to|Near|On|in front of|on|underpass)\s+", "", name, flags=re.I)
    n = re.sub(r"\s+(near|Bus stop|Footover Bridge|Flyover|Bridge|Chowk|Marg|Road|Complex|Stadium|Hospital|University|Metro|Mkt\.?|Cinema.*)$", "", n, flags=re.I).strip()
    n = re.sub(r"\s*_\d+$", "", n)
    return n if n else name


def main():
    text = download_pdf_text(PDF_URL)
    rows = parse_rows(text)
    log(f"parsed {len(rows)} raw rows from the source PDF")

    term_to_rows = {}
    for row in rows:
        cleaned = clean_term(row["name"])
        key = OVERRIDES.get(cleaned, cleaned)
        term_to_rows.setdefault(key, []).append(row)
    terms = [t for t in term_to_rows if len(t.split()) <= 4]  # drop overly long descriptive phrases, won't match any OSM name
    log(f"reduced to {len(terms)} candidate core search terms")

    poly = load_pc_poly(BOUNDARY_PATH)
    log("geocoding against the New Delhi PC polygon (this takes a few minutes, paced to avoid Overpass rate limits)")
    elements = geocode_terms_in_poly(terms, poly)

    fetched_at = now_iso()
    features = []
    for term in terms:
        match = best_match(term, elements)
        if not match:
            continue
        orig_rows = term_to_rows[term]
        descs = " / ".join(sorted(set(r["name"] for r in orig_rows)))
        ids = ", ".join(sorted(set(r["id"] for r in orig_rows if r["id"])))
        low_conf = term in LOW_CONFIDENCE_TERMS
        props = {
            "name": term,
            "theme": "waterlogging",
            "claim": f"Traffic Police-reported waterlogging location: {descs} (record ID(s) {ids}).",
            "status_tag": "waterlogging_hotspot",
            "confidence": "medium" if low_conf else "high",
            "geometry_basis": "point",
            "_source": SOURCE_LABEL,
            "_source_url": PDF_URL,
            "_fetched_at": fetched_at,
            "_status": STATUS_NEEDS_VERIFICATION if low_conf else STATUS_OK,
        }
        if low_conf:
            props["_note"] = "OSM name match is generic/ambiguous for this term -- point may not be the exact traffic-police location; spot-check before relying on it."
        features.append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [match["lon"], match["lat"]]}})

    out = {
        "type": "FeatureCollection",
        "features": features,
        "_theme_note": (
            "Sourced from the Delhi Traffic Police's own itemized waterlogging list (DDA Appendix III), "
            "not the news-reported '445 hotspots' figure (that fuller list isn't public). The source list "
            "covers all of NCT Delhi; shown here is the subset whose named landmark/road could be geocoded "
            "to a real OSM feature within the New Delhi PC boundary via a poly-filtered search."
        ),
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    log(f"wrote {OUT_PATH}: {len(features)} features (of {len(terms)} candidate terms)")


if __name__ == "__main__":
    main()
