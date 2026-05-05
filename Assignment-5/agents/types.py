"""Shared dataclasses for the A5 multi-agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Intent:
    question_type: str            # one of: time, fee, penalty, credit, requirement, yes_no, general
    keywords: list[str] = field(default_factory=list)
    aspect: str = "general"       # exam, admin, course, grade, credit, general
    expected_unit: str | None = None  # "minutes", "NTD", "credits", "years", ...
    polarity_question: bool = False   # True for yes/no
    raw: str = ""
    ambiguous: bool = False
