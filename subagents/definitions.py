from tools.config import get_subagent_model
from tools.gis_tools import check_development_plan, query_pmrda_layer
from tools.land_records_tools import fetch_7_12_extract, fetch_property_card
from tools.rera_tools import get_rera_project_details, search_rera_projects
from tools.regulatory_tools import query_udcpr
from tools.transit_tools import check_transit_proximity

_subagent_model = get_subagent_model()

rera_analyst = {
    "name": "rera-analyst",
    "model": _subagent_model,
    "description": (
        "Search MahaRERA registered projects by district and fetch project details. "
        "Use for developer compliance history, project registration status, and disputes."
    ),
    "system_prompt": (
        "You are a MahaRERA compliance analyst for Maharashtra, India. "
        "Given a district name, search for registered projects and summarize key data: "
        "developer name, RERA ID, project status, and any flags. "
        "Return a concise structured summary. Do NOT include raw JSON."
    ),
    "tools": [search_rera_projects, get_rera_project_details],
}

regulatory_checker = {
    "name": "regulatory-checker",
    "model": _subagent_model,
    "description": (
        "Query Maharashtra UDCPR building regulations via semantic search. "
        "Use for FSI limits, setbacks, parking norms, fire safety, height restrictions, "
        "ground coverage, and zoning rules."
    ),
    "system_prompt": (
        "You are a building regulations expert specializing in Maharashtra UDCPR "
        "(Unified Development Control and Promotion Regulations, updated Jan 2025). "
        "Given a question about building norms, query the regulation corpus and return "
        "precise clause references and requirements. Cite page numbers. "
        "If the query is ambiguous, state assumptions clearly."
    ),
    "tools": [query_udcpr],
}

gis_analyst = {
    "name": "gis-analyst",
    "model": _subagent_model,
    "description": (
        "Analyze spatial context for plots in Pune Metropolitan Region. "
        "Query transit proximity (metro, railway, bus), PMRDA GIS layers for "
        "jurisdiction boundaries, development plan zones, building permissions, "
        "and environmental overlays. Use for location assessment."
    ),
    "system_prompt": (
        "You are a GIS spatial analyst for Pune, Maharashtra. Given coordinates "
        "or location queries, analyze the spatial context including: "
        "(1) Transit proximity via OpenStreetMap - nearest metro, railway, bus stops; "
        "(2) PMRDA jurisdiction - village, taluka boundaries; "
        "(3) Development context - nearby building permissions, metro line proximity; "
        "(4) Environmental zones - wildlife sanctuaries, forest overlays. "
        "Return a structured location assessment with distances and zone classifications. "
        "Note that GIS data is for preliminary screening only."
    ),
    "tools": [check_transit_proximity, query_pmrda_layer, check_development_plan],
}

title_verifier = {
    "name": "title-verifier",
    "model": _subagent_model,
    "description": (
        "Verify land title and ownership from Mahabhulekh land records. "
        "Fetch 7/12 (Satbara) extracts and property cards to identify "
        "current owners, land classification, encumbrances, and area discrepancies."
    ),
    "system_prompt": (
        "You are a land title verification specialist for Maharashtra. "
        "Given district, taluka, village, and survey/gat number, fetch the "
        "7/12 extract from Mahabhulekh portal and analyze: "
        "(1) Current owners and their shares; "
        "(2) Land classification (agricultural, NA, gairan, etc.); "
        "(3) Total area vs pot kharab (unusable land); "
        "(4) Rights, liabilities, and encumbrances; "
        "(5) Any discrepancies or red flags. "
        "Return a structured title assessment. Note that Mahabhulekh data is "
        "for informational purposes per portal disclaimer, not for legal use."
    ),
    "tools": [fetch_7_12_extract, fetch_property_card],
}

ALL_SUBAGENTS = [rera_analyst, regulatory_checker, gis_analyst, title_verifier]
