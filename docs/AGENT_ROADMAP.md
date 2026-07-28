# Ultimate Prediction Market Agent

## Mission

Build a decision-support system that finds mispriced prediction markets, explains the evidence, sizes risk conservatively, and learns from resolved forecasts.

The system should optimize calibration and long-run expected value—not the number of bets, win rate, or excitement.

## Non-negotiable guardrails

- Paper trading is the default.
- No order execution without an explicit live-trading flag and separate credentials.
- Review the exact resolution rules before recommending any position.
- Cap exposure per market, category, correlated event cluster, and day.
- Never increase position size to recover losses.
- Store every forecast made, including passes, with timestamps and source evidence.
- Evaluate Brier score, log loss, calibration, closing-line value, drawdown, and realized return.

## Architecture

1. **Collectors**
   - Kalshi market metadata, order books, trades, and settlement rules
   - Public primary sources: government releases, weather data, sports feeds, filings, and official schedules
   - Public trader activity where available and legally accessible

2. **Normalization**
   - Convert all prices to probabilities
   - Detect mutually exclusive and conditional markets
   - Normalize timestamps, fees, spreads, and settlement dates

3. **Feature engine**
   - Market liquidity and microstructure
   - Base rates and comparable historical events
   - Time-to-resolution
   - Price momentum and disagreement
   - Source freshness and reliability
   - Trader-skill signals, adjusted for category, sample size, entry price, and survivorship bias

4. **Forecast ensemble**
   - Statistical base-rate model
   - Domain-specific models
   - Evidence/research agent
   - Market-price prior
   - Calibrated ensemble with out-of-sample weights

5. **Risk engine**
   - Minimum edge after fees and slippage
   - Fractional Kelly sizing
   - Hard position and correlated-exposure limits
   - Kill switch for stale data, model disagreement, unusual volatility, and ambiguous rules

6. **Decision journal**
   - Probability estimate and confidence
   - Supporting and opposing evidence
   - Market price at recommendation and at close
   - Position sizing rationale
   - Resolution and postmortem

7. **Interface**
   - Ranked opportunity dashboard
   - Market research page
   - Paper portfolio and bankroll view
   - Calibration and performance reports
   - Alerts for material price changes or new evidence

## Delivery phases

### Phase 1 — Research and paper-trading core

- Typed market, signal, and decision models
- Probability aggregation
- Conservative sizing and pass rules
- Unit tests
- CSV/JSON decision journal

### Phase 2 — Kalshi scanner

- Read-only API client
- Market and order-book polling
- Rules ingestion
- Liquidity and spread filters
- Scheduled opportunity reports

### Phase 3 — Skilled-trader research

- Build trader histories only from observable activity
- Score by category-specific calibration, profit after fees, drawdown, consistency, and entry-price quality
- Shrink small samples toward the population mean
- Detect likely market makers, bots, hedges, and copied trades
- Use trader activity as one signal, never as a standalone reason to trade

### Phase 4 — Forecasting agents

- Primary-source research agent
- Domain models for weather, economics, politics, sports, and company events
- Evidence contradiction checks
- Probability calibration layer

### Phase 5 — Dashboard and alerts

- Web dashboard
- Market watchlists
- Paper portfolio
- Explanation cards
- Daily and event-driven alerts

### Phase 6 — Optional controlled execution

Live execution is considered only after a meaningful paper-trading sample demonstrates calibration, positive closing-line value, acceptable drawdown, and stable performance. Any execution layer must require explicit confirmation, strict limits, audit logs, and an emergency stop.

## First success criteria

The first version is successful when it can:

1. Import a market snapshot.
2. Combine multiple probability signals.
3. Reject weak or poorly defined opportunities.
4. Recommend a capped paper position when edge survives risk checks.
5. Save enough detail to audit the decision after settlement.
