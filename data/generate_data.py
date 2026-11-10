"""
Generate a SYNTHETIC quick-commerce marketplace dataset.

All numbers are simulated for portfolio purposes. They do not describe any
real company. The structure mirrors a grocery quick-commerce business that
sells through three external delivery marketplaces (Marketplace A, B, C)
from 12 dark-store hubs in Berlin, Hamburg and Munich.

Output: data/marketplace.db (SQLite) + CSV copies in data/csv/
Run:    python data/generate_data.py
"""
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
ROOT = Path(__file__).resolve().parent
START, END = "2026-05-01", "2026-10-31"

# ---------------------------------------------------------------- dimensions
HUBS = pd.DataFrame({
    "hub_id": ["BER-01", "BER-02", "BER-03", "BER-04", "BER-05",
               "HAM-01", "HAM-02", "HAM-03", "HAM-04",
               "MUC-01", "MUC-02", "MUC-03"],
    "city": ["Berlin"] * 5 + ["Hamburg"] * 4 + ["Munich"] * 3,
    "base_daily_orders": [140, 120, 150, 100, 130, 115, 125, 95, 105, 135, 120, 110],
})

MARKETPLACES = pd.DataFrame({
    "marketplace_id": ["MP-A", "MP-B", "MP-C"],
    "marketplace_name": ["Marketplace A", "Marketplace B", "Marketplace C"],
    "commission_rate": [0.18, 0.15, 0.22],
    "order_share": [0.45, 0.35, 0.20],
})

GROSS_MARGIN = 0.38          # product margin before marketplace commission
FULFILMENT_COST = 2.50       # picking + packing per order (EUR)

CATEGORIES = {
    "Fruit & Veg": (["Bananas", "Apples", "Tomatoes", "Avocados", "Cucumbers", "Carrots",
                     "Blueberries", "Lemons", "Spinach", "Potatoes"], (0.9, 4.5)),
    "Dairy": (["Whole Milk", "Oat Drink", "Greek Yogurt", "Butter", "Gouda", "Mozzarella",
               "Skyr", "Cream Cheese", "Eggs (10)", "Feta"], (1.1, 4.9)),
    "Bakery": (["Sourdough Bread", "Croissants", "Toast Bread", "Pretzels", "Rye Bread",
                "Bagels", "Wraps", "Ciabatta"], (1.2, 4.2)),
    "Drinks": (["Sparkling Water", "Cola", "Orange Juice", "Iced Tea", "Energy Drink",
                "Beer 6-Pack", "Cold Brew", "Kombucha", "Still Water", "Lemonade"], (0.8, 7.5)),
    "Snacks": (["Crisps", "Dark Chocolate", "Gummy Bears", "Salted Nuts", "Protein Bar",
                "Biscuits", "Popcorn", "Rice Cakes"], (1.3, 3.9)),
    "Frozen": (["Pizza Margherita", "Ice Cream", "Frozen Berries", "Fish Fingers",
                "Veggie Burgers", "Frozen Peas"], (2.2, 6.5)),
    "Household": (["Toilet Paper", "Dish Soap", "Laundry Pods", "Kitchen Roll",
                   "Bin Bags", "Sponges"], (1.5, 8.9)),
    "Meat & Fish": (["Chicken Breast", "Minced Beef", "Salmon Fillet", "Ham Slices",
                     "Tofu", "Salami"], (2.5, 7.9)),
}
SIZES = ["S", "M", "L", "XL"]


def build_catalog() -> pd.DataFrame:
    rows, n = [], 1
    for cat, (items, (lo, hi)) in CATEGORIES.items():
        for item in items:
            for size in SIZES[: rng.integers(2, 5)]:
                price = round(rng.uniform(lo, hi) * (1 + SIZES.index(size) * 0.35), 2)
                rows.append({"sku": f"SKU-{n:04d}", "product_name": f"{item} {size}",
                             "category": cat, "price_eur": price, "is_active": 1})
                n += 1
    cat = pd.DataFrame(rows)
    # 10 SKUs were delisted in the master catalog last month
    delisted = rng.choice(cat.index, 10, replace=False)
    cat.loc[delisted, "is_active"] = 0
    return cat


