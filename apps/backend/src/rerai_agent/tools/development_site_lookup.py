"""Domain-level development site lookup.

This module keeps web retrieval behind a permitting-domain tool. The public
tool returns bounded, source-backed evidence instead of raw search text.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from langchain_core.tools import tool

from rerai_agent.tools.rera_tools import get_rera_project_details
from rerai_agent.tools.websearch import _call_exa_mcp

OFFICIAL_RERA_HOSTS = {
    "maharera.maharashtra.gov.in",
    "maharerait.maharashtra.gov.in",
}

OFFICIAL_LAND_RECORD_HOSTS = {
    "bhulekh.mahabhumi.gov.in",
    "mahabhumi.gov.in",
    "bhumiabhilekh.maharashtra.gov.in",
}


@dataclass
class DevelopmentSiteQuery:
    raw_query: str
    district: str
    taluka: Optional[str] = None
    village: Optional[str] = None
    locality: Optional[str] = None
    survey_number: Optional[str] = None
    gat_number: Optional[str] = None
    cts_number: Optional[str] = None
    plot_number: Optional[str] = None
    rera_registration_number: Optional[str] = None
    rera_view_url: Optional[str] = None
    project_name: Optional[str] = None
    promoter_name: Optional[str] = None
    search_hints: list[str] = field(default_factory=list)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source_type: str = "corroborating"


def _compact_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _hostname(url: str) -> str:
    return urlparse(url).hostname or ""


def _classify_source(url: str) -> str:
    host = _hostname(url).lower()
    if host in OFFICIAL_RERA_HOSTS:
        return "official_rera"
    if host in OFFICIAL_LAND_RECORD_HOSTS:
        return "official_land_record"
    return "corroborating"


def _extract_labelled_value(query: str, label_pattern: str) -> Optional[str]:
    match = re.search(
        rf"\b(?:{label_pattern})\s*(?:no\.?|number|#)?\s*[:\-]?\s*([A-Za-z0-9/-]+)",
        query,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return None


def _extract_rera_registration_number(query: str) -> Optional[str]:
    match = re.search(r"\bP\d{11}\b", query, flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    return None


def _infer_locality_from_commas(query: str, district: str) -> Optional[str]:
    parts = [p.strip() for p in query.split(",") if p.strip()]
    if len(parts) < 2:
        return None

    district_key = district.strip().lower()
    rejected = {
        district_key,
        "maharashtra",
        "india",
    }
    candidates = []
    for part in parts:
        key = part.lower()
        if key in rejected:
            continue
        if _extract_labelled_value(part, "plot") or _extract_labelled_value(
            part, "survey|s\\.n\\.|s no|gat|cts"
        ):
            continue
        if _extract_rera_registration_number(part):
            continue
        candidates.append(part)

    return candidates[-1] if candidates else None


def _build_development_site_query(
    *,
    query: str,
    district: str,
    taluka: Optional[str] = None,
    village: Optional[str] = None,
    locality: Optional[str] = None,
    survey_number: Optional[str] = None,
    gat_number: Optional[str] = None,
    cts_number: Optional[str] = None,
    plot_number: Optional[str] = None,
    rera_registration_number: Optional[str] = None,
    rera_view_url: Optional[str] = None,
    project_name: Optional[str] = None,
    promoter_name: Optional[str] = None,
) -> DevelopmentSiteQuery:
    raw_query = query.strip()
    normalized_district = district.strip()
    inferred_locality = locality or village or _infer_locality_from_commas(
        raw_query, normalized_district
    )

    site_query = DevelopmentSiteQuery(
        raw_query=raw_query,
        district=normalized_district,
        taluka=taluka,
        village=village,
        locality=inferred_locality,
        survey_number=survey_number
        or _extract_labelled_value(raw_query, "survey|s\\.n\\.|s no"),
        gat_number=gat_number or _extract_labelled_value(raw_query, "gat"),
        cts_number=cts_number or _extract_labelled_value(raw_query, "cts"),
        plot_number=plot_number or _extract_labelled_value(raw_query, "plot"),
        rera_registration_number=rera_registration_number
        or _extract_rera_registration_number(raw_query),
        rera_view_url=rera_view_url or _extract_rera_view_url(raw_query),
        project_name=project_name,
        promoter_name=promoter_name,
    )
    site_query.search_hints = _search_hints(site_query)
    return site_query


def _search_hints(site_query: DevelopmentSiteQuery) -> list[str]:
    hints = []
    for label, value in (
        ("survey", site_query.survey_number),
        ("gat", site_query.gat_number),
        ("cts", site_query.cts_number),
        ("plot", site_query.plot_number),
        ("rera", site_query.rera_registration_number),
        ("rera_view_url", site_query.rera_view_url),
        ("project", site_query.project_name),
        ("promoter", site_query.promoter_name),
    ):
        if value:
            hints.append(f"{label}:{value}")
    if site_query.village:
        hints.append(f"village:{site_query.village}")
    elif site_query.locality:
        hints.append(f"locality:{site_query.locality}")
    if site_query.taluka:
        hints.append(f"taluka:{site_query.taluka}")
    return hints


def _validate_research_brief(site_query: DevelopmentSiteQuery) -> list[str]:
    missing = []
    if not site_query.district:
        missing.append("district")
    if not any(
        [
            site_query.village,
            site_query.locality,
            site_query.taluka,
            site_query.project_name,
            site_query.rera_registration_number,
            site_query.rera_view_url,
        ]
    ):
        missing.append("village/locality/taluka/project_name/rera_registration_number")
    if not any(
        [
            site_query.plot_number,
            site_query.survey_number,
            site_query.gat_number,
            site_query.cts_number,
            site_query.rera_registration_number,
            site_query.rera_view_url,
            site_query.project_name,
        ]
    ):
        missing.append(
            "labeled plot/survey/gat/cts number, RERA registration number, or project name"
        )
    return missing


def _build_discovery_queries(site_query: DevelopmentSiteQuery) -> list[str]:
    place_parts = [
        p
        for p in (
            site_query.village or site_query.locality,
            site_query.taluka,
            site_query.district,
        )
        if p
    ]
    place = " ".join(place_parts)
    identifier_parts = [
        f"Survey {site_query.survey_number}" if site_query.survey_number else None,
        f"Gat {site_query.gat_number}" if site_query.gat_number else None,
        f"CTS {site_query.cts_number}" if site_query.cts_number else None,
        f"Plot {site_query.plot_number}" if site_query.plot_number else None,
        site_query.rera_registration_number,
        site_query.rera_view_url,
        f'"{site_query.project_name}"' if site_query.project_name else None,
    ]
    identifier = " ".join(p for p in identifier_parts if p)

    queries = [
        f"{identifier} {place} MahaRERA".strip(),
        (
            f"{identifier} {place} "
            "site:maharerait.maharashtra.gov.in/public/project/view"
        ).strip(),
        (
            f"{identifier} {place} "
            "site:maharera.maharashtra.gov.in"
        ).strip(),
    ]
    if site_query.promoter_name:
        queries.append(f'"{site_query.promoter_name}" {identifier} {place} MahaRERA')

    return list(dict.fromkeys(q for q in queries if q))


def _first_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            text = _first_text(item)
            if text:
                return text
    if isinstance(value, dict):
        for key in ("text", "snippet", "summary", "description", "content"):
            text = _first_text(value.get(key))
            if text:
                return text
    return ""


def _result_from_dict(item: dict[str, Any]) -> Optional[SearchResult]:
    url = str(item.get("url") or item.get("link") or item.get("href") or "").strip()
    if not url:
        return None
    title = str(item.get("title") or item.get("name") or url).strip()
    snippet = _first_text(
        item.get("text")
        or item.get("snippet")
        or item.get("summary")
        or item.get("content")
        or item.get("highlights")
    )
    return SearchResult(
        title=title[:160],
        url=url,
        snippet=snippet[:500],
        source_type=_classify_source(url),
    )


def _walk_dict_results(value: Any) -> list[SearchResult]:
    results = []
    if isinstance(value, dict):
        maybe_result = _result_from_dict(value)
        if maybe_result:
            results.append(maybe_result)
        for child in value.values():
            results.extend(_walk_dict_results(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(_walk_dict_results(child))
    return results


def _parse_exa_results(text: str) -> list[SearchResult]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _extract_urls_from_text(text)
    return _dedupe_results(_walk_dict_results(parsed))


def _extract_urls_from_text(text: str) -> list[SearchResult]:
    urls = re.findall(r"https?://[^\s\]\)\"'<>]+", text)
    return _dedupe_results(
        [
            SearchResult(title=url, url=url, source_type=_classify_source(url))
            for url in urls
        ]
    )


def _extract_rera_view_url(query: str) -> Optional[str]:
    match = re.search(
        r"https?://maharerait\.maharashtra\.gov\.in/public/project/view/\d+",
        query,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(0)
    return None


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen = set()
    unique = []
    for result in results:
        if result.url in seen:
            continue
        seen.add(result.url)
        unique.append(result)
    return unique


def _candidate_rera_view_urls(results: list[SearchResult]) -> list[str]:
    urls = []
    for result in results:
        if result.source_type != "official_rera":
            continue
        if "/public/project/view/" not in result.url:
            continue
        urls.append(result.url)
    return list(dict.fromkeys(urls))


def _response_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("responseObject"), dict):
        return value["responseObject"]
    return {}


def _reduce_rera_detail(detail_text: str, source_url: str) -> dict[str, Any]:
    try:
        data = json.loads(detail_text)
    except json.JSONDecodeError:
        return {
            "source_url": source_url,
            "source_type": "official_rera",
            "status": "unparseable_detail_response",
        }

    public_info = _response_object(data.get("public_info"))
    core_status = _response_object(data.get("status")).get("coreStatus") or {}
    authenticated = data.get("authenticated_info") or {}
    promoter = _response_object(authenticated.get("promoter"))
    project_details = promoter.get("projectDetails") or {}
    legal_address = project_details.get("projectLegalLandAddressDetails") or {}

    return {
        "source_url": source_url,
        "source_type": "official_rera",
        "project_id": data.get("projectId"),
        "rera_registration_number": public_info.get("projectRegistartionNo"),
        "project_name": public_info.get("projectName"),
        "project_type": public_info.get("projectTypeName"),
        "project_status": public_info.get("projectStatusName"),
        "project_current_status": public_info.get("projectCurrentStatus"),
        "core_status": core_status.get("statusName"),
        "registration_date": public_info.get("reraRegistrationDate"),
        "proposed_completion_date": public_info.get("projectProposeComplitionDate"),
        "total_units": public_info.get("totalNumberOfUnits"),
        "sold_units": public_info.get("totalNumberOfSoldUnits"),
        "legal_land_address": {
            "district": legal_address.get("districtName"),
            "taluka": legal_address.get("talukaName"),
            "village": legal_address.get("villageName"),
            "pin_code": legal_address.get("pinCode"),
            "boundaries_east": legal_address.get("boundariesEast"),
            "boundaries_west": legal_address.get("boundariesWest"),
            "boundaries_north": legal_address.get("boundariesNorth"),
            "boundaries_south": legal_address.get("boundariesSouth"),
            "total_area_sqmts": legal_address.get("totalAreaSqmts"),
            "proposed_area_sqmts": legal_address.get("proposedAreaSqmts"),
            "legal_land_details": legal_address.get("legalLandDetails"),
        },
    }


def _score_rera_evidence(
    site_query: DevelopmentSiteQuery, evidence: dict[str, Any]
) -> tuple[str, list[str]]:
    reasons = []
    legal = evidence.get("legal_land_address") or {}
    legal_text = " ".join(str(v or "") for v in legal.values())
    normalized_legal_text = _normalize_for_contains(legal_text)
    if site_query.district and str(legal.get("district") or "").lower() == (
        site_query.district.lower()
    ):
        reasons.append("district matched official RERA legal land address")
    if site_query.taluka and str(legal.get("taluka") or "").lower() == (
        site_query.taluka.lower()
    ):
        reasons.append("taluka matched official RERA legal land address")
    expected_village = site_query.village or site_query.locality
    if expected_village and str(legal.get("village") or "").lower() == (
        expected_village.lower()
    ):
        reasons.append("village/locality matched official RERA legal land address")
    if site_query.rera_registration_number and evidence.get(
        "rera_registration_number"
    ) != site_query.rera_registration_number:
        return (
            "no_match",
            [
                (
                    "RERA registration number did not match official RERA "
                    "response"
                )
            ],
        )
    if site_query.rera_registration_number:
        reasons.append("RERA registration number matched official RERA response")
    for label, value in (
        ("survey", site_query.survey_number),
        ("gat", site_query.gat_number),
        ("cts", site_query.cts_number),
        ("plot", site_query.plot_number),
    ):
        if value and _contains_labeled_identifier(normalized_legal_text, label, value):
            reasons.append(
                f"{label} number matched official RERA legal land address"
            )

    if any("RERA registration" in r or "number matched" in r for r in reasons):
        return "high", reasons
    if len(reasons) >= 2:
        return "medium", reasons
    if reasons:
        return "low", reasons
    return "candidate", reasons


def _normalize_for_contains(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/-]+", " ", value.lower())).strip()


def _contains_labeled_identifier(text: str, label: str, value: str) -> bool:
    normalized_value = _normalize_for_contains(value)
    candidates = {
        f"{label} {normalized_value}",
        f"{label} no {normalized_value}",
        f"{label} number {normalized_value}",
    }
    if label == "survey":
        candidates.update(
            {
                f"s no {normalized_value}",
                f"survey no {normalized_value}",
                f"survey number {normalized_value}",
            }
        )
    return any(candidate in text for candidate in candidates)


def _best_confidence(evidence: list[dict[str, Any]]) -> str:
    rank = {"none": 0, "no_match": 0, "candidate": 1, "low": 2, "medium": 3, "high": 4}
    best = "none"
    for item in evidence:
        confidence = item.get("match_confidence", "candidate")
        if rank.get(confidence, 0) > rank[best]:
            best = confidence
    return best


async def _search_exa(query: str, num_results: int) -> str:
    result = await _call_exa_mcp(
        "web_search_exa",
        {
            "query": query,
            "type": "auto",
            "numResults": num_results,
            "livecrawl": "fallback",
            "contextMaxCharacters": 600,
        },
    )
    return result or ""


@tool
async def lookup_development_site(
    query: str,
    district: str = "Pune",
    taluka: Optional[str] = None,
    village: Optional[str] = None,
    locality: Optional[str] = None,
    survey_number: Optional[str] = None,
    gat_number: Optional[str] = None,
    cts_number: Optional[str] = None,
    plot_number: Optional[str] = None,
    rera_registration_number: Optional[str] = None,
    rera_view_url: Optional[str] = None,
    project_name: Optional[str] = None,
    promoter_name: Optional[str] = None,
    max_candidates: int = 3,
) -> str:
    """Look up structured evidence for a development site.

    Use this after the user's request has been clarified into a research brief:
    district, one locality/admin hint, and one labeled site or project identifier.
    The tool performs targeted discovery and returns bounded evidence with source
    citations. It does not return raw search dumps.
    """
    site_query = _build_development_site_query(
        query=query,
        district=district,
        taluka=taluka,
        village=village,
        locality=locality,
        survey_number=survey_number,
        gat_number=gat_number,
        cts_number=cts_number,
        plot_number=plot_number,
        rera_registration_number=rera_registration_number,
        rera_view_url=rera_view_url,
        project_name=project_name,
        promoter_name=promoter_name,
    )
    missing = _validate_research_brief(site_query)
    if missing:
        return _compact_json(
            {
                "status": "needs_research_brief",
                "message": "Ask the user for the missing details before lookup.",
                "missing": missing,
                "query": asdict(site_query),
                "rera_project_evidence": [],
                "land_record_evidence": [],
                "sources": [],
            }
        )

    discovery_queries = _build_discovery_queries(site_query)
    search_payloads = await asyncio.gather(
        *[_search_exa(q, max_candidates) for q in discovery_queries],
        return_exceptions=True,
    )

    search_results: list[SearchResult] = []
    errors = []
    for payload in search_payloads:
        if isinstance(payload, Exception):
            errors.append(f"{type(payload).__name__}: {payload}")
            continue
        search_results.extend(_parse_exa_results(payload))
    search_results = _dedupe_results(search_results)

    rera_urls = []
    if site_query.rera_view_url:
        rera_urls.append(site_query.rera_view_url)
    rera_urls.extend(_candidate_rera_view_urls(search_results))
    rera_urls = list(dict.fromkeys(rera_urls))[:max_candidates]
    detail_payloads = await asyncio.gather(
        *[get_rera_project_details.ainvoke({"view_url": url}) for url in rera_urls],
        return_exceptions=True,
    )

    rera_evidence = []
    for source_url, detail in zip(rera_urls, detail_payloads):
        if isinstance(detail, Exception):
            rera_evidence.append(
                {
                    "source_url": source_url,
                    "source_type": "official_rera",
                    "status": "detail_fetch_failed",
                    "error": f"{type(detail).__name__}: {detail}",
                }
            )
            continue
        reduced = _reduce_rera_detail(detail, source_url)
        confidence, reasons = _score_rera_evidence(site_query, reduced)
        reduced["match_confidence"] = confidence
        reduced["match_reasons"] = reasons
        rera_evidence.append(reduced)

    sources = [
        {
            "title": result.title,
            "url": result.url,
            "source_type": result.source_type,
            "snippet": result.snippet,
        }
        for result in search_results[:10]
    ]
    best_confidence = _best_confidence(rera_evidence)
    matched_rera_evidence = [
        item
        for item in rera_evidence
        if item.get("match_confidence") not in {"no_match"}
        and item.get("status") != "detail_fetch_failed"
    ]

    return _compact_json(
        {
            "status": "completed" if search_results else "no_candidates_found",
            "query": asdict(site_query),
            "answer": {
                "summary": (
                    "Found candidate RERA evidence."
                    if matched_rera_evidence
                    else "No matching official RERA project detail candidate was found."
                ),
                "confidence": best_confidence,
            },
            "rera_project_evidence": rera_evidence,
            "land_record_evidence": [
                {
                    "status": "not_implemented",
                    "message": (
                        "Official 7/12 retrieval is not implemented yet; "
                        "no land-record facts were established."
                    ),
                }
            ],
            "sources": sources,
            "discovery_queries": discovery_queries,
            "errors": errors,
        }
    )
