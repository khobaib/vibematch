"""
geocode_hostels.py

Adds real latitude/longitude coordinates to every hostel in hostels.json,
using OpenStreetMap's Nominatim geocoding API (https://nominatim.org/).

Why Nominatim instead of Google Places API:
- Free, no API key, no billing account needed - appropriate for this phase,
  where the goal is validating *functionality* (does distance-based nearby
  search work at all), not production-scale accuracy or volume.
- Tradeoff: lower precision than Google Places, and a strict fair-use rate
  limit (max 1 request/second, enforced by pacing below). Fine for a
  one-time backfill of ~250 unique locations; would need revisiting (e.g.
  Google Places, or a paid geocoder) if this becomes a production data
  pipeline running continuously - see DECISIONS_LOG.md's existing
  "Location proximity matching is not distance-aware" entry.

Why geocode per unique (city, region, country) rather than per hostel:
- Nominatim's free-text search is unreliable at finding a specific small
  business by name (it's built for places, not most businesses) - asking
  it for "Roy's Villa Hostel, Krabi" is much more likely to fail or return
  a wrong match than asking for "Krabi, Thailand".
- ~475 hostels collapse into ~250 unique places, so geocoding once per
  place and reusing that coordinate for every hostel there is both cheaper
  (fewer requests against a 1 req/sec limit) and more reliable.
- This gives town-center-level precision, not exact-building precision -
  correct for the actual goal here (which nearby town has hostels?), not
  for walking-distance-within-a-town accuracy, which is a different,
  later-phase problem.

This script is deliberately split into two independent, resumable steps,
matching the pattern used in embed_vibe_profiles.py:

  1. geocode_locations() - looks up every unique (city, region, country)
     combo found in hostels.json, one at a time, paced at ~1.1s between
     requests. Results (and permanent failures) are cached to
     location_coords_cache.json after every single lookup, so a Ctrl+C or
     a crash loses at most one lookup, and re-running the script skips
     everything already resolved.

  2. apply_coords_to_hostels() - reads that cache and writes
     hostel["location"]["lat"] / ["lng"] into hostels.json for every
     hostel whose location was successfully geocoded. Hostels whose place
     could not be geocoded at all are left with lat/lng = null and are
     printed at the end for manual follow-up (e.g. fixing a typo'd city
     name, or geocoding by hand via Google Maps).

Run it with no arguments: `python geocode_hostels.py`
Safe to re-run any time (e.g. after adding new hostels) - it only makes
network requests for locations not already in the cache.
"""

import json
import os
import time
import urllib.parse
import urllib.request

HOSTELS_PATH = os.path.join(os.path.dirname(__file__), "hostels.json")
CACHE_PATH = os.path.join(os.path.dirname(__file__), "location_coords_cache.json")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Nominatim's usage policy (https://operations.osmfoundation.org/policies/nominatim/)
# requires a real identifying User-Agent and caps free use at 1 request/second.
# 1.1s gives a small safety margin.
SECONDS_BETWEEN_REQUESTS = 1.1
USER_AGENT = "VibeMatch-Hostel-Geocoder/1.0 (personal project, contact: khobaib@gmail.com)"


def load_hostels():
    with open(HOSTELS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_hostels(hostels):
    with open(HOSTELS_PATH, "w", encoding="utf-8") as f:
        json.dump(hostels, f, indent=2)


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def location_key(city, region, country):
    return f"{city}|{region}|{country}"


def unique_locations(hostels):
    seen = {}
    for h in hostels:
        city = h.get("city") or ""
        region = h.get("region") or ""
        country = h.get("country") or ""
        key = location_key(city, region, country)
        seen.setdefault(key, (city, region, country))
    return seen


def nominatim_lookup(query: str):
    """Single Nominatim call. Returns (lat, lon, display_name) or None."""
    url = f"{NOMINATIM_URL}?{urllib.parse.urlencode({'q': query, 'format': 'jsonv2', 'limit': 1})}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        results = json.load(resp)
    if not results:
        return None
    r = results[0]
    return float(r["lat"]), float(r["lon"]), r.get("display_name")


def geocode_one(city, region, country):
    """
    Tries progressively broader queries so a slightly-off region name
    (e.g. an unusual province spelling) doesn't sink the whole lookup:
    1. "city, region, country"
    2. "city, country"           (drop region)
    3. "region, country"         (fall back to just the region/province)
    Returns (lat, lon, display_name, query_used) or None if all fail.
    """
    candidates = []
    if city and region and country:
        candidates.append(f"{city}, {region}, {country}")
    if city and country:
        candidates.append(f"{city}, {country}")
    if region and country:
        candidates.append(f"{region}, {country}")

    for query in candidates:
        try:
            result = nominatim_lookup(query)
        except Exception as e:
            print(f"    error querying {query!r}: {e}")
            result = None
        time.sleep(SECONDS_BETWEEN_REQUESTS)
        if result:
            lat, lon, display_name = result
            return lat, lon, display_name, query

    return None


def geocode_locations():
    hostels = load_hostels()
    locations = unique_locations(hostels)
    cache = load_cache()

    to_resolve = {k: v for k, v in locations.items() if k not in cache}

    print(f"{len(locations)} unique locations found in hostels.json.")
    print(f"{len(cache)} already cached from a previous run.")
    print(f"{len(to_resolve)} left to geocode this run.\n")

    if not to_resolve:
        print("Nothing left to geocode.")
        return

    for i, (key, (city, region, country)) in enumerate(to_resolve.items(), 1):
        label = ", ".join(p for p in (city, region, country) if p)
        print(f"[{i}/{len(to_resolve)}] {label} ...", end=" ")

        result = geocode_one(city, region, country)
        if result:
            lat, lon, display_name, query_used = result
            cache[key] = {
                "lat": lat,
                "lon": lon,
                "display_name": display_name,
                "query_used": query_used,
                "found": True,
            }
            print(f"OK ({lat:.4f}, {lon:.4f}) via {query_used!r}")
        else:
            cache[key] = {"found": False}
            print("NOT FOUND")

        save_cache(cache)  # persist after every single lookup

    resolved = sum(1 for v in cache.values() if v.get("found"))
    print(f"\nDone geocoding. {resolved}/{len(cache)} locations resolved.")
    print(f"Cache written to: {CACHE_PATH}")


def apply_coords_to_hostels():
    hostels = load_hostels()
    cache = load_cache()

    updated = 0
    unresolved_hostels = []

    for h in hostels:
        city = h.get("city") or ""
        region = h.get("region") or ""
        country = h.get("country") or ""
        key = location_key(city, region, country)
        entry = cache.get(key)

        if "location" not in h or not isinstance(h["location"], dict):
            h["location"] = {}

        if entry and entry.get("found"):
            h["location"]["lat"] = entry["lat"]
            h["location"]["lng"] = entry["lon"]
            updated += 1
        else:
            h["location"].setdefault("lat", None)
            h["location"].setdefault("lng", None)
            unresolved_hostels.append((h["id"], h["name"], city, region, country))

    save_hostels(hostels)

    print(f"Applied coordinates to {updated}/{len(hostels)} hostels.")
    print(f"Written to: {HOSTELS_PATH}")

    if unresolved_hostels:
        print(f"\n{len(unresolved_hostels)} hostels could NOT be geocoded "
              f"(left with lat/lng = null) - review manually:")
        for id_, name, city, region, country in unresolved_hostels:
            print(f"  id={id_} {name!r} | {city}, {region}, {country}")


def main():
    geocode_locations()
    print()
    apply_coords_to_hostels()


if __name__ == "__main__":
    main()
