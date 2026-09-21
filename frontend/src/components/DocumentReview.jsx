import React, { useEffect, useState } from 'react';
import CapitalStack from './CapitalStack.jsx';
import { listSampleFiles, extractSample } from '../api';

export default function DocumentReview() {
  const [files, setFiles] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    listSampleFiles().then(setFiles);
  }, []);

  async function runExtraction(filename) {
    setLoading(true);
    const data = await extractSample(filename);
    setResult(data);
    setLoading(false);
  }

  const pct = result?.accuracy?.overall_field_level_accuracy_pct;

  return (
    <div>
      <div className="sheet">
        <h3>Document Abstraction</h3>
        <p className="lede">
          Runs the extractor against a real SEC EDGAR filing (Volkswagen Auto
          Lease Trust 2025-B, Form 424B5) and scores the result against
          manually-verified ground truth.
        </p>
        {files.map((f) => (
          <button key={f} className="btn" onClick={() => runExtraction(f)} disabled={loading}>
            {loading ? 'Extracting…' : `Extract ${f}`}
          </button>
        ))}
      </div>

      {result && (
        <>
          <div className="sheet reveal">
            <CapitalStack tranches={result.extraction.tranches.map((t) => ({
              class_name: t.class_name,
              seniority_rank: t.seniority_rank,
              initial_balance: t.initial_principal_balance,
            }))} />
          </div>

          <div className="sheet reveal">
            <div className="accuracy-readout">
              <span className={`pct ${pct >= 70 ? 'high' : 'low'}`}>{pct}%</span>
              <span className="caption">
                field-level accuracy · {result.accuracy.fields_correct}/{result.accuracy.fields_scored} fields
                vs. manually verified ground truth
              </span>
            </div>

            <table>
              <thead>
                <tr>
                  <th>Class</th>
                  <th className="num">Balance</th>
                  <th>Coupon</th>
                  <th>Final Payment</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {result.extraction.tranches.map((t) => (
                  <tr key={t.class_name} className={t.flagged_for_review ? 'review-flag' : ''}>
                    <td>{t.class_name}</td>
                    <td className="num">${Number(t.initial_principal_balance).toLocaleString()}</td>
                    <td className="num">
                      {t.coupon_type === 'fixed'
                        ? `${(t.coupon_rate * 100).toFixed(3)}%`
                        : `${t.reference_rate}+${(t.spread * 100).toFixed(2)}%`}
                    </td>
                    <td className="num">{t.final_scheduled_payment_date}</td>
                    <td>
                      {t.flagged_for_review ? (
                        <span className="status-flag">flagged — {t.flag_reason}</span>
                      ) : (
                        <span className="status-match">clear</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="sheet reveal">
            <h3 style={{ fontSize: 16 }}>Deal-level fields</h3>
            <table>
              <tbody>
                {Object.entries(result.accuracy.top_level).map(([field, v]) => (
                  <tr key={field}>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: 12.5, color: 'var(--steel)' }}>{field}</td>
                    <td>{String(v.extracted ?? '—')}</td>
                    <td style={{ textAlign: 'right' }}>
                      {v.match ? <span className="status-match">match</span> : <span className="status-mismatch">mismatch</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
