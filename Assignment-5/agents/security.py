"""Security / Policy agent.

Rejects any question that:
1. Tries to mutate / destroy KG data (Cypher write keywords).
2. Attempts prompt-injection ("ignore previous", "pretend you are admin", ...).
3. Asks for raw bulk data exfiltration ("dump all", "every regulation word-by-word").
4. Asks the system to bypass its own safety machinery.

The check is intentionally regex-/keyword-based and runs BEFORE any KG access,
so even a malicious payload that could trick a downstream LLM never reaches it.
"""

from __future__ import annotations

import re
from typing import Any

from agents.types import Intent


# Cypher mutation / admin verbs.
_CYPHER_WRITE = re.compile(
    r"\b(delete|detach\s+delete|drop|create\s+index|drop\s+index|merge|set\s+\w|"
    r"remove\s+\w|call\s+db\.|call\s+dbms|load\s+csv|alter|truncate)\b",
    re.IGNORECASE,
)

# Prompt-injection / role-swap.
_INJECTION = re.compile(
    r"(ignore\s+(all\s+)?previous|disregard\s+(all\s+)?previous|"
    r"pretend\s+you\s+are|act\s+as\s+(admin|root|system)|"
    r"disable\s+(safety|security|guardrails)|"
    r"i\s+authorize\s+you|bypass\s+(security|safety|check|policy)|"
    r"override\s+(safety|security|policy))",
    re.IGNORECASE,
)

# Bulk exfiltration / data dump.
_BULK_EXFIL = re.compile(
    r"(dump\s+(all|every|the\s+entire)|export\s+(the\s+)?entire|"
    r"return\s+all\s+(rule|node|article|database)|"
    r"list\s+all\s+rule\s+nodes|output\s+all\s+rule|"
    r"every\s+regulation\s+(content\s+)?word|word[-\s]by[-\s]word|"
    r"raw\s+json|database\s+credentials|all\s+credentials|"
    r"summarize\s+every\s+(fee|rule|regulation)\s+in\s+all)",
    re.IGNORECASE,
)

# Fake-rule injection / write requests phrased in English.
_WRITE_INTENT = re.compile(
    r"(modify\s+penalt|add\s+(new\s+)?(fake\s+)?rule|change\s+(the\s+)?(rule|penalty)|"
    r"insert\s+(a\s+)?rule|update\s+the\s+graph)",
    re.IGNORECASE,
)


class SecurityAgent:
    def run(self, question: str, intent: Intent) -> dict[str, Any]:
        q = (question or "").strip()
        if not q:
            return {"decision": "REJECT", "reason": "Empty question."}

        if _CYPHER_WRITE.search(q):
            return {"decision": "REJECT", "reason": "Write/admin Cypher keyword detected."}
        if _INJECTION.search(q):
            return {"decision": "REJECT", "reason": "Prompt-injection / role-swap pattern detected."}
        if _BULK_EXFIL.search(q):
            return {"decision": "REJECT", "reason": "Bulk data exfiltration request blocked."}
        if _WRITE_INTENT.search(q):
            return {"decision": "REJECT", "reason": "Graph mutation intent blocked."}

        return {"decision": "ALLOW", "reason": "Passed security policy."}
