from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Self


@dataclass
class SubagentSpec:
    name: str
    description: str
    system_prompt: str
    tool_names: set[str] = field(default_factory=set)
    model_factory: Callable[[], Any] | None = None


@dataclass(frozen=True)
class AssembledConfig:
    model: Any
    tools: list[Callable]
    subagents: list[dict[str, Any]]
    memory: list[str]
    skills: list[str]
    system_prompt: str | None


class Registry:
    def __init__(
        self,
        *,
        chat_model_factory: Callable[[], Any] | None = None,
        subagent_model_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._chat_model_factory = chat_model_factory
        self._subagent_model_factory = subagent_model_factory
        self._tools: dict[str, Callable] = {}
        self._subagents: dict[str, SubagentSpec] = {}

    def with_tool(self, name: str, tool: Callable) -> Self:
        self._tools[name] = tool
        return self

    def without_tool(self, name: str) -> Self:
        self._tools.pop(name, None)
        return self

    def with_subagent(self, spec: SubagentSpec) -> Self:
        self._subagents[spec.name] = spec
        return self

    def without_subagent(self, name: str) -> Self:
        self._subagents.pop(name, None)
        return self

    def assemble(
        self,
        *,
        memory: list[str] | None = None,
        skills: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> AssembledConfig:
        chat_model = self._chat_model_factory() if self._chat_model_factory else None

        tools = list(self._tools.values())

        subagents: list[dict[str, Any]] = []
        for spec in self._subagents.values():
            subagent_model = (
                spec.model_factory()
                if spec.model_factory
                else (
                    self._subagent_model_factory()
                    if self._subagent_model_factory
                    else None
                )
            )
            subagent_tools = [
                self._tools[name] for name in spec.tool_names if name in self._tools
            ]
            subagents.append(
                {
                    "name": spec.name,
                    "description": spec.description,
                    "system_prompt": spec.system_prompt,
                    "model": subagent_model,
                    "tools": subagent_tools,
                }
            )

        return AssembledConfig(
            model=chat_model,
            tools=tools,
            subagents=subagents,
            memory=memory if memory is not None else [],
            skills=skills if skills is not None else [],
            system_prompt=system_prompt,
        )
