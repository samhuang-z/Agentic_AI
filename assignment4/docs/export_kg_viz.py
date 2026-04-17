"""Export Neo4j KG subgraph snapshots as PNG images for the README.

Three figures are produced under ./docs/img/:

  1. kg_schema.png         — schema overview: Regulation -> Article -> Rule
  2. kg_sample_subgraph.png— a sampled instance subgraph around the exam
                             regulation (ncu6.pdf), showing real node labels
                             and rule_id / article number properties.
  3. kg_stats.png          — bar chart of node / rel counts per label.

Run after build_kg.py so Neo4j has live data:

    python docs/export_kg_viz.py
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (
    os.getenv("NEO4J_USER", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "password"),
)

OUT_DIR = Path(__file__).resolve().parent / "img"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _save(fig: plt.Figure, name: str) -> Path:
    path = OUT_DIR / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {path}")
    return path


def draw_schema() -> None:
    """High-level schema diagram (no DB call needed)."""
    G = nx.DiGraph()
    G.add_node("Regulation", kind="Regulation")
    G.add_node("Article", kind="Article")
    G.add_node("Rule", kind="Rule")
    G.add_edge("Regulation", "Article", label="HAS_ARTICLE")
    G.add_edge("Article", "Rule", label="CONTAINS_RULE")

    colors = {"Regulation": "#6fa8dc", "Article": "#93c47d", "Rule": "#f6b26b"}

    pos = {"Regulation": (0, 0), "Article": (1.2, 0), "Rule": (2.4, 0)}
    fig, ax = plt.subplots(figsize=(11, 4))
    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=[colors[n] for n in G.nodes],
        node_size=3800,
        edgecolors="#333",
        ax=ax,
    )
    nx.draw_networkx_labels(G, pos, font_size=12, font_weight="bold", ax=ax)
    nx.draw_networkx_edges(
        G, pos, arrows=True, arrowsize=28, node_size=3800, edge_color="#333", ax=ax
    )
    edge_labels = nx.get_edge_attributes(G, "label")
    nx.draw_networkx_edge_labels(
        G, pos, edge_labels=edge_labels, font_size=11, ax=ax
    )

    ax.set_title(
        "Assignment 4 KG Schema\n(Regulation)-[:HAS_ARTICLE]->(Article)-[:CONTAINS_RULE]->(Rule)",
        fontsize=13,
    )
    ax.set_axis_off()

    props = {
        "Regulation": "id, name, category",
        "Article": "number, content, reg_name, category",
        "Rule": "rule_id, type, action, result,\nart_ref, reg_name",
    }
    for node, (x, y) in pos.items():
        ax.text(
            x,
            y - 0.18,
            f"{{{props[node]}}}",
            ha="center",
            va="top",
            fontsize=9.5,
            color="#333",
            family="monospace",
        )

    ax.set_xlim(-0.7, 3.1)
    ax.set_ylim(-0.45, 0.35)
    _save(fig, "kg_schema.png")


def draw_sample_subgraph(driver) -> None:
    """Sample a small real subgraph from Neo4j (exam-related regulation)."""
    cypher = """
    MATCH (reg:Regulation)-[:HAS_ARTICLE]->(a:Article)-[:CONTAINS_RULE]->(r:Rule)
    WHERE toLower(a.reg_name) CONTAINS 'exam'
       OR toLower(reg.name)   CONTAINS 'exam'
    RETURN reg.name AS reg_name,
           a.number AS art_number,
           r.rule_id AS rule_id,
           r.type    AS rule_type,
           r.result  AS rule_result
    ORDER BY a.number, r.rule_id
    LIMIT 18
    """

    records: list[dict] = []
    with driver.session() as session:
        for row in session.run(cypher):
            records.append(dict(row))

    if not records:
        # Fallback: sample any regulation at all.
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (reg:Regulation)-[:HAS_ARTICLE]->(a:Article)-[:CONTAINS_RULE]->(r:Rule)
                RETURN reg.name AS reg_name, a.number AS art_number,
                       r.rule_id AS rule_id, r.type AS rule_type,
                       r.result AS rule_result
                LIMIT 18
                """
            )
            records = [dict(r) for r in rows]

    if not records:
        print("[warn] no KG data found — run build_kg.py first")
        return

    G = nx.DiGraph()
    reg_name = records[0]["reg_name"] or "Regulation"
    reg_label = f"Regulation\n{reg_name[:28]}..." if len(reg_name) > 28 else f"Regulation\n{reg_name}"
    G.add_node(reg_label, kind="Regulation")

    article_labels: dict[str, str] = {}
    for rec in records:
        art = rec["art_number"] or "?"
        art_key = f"Article\n{art}"
        if art_key not in article_labels:
            article_labels[art_key] = art_key
            G.add_node(art_key, kind="Article")
            G.add_edge(reg_label, art_key, label="HAS_ARTICLE")

        rid = rec["rule_id"]
        rtype = rec["rule_type"] or "general"
        rule_label = f"Rule {rid}\n({rtype})"
        G.add_node(rule_label, kind="Rule")
        G.add_edge(art_key, rule_label, label="CONTAINS_RULE")

    colors_map = {"Regulation": "#6fa8dc", "Article": "#93c47d", "Rule": "#f6b26b"}
    node_colors = [colors_map[G.nodes[n]["kind"]] for n in G.nodes]
    node_sizes = [
        3600 if G.nodes[n]["kind"] == "Regulation" else
        2600 if G.nodes[n]["kind"] == "Article" else 1800
        for n in G.nodes
    ]

    try:
        pos = nx.kamada_kawai_layout(G)
    except ImportError:
        pos = nx.spring_layout(G, seed=42, k=1.1, iterations=120)

    fig, ax = plt.subplots(figsize=(14, 9))
    nx.draw_networkx_nodes(
        G, pos, node_color=node_colors, node_size=node_sizes,
        edgecolors="#222", linewidths=1.2, ax=ax,
    )
    nx.draw_networkx_edges(
        G, pos, arrows=True, arrowsize=14, edge_color="#777",
        node_size=2600, width=1.1, ax=ax,
    )
    nx.draw_networkx_labels(G, pos, font_size=8.5, ax=ax)

    legend_handles = [
        plt.Line2D([0], [0], marker="o", color="w",
                   markerfacecolor=colors_map[k], markersize=14, label=k)
        for k in ("Regulation", "Article", "Rule")
    ]
    ax.legend(handles=legend_handles, loc="lower right", fontsize=10)
    ax.set_title(
        f"Sample KG subgraph — {reg_name}\n"
        "(live Neo4j export: 1 Regulation, multiple Articles, "
        "each containing Rules)",
        fontsize=12,
    )
    ax.set_axis_off()
    _save(fig, "kg_sample_subgraph.png")


