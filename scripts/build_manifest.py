#!/usr/bin/env python3
"""build_manifest.py

Called by fetch_all.sh at the end of a pipeline run. Combines:
  1. which fetcher scripts ran and whether they exited cleanly, and
  2. what each resulting /data file's own provenance (_source/_status/
     _fetched_at/_note) actually says

into a single data/manifest.json, so a run's health can be checked without
re-reading every fetcher's log output.

Usage: build_manifest.py <data_dir> <run_at_iso> <steps_log_path>
where steps_log_path is a TSV of "name<TAB>exit_code<TAB>duration_seconds"
lines, one per fetcher step.
"""
import glob
import json
import os
import sys

DATA_DIR, RUN_AT, STEPS_LOG_PATH = sys.argv[1:4]


def read_steps(path):
    steps = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            name, exit_code, duration_s = line.split("\t")
            steps.append({
                "name": name,
                "exit_code": int(exit_code),
                "duration_s": int(duration_s),
                "ok": exit_code == "0",
            })
    return steps


def read_layers(data_dir):
    layers = []
    patterns = [os.path.join(data_dir, "*.geojson"), os.path.join(data_dir, "*.json")]
    paths = sorted(set(p for pat in patterns for p in glob.glob(pat)))
    for path in paths:
        filename = os.path.basename(path)
        if filename == "manifest.json":
            continue
        try:
            with open(path) as f:
                content = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            layers.append({"file": filename, "_status": "error", "_note": f"could not read/parse file: {e}"})
            continue
        layers.append({
            "file": filename,
            "_source": content.get("_source"),
            "_status": content.get("_status"),
            "_fetched_at": content.get("_fetched_at"),
            "_note": content.get("_note"),
            "feature_count": len(content.get("features", [])) if "features" in content else None,
        })
    return layers


def main():
    steps = read_steps(STEPS_LOG_PATH)
    layers = read_layers(DATA_DIR)

    any_step_failed = any(not s["ok"] for s in steps)
    any_layer_bad = any(l.get("_status") in ("unavailable", "needs_verification", "error") for l in layers)
    if any_step_failed or any_layer_bad:
        overall_status = "partial" if not any_step_failed else "failed"
    else:
        overall_status = "ok"

    manifest = {
        "pipeline_run_at": RUN_AT,
        "overall_status": overall_status,
        "steps": steps,
        "layers": layers,
    }

    out_path = os.path.join(DATA_DIR, "manifest.json")
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[build_manifest] wrote {out_path} (overall_status={overall_status})")


if __name__ == "__main__":
    main()
