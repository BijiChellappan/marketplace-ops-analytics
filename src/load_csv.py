"""
Build data/marketplace.db from the CSV files in data/csv/.

To analyse your own data: replace the CSV files in data/csv/ (same file names and
columns, see README "Data dictionary"), then run:  python run_all.py
Extra columns are kept; missing required columns stop the run with a clear message.
"""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "csv"
DB = ROOT / "data" / "marketplace.db"

REQUIRED = {
    "hubs": ["hub_id", "city"],
    "marketplaces": ["marketplace_id", "marketplace_name", "commission_rate"],
    "catalog_master": ["sku", "product_name", "category", "price_eur", "is_active"],
    "marketplace_listings": ["marketplace_id", "sku", "listed_price_eur", "is_live"],
    "hub_stock": ["hub_id", "sku", "stock_qty"],
    "marketplace_hub_availability": ["marketplace_id", "hub_id", "sku", "shown_available"],
    "orders": ["order_id", "order_date", "hub_id", "marketplace_id", "gmv_eur", "discount_eur",
               "delivery_minutes", "is_cancelled"],
    "hub_uptime": ["date", "hub_id", "marketplace_id", "minutes_open", "minutes_offline", "offline_reason"],
    "experiments": ["experiment_id", "name", "marketplace_id", "start_date", "end_date", "test_hubs"],
    "cost_assumptions": ["gross_margin_rate", "fulfilment_cost_eur"],
}


def main():
    problems, tables = [], {}
    for name, cols in REQUIRED.items():
        path = CSV / f"{name}.csv"
        if not path.exists():
            problems.append(f"missing file: data/csv/{name}.csv")
            continue
        df = pd.read_csv(path)
        missing = [c for c in cols if c not in df.columns]
        if missing:
            problems.append(f"data/csv/{name}.csv is missing columns: {', '.join(missing)}")
        tables[name] = df
    if problems:
        sys.exit("Cannot build the database:\n  - " + "\n  - ".join(problems))

    for col in ["order_date"]:
        tables["orders"][col] = pd.to_datetime(tables["orders"][col]).dt.strftime("%Y-%m-%d")
    tables["hub_uptime"]["date"] = pd.to_datetime(tables["hub_uptime"]["date"]).dt.strftime("%Y-%m-%d")

    DB.unlink(missing_ok=True)
    with sqlite3.connect(DB) as con:
        for name, df in tables.items():
            df.to_sql(name, con, index=False)
        con.execute("CREATE INDEX idx_orders ON orders(marketplace_id, hub_id, order_date)")
        con.execute("CREATE INDEX idx_uptime ON hub_uptime(hub_id, marketplace_id, date)")
    print(f"Built data/marketplace.db from {len(tables)} CSV files "
          f"({len(tables['orders']):,} orders, {tables['orders'].order_date.min()} to {tables['orders'].order_date.max()})")


if __name__ == "__main__":
    main()
