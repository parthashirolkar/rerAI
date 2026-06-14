"""tools/websearch.py -- Low-level web search via Exa MCP.

This module contains Exa helpers and debug-oriented tools. The default agent
registry uses the domain-level ``lookup_development_site`` tool instead of
exposing raw web search results to the agent.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx
from langchain_core.tools import tool

EXA_MCP_URL = "https://mcp.exa.ai/mcp"


def _build_exa_mcp_url() -> str:
    """Return the Exa MCP endpoint.

    The public Exa MCP endpoint works for our current use without an API key.
    Do not append ``EXA_API_KEY`` to the URL: query-string credentials can be
    captured in proxy, server, and client logs.
    """
    return EXA_MCP_URL


def _build_jsonrpc_request(
    tool_name: str, arguments: dict, request_id: int = 1
) -> dict:
    """Build a JSON-RPC 2.0 ``tools/call`` request payload."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }


def _parse_sse_text(body: str) -> Optional[str]:
    """Parse an SSE-like text response looking for the first usable data event.

    Exa's MCP endpoint returns newline-delimited SSE text.  We scan for lines
    starting with ``data: `` and attempt to decode the JSON payload.  If the
    payload contains ``result.content[0].text`` we return it.
    """
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            data_part = line[len("data: ") :]
            if not data_part:
                continue
            try:
                data = json.loads(data_part)
            except json.JSONDecodeError:
                continue
            result = data.get("result", {})
            content = result.get("content", [])
            if content and isinstance(content, list) and content[0].get("text"):
                return content[0]["text"]
    return None


async def _call_exa_mcp(
    tool_name: str,
    arguments: dict,
    timeout: float = 25.0,
) -> Optional[str]:
    """Send a JSON-RPC request to Exa's MCP endpoint and return the result text."""
    url = _build_exa_mcp_url()
    payload = _build_jsonrpc_request(tool_name, arguments)

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "User-Agent": "rerAI/0.1",
            },
        )
        resp.raise_for_status()
        body = resp.text
        return _parse_sse_text(body)


@tool
async def websearch(
    query: str,
    num_results: int = 8,
    livecrawl: str = "fallback",
    search_type: str = "auto",
    context_max_characters: Optional[int] = None,
) -> str:
    """Search the web via Exa AI.

    Returns ranked web results for a natural-language query.  Useful for
    looking up current information, specific project or plot details, or
    anything not covered by the structured RERA tools.

    Args:
        query: Natural-language search query.
        num_results: Number of results to return (default 8).
        livecrawl: ``fallback`` (default) or ``preferred``.
        search_type: ``auto`` (default), ``fast``, or ``deep``.
        context_max_characters: Max characters per result snippet.

    Returns:
        JSON string with search results or an error message.
    """
    arguments: dict[str, object] = {
        "query": query,
        "type": search_type,
        "numResults": num_results,
        "livecrawl": livecrawl,
    }
    if context_max_characters is not None:
        arguments["contextMaxCharacters"] = context_max_characters

    try:
        result = await _call_exa_mcp("web_search_exa", arguments)
    except httpx.HTTPStatusError as exc:
        return json.dumps(
            {
                "error": f"Exa MCP HTTP error {exc.response.status_code}",
                "detail": exc.response.text[:500],
            }
        )
    except httpx.TimeoutException:
        return json.dumps({"error": "Exa MCP request timed out"})
    except Exception as exc:
        return json.dumps(
            {"error": f"Exa MCP call failed: {type(exc).__name__}: {exc}"}
        )

    if result is None:
        return json.dumps(
            {"error": "No search results found. Please try a different query."}
        )

    return result


@tool
async def websearch_find_specific_plot(
    plot_number: str,
    district: str = "Pune",
    num_results: int = 10,
) -> str:
    """Search the web for a specific plot or unit on the MahaRERA portals.

    Unlike ``search_rera_projects`` which returns every project in a district,
    this tool issues a targeted web query for an individual plot / unit number.
    It can surface RERA registration pages, project detail pages, or news
    articles that mention the plot.

    Args:
        plot_number: Plot / unit / flat number (e.g. "A-101", "Plot 42").
        district: District name to narrow the search (default "Pune").
        num_results: Number of web results to retrieve.

    Returns:
        JSON string with search results.
    """
    query = (
        f"MahaRERA {plot_number} {district} "
        f"site:maharera.maharashtra.gov.in OR site:maharerait.maharashtra.gov.in"
    )
    return await websearch.ainvoke(
        {
            "query": query,
            "num_results": num_results,
            "livecrawl": "preferred",
            "search_type": "deep",
        }
    )
