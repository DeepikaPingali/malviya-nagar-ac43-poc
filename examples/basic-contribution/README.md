# A minimal, complete, runnable contribution example

This folder is a teaching example, not real data. `example_output.geojson`
describes a real hospital (Safdarjung Hospital, genuinely geocoded via
Overpass) but every claim/source field in it says `EXAMPLE` -- it is never
loaded by the live site and must never be copied verbatim into a real
theme file.

## What's here

- **`fetch_example.py`** -- the entire pattern every real `fetch_<source>.py`
  script in this repo follows, stripped to its smallest useful form:
  load the target PC's boundary polygon, geocode one real landmark against
  it (never a bounding box -- see `scripts/lib_geocode.py`'s docstring for
  why that matters), build one `Feature` with every required field, write
  it out.
- **`example_output.geojson`** -- what running the script produces.

## Run it yourself

```bash
cd examples/basic-contribution
python3 fetch_example.py
```

Then validate it:

```bash
cd ../..
python3 scripts/validate_contribution.py --pc new-delhi \
    --file examples/basic-contribution/example_output.geojson
```

**This will fail, on purpose:**

```
FAIL 'EXAMPLE -- Safdarjung Hospital (replace before submitting)':
  properties.theme is 'public_health', expected 'example_output'
  (must match the filename)
```

That's the validator correctly catching that this demo file isn't named
after its theme. In the real pipeline, `index.html` discovers theme layers
by filename (`data/themes/water.geojson` *is* the `water` theme) -- so a
real contribution's output file must be named `<theme>.geojson`, matching
`properties.theme` on every feature inside it. This example intentionally
keeps a distinct filename so nobody mistakes it for something that's
actually wired into the site. If you rename your own copy to
`public_health.geojson` before validating, this specific check passes.

## Turning this into a real contribution

1. Copy `fetch_example.py` into `pcs/<your-pc>/scripts/fetch_<your-source>.py`.
2. Replace the geocoding target and the theme with your own.
3. Replace every field marked `EXAMPLE` with a real value:
   - `claim` -- one line, plain English, what you're actually claiming.
   - `_source` / `_source_url` -- where this claim genuinely comes from. If
     there's no document (you saw it yourself), use
     `"Field observation by <your name>, <date>"` as `_source` and explain
     in `_source_url` there isn't one.
   - `status_tag` -- must be one of the values already listed for your
     theme in `pcs/<your-pc>/theme_colors.json`. If none fit, add a new one
     there (with a color) in the same PR -- don't invent one silently.
   - Any optional structured fields for your theme -- see
     `schema/themes/<theme>.schema.json` for what's recommended. Leave
     fields you genuinely don't know as `null`, don't guess.
4. Leave `confidence: "low"` or `"medium"` and `_status: "needs_verification"`
   as your defaults -- a reviewer decides if either gets upgraded at merge
   time, not you.
5. Write your output to `pcs/<your-pc>/data/themes/<theme>.geojson`
   (matching the theme, so the filename check above passes), open a PR,
   and let CI + a human review it. See `CONTRIBUTING.md` at the repo root
   for the full process.
