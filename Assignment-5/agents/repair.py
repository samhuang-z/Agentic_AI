"""Query Repair agent.

Single-round repair. Given a failure diagnosis, produce a *different* plan that
broadens recall (synonyms only, drop low-signal terms, switch to OR).
"""

from __future__ import annotations

from typing import Any

from agents.types import Intent


# Terms that rarely help retrieval and often hurt fulltext relevance.
_LOW_SIGNAL = {
    "regulation", "regulations", "rule", "rules", "article",
    "student", "students", "school", "university",
    "happen", "happens", "happened", "case", "situation",
    "thing", "things", "stuff", "general", "generally",
    "process", "processes", "overall", "total",
    "exact", "exactly", "every", "all",
    "ok", "okay", "fine", "maybe", "probably",
}


class QueryRepairAgent:
    def run(
        self,
        diagnosis: dict[str, str],
        original_plan: dict[str, Any],
        intent: Intent,
    ) -> dict[str, Any]:
        plan = dict(original_plan)
        keywords = list(plan.get("keywords") or [])
        expanded = list(plan.get("expanded") or [])

        # Strategy A — drop low-signal tokens that may have over-narrowed the query.
        trimmed = [k for k in keywords if k.lower() not in _LOW_SIGNAL]

        # Strategy B — fall back to expanded (synonym) set if trimming left us empty.
        if not trimmed:
            trimmed = expanded[:6] if expanded else keywords

        # Strategy C — for SCHEMA_MISMATCH, route to article-only fallback.
        if diagnosis.get("label") == "SCHEMA_MISMATCH":
            plan["strategy"] = "article_fallback"
        else:
            plan["strategy"] = "broadened_or"

        # Rebuild queries (OR semantics, broader).
        primary_terms = trimmed[:6]
        broad_terms = list(dict.fromkeys(trimmed + expanded))[:12]

        plan["keywords"] = trimmed
        plan["expanded"] = broad_terms
        plan["primary_query"] = " OR ".join(_escape(t) for t in primary_terms)
        plan["broad_query"]   = " OR ".join(_escape(t) for t in broad_terms)
        plan["limit"] = max(int(plan.get("limit", 8)), 12)
        return plan


def _escape(term: str) -> str:
    out = term
    for ch in '+-&|!(){}[]^"~*?:\\/':
        out = out.replace(ch, " ")
    out = out.strip()
    if not out:
        return ""
    return f'"{out}"' if " " in out else out
