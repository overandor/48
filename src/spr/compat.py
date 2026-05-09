"""Compatibility layer over the current single-file prototype runtime.

This lets the new production package grow around the existing working prototype
without breaking current behavior. The long-term path is to move these classes
into first-class modules, but the production wedge can start with stable wrappers.
"""

from __future__ import annotations

from semantic_protocol_runtime import (  # type: ignore
    BaseLLMAdapter,
    ExecutionPlan,
    GraphBuilder,
    Planner,
    Program,
    ProgramGraph,
    ProgramParser,
    ProgramVerifier,
    PythonLowerer,
    SQLLowerer,
)

__all__ = [
    "BaseLLMAdapter",
    "ExecutionPlan",
    "GraphBuilder",
    "Planner",
    "Program",
    "ProgramGraph",
    "ProgramParser",
    "ProgramVerifier",
    "PythonLowerer",
    "SQLLowerer",
]
