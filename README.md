# Agentic RAG for Financial Document Intelligence

A multi-tool agentic RAG system built with LangGraph that analyzes SEC 
10-K filings using intelligent query routing — directing each question 
to the right tool rather than applying vector search uniformly.

---

## The Core Problem

Standard RAG applies vector search to every query. This fails silently 
on financial documents — retrieving text that *sounds* relevant but 
contains wrong figures. A system that can't distinguish "what are 
Tesla's risk factors?" from "what was Tesla's revenue in 2024?" will 
hallucinate financial data with high confidence.

This project solves that with a **LangGraph-powered query router** that 
classifies each question and dispatches it to the appropriate tool — 
vector search, Microsoft SQL Server, or live SEC EDGAR search.

---

## Architecture

```
User Query
     │
     ▼
 ┌─────────────────────────────────────────┐
 │            LangGraph Agent              │
 │                                         │
 │         ┌──────────────┐                │
 │         │ Router Node  │ (GPT-4o-mini)  │
 │         └──────┬───────┘                │
 │                │                        │
 │   narrative ───►  Vector Search Node    │
 │   numeric   ───►  SQL Tool Node         │
 │   current   ───►  Web Search Node       │
 │   cross_doc ───►  Vector Search Node    │
 │                    + SQL Tool Node      │
 │                │                        │
 │         ┌──────▼───────┐                │
 │         │ Synthesis    │ (GPT-4o-mini)  │
 │         │    Node      │                │
 │         └──────┬───────┘                │
 │                │                        │
 │         ┌──────▼───────┐                │
 │         │  Validator   │                │
 │         │    Node      │                │
 │         └──────┬───────┘                │
 └────────────────┼────────────────────────┘
                  │
                  ▼
            Final Answer
```

## Frameworks & Tools Used

| Layer | Technology | Purpose |
|---|---|---|
| Agent Orchestration | **LangGraph** | Stateful multi-node pipeline with conditional routing |
| LLM | **OpenAI GPT-4o-mini** | Query classification, NL→SQL generation, synthesis |
| Embeddings | **OpenAI text-embedding-3-small** | Converting text chunks to vectors |
| Vector Store | **ChromaDB** | Semantic search over 10-K narrative sections |
| Structured Database | **Microsoft SQL Server** | Financial data storage and querying via pyodbc |
| Data Ingestion | **SEC XBRL API** | Structured financial facts (revenue, net income, R&D) |
| Filing Retrieval | **SEC EDGAR Full-Text API** | 10-K HTML downloads and recency search |
| HTML Parsing | **BeautifulSoup + lxml** | Extracting narrative sections from 10-K filings |
| Environment | **python-dotenv** | Secure API key management |
| Evaluation | **Manual grading + automated routing check** | Systematic performance measurement |

---

## Agent Pipeline (LangGraph Nodes)

The agent is built as a **LangGraph StateGraph** with 6 nodes and 
conditional edges that route each query to the appropriate tool.

### Node 1 — Router
Uses GPT-4o-mini with structured JSON output to classify every 
incoming query into one of four categories:
- `narrative` → qualitative questions about risk factors, strategy, MD&A
- `numeric` → questions requiring exact financial figures
- `current` → questions about recent filings or events
- `cross_doc` → questions requiring both narrative and numeric data

### Node 2 — Vector Search (ChromaDB)
Converts the query to an embedding vector using OpenAI's 
`text-embedding-3-small` model and retrieves the top-5 most 
semantically similar chunks from ChromaDB. Supports metadata 
filtering by company and section.

### Node 3 — SQL Tool (Microsoft SQL Server)
Uses GPT-4o-mini to translate the natural language question into 
T-SQL, executes it against Microsoft SQL Server via `pyodbc`, and 
returns deduplicated financial rows using correlated subqueries on 
`MAX(period_end)` and `MAX(filed)`.

### Node 4 — Web Search (SEC EDGAR)
Queries SEC EDGAR's submissions API and full-text search API to 
retrieve the most recent 10-K filing metadata for any company in scope.

### Node 5 — Synthesis
Assembles context from whichever tools ran and uses GPT-4o-mini to 
generate a grounded answer citing specific companies, sections, and 
fiscal years.

