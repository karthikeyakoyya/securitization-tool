import React, { useMemo, useState } from 'react';

const RANK_COLORS = {
  1: '#4c6b85',
  2: '#6d84a0',
  3: '#c08a34',
  4: '#a63d2f',
};

export default function WaterfallExplorer({ tranches }) {
  const maxPeriod = Math.max(...tranches.map((t) => t.schedule.length));
  const [period, setPeriod] = useState(1);

  const rowsAtPeriod = useMemo(() => {
    return tranches.map((t) => {
      const row = t.schedule[Math.min(period - 1, t.schedule.length - 1)];
      const initial = t.schedule[0]?.beg_balance || 1;
      const endBalance = row ? row.end_balance : 0;
      const pctPaid = 100 - (endBalance / initial) * 100;
      return {
        class_name: t.class_name,
        rank: t.rank,
        initial,
        endBalance,
        pctPaid,
      };
    });
  }, [tranches, period]);

  return (
    <div>
      <div className="explorer-header">
        <span className="muted">Drag to watch principal pay down, senior class first</span>
        <span className="period-readout">
          Month <strong>{period}</strong> of {maxPeriod}
        </span>
      </div>

      <input
        type="range"
        className="slider"
        min={1}
        max={maxPeriod}
        value={period}
        onChange={(e) => setPeriod(Number(e.target.value))}
      />

      <div className="explorer-stack">
        {rowsAtPeriod.map((r) => (
          <div className="explorer-row" key={r.class_name}>
            <span>{r.class_name}</span>
            <div className="track">
              <div
                className="fill"
                style={{
                  width: `${100 - r.pctPaid}%`,
                  background: RANK_COLORS[r.rank] || '#7f97ab',
                }}
              />
            </div>
            <span>${(r.endBalance / 1e6).toFixed(1)}M</span>
            <span className="pct-paid">{r.pctPaid.toFixed(0)}% paid</span>
          </div>
        ))}
      </div>
    </div>
  );
}
