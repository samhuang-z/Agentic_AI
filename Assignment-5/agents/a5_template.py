"""Backwards-compat shim.

The original starter pack used `agents.a5_template.build_template_pipeline()`.
The actual implementation now lives in modular files (`agents/nlu.py`,
`agents/security.py`, ...). This shim re-exports them under their old names so
any lingering import that still references the template path keeps working.
"""

from __future__ import annotations

from typing import Any

from agents.diagnosis import DiagnosisAgent
from agents.executor import QueryExecutionAgent
from agents.explanation import ExplanationAgent
from agents.nlu import NLUnderstandingAgent
from agents.planner import QueryPlannerAgent
from agents.repair import QueryRepairAgent
from agents.security import SecurityAgent
from agents.types import Intent

__all__ = [
    "Intent",
    "NLUnderstandingAgent",
    "SecurityAgent",
    "QueryPlannerAgent",
    "QueryExecutionAgent",
    "DiagnosisAgent",
    "QueryRepairAgent",
    "ExplanationAgent",
    "build_template_pipeline",
]


def build_template_pipeline() -> dict[str, Any]:
    return {
        "nlu": NLUnderstandingAgent(),
        "security": SecurityAgent(),
        "planner": QueryPlannerAgent(),
        "executor": QueryExecutionAgent(),
        "diagnosis": DiagnosisAgent(),
        "repair": QueryRepairAgent(),
        "explanation": ExplanationAgent(),
    }