### Node 6 — Validator
For numeric and cross-document answers: extracts financial figures 
from the generated answer using regex, retrieves ground truth values 
directly from SQL Server, and flags any inconsistency before the 
answer reaches the user.

---

## Tools in Detail

| Tool | Data Source | Query Type | Returns |
|---|---|---|---|
| Vector Search | ChromaDB (154 chunks) | Semantic similarity | Top-5 text passages with scores |
| SQL Tool | Microsoft SQL Server | NL → T-SQL → exact rows | Financial figures with fiscal year |
| Web Search | SEC EDGAR live API | Keyword + company lookup | Filing dates, accession numbers |
| Validator | SQL Server ground truth | Regex extraction + math | Pass/fail with difference % |

---

## Companies in Scope

| Company | Ticker | CIK | Role |
|---|---|---|---|
| Tesla | TSLA | 0001318605 | Primary subject |
| Ford | F | 0000037996 | Comparable |
| Rivian | RIVN | 0001874178 | Comparable |

Latest 10-K filings (FY2025, filed Jan–Feb 2026) + full XBRL 
historical data loaded into Microsoft SQL Server.

---

## Evaluation Results

**19 hand-written test questions across 3 categories.**

| Category | n | Routing Correct | Accuracy |
|---|---|---|---|
| Narrative | 7 | 7/7 | 100% |
| Numeric | 7 | 7/7 | 100% |
| Cross-document | 5 | 5/5 | 100% |
| **Overall** | **19** | **19/19** | **100%** |

**Validator stress test:** 5/5 injected errors caught  
(inflated figures, wrong magnitudes, hallucinated values)

---

## Setup

**Prerequisites:** Python 3.11+, OpenAI API key, Microsoft SQL Server
(local install with SSMS)

```bash
git clone https://github.com/YOUR-USERNAME/agentic-rag-finance.git
cd agentic-rag-finance
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux
pip install -r requirements.txt
```

**Configure `.env`:**
OPENAI_API_KEY=sk-proj-...

**Create SQL Server database:**  
Open SSMS → connect to your server → right-click Databases →  
New Database → name it `agentic_rag_finance`

Update `config.py`:
```python
SQL_SERVER = "YourServerName"  # as shown in SSMS connect dialog
```

**Build the data layer:**
```bash
# Pull SEC XBRL financial data → Microsoft SQL Server
python src/data/ingest_xbrl.py

# Pull 10-K narrative text → ChromaDB vector store
python src/data/ingest_filings.py
```

**Run a query:**
```bash
python -c "
from src.agent.graph import run_query
result = run_query('What are Tesla\'s main risk factors related to competition?')
print(result['final_answer'])
print('Validated:', result['validated'])
"
```

**Run the full evaluation:**
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

router.py         # LangGraph node — LLM query classifier

graph.py          # LangGraph StateGraph pipeline (6 nodes)

validator.py      # Numeric answer validation against SQL Server

tools/

vector_search.py  # ChromaDB semantic search tool

sql_tool.py       # NL→T-SQL + Microsoft SQL Server execution

web_search.py     # SEC EDGAR live filing search

data/

ingest_xbrl.py    # SEC XBRL API → Microsoft SQL Server

ingest_filings.py # 10-K HTML → ChromaDB vector store

eval/

questions.py      # 19 hand-written evaluation questions

run_eval.py       # Evaluation runner + routing accuracy report

data/

processed/

chroma/           # ChromaDB vector store (local)

eval_results.json # Full evaluation output

config.py             # Central configuration (models, DB, paths)

requirements.txt      # All dependencies

---

## Known Limitations

- **XBRL tag gaps:** Ford does not report `GrossProfit` and Tesla 
  does not file `EarningsPerShareBasic` as standalone XBRL tags — 
  those queries return no SQL rows. Solvable by adding derived 
  metric calculations from available tags.
- **Validator false negatives:** The LLM-based consistency checker 
  occasionally flags correct answers when SQL returns many rows 
  across multiple years. The regex-based validator in `validator.py` 
  is more reliable for single-metric checks.
- **Narrative scope:** Only Risk Factors and MD&A sections are 
  indexed. Adding Item 1 (Business) and Item 7A (Quantitative Risk) 
  would improve coverage.
- **3-company scope:** Intentional for this iteration. Adding 
  companies requires only updating `config.py` — the rest of the 
  pipeline generalizes automatically.