def build_listings(catalog: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mp in MARKETPLACES.marketplace_id:
        for _, p in catalog.iterrows():
            rows.append({"marketplace_id": mp, "sku": p.sku,
                         "listed_price_eur": p.price_eur, "is_live": int(p.is_active)})
    lst = pd.DataFrame(rows)
    active = catalog[catalog.is_active == 1].sku.values
    inactive = catalog[catalog.is_active == 0].sku.values
    # Injected catalog problems (what the automation should catch)
    miss = rng.choice(active, 7, replace=False)                      # MP-A: missing listings
    lst.loc[(lst.marketplace_id == "MP-A") & lst.sku.isin(miss), "is_live"] = 0
    stale = rng.choice(active, 9, replace=False)                     # MP-B: old prices
    m = (lst.marketplace_id == "MP-B") & lst.sku.isin(stale)
    lst.loc[m, "listed_price_eur"] = (lst.loc[m, "listed_price_eur"] * rng.uniform(0.82, 0.93, m.sum())).round(2)
    ghost = rng.choice(inactive, 6, replace=False)                   # MP-C: delisted but still live
    lst.loc[(lst.marketplace_id == "MP-C") & lst.sku.isin(ghost), "is_live"] = 1
    return lst


def build_stock_and_hub_listing(catalog: pd.DataFrame):
    stock_rows, show_rows = [], []
    for hub in HUBS.hub_id:
        qty = rng.poisson(28, len(catalog))
        qty[rng.random(len(catalog)) < 0.04] = 0                     # normal stock-outs
        for sku, q, active in zip(catalog.sku, qty, catalog.is_active):
            stock_rows.append({"hub_id": hub, "sku": sku, "stock_qty": int(q * active)})
    stock = pd.DataFrame(stock_rows)
    for mp in MARKETPLACES.marketplace_id:
        s = stock.copy()
        s["marketplace_id"] = mp
        s["shown_available"] = (s.stock_qty > 0).astype(int)
        show_rows.append(s)
    show = pd.concat(show_rows, ignore_index=True)
    # Sync problems: MUC-02 on MP-C shows sold-out items as available,
    # and some in-stock items are hidden (= lost sales)
    bad = (show.marketplace_id == "MP-C") & (show.hub_id == "MUC-02") & (show.stock_qty == 0)
    show.loc[bad, "shown_available"] = 1
    hidden_idx = show[(show.stock_qty > 15)].sample(25, random_state=SEED).index
    show.loc[hidden_idx, "shown_available"] = 0
    return stock, show[["marketplace_id", "hub_id", "sku", "shown_available"]]


# ---------------------------------------------------------------- facts
EXP = {"marketplace_id": "MP-B", "start": "2026-09-15", "end": "2026-10-31",
       "test_hubs": ["BER-01", "BER-03", "BER-05", "HAM-02", "HAM-04", "MUC-01"],
       "name": "EUR 3 off baskets over EUR 35", "discount": 3.0, "threshold": 35.0}

OFFLINE_REASONS = ["catalog sync error", "rider shortage", "tech outage", "hub stock-out"]


def build_facts():
    dates = pd.date_range(START, END, freq="D")
    dow_factor = {0: 0.92, 1: 0.90, 2: 0.95, 3: 1.00, 4: 1.12, 5: 1.18, 6: 1.10}
    orders, avail = [], []
    oid = 1
    for _, hub in HUBS.iterrows():
        for _, mp in MARKETPLACES.iterrows():
            for d in dates:
                ds = d.strftime("%Y-%m-%d")
                months = (d - pd.Timestamp(START)).days / 30.4
                lam = hub.base_daily_orders * mp.order_share * dow_factor[d.dayofweek] * (1 + 0.02 * months)

                # hub availability on the marketplace (open 07:00-22:00 = 900 min)
                offline, reason = int(rng.exponential(7)), None
                if rng.random() < 0.05:
                    offline += int(rng.uniform(60, 200))
                    reason = rng.choice(OFFLINE_REASONS, p=[0.3, 0.35, 0.2, 0.15])
                if hub.hub_id == "MUC-02" and mp.marketplace_id == "MP-C" and "2026-08-10" <= ds <= "2026-08-16":
                    offline, reason = int(rng.uniform(320, 480)), "catalog sync error"
                offline = min(offline, 900)
                if reason is None and offline > 30:
                    reason = "no reason logged"
                avail.append({"date": ds, "hub_id": hub.hub_id, "marketplace_id": mp.marketplace_id,
                              "minutes_open": 900, "minutes_offline": offline,
                              "offline_reason": reason})
                lam *= (1 - offline / 900)

                in_exp = (mp.marketplace_id == EXP["marketplace_id"] and hub.hub_id in EXP["test_hubs"]
                          and EXP["start"] <= ds <= EXP["end"])
                if in_exp:
                    lam *= 1.12
                n = rng.poisson(lam)
                if n == 0:
                    continue
                basket = rng.poisson(8, n) + 1
                gmv = np.round(rng.lognormal(np.log(26), 0.38, n) * (1.06 if in_exp else 1.0), 2)
                discount = np.where(in_exp & (gmv >= EXP["threshold"]), EXP["discount"], 0.0)
                delivery = np.clip(rng.normal(18 + (4 if offline > 200 else 0), 6, n), 6, 75).round(1)
                cancel_p = 0.022 + (0.03 if offline > 200 else 0)
                cancelled = (rng.random(n) < cancel_p).astype(int)
                for i in range(n):
                    orders.append((f"O{oid:07d}", ds, hub.hub_id, mp.marketplace_id, int(basket[i]),
                                   float(gmv[i]), float(discount[i]), float(delivery[i]), int(cancelled[i])))
                    oid += 1
    orders = pd.DataFrame(orders, columns=["order_id", "order_date", "hub_id", "marketplace_id",
                                           "items", "gmv_eur", "discount_eur", "delivery_minutes",
                                           "is_cancelled"])
    return orders, pd.DataFrame(avail)


def main():
    catalog = build_catalog()
    listings = build_listings(catalog)
    stock, hub_listing = build_stock_and_hub_listing(catalog)
    orders, avail = build_facts()
    experiments = pd.DataFrame([{
        "experiment_id": "EXP-2026-09-B1", "name": EXP["name"], "marketplace_id": EXP["marketplace_id"],
        "start_date": EXP["start"], "end_date": EXP["end"],
        "test_hubs": ",".join(EXP["test_hubs"]), "discount_eur": EXP["discount"],
        "basket_threshold_eur": EXP["threshold"]}])
    tables = {"hubs": HUBS, "marketplaces": MARKETPLACES, "catalog_master": catalog,
              "marketplace_listings": listings, "hub_stock": stock,
              "marketplace_hub_availability": hub_listing, "orders": orders,
              "hub_uptime": avail, "experiments": experiments,
              "cost_assumptions": pd.DataFrame([{"gross_margin_rate": GROSS_MARGIN,
                                                 "fulfilment_cost_eur": FULFILMENT_COST}])}
    db = ROOT / "marketplace.db"
    db.unlink(missing_ok=True)
    (ROOT / "csv").mkdir(exist_ok=True)
    with sqlite3.connect(db) as con:
        for name, df in tables.items():
            df.to_sql(name, con, index=False)
            df.to_csv(ROOT / "csv" / f"{name}.csv", index=False)
    print(f"Created {db.name}: " + ", ".join(f"{k}={len(v):,}" for k, v in tables.items()))


if __name__ == "__main__":
    main()
