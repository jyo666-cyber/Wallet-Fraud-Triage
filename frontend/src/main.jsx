import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from './api'
import Cases from './pages/Cases'
import NewCase from './pages/NewCase'
import CaseDetail from './pages/CaseDetail'
import WalletCheck from './pages/WalletCheck'
import Model from './pages/Model'
import Audit from './pages/Audit'
import './styles.css'

function Shell() {
  const [health, setHealth] = useState(null)
  const [down, setDown] = useState(false)
  const location = useLocation()

  useEffect(() => {
    api.health().then((h) => { setHealth(h); setDown(false) }).catch(() => setDown(true))
  }, [location.pathname])

  return (
    <>
      <header className="topbar no-print">
        <div className="topbar-inner">
          <NavLink to="/" className="brand">
            <svg width="20" height="20" viewBox="0 0 32 32" aria-hidden="true"><path d="M6 25 L16 7 L26 25 Z" fill="none" stroke="currentColor" strokeWidth="3" strokeLinejoin="round" /></svg>
            Wallet Fraud Triage
          </NavLink>
          <nav aria-label="Main">
            <NavLink to="/" end>Cases</NavLink>
            <NavLink to="/wallet">Wallet check</NavLink>
            <NavLink to="/model">Model</NavLink>
            <NavLink to="/audit">Audit log</NavLink>
          </nav>
          <NavLink to="/new" className="btn btn-primary btn-nav">New report</NavLink>
        </div>
      </header>
      {down && (
        <div className="banner banner-critical no-print" role="alert">
          The backend is not responding on port 8000. Start it with start.ps1, then reload this page.
        </div>
      )}
      {health && !health.model_loaded && (
        <div className="banner banner-warning no-print" role="status">
          No trained model yet, so tracing works but new cases get no risk score. The model appears here automatically once ml/train.py finishes.
        </div>
      )}
      <main className="page">
        <Routes>
          <Route path="/" element={<Cases />} />
          <Route path="/new" element={<NewCase />} />
          <Route path="/cases/:id" element={<CaseDetail />} />
          <Route path="/wallet" element={<WalletCheck />} />
          <Route path="/model" element={<Model />} />
          <Route path="/audit" element={<Audit />} />
          <Route path="*" element={<p className="muted">This page does not exist.</p>} />
        </Routes>
      </main>
      <footer className="footnote no-print">
        Output is a risk indication for human review, not proof of fraud. Chain data from Blockscout.
      </footer>
    </>
  )
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  </React.StrictMode>,
)
