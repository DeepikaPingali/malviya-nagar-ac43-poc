#!/usr/bin/env bash
# fetch_boundary.sh
#
# Extracts the Malviya Nagar (Delhi) assembly constituency polygon from
# datameet/maps and writes data/boundary.geojson.
#
# Pipeline:
#   1. Sparse-clone datameet/maps (assembly-constituencies/ only -- the repo
#      is ~175MB total, we only need one shapefile).
#   2. ogrinfo the shapefile to confirm field names BEFORE filtering on them.
#      Source schemas change; asserting first fails loudly instead of
#      silently returning zero features.
#   3. ogr2ogr to extract the one matching feature, reprojected to EPSG:4326.
#   4. Simplify with mapshaper if available, else fall back to ogr2ogr's
#      Douglas-Peucker simplify and say so in the provenance note.
#   5. Stamp _source / _fetched_at / _status and write the final file.
#
# NOTE ON AC NUMBER: the request that spawned this pipeline referred to
# Malviya Nagar as "AC-46". The datameet/maps shapefile lists it as AC_NO=43
# (Chhatarpur is 46 in Delhi's official sequence). We match on AC_NAME +
# ST_NAME (not AC_NO) so the extraction doesn't depend on that discrepancy,
# and we record the actual AC_NO found in the source as provenance.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RAW_DIR="$ROOT_DIR/data/raw"
DATA_DIR="$ROOT_DIR/data"
CLONE_DIR="$RAW_DIR/datameet-maps"
REPO_URL="https://github.com/datameet/maps.git"
SHP="$CLONE_DIR/assembly-constituencies/India_AC.shp"

ST_NAME="DELHI"
AC_NAME="Malviya Nagar"
REQUESTED_AC_NO="46"   # as given in the original request, kept for the record

SOURCE_LABEL="datameet/maps assembly-constituencies/India_AC.shp (github.com/datameet/maps)"
FETCHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

OUT_SCHEMA="$RAW_DIR/india_ac_schema.txt"
OUT_EXTRACTED="$RAW_DIR/boundary_extracted.geojson"
OUT_SIMPLIFIED="$RAW_DIR/boundary_simplified.geojson"
OUT_FINAL="$DATA_DIR/boundary.geojson"

mkdir -p "$RAW_DIR" "$DATA_DIR"

log() { echo "[fetch_boundary] $*"; }

# --- Step 1: sparse clone (or update) datameet/maps ------------------------
if [ -d "$CLONE_DIR/.git" ]; then
  log "existing clone found, fetching latest master"
  git -C "$CLONE_DIR" fetch --depth 1 origin master
  git -C "$CLONE_DIR" checkout master
  git -C "$CLONE_DIR" reset --hard origin/master
else
  log "sparse-cloning $REPO_URL (assembly-constituencies/ only)"
  rm -rf "$CLONE_DIR"
  git clone --depth 1 --filter=blob:none --no-checkout --quiet "$REPO_URL" "$CLONE_DIR"
  (
    cd "$CLONE_DIR"
    git sparse-checkout init --cone
    git sparse-checkout set assembly-constituencies
    git checkout master --quiet
  )
fi

COMMIT_SHA="$(git -C "$CLONE_DIR" rev-parse --short HEAD)"
log "using datameet/maps @ $COMMIT_SHA"

if [ ! -f "$SHP" ]; then
  log "ERROR: expected shapefile not found at $SHP -- repo layout may have changed"
  exit 1
fi

# --- Step 2: inspect schema BEFORE filtering --------------------------------
log "running ogrinfo to confirm field names before filtering"
ogrinfo -so "$SHP" India_AC | tee "$OUT_SCHEMA" >/dev/null

for required_field in ST_NAME AC_NAME AC_NO; do
  if ! grep -q "^${required_field}:" "$OUT_SCHEMA"; then
    log "ERROR: expected field '$required_field' not present in source schema (see $OUT_SCHEMA)"
    log "source schema changed -- refusing to guess a substitute field name"
    exit 1
  fi
done
log "confirmed fields ST_NAME, AC_NAME, AC_NO exist (full schema: $OUT_SCHEMA)"

