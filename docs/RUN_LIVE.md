# Run the Prediction Agent Live

This deployment runs against live public Kalshi data and remains paper-trading only. It scans continuously, ranks liquid markets, writes append-only snapshots, and exposes health/status JSON.

## Local one-shot scan

```bash
uv sync
python -m src.agent.cli --limit 100 --top 20
```

## Local continuous service

```bash
cp .env.example .env
uv sync
uv run python -m src.agent.service
```

Open `http://localhost:8080/health` to confirm the service is operating.

## Docker

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f prediction-agent
```

The snapshot journal is stored at `output/live/market_snapshots.jsonl` and survives container replacement through the mounted volume.

## Render deployment

1. Connect this GitHub repository to Render.
2. Create a Blueprint from `render.yaml`.
3. Deploy the branch after this PR is merged.
4. Confirm `/health` returns `status: ok` after the first scan.
5. Attach a larger persistent disk before retaining extensive history.

## Operating checklist

- Health endpoint responds successfully.
- `last_success_at` keeps advancing.
- Snapshot file size increases after each interval.
- Market counts are plausible and nonzero.
- No API credentials are stored in Git.
- Alerts are configured for repeated health-check failures.

## Live-money boundary

This service does not submit, cancel, or modify orders. Before adding execution, the project must have authenticated API handling, secret management, idempotency, order-state reconciliation, daily and correlated-risk limits, a kill switch, and an audited paper-trading record. Execution must be developed as a separate module with dry-run as the default.
