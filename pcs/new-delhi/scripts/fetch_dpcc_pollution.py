#!/usr/bin/env python3
"""fetch_dpcc_pollution.py -- New Delhi PC only

Source: DPCC's "Inventory of major point air pollution sources in Delhi:
Hotspots and other priority areas" (2023) -- a real, official document
naming specific pollution sources (construction sites, traffic congestion,
illegal dumping, road dust) near its CAAQMS monitoring hotspots, each with
a responsible department.

Method: the site-to-source mapping below was hand-extracted from the PDF
(pdftotext -layout, then manual reading -- the source's tabular layout
doesn't parse cleanly enough to automate reliably, unlike the simpler
row-per-line lists the other fetch_*.py scripts handle). Anchor
coordinates for each hotspot were geocoded against the PC polygon once
and are hardcoded below since they don't change; individual sources within
a hotspot are placed at that same anchor (DPCC itself describes several by
aerial distance from the hotspot, not an independent address).

Sources are split by their ACTUAL cause across three theme files, not
lumped into "air": traffic-congestion items -> roads_congestion.geojson,
illegal-dumping items -> solid_waste.geojson, everything else (construction
dust, biomass burning) -> air.geojson.

ITO's sources were checked and excluded: the PC polygon confirms ITO
itself sits just outside this constituency's boundary, despite being
adjacent to New Delhi AC.

Usage: python3 fetch_dpcc_pollution.py
(run from this directory; rewrites the DPCC-sourced features in
../data/themes/{air,roads_congestion,solid_waste}.geojson, leaving any
other features already in those files untouched)
"""
import json
import os
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PC_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, os.path.join(PC_DIR, "..", "..", "scripts"))
from lib_provenance import now_iso

SOURCE_LABEL = "DPCC 'Inventory of major point air pollution sources in Delhi: Hotspots and other priority areas' (2023)"
SOURCE_URL = "https://www.dpcc.delhigovt.nic.in/uploads/news/ae9ce818bf8b9e12ddb90177ce3108c7.pdf"

# Anchors geocoded once against the PC polygon (Overpass, poly-filtered) -- see
# lib_geocode.py for the method. Re-geocode these if OSM's tagging of these
# places changes significantly; they're hardcoded here because DPCC's hotspots
# themselves don't move.
ANCHORS = {
    "PUNJABI_BAGH": (77.1420875, 28.6703201),       # OSM "Punjabi Bagh West" neighbourhood node
    "RK_PURAM": (77.176309, 28.5669356),            # OSM "R.K.Puram" node
    "SAROJINI_NAGAR_DEPOT": (77.1899867, 28.5734543),
    "NAUROJI_NAGAR": (77.19387, 28.56852),
    "NEW_MOTI_BAGH": (77.17280, 28.58192),           # reuses the "Moti Bagh" OSM point; "New Moti Bagh" isn't separately mapped in OSM
    "SHADIPUR": (77.1536389, 28.6526021),
    "SHADIPUR_DTC_DEPOT": (77.15617, 28.65381),
    "SIRIFORT": (77.22470, 28.55215),
    "SRI_AUROBINDO": (77.194, 28.531),               # same point as the existing Sri Aurobindo Marg CAAQMS station
    "LODHI_ROAD": (77.22731, 28.591824),             # same point as the existing Lodhi Road CAAQMS station
}
NOTE_CLUSTER = (
    "point placed at the hotspot's OSM-geocoded anchor, not an independently geocoded "
    "address -- DPCC's own document describes several of these sources by aerial "
    "distance from the hotspot rather than a separate address."
)


def point(key):
    lon, lat = ANCHORS[key]
    return {"type": "Point", "coordinates": [lon, lat]}


def feat(theme, name, claim, status_tag, anchor_key, confidence="high", note=NOTE_CLUSTER, fetched_at=None):
    props = {
        "name": name, "theme": theme, "claim": claim, "status_tag": status_tag,
        "confidence": confidence, "geometry_basis": "point",
        "_source": SOURCE_LABEL, "_source_url": SOURCE_URL, "_fetched_at": fetched_at, "_status": "ok",
    }
    if note:
        props["_note"] = note
    return {"type": "Feature", "properties": props, "geometry": point(anchor_key)}


