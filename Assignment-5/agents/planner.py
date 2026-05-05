"""Query Planner agent.

Builds a read-only retrieval plan from an Intent. The plan is a dict that the
Executor consumes (we do NOT inline raw Cypher into the plan because the
Executor must guarantee read-only semantics regardless of plan content).
"""

from __future__ import annotations

from typing import Any

from agents.types import Intent


# Domain-specific synonym expansion improves fulltext recall on this small KG.
_SYNONYMS: dict[str, list[str]] = {
    "late": ["late", "delay", "tardy"],
    "leave": ["leave", "exit", "depart"],
    "exam": ["exam", "examination", "test"],
    "id": ["ID", "identification", "card"],
    "card": ["card", "EasyCard", "Mifare"],
    "easycard": ["EasyCard"],
    "mifare": ["Mifare"],
    "fee": ["fee", "NTD", "cost", "price", "replacement"],
    "credit": ["credit", "credits"],
    "credits": ["credit", "credits"],
    "graduation": ["graduation", "graduate", "graduating"],
    "passing": ["passing", "pass", "score"],
    "score": ["score", "grade", "points"],
    "punish": ["punishment", "penalty", "discipline", "deduction"],
    "penalty": ["penalty", "punishment", "deduction", "discipline"],
    "cheat": ["cheat", "cheating", "copy", "copying"],
    "phone": ["phone", "electronic", "communication"],
    "electronic": ["electronic", "phone", "device", "communication"],
    "device": ["device", "electronic", "phone", "communication"],
    "absence": ["absence", "leave", "suspension"],
    "suspension": ["suspension", "absence"],
    "extension": ["extension", "extend"],
    "duration": ["duration", "period", "years"],
    "physical": ["physical", "PE"],
    "education": ["education", "PE"],
    "military": ["military", "training"],
    "threaten": ["threaten", "threats", "threat"],
    "invigilator": ["invigilator", "proctor"],
    "question": ["question", "paper"],
    "paper": ["paper", "question"],
    "forgot": ["forgot", "forgetting", "missing"],
    "forgetting": ["forgot", "forgetting", "missing"],
    "expel": ["expel", "expelled", "dismiss", "dismissal"],
    "dismiss": ["expel", "expelled", "dismiss", "dismissal"],
    "make-up": ["make-up", "makeup"],
    "bachelor": ["bachelor", "undergraduate"],
    "undergraduate": ["bachelor", "undergraduate"],
    "graduate": ["graduate", "master", "phd"],
}


def _expand(keywords: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        for token in _SYNONYMS.get(kw.lower(), [kw]):
            t = token.strip()
            if t and t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
    return out


def _to_lucene_query(terms: list[str], mode: str = "and") -> str:
    """Build a Lucene-style query string for Neo4j fulltext.

    - escape reserved characters
    - default to OR with boosted required terms when mode == 'should'
    """
    cleaned: list[str] = []
    for t in terms:
        t = t.strip()
        if not t:
            continue
        # Escape Lucene special chars.
        for ch in '+-&|!(){}[]^"~*?:\\/':
            t = t.replace(ch, " ")
        t = t.strip()
        if not t:
            continue
        if " " in t:
            cleaned.append(f'"{t}"')
        else:
            cleaned.append(t)
    if not cleaned:
        return ""
    if mode == "and":
        return " AND ".join(cleaned)
    return " OR ".join(cleaned)


class QueryPlannerAgent:
    """Returns an executable plan dict (read-only)."""

    def run(self, intent: Intent) -> dict[str, Any]:
        keywords = list(intent.keywords)
        expanded = _expand(keywords)
        primary = _to_lucene_query(keywords[:5], mode="or")
        broad = _to_lucene_query(expanded[:10], mode="or")
        return {
            "strategy": "typed_then_broad",
            "keywords": keywords,
            "expanded": expanded,
            "primary_query": primary,
            "broad_query": broad,
            "aspect": intent.aspect,
            "question_type": intent.question_type,
            "expected_unit": intent.expected_unit,
            "limit": 8,
        }
