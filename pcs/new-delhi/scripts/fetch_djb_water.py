#!/usr/bin/env python3
"""fetch_djb_water.py -- New Delhi PC only

Source: DJB's "Summer Action Plan 2026", published separately per assembly
constituency -- one PDF per AC, listing colony-level water supply hours,
fixed tanker points, and named "vulnerable" water-deficit/contamination
colonies with remedial status and timelines. DJB publishes a fresh one of
these every year; re-run this each summer to refresh the data.

AC-38 (Delhi Cantt) and AC-40 (New Delhi) have NO DJB plan -- confirmed by
trying every URL-naming variant DJB uses elsewhere and finding none exist
for these two segments, consistent with them being served by the
Cantonment Board / NDMC (which buy DJB bulk supply but distribute
independently), not DJB directly. Their features are written with
_status: "unavailable", not silently skipped.

Method:
  1. Download each AC's PDF, extract text (pdftotext -layout).
  2. DJB's tables don't have consistent enough structure across all 8 PDFs
     for reliable fully-automated parsing (column widths, multi-line
     cells, and JICA-area formatting all vary) -- this script fetches and
     dumps text for reference, but the actual table-to-claim extraction
     below is hand-transcribed from reading that output, same as the
     PM-UDAY script's ACCEPTED_MATCHES pattern. ENTRIES below is the
     result.
  3. "General supply" summary features per AC reuse that AC's own polygon
     from boundary.geojson (real geometry) -- not every individual
     colony's water-supply window is mapped as a separate feature; DJB's
     source has far finer per-colony/per-JJC granularity than shown here
     (see each summary's claim text and _note).
  4. Named "vulnerable deficit/contamination" colonies ARE mapped
     individually, geocoded against the PC polygon where a real OSM match
     exists, else placed at that AC's centroid and flagged
     needs_verification (never silently guessed at a precise point).
  5. Sewer-overflow items go to sanitation.geojson, not water.geojson --
     matches the DJB source's own table structure.

Usage:
    python3 fetch_djb_water.py            # downloads PDFs, dumps text to /tmp for reference
    python3 fetch_djb_water.py --write     # writes ENTRIES to water.geojson + sanitation.geojson
"""
import argparse
import json
import os
import sys
import urllib.request

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PC_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, os.path.join(PC_DIR, "..", "..", "scripts"))
from lib_provenance import now_iso

DJB_URL_BASE = "https://delhijalboard.delhi.gov.in/sites/default/files/inline-files/"
AC_PDF_FILENAMES = {
    "Karol Bagh": "ac_23_karol_bagh_0.pdf",
    "Patel Nagar": "ac_24_patel_nagar_0.pdf",
    "Moti Nagar": "ac_25_moti_nagar_0.pdf",
    "Rajinder Nagar": "ac_39_rajinder_nagar.pdf",
    "Kasturba Nagar": "ac_42_kasturba_nagar.pdf",
    "Malviya Nagar": "ac_43_malviya_nagar_1.pdf",
    "R.K. Puram": "ac_44_r_k_puram_1.pdf",
    "Greater Kailash": "ac_50_greater_kailash_0.pdf",
    # Delhi Cantt (AC-38) and New Delhi (AC-40) deliberately absent -- see module docstring.
}
BOUNDARY_PATH = os.path.join(PC_DIR, "data", "boundary.geojson")
WATER_PATH = os.path.join(PC_DIR, "data", "themes", "water.geojson")
SANITATION_PATH = os.path.join(PC_DIR, "data", "themes", "sanitation.geojson")

# --- hand-transcribed from each AC's PDF text (see module docstring) -------

