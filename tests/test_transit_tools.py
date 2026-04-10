"""tests/test_transit_tools.py -- Tests for check_transit_proximity."""

import json

import pytest

from tools.transit_tools import (
    _build_overpass_query,
    _classify_element,
    check_transit_proximity,
)


class TestBuildOverpassQuery:
    def test_query_contains_lat_lon(self):
        q = _build_overpass_query(18.59, 73.76, 2000)
        assert "18.59" in q
        assert "73.76" in q
        assert "2000" in q

    def test_query_has_json_output(self):
        q = _build_overpass_query(18.5, 73.8, 1000)
        assert "[out:json]" in q

    def test_query_has_timeout(self):
        q = _build_overpass_query(18.5, 73.8, 1000)
        assert "[timeout:" in q

    def test_bus_radius_capped_at_500(self):
        q = _build_overpass_query(18.5, 73.8, 2000)
        assert "500" in q

    def test_metro_query_included(self):
        q = _build_overpass_query(18.5, 73.8, 1000)
        assert "railway" in q
        assert "subway" in q

    def test_bus_stop_query_included(self):
        q = _build_overpass_query(18.5, 73.8, 1000)
        assert "highway" in q and "bus_stop" in q


class TestClassifyElement:
    def test_metro_station(self):
        tags = {"railway": "station", "station": "subway", "subway": "yes"}
        assert _classify_element(tags) == "metro_station"

    def test_railway_station(self):
        tags = {"railway": "station", "train": "yes"}
        assert _classify_element(tags) == "railway_station"

    def test_bus_stop(self):
        tags = {"highway": "bus_stop"}
        assert _classify_element(tags) == "bus_stop"

    def test_bus_station(self):
        tags = {"amenity": "bus_station"}
        assert _classify_element(tags) == "bus_station"

    def test_unknown(self):
        tags = {"highway": "residential"}
        assert _classify_element(tags) == "unknown"


@pytest.mark.live
class TestCheckTransitProximityLive:
    @pytest.mark.timeout(120)
    async def test_kothrud_finds_metro_stations(self, pune_kothrud_coords):
        result = await check_transit_proximity.ainvoke(
            {
                "lat": pune_kothrud_coords["lat"],
                "lon": pune_kothrud_coords["lon"],
                "radius_km": 2.0,
            }
        )
        data = json.loads(result)
        assert "error" not in data, f"Unexpected error: {data.get('error')}"
        assert "summary" in data
        assert "results" in data
        assert data["summary"]["found"]["metro_stations"] >= 1

    @pytest.mark.timeout(120)
    async def test_wakad_finds_metro_stations(self, pune_wakad_coords):
        result = await check_transit_proximity.ainvoke(
            {
                "lat": pune_wakad_coords["lat"],
                "lon": pune_wakad_coords["lon"],
                "radius_km": 2.0,
            }
        )
        data = json.loads(result)
        assert "error" not in data, f"Unexpected error: {data.get('error')}"
        assert data["summary"]["found"]["metro_stations"] >= 1

    @pytest.mark.timeout(120)
    async def test_returns_distance_for_each_station(self, pune_kothrud_coords):
        result = await check_transit_proximity.ainvoke(
            {
                "lat": pune_kothrud_coords["lat"],
                "lon": pune_kothrud_coords["lon"],
                "radius_km": 2.0,
            }
        )
        data = json.loads(result)
        for station in data["results"]["metro_stations"]:
            assert "name" in station
            assert "distance_km" in station
            assert station["distance_km"] <= 2.0

    @pytest.mark.timeout(120)
    async def test_results_sorted_by_distance(self, pune_kothrud_coords):
        result = await check_transit_proximity.ainvoke(
            {
                "lat": pune_kothrud_coords["lat"],
                "lon": pune_kothrud_coords["lon"],
                "radius_km": 2.0,
            }
        )
        data = json.loads(result)
        distances = [s["distance_km"] for s in data["results"]["metro_stations"]]
        assert distances == sorted(distances)

    @pytest.mark.timeout(300)
    async def test_radius_km_parameter_respected(self, pune_kothrud_coords):
        result_1km = await check_transit_proximity.ainvoke(
            {
                "lat": pune_kothrud_coords["lat"],
                "lon": pune_kothrud_coords["lon"],
                "radius_km": 1.0,
            }
        )
        result_3km = await check_transit_proximity.ainvoke(
            {
                "lat": pune_kothrud_coords["lat"],
                "lon": pune_kothrud_coords["lon"],
                "radius_km": 3.0,
            }
        )
        data_1km = json.loads(result_1km)
        data_3km = json.loads(result_3km)
        if "error" in data_1km:
            pytest.skip(f"Overpass returned error for 1km query: {data_1km['error']}")
        if "error" in data_3km:
            pytest.skip(f"Overpass returned error for 3km query: {data_3km['error']}")
        assert data_1km["summary"]["radius_km"] == 1.0
        assert data_3km["summary"]["radius_km"] == 3.0
