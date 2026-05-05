"""Explanation agent.

Emits a single-line trace summarising the path each request took through the
pipeline. Useful both for grading transparency and for post-mortem debugging
of failure / unsafe cases.
"""

from __future__ import annotations

from typing import Any

from agents.types import Intent


class ExplanationAgent:
    def run(
        self,
        question: str,
        intent: Intent,
        security: dict[str, Any],
        diagnosis: dict[str, Any],
        answer: str,
        repair_attempted: bool,
        sources: list[str] | None = None,
    ) -> str:
        kw = ",".join(intent.keywords[:5]) if intent.keywords else "-"
        srcs = ",".join(sources) if sources else "-"
        return (
            f"intent={intent.question_type}/{intent.aspect}"
            f" unit={intent.expected_unit or '-'}"
            f" keywords=[{kw}]"
            f" security={security.get('decision')}({security.get('reason','')[:40]})"
            f" diagnosis={diagnosis.get('label')}({diagnosis.get('reason','')[:40]})"
            f" repair={repair_attempted}"
            f" sources={srcs}"
            f" | answer: {answer[:160]}"
        )
