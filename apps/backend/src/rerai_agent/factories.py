from rerai_agent.registry import Registry
from rerai_agent.subagents.definitions import (
    GIS_ANALYST,
    RERA_ANALYST,
    REGULATORY_CHECKER,
    TITLE_VERIFIER,
)
from rerai_agent.tools import development_site_lookup, gis_tools, regulatory_tools
from rerai_agent.tools import transit_tools
from rerai_agent.tools.config import get_chat_model, get_subagent_model


def default_registry() -> Registry:
    return (
        Registry(
            chat_model_factory=get_chat_model,
            subagent_model_factory=get_subagent_model,
        )
        .with_tool(
            "lookup_development_site",
            development_site_lookup.lookup_development_site,
        )
        .with_tool("query_udcpr", regulatory_tools.query_udcpr)
        .with_tool("geocode_address", gis_tools.geocode_address)
        .with_tool("check_transit_proximity", transit_tools.check_transit_proximity)
        .with_tool("query_pmrda_layer", gis_tools.query_pmrda_layer)
        .with_tool("check_development_plan", gis_tools.check_development_plan)
        .with_subagent(RERA_ANALYST)
        .with_subagent(REGULATORY_CHECKER)
        .with_subagent(GIS_ANALYST)
        .with_subagent(TITLE_VERIFIER)
    )
