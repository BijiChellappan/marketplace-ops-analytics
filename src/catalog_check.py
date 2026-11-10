"""
Daily catalog & availability check across all marketplaces.

Replaces a manual morning routine: comparing the master catalog and hub stock
with what each marketplace actually shows customers. Every finding gets a type,
a severity and an owner, so it can be fixed or routed to the right team.

Checks
  1. MISSING_LISTING      active SKU is not live on a marketplace          -> lost sales
  2. PRICE_MISMATCH       marketplace price differs from master by > 2 %   -> margin / trust risk
  3. DELISTED_STILL_LIVE  SKU delisted in master but still sold            -> cancellations
  4. PHANTOM_STOCK        shown as available, but hub stock is 0           -> cancellations
  5. HIDDEN_STOCK         hub has stock (> 15), but item is hidden         -> lost sales
  6. HUB_OFFLINE          hub offline on a marketplace > 60 min yesterday  -> lost orders

Output: reports/issues_<date>.csv and a short summary ready to paste into Slack.
Run:    python src/catalog_check.py            (schedule daily via cron / GitHub Actions)
"""
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "marketplace.db"
OUT = ROOT / "reports"
PRICE_TOLERANCE = 0.02
OFFLINE_ALERT_MIN = 60

SEVERITY = {"DELISTED_STILL_LIVE": "high", "PHANTOM_STOCK": "high", "HUB_OFFLINE": "high",
            "PRICE_MISMATCH": "medium", "MISSING_LISTING": "medium", "HIDDEN_STOCK": "low"}
OWNER = {"DELISTED_STILL_LIVE": "Catalog team", "PRICE_MISMATCH": "Commercial / pricing",
         "MISSING_LISTING": "Catalog team", "PHANTOM_STOCK": "Partner integration (stock feed)",
         "HIDDEN_STOCK": "Partner integration (stock feed)", "HUB_OFFLINE": "Hub ops + partner"}


def q(con, sql):
    return pd.read_sql_query(sql, con)


def run_checks(con) -> pd.DataFrame:
    checks = []

    missing = q(con, """
        SELECT l.marketplace_id, NULL AS hub_id, c.sku, c.product_name,
               'active in master, not live on marketplace' AS detail
        FROM catalog_master c JOIN marketplace_listings l USING (sku)
        WHERE c.is_active = 1 AND l.is_live = 0""")
    checks.append(missing.assign(issue_type="MISSING_LISTING"))

    price = q(con, f"""
        SELECT l.marketplace_id, NULL AS hub_id, c.sku, c.product_name,
               printf('master EUR %.2f vs listed EUR %.2f (%.1f%%)', c.price_eur, l.listed_price_eur,
                      100.0 * (l.listed_price_eur - c.price_eur) / c.price_eur) AS detail
        FROM catalog_master c JOIN marketplace_listings l USING (sku)
        WHERE c.is_active = 1 AND l.is_live = 1
          AND ABS(l.listed_price_eur - c.price_eur) / c.price_eur > {PRICE_TOLERANCE}""")
    checks.append(price.assign(issue_type="PRICE_MISMATCH"))

    ghost = q(con, """
        SELECT l.marketplace_id, NULL AS hub_id, c.sku, c.product_name,
               'delisted in master, still live' AS detail
        FROM catalog_master c JOIN marketplace_listings l USING (sku)
        WHERE c.is_active = 0 AND l.is_live = 1""")
    checks.append(ghost.assign(issue_type="DELISTED_STILL_LIVE"))

    phantom = q(con, """
        SELECT a.marketplace_id, a.hub_id, a.sku, c.product_name,
               'shown available, hub stock = 0' AS detail
        FROM marketplace_hub_availability a
        JOIN hub_stock s USING (hub_id, sku)
        JOIN catalog_master c USING (sku)
        WHERE a.shown_available = 1 AND s.stock_qty = 0 AND c.is_active = 1""")
    checks.append(phantom.assign(issue_type="PHANTOM_STOCK"))

    hidden = q(con, """
        SELECT a.marketplace_id, a.hub_id, a.sku, c.product_name,
               'hub stock ' || s.stock_qty || ' units, hidden on marketplace' AS detail
        FROM marketplace_hub_availability a
        JOIN hub_stock s USING (hub_id, sku)
        JOIN catalog_master c USING (sku)
        WHERE a.shown_available = 0 AND s.stock_qty > 15 AND c.is_active = 1""")
    checks.append(hidden.assign(issue_type="HIDDEN_STOCK"))

    offline = q(con, f"""
        SELECT marketplace_id, hub_id, NULL AS sku, NULL AS product_name,
               minutes_offline || ' min offline (' || COALESCE(offline_reason, 'n/a') || ')' AS detail
        FROM hub_uptime
        WHERE date = (SELECT MAX(date) FROM hub_uptime) AND minutes_offline > {OFFLINE_ALERT_MIN}""")
    checks.append(offline.assign(issue_type="HUB_OFFLINE"))

    issues = pd.concat(checks, ignore_index=True)
    issues["severity"] = issues.issue_type.map(SEVERITY)
    issues["owner"] = issues.issue_type.map(OWNER)
    order = {"high": 0, "medium": 1, "low": 2}
    issues = issues.sort_values(["severity", "issue_type", "marketplace_id", "hub_id"],
                                key=lambda s: s.map(order) if s.name == "severity" else s)
    return issues[["severity", "issue_type", "marketplace_id", "hub_id", "sku",
                   "product_name", "detail", "owner"]].reset_index(drop=True)


def summary(issues: pd.DataFrame, run_date: str) -> str:
    lines = [f"*Marketplace catalog & availability check - {run_date}*",
             f"{len(issues)} issues found "
             f"({(issues.severity == 'high').sum()} high, {(issues.severity == 'medium').sum()} medium, "
             f"{(issues.severity == 'low').sum()} low)", ""]
    grp = issues.groupby(["severity", "issue_type", "owner"]).size().reset_index(name="n")
    grp = grp.sort_values("severity", key=lambda s: s.map({"high": 0, "medium": 1, "low": 2}))
    for _, r in grp.iterrows():
        lines.append(f"- [{r.severity.upper()}] {r.issue_type}: {r.n} -> {r.owner}")
    # Pattern detection: is one hub/marketplace pair responsible for most phantom stock?
    ph = issues[issues.issue_type == "PHANTOM_STOCK"]
    if len(ph):
        top = ph.groupby(["hub_id", "marketplace_id"]).size().sort_values(ascending=False)
        (hub, mp), n = top.index[0], top.iloc[0]
        if n / len(ph) > 0.5:
            lines += ["", f"Pattern: {n} of {len(ph)} phantom-stock items are {hub} on {mp} "
                          f"- likely a stock-feed sync problem, not single items. Escalate to partner."]
    return "\n".join(lines)


def main():
    run_date = date.today().isoformat()
    OUT.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as con:
        issues = run_checks(con)
    path = OUT / "issues_latest.csv"
    issues.to_csv(path, index=False)
    text = summary(issues, run_date)
    (OUT / "issues_summary_latest.txt").write_text(text)
    print(text)
    print(f"\nFull list: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
