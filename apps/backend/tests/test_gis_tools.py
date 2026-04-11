"""tests/test_gis_tools.py -- Tests for GIS tools (geocode, PMRDA, development plan)."""

import json

import pytest

from rerai_agent.tools.gis_tools import (
    _centroid,
    check_development_plan,
    geocode_address,
    query_pmrda_layer,
)


class TestCentroid:
    def test_point_returns_coords(self):
        geom = {"type": "Point", "coordinates": [73.85, 18.52]}
        lon, lat = _centroid(geom)
        assert lon == 73.85
        assert lat == 18.52

    def test_polygon_returns_center(self):
        geom = {
            "type": "Polygon",
            "coordinates": [
                [[73.8, 18.5], [73.9, 18.5], [73.9, 18.6], [73.8, 18.6], [73.8, 18.5]]
            ],
        }
        lon, lat = _centroid(geom)
        assert 73.8 < lon < 73.9
        assert 18.5 < lat < 18.6

    def test_empty_coords_returns_zero_zero(self):
        geom = {"type": "Point", "coordinates": []}
        lon, lat = _centroid(geom)
        assert lon == 0.0
        assert lat == 0.0

    def test_linestring(self):
        geom = {"type": "LineString", "coordinates": [[73.8, 18.5], [73.9, 18.6]]}
        lon, lat = _centroid(geom)
        assert abs(lon - 73.85) < 0.01
        assert abs(lat - 18.55) < 0.01


@pytest.mark.live
class TestGeocodeAddressLive:
    @pytest.mark.timeout(30)
    async def test_geocode_wakad(self, wakad_address):
        result = await geocode_address.ainvoke({"address": wakad_address})
        data = json.loads(result)
        assert data["found"] is True
        assert "lat" in data
        assert "lon" in data
        assert "display_name" in data
        assert 18.5 < data["lat"] < 18.7
        assert 73.6 < data["lon"] < 73.9

    @pytest.mark.timeout(30)
    async def test_geocode_kothrud(self, kothrud_address):
        result = await geocode_address.ainvoke({"address": kothrud_address})
        data = json.loads(result)
        assert data["found"] is True
        assert data["lat"] == pytest.approx(18.507, abs=0.01)
        assert data["lon"] == pytest.approx(73.805, abs=0.01)

    @pytest.mark.timeout(30)
    async def test_geocode_hinjewadi(self, hinjewadi_address):
        result = await geocode_address.ainvoke({"address": hinjewadi_address})
        data = json.loads(result)
        assert data["found"] is True
        assert 18.5 < data["lat"] < 18.65
        assert 73.6 < data["lon"] < 73.8

    @pytest.mark.timeout(30)
    async def test_geocode_viman_nagar(self, viman_nagar_address):
        result = await geocode_address.ainvoke({"address": viman_nagar_address})
        data = json.loads(result)
        assert data["found"] is True
        assert 18.55 < data["lat"] < 18.65
        assert 73.85 < data["lon"] < 73.95

    @pytest.mark.timeout(30)
    async def test_geocode_returns_address_details(self, wakad_address):
        result = await geocode_address.ainvoke({"address": wakad_address})
        data = json.loads(result)
        assert "address" in data
        addr = data["address"]
        assert addr and isinstance(addr, dict)

    @pytest.mark.timeout(30)
    async def test_geocode_nonexistent_returns_not_found(self):
        result = await geocode_address.ainvoke(
            {"address": "xyzzythisdoesnotexistnowhere123"}
        )
        data = json.loads(result)
        assert data["found"] is False


@pytest.mark.live
class TestQueryPmrdalayerLive:
    @pytest.mark.timeout(60)
    async def test_boundary_village_finds_features(self, pune_wakad_coords):
        result = await query_pmrda_layer.ainvoke(
            {
                "layer_name": "boundary_village",
                "lat": pune_wakad_coords["lat"],
                "lon": pune_wakad_coords["lon"],
                "radius_m": 2000,
            }
        )
        data = json.loads(result)
        assert "error" not in data, f"Unexpected error: {data.get('error')}"
        assert "features" in data

    @pytest.mark.timeout(60)
    async def test_boundary_taluka(self, pune_hinjewadi_coords):
        result = await query_pmrda_layer.ainvoke(
            {
                "layer_name": "boundary_taluka",
                "lat": pune_hinjewadi_coords["lat"],
                "lon": pune_hinjewadi_coords["lon"],
                "radius_m": 5000,
            }
        )
        data = json.loads(result)
        assert "features" in data

    @pytest.mark.timeout(60)
    async def test_unknown_layer_returns_error_or_features(self, pune_wakad_coords):
        result = await query_pmrda_layer.ainvoke(
            {
                "layer_name": "nonexistent_layer_xyz",
                "lat": pune_wakad_coords["lat"],
                "lon": pune_wakad_coords["lon"],
                "radius_m": 500,
            }
        )
        data = json.loads(result)
        assert "features" in data or "error" in data


@pytest.mark.live
class TestCheckDevelopmentPlanLive:
    @pytest.mark.timeout(90)
    async def test_dev_plan_returns_jurisdiction(self, pune_wakad_coords):
        result = await check_development_plan.ainvoke(
            {
                "lat": pune_wakad_coords["lat"],
                "lon": pune_wakad_coords["lon"],
            }
        )
        data = json.loads(result)
        assert "error" not in data, f"Unexpected error: {data.get('error')}"
        assert "query_point" in data
        assert "jurisdiction" in data

    @pytest.mark.timeout(90)
    async def test_dev_plan_returns_transit(self, pune_kothrud_coords):
        result = await check_development_plan.ainvoke(
            {
                "lat": pune_kothrud_coords["lat"],
                "lon": pune_kothrud_coords["lon"],
            }
        )
        data = json.loads(result)
        assert "transit_proximity" in data

    @pytest.mark.timeout(90)
    async def test_dev_plan_returns_environmental_zones(self, pune_hinjewadi_coords):
        result = await check_development_plan.ainvoke(
            {
                "lat": pune_hinjewadi_coords["lat"],
                "lon": pune_hinjewadi_coords["lon"],
            }
        )
        data = json.loads(result)
        assert "environmental_zones" in data

    @pytest.mark.timeout(90)
    async def test_dev_plan_query_point_matches_input(self, pune_viman_nagar_coords):
        result = await check_development_plan.ainvoke(
            {
                "lat": pune_viman_nagar_coords["lat"],
                "lon": pune_viman_nagar_coords["lon"],
            }
        )
        data = json.loads(result)
        assert data["query_point"]["lat"] == pytest.approx(
            pune_viman_nagar_coords["lat"], abs=0.001
        )
        assert data["query_point"]["lon"] == pytest.approx(
            pune_viman_nagar_coords["lon"], abs=0.001
        )
