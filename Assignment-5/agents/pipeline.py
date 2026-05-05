"""Pipeline factory.

Wires the seven agents into a single dict so the top-level
`query_system_multiagent.py` only has to pull them and orchestrate the flow.
"""

from __future__ import annotations

from typing import Any

from agents.answer import synthesize_answer
from agents.diagnosis import DiagnosisAgent
from agents.executor import QueryExecutionAgent
from agents.explanation import ExplanationAgent
from agents.nlu import NLUnderstandingAgent
from agents.planner import QueryPlannerAgent
from agents.repair import QueryRepairAgent
from agents.security import SecurityAgent


def build_pipeline() -> dict[str, Any]:
    return {
        "nlu": NLUnderstandingAgent(),
        "security": SecurityAgent(),
        "planner": QueryPlannerAgent(),
        "executor": QueryExecutionAgent(),
        "diagnosis": DiagnosisAgent(),
        "repair": QueryRepairAgent(),
        "explanation": ExplanationAgent(),
        "synthesize_answer": synthesize_answer,
    }