def build_features(fetched_at):
    air = [
        feat("air", "Moti Nagar Flyover construction (Punjabi Bagh hotspot)",
             "Construction of Moti Nagar Flyover identified by DPCC as a point air pollution source. Concerned dept: PWD.",
             "pollution_source", "PUNJABI_BAGH", fetched_at=fetched_at),
        feat("air", "Ram Leela ground dust (Punjabi Bagh hotspot)",
             "Ram Leela ground used as a driving-training park, causing dust emission. Concerned dept: MCD.",
             "pollution_source", "PUNJABI_BAGH", fetched_at=fetched_at),
        feat("air", "Netaji Nagar Redevelopment + NBCC World Trade Centre construction (R.K. Puram hotspot)",
             "Netaji Nagar Redevelopment Project and NBCC World Trade Centre Project, Nauroji Nagar, in the vicinity of the R.K. Puram hotspot. Concerned dept: NBCC.",
             "pollution_source", "NAUROJI_NAGAR", fetched_at=fetched_at),
        feat("air", "Safdarjung Railway Station redevelopment (New Moti Bagh hotspot)",
             "Safdarjung Railway Station redevelopment work near Kaushal Bhawan/Hotel Leela Palace. Concerned dept: IRCON.",
             "pollution_source", "NEW_MOTI_BAGH", fetched_at=fetched_at),
        feat("air", "Netaji Nagar Redevelopment (New Moti Bagh hotspot)",
             "Netaji Nagar Redevelopment Work. Concerned dept: NBCC.",
             "pollution_source", "NEW_MOTI_BAGH", fetched_at=fetched_at),
        feat("air", "Sarojini Nagar GPRA redevelopment (New Moti Bagh hotspot)",
             "Sarojini Nagar GPRA and redevelopment work. Concerned dept: NBCC.",
             "pollution_source", "NEW_MOTI_BAGH", fetched_at=fetched_at),
        feat("air", "Raheja Developers construction site (Shadipur hotspot)",
             "Raheja Developers main EIA project at Patel Nagar Road (aerial distance approx. 680m from the monitoring station). Concerned: Project Proponent, DPCC.",
             "pollution_source", "SHADIPUR", fetched_at=fetched_at),
        feat("air", "Delhi Milk Scheme (DMS) Campus dust/biomass burning (Shadipur hotspot)",
             "Burning of biomass inside DMS Campus; dust along roads leading to the monitoring station and from campus parks. Concerned depts: PWD, MCD, DMS.",
             "pollution_source", "SHADIPUR", fetched_at=fetched_at),
        feat("air", "DTC Depot Shadipur dust (Shadipur hotspot)",
             "DTC Depot Shadipur (aerial distance approx. 535m) -- bus traffic and dust plying inside the depot flagged as a main PM2.5 source. Concerned depts: PWD, MCD, DTC.",
             "pollution_source", "SHADIPUR_DTC_DEPOT", fetched_at=fetched_at),
        feat("air", "C&D sites near the Sirifort monitoring station",
             "Construction & demolition sites, mostly under 500 sqm, within a 2km radius of the CAQM station. Concerned dept: MCD.",
             "pollution_source", "SIRIFORT", fetched_at=fetched_at),
        feat("air", "Dusty service road near Sirifort monitoring station",
             "~100m stretch of dusty service road with broken top-layer patches. Concerned dept: PWD.",
             "pollution_source", "SIRIFORT", fetched_at=fetched_at),
        feat("air", "NITRD campus construction (Sri Aurobindo Marg hotspot)",
             "Construction work inside NITRD Campus. Concerned dept: NITRD.",
             "pollution_source", "SRI_AUROBINDO", note=None, fetched_at=fetched_at),
        feat("air", "Road-side dust near NITRD exit gate (Sri Aurobindo Marg hotspot)",
             "Road-side dust near the NITRD exit gate. Concerned dept: PWD.",
             "pollution_source", "SRI_AUROBINDO", note=None, fetched_at=fetched_at),
    ]

    roads_congestion = [
        feat("roads_congestion", "Punjabi Bagh Club Road congestion (Moti Nagar Flyover construction)",
             "Traffic congestion below the Moti Nagar flyover and on Punjabi Bagh Club Road, worsened by construction and parked-vehicle obstruction. Concerned: Delhi Traffic Police, PWD.",
             "congestion", "PUNJABI_BAGH", fetched_at=fetched_at),
        feat("roads_congestion", "Potholes/road dust, Road No. 77 & Club Road, west Punjabi Bagh",
             "Potholes and road dust at various stretches (unpaved Road No. 77 and Club Road). Concerned: PWD, MCD.",
             "road_quality", "PUNJABI_BAGH", fetched_at=fetched_at),
        feat("roads_congestion", "Sarojini Nagar Bus Depot exit -- road repair needed",
             "Road repair needed at the exit point of Sarojini Nagar (S.N.) Bus Depot; broken patches also found at Church Road, R.K. Puram. Concerned dept: MCD.",
             "road_quality", "SAROJINI_NAGAR_DEPOT", fetched_at=fetched_at),
        feat("roads_congestion", "Sarojini Nagar Bus Depot exit + Africa Avenue/Outer Ring Road congestion",
             "Traffic congestion at the Sarojini Nagar Bus Depot exit; Africa Avenue Road and Outer Ring Road heavily congested, adjacent to the R.K. Puram CAAQMS hotspot. Concerned: Delhi Traffic Police.",
             "congestion", "RK_PURAM", fetched_at=fetched_at),
        feat("roads_congestion", "DMS Campus to Girdhari Lal Chowk congestion (Shadipur hotspot)",
             "Traffic congestion from DMS Campus to Girdhari Lal Chowk. Concerned dept: Delhi Traffic Police.",
             "congestion", "SHADIPUR", fetched_at=fetched_at),
        feat("roads_congestion", "Potholes/road dust, Main Mathura Marg & Goswami Girdhari Lal Marg (Shadipur hotspot)",
             "Major potholes and road dust on Main Mathura Marg and Goswami Girdhari Lal Marg. Concerned dept: PWD.",
             "road_quality", "SHADIPUR", fetched_at=fetched_at),
        feat("roads_congestion", "Vehicle parking in front of the Sirifort monitoring station",
             "Vehicle parking obstruction directly in front of the CAQM station. Concerned dept: MCD.",
             "congestion", "SIRIFORT", fetched_at=fetched_at),
        feat("roads_congestion", "Traffic signal congestion at NITRD entry gate (Sri Aurobindo Marg hotspot)",
             "Traffic congestion at the signal near the entry gate of NITRD. Concerned dept: Delhi Traffic Police.",
             "congestion", "SRI_AUROBINDO", note=None, fetched_at=fetched_at),
        feat("roads_congestion", "Traffic congestion near Mausam Bhawan (Lodhi Road hotspot)",
             "Traffic congestion at Lodhi Road, near Mausam Bhawan. Concerned dept: Delhi Traffic Police.",
             "congestion", "LODHI_ROAD", note=None, fetched_at=fetched_at),
    ]

    solid_waste = [
        feat("solid_waste", "Illegal C&D waste dumping, Rohtak Road (Madipur to Shivaji Park metro stretch)",
             "Illegal dumping of construction and demolition waste on vacant lands and along the Rohtak Road stretch between Madipur metro station and Shivaji Park metro station. Concerned: PWD, Indian Railways, MCD.",
             "illegal_dumping", "PUNJABI_BAGH", fetched_at=fetched_at),
    ]

    return air, roads_congestion, solid_waste


def merge_into(path, dpcc_features):
    """Replace any previously-written DPCC-sourced features in this file with
    the freshly built set, leaving features from other sources untouched."""
    if os.path.exists(path):
        with open(path) as f:
            existing = json.load(f)
    else:
        existing = {"type": "FeatureCollection", "features": []}
    kept = [f for f in existing["features"] if f["properties"].get("_source") != SOURCE_LABEL]
    existing["features"] = kept + dpcc_features
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"[fetch_dpcc_pollution] wrote {path}: {len(kept)} other feature(s) + {len(dpcc_features)} DPCC feature(s)")


def main():
    fetched_at = now_iso()
    air, roads_congestion, solid_waste = build_features(fetched_at)
    themes_dir = os.path.join(PC_DIR, "data", "themes")
    merge_into(os.path.join(themes_dir, "air.geojson"), air)
    merge_into(os.path.join(themes_dir, "roads_congestion.geojson"), roads_congestion)
    merge_into(os.path.join(themes_dir, "solid_waste.geojson"), solid_waste)


if __name__ == "__main__":
    main()
