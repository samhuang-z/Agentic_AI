"""
Experiment script for comparing:
1. Different embedding models
2. Different chunk sizes
"""

import os
import re
import json
import shutil
import time
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
from config import get_llm, DATA_FOLDER, FILES

load_dotenv(override=True)

# ============================================================
# Embedding Models to Compare
# ============================================================
EMBEDDING_MODELS = {
    "MiniLM-L12-v2 (Multilingual)": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "all-MiniLM-L6-v2 (English)": "sentence-transformers/all-MiniLM-L6-v2",
    "all-mpnet-base-v2 (English)": "sentence-transformers/all-mpnet-base-v2",
}

# ============================================================
# Chunk Sizes to Compare
# ============================================================
CHUNK_SIZES = [500, 1000, 2000, 4000]

# ============================================================
# Test Queries (subset for quick experiment)
# ============================================================
TEST_QUERIES = [
    {
        "name": "Apple Revenue",
        "question": "What was Apple's Total Net Sales for the fiscal year 2024?",
        "target": "apple",
        "expected_keywords": ["391,035", "391"]
    },
    {
        "name": "Tesla R&D",
        "question": "What were Tesla's research and development expenses in 2024?",
        "target": "tesla",
        "expected_keywords": ["4,540", "4.54", "4,770", "4.77"]
    },
    {
        "name": "Apple R&D",
        "question": "What were Apple's research and development expenses in 2024?",
        "target": "apple",
        "expected_keywords": ["31,370", "31.37"]
    },
    {
        "name": "Tesla CapEx",
        "question": "What were Tesla's capital expenditures in 2024?",
        "target": "tesla",
        "expected_keywords": ["11,339", "11,153", "11.3", "11.1"]
    },
    {
        "name": "Tesla Energy Revenue",
        "question": "What was Tesla's Energy generation and storage revenue in 2024?",
        "target": "tesla",
        "expected_keywords": ["10,086", "10.1"]
    },
]


def clean_text(text: str) -> str:
    text = text.replace("\n", " ")
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def build_db(embedding_model_name, chunk_size, db_dir):
    """Build vector DB with specific embedding model and chunk size."""
    embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)

    for key, filename in FILES.items():
        persist_dir = os.path.join(db_dir, key)
        file_path = os.path.join(DATA_FOLDER, filename)

        if not os.path.exists(file_path):
            continue

        loader = PyMuPDFLoader(file_path)
        docs = loader.load()
        for doc in docs:
            doc.page_content = clean_text(doc.page_content)

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )
        splits = splitter.split_documents(docs)

        Chroma.from_documents(splits, embeddings, persist_directory=persist_dir)

    return embeddings


def retrieve_and_evaluate(embeddings, db_dir, queries):
    """Retrieve documents and check if expected keywords are found."""
    results = []

    for q in queries:
        key = q["target"]
        persist_dir = os.path.join(db_dir, key)
        vectorstore = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

        docs = retriever.invoke(q["question"])
        combined = " ".join([d.page_content for d in docs])

        # Check if any expected keyword found in retrieved docs
        found_keywords = [kw for kw in q["expected_keywords"] if kw in combined]
        hit = len(found_keywords) > 0

        results.append({
            "name": q["name"],
            "hit": hit,
            "found": found_keywords,
            "doc_lengths": [len(d.page_content) for d in docs],
        })

    return results


