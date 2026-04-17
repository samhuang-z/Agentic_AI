"""KG builder for Assignment 4.

Schema (do not change):
    (Regulation)-[:HAS_ARTICLE]->(Article)-[:CONTAINS_RULE]->(Rule)
    Article: number, content, reg_name, category
    Rule:    rule_id, type, action, result, art_ref, reg_name
    Fulltext indexes: article_content_idx, rule_idx
    SQLite file: ncu_regulations.db

Rule extraction is deterministic (regex/keyword based) so the build is
reproducible and fast on CPU. The goal is to surface the *fact-bearing*
sentences inside each article (numbers, penalties, durations, fees) as
Rule nodes that can be retrieved via the rule_idx fulltext index.
"""

import os
import re
import sqlite3
from typing import Any

from dotenv import load_dotenv
from neo4j import GraphDatabase


# ========== 0) Initialization ==========
load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (
    os.getenv("NEO4J_USER", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "password"),
)


# ---------------------------------------------------------------------------
# Deterministic rule extraction
# ---------------------------------------------------------------------------

# Numeric / unit patterns that usually mark a fact-bearing sentence.
NUMERIC_PATTERNS: list[tuple[str, str]] = [
    (r"\b(\d+)\s*minutes?\b", "duration"),
    (r"\b(\d+)\s*hours?\b", "duration"),
    (r"\b(\d+)\s*(?:working\s*days?|workdays?)\b", "duration"),
    (r"\b(\d+)\s*days?\b", "duration"),
    (r"\b(\d+)\s*semesters?\b", "duration"),
    (r"\b(\d+)\s*(?:academic\s*)?years?\b", "duration"),
    (r"\b(\d+)\s*credits?\b", "credit"),
    (r"\b(\d+)\s*course\s*credits?\b", "credit"),
    (r"\b(\d+)\s*(?:points?|marks?)\b", "score"),
    (r"\bNTD?\s*\$?\s*(\d+)\b", "fee"),
    (r"\b(\d+)\s*NTD?\b", "fee"),
    (r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)\s+"
     r"(?:minutes?|hours?|days?|semesters?|years?|credits?|points?|marks?)\b", "duration"),
    (r"\b(?:half|one[- ]?third|two[- ]?thirds?|one[- ]?fourth|one[- ]?half)\b", "fraction"),
]

PENALTY_KEYWORDS = [
    "zero grade",
    "zero score",
    "shall receive a zero",
    "points deducted",
    "deducted from",
    "forced to withdraw",
    "expelled",
    "disciplinary",
    "shall not be permitted",
    "not permitted to",
    "prohibited",
    "violators",
    "withdraw from school",
    "disqualified",
    "cancelled",
    "shall be barred",
]

# Topical keywords — sentences that mention any of these are also kept as
# Rule nodes even if they don't carry an explicit number/penalty signal.
TOPIC_KEYWORDS = [
    "military training",
    "physical education",
    "pe interest",
    "freshman pe",
    "make-up",
    "make up exam",
    "graduation",
    "graduate",
    "easycard",
    "mifare",
    "student id",
    "passing grade",
    "lowest passing",
    "leave of absence",
    "suspension",
    "resumption",
    "withdraw",
    "expel",
    "elective",
    "not included",
    "not counted",
    "not count toward",
    "do not count",
    "does not count",
    "exam room",
    "exam paper",
    "proctor",
]


def split_sentences(text: str) -> list[str]:
    """Split an article into rough sentences, preserving useful clauses."""
    if not text:
        return []
    # First, split on sentence punctuation (., ;, !, ?) followed by a space and capital/digit.
    parts = re.split(r"(?<=[.;!?])\s+(?=[A-Z0-9\"'(])", text.strip())
    result: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Further split numbered list items inside the same sentence.
        sub = re.split(r"\s+(?=\d+\.\s+[A-Z])", part)
        for s in sub:
            s = s.strip(" .;")
            if len(s) >= 12:
                result.append(s)
    return result


def classify_rule(sentence: str) -> tuple[str, str]:
    """Return (rule_type, normalized_result_phrase)."""
    s = sentence.lower()

    # Penalty type wins if explicit consequence keywords appear.
    if any(k in s for k in PENALTY_KEYWORDS):
        # Try to grab the consequence clause around the keyword.
        for k in PENALTY_KEYWORDS:
            idx = s.find(k)
            if idx >= 0:
                start = max(0, idx - 10)
                end = min(len(sentence), idx + 80)
                return "penalty", sentence[start:end].strip()
        return "penalty", sentence[:120].strip()

    # Otherwise, look for the first numeric / unit match.
    for pat, label in NUMERIC_PATTERNS:
        m = re.search(pat, sentence, flags=re.IGNORECASE)
        if m:
            ctx_start = max(0, m.start() - 25)
            ctx_end = min(len(sentence), m.end() + 50)
            return label, sentence[ctx_start:ctx_end].strip()

    return "general", sentence[:120].strip()


