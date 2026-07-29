/* Runtime presentation layer for the multi-source evidence engine. */
(() => {
  const evidenceMetricLabel = document.querySelector('#matchCount')?.closest('.metric')?.querySelector('small');
  if (evidenceMetricLabel) evidenceMetricLabel.textContent = 'Evidence markets';

  const originalUpdateHeader = updateHeader;
  updateHeader = function updateMultiSourceHeader() {
    originalUpdateHeader();
    const matched = rows.filter(row => row.model_probability != null);
    const sources = Array.isArray(evidenceMeta.sources) ? evidenceMeta.sources : [];
    const healthySources = sources.filter(source => source.status === 'healthy').length;
    const evidenceMarkets = meta.evidence_market_count ?? evidenceMeta.independent_signal_markets ?? matched.length;
    const venueMatches = meta.cross_venue_match_count ?? evidenceMeta.cross_venue_matches ?? 0;
    const nearMatches = meta.near_match_count ?? evidenceMeta.near_match_count ?? 0;
    const perf = history.performance || {};

    document.getElementById('matchCount').textContent = evidenceMarkets;
    document.getElementById('matchDetail').textContent = `${venueMatches} venue matches · ${healthySources}/${sources.length || 0} sources healthy`;
    document.getElementById('foot').textContent = `Updated every 15 minutes. ${evidenceMarkets} signal-bearing markets, ${venueMatches} venue matches, ${nearMatches} rejected near matches, and ${perf.total_picks || 0} paper picks recorded. No real-money orders are placed.`;
  };

  renderRadar = function renderMultiSourceRadar() {
    const data = filteredRows(matchedRows());
    document.getElementById('resultCount').textContent = `${data.length} evidence-bearing market${data.length === 1 ? '' : 's'}`;
    const root = document.getElementById('content');
    if (!data.length) {
      root.innerHTML = '<div class="panel empty"><strong>No independent probability signal is available.</strong>Review Near matches for rejected venue candidates and Sources & health for model coverage.</div>';
      return;
    }
    root.innerHTML = data.map((row, index) => playCard(row, index + 1, row.action === 'PASS' ? 'WATCH' : 'TRADE')).join('');
  };

  renderSystem = function renderMultiSourceSystem() {
    const matches = Array.isArray(evidenceMeta.matches) ? evidenceMeta.matches : [];
    const near = Array.isArray(evidenceMeta.near_matches) ? evidenceMeta.near_matches : [];
    const sources = Array.isArray(evidenceMeta.sources) ? evidenceMeta.sources : [];
    document.getElementById('resultCount').textContent = `Build ${meta.build_sha || 'unknown'} · run ${meta.build_run || '—'}`;

    const sourceRows = sources.length
      ? `<div class="table-wrap"><table class="table"><thead><tr><th>Source</th><th>Status</th><th>Items loaded</th><th>Signals</th><th>Venue matches</th><th>Diagnostics</th></tr></thead><tbody>${sources.map(source => `<tr><td><strong>${esc(source.name || 'Unknown')}</strong><div class="small">${esc(source.api || 'Public API')}</div></td><td><span class="badge ${source.status === 'healthy' ? 'good' : source.status === 'partial' ? 'warn' : source.status === 'not_applicable' ? '' : 'bad'}">${esc(source.status || 'unknown')}</span></td><td>${fmtNum(source.markets_loaded || 0)}</td><td>${fmtNum(source.signals ?? source.matches ?? 0)}</td><td>${fmtNum(source.matches || 0)}</td><td class="small">${esc(source.error || source.weighting || `${source.targeted_queries || source.request_count || 0} requests · ${source.targeted_query_errors || source.request_errors || 0} errors`)}</td></tr>`).join('')}</tbody></table></div>`
      : '<div class="empty">No source-level health records were published.</div>';

    const matchRows = matches.length
      ? `<div class="table-wrap"><table class="table"><thead><tr><th>Kalshi ticker</th><th>Source</th><th>Matched question</th><th>Probability</th><th>Similarity</th><th>Confidence</th></tr></thead><tbody>${matches.slice(0, 40).map(match => `<tr><td class="ticker">${esc(match.ticker)}</td><td><span class="badge">${esc(match.source || 'External')}</span></td><td>${match.source_url ? `<a href="${esc(match.source_url)}" target="_blank" rel="noopener">${esc(match.external_question)}</a>` : esc(match.external_question)}</td><td>${fmtPct(match.external_probability)}</td><td>${fmtPct(match.similarity)}</td><td>${fmtPct(match.confidence)}</td></tr>`).join('')}</tbody></table></div>`
      : '<div class="empty">No equivalent venue contract cleared the semantic, date, activity, and volume gates. Category models can still produce independent probabilities.</div>';

    document.getElementById('content').innerHTML = `<div class="system-grid"><div class="panel"><h3>Runtime</h3>${metricLine('Kalshi scanner', markets.length ? `Healthy · ${markets.length} markets` : 'Degraded')}${metricLine('Overall evidence', evidenceMeta.source_status || 'unknown')}${metricLine('Source items loaded', fmtNum(evidenceMeta.source_items_loaded ?? evidenceMeta.external_markets_loaded ?? 0))}${metricLine('Independent signal markets', fmtNum(evidenceMeta.independent_signal_markets ?? meta.evidence_market_count ?? 0))}${metricLine('Venue-equivalent matches', fmtNum(evidenceMeta.cross_venue_matches || 0))}${metricLine('Rejected near matches', fmtNum(evidenceMeta.near_match_count || near.length))}</div><div class="panel"><h3>Trade gates</h3>${metricLine('Independent probability', 'Required')}${metricLine('Gross edge', 'At least 4%')}${metricLine('Confidence', 'At least 65%')}${metricLine('Hard volume floor', '100 contracts')}${metricLine('Hard spread limit', 'Below 10%')}${metricLine('Settlement rules', 'Required')}${metricLine('Correlation', 'One play per category')}${metricLine('Sizing', '2% per play · 10% portfolio')}</div></div><div class="panel"><h3>Evidence sources</h3>${sourceRows}</div><div class="panel"><h3>Latest venue-equivalent matches</h3>${matchRows}</div><div class="panel"><h3>What this can prove</h3><p class="small">The dashboard can prove that current data was retrieved, an independent forecast passed declared gates, the recommendation used declared sizing and portfolio rules, and the paper result was recorded afterward. It cannot guarantee an outcome or claim profitability before enough picks resolve.</p></div>`;
  };

  // Apply the revised labels immediately, then again after the asynchronous data load.
  document.getElementById('matchDetail').textContent = 'Independent probability signals';
  setTimeout(() => {
    if (Array.isArray(rows) && rows.length) updateHeader();
  }, 0);
})();
