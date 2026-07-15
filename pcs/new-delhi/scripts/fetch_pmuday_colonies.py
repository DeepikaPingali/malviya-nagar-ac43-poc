#!/usr/bin/env python3
"""fetch_pmuday_colonies.py -- New Delhi PC only

Source: DDA's PM-UDAY notified list of 1,731 unauthorised colonies
(NCT of Delhi Recognition of Property Rights of Residents in Unauthorised
Colonies Act, 2019). Covers all of Delhi; nearly all 1,731 entries are
outside this PC (unauthorised colonies concentrate in outer Delhi --
Nangloi, Najafgarh, Burari -- while this PC is mostly planned/institutional
Lutyens-era development).

IMPORTANT data-quality note this script encodes: the source PDF's own
"Delhi-XX" pincode-like suffixes are NOT reliable postal codes -- cross-
checking against the real India Post pincode directory caught Timarpur
(North Delhi) and Uttam Nagar (West Delhi) both mislabeled with codes that
would suggest they're inside this PC. So this script does NOT filter by
those suffixes at all. The only trustworthy filter is geometry: geocode
every candidate colony name against the actual PC polygon and keep only
what a poly-filtered Overpass search confirms is really here.

Method:
  1. Download the PDF, extract text (pdftotext -layout).
  2. Reconstruct rows (they wrap across physical lines in the source).
  3. Extract a primary place-name phrase per row (text before the first
     comma, with Ph-*/Extn/Part-* suffixes stripped), then reduce to a
     2-word core term for better OSM name-tag matching.
  4. Batch-geocode all core terms against the PC polygon.
  5. For every match, manually cross-check the ORIGINAL row text (not just
     the geocoded term) before accepting it -- name collisions are the
     dominant failure mode here (e.g. "Amar Colony" exists in both Mundka/
     Nangloi -- outside this PC -- AND coincidentally matches unrelated
     OSM points inside it). This step is NOT automated in this script
     because it requires exactly the kind of judgment that produced real,
     documented false positives during initial development (see the git
     history for the specific ones caught and excluded: Amar Colony, Sant
     Nagar, Press Enclave, Ramesh Nagar, Sudarshan Park,
     New Ashok Nagar, Ambedkar Nagar, Budh Vihar -- all same-named places
     elsewhere in Delhi). ACCEPTED_MATCHES below is the result of that
     manual review, not something to trust blindly on a fresh run.

This script prints geocoded CANDIDATES for review; it does not write
land_housing.geojson directly. To add a genuinely new match, verify it
against the original PDF row text yourself, then add it to
ACCEPTED_MATCHES and re-run with --write.

Usage:
    python3 fetch_pmuday_colonies.py            # prints candidates for review
    python3 fetch_pmuday_colonies.py --write    # writes ACCEPTED_MATCHES to land_housing.geojson
"""
import argparse
import json
import os
import re
import sys
import urllib.request

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PC_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, os.path.join(PC_DIR, "..", "..", "scripts"))
from lib_provenance import now_iso
from lib_geocode import load_pc_poly, geocode_terms_in_poly, best_match

PDF_URL = "https://dda.gov.in/sites/default/files/pmuday/1731_uc.pdf"
SOURCE_LABEL = "DDA PM-UDAY notified list of 1,731 unauthorised colonies"
BOUNDARY_PATH = os.path.join(PC_DIR, "data", "boundary.geojson")
OUT_PATH = os.path.join(PC_DIR, "data", "themes", "land_housing.geojson")

