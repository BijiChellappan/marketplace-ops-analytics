# Experiment readout - EUR 3 off baskets over EUR 35 (Marketplace B)

**Setup:** 6 test hubs vs 6 control hubs on Marketplace B. Pre-period 6 weeks, experiment 15.09.2026-31.10.2026.
**Method:** difference-in-differences on hub-day averages; 95 % CI from a cluster bootstrap over hubs (2,000 resamples).
*Synthetic data.*

| Metric | Effect | Effect % | 95 % CI | Significant |
|---|---|---|---|---|
| Orders per hub-day | +6.91 | +13.6 % | +11.0 % to +16.2 % | yes |
| GMV per hub-day (EUR) | +282.51 | +20.3 % | +16.4 % to +24.3 % | yes |
| Average order value (EUR) | +1.63 | +6.0 % | +4.0 % to +8.1 % | yes |
| Contribution per hub-day (EUR) | +2.57 | +1.3 % | -2.5 % to +5.8 % | no |

## What happened
- Orders per hub-day: **+13.6 %** (significant); average order value: **+6.0 %**.
- Every discount is paid out of margin, and Marketplace B also takes commission on any extra GMV.
- **Net effect on contribution: +1.3 % per hub-day** (95 % CI -2.5 % to +5.8 %, not significant; about EUR 725 over the 282 test hub-days).

## Decision: DO NOT ROLL OUT as designed - negotiate co-funding first
- Contribution did not change measurably: the discount is buying volume at roughly zero extra profit, while the marketplace earns commission on all the extra GMV.
- Growth only counts if it pays: the decision is made on contribution, not on orders.

## Next steps
1. Take the result to Marketplace B: with **50 % co-funding** the same promotion would lift contribution by about **+13 %** per hub-day.
2. If no co-funding: re-test with a higher threshold (EUR 40) or a EUR 2 discount - fewer subsidised orders, similar basket push.
3. Track the repeat rate of customers who used the promotion for 8 weeks - long-term value could change the call.
