import requests
import sqlite3
import json
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
import config


def fetch_xbrl_data(company_name: str, cik: str) -> dict:
    """Fetch raw XBRL company facts from SEC API."""
    url = f"{config.XBRL_API_BASE}/CIK{cik}.json"
    print(f"  Fetching {company_name} ({cik}) from SEC...")
    response = requests.get(url, headers=config.SEC_HEADERS)
    if response.status_code != 200:
        raise Exception(f"SEC API error {response.status_code} for {company_name}")
    return response.json()


def extract_annual_metrics(company_name: str, cik: str, facts: dict) -> list[dict]:
    """
    Pull annual (10-K) values for each metric we care about.
    Returns a list of row dicts ready for SQLite insertion.
    """
    rows = []
    us_gaap = facts.get("facts", {}).get("us-gaap", {})

    for metric in config.XBRL_METRICS:
        if metric not in us_gaap:
            continue

        units = us_gaap[metric].get("units", {})

        # Most financial metrics are in USD
        entries = units.get("USD", [])

        for entry in entries:
            # Only want annual 10-K filings, not quarterly
            if entry.get("form") != "10-K":
                continue
            # Skip amended filings to avoid duplicates
            if entry.get("form") == "10-K/A":
                continue

            rows.append({
                "company":     company_name,
                "cik":         cik,
                "metric":      metric,
                "fiscal_year": entry.get("fy"),
                "period_end":  entry.get("end"),
                "value":       entry.get("val"),
                "unit":        "USD",
                "filed":       entry.get("filed"),
            })

    return rows


def create_database(db_path: str):
    """Create SQLite DB and financials table if they don't exist."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financials (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company     TEXT NOT NULL,
            cik         TEXT NOT NULL,
            metric      TEXT NOT NULL,
            fiscal_year INTEGER,
            period_end  TEXT,
            value       REAL,
            unit        TEXT,
            filed       TEXT,
            UNIQUE(company, metric, fiscal_year, period_end)
        )
    """)
    conn.commit()
    return conn


def insert_rows(conn: sqlite3.Connection, rows: list[dict]):
    """Insert rows, skipping duplicates."""
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    for row in rows:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO financials
                    (company, cik, metric, fiscal_year, period_end, value, unit, filed)
                VALUES
                    (:company, :cik, :metric, :fiscal_year, :period_end, :value, :unit, :filed)
            """, row)
            if cursor.rowcount > 0:
                inserted += 1
            else:
                skipped += 1
        except sqlite3.Error as e:
            print(f"    DB error on row {row}: {e}")
    conn.commit()
    return inserted, skipped


def run():
    print("=== XBRL Ingestion ===\n")
    conn = create_database(config.SQLITE_DB_PATH)

    for company_name, cik in config.COMPANIES.items():
        print(f"[{company_name.upper()}]")
        try:
            facts = fetch_xbrl_data(company_name, cik)
            rows  = extract_annual_metrics(company_name, cik, facts)
            ins, skip = insert_rows(conn, rows)
            print(f"  Extracted {len(rows)} entries → inserted {ins}, skipped {skip} duplicates\n")
        except Exception as e:
            print(f"  ERROR: {e}\n")

    # Quick sanity check — print row counts per company
    cursor = conn.cursor()
    print("=== Database summary ===")
    cursor.execute("""
        SELECT company, COUNT(*) as rows, MIN(fiscal_year) as earliest, MAX(fiscal_year) as latest
        FROM financials
        GROUP BY company
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]:10s} | {row[1]} rows | FY {row[2]}–{row[3]}")

    conn.close()
    print("\nDone. Database saved to:", config.SQLITE_DB_PATH)


if __name__ == "__main__":
    run()