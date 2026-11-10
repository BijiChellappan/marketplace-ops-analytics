-- 01 | Monthly performance by marketplace
-- Revenue, orders, AOV, cancellation rate, delivery time and contribution
-- after marketplace commission, fulfilment cost and discounts.

WITH costs AS (
    SELECT gross_margin_rate, fulfilment_cost_eur FROM cost_assumptions
),
order_contribution AS (
    SELECT
        o.order_id,
        substr(o.order_date, 1, 7)                    AS month,
        o.marketplace_id,
        o.gmv_eur,
        o.discount_eur,
        o.delivery_minutes,
        o.is_cancelled,
        CASE WHEN o.is_cancelled = 1 THEN 0
             ELSE o.gmv_eur * c.gross_margin_rate
                  - o.gmv_eur * m.commission_rate
                  - c.fulfilment_cost_eur
                  - o.discount_eur
        END                                           AS contribution_eur
    FROM orders o
    JOIN marketplaces m USING (marketplace_id)
    CROSS JOIN costs c
)
SELECT
    month,
    marketplace_id,
    COUNT(*)                                                    AS orders,
    ROUND(SUM(CASE WHEN is_cancelled = 0 THEN gmv_eur END), 0)  AS gmv_eur,
    ROUND(AVG(CASE WHEN is_cancelled = 0 THEN gmv_eur END), 2)  AS aov_eur,
    ROUND(100.0 * AVG(is_cancelled), 2)                         AS cancel_rate_pct,
    ROUND(AVG(delivery_minutes), 1)                             AS avg_delivery_min,
    ROUND(SUM(contribution_eur), 0)                             AS contribution_eur,
    ROUND(SUM(contribution_eur) / SUM(CASE WHEN is_cancelled = 0 THEN 1 END), 2)
                                                                AS contribution_per_order_eur
FROM order_contribution
GROUP BY month, marketplace_id
ORDER BY month, marketplace_id;
