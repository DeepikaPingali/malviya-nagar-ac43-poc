# Contributing

## What this is

A civic-transparency map, one Lok Sabha constituency at a time. Every
claim on the map -- a colony's tenure status, how many hours a day water
runs, a waterlogging spot, a named pollution source -- carries its own
source, its own confidence level, and an honest tag for how good its
geometry is. The point of this project is that you can click any shape or
pin and see exactly where the claim came from and how sure we are of it.
That discipline is the entire value of the site; contributing here means
signing up for it, not just adding a pin to a map.

This is a **technical contribution path** right now: you write a script
that fetches/derives data and the GeoJSON it produces, together, as a pair.
A more form-based path for non-technical contributors may come later; for
now, if you're comfortable with Python and a `git` PR, you're the audience.

## Ground rules (non-negotiable)

- **Never fabricate a precise location.** Every feature's `geometry_basis`
  must honestly be `"surveyed"` (a real, checkable boundary source --
  official shapefile, OSM admin relation, etc.), `"approximate"`
  (hand-drawn, must render visibly different from a real boundary), or
  `"point"` (a single representative location, not a boundary claim).
- **Every feature carries its own source.** Not the file, not the script --
  the feature. `_source` + `_source_url` are required on every single one.
  If there's genuinely no document (you observed something yourself), use
  `_source: "Field observation by <name>, <date>"` and say so.
- **Uncertain → `needs_verification`, not `"ok"`.** Every feature you
  contribute starts as `_status: "needs_verification"`. Only a reviewer who
  has independently corroborated it upgrades that at merge time. Don't
  self-certify.
- **If a source says nothing about an area, leave it out.** Don't guess to
  fill a gap. An empty theme file with an honest `_theme_note` explaining
  why is a legitimate, better answer than a fabricated feature.
- **Geocode against the real constituency polygon, never a bounding box.**
  A bbox spills into neighbouring constituencies and produces false-positive
  name collisions -- this project has hit that repeatedly in practice (a
  "Sant Nagar" bbox-matched near one part of Delhi turned out to be a
  different, unrelated Sant Nagar elsewhere in the city; the actual
  boundary polygon would have excluded it). Use `scripts/lib_geocode.py`.

## Repo layout

```
/pcs/<pc-id>/                  -- one folder per parliamentary constituency (kebab-case, e.g. new-delhi)
    config.json                -- display name, state, shapefile lookup key, map center/zoom
    theme_colors.json          -- THIS PC's status_tag -> color per theme (local government schemes vary per city, this doesn't)
    boundary.geojson           -- generated, never hand-edited
    data/
        osm_roads.geojson, osm_metro.geojson, osm_civic.geojson, manifest.json  -- generated
        themes/
            water.geojson, land_housing.geojson, ...  -- one FeatureCollection per theme
    scripts/                    -- THIS PC's own fetch_<source>.py scripts (source-specific, not reusable elsewhere)
/pcs/index.json                 -- registry of onboarded PCs, drives the PC picker
/scripts/                       -- shared, PC-agnostic: fetch_boundary_pc.py, fetch_osm.py,
                                    validate_contribution.py, new_pc_scaffold.py, lib_geocode.py, lib_provenance.py
/schema/
    feature.schema.json         -- universal required fields, every theme, every PC
    themes/<theme>.schema.json  -- optional, theme-specific structured fields (universal across PCs --
                                    see "Two kinds of vocabulary" below)
/examples/basic-contribution/   -- a tiny, complete, runnable example -- start here
/index.html                     -- one shared, PC-aware frontend
```

**Naming**: PC folder ids are kebab-case matching the official Lok Sabha PC
name (`new-delhi`, `mumbai-north`) -- no state prefix needed, PC names
don't collide nationally. Theme files are snake_case
(`land_housing.geojson`, `roads_congestion.geojson`). Scripts are named
`fetch_<source>_<optional-year>.py` -- one script per *source document*,
not per theme, since one source often feeds several themes (e.g. Delhi's
DJB Summer Action Plans feed both `water` and `sanitation`).

## Two kinds of vocabulary

- **Structured field *names and types*** (e.g. `water`'s
  `supply_hours_per_day: number`) are universal across every PC --
  defined once in `schema/themes/<theme>.schema.json`. This is what makes
  cross-city comparison possible at all.
- **`status_tag` *values*** are PC-specific, in each PC's
  `theme_colors.json`, because they encode local government schemes
  (Delhi's `land_housing` tags come from PM-UDAY; another city's would come
  from its own local housing scheme entirely). A genuinely new tag must be
  added there, with a color, in the same PR -- never invented silently.

## The required fields, on every feature, in every theme, in every PC

See `schema/feature.schema.json` for the authoritative, machine-checked
version. In short: `name`, `theme`, `claim`, `status_tag`, `confidence`,
`geometry_basis`, `_source`, `_source_url`, `_fetched_at`, `_status`.
`schema/themes/<theme>.schema.json` (if one exists for your theme) lists
additional, recommended-not-required structured fields.

## How to contribute

### Adding a feature to an existing theme (the common case)

1. Read `examples/basic-contribution/` end to end -- run it, run the
   validator against it, see what a failure looks like.
2. Write `pcs/<pc-id>/scripts/fetch_<your-source>.py` following that
   pattern: geocode against the real PC polygon, build features satisfying
   the required schema, write to `pcs/<pc-id>/data/themes/<theme>.geojson`.
3. Run `python3 scripts/validate_contribution.py --pc <pc-id> --theme
   <theme>` locally and fix everything it flags before opening a PR.
4. Open a PR with **both** the script and the data changes it produced.
   CI re-runs your script and diffs the result against what you submitted
   (best-effort, non-blocking if a source is briefly unreachable) --
   scripts that don't actually reproduce their claimed output get flagged.
5. A human reviews the script's logic and source, spot-checks a few claims
   against your cited source, and merges. Merging *is* publishing --
   GitHub Pages rebuilds from `main` automatically, there's no separate
   "go live" step.

### Onboarding a new theme within an existing PC

Same as above, but justify in the PR description **why this needs to be a
new theme rather than a new `status_tag` or field on an existing one** --
a new theme has real ongoing cost (a new color palette, a new legend
entry) and review should weigh that deliberately, not just check the JSON
is valid.

### Onboarding a whole new PC

1. `python3 scripts/new_pc_scaffold.py --id <id> --display-name "..." \
   --state "..." --shapefile-state "STATE NAME" --shapefile-pc-name "PC NAME"`
2. `python3 scripts/fetch_boundary_pc.py --state ... --pc-name "..." --out-dir pcs/<id>`
3. `python3 scripts/fetch_osm.py --out-dir pcs/<id>`
4. `python3 scripts/build_themes_index.py --out-dir pcs/<id>`
5. Start writing `pcs/<id>/scripts/fetch_<source>.py` and filling in real,
   sourced theme files -- one claim at a time, same discipline as above.

## What a reviewer actually checks

1. CI's consolidated comment first (schema validity, `status_tag` vocab,
   in-boundary geometry check, reproducibility re-run) -- hard failures
   there get sent back before anything else is reviewed.
2. Does the script's source URL look legitimate? Does its parsing logic
   look sound?
3. Spot-check 2-3 claims against the actual cited source.
4. Is `_status` honestly `needs_verification` unless independently
   corroborated? Is `confidence` a reasonable self-rating, not overclaimed?
5. Merge, or request changes, or reject with a stated reason (rejected PRs
   stay visible -- transparency cuts both ways).
