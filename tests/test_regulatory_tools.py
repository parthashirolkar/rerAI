"""tests/test_regulatory_tools.py -- Tests for UDCPR regulatory query tool."""

import os

import pytest

from tools.regulatory_tools import init_udcpr_store, query_udcpr


@pytest.fixture(scope="module")
def udcpr_store():
    pdf_dir = os.path.join(os.path.dirname(__file__), "..", "data", "pdfs")
    if not os.path.exists(pdf_dir) or not os.listdir(pdf_dir):
        pytest.skip("No UDCPR PDFs found in data/pdfs/")
    count = init_udcpr_store()
    if count == 0:
        pytest.skip("UDCPR vector store is empty after initialization")
    return count


@pytest.mark.live
class TestQueryUdcprLive:
    @pytest.mark.timeout(60)
    async def test_query_fsi_returns_results(self, udcpr_store):
        result = await query_udcpr.ainvoke(
            {
                "question": "FSI limit for residential building",
            }
        )
        assert isinstance(result, str)
        assert len(result) > 20
        assert "FSI" in result or "fsi" in result.lower()

    @pytest.mark.timeout(60)
    async def test_query_setback_returns_results(self, udcpr_store):
        result = await query_udcpr.ainvoke(
            {
                "question": "minimum setback requirements front side rear",
            }
        )
        assert isinstance(result, str)
        assert len(result) > 20

    @pytest.mark.timeout(60)
    async def test_query_parking_returns_results(self, udcpr_store):
        result = await query_udcpr.ainvoke(
            {
                "question": "parking space requirements residential",
            }
        )
        assert isinstance(result, str)
        assert len(result) > 20
        assert "parking" in result.lower() or "ECS" in result

    @pytest.mark.timeout(60)
    async def test_query_returns_page_references(self, udcpr_store):
        result = await query_udcpr.ainvoke(
            {
                "question": "ground coverage percentage",
            }
        )
        assert isinstance(result, str)
        assert "page" in result.lower() or "pg" in result.lower()

    @pytest.mark.timeout(60)
    async def test_query_unknown_topic_returns_empty_message(self, udcpr_store):
        result = await query_udcpr.ainvoke(
            {
                "question": "xyzxyz totally unrelated topic 12345",
            }
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.timeout(60)
    async def test_query_fire_safety_returns_results(self, udcpr_store):
        result = await query_udcpr.ainvoke(
            {
                "question": "fire safety regulations building",
            }
        )
        assert isinstance(result, str)
        assert len(result) > 20

    @pytest.mark.timeout(60)
    async def test_n_results_parameter(self, udcpr_store):
        r1 = await query_udcpr.ainvoke({"question": "FSI setback ", "n_results": 1})
        r3 = await query_udcpr.ainvoke({"question": "FSI setback ", "n_results": 3})
        assert isinstance(r1, str)
        assert isinstance(r3, str)
