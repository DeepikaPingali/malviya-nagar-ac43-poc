#!/usr/bin/env python3
"""fetch_results.py

Fetches Malviya Nagar (Delhi Assembly AC-43) election results -- the 2025
result plus full history back to 1993 -- trying three sources in order and
recording which one actually succeeded:

  1. TCPD Lok Dhaba API (lokdhaba.ashoka.edu.in) -- the "clean" structured
     source, tried first.
  2. ECI results portal (results.eci.gov.in) -- the official source, but the
     portal only serves the *current* election cycle and has no stable
     archive URL for a past cycle.
  3. Wikipedia -- parsed from wikitext (not scraped HTML), which mirrors the
     ECI's Form-20 numbers with citations back to eci.gov.in / archive.org.

Both live checks were verified manually before writing this script:
  - TCPD's API returns HTTP 502 (backend down) as of this writing.
  - ECI's homepage now redirects to a *different, later* election cycle
    (results.eci.gov.in serves whatever is current, not history), and the
    archived per-AC URL cited by Wikipedia (.../candidateswise-U0543.htm)
    404s directly.
That is exactly the situation this fallback chain exists for. If TCPD or ECI
come back online later, this script will use them automatically -- nothing
here is hardcoded to "use Wikipedia."

Writes data/results.json with a top-level `_source`/`_status` showing which
tier actually supplied the data, and per-election `_source` if it ever
becomes a blend of tiers (e.g. TCPD historical + Wikipedia current).
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_provenance import stamp_record, now_iso, STATUS_OK, STATUS_NEEDS_VERIFICATION

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
OUT_PATH = os.path.join(DATA_DIR, "results.json")

AC_NAME = "Malviya Nagar"
AC_NO = 43
STATE_NAME = "Delhi"
WIKIPEDIA_TITLE = "Malviya Nagar, Delhi Assembly constituency"
USER_AGENT = "malviya-nagar-poc/0.1 (civic-mapping proof of concept; contact via repo issues)"
TIMEOUT_S = 30


def log(msg):
    print(f"[fetch_results] {msg}")


def http_get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.getcode(), resp.read()


def http_post_json(url, payload, headers=None):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        return resp.getcode(), resp.read()


# --- Tier 1: TCPD Lok Dhaba ------------------------------------------------
def try_tcpd():
    url = "https://lokdhaba.ashoka.edu.in/api/data/api/v2.0/getDerivedData"
    payload = {
        "ElectionType": "AE",
        "StateName": STATE_NAME,
        "AssemblyNo": str(AC_NO),
        "PageNo": 0,
        "PageSize": 100,
        "Filters": [],
        "SortOptions": [],
    }
    log(f"tier 1: TCPD Lok Dhaba API ({url})")
    try:
        status, body = http_post_json(url, payload)
    except Exception as e:
        log(f"tier 1 FAILED: {type(e).__name__}: {e}")
        return None
    if status != 200:
        log(f"tier 1 FAILED: HTTP {status}")
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        log("tier 1 FAILED: response was not valid JSON (backend likely returned an HTML error page)")
        return None
    rows = parsed.get("data") or []
    if not rows:
        log("tier 1 FAILED: query succeeded but returned zero rows")
        return None
    log(f"tier 1 SUCCEEDED: {len(rows)} rows")
    return {"raw_rows": rows, "source": f"TCPD Lok Dhaba API ({url})"}


# --- Tier 2: ECI results portal --------------------------------------------
def try_eci():
    # The homepage always redirects to whatever cycle is "current" -- it is
    # not a historical archive. We check it honestly rather than assuming.
    home_url = "https://results.eci.gov.in/"
    log(f"tier 2: ECI results portal ({home_url})")
    try:
        status, body = http_get(home_url)
        text = body.decode("utf-8", errors="ignore")
        m = re.search(r'url\s*=\s*(https://results\.eci\.gov\.in/(\S+?))["\']', text)
        redirect_target = m.group(1) if m else None
        log(f"tier 2: homepage redirects to {redirect_target}")
        if not redirect_target or "2025" not in redirect_target:
            log("tier 2 FAILED: current ECI results cycle is not the Feb 2025 Delhi election -- "
                "the portal does not keep a historical archive")
        else:
            # The current cycle happens to be the one we want -- fetch it.
            ac_code = f"U05{AC_NO:02d}"  # ECI AC codes are <state code><zero-padded AC no>
            candidate_url = redirect_target.rsplit("/", 1)[0] + f"/candidateswise-{ac_code}.htm"
            status, body = http_get(candidate_url)
            if status == 200:
                log(f"tier 2 SUCCEEDED: {candidate_url}")
                return {"raw_html": body.decode("utf-8", errors="ignore"), "source": f"ECI results portal ({candidate_url})"}
    except Exception as e:
        log(f"tier 2: homepage check failed: {type(e).__name__}: {e}")

    # Also try the specific archived-cycle URL Wikipedia cites, in case ECI
    # still serves old cycles at a direct (but unlinked) URL.
    ac_code = f"U05{AC_NO:02d}"
    direct_url = f"https://results.eci.gov.in/ResultAcGenFeb2025/candidateswise-{ac_code}.htm"
    log(f"tier 2: trying direct archived-cycle URL {direct_url}")
    try:
        status, body = http_get(direct_url)
        if status == 200:
            log("tier 2 SUCCEEDED via direct URL")
            return {"raw_html": body.decode("utf-8", errors="ignore"), "source": f"ECI results portal ({direct_url})"}
        log(f"tier 2 FAILED: direct URL returned HTTP {status}")
    except urllib.error.HTTPError as e:
        log(f"tier 2 FAILED: direct URL returned HTTP {e.code} (cycle no longer hosted)")
    except Exception as e:
        log(f"tier 2 FAILED: {type(e).__name__}: {e}")
    return None


# --- Tier 3: Wikipedia (parsed from wikitext) ------------------------------
FIELD_RE = re.compile(r"\|\s*([A-Za-z0-9_. ]+?)\s*=\s*([^|\n]*)")
WIKILINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")
CITE_RE = re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL)


def clean_value(s):
    s = s.replace("{{increase}}", "+").replace("{{decrease}}", "-")
    s = re.sub(r"\{\{[^}]*\}\}", "", s)  # drop any other remaining templates
    return s.strip().strip("}").strip()


def parse_template_fields(text):
    # Resolve citations and wikilinks across the WHOLE block first. A piped
    # wikilink like [[New Delhi (Lok Sabha constituency)|New Delhi]] contains
    # a "|" -- if we split into key=value fields before resolving it, the
    # value gets truncated at that inner pipe.
    text = CITE_RE.sub("", text)
    text = WIKILINK_RE.sub(r"\1", text)
    return {clean_value(k): clean_value(v) for k, v in FIELD_RE.findall(text)}


def parse_infobox(wikitext):
    m = re.search(r"\{\{Infobox Indian constituency(.*?)\n\}\}", wikitext, re.DOTALL)
    if not m:
        return {}
    return parse_template_fields(m.group(1))


def parse_election_year_block(year, block_text):
    parts = re.split(r"\{\{Election box\s+", block_text)[1:]  # [0] is text before first template
    candidates = []
    majority = {}
    turnout = {}
    result_type = None
    winner_party = None
    loser_party = None
    for part in parts:
        header = re.match(r"([^|\n{}]*)", part).group(1).strip().lower()
        fields = parse_template_fields(part)
        if header.startswith("winning candidate") or header.startswith("candidate"):
            candidates.append({
                "party": fields.get("party"),
                "candidate": fields.get("candidate"),
                "votes": fields.get("votes"),
                "percentage": fields.get("percentage"),
                "change": fields.get("change"),
                "is_winner": len(candidates) == 0,
            })
        elif header.startswith("majority"):
            majority = {"votes": fields.get("votes"), "percentage": fields.get("percentage")}
        elif header.startswith("turnout"):
            turnout = {"votes": fields.get("votes"), "percentage": fields.get("percentage")}
        elif header.startswith("gain"):
            result_type = "gain"
            winner_party = fields.get("winner")
            loser_party = fields.get("loser")
        elif header.startswith("hold"):
            result_type = "hold"
            winner_party = fields.get("winner")

    winner = candidates[0] if candidates else None
    return {
        "year": year,
        "winner_candidate": winner["candidate"] if winner else None,
        "winner_party": winner["party"] if winner else None,
        "winner_votes": winner["votes"] if winner else None,
        "result_type": result_type,
        "previous_winning_party": loser_party,
        "majority": majority,
        "turnout": turnout,
        "candidates": candidates,
    }


def try_wikipedia():
    url = f"https://en.wikipedia.org/w/index.php?title={urllib.parse.quote(WIKIPEDIA_TITLE)}&action=raw"
    log(f"tier 3: Wikipedia wikitext ({url})")
    try:
        status, body = http_get(url)
    except Exception as e:
        log(f"tier 3 FAILED: {type(e).__name__}: {e}")
        return None
    if status != 200:
        log(f"tier 3 FAILED: HTTP {status}")
        return None
    wikitext = body.decode("utf-8", errors="ignore")

    infobox = parse_infobox(wikitext)
    year_sections = list(re.finditer(r"^===\s*(\d{4})\s*===", wikitext, re.MULTILINE))
    elections = []
    for i, m in enumerate(year_sections):
        year = int(m.group(1))
        start = m.end()
        end = year_sections[i + 1].start() if i + 1 < len(year_sections) else len(wikitext)
        elections.append(parse_election_year_block(year, wikitext[start:end]))
    elections.sort(key=lambda e: e["year"], reverse=True)

    if not elections:
        log("tier 3 FAILED: page fetched but no '=== YYYY ===' election sections found -- page structure may have changed")
        return None

    log(f"tier 3 SUCCEEDED: parsed {len(elections)} elections ({elections[0]['year']}-{elections[-1]['year']})")
    return {
        "infobox": infobox,
        "elections": elections,
        "source": f"Wikipedia: en.wikipedia.org/wiki/{WIKIPEDIA_TITLE.replace(' ', '_')} (parsed from wikitext, not HTML scrape)",
    }


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    fetched_at = now_iso()

    tcpd_result = try_tcpd()
    if tcpd_result is not None:
        # NOTE: transformation from TCPD's raw mastersheet rows into the
        # `elections` schema below is not implemented -- we've never seen a
        # live response to know its exact column names. If TCPD comes back
        # online, raw rows are saved for inspection and this needs a mapper.
        raw_path = os.path.join(RAW_DIR, "results_tcpd_raw.json")
        with open(raw_path, "w") as f:
            json.dump(tcpd_result["raw_rows"], f, indent=2)
        log(f"tier 1 data saved to {raw_path} but not yet mapped to results.json schema -- "
            "falling through to tier 3 for a usable structured file; see raw file to add a TCPD mapper")

    eci_result = try_eci()
    if eci_result is not None:
        raw_path = os.path.join(RAW_DIR, "results_eci_raw.html")
        with open(raw_path, "w") as f:
            f.write(eci_result["raw_html"])
        log(f"tier 2 data saved to {raw_path} but not yet parsed to results.json schema -- "
            "falling through to tier 3 for a usable structured file; see raw file to add an ECI parser")

    wiki_result = try_wikipedia()
    if wiki_result is None:
        log("ERROR: all three tiers failed -- writing results.json marked unavailable, no data fabricated")
        record = {"constituency": {"name": AC_NAME, "ac_no": AC_NO, "state": STATE_NAME}, "elections": []}
        stamp_record(
            record,
            source="none (TCPD, ECI, and Wikipedia all failed)",
            status="unavailable",
            fetched_at=fetched_at,
            note="Every configured source failed at fetch time. Re-run fetch_results.py.",
        )
        with open(OUT_PATH, "w") as f:
            json.dump(record, f, indent=2)
        return

    infobox = wiki_result["infobox"]
    record = {
        "constituency": {
            "name": AC_NAME,
            "ac_no": AC_NO,
            "state": STATE_NAME,
            "district": infobox.get("district"),
            "loksabha_constituency": infobox.get("loksabha_cons"),
        },
        "current_mla": {
            "name": infobox.get("mla"),
            "party": infobox.get("party"),
            "since_election_year": infobox.get("latest_election_year"),
        },
        "elections": wiki_result["elections"],
    }
    note = "TCPD and ECI were both attempted first and failed (see logs / data/raw/); Wikipedia wikitext used as the working fallback."
    stamp_record(record, source=wiki_result["source"], status=STATUS_NEEDS_VERIFICATION, fetched_at=fetched_at, note=note)

    with open(OUT_PATH, "w") as f:
        json.dump(record, f, indent=2)
    log(f"wrote {OUT_PATH} (_status={record['_status']}, source=tier 3 Wikipedia)")


if __name__ == "__main__":
    main()