def extract_entities(article_number: str, reg_name: str, content: str) -> dict[str, Any]:
    """Return {"rules": [...]} of fact-bearing sentences inside this article."""
    rules: list[dict[str, str]] = []
    seen: set[str] = set()

    sentences = split_sentences(content)
    for sent in sentences:
        sl = sent.lower()
        has_num = any(re.search(p, sent, re.IGNORECASE) for p, _ in NUMERIC_PATTERNS)
        has_pen = any(k in sl for k in PENALTY_KEYWORDS)
        has_topic = any(k in sl for k in TOPIC_KEYWORDS)
        if not (has_num or has_pen or has_topic):
            continue

        rule_type, result_phrase = classify_rule(sent)
        action = sent[:240]
        key = (rule_type, action[:80])
        if key in seen:
            continue
        seen.add(key)

        rules.append(
            {
                "type": rule_type,
                "action": action,
                "result": result_phrase[:240] or action,
            }
        )

    # Always keep at least one fallback rule per article so that retrieval can
    # still hit short articles via the rule_idx index.
    if not rules and content.strip():
        rules.append(
            {
                "type": "general",
                "action": content.strip()[:240],
                "result": content.strip()[:240],
            }
        )

    return {"rules": rules}


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


def build_graph() -> None:
    sql_conn = sqlite3.connect("ncu_regulations.db")
    cursor = sql_conn.cursor()
    driver = GraphDatabase.driver(URI, auth=AUTH)

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

        # Drop existing fulltext indexes so we can recreate cleanly.
        for idx in ("article_content_idx", "rule_idx"):
            try:
                session.run(f"DROP INDEX {idx} IF EXISTS")
            except Exception:
                pass

        # 1) Regulation nodes
        cursor.execute("SELECT reg_id, name, category FROM regulations")
        regulations = cursor.fetchall()
        reg_map: dict[int, tuple[str, str]] = {}

        for reg_id, name, category in regulations:
            reg_map[reg_id] = (name, category)
            session.run(
                "MERGE (r:Regulation {id:$rid}) SET r.name=$name, r.category=$cat",
                rid=reg_id,
                name=name,
                cat=category,
            )

        # 2) Article nodes + HAS_ARTICLE
        cursor.execute("SELECT reg_id, article_number, content FROM articles")
        articles = cursor.fetchall()

        for reg_id, article_number, content in articles:
            reg_name, reg_category = reg_map.get(reg_id, ("Unknown", "Unknown"))
            session.run(
                """
                MATCH (r:Regulation {id: $rid})
                CREATE (a:Article {
                    number:   $num,
                    content:  $content,
                    reg_name: $reg_name,
                    category: $reg_category
                })
                MERGE (r)-[:HAS_ARTICLE]->(a)
                """,
                rid=reg_id,
                num=article_number,
                content=content,
                reg_name=reg_name,
                reg_category=reg_category,
            )

        # 3) Article fulltext index
        session.run(
            """
            CREATE FULLTEXT INDEX article_content_idx IF NOT EXISTS
            FOR (a:Article) ON EACH [a.content]
            """
        )

        # 4) Rule extraction + CONTAINS_RULE
        rule_counter = 0
        for reg_id, article_number, content in articles:
            reg_name, _ = reg_map.get(reg_id, ("Unknown", "Unknown"))
            extracted = extract_entities(article_number, reg_name, content)
            for rule in extracted.get("rules", []):
                action = (rule.get("action") or "").strip()
                result = (rule.get("result") or "").strip()
                if not action and not result:
                    continue
                rule_counter += 1
                rule_id = f"R{rule_counter:05d}"
                session.run(
                    """
                    MATCH (a:Article {number: $num, reg_name: $reg_name})
                    CREATE (rule:Rule {
                        rule_id:  $rule_id,
                        type:     $type,
                        action:   $action,
                        result:   $result,
                        art_ref:  $art_ref,
                        reg_name: $reg_name
                    })
                    MERGE (a)-[:CONTAINS_RULE]->(rule)
                    """,
                    num=article_number,
                    reg_name=reg_name,
                    rule_id=rule_id,
                    type=rule.get("type", "general"),
                    action=action,
                    result=result,
                    art_ref=article_number,
                )

        # 5) Rule fulltext index
        session.run(
            """
            CREATE FULLTEXT INDEX rule_idx IF NOT EXISTS
            FOR (r:Rule) ON EACH [r.action, r.result]
            """
        )

        # 6) Coverage audit
        coverage = session.run(
            """
            MATCH (a:Article)
            OPTIONAL MATCH (a)-[:CONTAINS_RULE]->(r:Rule)
            WITH a, count(r) AS rule_count
            RETURN count(a) AS total_articles,
                   sum(CASE WHEN rule_count > 0 THEN 1 ELSE 0 END) AS covered_articles,
                   sum(CASE WHEN rule_count = 0 THEN 1 ELSE 0 END) AS uncovered_articles
            """
        ).single()

        total_articles = int((coverage or {}).get("total_articles", 0) or 0)
        covered_articles = int((coverage or {}).get("covered_articles", 0) or 0)
        uncovered_articles = int((coverage or {}).get("uncovered_articles", 0) or 0)

        print(
            f"[KG] articles={total_articles}, rules={rule_counter}, "
            f"covered={covered_articles}/{total_articles}, "
            f"uncovered={uncovered_articles}"
        )

    driver.close()
    sql_conn.close()


if __name__ == "__main__":
    build_graph()
