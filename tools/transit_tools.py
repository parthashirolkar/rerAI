"""tools/transit_tools.py -- Transit proximity checker for rerAI.

Queries OpenStreetMap via the Overpass API to find nearby transit
infrastructure (metro stations, railway stations, bus stops/depots)
around a given lat/lon coordinate in Pune, India.

Uses only Python stdlib -- no additional dependencies required.
"""

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from langchain_core.tools import tool

from tools.geo import haversine_km

OVERPASS_API_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_TIMEOUT_SECS = 25


def _build_overpass_query(lat: float, lon: float, radius_m: int) -> str:
    """Build Overpass QL query for transit near a point in Pune.

    Bus stops are queried with a smaller radius (500m max) to avoid
    timeout due to the high density of bus stops in Pune.
    """
    bus_radius = min(radius_m, 500)

    return (
        f"[out:json][timeout:{DEFAULT_TIMEOUT_SECS}];\n"
        f"(\n"
        f'  node["railway"="station"]["station"="subway"]'
        f"(around:{radius_m},{lat},{lon});\n"
        f'  node["railway"="station"]["train"="yes"]'
        f"(around:{radius_m},{lat},{lon});\n"
        f'  node["highway"="bus_stop"]'
        f"(around:{bus_radius},{lat},{lon});\n"
        f'  node["amenity"="bus_station"]'
        f"(around:{radius_m},{lat},{lon});\n"
        f");\n"
        f"out body;"
    )


def _classify_element(tags: dict[str, str]) -> str:
    """Classify a transit element based on its OSM tags."""
    if tags.get("station") == "subway" or tags.get("subway") == "yes":
        return "metro_station"
    if tags.get("train") == "yes" or (
        tags.get("railway") == "station" and "station" not in tags
    ):
        return "railway_station"
    if tags.get("highway") == "bus_stop":
        return "bus_stop"
    if tags.get("amenity") == "bus_station":
        return "bus_station"
    return "unknown"


def _query_overpass(query: str) -> dict[str, Any]:
    """Execute an Overpass API query and return the parsed JSON response."""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_API_URL,
        data=data,
        headers={"User-Agent": "rerAI/0.1 (Pune permitting assistant)"},
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECS + 10) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _query_overpass_async(query: str) -> dict[str, Any]:
    """Async wrapper around _query_overpass to avoid blocking the event loop."""
    return await asyncio.to_thread(_query_overpass, query)


@tool
async def check_transit_proximity(
    lat: float, lon: float, radius_km: float = 2.0
) -> str:
    """Find nearby transit infrastructure around a given coordinate in Pune.

    Queries OpenStreetMap via the Overpass API for:
    - Metro stations (Pune Metro)
    - Railway stations (Indian Railways)
    - Bus stops and bus stations/depots

    Returns a JSON string with categorized results sorted by distance,
    including station names, distances, and lines/networks where available.

    Args:
        lat: Latitude of the query point (e.g. 18.5314)
        lon: Longitude of the query point (e.g. 73.8446)
        radius_km: Search radius in kilometers (default 2.0, max 5.0)
    """
    radius_km = min(radius_km, 5.0)
    radius_m = int(radius_km * 1000)

    query = _build_overpass_query(lat, lon, radius_m)

    try:
        result = await _query_overpass_async(query)
    except urllib.error.URLError as e:
        return json.dumps({"error": f"Overpass API request failed: {e}"})
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Failed to parse Overpass response: {e}"})

    elements = result.get("elements", [])

    categorized: dict[str, list[dict]] = {
        "metro_stations": [],
        "railway_stations": [],
        "bus_stops": [],
        "bus_stations": [],
    }

    seen = set()
    for elem in elements:
        tags = elem.get("tags", {})
        name = tags.get("name") or tags.get("name:en", f"Unnamed ({elem.get('id')})")

        key = (name.strip().lower(), round(elem.get("lat", 0), 4))
        if key in seen:
            continue
        seen.add(key)

        distance_km = round(
            haversine_km(lat, lon, elem.get("lat", 0), elem.get("lon", 0)), 2
        )

        entry = {
            "name": name,
            "distance_km": distance_km,
            "lat": elem.get("lat"),
            "lon": elem.get("lon"),
            "network": tags.get("network", ""),
            "operator": tags.get("operator", ""),
            "lines": tags.get("lines", ""),
        }

        category = _classify_element(tags)
        if category == "metro_station":
            categorized["metro_stations"].append(entry)
        elif category == "railway_station":
            categorized["railway_stations"].append(entry)
        elif category == "bus_stop":
            categorized["bus_stops"].append(entry)
        elif category == "bus_station":
            categorized["bus_stations"].append(entry)

    for key in categorized:
        categorized[key].sort(key=lambda x: x["distance_km"])
    categorized["bus_stops"] = categorized["bus_stops"][:10]

    summary = {
        "query_point": {"lat": lat, "lon": lon},
        "radius_km": radius_km,
        "found": {
            "metro_stations": len(categorized["metro_stations"]),
            "railway_stations": len(categorized["railway_stations"]),
            "bus_stops": len(categorized["bus_stops"]),
            "bus_stations": len(categorized["bus_stations"]),
        },
    }

    output = {"summary": summary, "results": categorized}
    return json.dumps(output, indent=2, ensure_ascii=False)
