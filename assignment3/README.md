# Assignment 3: Autonomous Multi-Doc Financial Analyst

A multi-document financial analyst system that uses RAG (Retrieval-Augmented Generation) to answer questions about Apple and Tesla 10-K filings. Implemented with both **LangChain ReAct Agent** (Legacy) and **LangGraph** state machine.

## Prerequisites

- Python 3.11
- Anthropic API Key (or Google Gemini / OpenAI)

## Setup

```bash
# Create virtual environment
uv venv --python 3.11 .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Configure API key
cp .env_example .env
# Edit .env and add your API key
```

## Execution

```bash
# Step 1: Build vector databases from PDFs
python build_rag.py

# Step 2: Run evaluation (change TEST_MODE in evaluator.py)
python evaluator.py
```

## Project Structure

| File | Description |
|------|-------------|
| `langgraph_agent.py` | **Main implementation** — LangGraph nodes (router, grader, generator, rewriter) + Legacy ReAct agent |
| `build_rag.py` | PDF ingestion → text cleaning → chunking → embedding → ChromaDB storage |
| `config.py` | LLM provider factory (Google/OpenAI/Anthropic) + embedding model config |
| `evaluator.py` | 14 benchmark test cases with LLM-as-Judge grading |
| `experiment.py` | Embedding model & chunk size comparison experiments |
| `generate_report.py` | Report PDF generation script |
| `data/` | Source PDF financial reports (Apple FY24 Q4, Tesla 10-K 2024) |

## Configuration

Edit `.env` to switch LLM providers:

```
LLM_PROVIDER=anthropic    # google, openai, or anthropic
ANTHROPIC_API_KEY=sk-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
```

## Key Design Decisions

- **Embedding**: `paraphrase-multilingual-MiniLM-L12-v2` — best balance of multilingual support and speed
- **Chunk Size**: 2000 characters — preserves complete financial tables
- **Retrieval k=5**: More context for the LLM to find exact figures
- **LangGraph over LangChain**: 9/14 vs 5/14 accuracy on benchmark

## Results

| Mode | Score | Strengths |
|------|-------|-----------|
| LangGraph | **9/14** | Self-correction, intelligent routing, relevance grading |
| LangChain ReAct | 5/14 | Simpler setup, sequential tool calling |
