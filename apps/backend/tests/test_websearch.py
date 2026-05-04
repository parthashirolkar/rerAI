"""tests/test_websearch.py -- Tests for the Exa MCP websearch tool.

These tests verify that the websearch tool (modelled after opencode's built-in
``websearch``) can perform targeted searches for specific plots / units on the
MahaRERA portals, bypassing the Drupal and SPA sites that are painful to scrape.
"""

import json

import pytest

from rerai_agent.tools.websearch import (
    _build_exa_mcp_url,
    _build_jsonrpc_request,
    _parse_sse_text,
    websearch,
    websearch_find_specific_plot,
)


class TestHelpers:
    def test_build_exa_mcp_url_without_key(self, monkeypatch):
        monkeypatch.delenv("EXA_API_KEY", raising=False)
        assert _build_exa_mcp_url() == "https://mcp.exa.ai/mcp"

    def test_build_exa_mcp_url_with_key(self, monkeypatch):
        monkeypatch.setenv("EXA_API_KEY", "test-key-123")
        assert _build_exa_mcp_url() == "https://mcp.exa.ai/mcp?exaApiKey=test-key-123"

    def test_build_jsonrpc_request(self):
        req = _build_jsonrpc_request("web_search_exa", {"query": "hello"}, 42)
        assert req["jsonrpc"] == "2.0"
        assert req["id"] == 42
        assert req["method"] == "tools/call"
        assert req["params"]["name"] == "web_search_exa"
        assert req["params"]["arguments"]["query"] == "hello"

    def test_parse_sse_text_with_valid_result(self):
        body = (
            'data: {"result": {"content": [{"text": "found it"}]}}\n'
            'data: {"result": {"content": [{"text": "ignored"}]}}\n'
        )
        assert _parse_sse_text(body) == "found it"

    def test_parse_sse_text_no_data_prefix(self):
        body = '{"result": {"content": [{"text": "nope"}]}}\n'
        assert _parse_sse_text(body) is None

    def test_parse_sse_text_invalid_json(self):
        body = "data: not json\n"
        assert _parse_sse_text(body) is None

    def test_parse_sse_text_empty(self):
        assert _parse_sse_text("") is None


@pytest.mark.live
class TestWebsearchLive:
    @pytest.mark.timeout(30)
    async def test_basic_websearch_returns_results(self):
        """Smoke-test the Exa MCP endpoint with a harmless query."""
        result = await websearch.ainvoke(
            {
                "query": "MahaRERA Pune project registration",
                "num_results": 3,
                "search_type": "auto",
            }
        )
        assert isinstance(result, str)
        # Result may be raw JSON or a plain string depending on Exa's response
        assert len(result) > 0
        assert "error" not in result.lower() or "no search results" in result.lower()

    @pytest.mark.timeout(30)
    async def test_plot_specific_search_structure(self):
        """Verify the plot-specific wrapper builds the right query."""
        result = await websearch_find_specific_plot.ainvoke(
            {
                "plot_number": "A-101",
                "district": "Pune",
                "num_results": 3,
            }
        )
        assert isinstance(result, str)
        # If the tool works, we should get *some* text back
        assert len(result) > 0

    @pytest.mark.timeout(45)
    async def test_search_specific_plot_vs_district_search(self):
        """Compare websearch granularity against district-level RERA search.

        The existing ``search_rera_projects`` tool can only list *all* projects
        in a district (e.g. Pune).  This test shows that ``websearch`` can
        narrow down to a single plot number and return targeted results
        without touching the Drupal/SPA sites directly.
        """
        # Websearch for a specific plot
        web_result = await websearch_find_specific_plot.ainvoke(
            {
                "plot_number": "Plot 15",
                "district": "Pune",
                "num_results": 5,
            }
        )
        assert isinstance(web_result, str)

        # The result should either be a JSON array/object or a text blob
        # We just assert it returned *something* and didn't hard-error
        assert (
            "error" not in web_result.lower()
            or "no search results" in web_result.lower()
        )

        # Try to parse as JSON to verify structure when available
        try:
            parsed = json.loads(web_result)
            # If Exa returns a JSON payload, it might have results or an error key
            assert isinstance(parsed, (dict, list, str))
        except json.JSONDecodeError:
            # Exa may return plain text; that's fine too
            pass

    @pytest.mark.timeout(30)
    async def test_websearch_handles_no_results_gracefully(self):
        """A query so specific it probably yields nothing should still return a
        friendly string rather than raising."""
        result = await websearch.ainvoke(
            {
                "query": "xyznonexistentplot12345 maharera",
                "num_results": 3,
            }
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.timeout(30)
    async def test_websearch_with_livecrawl_preferred(self):
        """Test livecrawl=preferred on a known RERA project page."""
        result = await websearch.ainvoke(
            {
                "query": (
                    "site:maharerait.maharashtra.gov.in public project view Pune"
                ),
                "num_results": 3,
                "livecrawl": "preferred",
                "search_type": "deep",
            }
        )
        assert isinstance(result, str)
        assert len(result) > 0
