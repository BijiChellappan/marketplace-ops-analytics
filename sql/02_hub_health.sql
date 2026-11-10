-- 02 | Hub health scorecard per marketplace (last 4 weeks vs previous 4 weeks)
-- Flags hubs where orders dropped and connects the drop to uptime.

WITH params AS (
    SELECT DATE(MAX(order_date), '-27 days') AS cur_start,
           DATE(MAX(order_date), '-55 days') AS prev_start
    FROM orders
),
daily AS (
    SELECT o.hub_id, o.marketplace_id, o.order_date,
           COUNT(*)          AS orders,
           AVG(o.is_cancelled) AS cancel_rate
    FROM orders o
    GROUP BY o.hub_id, o.marketplace_id, o.order_date
),
periods AS (
    SELECT d.hub_id, d.marketplace_id,
           SUM(CASE WHEN d.order_date >= p.cur_start THEN d.orders END)                       AS orders_cur,
           SUM(CASE WHEN d.order_date >= p.prev_start AND d.order_date < p.cur_start
                    THEN d.orders END)                                                       AS orders_prev
    FROM daily d CROSS JOIN params p
    WHERE d.order_date >= p.prev_start
    GROUP BY d.hub_id, d.marketplace_id
),
uptime AS (
    SELECT u.hub_id, u.marketplace_id,
           ROUND(100.0 * (1 - 1.0 * SUM(u.minutes_offline) / SUM(u.minutes_open)), 2) AS uptime_pct
    FROM hub_uptime u CROSS JOIN params p
    WHERE u.date >= p.cur_start
    GROUP BY u.hub_id, u.marketplace_id
)
SELECT
    p.hub_id,
    p.marketplace_id,
    p.orders_cur,
    p.orders_prev,
    ROUND(100.0 * (p.orders_cur - p.orders_prev) / p.orders_prev, 1) AS orders_change_pct,
    u.uptime_pct,
    CASE
        WHEN u.uptime_pct < 97 THEN 'check uptime'
        WHEN 100.0 * (p.orders_cur - p.orders_prev) / p.orders_prev < -5 THEN 'investigate demand'
        ELSE 'ok'
    END AS status
FROM periods p
JOIN uptime u USING (hub_id, marketplace_id)
ORDER BY CASE status WHEN 'check uptime' THEN 1 WHEN 'investigate demand' THEN 2 ELSE 3 END,
         orders_change_pct;