def draw_stats(driver) -> None:
    """Bar chart of node / relationship counts."""
    cypher_counts = """
    MATCH (n)
    WITH labels(n)[0] AS lbl, count(*) AS c
    RETURN lbl, c ORDER BY c DESC
    """
    cypher_rel_counts = """
    MATCH ()-[r]->()
    WITH type(r) AS t, count(*) AS c
    RETURN t, c ORDER BY c DESC
    """

    with driver.session() as session:
        nodes = [(r["lbl"], r["c"]) for r in session.run(cypher_counts)]
        rels = [(r["t"], r["c"]) for r in session.run(cypher_rel_counts)]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))

    if nodes:
        labels, counts = zip(*nodes)
        bars = axes[0].bar(labels, counts, color=["#6fa8dc", "#93c47d", "#f6b26b"][: len(labels)])
        axes[0].set_title("Node counts by label")
        axes[0].bar_label(bars)
        axes[0].set_ylabel("count")
    if rels:
        labels, counts = zip(*rels)
        bars = axes[1].bar(labels, counts, color=["#8e7cc3", "#e06666"][: len(labels)])
        axes[1].set_title("Relationship counts by type")
        axes[1].bar_label(bars)

    fig.suptitle("Neo4j KG statistics (live build)", fontsize=13)
    fig.tight_layout()
    _save(fig, "kg_stats.png")


def main() -> None:
    driver = GraphDatabase.driver(URI, auth=AUTH)
    driver.verify_connectivity()
    try:
        draw_schema()
        draw_sample_subgraph(driver)
        draw_stats(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
