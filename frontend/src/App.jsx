import React, { useState } from 'react';
import DocumentReview from './components/DocumentReview.jsx';
import CashFlowTab from './components/CashFlowTab.jsx';

export default function App() {
  const [tab, setTab] = useState('documents');

  return (
    <div className="app">
      <header className="masthead">
        <p className="kicker">Form 424B5 — Volkswagen Auto Lease Trust 2025-B</p>
        <h1>Securitization Document Intelligence</h1>
        <p className="dek">
          Abstracts tranche terms from real SEC-filed offering documents and
          models the resulting note payment waterfall.
        </p>
      </header>

      <nav className="tabs">
        <button className={tab === 'documents' ? 'active' : ''} onClick={() => setTab('documents')}>
          Document Review
        </button>
        <button className={tab === 'cashflow' ? 'active' : ''} onClick={() => setTab('cashflow')}>
          Cash Flow
        </button>
      </nav>

      {tab === 'documents' ? <DocumentReview /> : <CashFlowTab />}
    </div>
  );
}
