# Prediction Market Analysis

A framework for analyzing prediction market data, including the largest publicly available dataset of Polymarket and Kalshi market and trade data. Provides tools for data collection, storage, and running analysis scripts that generate figures and statistics.

## Overview

This project enables research and analysis of prediction markets by providing:
- Pre-collected datasets from Polymarket and Kalshi
- Data collection indexers for gathering new data
- Analysis framework for generating figures and statistics

Currently supported features:
- Market metadata collection (Kalshi & Polymarket)
- Trade history collection via API and blockchain
- Parquet-based storage with automatic progress saving
- Extensible analysis script framework
- Live evidence-first command center (below)

## Live Command Center

A scheduled GitHub Actions workflow
([live-kalshi-scan.yml](.github/workflows/live-kalshi-scan.yml)) scans every
15 minutes and publishes a decision dashboard to GitHub Pages. Each run:

1. **Scans Kalshi** (read-only, public API) and curates standard binary
   markets through quality gates.
2. **Builds independent evidence** from five sources, each behind a failure
   boundary so one outage never blocks the rest: Polymarket (bulk + targeted
   search), Manifold, PredictIt, Metaculus, and Open-Meteo weather forecasts,
   plus any manually registered signals in
   [config/forecast_signals.json](config/forecast_signals.json).
3. **Matches equivalent contracts across venues** with a high-recall,
   fail-closed matcher (numeric terms, months, negation, and expiration must
   agree) and publishes both accepted matches and rejected near-matches with
   the exact rejection reason.
4. **Detects structural arbitrage** — YES+NO under $1 on a single contract,
   and cross-venue boxes against high-similarity Polymarket matches using
   executable two-sided quotes — behind conservative fee buffers and always
   with a resolution-rules caveat.
5. **Ranks evidence-backed paper plays** under portfolio limits (play cap,
   risk cap, correlated-category cap). Markets with no independent evidence
   always PASS; the engine never invents an edge.
6. **Keeps an honest scorecard**: every TRADE alert becomes a paper pick,
   marks update on each scan, and awaiting picks are graded against official
   Kalshi settlement results so win rate, Brier score, and realized paper P/L
   reflect real outcomes.

Everything is read-only research tooling: no orders are placed, and paper
sizing uses a $1,000 research bankroll. Prediction-market trading involves
real risk of loss; nothing here guarantees profit.

## Installation & Usage

Requires Python 3.9+. Install dependencies with [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

Download and extract the pre-collected dataset (36GiB compressed):

```bash
make setup
```

This downloads `data.tar.zst` from [Cloudflare R2 Storage](https://s3.jbecker.dev/data.tar.zst) and extracts it to `data/`.

### Data Collection

Collect market and trade data from prediction market APIs:

```bash
make index
```

This opens an interactive menu to select which indexer to run. Data is saved to `data/kalshi/` and `data/polymarket/` directories. Progress is saved automatically, so you can interrupt and resume collection.

### Running Analyses

```bash
make analyze
```

This opens an interactive menu to select which analysis to run. You can run all analyses or select a specific one. Output files (PNG, PDF, CSV, JSON) are saved to `output/`.

### Packaging Data

To compress the data directory for storage/distribution:

```bash
make package
```

This creates a zstd-compressed tar archive (`data.tar.zst`) and removes the `data/` directory.

## Project Structure

```
├── src/
│   ├── analysis/           # Analysis scripts
│   │   ├── kalshi/         # Kalshi-specific analyses
│   │   └── polymarket/     # Polymarket-specific analyses
│   ├── indexers/           # Data collection indexers
│   │   ├── kalshi/         # Kalshi API client and indexers
│   │   └── polymarket/     # Polymarket API/blockchain indexers
│   └── common/             # Shared utilities and interfaces
├── data/                   # Data directory (extracted from data.tar.zst)
│   ├── kalshi/
│   │   ├── markets/
│   │   └── trades/
│   └── polymarket/
│       ├── blocks/
│       ├── markets/
│       └── trades/
├── docs/                   # Documentation
└── output/                 # Analysis outputs (figures, CSVs)
```

## Documentation

- [Data Schemas](docs/SCHEMAS.md) - Parquet file schemas for markets and trades
- [Writing Analyses](docs/ANALYSIS.md) - Guide for writing custom analysis scripts

## Contributing

If you'd like to contribute to this project, please open a pull-request with your changes, as well as detailed information on what is changed, added, or improved.

For more information, see the [contributing guide](CONTRIBUTING.md).

## Issues

If you've found an issue or have a question, please open an issue [here](https://github.com/jon-becker/prediction-market-analysis/issues).

## Research & Citations

- Becker, J. (2026). _The Microstructure of Wealth Transfer in Prediction Markets_. Jbecker. https://jbecker.dev/research/prediction-market-microstructure
- Le, N. A. (2026). _Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets_. arXiv. https://arxiv.org/abs/2602.19520
- Akey P., Gregoire, V., Harvie, N., Martineau, C. (2026). _Who Wins and Who Loses In Prediction Markets? Evidence from Polymarket_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6443103
- Vedova, J. (2026). _Who Profits from Prediction Markets? Execution, not Information_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6191618
- Brown, A. (2026). _Cassandra Or the Boy Who Cried Wolf? Are Prediction Markets Effective Early Warning Systems?_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6381538
- Cao, D. (2026). _Retail-Adjusted Expected Value in Prediction Markets: Calibration, Longshot Bias, and Consumer Welfare_. SSRN. https://papers.ssrn.com/sol3/Delivery.cfm/7049119.pdf?abstractid=7049119&mirid=1
- Reichenbach, F., Walther, M. (2025). _Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5910522
- Bartlett, R., O'Hara, M. (2026). _Adverse Selection in Prediction Markets: Evidence from Kalshi_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615739
- Luong, K. L., Heesen, G. (2026). _The Wisdom of the Few: Skilled Traders and Prediction Market Accuracy_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6758662
- Adegbenro, A. (2026). _What Prediction Markets Can See: Market Formation, Settlement Legibility, and the Geography of Tradable Uncertainty in Africa and Latin America_. arXiv. https://arxiv.org/abs/2606.17503

If you have used or plan to use this dataset in your research, please reach out via [email](mailto:jonathan@jbecker.dev) or [Twitter](https://x.com/BeckerrJon) -- i'd love to hear about what you're using the data for! Additionally, feel free to open a PR and update this section with a link to your paper.
