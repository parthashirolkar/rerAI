"""tests/conftest.py -- Shared pytest fixtures."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture
def pune_wakad_coords():
    return {"lat": 18.5910, "lon": 73.7627}


@pytest.fixture
def pune_kothrud_coords():
    return {"lat": 18.5071, "lon": 73.8051}


@pytest.fixture
def pune_hinjewadi_coords():
    return {"lat": 18.5676, "lon": 73.6980}


@pytest.fixture
def pune_viman_nagar_coords():
    return {"lat": 18.5989, "lon": 73.9145}


@pytest.fixture
def wakad_address():
    return "Wakad, Pune, Maharashtra, India"


@pytest.fixture
def kothrud_address():
    return "Kothrud, Pune, Maharashtra, India"


@pytest.fixture
def hinjewadi_address():
    return "Hinjewadi, Pune, Maharashtra, India"


@pytest.fixture
def viman_nagar_address():
    return "Viman Nagar, Pune, Maharashtra, India"
