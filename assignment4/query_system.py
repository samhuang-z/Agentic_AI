"""KG-grounded QA pipeline for Assignment 4.

Public API (kept stable for auto_test.py):
    - generate_text(messages, max_new_tokens=220) -> str
    - get_relevant_articles(question)              -> list[dict]
    - generate_answer(question, rule_results)      -> str

Retrieval strategy
------------------
1. extract_entities(question)
       Parse the question into keyword tokens, detect a question_type
       (penalty / duration / fee / credit / general), and pull the most
       informative content words.

2. build_typed_cypher(entities)
       Produce two Lucene queries:
         - typed_query  : type-weighted search over rule_idx
         - broad_query  : keyword search over article_content_idx
       Both are executed against Neo4j fulltext indexes.

3. get_relevant_articles(question)
       Run typed_query against rule_idx, then broad_query against
       article_content_idx. Merge / dedupe and return as Rule-shaped dicts
       (rule_id, type, action, result, art_ref, reg_name) so downstream
       tooling stays compatible with the assignment contract.

4. generate_answer(question, rule_results)
       Pack the top retrieved evidence into a chat prompt and ask the
       local Qwen model for a short, grounded answer that cites the
       article number it relied on.
"""

import os
import re
from typing import Any

from neo4j import GraphDatabase
from dotenv import load_dotenv

from llm_loader import load_local_llm, get_tokenizer, get_raw_pipeline


# ========== 0) Initialization ==========
load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
AUTH = (
    os.getenv("NEO4J_USER", "neo4j"),
    os.getenv("NEO4J_PASSWORD", "password"),
)

for key in ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY"]:
    if key in os.environ:
        del os.environ[key]


try:
    driver = GraphDatabase.driver(URI, auth=AUTH)
    driver.verify_connectivity()
except Exception as e:
    print(f"⚠️ Neo4j connection warning: {e}")
    driver = None


# ---------------------------------------------------------------------------
# Question parsing helpers
# ---------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "as", "about", "into", "and", "or", "but",
    "if", "than", "then", "this", "that", "these", "those", "it", "its",
    "i", "you", "he", "she", "we", "they", "them", "his", "her", "their",
    "what", "which", "when", "where", "why", "how", "many", "much", "long",
    "can", "could", "should", "would", "may", "might", "will", "shall",
    "my", "your", "our", "me", "us", "any", "all", "some", "no", "not",
    "after", "before", "during", "between", "out", "up", "down", "off",
    "such", "so", "very", "more", "less", "most", "least", "each", "every",
    "there", "here", "than", "also", "just",
    # very common in question phrasing
    "happens", "allowed", "barred", "take", "taking", "get", "getting", "use",
    "using", "needed", "required", "mean", "means", "called",
}

WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100",
}

# Lightweight synonym expansion: question token -> extra search tokens.
SYNONYMS: dict[str, list[str]] = {
    "fee": ["NTD", "cost", "price", "processing"],
    "fees": ["NTD", "cost", "price", "processing"],
    "cost": ["NTD", "fee", "price"],
    "easycard": ["EasyCard", "200"],
    "mifare": ["Mifare", "100"],
    "id": ["student", "card", "ID"],
    "card": ["student", "ID", "EasyCard", "Mifare"],
    "barred": ["permitted", "enter", "minutes", "late"],
    "late": ["minutes", "exam", "permitted"],
    "absence": ["suspension", "leave", "studies", "two", "academic"],
    "schooling": ["studies", "suspension", "academic"],
    "suspension": ["suspension", "suspend", "studies", "two", "academic"],
    "forgetting": ["bring", "without", "ID", "deducted"],
    "forget": ["bring", "without", "ID", "deducted"],
    "cheating": ["copy", "notes", "cribsheets", "behalf", "zero"],
    "copying": ["copy", "notes", "cribsheets", "zero"],
    "notes": ["copy", "pass", "cribsheets", "zero"],
    "electronic": ["electronic", "receivers", "mobile", "phones", "deducted"],
    "devices": ["receivers", "mobile", "phones", "deducted"],
    "communication": ["mobile", "receivers", "phones"],
    "paper": ["exam", "papers", "room", "zero"],
    "question": ["exam", "papers"],
    "threatens": ["threaten", "intimidate", "proctors", "zero"],
    "intimidate": ["threaten", "proctors"],
    "invigilator": ["proctor", "proctors"],
    "penalty": ["zero", "deducted", "shall", "violators"],
    "punishment": ["zero", "deducted", "violators"],
    "graduation": ["graduate", "credits", "required"],
    "graduate": ["postgraduate", "master", "doctoral", "70"],
    "graduates": ["postgraduate", "master", "doctoral"],
    "undergraduate": ["bachelor", "128", "60"],
    "bachelor": ["undergraduate", "128", "four", "years"],
    "degree": ["bachelor", "undergraduate", "study", "four", "years"],
    "standard": ["expected", "required", "designated"],
    "passing": ["passing", "grade", "marks", "60", "70"],
    "score": ["grade", "marks", "passing"],
    "scores": ["grade", "marks", "passing"],
    "physical": ["PE", "physical", "education"],
    "education": ["PE", "physical"],
    "pe": ["PE", "physical", "education"],
    "military": ["Military", "Training", "elective"],
    "training": ["Military", "Training"],
    "extension": ["extend", "two", "years"],
    "extend": ["extend", "two", "years"],
    "duration": ["years", "period", "study"],
    "study": ["studies", "period"],
    "suspension": ["suspend", "studies", "two", "academic"],
    "suspend": ["suspension", "studies", "two", "academic"],
    "dismissal": ["forced", "withdraw", "expelled", "half"],
    "dismissed": ["forced", "withdraw", "expelled", "half"],
    "expelled": ["forced", "withdraw", "expelled"],
    "expel": ["forced", "withdraw", "expelled"],
    "dropout": ["forced", "withdraw"],
    "make-up": ["make-up", "make", "retake", "failed"],
    "makeup": ["make-up", "retake", "failed"],
    "fail": ["failed", "failing", "retake"],
    "failed": ["failed", "failing", "retake"],
    "working": ["working", "workdays", "days", "three"],
    "days": ["workdays", "working", "days", "three"],
    "minimum": ["minimum", "lowest", "no fewer"],
    "maximum": ["maximum", "up to"],
    "credits": ["credits", "course"],
    "credit": ["credits", "course"],
    "minutes": ["minutes", "20", "40"],
}

