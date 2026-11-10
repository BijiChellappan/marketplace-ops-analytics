"""
Experiment readout for the most recent experiment in the experiments table
(demo data: "EUR 3 off baskets over EUR 35" on Marketplace B).

Design   6 test hubs vs 6 control hubs, 6 weeks before vs 6.5 weeks during.
Method   Difference-in-differences on hub-day metrics: (test during - test pre) - (control during - control pre),
         which removes the general trend and seasonality that hit both groups.
         95 % confidence interval from a cluster bootstrap over hubs (hubs are the unit that was randomised).
Decision Judge on contribution, not just orders: a promotion that grows orders but loses money is not a win.

Run:     python src/experiment_readout.py
"""
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "marketplace.db"
OUT = ROOT / "reports"
rng = np.random.default_rng(7)
METRICS = {"orders": "Orders per hub-day", "gmv_eur": "GMV per hub-day (EUR)",
           "aov_eur": "Average order value (EUR)", "contribution_eur": "Contribution per hub-day (EUR)"}


def load() -> pd.DataFrame:
    with sqlite3.connect(DB) as con:
        df = pd.read_sql_query((ROOT / "sql" / "04_experiment_hub_days.sql").read_text(), con)
    df["aov_eur"] = df.gmv_eur / df.orders
    return df


def did(df: pd.DataFrame, metric: str) -> tuple[float, float]:
    m = df.groupby(["grp", "period"])[metric].mean()
    base = m["test", "pre"] * m["control", "during"] / m["control", "pre"]   # expected test without promo
    effect = m["test", "during"] - base
    return effect, effect / base


def bootstrap(df: pd.DataFrame, metric: str, n: int = 2000) -> tuple[float, float]:
    hubs = {g: df[df.grp == g].hub_id.unique() for g in ["test", "control"]}
    by_hub = {h: d for h, d in df.groupby("hub_id")}
    rel = []
    for _ in range(n):
        sample = [by_hub[h] for g in hubs for h in rng.choice(hubs[g], len(hubs[g]), replace=True)]
        rel.append(did(pd.concat(sample), metric)[1])
    return np.percentile(rel, 2.5), np.percentile(rel, 97.5)


def meta() -> dict:
    with sqlite3.connect(DB) as con:
        e = pd.read_sql_query("SELECT * FROM experiments ORDER BY start_date DESC LIMIT 1", con).iloc[0]
        mp = pd.read_sql_query("SELECT marketplace_name FROM marketplaces WHERE marketplace_id = ?", con,
                               params=(e.marketplace_id,)).marketplace_name.iloc[0]
    return {"name": e["name"], "mp": mp, "start": e.start_date, "end": e.end_date,
            "n_test": len(e.test_hubs.split(","))}


