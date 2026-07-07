"""Shared provenance stamping for all fetch_*.py scripts.

Every record written to /data must carry _source, _fetched_at, and _status
so the front end can show where each layer came from and whether it's been
verified. Nothing in this pipeline should invent data to fill a gap --
unavailable data is written with _status "needs_verification" (or
"unavailable") and an explanation, never silently dropped or guessed.
"""
import datetime


STATUS_OK = "ok"
STATUS_NEEDS_VERIFICATION = "needs_verification"
STATUS_UNAVAILABLE = "unavailable"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp_feature_collection(geojson, source, status=STATUS_OK, fetched_at=None, note=None):
    """Stamp every feature's properties in a GeoJSON FeatureCollection in place."""
    fetched_at = fetched_at or now_iso()
    for feature in geojson.get("features", []):
        props = feature.setdefault("properties", {})
        props["_source"] = source
        props["_fetched_at"] = fetched_at
        props["_status"] = status
        if note:
            props["_note"] = note
    geojson["_source"] = source
    geojson["_fetched_at"] = fetched_at
    geojson["_status"] = status
    if note:
        geojson["_note"] = note
    return geojson


def stamp_record(record, source, status=STATUS_OK, fetched_at=None, note=None):
    """Stamp a plain dict record (e.g. one row of election results)."""
    fetched_at = fetched_at or now_iso()
    record["_source"] = source
    record["_fetched_at"] = fetched_at
    record["_status"] = status
    if note:
        record["_note"] = note
    return record