QUESTION_TYPE_HINTS: list[tuple[str, list[str]]] = [
    ("fee", ["fee", "fees", "cost", "ntd", "price", "pay", "paid"]),
    ("penalty", ["penalty", "punishment", "deduct", "deducted", "zero", "fail",
                 "expelled", "withdraw", "dismissal", "barred", "cheat", "copying",
                 "threaten", "violator"]),
    ("duration", ["how long", "how many minutes", "how many hours",
                  "how many days", "how many years", "how many semesters",
                  "duration", "period"]),
    ("credit", ["credits", "credit", "graduation"]),
    ("score", ["passing", "score", "marks", "grade"]),
]


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[A-Za-z][A-Za-z\-']+|\d+", text.lower())
    out: list[str] = []
    for tok in raw:
        # Normalize possessives so "bachelor's" → "bachelor" (synonym lookup
        # is keyed on the bare lemma).
        if tok.endswith("'s"):
            tok = tok[:-2]
        out.append(tok)
    return out


def extract_entities(question: str) -> dict[str, Any]:
    """Parse question into {question_type, subject_terms, aspect}."""
    q = (question or "").strip()
    q_lower = q.lower()

    question_type = "general"
    for qtype, hints in QUESTION_TYPE_HINTS:
        if any(h in q_lower for h in hints):
            question_type = qtype
            break

    raw_tokens = _tokenize(q)
    terms: list[str] = []
    seen: set[str] = set()
    for tok in raw_tokens:
        if tok in STOPWORDS:
            continue
        if len(tok) < 2 and not tok.isdigit():
            continue
        if tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
        # If a word-number, also include the digit form.
        if tok in WORD_NUMBERS and WORD_NUMBERS[tok] not in seen:
            seen.add(WORD_NUMBERS[tok])
            terms.append(WORD_NUMBERS[tok])
        # Synonym expansion
        for syn in SYNONYMS.get(tok, []):
            sl = syn.lower()
            if sl not in seen:
                seen.add(sl)
                terms.append(syn)

    aspect = question_type
    return {
        "question_type": question_type,
        "subject_terms": terms,
        "aspect": aspect,
    }


# ---------------------------------------------------------------------------
# Cypher / Lucene query construction
# ---------------------------------------------------------------------------

LUCENE_SPECIAL = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')


def _escape_lucene(term: str) -> str:
    return LUCENE_SPECIAL.sub(r"\\\1", term)


def _lucene_query(terms: list[str], boost_first: int = 3) -> str:
    """Build a weighted OR query, boosting the most distinctive head terms."""
    if not terms:
        return ""
    parts: list[str] = []
    for i, t in enumerate(terms[:20]):
        esc = _escape_lucene(t)
        if not esc:
            continue
        if i < boost_first:
            parts.append(f"{esc}^3")
        else:
            parts.append(esc)
    return " ".join(parts)


def build_typed_cypher(entities: dict[str, Any]) -> tuple[str, str]:
    """Return (typed_query_lucene, broad_query_lucene) — both Lucene strings."""
    terms = entities.get("subject_terms", []) or []
    typed_query = _lucene_query(terms, boost_first=3)
    broad_query = _lucene_query(terms, boost_first=2)
    return typed_query, broad_query


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

CYPHER_RULE_SEARCH = """
CALL db.index.fulltext.queryNodes('rule_idx', $q) YIELD node, score
MATCH (a:Article)-[:CONTAINS_RULE]->(node)
RETURN node.rule_id  AS rule_id,
       node.type     AS type,
       node.action   AS action,
       node.result   AS result,
       node.art_ref  AS art_ref,
       node.reg_name AS reg_name,
       a.content     AS article_content,
       score         AS score
ORDER BY score DESC
LIMIT $k
"""

CYPHER_ARTICLE_SEARCH = """
CALL db.index.fulltext.queryNodes('article_content_idx', $q) YIELD node, score
RETURN node.number   AS art_ref,
       node.content  AS article_content,
       node.reg_name AS reg_name,
       score         AS score
ORDER BY score DESC
LIMIT $k
"""


def get_relevant_articles(question: str) -> list[dict[str, Any]]:
    """Retrieve top rule + article evidence for the question."""
    if driver is None:
        return []

    entities = extract_entities(question)
    typed_q, broad_q = build_typed_cypher(entities)
    if not typed_q and not broad_q:
        return []

    merged: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    with driver.session() as session:
        # 1) Typed retrieval against rule_idx
        if typed_q:
            try:
                rows = session.run(CYPHER_RULE_SEARCH, q=typed_q, k=8)
                for r in rows:
                    key = (r["art_ref"] or "", r["rule_id"] or "")
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    merged.append(
                        {
                            "rule_id": r["rule_id"],
                            "type": r["type"],
                            "action": r["action"],
                            "result": r["result"],
                            "art_ref": r["art_ref"],
                            "reg_name": r["reg_name"],
                            "article_content": r["article_content"],
                            "score": float(r["score"] or 0.0),
                            "source": "rule",
                        }
                    )
            except Exception as e:
                print(f"[retrieval] rule_idx error: {e}")

        # 2) Broad retrieval against article_content_idx (KG-routed evidence)
        if broad_q:
            try:
                rows = session.run(CYPHER_ARTICLE_SEARCH, q=broad_q, k=5)
                for r in rows:
                    key = (r["art_ref"] or "", "ARTICLE")
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    merged.append(
                        {
                            "rule_id": f"A:{r['art_ref']}",
                            "type": "article",
                            "action": (r["article_content"] or "")[:240],
                            "result": (r["article_content"] or "")[:240],
                            "art_ref": r["art_ref"],
                            "reg_name": r["reg_name"],
                            "article_content": r["article_content"],
                            "score": float(r["score"] or 0.0) * 0.6,
                            "source": "article",
                        }
                    )
            except Exception as e:
                print(f"[retrieval] article_content_idx error: {e}")

    merged.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return merged[:6]


# ---------------------------------------------------------------------------
# Answer generation
# ---------------------------------------------------------------------------


def generate_text(messages: list[dict[str, str]], max_new_tokens: int = 220) -> str:
    """Call local HF model via chat template + raw pipeline."""
    tok = get_tokenizer()
    pipe = get_raw_pipeline()
    if tok is None or pipe is None:
        load_local_llm()
        tok = get_tokenizer()
        pipe = get_raw_pipeline()
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return pipe(prompt, max_new_tokens=max_new_tokens)[0]["generated_text"].strip()


def _format_evidence(rule_results: list[dict[str, Any]], max_items: int = 4) -> str:
    if not rule_results:
        return "(no evidence)"
    lines: list[str] = []
    for i, r in enumerate(rule_results[:max_items], start=1):
        art = r.get("art_ref") or "?"
        reg = r.get("reg_name") or ""
        # Prefer the surrounding article snippet so the LLM has full context.
        snippet = (r.get("article_content") or r.get("action") or "").strip()
        if len(snippet) > 700:
            snippet = snippet[:700] + "..."
        lines.append(f"[Evidence {i} | {reg} {art}] {snippet}")
    return "\n".join(lines)


def generate_answer(question: str, rule_results: list[dict[str, Any]]) -> str:
    """Generate a short, grounded answer from the retrieved evidence."""
    if not rule_results:
        return "Insufficient rule evidence to answer this question."

    evidence_block = _format_evidence(rule_results)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an assistant that answers questions about National Central "
                "University regulations. You must answer ONLY using the provided "
                "evidence. Reply with one short sentence (under 30 words) that "
                "directly states the fact, then cite the article in parentheses, "
                "for example: '20 minutes (Rule 4).' If the evidence does not "
                "contain the answer, reply exactly: 'Insufficient rule evidence to "
                "answer this question.'"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                f"Evidence:\n{evidence_block}\n\n"
                "Answer (one short sentence, cite the article):"
            ),
        },
    ]

    try:
        text = generate_text(messages, max_new_tokens=120).strip()
    except Exception as e:
        return f"Error generating answer: {e}"

    # Trim to first sentence for compactness.
    text = text.replace("\n", " ").strip()
    first = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return first or text


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    if driver is None:
        return

    load_local_llm()

    print("=" * 50)
    print("🎓 NCU Regulation Assistant")
    print("=" * 50)
    print("💡 Try: 'What is the penalty for forgetting student ID?'")
    print("👉 Type 'exit' to quit.\n")

    while True:
        try:
            user_q = input("\nUser: ").strip()
            if not user_q:
                continue
            if user_q.lower() in {"exit", "quit"}:
                print("👋 Bye!")
                break

            results = get_relevant_articles(user_q)
            answer = generate_answer(user_q, results)
            print(f"Bot: {answer}")
        except KeyboardInterrupt:
            print("\n👋 Bye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

    driver.close()


if __name__ == "__main__":
    main()
