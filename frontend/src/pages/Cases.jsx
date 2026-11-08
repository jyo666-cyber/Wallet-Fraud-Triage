import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { LevelBadge, StatusBadge, Tile, formatDate, pct, shortAddr } from '../components/bits'

const RANK = { high: 0, medium: 1, low: 2 }
const REVIEW_TEXT = { open: 'Open', escalated: 'Escalated', dismissed: 'Dismissed', resolved: 'Resolved' }

export default function Cases() {
  const [cases, setCases] = useState(null)
  const [error, setError] = useState(null)
  const [priority, setPriority] = useState('all')
  const [review, setReview] = useState('open')
  const navigate = useNavigate()

  useEffect(() => {
    let alive = true
    const load = () => api.cases().then((c) => { if (alive) { setCases(c); setError(null) } }).catch((e) => alive && setError(e.message))
    load()
    const timer = setInterval(load, 5000)
    return () => { alive = false; clearInterval(timer) }
  }, [])

  const visible = useMemo(() => (cases || [])
    .filter((c) => priority === 'all' || c.priority === priority)
    .filter((c) => review === 'all' || c.review_status === review)
    .sort((a, b) => (RANK[a.priority] ?? 3) - (RANK[b.priority] ?? 3) || b.created_at.localeCompare(a.created_at)),
  [cases, priority, review])

  const head = (
    <div className="page-head">
      <div>
        <h1>Case queue</h1>
        <p>Victim reports, highest review priority first. Each one is scored, traced toward exchanges and sealed in the audit log.</p>
      </div>
    </div>
  )

  if (error && !cases) return <>{head}<div className="callout callout-critical">{error}</div></>
  if (!cases) return <>{head}<p className="muted">Loading cases…</p></>
  if (!cases.length) {
    return (
      <>
        {head}
        <div className="card empty">
          <h2>No reports yet</h2>
          <p>Start with a suspect wallet address. The trace runs live against Ethereum and usually takes under a minute.</p>
          <Link className="btn btn-primary" to="/new">File the first report</Link>
        </div>
      </>
    )
  }

  const open = cases.filter((c) => c.review_status === 'open')
  return (
    <>
      {head}
      <div className="stack">
        <div className="tiles">
          <Tile label="Open cases" value={open.length} />
          <Tile label="High priority, open" value={open.filter((c) => c.priority === 'high').length} />
          <Tile label="Cases reaching an exchange" value={cases.filter((c) => c.exchanges.length).length} note={`of ${cases.length} total`} />
        </div>
        <div className="card">
          <div className="filters">
            <label className="small ink-2" htmlFor="f-priority">Priority</label>
            <select id="f-priority" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="all">All</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option>
            </select>
            <label className="small ink-2" htmlFor="f-review">Review</label>
            <select id="f-review" value={review} onChange={(e) => setReview(e.target.value)}>
              <option value="all">All</option><option value="open">Open</option><option value="escalated">Escalated</option><option value="dismissed">Dismissed</option><option value="resolved">Resolved</option>
            </select>
          </div>
          {visible.length === 0 ? (
            <p className="muted" style={{ padding: '12px 0' }}>No cases match these filters.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Priority</th><th>Case</th><th>Suspect wallet</th><th>Exchanges reached</th><th className="r">Model score</th><th>Status</th><th>Review</th><th>Reported</th></tr></thead>
                <tbody>
                  {visible.map((c) => (
                    <tr key={c.id} className="clickable" onClick={() => navigate(`/cases/${c.id}`)}>
                      <td><LevelBadge level={c.priority} /></td>
                      <td><Link to={`/cases/${c.id}`} onClick={(e) => e.stopPropagation()}>{c.id}</Link></td>
                      <td className="addr">{shortAddr(c.address)}{c.flagged && <div className="small" style={{ color: 'var(--critical)', fontFamily: 'var(--sans)' }}>On a fraud list</div>}</td>
                      <td>{c.exchanges.length ? c.exchanges.join(', ') : <span className="muted">{c.status === 'complete' ? 'None found' : '—'}</span>}</td>
                      <td className="r">{pct(c.score)}</td>
                      <td><StatusBadge status={c.status} /></td>
                      <td>{REVIEW_TEXT[c.review_status]}</td>
                      <td className="small muted" style={{ whiteSpace: 'nowrap' }}>{formatDate(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