# Manually verified against the original PDF row text -- see the module
# docstring. Each entry: (term, AC, claim, coordinates, confidence, status, note)
ACCEPTED_MATCHES = [
    {
        "name": "Baljeet Nagar & Punjabi Basti", "ac": "Patel Nagar",
        "claim": ("Unauthorised colony pocket in Patel Nagar; notified under DDA's PM-UDAY 1,731-colony list "
                   "(two separate list entries: 'Baljeet Nagar and Punjabi basti', and 'Baljeet Nagar & Punjabi "
                   "Basti Extn. Near Nepali Mandir'), eligible for ownership rights under the 2019 Act. Also "
                   "flagged in DJB's own Summer Action Plan as a JICA-area water-deficit tail-end pocket -- "
                   "cross-confirmed by two independent government sources."),
        "coords": (77.1605162, 28.6563217), "confidence": "high", "status": "ok", "note": None,
    },
    {
        "name": "Anand Parbat", "ac": "Moti Nagar",
        "claim": "Unauthorised colony pocket at the Moti Nagar/Karol Bagh boundary; notified under DDA's PM-UDAY list ('Anand Parbat Delhi').",
        "coords": (77.17041, 28.66023), "confidence": "medium", "status": "needs_verification",
        "note": ("PM-UDAY entry has no further address qualifier beyond 'Anand Parbat Delhi'; the postal zone "
                 "(110005) is associated with Karol Bagh, but the matched OSM point geographically falls just "
                 "inside Moti Nagar AC, not Karol Bagh AC -- placed per the polygon check, not the postal zone."),
    },
    {
        "name": "Gautam Nagar (Yusuf Sarai)", "ac": "Kasturba Nagar",
        "claim": "Urban village pocket in Kasturba Nagar, near Yusuf Sarai/Green Park; notified under DDA's PM-UDAY list ('Gautam Nagar Village Yusuf Sarai').",
        "coords": (77.21245, 28.56212), "confidence": "medium", "status": "ok", "note": None,
    },
    {
        "name": "Lado Sarai Extension", "ac": "Malviya Nagar",
        "claim": ("Notified under DDA's PM-UDAY list ('Lado Sarai Extn.'). Lado Sarai is colloquially associated "
                   "with the separate Mehrauli constituency, but this specific OSM-matched point falls just "
                   "inside the Malviya Nagar AC polygon, right at the boundary."),
        "coords": (77.18976, 28.52732), "confidence": "low", "status": "needs_verification",
        "note": "right at the Malviya Nagar AC boundary edge -- worth field-verifying which side of the line this colony actually sits on before relying on it.",
    },
    {
        "name": "Prem Nagar, Karol Bagh (Zone)", "ac": "Patel Nagar",
        "claim": ("Notified under DDA's PM-UDAY list ('Prem Nagar, Karol Bagh (Zone) New Delhi-8'). The "
                   "overwhelming majority of PM-UDAY's ~40 'Prem Nagar' entries are in Kirari/Nangloi (far "
                   "outside this PC) -- this specific one is pincode-anchored to 110008 (Patel Nagar), which is "
                   "the only reason it's included here."),
        "coords": None,  # placed at the Patel Nagar AC centroid at write time -- no independent geocode exists
        "confidence": "low", "status": "needs_verification",
        "note": "no distinguishing address detail beyond the zone/pincode -- could not be geocoded to a specific OSM feature; placed at the Patel Nagar AC centroid as an honest placeholder.",
    },
]

# NOTE (important, checked once during development, not re-verified on every run):
# Basai Darapur ('Extended Abadi of Village, Basai Dara Pur, New Delhi-15') was
# initially accepted here but scripts/validate_contribution.py's boundary check
# caught it 424m outside the real PC polygon (an AC-bounding-box check isn't the
# same as an AC-polygon check) -- removed rather than shipped with a known-wrong
# location. Left out of ACCEPTED_MATCHES deliberately.


def log(msg):
    print(f"[fetch_pmuday_colonies] {msg}")


def download_pdf_text(url):
    tmp_pdf = "/tmp/pmuday_1731.pdf"
    log(f"downloading {url}")
    urllib.request.urlretrieve(url, tmp_pdf)
    tmp_txt = "/tmp/pmuday_1731.txt"
    os.system(f'pdftotext -layout "{tmp_pdf}" "{tmp_txt}"')
    with open(tmp_txt) as f:
        return f.read()


