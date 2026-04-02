from tools.config import get_subagent_model
from tools.rera_tools import get_rera_project_details, search_rera_projects
from tools.regulatory_tools import query_udcpr

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

ALL_SUBAGENTS = [rera_analyst, regulatory_checker]
