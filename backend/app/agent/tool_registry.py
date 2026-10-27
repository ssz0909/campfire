from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.models.role import Permission


@dataclass
class ToolDefinition:
    name: str
    version: str
    description: str
    input_schema: dict
    output_schema: dict
    required_permissions: list[Permission]
    risk_level: str  # low | medium | high | critical
    requires_approval: bool
    timeout_seconds: int
    max_retries: int
    is_idempotent: bool
    estimated_cost_description: str
    log_strategy: str  # minimal | standard | full


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[ToolDefinition, Callable]] = {}

    def register(self, tool_def: ToolDefinition, handler_fn: Callable) -> None:
        if tool_def.name in self._tools:
            raise ValueError(f"Tool '{tool_def.name}' is already registered")
        self._tools[tool_def.name] = (tool_def, handler_fn)

    def get(self, name: str) -> tuple[ToolDefinition, Callable]:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def check_permission(
        self, tool_name: str, user_permissions: set[Permission]
    ) -> bool:
        tool_def, _ = self.get(tool_name)
        return all(p in user_permissions for p in tool_def.required_permissions)

    def list_available(
        self, user_permissions: set[Permission]
    ) -> list[ToolDefinition]:
        return [
            tool_def
            for tool_def, _ in self._tools.values()
            if all(p in user_permissions for p in tool_def.required_permissions)
        ]


# Global registry instance
tool_registry = ToolRegistry()
