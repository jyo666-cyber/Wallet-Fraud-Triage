import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { formatDate } from '../components/bits'

const EVENT_TEXT = {
  case_created: 'Case created',
  report_sealed: 'Report sealed',
  review_updated: 'Review updated',
  case_failed: 'Analysis failed',
}

export default function Audit() {
  const [entries, setEntries] = useState(null)
  const [check, setCheck] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.audit().then(setEntries).catch((e) => setError(e.message)) }, [])

  const verify = async () => {
    setBusy(true)
    setError(null)
    try {
      setCheck(await api.verifyAudit())
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Audit log</h1>
          <p>Each entry includes the hash of the one before it, and sealed reports are checked against their recorded hash. This detects later edits. It does not show that a finding is correct.</p>
        </div>
        <button className="btn btn-primary" onClick={verify} disabled={busy}>{busy ? 'Checking…' : 'Verify integrity'}</button>
      </div>
      <div className="stack">
        {error && <div className="callout callout-critical" role="alert">{error}</div>}
        {check && (check.valid ? (
          <div className="callout callout-good" role="status">
            <strong>✓ Intact.</strong> {check.entries} log entries and {check.reports_checked} sealed reports match their hashes.
          </div>
        ) : (
          <div className="callout callout-critical" role="alert">
            <strong>✕ Tampering or corruption detected.</strong> {check.problems.length} problem{check.problems.length > 1 ? 's' : ''} found:
            <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
              {check.problems.slice(0, 10).map((p, i) => <li key={i}>{p.seq ? `Entry ${p.seq}` : p.case_id}: {p.problem}</li>)}
            </ul>
          </div>
        ))}
        <section className="card">
          {!entries ? <p className="muted">Loading log…</p> : entries.length === 0 ? (
            <p className="muted">The log is empty. Entries appear once a <Link to="/new">report is filed</Link>.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead><tr><th className="r">#</th><th>When</th><th>Event</th><th>Case</th><th>Content hash</th><th>Entry hash</th></tr></thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.seq}>
                      <td className="r">{e.seq}</td>
                      <td className="small" style={{ whiteSpace: 'nowrap' }}>{formatDate(e.ts)}</td>
                      <td>{EVENT_TEXT[e.event] || e.event}</td>
                      <td>{e.case_id ? <Link to={`/cases/${e.case_id}`}>{e.case_id}</Link> : '—'}</td>
                      <td className="addr" title={e.payload_hash}>{e.payload_hash.slice(0, 16)}…</td>
                      <td className="addr" title={e.entry_hash}>{e.entry_hash.slice(0, 16)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  )
}