def run_embedding_experiment():
    """Experiment 1: Compare different embedding models (fixed chunk_size=2000)."""
    print("=" * 60)
    print("EXPERIMENT 1: Embedding Model Comparison (chunk_size=2000)")
    print("=" * 60)

    chunk_size = 2000
    all_results = {}

    for model_label, model_name in EMBEDDING_MODELS.items():
        print(f"\n--- Testing: {model_label} ---")
        db_dir = f"exp_chroma_{model_name.split('/')[-1]}"

        if os.path.exists(db_dir):
            shutil.rmtree(db_dir)

        start = time.time()
        embeddings = build_db(model_name, chunk_size, db_dir)
        build_time = time.time() - start

        start = time.time()
        results = retrieve_and_evaluate(embeddings, db_dir, TEST_QUERIES)
        query_time = time.time() - start

        hits = sum(1 for r in results if r["hit"])
        all_results[model_label] = {
            "model_name": model_name,
            "hits": hits,
            "total": len(TEST_QUERIES),
            "build_time": round(build_time, 2),
            "query_time": round(query_time, 2),
            "details": results,
        }

        print(f"  Retrieval Hits: {hits}/{len(TEST_QUERIES)}")
        print(f"  Build Time: {build_time:.2f}s | Query Time: {query_time:.2f}s")
        for r in results:
            status = "✅" if r["hit"] else "❌"
            print(f"  {status} {r['name']}: found={r['found']}")

        # Cleanup
        shutil.rmtree(db_dir)

    return all_results


def run_chunk_size_experiment():
    """Experiment 2: Compare different chunk sizes (fixed embedding model)."""
    print("\n" + "=" * 60)
    print("EXPERIMENT 2: Chunk Size Comparison")
    print(f"Embedding: paraphrase-multilingual-MiniLM-L12-v2")
    print("=" * 60)

    model_name = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    all_results = {}

    for chunk_size in CHUNK_SIZES:
        print(f"\n--- Testing: chunk_size={chunk_size} ---")
        db_dir = f"exp_chroma_chunk_{chunk_size}"

        if os.path.exists(db_dir):
            shutil.rmtree(db_dir)

        start = time.time()
        embeddings = build_db(model_name, chunk_size, db_dir)
        build_time = time.time() - start

        # Count chunks
        chunk_counts = {}
        for key in FILES.keys():
            persist_dir = os.path.join(db_dir, key)
            vs = Chroma(persist_directory=persist_dir, embedding_function=embeddings)
            chunk_counts[key] = vs._collection.count()

        start = time.time()
        results = retrieve_and_evaluate(embeddings, db_dir, TEST_QUERIES)
        query_time = time.time() - start

        hits = sum(1 for r in results if r["hit"])
        avg_doc_len = sum(
            sum(r["doc_lengths"]) / len(r["doc_lengths"]) for r in results
        ) / len(results)

        all_results[chunk_size] = {
            "hits": hits,
            "total": len(TEST_QUERIES),
            "build_time": round(build_time, 2),
            "query_time": round(query_time, 2),
            "chunk_counts": chunk_counts,
            "avg_retrieved_doc_len": round(avg_doc_len),
            "details": results,
        }

        print(f"  Chunks: Apple={chunk_counts.get('apple', 0)}, Tesla={chunk_counts.get('tesla', 0)}")
        print(f"  Retrieval Hits: {hits}/{len(TEST_QUERIES)}")
        print(f"  Avg Retrieved Doc Length: {avg_doc_len:.0f} chars")
        print(f"  Build Time: {build_time:.2f}s | Query Time: {query_time:.2f}s")
        for r in results:
            status = "✅" if r["hit"] else "❌"
            print(f"  {status} {r['name']}: found={r['found']}, doc_lens={r['doc_lengths']}")

        # Cleanup
        shutil.rmtree(db_dir)

    return all_results


if __name__ == "__main__":
    emb_results = run_embedding_experiment()
    chunk_results = run_chunk_size_experiment()

    # Save results for report
    with open("experiment_results.json", "w") as f:
        json.dump({
            "embedding_experiment": {k: {kk: vv for kk, vv in v.items() if kk != "details"} for k, v in emb_results.items()},
            "chunk_size_experiment": {str(k): {kk: vv for kk, vv in v.items() if kk != "details"} for k, v in chunk_results.items()},
        }, f, indent=2)

    print("\n\nResults saved to experiment_results.json")
