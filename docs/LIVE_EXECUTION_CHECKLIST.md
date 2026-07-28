# Live Execution Readiness Checklist

The scanner may run on live market data today. Real-money order submission must remain disabled until every item below is complete and reviewed.

## Credentials and secrets

- Create a dedicated Kalshi API key with the narrowest available permissions.
- Store the private key only in the deployment platform's encrypted secret store.
- Never commit credentials, private keys, account identifiers, or signed requests.
- Rotate credentials after any suspected exposure.

## Required controls

- `LIVE_TRADING_ENABLED` defaults to false.
- Every order requires explicit operator confirmation.
- Deterministic client order IDs prevent duplicate submission.
- Per-order, per-market, per-category, and daily-loss limits are enforced before submission.
- A kill switch blocks new orders and triggers cancel-all handling.
- Stale market data, ambiguous rules, reconciliation failures, and API errors fail closed.
- Orders use limit prices; unrestricted market orders are prohibited.

## Reconciliation

Before and after every submission cycle:

1. Fetch exchange balances, positions, and open orders.
2. Compare remote orders with the local append-only journal.
3. Stop trading on any missing, unknown, duplicated, or mismatched order.
4. Persist acknowledgements, fills, cancellations, fees, and final positions.
5. Require manual review before clearing a reconciliation incident.

## Rollout sequence

1. Run live-data collection for at least seven uninterrupted days.
2. Run shadow execution using real order books but no submissions.
3. Verify deterministic replay produces identical order plans.
4. Complete at least 100 resolved paper forecasts across multiple categories.
5. Confirm calibration, positive closing-line value, and acceptable drawdown.
6. Enable a sandbox or smallest-possible live limit.
7. Start with one order at a time and a maximum daily loss of $10.
8. Increase limits only after a written review of at least 50 reconciled live orders.

## Immediate shutdown conditions

- Unknown remote order or position
- Duplicate client order ID
- Stale price or missing settlement rules
- Daily loss limit reached
- Authentication or signature anomaly
- Clock drift affecting signed requests
- Repeated API timeout or rate-limit failure
- Local journal unavailable or unwritable
- Any difference between expected and exchange-reported exposure