AC_SUMMARY_CLAIMS = {
    "Karol Bagh": "Pahar Ganj, Karol Bagh, and Dev Nagar wards get ~1.5-2.25 hrs/day piped supply (5:00-6:30 AM plus a short evening window), per DJB's 2026 summer plan.",
    "Patel Nagar": "Supply is tracked at individual JJC/camp level (40+ named points) rather than by colony; the JICA-assisted network upgrade (new mains, DMA formation) is in progress, targeted for completion Dec 2026.",
    "Moti Nagar": "Kirti Nagar, Ramesh Nagar, Rakhi Market, Karampura, and Moti Nagar/Sudarshan Park get ~4 hrs/day (4:30-8 AM plus a short evening window), per DJB's 2026 summer plan.",
    "Rajinder Nagar": "Supply windows vary sharply by pocket -- from under an hour a day in some Naraina/Inderpuri mohallas up to 24-hour backup at a few named points (Shiv Mandir, Sabji Mandi Chowk) -- per DJB's 2026 summer plan (28 named colony-groups).",
    "Kasturba Nagar": "Defence Colony, Lajpat Nagar-1, Kotla Village, and Aliganj get ~5 hrs/day (4-7 AM + 5-7 PM); NDSE-2 gets ~3 hrs/day (3-6 AM), per DJB's 2026 summer plan.",
    "R.K. Puram": "Supply windows range ~1.5-6 hrs/day and include odd late-night/midday slots (e.g. Mohammadpur village and Sectors 1-5 get 12 AM-3 AM plus 12 PM-3 PM), per DJB's 2026 summer plan.",
    "Greater Kailash": "GK-Enclave-I, Kalkaji, CR Park pockets, NRI Colony, and Aravali Apartment get roughly 2-3 hrs/day across ~7 named colony pockets, per DJB's 2026 summer plan.",
}

