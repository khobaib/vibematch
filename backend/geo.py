"""
geo.py

Distance-based "nearby" support for location matching, built on top of the
real lat/lng coordinates added by geocode_hostels.py (see that file's
docstring for how/why those were generated).

This replaces the old text-only location matching's biggest gap: searching
a place with zero hostels in it (e.g. "Lovina" before any Lovina hostels
existed) used to return nothing at all, even though real hostels existed
a short distance away. See DECISIONS_LOG.md for the original bug report
and the design discussion behind this fix.

Two pieces live here:

1. haversine(lat1, lon1, lat2, lon2) - great-circle distance in km between
   two coordinates. Standard formula, no external dependencies.

2. resolve_place_coords(location) - turns a free-text place name (already
   lowercased and alias-resolved by matching.py's resolve_location_alias)
   into a single (lat, lon) anchor point, by looking it up against every
   city/region we already have real coordinates for.

DELIBERATE DESIGN CHOICE - no live geocoding at search time:
resolve_place_coords() only ever does a local dictionary lookup against
location_coords_cache.json (built once, offline, by geocode_hostels.py).
It never calls Nominatim live. Two reasons:
- Nominatim's usage policy caps free use at 1 request/second - fine for a
  one-time batch job, but not safe to depend on inside a live request path
  serving real traffic (a burst of concurrent searches could blow through
  that limit and get the app's requests throttled or blocked).
- Latency: a live geocoding call would add real, unpredictable time to
  every search that needs it, on top of the Claude and Voyage calls
  already in the critical path.
A location typed by a user that isn't recognized (not close to any known
city/region name) simply returns None here, and callers fall back to the
existing text-based region/country/continent matching. Growing the local
place vocabulary (e.g. adding a genuinely new place name someone searched)
is a deliberate, reviewed step - rerun geocode_hostels.py after adding the
place's hostels to hostels.json, same as any other data update - not an
automatic/live process. This mirrors the same phase-appropriate tradeoff
already made for LOCATION_ALIASES in matching.py: real, but intentionally
not fully automatic yet.
"""

import json
import math
import os

CACHE_PATH = os.path.join(os.path.dirname(__file__), "location_coords_cache.json")


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in kilometers."""
    R = 6371.0  # mean Earth radius, km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


_place_coords_cache = None  # lazy-built, module-level, so it's built once per process


def _build_place_coords_index() -> dict:
    """
    Reads location_coords_cache.json (keyed "city|region|country" ->
    {lat, lon, found, ...}) and builds a simpler lookup indexed by plain
    lowercased city name and plain lowercased region name, since that's
    what a user's search term actually looks like ("lovina", not
    "lovina|bali|indonesia").

    A region name (e.g. "bali") appears across many city entries - its
    coordinate here is the centroid (simple average) of every city found
    under that region, which is good enough for a "point somewhere in
    this region" anchor; it's not meant to be precise the way a specific
    city's coordinate is.
    """
    if not os.path.exists(CACHE_PATH):
        return {"by_city": {}, "by_region": {}}

    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        cache = json.load(f)

    by_city = {}
    region_points = {}  # region -> list of (lat, lon)

    for key, entry in cache.items():
        if not entry.get("found"):
            continue
        city, region, country = (key.split("|", 2) + ["", "", ""])[:3]
        lat, lon = entry["lat"], entry["lon"]

        city_key = city.strip().lower()
        if city_key and city_key not in by_city:
            by_city[city_key] = (lat, lon)

        region_key = region.strip().lower()
        if region_key:
            region_points.setdefault(region_key, []).append((lat, lon))

    by_region = {}
    for region_key, points in region_points.items():
        avg_lat = sum(p[0] for p in points) / len(points)
        avg_lon = sum(p[1] for p in points) / len(points)
        by_region[region_key] = (avg_lat, avg_lon)

    return {"by_city": by_city, "by_region": by_region}


def resolve_place_coords(location: str):
    """
    Looks up a free-text, already-lowercased/alias-resolved location
    string against known city names first, then known region names.
    Returns (lat, lon) or None if the place isn't recognized locally.
    """
    global _place_coords_cache
    if _place_coords_cache is None:
        _place_coords_cache = _build_place_coords_index()

    if not location:
        return None

    if location in _place_coords_cache["by_city"]:
        return _place_coords_cache["by_city"][location]

    if location in _place_coords_cache["by_region"]:
        return _place_coords_cache["by_region"][location]

    return None
