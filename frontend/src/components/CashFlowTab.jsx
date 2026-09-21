import React, { useEffect, useState } from 'react';
import WaterfallExplorer from './WaterfallExplorer.jsx';
import { getSampleCashflowRequest, runWaterfall, exportExcel } from '../api';

export default function CashFlowTab() {
  const [sampleReq, setSampleReq] = useState(null);
  const [runData, setRunData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getSampleCashflowRequest().then(setSampleReq);
  }, []);

  async function handleRun() {
    setLoading(true);
    const data = await runWaterfall({ tranches: sampleReq.tranches, assumptions: sampleReq.assumptions });
    const rankByName = Object.fromEntries(sampleReq.tranches.map((t) => [t.class_name, t.seniority_rank]));
    data.tranches.forEach((t) => (t.rank = rankByName[t.class_name]));
    setRunData(data);
    setLoading(false);
  }

  async function handleExport() {
    await exportExcel(sampleReq);
  }

  return (
    <div>
      <div className="sheet">
        <h3>Cash Flow / Waterfall Engine</h3>
        <p className="lede">
          Simplified sequential-pay waterfall for the VW ALT 2025-B tranche structure.
          Senior classes are retired first; the model does not simulate pro-rata, turbo,
          or trigger-driven priority changes.
        </p>
        {sampleReq && (
          <p className="assumption-line">
            CPR {(sampleReq.assumptions.annual_cpr * 100).toFixed(1)}% · default rate{' '}
            {(sampleReq.assumptions.annual_default_rate * 100).toFixed(1)}% · collateral WAC{' '}
            {(sampleReq.assumptions.collateral_wac * 100).toFixed(1)}%
          </p>
        )}
        <button className="btn" onClick={handleRun} disabled={loading || !sampleReq}>
          {loading ? 'Running…' : 'Run Waterfall'}
        </button>{' '}
        <button className="btn secondary" onClick={handleExport} disabled={!sampleReq}>
          Download Excel
        </button>
      </div>

      {runData && (
        <div className="sheet reveal">
          <h3>Paydown Explorer</h3>
          <WaterfallExplorer tranches={runData.tranches} />

          <div className="summary-grid">
            {runData.tranches.map((t) => (
              <div className="summary-cell" key={t.class_name}>
                <div className="k">{t.class_name} · WAL / YTM</div>
                <div className="v">
                  {t.wal_years}y / {t.approx_pretax_ytm != null ? `${(t.approx_pretax_ytm * 100).toFixed(2)}%` : '—'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
