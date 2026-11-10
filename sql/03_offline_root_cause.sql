-- 03 | Root causes of lost availability
-- Which reasons cost the most offline time, and roughly how many orders did that cost?
-- Lost orders = offline share of the day x the hub's normal daily orders on that marketplace.

WITH normal_orders AS (
    SELECT hub_id, marketplace_id, order_date, COUNT(*) AS orders
    FROM orders
    GROUP BY hub_id, marketplace_id, order_date
),
baseline AS (
    -- median-like baseline: average of days with < 30 min offline
    SELECT n.hub_id, n.marketplace_id, AVG(n.orders) AS normal_daily_orders
    FROM normal_orders n
    JOIN hub_uptime u
      ON u.hub_id = n.hub_id AND u.marketplace_id = n.marketplace_id AND u.date = n.order_date
    WHERE u.minutes_offline < 30
    GROUP BY n.hub_id, n.marketplace_id
),
incidents AS (
    SELECT u.*,
           1.0 * u.minutes_offline / u.minutes_open * b.normal_daily_orders AS lost_orders
    FROM hub_uptime u
    JOIN baseline b USING (hub_id, marketplace_id)
    WHERE u.offline_reason IS NOT NULL
),
worst AS (
    -- the hub/marketplace pair that lost the most orders for each reason
    SELECT offline_reason, hub_id || ' on ' || marketplace_id AS worst_hub,
           ROW_NUMBER() OVER (PARTITION BY offline_reason ORDER BY SUM(lost_orders) DESC) AS rn,
           ROUND(SUM(lost_orders), 0) AS worst_hub_lost_orders
    FROM incidents
    GROUP BY offline_reason, hub_id, marketplace_id
)
SELECT
    i.offline_reason,
    COUNT(*)                                        AS incident_days,
    SUM(i.minutes_offline)                          AS minutes_offline,
    ROUND(SUM(i.lost_orders), 0)                    AS est_lost_orders,
    COUNT(DISTINCT i.hub_id || i.marketplace_id)    AS hub_marketplace_pairs,
    w.worst_hub,
    w.worst_hub_lost_orders
FROM incidents i
JOIN worst w ON w.offline_reason = i.offline_reason AND w.rn = 1
GROUP BY i.offline_reason
ORDER BY est_lost_orders DESC;
