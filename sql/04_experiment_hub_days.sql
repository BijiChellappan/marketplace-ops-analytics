-- 04 | Experiment base table: one row per hub and day on the test marketplace
-- Used by src/experiment_readout.py for the difference-in-differences readout.
-- Uses the most recent experiment in the experiments table.

WITH exp AS (SELECT * FROM experiments ORDER BY start_date DESC LIMIT 1),
costs AS (SELECT gross_margin_rate, fulfilment_cost_eur FROM cost_assumptions)
SELECT
    o.order_date,
    o.hub_id,
    CASE WHEN instr(',' || exp.test_hubs || ',', ',' || o.hub_id || ',') > 0
         THEN 'test' ELSE 'control' END                         AS grp,
    CASE WHEN o.order_date >= exp.start_date THEN 'during' ELSE 'pre' END AS period,
    COUNT(*)                                                     AS orders,
    SUM(CASE WHEN o.is_cancelled = 0 THEN o.gmv_eur ELSE 0 END)  AS gmv_eur,
    SUM(o.discount_eur)                                          AS discount_eur,
    SUM(CASE WHEN o.is_cancelled = 1 THEN 0
             ELSE o.gmv_eur * (costs.gross_margin_rate - m.commission_rate)
                  - costs.fulfilment_cost_eur - o.discount_eur END) AS contribution_eur
FROM orders o
JOIN marketplaces m USING (marketplace_id)
CROSS JOIN exp
CROSS JOIN costs
WHERE o.marketplace_id = exp.marketplace_id
  AND o.order_date >= DATE(exp.start_date, '-42 days')
  AND o.order_date <= exp.end_date
GROUP BY o.order_date, o.hub_id
ORDER BY o.order_date, o.hub_id;
