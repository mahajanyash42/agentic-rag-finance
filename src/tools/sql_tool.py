import os
import sys
import sqlite3
import json

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
import config

from dotenv import load_dotenv
load_dotenv(override=True)


def run_sql_query(query: str) -> list[dict]:
    """
    Execute a SQL query against the financials SQLite database.
    Returns list of row dicts.
    """
    conn = sqlite3.connect(config.SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        rows = [dict(row) for row in cursor.fetchall()]

        # Dedup safety net: if we got multiple rows for same
        # company+metric+fiscal_year, keep the one with latest filed date
        seen = {}
        deduped = []
        for row in rows:
            key = (
                row.get("company", ""),
                row.get("metric", ""),
                row.get("fiscal_year", ""),
            )
            if key == ("", "", ""):
                # Query doesn't return those columns, skip dedup
                deduped = rows
                break
            filed = row.get("filed", "")
            if key not in seen or filed > seen[key]["filed"]:
                seen[key] = row
        if seen:
            deduped = list(seen.values())

        return deduped
    except sqlite3.Error as e:
        return [{"error": str(e)}]
    finally:
        conn.close()


def get_schema() -> str:
    """Return a description of the financials table for the LLM to use."""
    return """
Table: financials
Columns:
  - company     TEXT    : 'tesla', 'ford', 'rivian'
  - cik         TEXT    : SEC CIK number
  - metric      TEXT    : XBRL metric name (e.g. 'Revenues', 'NetIncomeLoss', 'ResearchAndDevelopmentExpense')
  - fiscal_year INTEGER : e.g. 2022, 2023, 2024
  - period_end  TEXT    : date string e.g. '2024-12-31'
  - value       REAL    : monetary value in USD (not thousands — raw dollars)
  - unit        TEXT    : 'USD'
  - filed       TEXT    : date the filing was submitted

Available metrics: Revenues, RevenueFromContractWithCustomerExcludingAssessedTax,
NetIncomeLoss, ResearchAndDevelopmentExpense, GrossProfit,
OperatingIncomeLoss, EarningsPerShareBasic

Example queries:
  SELECT fiscal_year, value FROM financials WHERE company='tesla' AND metric='Revenues' ORDER BY fiscal_year;
  SELECT company, fiscal_year, value FROM financials WHERE metric='Revenues' AND fiscal_year IN (2023,2024) ORDER BY company, fiscal_year;
"""


def nl_to_sql(natural_language_query: str) -> str:
    """
    Use GPT to convert a natural language financial question to SQL.
    Returns the SQL string.
    """
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    prompt = f"""You are a SQL expert. Convert the user's financial question into a valid SQLite query.

{get_schema()}

Rules:
- Only use SELECT statements, never INSERT/UPDATE/DELETE
- Always use lowercase for company names: 'tesla', 'ford', 'rivian'
- For revenue, try both 'Revenues' and 'RevenueFromContractWithCustomerExcludingAssessedTax'
- IMPORTANT: To avoid duplicates, always select only the latest filed row per company+metric+fiscal_year
  using this pattern:
  SELECT company, metric, fiscal_year, value, filed
  FROM financials
  WHERE (company, metric, fiscal_year, filed) IN (
      SELECT company, metric, fiscal_year, MAX(filed)
      FROM financials
      WHERE <your filters here>
      GROUP BY company, metric, fiscal_year
  )
- Return ONLY the SQL query, no explanation, no markdown, no backticks

User question: {natural_language_query}
SQL:"""

    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    sql = response.choices[0].message.content.strip()
    # Clean up any accidental markdown
    sql = sql.replace("```sql", "").replace("```", "").strip()
    return sql


def sql_tool(natural_language_query: str) -> dict:
    """
    Full pipeline: NL question → SQL → execute → return results.
    Returns { sql, results, error }
    """
    sql = nl_to_sql(natural_language_query)
    results = run_sql_query(sql)

    return {
        "sql":     sql,
        "results": results,
        "error":   results[0].get("error") if results and "error" in results[0] else None
    }


if __name__ == "__main__":
    # Test 1: simple revenue lookup
    print("=== Test 1: Tesla revenue by year ===")
    result = sql_tool("What was Tesla's revenue in 2023 and 2024?")
    print("SQL:", result["sql"])
    print("Results:", json.dumps(result["results"], indent=2))

    # Test 2: cross-company comparison
    print("\n=== Test 2: R&D spend comparison ===")
    result = sql_tool("Compare R&D spending between Tesla, Ford and Rivian in 2024")
    print("SQL:", result["sql"])
    print("Results:", json.dumps(result["results"], indent=2))

    # Test 3: YoY growth (raw numbers, growth calc happens in validator)
    print("\n=== Test 3: Net income 2022-2024 ===")
    result = sql_tool("Show Tesla net income from 2022 to 2024")
    print("SQL:", result["sql"])
    print("Results:", json.dumps(result["results"], indent=2))  