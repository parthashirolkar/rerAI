"""tools/gis_tools.py -- GIS spatial tools for rerAI.

Queries PMRDA GIS Portal and related services for spatial data about
plots in the Pune Metropolitan Region.

Uses urllib (stdlib) for HTTP requests -- no additional dependencies.
"""

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from langchain_core.tools import tool

PMRDA_GIS_API_URL = "https://gis.pmrda.gov.in/api"
PMRDA_WMS_URL = "https://gismap.pmrda.gov.in:8443/cgi-bin/IGiS_Ent_service.exe"
DEFAULT_TIMEOUT_SECS = 30
EARTH_RADIUS_KM = 6371.0

# Key PMRDA layers of interest for permitting
KEY_LAYERS = {
    "boundary_village": "Village boundaries",
    "boundary_taluka": "Taluka boundaries",
    "bld_permission": "Building permissions",
    "illegal_con": "Illegal constructions",
    "pmr_metro_line": "PMR Metro line alignments",
    "existing_roads": "Existing road network",
    "wildlife_santuary": "Wildlife sanctuary boundaries",
    "pvt_forest_over": "Private forest overlay",
    "dp_road_all_pmr": "DP roads across PMR",
}

_layer_cache: Optional[list[dict]] = None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance between two points in km."""
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _make_request(
    url: str, method: str = "GET", data: Optional[bytes] = None
) -> dict[str, Any]:
    """Make HTTP request and return parsed JSON."""
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "User-Agent": "rerAI/0.1 (Pune permitting assistant)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT_SECS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_layers() -> list[dict]:
    """Fetch and cache the list of available PMRDA GIS layers."""
    global _layer_cache
    if _layer_cache is not None:
        return _layer_cache

    url = f"{PMRDA_GIS_API_URL}/app/layer-group/portal-layer-groups"
    try:
        result = _make_request(url)
        # The API returns a nested structure with layer groups
        layers = []
        for group in result.get("items", []):
            for layer in group.get("layers", []):
                layers.append(
                    {
                        "name": layer.get("layerName"),
                        "table_name": layer.get("tableName"),
                        "description": layer.get("description"),
                        "group": group.get("name"),
                    }
                )
        _layer_cache = layers
        return layers
    except Exception:
        # Fallback to known layers if API fails
        return [
            {"name": k, "table_name": k, "description": v}
            for k, v in KEY_LAYERS.items()
        ]


def _get_layer_columns(layer_name: str) -> list[dict]:
    """Get the column definitions for a specific layer."""
    url = f"{PMRDA_GIS_API_URL}/app/all-common/column-list-by-layer-name?layerName={urllib.parse.quote(layer_name)}"
    try:
        result = _make_request(url)
        return result.get("items", [])
    except Exception:
        return []


@tool
async def query_pmrda_layer(
    layer_name: str, lat: float, lon: float, radius_m: int = 500
) -> str:
    """Query a PMRDA GIS layer for features near a coordinate.

    Searches the PMRDA GIS database for spatial features (boundaries,
    permissions, infrastructure) within a radius of the specified point.

    Args:
        layer_name: Name of the PMRDA layer (e.g., 'boundary_village', 'bld_permission')
        lat: Latitude of query point
        lon: Longitude of query point
        radius_m: Search radius in meters (default 500, max 2000)

    Returns:
        JSON string with matching features and their attributes.

    Available layers include:
    - boundary_village: Village boundaries
    - boundary_taluka: Taluka boundaries
    - bld_permission: Building permissions
    - illegal_con: Illegal constructions
    - pmr_metro_line: Metro line alignments
    - existing_roads: Road network
    - wildlife_santuary: Wildlife sanctuary boundaries
    """
    radius_m = min(radius_m, 2000)

    # Try to query via WMS GetFeatureInfo first (more reliable for point queries)
    bbox_size = radius_m / 111000.0  # Rough conversion meters to degrees
    bbox = f"{lon - bbox_size},{lat - bbox_size},{lon + bbox_size},{lat + bbox_size}"

    params = urllib.parse.urlencode(
        {
            "IEG_PROJECT": "pmrda_ws",
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetFeatureInfo",
            "layers": layer_name,
            "query_layers": layer_name,
            "bbox": bbox,
            "width": "400",
            "height": "400",
            "srs": "EPSG:4326",
            "x": "200",
            "y": "200",
            "info_format": "application/json",
        }
    )

    wms_url = f"{PMRDA_WMS_URL}?{params}"

    try:
        result = _make_request(wms_url)
        features = result.get("features", [])

        if not features:
            return json.dumps(
                {
                    "layer": layer_name,
                    "query_point": {"lat": lat, "lon": lon},
                    "radius_m": radius_m,
                    "found": 0,
                    "features": [],
                    "note": "No features found in this area. The plot may be outside PMRDA jurisdiction or in a different layer.",
                },
                indent=2,
                ensure_ascii=False,
            )

        # Enhance features with distance from query point
        for feat in features:
            geom = feat.get("geometry", {})
            if geom.get("type") == "Point":
                coords = geom.get("coordinates", [lon, lat])
                feat["distance_km"] = round(
                    _haversine_km(lat, lon, coords[1], coords[0]), 3
                )
            else:
                feat["distance_km"] = None

        return json.dumps(
            {
                "layer": layer_name,
                "layer_description": KEY_LAYERS.get(layer_name, ""),
                "query_point": {"lat": lat, "lon": lon},
                "radius_m": radius_m,
                "found": len(features),
                "features": features,
            },
            indent=2,
            ensure_ascii=False,
        )

    except urllib.error.URLError as e:
        return json.dumps(
            {
                "error": f"PMRDA GIS request failed: {e}",
                "layer": layer_name,
                "query_point": {"lat": lat, "lon": lon},
            },
            indent=2,
        )
    except json.JSONDecodeError as e:
        return json.dumps(
            {
                "error": f"Failed to parse PMRDA response: {e}",
                "layer": layer_name,
            },
            indent=2,
        )


@tool
async def check_development_plan(lat: float, lon: float) -> str:
    """Check the development plan context for a coordinate in Pune region.

    Queries multiple PMRDA GIS layers to determine:
    - Which village/taluka the point falls within
    - Proximity to metro lines
    - Nearby building permissions
    - Special zones (wildlife sanctuaries, forest overlays)

    Args:
        lat: Latitude of query point (e.g., 18.5314)
        lon: Longitude of query point (e.g., 73.8446)

    Returns:
        JSON string with comprehensive spatial context assessment.
    """
    result = {
        "query_point": {"lat": lat, "lon": lon},
        "jurisdiction": {},
        "transit_proximity": {},
        "development_context": {},
        "environmental_zones": {},
    }

    # Query boundary layers to determine jurisdiction
    for layer in ["boundary_village", "boundary_taluka"]:
        try:
            params = urllib.parse.urlencode(
                {
                    "IEG_PROJECT": "pmrda_ws",
                    "service": "WMS",
                    "version": "1.1.1",
                    "request": "GetFeatureInfo",
                    "layers": layer,
                    "query_layers": layer,
                    "bbox": f"{lon - 0.001},{lat - 0.001},{lon + 0.001},{lat + 0.001}",
                    "width": "200",
                    "height": "200",
                    "srs": "EPSG:4326",
                    "x": "100",
                    "y": "100",
                    "info_format": "application/json",
                }
            )
            url = f"{PMRDA_WMS_URL}?{params}"
            resp = _make_request(url)
            features = resp.get("features", [])
            if features:
                props = features[0].get("properties", {})
                if layer == "boundary_village":
                    result["jurisdiction"]["village"] = props.get("name") or props.get(
                        "village_name", ""
                    )
                else:
                    result["jurisdiction"]["taluka"] = props.get("name") or props.get(
                        "taluka_name", ""
                    )
        except Exception:
            pass

    # Check metro line proximity
    try:
        params = urllib.parse.urlencode(
            {
                "IEG_PROJECT": "pmrda_ws",
                "service": "WMS",
                "version": "1.1.1",
                "request": "GetFeatureInfo",
                "layers": "pmr_metro_line",
                "query_layers": "pmr_metro_line",
                "bbox": f"{lon - 0.01},{lat - 0.01},{lon + 0.01},{lat + 0.01}",
                "width": "200",
                "height": "200",
                "srs": "EPSG:4326",
                "x": "100",
                "y": "100",
                "info_format": "application/json",
            }
        )
        url = f"{PMRDA_WMS_URL}?{params}"
        resp = _make_request(url)
        features = resp.get("features", [])
        if features:
            result["transit_proximity"]["metro_line_nearby"] = True
            props = features[0].get("properties", {})
            result["transit_proximity"]["metro_line_name"] = props.get(
                "name", "Unknown"
            )
        else:
            result["transit_proximity"]["metro_line_nearby"] = False
    except Exception:
        result["transit_proximity"]["metro_line_nearby"] = None

    # Check for nearby building permissions
    try:
        params = urllib.parse.urlencode(
            {
                "IEG_PROJECT": "pmrda_ws",
                "service": "WMS",
                "version": "1.1.1",
                "request": "GetFeatureInfo",
                "layers": "bld_permission",
                "query_layers": "bld_permission",
                "bbox": f"{lon - 0.005},{lat - 0.005},{lon + 0.005},{lat + 0.005}",
                "width": "200",
                "height": "200",
                "srs": "EPSG:4326",
                "x": "100",
                "y": "100",
                "info_format": "application/json",
            }
        )
        url = f"{PMRDA_WMS_URL}?{params}"
        resp = _make_request(url)
        features = resp.get("features", [])
        result["development_context"]["nearby_permissions_count"] = len(features)
        if features:
            result["development_context"]["nearby_permissions"] = [
                f.get("properties", {}).get("permission_no", "Unknown")
                for f in features[:5]
            ]
    except Exception:
        result["development_context"]["nearby_permissions_count"] = None

    # Check environmental zones
    for layer, zone_type in [
        ("wildlife_santuary", "wildlife_sanctuary"),
        ("pvt_forest_over", "private_forest"),
    ]:
        try:
            params = urllib.parse.urlencode(
                {
                    "IEG_PROJECT": "pmrda_ws",
                    "service": "WMS",
                    "version": "1.1.1",
                    "request": "GetFeatureInfo",
                    "layers": layer,
                    "query_layers": layer,
                    "bbox": f"{lon - 0.01},{lat - 0.01},{lon + 0.01},{lat + 0.01}",
                    "width": "200",
                    "height": "200",
                    "srs": "EPSG:4326",
                    "x": "100",
                    "y": "100",
                    "info_format": "application/json",
                }
            )
            url = f"{PMRDA_WMS_URL}?{params}"
            resp = _make_request(url)
            features = resp.get("features", [])
            result["environmental_zones"][zone_type] = len(features) > 0
        except Exception:
            result["environmental_zones"][zone_type] = None

    return json.dumps(result, indent=2, ensure_ascii=False)
