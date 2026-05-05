"""NL Understanding agent.

Converts a natural-language question into a structured Intent that downstream
planning/repair agents can act on. Deterministic, no LLM dependency.
"""

from __future__ import annotations

import re

from agents.types import Intent


_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "of", "to", "in", "on", "for", "and", "or",
    "i", "me", "my", "you", "your", "we", "our", "it", "this", "that",
    "what", "which", "who", "whom", "where", "when", "why", "how",
    "can", "could", "should", "would", "may", "might", "must", "will", "shall",
    "if", "then", "than", "as", "at", "by", "with", "without", "from",
    "about", "into", "out", "over", "under", "after", "before",
    "any", "all", "every", "some", "no", "not", "only",
    "up", "down", "off", "such", "so", "but",
    "have", "has", "had", "get", "got", "go", "going", "make", "made",
    "ok", "okay", "fine", "maybe", "probably", "really", "very", "much",
    "like", "just", "yet", "more", "most", "less", "least",
    "they", "them", "their", "his", "her", "him", "she", "he",
    "there", "here", "now", "still",
    "tell", "say", "said", "saying", "ask", "asked",
    "regulation", "regulations", "rule", "rules", "article",
}

# Map from question intent to expected numeric unit / final answer flavour.
_UNIT_HINTS = [
    ("minutes", ["minute", "minutes", "late", "leave the exam", "barred"]),
    ("NTD",     ["fee", "cost", "price", "ntd", "dollar", "replacement"]),
    ("credits", ["credit", "credits"]),
    ("years",   ["year", "years", "duration", "extension", "absence", "suspension"]),
    ("semesters", ["semester", "semesters", "physical education", " pe "]),
    ("days",    ["working day", "working days", "days"]),
    ("score",   ["passing score", "score", "points"]),
]

# Question typing.
_TIME_HINTS    = {"minute", "minutes", "hour", "hours", "day", "days", "year", "years", "semester", "semesters", "duration", "long"}
_FEE_HINTS     = {"fee", "cost", "price", "dollar", "ntd"}
_PENALTY_HINTS = {"penalty", "punish", "punishment", "sanction", "deduction", "deduct", "happens", "consequence"}
_CREDIT_HINTS  = {"credit", "credits", "graduate", "graduation", "passing"}
_REQ_HINTS     = {"required", "requirement", "must", "mandatory", "allowed", "permitted"}

_ASPECT_HINTS = {
    "exam":   {"exam", "exams", "invigilator", "cheat", "cheating", "test", "question paper"},
    "admin":  {"id", "card", "easycard", "mifare", "replacement", "lost"},
    "credit": {"credit", "credits", "graduation", "graduate"},
    "grade":  {"grade", "grades", "score", "passing", "fail", "failed"},
    "course": {"course", "courses", "selection", "enrolment", "enroll"},
}


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\-\s]", " ", text)
    return [t for t in text.split() if t]


def _classify_question(tokens: set[str], raw_lower: str) -> tuple[str, bool]:
    if any(t in tokens for t in _FEE_HINTS):
        return "fee", False
    if any(t in tokens for t in _TIME_HINTS) or "how long" in raw_lower or "how many" in raw_lower:
        if any(t in tokens for t in _CREDIT_HINTS):
            return "credit", False
        return "time", False
    if any(t in tokens for t in _PENALTY_HINTS):
        return "penalty", False
    if any(t in tokens for t in _CREDIT_HINTS):
        return "credit", False
    if any(t in tokens for t in _REQ_HINTS):
        return "requirement", False
    if raw_lower.startswith(("can ", "is ", "are ", "do ", "does ", "did ", "may ", "could ", "should ")):
        return "yes_no", True
    return "general", False


def _detect_unit(raw_lower: str) -> str | None:
    for unit, hints in _UNIT_HINTS:
        for h in hints:
            if h in raw_lower:
                return unit
    return None


def _detect_aspect(tokens: set[str]) -> str:
    for aspect, hints in _ASPECT_HINTS.items():
        if tokens & hints:
            return aspect
    return "general"


class NLUnderstandingAgent:
    """Parses a question into a structured Intent (deterministic)."""

    def run(self, question: str) -> Intent:
        raw = (question or "").strip()
        raw_lower = raw.lower()
        tokens = _tokenize(raw_lower)
        token_set = set(tokens)

        keywords = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
        # Preserve order, drop duplicates.
        seen: set[str] = set()
        ordered_keywords: list[str] = []
        for t in keywords:
            if t not in seen:
                seen.add(t)
                ordered_keywords.append(t)

        qtype, polarity = _classify_question(token_set, raw_lower)
        aspect = _detect_aspect(token_set)
        unit = _detect_unit(raw_lower)

        # If the question is so short that we have <2 keywords after stopwording,
        # treat as ambiguous so the planner can broaden later.
        ambiguous = len(ordered_keywords) < 2

        return Intent(
            question_type=qtype,
            keywords=ordered_keywords,
            aspect=aspect,
            expected_unit=unit,
            polarity_question=polarity,
            raw=raw,
            ambiguous=ambiguous,
        )
