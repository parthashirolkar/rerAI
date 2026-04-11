"""tests/test_integration.py -- End-to-end integration tests chaining tool outputs."""

import asyncio
import json

import pytest

from rerai_agent.tools.gis_tools import (
    check_development_plan,
    geocode_address,
    query_pmrda_layer,
)
from rerai_agent.tools.rera_tools import get_rera_project_details, search_rera_projects
from rerai_agent.tools.transit_tools import check_transit_proximity


class TestIntegrationGeocodeChains:
    """Geocode output feeds into all downstream GIS tools."""

    @pytest.mark.live
    @pytest.mark.timeout(300)
    async def test_geocode_to_transit_kothrud(self, kothrud_address):
        geo_data = json.loads(
            await geocode_address.ainvoke({"address": kothrud_address})
        )
        assert geo_data["found"] is True

        transit_data = json.loads(
            await check_transit_proximity.ainvoke(
                {
                    "lat": geo_data["lat"],
                    "lon": geo_data["lon"],
                    "radius_km": 2.0,
                }
            )
        )
        assert "error" not in transit_data, (
            f"Transit failed: {transit_data.get('error')}"
        )
        assert transit_data["summary"]["found"]["metro_stations"] >= 1

    @pytest.mark.live
    @pytest.mark.timeout(300)
    async def test_geocode_to_transit_wakad(self, wakad_address):
        geo_data = json.loads(await geocode_address.ainvoke({"address": wakad_address}))
        assert geo_data["found"] is True

        transit_data = json.loads(
            await check_transit_proximity.ainvoke(
                {
                    "lat": geo_data["lat"],
                    "lon": geo_data["lon"],
                    "radius_km": 2.0,
                }
            )
        )
        if "error" in transit_data:
            pytest.skip(f"Overpass error: {transit_data['error']}")
        assert transit_data["summary"]["found"]["metro_stations"] >= 1

    @pytest.mark.live
    @pytest.mark.timeout(120)
    async def test_geocode_to_pmrda_village(self, hinjewadi_address):
        geo_data = json.loads(
            await geocode_address.ainvoke({"address": hinjewadi_address})
        )
        assert geo_data["found"] is True

        pmrda_data = json.loads(
            await query_pmrda_layer.ainvoke(
                {
                    "layer_name": "boundary_village",
                    "lat": geo_data["lat"],
                    "lon": geo_data["lon"],
                    "radius_m": 5000,
                }
            )
        )
        assert "error" not in pmrda_data, f"PMRDA failed: {pmrda_data.get('error')}"
        assert "features" in pmrda_data

    @pytest.mark.live
    @pytest.mark.timeout(180)
    async def test_geocode_to_dev_plan_viman_nagar(self, viman_nagar_address):
        geo_data = json.loads(
            await geocode_address.ainvoke({"address": viman_nagar_address})
        )
        assert geo_data["found"] is True

        dev_data = json.loads(
            await check_development_plan.ainvoke(
                {
                    "lat": geo_data["lat"],
                    "lon": geo_data["lon"],
                }
            )
        )
        assert "error" not in dev_data, f"Dev plan failed: {dev_data.get('error')}"
        assert "jurisdiction" in dev_data
        assert "transit_proximity" in dev_data

    @pytest.mark.live
    @pytest.mark.timeout(300)
    async def test_geocode_to_all_gis_parallel(self, kothrud_address):
        geo_data = json.loads(
            await geocode_address.ainvoke({"address": kothrud_address})
        )
        assert geo_data["found"] is True

        lat, lon = geo_data["lat"], geo_data["lon"]

        transit, pmrda_village, pmrda_taluka, dev_plan = await asyncio.gather(
            check_transit_proximity.ainvoke({"lat": lat, "lon": lon, "radius_km": 2.0}),
            query_pmrda_layer.ainvoke(
                {
                    "layer_name": "boundary_village",
                    "lat": lat,
                    "lon": lon,
                    "radius_m": 2000,
                }
            ),
            query_pmrda_layer.ainvoke(
                {
                    "layer_name": "boundary_taluka",
                    "lat": lat,
                    "lon": lon,
                    "radius_m": 5000,
                }
            ),
            check_development_plan.ainvoke({"lat": lat, "lon": lon}),
        )

        transit_data = json.loads(transit)
        assert "error" not in transit_data

        pmrda_v_data = json.loads(pmrda_village)
        assert "error" not in pmrda_v_data

        pmrda_t_data = json.loads(pmrda_taluka)
        assert "error" not in pmrda_t_data

        dev_data = json.loads(dev_plan)
        assert "error" not in dev_data


class TestIntegrationReraChains:
    """RERA search output feeds into project details."""

    @pytest.mark.live
    @pytest.mark.timeout(120)
    async def test_search_then_get_details_pune(self):
        search_data = json.loads(
            await search_rera_projects.ainvoke(
                {
                    "district_name": "Pune",
                    "max_pages": 1,
                }
            )
        )
        projects = search_data.get("projects", search_data.get("results", []))

        if not projects:
            pytest.skip("No projects found in Pune search")

        view_urls = [
            p.get("view_url") or p.get("url") or p.get("link") for p in projects if p
        ]
        valid_url = next(
            (u for u in view_urls if u and "public/project/view/" in str(u)), None
        )
        if not valid_url:
            pytest.skip("No valid view_url found in project results")

        details_data = json.loads(
            await get_rera_project_details.ainvoke({"view_url": valid_url})
        )
        assert "error" not in details_data, (
            f"Details failed: {details_data.get('error')}"
        )
        assert len(details_data) > 0

    @pytest.mark.live
    @pytest.mark.timeout(120)
    async def test_search_returns_urls_usable_for_details(self):
        search_data = json.loads(
            await search_rera_projects.ainvoke(
                {
                    "district_name": "Pune",
                    "max_pages": 1,
                }
            )
        )
        projects = search_data.get("projects", search_data.get("results", []))
        if not projects:
            pytest.skip("No projects found")

        urls = [p.get("view_url") or p.get("url") for p in projects if p]
        assert len(urls) > 0, "Search returned projects but none had view_url"
        assert all("maharera" in str(u).lower() for u in urls if u)


class TestIntegrationCrossTool:
    """Full pipeline: address -> geocode -> multiple tools."""

    @pytest.mark.live
    @pytest.mark.timeout(300)
    async def test_full_pipeline_wakad(self, wakad_address):
        geo_data = json.loads(await geocode_address.ainvoke({"address": wakad_address}))
        assert geo_data["found"] is True
        lat, lon = geo_data["lat"], geo_data["lon"]

        search_data = json.loads(
            await search_rera_projects.ainvoke(
                {
                    "district_name": "Pune",
                    "max_pages": 1,
                }
            )
        )
        projects = search_data.get("projects", search_data.get("results", []))

        transit, dev_plan = await asyncio.gather(
            check_transit_proximity.ainvoke({"lat": lat, "lon": lon, "radius_km": 3.0}),
            check_development_plan.ainvoke({"lat": lat, "lon": lon}),
        )

        transit_data = json.loads(transit)
        dev_data = json.loads(dev_plan)

        assert "summary" in transit_data
        assert transit_data["summary"]["query_point"]["lat"] == pytest.approx(
            lat, abs=0.001
        )
        assert "jurisdiction" in dev_data

        if projects:
            assert isinstance(search_data, dict)