# --- Step 3: extract the one matching feature -------------------------------
log "extracting ST_NAME='$ST_NAME' AC_NAME='$AC_NAME' with ogr2ogr, reprojecting to EPSG:4326"
rm -f "$OUT_EXTRACTED"
ogr2ogr -f GeoJSON -t_srs EPSG:4326 \
  -where "ST_NAME = '${ST_NAME}' AND AC_NAME = '${AC_NAME}'" \
  "$OUT_EXTRACTED" "$SHP"

FEATURE_COUNT="$(python3 -c "
import json, sys
print(len(json.load(open(sys.argv[1]))['features']))
" "$OUT_EXTRACTED")"
if [ "$FEATURE_COUNT" != "1" ]; then
  log "ERROR: expected exactly 1 matching feature, got $FEATURE_COUNT"
  exit 1
fi

ACTUAL_AC_NO="$(python3 -c "
import json, sys
print(json.load(open(sys.argv[1]))['features'][0]['properties']['AC_NO'])
" "$OUT_EXTRACTED")"
log "extracted 1 feature, source AC_NO=$ACTUAL_AC_NO (request referred to AC-$REQUESTED_AC_NO -- see note below)"

# --- Step 4: simplify --------------------------------------------------------
if command -v mapshaper >/dev/null 2>&1; then
  log "simplifying with mapshaper (10% retained, keep-shapes)"
  mapshaper "$OUT_EXTRACTED" -simplify 10% keep-shapes -o format=geojson force "$OUT_SIMPLIFIED"
  SIMPLIFY_METHOD="mapshaper -simplify 10% keep-shapes"
elif command -v npx >/dev/null 2>&1 && npx --yes -q mapshaper --version >/dev/null 2>&1; then
  log "simplifying with mapshaper via npx (10% retained, keep-shapes)"
  npx --yes mapshaper "$OUT_EXTRACTED" -simplify 10% keep-shapes -o format=geojson force "$OUT_SIMPLIFIED"
  SIMPLIFY_METHOD="mapshaper (via npx) -simplify 10% keep-shapes"
else
  log "WARNING: mapshaper not available on this machine (no node/npm) -- falling back to ogr2ogr -simplify"
  ogr2ogr -f GeoJSON -simplify 0.0001 "$OUT_SIMPLIFIED" "$OUT_EXTRACTED"
  SIMPLIFY_METHOD="ogr2ogr -simplify 0.0001deg (Douglas-Peucker; mapshaper unavailable, install node/npm to use mapshaper instead)"
fi
log "simplify method: $SIMPLIFY_METHOD"

# --- Step 5: stamp provenance and write final file --------------------------
python3 - "$OUT_SIMPLIFIED" "$OUT_FINAL" "$SOURCE_LABEL @ $COMMIT_SHA" "$FETCHED_AT" "$SIMPLIFY_METHOD" "$ACTUAL_AC_NO" "$REQUESTED_AC_NO" "$ROOT_DIR/scripts" <<'PYEOF'
import json
import sys

in_path, out_path, source, fetched_at, simplify_method, actual_ac_no, requested_ac_no, scripts_dir = sys.argv[1:9]
sys.path.insert(0, scripts_dir)
from lib_provenance import stamp_feature_collection, STATUS_OK, STATUS_NEEDS_VERIFICATION

with open(in_path) as f:
    gj = json.load(f)

note = (
    f"simplify method: {simplify_method}. "
    f"AC_NO in source = {actual_ac_no}; original request referred to AC-{requested_ac_no}; "
    f"matched by AC_NAME='Malviya Nagar' + ST_NAME='DELHI', not by AC number."
)
status = STATUS_OK if actual_ac_no == requested_ac_no else STATUS_NEEDS_VERIFICATION
stamp_feature_collection(gj, source=source, status=status, fetched_at=fetched_at, note=note)

with open(out_path, "w") as f:
    json.dump(gj, f, indent=2)

print(f"[fetch_boundary] wrote {out_path} (_status={status})")
PYEOF

log "done -> $OUT_FINAL"
