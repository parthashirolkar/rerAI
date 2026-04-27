from __future__ import annotations

import warnings

from rerai_agent.hub import build_graph  # noqa: F401

warnings.warn(
    "rerai_agent.graph is deprecated; use rerai_agent.hub.build_graph or AgentHub instead",
    DeprecationWarning,
    stacklevel=2,
)
