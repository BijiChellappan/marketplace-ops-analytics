"""Run every query in sql/ against data/marketplace.db and save results to reports/sql/."""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "marketplace.db"
OUT = ROOT / "reports" / "sql"


def run(path: Path, con) -> pd.DataFrame:
    return pd.read_sql_query(path.read_text(), con)


def main(show_rows: int = 12):
    OUT.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as con:
        for path in sorted((ROOT / "sql").glob("*.sql")):
            df = run(path, con)
            df.to_csv(OUT / f"{path.stem}.csv", index=False)
            print(f"\n== {path.name} ({len(df):,} rows) -> reports/sql/{path.stem}.csv")
            with pd.option_context("display.width", 160, "display.max_columns", 20):
                print(df.head(show_rows).to_string(index=False))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
