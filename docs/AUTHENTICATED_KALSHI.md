# Authenticated Kalshi operation

The continuous scanner can run without credentials. Authenticated account reads and order writes use the official RSA-PSS/SHA-256 signing scheme.

## Recommended deployment

Use Render (or another always-on container platform) for the worker. Vercel is not the right primary host for this service because the scanner is a persistent process with local health state and durable snapshot storage. Vercel can host a future dashboard, but not the core worker.

## Safe rollout

1. Create a Kalshi demo API key and private key.
2. Store `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PEM` as deployment secrets.
3. Keep `KALSHI_ENVIRONMENT=demo` and `KALSHI_LIVE_WRITE_ENABLED=false`.
4. Verify signed reads:

```bash
python -m src.agent.trading_cli balance
python -m src.agent.trading_cli positions
python -m src.agent.trading_cli orders --status resting
```

5. Run paper trading until calibration, closing-line value, and drawdown thresholds are met.
6. Review the live execution checklist and set a unique runtime confirmation token.
7. Enable writes only in demo first. Production requires a separate approval and deployment change.

## Secret handling

Never commit the API key or PEM. Prefer a mounted secret file locally and a secret environment variable in hosted deployments. Rotate credentials immediately if a secret appears in logs, an issue, a pull request, or shell history.
