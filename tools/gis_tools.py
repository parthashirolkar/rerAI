"""tools/gis_tools.py -- GIS spatial tools for rerAI.

Queries PMRDA GIS Portal and related services for spatial data about
plots in the Pune Metropolitan Region.

Uses urllib (stdlib) for HTTP requests -- no additional dependencies.
"""

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from langchain_core.tools import tool

from tools.geo import haversine_km

PMRDA_GIS_API_URL = "https://gis.pmrda.gov.in/api"
PMRDA_WMS_URL = "https://gismap.pmrda.gov.in:8443/cgi-bin/IGiS_Ent_service.exe"
DEFAULT_TIMEOUT_SECS = 30

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
        raw = resp.read().decode("utf-8")
        if not raw.strip():
            return {"type": "FeatureCollection", "features": []}
        return json.loads(raw)


async def _make_request_async(
    url: str, method: str = "GET", data: Optional[bytes] = None
) -> dict[str, Any]:
    """Async wrapper around _make_request to avoid blocking the event loop."""
    return await asyncio.to_thread(_make_request, url, method, data)


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

    bbox_size = radius_m / 111000.0
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
        result = await _make_request_async(wms_url)
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

        for feat in features:
            geom = feat.get("geometry", {})
            if geom.get("type") == "Point":
                coords = geom.get("coordinates", [lon, lat])
                feat["distance_km"] = round(
                    haversine_km(lat, lon, coords[1], coords[0]), 3
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


def _build_wms_params(layer: str, lat: float, lon: float, bbox_delta: float) -> str:
    """Build WMS GetFeatureInfo query parameters."""
    return urllib.parse.urlencode(
        {
            "IEG_PROJECT": "pmrda_ws",
            "service": "WMS",
            "version": "1.1.1",
            "request": "GetFeatureInfo",
            "layers": layer,
            "query_layers": layer,
            "bbox": f"{lon - bbox_delta},{lat - bbox_delta},{lon + bbox_delta},{lat + bbox_delta}",
            "width": "200",
            "height": "200",
            "srs": "EPSG:4326",
            "x": "100",
            "y": "100",
            "info_format": "application/json",
        }
    )


async def _query_boundary_layer(
    layer: str, lat: float, lon: float, bbox_delta: float = 0.001
) -> dict[str, Any]:
    """Query a single WMS layer and return features."""
    params = _build_wms_params(layer, lat, lon, bbox_delta)
    url = f"{PMRDA_WMS_URL}?{params}"
    return await _make_request_async(url)


async def _query_metro(lat: float, lon: float) -> dict:
    """Query metro line proximity."""
    try:
        resp = await _query_boundary_layer("pmr_metro_line", lat, lon, 0.01)
        features = resp.get("features", [])
        if features:
            props = features[0].get("properties", {})
            return {
                "metro_line_nearby": True,
                "metro_line_name": props.get("name", "Unknown"),
            }
        return {"metro_line_nearby": False}
    except Exception:
        return {"metro_line_nearby": None}


async def _query_permissions(lat: float, lon: float) -> dict:
    """Query nearby building permissions."""
    try:
        resp = await _query_boundary_layer("bld_permission", lat, lon, 0.005)
        features = resp.get("features", [])
        result: dict[str, Any] = {"nearby_permissions_count": len(features)}
        if features:
            result["nearby_permissions"] = [
                f.get("properties", {}).get("permission_no", "Unknown")
                for f in features[:5]
            ]
        return result
    except Exception:
        return {"nearby_permissions_count": None}


async def _query_env_zone(layer: str, lat: float, lon: float) -> dict[str, Any]:
    """Query a single environmental zone layer."""
    try:
        resp = await _query_boundary_layer(layer, lat, lon, 0.01)
        features = resp.get("features", [])
        return features
    except Exception:
        return None


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

    boundary_results = await asyncio.gather(
        _query_boundary_layer("boundary_village", lat, lon),
        _query_boundary_layer("boundary_taluka", lat, lon),
        return_exceptions=True,
    )

    for layer_name, layer_result in zip(
        ["boundary_village", "boundary_taluka"], boundary_results
    ):
        if isinstance(layer_result, Exception):
            continue
        features = layer_result.get("features", [])
        if features:
            props = features[0].get("properties", {})
            key = "village" if layer_name == "boundary_village" else "taluka"
            prop_key = f"{key}_name"
            result["jurisdiction"][key] = props.get("name") or props.get(prop_key, "")

    transit, permissions = await asyncio.gather(
        _query_metro(lat, lon), _query_permissions(lat, lon)
    )
    result["transit_proximity"] = transit
    result["development_context"] = permissions

    env_results = await asyncio.gather(
        _query_env_zone("wildlife_santuary", lat, lon),
        _query_env_zone("pvt_forest_over", lat, lon),
    )
    for zone_type, env_features in zip(
        ["wildlife_sanctuary", "private_forest"], env_results
    ):
        result["environmental_zones"][zone_type] = (
            len(env_features) > 0 if env_features is not None else None
        )

    return json.dumps(result, indent=2, ensure_ascii=False)
