"""lib_geocode.py -- shared, PC-agnostic

Overpass-API geocoding helper used by every fetch_<source>.py script in
this project. The one rule this file exists to enforce: geocode against
the actual PC polygon (Overpass "poly" filter), never a bounding-box
rectangle -- a bbox spills into neighbouring constituencies and produces
false-positive name collisions (we hit this repeatedly in practice: a
"Sant Nagar" bbox-matched near Greater Kailash turned out to be a
different Sant Nagar in Burari; the poly filter would have excluded it).

Also used by scripts/validate_contribution.py's boundary check, so the
"is this point actually in the PC" logic only lives in one place.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

OVERPASS_MIRRORS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "civic-map-poc/0.1 (civic-mapping proof of concept; contact via repo issues)"


def load_pc_poly(boundary_path):
    """Return an Overpass 'poly' filter string ("lat lon lat lon ...") for
    the parliamentary_constituency feature in a boundary.geojson."""
    with open(boundary_path) as f:
        gj = json.load(f)
    pc = next(
        (f for f in gj["features"] if f["properties"].get("feature_type") == "parliamentary_constituency"),
        None,
    )
    if pc is None:
        raise RuntimeError(f"no parliamentary_constituency feature found in {boundary_path}")
    coords = pc["geometry"]["coordinates"][0]  # outer ring, [lon, lat] pairs
    return " ".join(f"{lat} {lon}" for lon, lat in coords)


def run_overpass_query(query, retries_per_mirror=2, sleep_between_s=8):
    """POST an Overpass QL query, trying each mirror with retries. Returns
    parsed JSON, or None if every attempt failed -- callers must handle
    None explicitly (never silently proceed as if it succeeded)."""
    for attempt in range(retries_per_mirror):
        for endpoint in OVERPASS_MIRRORS:
            req = urllib.request.Request(
                endpoint,
                data=f"data={urllib.parse.quote(query)}".encode("utf-8"),
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
            )
            try:
                with urllib.request.urlopen(req, timeout=150) as resp:
                    return json.loads(resp.read())
            except Exception as e:
                print(f"[lib_geocode] {endpoint} attempt {attempt+1} failed: {type(e).__name__}: {e}")
                time.sleep(sleep_between_s)
    return None


def geocode_terms_in_poly(terms, poly, batch_size=30, pause_s=12):
    """Batched name search for many terms at once, scoped to the poly filter.
    Returns the raw list of matched Overpass elements (nodes/ways with
    'out center' geometry) across all batches. Batching keeps individual
    queries small enough to avoid the timeouts a single giant regex
    alternation tends to trigger."""
    import re
    elements = []
    esc_terms = [re.escape(t) for t in terms]
    for i in range(0, len(esc_terms), batch_size):
        batch = esc_terms[i:i + batch_size]
        alt = "|".join(batch)
        query = f'''[out:json][timeout:100];
        (
          node["name"~"{alt}",i](poly:"{poly}");
          way["name"~"{alt}",i](poly:"{poly}");
        );
        out center;'''
        body = run_overpass_query(query)
        if body:
            elements.extend(body.get("elements", []))
        else:
            print(f"[lib_geocode] WARNING: batch {i // batch_size + 1} failed on every mirror -- terms in it won't be geocoded")
        time.sleep(pause_s)
    return elements


def best_match(term, elements):
    """Pick the best-matching element for one term: word-boundary match
    (never bare substring -- 'Minto' matching inside 'Badminton' is exactly
    the bug this guards against), preferring an exact name match, then a
    name that starts with the term, then the shortest name."""
    import re
    pat = re.compile(r"\b" + re.escape(term.lower()) + r"\b")
    candidates = [e for e in elements if pat.search((e.get("tags", {}).get("name") or "").lower())]
    if not candidates:
        return None

    def score(e):
        name = e.get("tags", {}).get("name") or ""
        return (name.lower() != term.lower(), not name.lower().startswith(term.lower()), len(name))

    candidates.sort(key=score)
    best = candidates[0]
    if best["type"] == "node":
        lat, lon = best.get("lat"), best.get("lon")
    else:
        c = best.get("center", {})
        lat, lon = c.get("lat"), c.get("lon")
    return {"name": best["tags"].get("name"), "lat": lat, "lon": lon, "n_candidates": len(candidates), "osm_type": best["type"]}
