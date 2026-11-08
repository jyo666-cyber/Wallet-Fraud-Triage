import { useState } from 'react'

export const shortAddr = (a) => (a ? `${a.slice(0, 8)}…${a.slice(-6)}` : '')
export const etherscanAddr = (a) => `https://etherscan.io/address/${a}`
export const etherscanTx = (h) => `https://etherscan.io/tx/${h}`
export const pct = (x, digits = 0) => (x == null ? '—' : `${(x * 100).toFixed(digits)}%`)

export function formatAmount(value) {
  if (value == null) return '—'
  if (value >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (value >= 1) return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return value.toLocaleString(undefined, { maximumSignificantDigits: 3 })
}

export function formatDate(value) {
  if (!value) return '—'
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value)
  return date.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

const LEVEL_ICON = { high: '▲', medium: '◆', low: '●' }
const LEVEL_TEXT = { high: 'High', medium: 'Medium', low: 'Low' }

export function LevelBadge({ level, suffix = '' }) {
  if (!level) return <span className="badge">Not rated</span>
  return (
    <span className={`badge badge-${level}`}>
      <span aria-hidden="true">{LEVEL_ICON[level]}</span> {LEVEL_TEXT[level]}{suffix}
    </span>
  )
}

const STATUS_TEXT = { queued: 'Queued', running: 'Analysing', complete: 'Complete', failed: 'Failed' }
export function StatusBadge({ status }) {
  if (status === 'failed') return <span className="badge badge-high">Failed</span>
  if (status === 'complete') return <span className="badge">Complete</span>
  return <span className="badge badge-info">{STATUS_TEXT[status] || status}</span>
}

export function Address({ value, short = false }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard can be blocked; the value is still on screen */ }
  }
  return (
    <span className="addr">
      <a href={etherscanAddr(value)} target="_blank" rel="noreferrer" title={value}>{short ? shortAddr(value) : value}</a>{' '}
      <button type="button" className="link-btn small no-print" onClick={copy} aria-label={`Copy address ${value}`}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </span>
  )
}

export function Tile({ label, value, note }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {note && <div className="tile-note">{note}</div>}
    </div>
  )
}

export function Reasons({ reasons }) {
  const max = Math.max(...reasons.map((r) => Math.abs(r.contribution)), 0.001)
  return (
    <div>
      {reasons.map((r) => (
        <div className="reason" key={r.feature}>
          <div>
            <div className="reason-title">{r.description}</div>
            <div className="reason-values">
              This wallet: {r.value} · Typical control wallet: {r.typical} · Pushes risk {r.pushes}
            </div>
          </div>
          <div className="div-bar" aria-hidden="true">
            <i className={r.pushes} style={{ width: `${(Math.abs(r.contribution) / max) * 50}%` }} />
          </div>
        </div>
      ))}
      <div className="legend">
        <span><i style={{ background: 'var(--up)' }} />Raises the score</span>
        <span><i style={{ background: 'var(--down)' }} />Lowers the score</span>
      </div>
    </div>
  )
}

export function RiskSummary({ risk }) {
  if (!risk) return null
  if (risk.status !== 'scored') return <div className="callout">{risk.message}</div>
  const { medium, high } = risk.thresholds
  return (
    <div>
      <div className="row" style={{ alignItems: 'baseline', gap: 14 }}>
        <span className="hero-score">{pct(risk.score)}</span>
        <LevelBadge level={risk.level} suffix=" review priority" />
      </div>
      <p className="muted small" style={{ marginTop: 6 }}>
        Model score from {risk.model_name}. It says how closely this wallet's behaviour resembles wallets on public scam lists. It is not a probability that this person committed fraud.
      </p>
      <div className="track" role="img" aria-label={`Score ${pct(risk.score)}. Medium starts at ${pct(medium)}, high at ${pct(high)}.`}>
        <div className="track-mark" style={{ left: `${medium * 100}%` }}><span>Medium {pct(medium)}</span></div>
        <div className="track-mark" style={{ left: `${high * 100}%` }}><span>High {pct(high)}</span></div>
        <div className="track-dot" style={{ left: `${risk.score * 100}%` }} />
      </div>
      {risk.history_truncated && (
        <p className="small muted">This wallet is busy, so the score covers only its most recent activity.</p>
      )}
    </div>
  )
}
