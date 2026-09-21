import React from 'react';

// Seniority -> color, senior (safest) to junior (riskiest). Not a generic
// gradient — the color mapping is meaningful: steel = investment-grade senior,
// warming toward amber as subordination increases.
const RANK_COLORS = {
  1: '#4c6b85', // Class A-1, most senior
  2: '#6d84a0', // Class A-2 (A/B pari passu)
  3: '#c08a34', // Class A-3
  4: '#a63d2f', // Class A-4, most junior
};

export default function CapitalStack({ tranches }) {
  if (!tranches || tranches.length === 0) return null;

  const total = tranches.reduce((sum, t) => sum + t.initial_balance, 0);

  return (
    <div className="stack-wrap">
      <div className="stack">
        {tranches
          .slice()
          .sort((a, b) => a.seniority_rank - b.seniority_rank)
          .map((t) => {
            const pct = (t.initial_balance / total) * 100;
            return (
              <div
                key={t.class_name}
                className="stack-row"
                style={{
                  background: RANK_COLORS[t.seniority_rank] || '#7f97ab',
                  flexBasis: `${Math.max(pct, 8)}%`,
                }}
              >
                <span className="cls">{t.class_name}</span>
                <span className="amt">${(t.initial_balance / 1e6).toFixed(1)}M</span>
              </div>
            );
          })}
      </div>
      <div className="stack-total">
        <span className="amount">${(total / 1e6).toFixed(0)}M</span>
        <span className="label">aggregate note offering, senior (top) to junior (bottom)</span>
      </div>
    </div>
  );
}