def extract_candidate_terms(text):
    candidates = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("LIST OF") or line.startswith("SL."):
            continue
        stripped = re.sub(r"^\d+\.\s*[\w\-\(\)]*\s*[A-Z]?\s*", "", line).strip()
        if len(stripped) < 4:
            continue
        primary = stripped.split(",")[0].strip()
        primary = re.sub(r"[\.\-]?\s*(New )?Delhi[\-\s]*\d*$", "", primary, flags=re.I).strip()
        primary = re.sub(r"\bPh[- ]?[IVX0-9]+.*$", "", primary, flags=re.I).strip()
        primary = re.sub(r"\bExtn?\.?.*$", "", primary, flags=re.I).strip()
        primary = re.sub(r"\bPart[- ]?[IVX0-9]+.*$", "", primary, flags=re.I).strip()
        words = primary.split()
        while words and words[0].lower() in ("near", "opp", "opp.", "at", "the"):
            words = words[1:]
        core = " ".join(words[:2]) if len(words) >= 2 else (words[0] if words else "")
        if len(core) >= 4:
            candidates.add(core)
    return sorted(candidates)


def ac_centroid(ac_name):
    with open(BOUNDARY_PATH) as f:
        boundary = json.load(f)
    feat = next(f for f in boundary["features"] if f["properties"].get("AC_NAME", "").split(" (")[0] == ac_name)
    pts = []
    def rec(x):
        if isinstance(x[0], (int, float)):
            pts.append(x)
        else:
            for y in x:
                rec(y)
    rec(feat["geometry"]["coordinates"])
    lons = [p[0] for p in pts]
    lats = [p[1] for p in pts]
    return sum(lons) / len(lons), sum(lats) / len(lats)


def print_candidates():
    """Discovery mode: geocode every candidate term and print matches for manual
    review -- this is how ACCEPTED_MATCHES above was originally built."""
    text = download_pdf_text(PDF_URL)
    terms = extract_candidate_terms(text)
    log(f"{len(terms)} candidate core terms extracted from {PDF_URL}")
    poly = load_pc_poly(BOUNDARY_PATH)
    log("geocoding against the PC polygon (takes several minutes, paced to avoid rate limits)")
    elements = geocode_terms_in_poly(terms, poly)
    found = 0
    for term in terms:
        m = best_match(term, elements)
        if m:
            found += 1
            print(f"{term!r:30} -> {m['name']!r} ({m['lat']:.5f},{m['lon']:.5f}) n_candidates={m['n_candidates']}")
    log(f"{found}/{len(terms)} terms had an OSM match within the PC polygon")
    log("Cross-check each against the ORIGINAL PDF row text before adding to ACCEPTED_MATCHES -- "
        "name collisions with same-named places elsewhere in Delhi are the norm, not the exception.")


def write_accepted():
    fetched_at = now_iso()
    with open(OUT_PATH) as f:
        land_housing = json.load(f)
    existing_names = {f["properties"]["name"] for f in land_housing["features"]}

    added = 0
    for m in ACCEPTED_MATCHES:
        if m["name"] in existing_names:
            continue
        coords = m["coords"] or ac_centroid(m["ac"])
        props = {
            "name": m["name"], "theme": "land_housing", "claim": m["claim"],
            "status_tag": "unauthorised_colony", "confidence": m["confidence"], "geometry_basis": "point",
            "_source": SOURCE_LABEL, "_source_url": PDF_URL, "_fetched_at": fetched_at, "_status": m["status"],
        }
        if m["note"]:
            props["_note"] = m["note"]
        land_housing["features"].append({
            "type": "Feature", "properties": props,
            "geometry": {"type": "Point", "coordinates": [coords[0], coords[1]]},
        })
        added += 1

    with open(OUT_PATH, "w") as f:
        json.dump(land_housing, f, indent=2)
    log(f"wrote {OUT_PATH}: {added} new feature(s) added ({len(ACCEPTED_MATCHES) - added} already present, skipped)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write ACCEPTED_MATCHES to land_housing.geojson (default: print candidates for review only)")
    args = ap.parse_args()
    if args.write:
        write_accepted()
    else:
        print_candidates()


if __name__ == "__main__":
    main()
