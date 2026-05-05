"""Tests for the development site lookup reducer."""

import json

import pytest

from rerai_agent.tools import development_site_lookup as lookup_module
from rerai_agent.tools.development_site_lookup import (
    _best_confidence,
    _build_development_site_query,
    _classify_source,
    _parse_exa_results,
    _reduce_rera_detail,
    _score_rera_evidence,
    _validate_research_brief,
    lookup_development_site,
)


class TestResearchBrief:
    def test_build_query_extracts_strict_plot_label_and_locality(self):
        site_query = _build_development_site_query(
            query="Check Plot 15, Jamtha, Pune",
            district="Pune",
        )

        assert site_query.plot_number == "15"
        assert site_query.survey_number is None
        assert site_query.gat_number is None
        assert site_query.locality == "Jamtha"

    def test_build_query_uses_first_unidentified_comma_part_as_locality(self):
        site_query = _build_development_site_query(
            query="Check Plot 15, Jamtha, Pune, Near Highway",
            district="Pune",
        )

        assert site_query.locality == "Jamtha"

    def test_rejects_missing_labeled_identifier(self):
        site_query = _build_development_site_query(
            query="Check Jamtha, Pune",
            district="Pune",
        )

        missing = _validate_research_brief(site_query)

        assert any("labeled" in item for item in missing)

    def test_accepts_rera_registration_as_project_identifier(self):
        site_query = _build_development_site_query(
            query="Check P50500001839 Jamtha Pune",
            district="Pune",
            locality="Jamtha",
        )

        assert site_query.rera_registration_number == "P50500001839"
        assert _validate_research_brief(site_query) == []

    def test_rejects_rera_registration_without_location_hint(self):
        site_query = _build_development_site_query(
            query="Check P50500001839",
            district="Nagpur",
        )

        missing = _validate_research_brief(site_query)

        assert any("village/locality/taluka" in item for item in missing)

    def test_accepts_official_rera_view_url_as_project_identifier(self):
        site_query = _build_development_site_query(
            query=(
                "Check https://maharerait.maharashtra.gov.in"
                "/public/project/view/531 Jamtha Nagpur"
            ),
            district="Nagpur",
            locality="Jamtha",
        )

        assert (
            site_query.rera_view_url
            == "https://maharerait.maharashtra.gov.in/public/project/view/531"
        )
        assert _validate_research_brief(site_query) == []


class TestSources:
    def test_classifies_official_rera_source(self):
        source_type = _classify_source(
            "https://maharerait.maharashtra.gov.in/public/project/view/531"
        )

        assert source_type == "official_rera"

    def test_classifies_official_land_record_source(self):
        source_type = _classify_source("https://bhulekh.mahabhumi.gov.in/")

        assert source_type == "official_land_record"

    def test_parse_exa_results_from_structured_json(self):
        payload = json.dumps(
            {
                "results": [
                    {
                        "title": "Project View",
                        "url": (
                            "https://maharerait.maharashtra.gov.in"
                            "/public/project/view/531"
                        ),
                        "text": "Official project page",
                    }
                ]
            }
        )

        results = _parse_exa_results(payload)

        assert len(results) == 1
        assert results[0].source_type == "official_rera"
        assert results[0].snippet == "Official project page"


class TestReraReduction:
    def test_reduce_rera_detail_keeps_only_compact_evidence(self):
        detail = json.dumps(
            {
                "projectId": 531,
                "public_info": {
                    "responseObject": {
                        "projectRegistartionNo": "P50500001839",
                        "projectName": "MAHALAXMI NAGAR 1",
                        "projectTypeName": "Plotted",
                    }
                },
                "status": {"responseObject": {"coreStatus": {"statusName": "Done"}}},
                "authenticated_info": {
                    "promoter": {
                        "responseObject": {
                            "projectDetails": {
                                "projectLegalLandAddressDetails": {
                                    "districtName": "Pune",
                                    "talukaName": "Haveli",
                                    "villageName": "Jamtha",
                                    "boundariesEast": "Survey No 15",
                                }
                            }
                        }
                    }
                },
            }
        )

        evidence = _reduce_rera_detail(
            detail,
            "https://maharerait.maharashtra.gov.in/public/project/view/531",
        )

        assert evidence["project_id"] == 531
        assert evidence["rera_registration_number"] == "P50500001839"
        assert evidence["legal_land_address"]["village"] == "Jamtha"
        assert "authenticated_info" not in evidence

    def test_score_medium_when_only_official_legal_identifier_matches(self):
        site_query = _build_development_site_query(
            query="Survey No 15, Jamtha, Pune",
            district="Pune",
        )
        evidence = {
            "legal_land_address": {
                "district": "Nagpur",
                "village": "Ravet",
                "boundaries_east": "Survey No 15",
            }
        }

        confidence, reasons = _score_rera_evidence(site_query, evidence)

        assert confidence == "medium"
        assert any("survey number matched" in reason for reason in reasons)

    def test_score_high_when_legal_identifier_and_location_match(self):
        site_query = _build_development_site_query(
            query="Survey No 15, Jamtha, Pune",
            district="Pune",
        )
        evidence = {
            "legal_land_address": {
                "district": "Pune",
                "village": "Jamtha",
                "boundaries_east": "Survey No 15",
            }
        }

        confidence, reasons = _score_rera_evidence(site_query, evidence)

        assert confidence == "high"
        assert any("survey number matched" in reason for reason in reasons)

    def test_score_no_match_when_rera_registration_differs(self):
        site_query = _build_development_site_query(
            query="RERA P50500001839, Jamtha, Nagpur",
            district="Nagpur",
            locality="Jamtha",
        )
        evidence = {
            "rera_registration_number": "P52100079515",
            "legal_land_address": {
                "district": "Pune",
                "village": "Ravet",
            },
        }

        confidence, reasons = _score_rera_evidence(site_query, evidence)

        assert confidence == "no_match"
        assert any("did not match" in reason for reason in reasons)

    def test_best_confidence_uses_strongest_candidate(self):
        assert _best_confidence(
            [
                {"match_confidence": "low"},
                {"match_confidence": "high"},
                {"match_confidence": "medium"},
            ]
        ) == "high"


