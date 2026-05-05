"""Diagnosis agent.

Maps an executor result to one of the four contract labels:
- SUCCESS:           rows present and look usable
- NO_DATA:           query ran cleanly but returned nothing
- QUERY_ERROR:       executor itself raised (driver / Cypher error)
- SCHEMA_MISMATCH:   query referenced fields/indexes the KG does not have
"""

from __future__ import annotations

from typing import Any


_SCHEMA_HINTS = (
    "no such index", "unknown function", "no such property",
    "variable `", "index does not exist", "no procedure with the name",
    "rule_idx", "article_content_idx",
)


class DiagnosisAgent:
    def run(self, execution: dict[str, Any]) -> dict[str, str]:
        rows = execution.get("rows") or []
        err = execution.get("error")

        if rows:
            return {"label": "SUCCESS", "reason": f"{len(rows)} row(s) retrieved."}

        if not err or err == "empty":
            return {"label": "NO_DATA", "reason": "No matching rule/article in KG."}

        if err == "empty_query":
            return {"label": "QUERY_ERROR", "reason": "Planner produced an empty query."}

        if err == "neo4j_unavailable":
            return {"label": "QUERY_ERROR", "reason": "Neo4j driver unavailable."}

        err_l = str(err).lower()
        if any(h in err_l for h in _SCHEMA_HINTS):
            return {"label": "SCHEMA_MISMATCH", "reason": str(err)[:200]}

        return {"label": "QUERY_ERROR", "reason": str(err)[:200]}
