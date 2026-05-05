"""Query Execution agent.

Runs read-only Cypher against Neo4j. The executor never accepts arbitrary Cypher
from upstream — it only renders parameterised, hard-coded read templates so a
malicious or buggy planner cannot escalate to a write.
"""

from __future__ import annotations

import os
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

# Neo4j is optional at import time; we connect lazily so that running the
# pipeline file in a checker environment (no DB) does not crash on import.
_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
_AUTH = (
    os.getenv("NEO4J_USER", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "password"),
)


class QueryExecutionAgent:
    def __init__(self) -> None:
        try:
            self._driver = GraphDatabase.driver(_URI, auth=_AUTH)
            self._driver.verify_connectivity()
        except Exception as e:  # noqa: BLE001
            print(f"[Executor] Neo4j connection warning: {e}")
            self._driver = None

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _read(self, cypher: str, **params: Any) -> list[dict[str, Any]]:
        if self._driver is None:
            raise RuntimeError("Neo4j driver unavailable.")
        with self._driver.session(default_access_mode="READ") as session:
            result = session.run(cypher, **params)
            return [dict(rec) for rec in result]

    def _search_rules(self, query: str, limit: int) -> list[dict[str, Any]]:
        cypher = """
        CALL db.index.fulltext.queryNodes('rule_idx', $q)
          YIELD node, score
        OPTIONAL MATCH (a:Article)-[:CONTAINS_RULE]->(node)
        RETURN node.rule_id   AS rule_id,
               node.type      AS type,
               node.action    AS action,
               node.result    AS result,
               node.art_ref   AS art_ref,
               node.reg_name  AS reg_name,
               coalesce(a.content, '') AS article_content,
               score
        ORDER BY score DESC
        LIMIT $limit
        """
        return self._read(cypher, q=query, limit=limit)

    def _search_articles(self, query: str, limit: int) -> list[dict[str, Any]]:
        cypher = """
        CALL db.index.fulltext.queryNodes('article_content_idx', $q)
          YIELD node, score
        RETURN node.number   AS art_ref,
               node.reg_name AS reg_name,
               node.category AS category,
               node.content  AS article_content,
               score
        ORDER BY score DESC
        LIMIT $limit
        """
        return self._read(cypher, q=query, limit=limit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        if self._driver is None:
            return {"rows": [], "error": "neo4j_unavailable", "plan": plan}

        primary = plan.get("primary_query", "")
        broad = plan.get("broad_query", "")
        limit = int(plan.get("limit", 8))

        rows: list[dict[str, Any]] = []
        sources: list[str] = []
        last_error: str | None = None

        # 1) Typed retrieval against rule_idx with the precise terms.
        if primary:
            try:
                r = self._search_rules(primary, limit)
                if r:
                    sources.append("rule_idx:primary")
                    rows.extend(r)
            except Neo4jError as e:
                last_error = f"rule_idx primary: {e.message}"

        # 2) Fallback to broad expansion if primary returned nothing.
        if not rows and broad:
            try:
                r = self._search_rules(broad, limit)
                if r:
                    sources.append("rule_idx:broad")
                    rows.extend(r)
            except Neo4jError as e:
                last_error = f"rule_idx broad: {e.message}"

        # 3) Fall through to article-content search as a recall safety net.
        if not rows:
            for q, tag in [(primary, "article:primary"), (broad, "article:broad")]:
                if not q:
                    continue
                try:
                    r = self._search_articles(q, limit)
                    if r:
                        sources.append(tag)
                        rows.extend(r)
                        break
                except Neo4jError as e:
                    last_error = f"{tag}: {e.message}"

        return {
            "rows": rows,
            "error": None if rows else (last_error or ("empty" if (primary or broad) else "empty_query")),
            "sources": sources,
            "plan": plan,
        }