class FakeReraDetailTool:
    async def ainvoke(self, payload):
        assert "public/project/view/531" in payload["view_url"]
        return json.dumps(
            {
                "projectId": 531,
                "public_info": {
                    "responseObject": {
                        "projectRegistartionNo": "P50500001839",
                        "projectName": "MAHALAXMI NAGAR 1",
                    }
                },
                "status": {"responseObject": {"coreStatus": {"statusName": "Done"}}},
                "authenticated_info": {
                    "promoter": {
                        "responseObject": {
                            "projectDetails": {
                                "projectLegalLandAddressDetails": {
                                    "districtName": "Pune",
                                    "villageName": "Jamtha",
                                    "boundariesEast": "Survey No 15",
                                }
                            }
                        }
                    }
                },
            }
        )


async def test_lookup_development_site_returns_structured_evidence(monkeypatch):
    async def fake_search_exa(query, num_results):
        assert "MahaRERA" in query or "maharera" in query
        return json.dumps(
            {
                "results": [
                    {
                        "title": "Project View",
                        "url": (
                            "https://maharerait.maharashtra.gov.in"
                            "/public/project/view/531"
                        ),
                    }
                ]
            }
        )

    monkeypatch.setattr(lookup_module, "_search_exa", fake_search_exa)
    monkeypatch.setattr(
        lookup_module,
        "get_rera_project_details",
        FakeReraDetailTool(),
    )

    result = await lookup_development_site.ainvoke(
        {
            "query": "Survey No 15, Jamtha, Pune",
            "district": "Pune",
        }
    )
    data = json.loads(result)

    assert data["status"] == "completed"
    assert data["answer"]["confidence"] == "high"
    assert data["rera_project_evidence"][0]["project_id"] == 531
    assert "authenticated_info" not in result


async def test_lookup_development_site_requires_research_brief():
    result = await lookup_development_site.ainvoke(
        {
            "query": "15 Pune",
            "district": "Pune",
        }
    )
    data = json.loads(result)

    assert data["status"] == "needs_research_brief"
    assert data["rera_project_evidence"] == []


async def test_lookup_development_site_rejects_mismatched_rera_candidate(
    monkeypatch,
):
    async def fake_search_exa(query, num_results):
        return json.dumps(
            {
                "results": [
                    {
                        "title": "Unrelated Project View",
                        "url": (
                            "https://maharerait.maharashtra.gov.in"
                            "/public/project/view/54546"
                        ),
                    }
                ]
            }
        )

    class MismatchedReraDetailTool:
        async def ainvoke(self, payload):
            return json.dumps(
                {
                    "projectId": 54546,
                    "public_info": {
                        "responseObject": {
                            "projectRegistartionNo": "P52100079515",
                            "projectName": "STELLAR SYMPHONY",
                        }
                    },
                    "status": {
                        "responseObject": {"coreStatus": {"statusName": "Active"}}
                    },
                }
            )

    monkeypatch.setattr(lookup_module, "_search_exa", fake_search_exa)
    monkeypatch.setattr(
        lookup_module,
        "get_rera_project_details",
        MismatchedReraDetailTool(),
    )

    result = await lookup_development_site.ainvoke(
        {
            "query": "RERA P50500001839, Jamtha, Nagpur",
            "district": "Nagpur",
            "locality": "Jamtha",
            "rera_registration_number": "P50500001839",
        }
    )
    data = json.loads(result)

    assert data["answer"]["confidence"] == "none"
    assert data["answer"]["summary"].startswith("No matching official RERA")
    assert data["rera_project_evidence"][0]["match_confidence"] == "no_match"


async def test_lookup_development_site_reports_search_failure(monkeypatch):
    async def failing_search_exa(query, num_results):
        raise TimeoutError("network unavailable")

    monkeypatch.setattr(lookup_module, "_search_exa", failing_search_exa)

    result = await lookup_development_site.ainvoke(
        {
            "query": "Survey No 15, Jamtha, Pune",
            "district": "Pune",
        }
    )
    data = json.loads(result)

    assert data["status"] == "search_failed"
    assert data["errors"]


@pytest.mark.live
@pytest.mark.timeout(90)
async def test_live_lookup_development_site_user_flow():
    """Mimic the real agent flow for a clarified development-site brief."""
    result = await lookup_development_site.ainvoke(
        {
            "query": (
                "Check RERA P50500001839 at "
                "https://maharerait.maharashtra.gov.in/public/project/view/531, "
                "Jamtha, Nagpur"
            ),
            "district": "Nagpur",
            "locality": "Jamtha",
            "rera_registration_number": "P50500001839",
            "rera_view_url": (
                "https://maharerait.maharashtra.gov.in/public/project/view/531"
            ),
            "max_candidates": 2,
        }
    )
    data = json.loads(result)

    assert data["status"] == "completed"
    assert data["answer"]["confidence"] == "high"
    assert data["sources"]
    assert data["rera_project_evidence"]
    assert data["rera_project_evidence"][0]["source_type"] == "official_rera"
    assert data["rera_project_evidence"][0]["project_id"] == 531
    assert (
        data["rera_project_evidence"][0]["rera_registration_number"]
        == "P50500001839"
    )
    assert "authenticated_info" not in result
