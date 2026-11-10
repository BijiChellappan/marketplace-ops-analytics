"""Build dashboard/index.html from the report outputs (self-contained, Chart.js from CDN)."""
import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "reports"

kpi = pd.read_csv(R / "sql" / "01_marketplace_kpis.csv")
health = pd.read_csv(R / "sql" / "02_hub_health.csv")
causes = pd.read_csv(R / "sql" / "03_offline_root_cause.csv")
issues = pd.read_csv(R / "issues_latest.csv")
summary_txt = (R / "issues_summary_latest.txt").read_text()
exp = pd.read_csv(R / "experiment_results.csv")
weekly = pd.read_csv(R / "experiment_weekly.csv")
exp_sum = json.loads((R / "experiment_summary.json").read_text())
with sqlite3.connect(ROOT / "data" / "marketplace.db") as con:
    mp_df = pd.read_sql_query("SELECT * FROM marketplaces ORDER BY marketplace_id", con)
    hubs_df = pd.read_sql_query("SELECT * FROM hubs", con)
    span = pd.read_sql_query("SELECT MIN(order_date) AS a, MAX(order_date) AS b FROM orders", con).iloc[0]

# ---- KPI tiles: last month vs previous month, all marketplaces
months = sorted(kpi.month.unique())
cur, prev = months[-1], months[-2]


def tot(m):
    d = kpi[kpi.month == m]
    return {"gmv": d.gmv_eur.sum(), "orders": d.orders.sum(),
            "cpo": d.contribution_eur.sum() / (d.orders * (1 - d.cancel_rate_pct / 100)).sum(),
            "cancel": (d.orders * d.cancel_rate_pct).sum() / d.orders.sum()}


c, p = tot(cur), tot(prev)


PREV_NAME = pd.Timestamp(prev + "-01").strftime("%b")


def delta(a, b, pct=True, good_up=True, unit=""):
    v = (a - b) / b * 100 if pct else a - b
    txt = f"{v:+.1f} %" if pct else f"{v:+.2f}{unit}"
    if round(v, 2) == 0:
        return f'<span class="delta flat">● no change vs {PREV_NAME}</span>'
    good = (v > 0) == good_up
    return f'<span class="delta {"up" if good else "down"}">{"▲" if v > 0 else "▼"} {txt} vs {PREV_NAME}</span>'


month_name = pd.Timestamp(cur + "-01").strftime("%B %Y")
tiles = [
    ("GMV", f"€{c['gmv']/1e6:.2f}M", delta(c["gmv"], p["gmv"])),
    ("Orders", f"{c['orders']:,}", delta(c["orders"], p["orders"])),
    ("Contribution per order", f"€{c['cpo']:.2f}", delta(c["cpo"], p["cpo"], pct=False, unit=" €")),
    ("Cancellation rate", f"{c['cancel']:.2f} %", delta(c["cancel"], p["cancel"], pct=False, good_up=False, unit=" pp")),
]
tiles_html = "".join(f'<div class="tile"><div class="label">{l}</div><div class="value">{v}</div>{d}</div>'
                     for l, v, d in tiles)

# ---- chart data
mps = mp_df.marketplace_id.tolist()
mp_names = dict(zip(mp_df.marketplace_id, mp_df.marketplace_name))
orders_series = {mp_names[m]: kpi[kpi.marketplace_id == m].sort_values("month").orders.tolist() for m in mps}
cpo_cur = {mp_names[m]: float(kpi[(kpi.month == cur) & (kpi.marketplace_id == m)].contribution_per_order_eur.iloc[0])
           for m in mps}
wk = weekly.pivot(index="week", columns="grp", values="orders").reset_index()
data = {
    "months": [pd.Timestamp(m + "-01").strftime("%b") for m in months],
    "orders": orders_series,
    "cpo": cpo_cur,
    "causes": {"labels": causes.offline_reason.tolist(), "values": causes.est_lost_orders.tolist()},
    "exp": {"weeks": [pd.Timestamp(w).strftime("%d %b") for w in wk.week],
            "test": wk.test.round(1).tolist(), "control": wk.control.round(1).tolist(),
            "start_idx": int((pd.to_datetime(wk.week) + pd.Timedelta(days=6) >= pd.Timestamp(exp_sum["start"])).argmax())},
}

# ---- tables
issue_grp = (issues.groupby(["severity", "issue_type", "owner"]).size().reset_index(name="count")
             .sort_values("severity", key=lambda s: s.map({"high": 0, "medium": 1, "low": 2})))
sev_icon = {"high": "▲", "medium": "◆", "low": "○"}
issue_rows = "".join(
    f'<tr><td><span class="sev {r.severity}">{sev_icon[r.severity]} {r.severity}</span></td>'
    f'<td>{r.issue_type.replace("_", " ").lower()}</td><td class="num">{r.count}</td><td>{r.owner}</td></tr>'
    for r in issue_grp.itertuples())