def main():
    df = load()
    m = meta()
    n_control = df[df.grp == "control"].hub_id.nunique()
    pre_weeks = df[df.period == "pre"].order_date.nunique() / 7
    fmt = lambda d: pd.Timestamp(d).strftime("%d.%m.%Y")
    rows = []
    for metric, label in METRICS.items():
        abs_eff, rel_eff = did(df, metric)
        lo, hi = bootstrap(df, metric)
        rows.append({"metric": label, "effect_abs": round(abs_eff, 2), "effect_pct": round(100 * rel_eff, 1),
                     "ci95_low_pct": round(100 * lo, 1), "ci95_high_pct": round(100 * hi, 1),
                     "significant": "yes" if lo > 0 or hi < 0 else "no"})
    res = pd.DataFrame(rows)

    # What-if: partner co-funds part of the discount
    during_test = df[(df.grp == "test") & (df.period == "during")]
    discount_per_day = during_test.discount_eur.mean()
    contrib_eff = res.loc[res.metric.str.startswith("Contribution"), "effect_abs"].iloc[0]
    breakeven_share = max(0.0, -contrib_eff / discount_per_day) if discount_per_day else 0
    test_hub_days = len(during_test)
    total_contrib_effect = contrib_eff * test_hub_days

    res.to_csv(OUT / "experiment_results.csv", index=False)
    weekly = (df.assign(week=pd.to_datetime(df.order_date).dt.to_period("W").dt.start_time.dt.strftime("%Y-%m-%d"))
                .groupby(["week", "grp"])[["orders", "contribution_eur"]].mean().round(2).reset_index())
    weekly.to_csv(OUT / "experiment_weekly.csv", index=False)

    contrib = res.iloc[3]
    base_contrib = contrib_eff / (contrib.effect_pct / 100) if contrib.effect_pct else np.nan
    cofund_pct = 100 * (contrib_eff + 0.5 * discount_per_day) / base_contrib
    if contrib.significant == "yes" and contrib.effect_pct > 0:
        verdict = "ROLL OUT"
        why = ("- Contribution rose significantly, so the extra volume more than pays for the discount.",
               f"1. Roll out to all hubs on {m['mp']} and keep 2 hubs as a hold-out to monitor the effect.")
    elif contrib.significant == "yes":
        verdict = "DO NOT ROLL OUT as designed"
        why = ("- Contribution fell significantly: the discount costs more than the extra volume earns.",
               f"1. Ask {m['mp']} to co-fund at least {100*breakeven_share:.0f} % of the discount, or stop the promotion.")
    else:
        verdict = "DO NOT ROLL OUT as designed - negotiate co-funding first"
        why = ("- Contribution did not change measurably: the discount is buying volume at roughly zero extra profit, "
               "while the marketplace earns commission on all the extra GMV.",
               f"1. Take the result to {m['mp']}: with **50 % co-funding** the same promotion would lift "
               f"contribution by about **{cofund_pct:+.0f} %** per hub-day.")
    md = f"""# Experiment readout - {m['name']} ({m['mp']})

**Setup:** {m['n_test']} test hubs vs {n_control} control hubs on {m['mp']}. Pre-period {pre_weeks:.0f} weeks, experiment {fmt(m['start'])}-{fmt(m['end'])}.
**Method:** difference-in-differences on hub-day averages; 95 % CI from a cluster bootstrap over hubs (2,000 resamples).
*{json.loads((ROOT / 'config.json').read_text())['data_note'].capitalize()}.*

| Metric | Effect | Effect % | 95 % CI | Significant |
|---|---|---|---|---|
""" + "\n".join(f"| {r.metric} | {r.effect_abs:+,.2f} | {r.effect_pct:+.1f} % | {r.ci95_low_pct:+.1f} % to {r.ci95_high_pct:+.1f} % | {r.significant} |"
                for r in res.itertuples()) + f"""

## What happened
- Orders per hub-day: **{res.iloc[0].effect_pct:+.1f} %** ({"significant" if res.iloc[0].significant == "yes" else "not significant"}); average order value: **{res.iloc[2].effect_pct:+.1f} %**.
- Every discount is paid out of margin, and {m['mp']} also takes commission on any extra GMV.
- **Net effect on contribution: {contrib.effect_pct:+.1f} % per hub-day** (95 % CI {contrib.ci95_low_pct:+.1f} % to {contrib.ci95_high_pct:+.1f} %, {"significant" if contrib.significant == "yes" else "not significant"}; about EUR {total_contrib_effect:,.0f} over the {test_hub_days} test hub-days).

## Decision: {verdict}
{why[0]}
- Growth only counts if it pays: the decision is made on contribution, not on orders.

## Next steps
{why[1]}
2. If no co-funding: re-test with a higher threshold (EUR 40) or a EUR 2 discount - fewer subsidised orders, similar basket push.
3. Track the repeat rate of customers who used the promotion for 8 weeks - long-term value could change the call.
"""
    summary = {"verdict": verdict, "cofund_50_contribution_pct": round(cofund_pct, 1), "name": m["name"],
               "marketplace": m["mp"], "start": m["start"], "end": m["end"], "n_test": m["n_test"],
               "n_control": int(n_control)}
    pd.Series(summary).to_json(OUT / "experiment_summary.json")
    (OUT / "experiment_readout.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
