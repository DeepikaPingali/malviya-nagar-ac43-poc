#!/usr/bin/env bash
# fetch_all.sh
#
# Runs every fetcher in the pipeline, in order, and writes data/manifest.json
# summarizing which steps succeeded and what each output layer's own
# provenance says. Does NOT abort on the first failure -- a partial run
# (e.g. one flaky source) still produces a manifest showing exactly what
# happened, rather than leaving no record at all.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
DATA_DIR="$ROOT_DIR/data"
RUN_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STEPS_LOG="$(mktemp)"

mkdir -p "$DATA_DIR"
trap 'rm -f "$STEPS_LOG"' EXIT

run_step() {
  local name="$1"; shift
  echo "=== running $name ==="
  local start end code duration
  start="$(date +%s)"
  "$@"
  code=$?
  end="$(date +%s)"
  duration=$((end - start))
  printf "%s\t%s\t%s\n" "$name" "$code" "$duration" >> "$STEPS_LOG"
  if [ "$code" -eq 0 ]; then
    echo "=== $name OK (${duration}s) ==="
  else
    echo "=== $name FAILED (exit $code, ${duration}s) ==="
  fi
  echo
}

run_step "fetch_boundary.sh" bash "$SCRIPTS_DIR/fetch_boundary.sh"
run_step "fetch_osm.py" python3 "$SCRIPTS_DIR/fetch_osm.py"
run_step "fetch_results.py" python3 "$SCRIPTS_DIR/fetch_results.py"
run_step "fetch_mcd_wards.py" python3 "$SCRIPTS_DIR/fetch_mcd_wards.py"

echo "=== building manifest ==="
python3 "$SCRIPTS_DIR/build_manifest.py" "$DATA_DIR" "$RUN_AT" "$STEPS_LOG"

# Exit non-zero if any step failed, so CI/automation can detect it --
# the manifest itself is still written either way.
FAILED_COUNT=$(awk -F'\t' '$2 != 0 {c++} END {print c+0}' "$STEPS_LOG")
if [ "$FAILED_COUNT" -gt 0 ]; then
  echo "fetch_all.sh: $FAILED_COUNT step(s) failed -- see data/manifest.json for details"
  exit 1
fi
echo "fetch_all.sh: all steps completed successfully"