pattern = next((l for l in summary_txt.splitlines() if l.startswith("Pattern")), "")
exp_rows = "".join(
    f'<tr><td>{r.metric}</td><td class="num">{r.effect_pct:+.1f} %</td>'
    f'<td class="num">{r.ci95_low_pct:+.1f} to {r.ci95_high_pct:+.1f} %</td>'
    f'<td>{"✔ significant" if r.significant == "yes" else "– not significant"}</td></tr>'
    for r in exp.itertuples())
watch = health[health.status != "ok"]
watch_rows = "".join(
    f'<tr><td>{r.hub_id}</td><td>{mp_names[r.marketplace_id]}</td><td class="num">{r.orders_change_pct:+.1f} %</td>'
    f'<td class="num">{r.uptime_pct:.1f} %</td><td>{r.status}</td></tr>' for r in watch.itertuples()) \
    or '<tr><td colspan="5">All hubs within normal range.</td></tr>'
orders_table = "".join(
    f"<tr><td>{data['months'][i]}</td>" + "".join(f'<td class="num">{orders_series[n][i]:,}</td>' for n in orders_series) + "</tr>"
    for i in range(len(months)))

orders_c = exp[exp.metric.str.startswith("Orders")].iloc[0]
contrib_c = exp[exp.metric.str.startswith("Contribution")].iloc[0]
top_cause = causes.iloc[0]
# weakest marketplace by contribution per order this month
cpo_s = pd.Series(cpo_cur)
weak, best = cpo_s.idxmin(), cpo_s.idxmax()
weak_comm = float(mp_df.set_index("marketplace_name").loc[weak, "commission_rate"])
ratio = cpo_s[weak] / cpo_s[best]
cities = ", ".join(sorted(hubs_df.city.unique()))
fmt_month = lambda d: pd.Timestamp(d).strftime("%b %Y")
period = f"{fmt_month(span.a)} – {fmt_month(span.b)}"
subtitle = (f"{len(hubs_df)} hubs ({cities}) · {len(mp_df)} delivery marketplaces · {period}")
exp_title = f"Experiment: {exp_sum['name'].replace('EUR ', '€')} on {exp_sum['marketplace']}"
exp_sub = (f"Average orders per hub-day, {exp_sum['n_test']} test vs {exp_sum['n_control']} control hubs. "
           f"Experiment from {pd.Timestamp(exp_sum['start']).strftime('%d %b')} (dashed line).")
exp_head = (f"{orders_c.effect_pct:+.0f} % orders, {contrib_c.effect_pct:+.1f} % contribution")
exp_text = (f"{exp_sum['name'].replace('EUR ', '€')} on {exp_sum['marketplace']}: "
            f"contribution change is {'significant' if contrib_c.significant == 'yes' else 'not significant'}. "
            f"{exp_sum['verdict']}.")
cause_text = (f"from {top_cause.offline_reason}, the biggest offline cause. Worst case: {top_cause.worst_hub}.")
if pattern:
    cause_text += " Check it against today's catalog-check pattern."
weak_text = (f"{weak} earns €{cpo_s[weak]:.2f} per order ({ratio:.0%} of {best}) after its "
             f"{weak_comm:.0%} commission. Price or assortment there should reflect that.")

cfg = json.loads((ROOT / "config.json").read_text())
html = (ROOT / "src" / "dashboard_template.html").read_text()
html = (html.replace("{{TILES}}", tiles_html).replace("{{MONTH}}", month_name)
        .replace("{{ISSUE_ROWS}}", issue_rows).replace("{{ISSUE_TOTAL}}", str(len(issues)))
        .replace("{{PATTERN}}", pattern.replace("Pattern: ", ""))
        .replace("{{EXP_ROWS}}", exp_rows).replace("{{VERDICT}}", exp_sum["verdict"])
        .replace("{{COFUND}}", f"{exp_sum['cofund_50_contribution_pct']:+.0f} %")
        .replace("{{WATCH_ROWS}}", watch_rows).replace("{{ORDERS_TABLE}}", orders_table)
        .replace("{{SUBTITLE}}", subtitle).replace("{{AUTHOR}}", cfg["author"]).replace("{{BUSINESS}}", cfg["business"])
        .replace("{{DATA_NOTE}}", cfg["data_note"]).replace("{{FOOTER}}", cfg["footer"]).replace("{{PERIOD}}", period)
        .replace("{{EXP_TITLE}}", exp_title).replace("{{EXP_SUB}}", exp_sub)
        .replace("{{EXP_HEAD}}", exp_head).replace("{{EXP_TEXT}}", exp_text)
        .replace("{{CAUSE_HEAD}}", f"~{top_cause.est_lost_orders:,.0f} lost orders").replace("{{CAUSE_TEXT}}", cause_text)
        .replace("{{WEAK_HEAD}}", f"{weak}: lowest margin").replace("{{WEAK_TEXT}}", weak_text)
        .replace("{{MP_HEADERS}}", "".join(f'<th class="num">{n}</th>' for n in orders_series))
        .replace("{{DATA}}", json.dumps(data)))
(ROOT / "dashboard").mkdir(exist_ok=True)
(ROOT / "dashboard" / "index.html").write_text(html)
print("Wrote dashboard/index.html")
