"""tests/test_geo.py -- Unit tests for geo utilities."""

import math


from rerai_agent.tools.geo import EARTH_RADIUS_KM, haversine_km


class TestHaversineKm:
    def test_same_point_is_zero(self):
        assert haversine_km(18.52, 73.85, 18.52, 73.85) == 0.0

    def test_known_distance_pune_to_mumbai(self):
        pune_lat, pune_lon = 18.5204, 73.8567
        mumbai_lat, mumbai_lon = 19.0760, 72.8777
        dist = haversine_km(pune_lat, pune_lon, mumbai_lat, mumbai_lon)
        assert 115 < dist < 125

    def test_symmetric(self):
        d1 = haversine_km(18.5, 73.8, 18.6, 73.9)
        d2 = haversine_km(18.6, 73.9, 18.5, 73.8)
        assert abs(d1 - d2) < 0.001

    def test_antipodal_approx(self):
        d = haversine_km(0.0, 0.0, 0.0, 180.0)
        assert abs(d - EARTH_RADIUS_KM * math.pi) < 1.0

    def test_returns_float(self):
        result = haversine_km(18.5, 73.5, 18.6, 73.6)
        assert isinstance(result, float)

    def test_small_distance_wakad_to_kothrud(
        self, pune_wakad_coords, pune_kothrud_coords
    ):
        d = haversine_km(
            pune_wakad_coords["lat"],
            pune_wakad_coords["lon"],
            pune_kothrud_coords["lat"],
            pune_kothrud_coords["lon"],
        )
        assert 5 < d < 15
