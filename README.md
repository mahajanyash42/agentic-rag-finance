# Agentic RAG for Financial Document Intelligence

A multi-tool agentic RAG system that analyzes SEC 10-K filings using 
intelligent query routing — directing each question to the right tool 
rather than applying vector search uniformly.

**TA Project — [Your Professor's Name], [Your University]**  
**Author:** [Your Name]

---

## The Core Problem

Standard RAG applies vector search to every query. This fails silently 
on financial documents — retrieving text that *sounds* relevant but 
contains wrong figures. A system that can't distinguish "what are Tesla's 
risk factors?" from "what was Tesla's revenue in 2024?" will hallucinate 
financial data with high confidence.

This project solves that with a **query router** that classifies each 
question and dispatches it to the appropriate tool.

---

## Architecture
User Query

│

▼

┌─────────┐     narrative → Vector Search (ChromaDB)

│ Router  │ ──► numeric   → SQL Tool (SQLite + XBRL)

│  (LLM)  │     current   → Web Search (SEC EDGAR)

└─────────┘     cross_doc → Vector Search + SQL

│

▼

Synthesis (LLM)

│

▼

Numeric Validator ──► Final Answer

---

## Tools

| Tool | Purpose | Data Source |
|------|---------|-------------|
| Vector Search | Narrative questions (risk factors, MD&A) | ChromaDB, 154 chunks from 10-K filings |
| SQL Tool | Numeric questions (revenue, R&D, net income) | SQLite, SEC XBRL company facts API |
| Web Search | Recency questions (latest filings) | SEC EDGAR full-text search |
| Validator | Cross-checks numeric answers against SQL | SQLite ground truth |

---

## Companies in Scope

- **Tesla (TSLA)** — primary subject
- **Ford (F)** — comparable
- **Rivian (RIVN)** — comparable

Latest 10-K filings (FY2025, filed Jan–Feb 2026) + historical XBRL data.

---

## Evaluation Results

**19 hand-written test questions across 3 categories.**

| Category | n | Routing Correct | Accuracy |
|----------|---|----------------|----------|
| Narrative | 7 | 7/7 | 100% |
| Numeric | 7 | 7/7 | 100% |
| Cross-document | 5 | 5/5 | 100% |
| **Overall** | **19** | **19/19** | **100%** |

**Validator stress test:** 5/5 injected errors caught  
(inflated figures, wrong magnitudes, hallucinated values)

---

## Setup

**Requirements:** Python 3.11+, OpenAI API key

```bash
git clone https://github.com/YOUR-USERNAME/agentic-rag-finance.git
cd agentic-rag-finance
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

Add your OpenAI API key to `.env`:
OPENAI_API_KEY=sk-proj-...

**Build the data layer:**
```bash
python src/data/ingest_xbrl.py      # pulls SEC XBRL → SQLite
python src/data/ingest_filings.py   # pulls 10-K text → ChromaDB
```

**Run a query:**
```bash
python -c "
from src.agent.graph import run_query
result = run_query('What are Tesla\'s main risk factors related to competition?')
print(result['final_answer'])
"
```

**Run the full eval:**
```bash
python src/eval/run_eval.py
```

**Run validator stress test:**
```bash
python src/agent/validator.py
```

---

## Project Structure
src/

agent/

router.py      # LLM-based query classifier

graph.py       # LangGraph agent pipeline

validator.py   # Numeric answer validation

tools/

vector_search.py  # ChromaDB semantic search

sql_tool.py       # NL→SQL + SQLite execution

web_search.py     # SEC EDGAR live search

data/

ingest_xbrl.py    # SEC XBRL API → SQLite

ingest_filings.py # 10-K HTML → ChromaDB

eval/

questions.py      # 19 hand-written test questions

run_eval.py       # Evaluation runner

data/

processed/

financials.db     # SQLite financial database

chroma/           # ChromaDB vector store

eval_results.json # Full evaluation output

config.py             # Central configuration

---

## Known Limitations

- **XBRL tag gaps:** Ford does not report `GrossProfit` and Tesla does 
  not file `EarningsPerShareBasic` as standalone XBRL tags — those 
  queries return no SQL rows. Solvable by adding derived metric 
  calculations.
- **Validator false negatives:** The LLM-based consistency checker 
  occasionally flags correct answers when SQL returns many rows across 
  multiple years. The regex-based validator in `validator.py` is more 
  reliable for single-metric checks.
- **Narrative scope:** Only Risk Factors and MD&A sections are indexed. 
  Adding Item 1 (Business) and Item 7A (Quantitative Risk) would improve 
  coverage.
- **3-company scope:** Intentional for this iteration. 
  Adding companies requires only updating `config.py`.

---

## Tech Stack

- **Orchestration:** LangGraph
- **LLM:** GPT-4o-mini (OpenAI)
- **Vector store:** ChromaDB (local)
- **Structured data:** SQLite via SEC XBRL API
- **Narrative data:** SEC EDGAR full-text 10-K filings
- **Embeddings:** OpenAI text-embedding-3-small