WATER_POINT_ENTRIES = [
    {"name": "Gali 49, Karol Bagh", "ac": "Karol Bagh", "claim": "100mm-dia water line blocked by leaks; replacement work targeted for completion 31 Mar 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "needs_verification", "note": "no specific-enough OSM match for 'Gali 49' -- placed at the Karol Bagh AC centroid as an honest placeholder, not a real location fix.", "coords": None},
    {"name": "53 Regharpura, Karol Bagh", "ac": "Karol Bagh", "claim": "100mm-dia water line blocked by leaks; replacement work targeted for completion 31 Mar 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "ok", "note": None, "coords": (77.1860862, 28.6486581)},
    {"name": "Baljeet Nagar, Nehru Nagar, Punjabi Basti, Baba Farid Puri, Gayatri Colony, Than Singh Nagar (tail-end, JICA area)", "ac": "Patel Nagar", "claim": "Tail-end areas of the JICA-assisted water network upgrade; new/replaced mains in progress, targeted completion Dec 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "needs_verification", "note": "combined multi-colony DJB table row; point placed at 'Baljeet Nagar', the first-named locality, as a representative anchor.", "coords": (77.1605162, 28.6563217)},
    {"name": "Kirti Nagar N Block", "ac": "Moti Nagar", "claim": "172m of water line being replaced; targeted completion 31 Mar 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "ok", "note": None, "coords": (77.1417729, 28.6532807)},
    {"name": "East Avenue Road, Punjabi Bagh", "ac": "Moti Nagar", "claim": "Water line replacement work in progress; targeted completion 31 Mar 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "needs_verification", "note": "anchored to the 'Punjabi Bagh West' OSM neighbourhood node, not the specific road.", "coords": (77.1420875, 28.6703201)},
    {"name": "Ashoka Park Extension", "ac": "Moti Nagar", "claim": "Water line replacement at tender stage; targeted completion 31 May 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "ok", "note": None, "coords": (77.1569775, 28.671984)},
    {"name": "Naraina Village, Todapur Village, Dasghara Village (tail-end, JICA area)", "ac": "Rajinder Nagar", "claim": "Tail-end areas of the JICA-assisted water network upgrade; targeted completion Dec 2026. Tankers sent on demand in the interim.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "needs_verification", "note": "combined multi-village DJB table row; point placed at 'Naraina Village', the first-named locality.", "coords": (77.1386441, 28.6220547)},
    {"name": "South Extension Part-2", "ac": "Kasturba Nagar", "claim": "New GI water line being laid; targeted completion 31 Mar 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "needs_verification", "note": "anchored to the 'South Extension I' OSM node (nearest named match); the DJB table specifically names 'Part-2'.", "coords": (77.2203844, 28.5705664)},
    {"name": "Double Storey flats, Amar Colony", "ac": "Kasturba Nagar", "claim": "Water line replacement out to tender; targeted completion 31 Mar 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "ok", "note": None, "coords": (77.2431499, 28.5615391)},
    {"name": "Budh Vihar, Munirka", "ac": "R.K. Puram", "claim": "Water line replacement in progress to address contamination complaints; targeted completion 31 Mar 2026.", "status_tag": "vulnerable_contamination", "confidence": "high", "status": "needs_verification", "note": "anchored to the 'Munirka' OSM locality node; Budh Vihar is a sub-pocket not separately mapped in OSM.", "coords": (77.1710841, 28.554886)},
    {"name": "Munirka Village", "ac": "R.K. Puram", "claim": "Water line replacement in progress to address contamination complaints; targeted completion 31 Mar 2026.", "status_tag": "vulnerable_contamination", "confidence": "high", "status": "ok", "note": None, "coords": (77.1710841, 28.554886)},
    {"name": "C.R. Park I-Block (house nos. 1760-1784, 1736-1747)", "ac": "Greater Kailash", "claim": "Old/damaged water line replacement awarded; targeted completion 30 Apr 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "needs_verification", "note": "anchored to the 'Chittaranjan Park' OSM suburb node, not the specific block.", "coords": (77.2516536, 28.5376883)},
    {"name": "Sant Nagar (near H.No. 326)", "ac": "Greater Kailash", "claim": "New water line to be laid; targeted completion 28 Feb 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "ok", "note": None, "coords": (77.2495194, 28.5548352)},
    {"name": "GK Enclave-I", "ac": "Greater Kailash", "claim": "New water line to be laid; targeted completion 30 Apr 2026.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "needs_verification", "note": "anchored to the 'Greater Kailash I' OSM neighbourhood node.", "coords": (77.2360199, 28.5512676)},
    {"name": "Chirag Delhi Village (elevated/tail-end areas)", "ac": "Greater Kailash", "claim": "Part of the Malviya Nagar Water Supply (MNWS) PPP zone: total availability (~62 MLD) falls short of the ~88 MLD agreed demand at Malviya Nagar UGR, so elevated/tail-end houses here go short. Valve regulation + additional tankers deployed as interim measures.", "status_tag": "vulnerable_deficit", "confidence": "high", "status": "ok", "note": None, "coords": (77.2280694, 28.5381411)},
]

SANITATION_POINT_ENTRIES = [
    {"name": "Shadipur, Ranjeet Nagar (Gali No. 19, 12A, 10 & Shiv Chowk)", "ac": "Patel Nagar", "claim": "Sewer line up-gradation/realignment estimated at Rs 1.40 Cr; taken up in DJB action plan 2026-27.", "confidence": "high", "status": "ok", "note": "anchored to the 'Shadipur' OSM neighbourhood node; the DJB entry covers specific galis nearby.", "coords": (77.1536389, 28.6526021)},
    {"name": "Baba Faridpuri, near Military Station", "ac": "Patel Nagar", "claim": "Sewer line re-alignment/up-gradation work in progress; financial bid opened and under award.", "confidence": "low", "status": "needs_verification", "note": "no specific-enough OSM match for 'Baba Faridpuri' -- placed at the Patel Nagar AC centroid as an honest placeholder.", "coords": None},
    {"name": "Road No-5, East Punjabi Bagh", "ac": "Moti Nagar", "claim": "Sewer line settlement work completed.", "confidence": "high", "status": "ok", "note": "anchored to the 'Punjabi Bagh West' OSM neighbourhood node, not the specific road.", "coords": (77.1420875, 28.6703201)},
    {"name": "Pandav Nagar (A & B Block)", "ac": "Rajinder Nagar", "claim": "Area silted up due to the West Delhi trunk sewer line running below capacity; regular desilting with available SCMs (sewer cleaning machines) ongoing pending trunk-line desilting.", "confidence": "high", "status": "ok", "note": None, "coords": (77.1536755, 28.6500237)},
    {"name": "TC Camp, Rajinder Nagar", "ac": "Rajinder Nagar", "claim": "Sewer line replacement/up-gradation; tenders invited, targeted completion 31 May 2026.", "confidence": "low", "status": "needs_verification", "note": "'TC Camp' too generic/informal to geocode reliably -- placed at the Rajinder Nagar AC centroid.", "coords": None},
    {"name": "Budh Nagar (A to F Block)", "ac": "Rajinder Nagar", "claim": "Sewer line replacement/up-gradation; tenders invited, targeted completion 31 May 2026.", "confidence": "high", "status": "ok", "note": None, "coords": (77.1440854, 28.6325424)},
    {"name": "C-Block, Lajpat Nagar-II", "ac": "Kasturba Nagar", "claim": "Sewer line replacement; work order issued, targeted completion 31 Mar 2026.", "confidence": "high", "status": "ok", "note": None, "coords": (77.2431796, 28.5700938)},
    {"name": "Pillanji Village", "ac": "Kasturba Nagar", "claim": "Sewer line replacement; work order issued, targeted completion 30 Apr 2026.", "confidence": "low", "status": "needs_verification", "note": "no OSM match found for 'Pillanji' (tried Pillanji/Pilanji/Pillangi/Pilangi spellings) -- placed at the Kasturba Nagar AC centroid.", "coords": None},
    {"name": "Mohammadpur Village", "ac": "R.K. Puram", "claim": "Old sewer line replacement + desilting in progress, targeted completion 31 Mar 2026.", "confidence": "high", "status": "ok", "note": None, "coords": (77.1869544, 28.5653336)},
    {"name": "Vasant Vihar", "ac": "R.K. Puram", "claim": "Old sewer line replacement + desilting in progress, targeted completion 31 Mar 2026.", "confidence": "high", "status": "ok", "note": None, "coords": (77.1628475, 28.5602932)},
    {"name": "Satya Niketan", "ac": "R.K. Puram", "claim": "Old sewer line replacement + desilting in progress, targeted completion 31 Aug 2026.", "confidence": "high", "status": "ok", "note": None, "coords": (77.1689581, 28.587462)},
    {"name": "W-Block, GK-II", "ac": "Greater Kailash", "claim": "Sewer line replacement, targeted completion 30 May 2026.", "confidence": "low", "status": "needs_verification", "note": "'W-Block, GK-II' too fine-grained to geocode reliably -- placed at the Greater Kailash AC centroid.", "coords": None},
]


def log(msg):
    print(f"[fetch_djb_water] {msg}")


def download_texts():
    for ac, filename in AC_PDF_FILENAMES.items():
        url = DJB_URL_BASE + filename
        tmp_pdf = f"/tmp/djb_{filename}"
        log(f"downloading {ac}: {url}")
        try:
            urllib.request.urlretrieve(url, tmp_pdf)
        except Exception as e:
            log(f"  FAILED: {e}")
            continue
        tmp_txt = tmp_pdf.replace(".pdf", ".txt")
        os.system(f'pdftotext -layout "{tmp_pdf}" "{tmp_txt}"')
        log(f"  -> {tmp_txt}")
    log("Read these to (re-)build/verify AC_SUMMARY_CLAIMS, WATER_POINT_ENTRIES, SANITATION_POINT_ENTRIES above.")


def ac_polygon_and_centroid(ac_name):
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
    centroid = (sum(lons) / len(lons), sum(lats) / len(lats))
    return feat["geometry"], centroid


def write_features():
    fetched_at = now_iso()

    with open(WATER_PATH) as f:
        water = json.load(f)
    with open(SANITATION_PATH) as f:
        sanitation = json.load(f)

    existing_water_names = {f["properties"]["name"] for f in water["features"]}
    existing_sanitation_names = {f["properties"]["name"] for f in sanitation["features"]}

    added_water = 0
    for ac, claim in AC_SUMMARY_CLAIMS.items():
        name = f"{ac} (general supply)"
        if name in existing_water_names:
            continue
        geom, _ = ac_polygon_and_centroid(ac)
        props = {
            "name": name, "theme": "water", "claim": claim, "status_tag": "limited_supply",
            "confidence": "high", "geometry_basis": "surveyed",
            "_source": f"DJB Summer Action Plan 2026 -- AC {ac}", "_source_url": DJB_URL_BASE + AC_PDF_FILENAMES[ac],
            "_fetched_at": fetched_at, "_status": "ok",
            "_note": "Geometry is the AC boundary (real) standing in for a colony-by-colony water-supply map; the source PDF has finer per-colony/per-JJC detail than shown here.",
        }
        water["features"].append({"type": "Feature", "properties": props, "geometry": geom})
        added_water += 1

    for entry in WATER_POINT_ENTRIES:
        if entry["name"] in existing_water_names:
            continue
        coords = entry["coords"] or ac_polygon_and_centroid(entry["ac"])[1]
        props = {
            "name": entry["name"], "theme": "water", "claim": entry["claim"], "status_tag": entry["status_tag"],
            "confidence": entry["confidence"], "geometry_basis": "point",
            "_source": f"DJB Summer Action Plan 2026 -- AC {entry['ac']}", "_source_url": DJB_URL_BASE + AC_PDF_FILENAMES[entry["ac"]],
            "_fetched_at": fetched_at, "_status": entry["status"],
        }
        if entry["note"]:
            props["_note"] = entry["note"]
        water["features"].append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [coords[0], coords[1]]}})
        added_water += 1

    added_sanitation = 0
    for entry in SANITATION_POINT_ENTRIES:
        if entry["name"] in existing_sanitation_names:
            continue
        coords = entry["coords"] or ac_polygon_and_centroid(entry["ac"])[1]
        props = {
            "name": entry["name"], "theme": "sanitation", "claim": entry["claim"], "status_tag": "sewer_gap",
            "confidence": entry["confidence"], "geometry_basis": "point",
            "_source": f"DJB Summer Action Plan 2026 -- AC {entry['ac']}", "_source_url": DJB_URL_BASE + AC_PDF_FILENAMES[entry["ac"]],
            "_fetched_at": fetched_at, "_status": entry["status"],
        }
        if entry["note"]:
            props["_note"] = entry["note"]
        sanitation["features"].append({"type": "Feature", "properties": props, "geometry": {"type": "Point", "coordinates": [coords[0], coords[1]]}})
        added_sanitation += 1

    with open(WATER_PATH, "w") as f:
        json.dump(water, f, indent=2)
    with open(SANITATION_PATH, "w") as f:
        json.dump(sanitation, f, indent=2)
    log(f"wrote {WATER_PATH}: {added_water} new feature(s) added")
    log(f"wrote {SANITATION_PATH}: {added_sanitation} new feature(s) added")
    log("Delhi Cantt / New Delhi 'no DJB data' features are written separately by hand (no PDF exists for them) -- see this module's docstring.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write the hand-transcribed ENTRIES to water/sanitation.geojson (default: just download PDFs and dump text for reference)")
    args = ap.parse_args()
    if args.write:
        write_features()
    else:
        download_texts()


if __name__ == "__main__":
    main()
