import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import {
  Address, LevelBadge, Reasons, RiskSummary, StatusBadge,
  etherscanTx, formatAmount, formatDate, pct, shortAddr,
} from '../components/bits'
import FlowGraph from '../components/FlowGraph'

const TERMINAL_TEXT = {
  mixer: 'Entered a mixer, where the on-chain trail is deliberately broken',
  dex: 'Swapped on a decentralised exchange, so it may continue as another asset',
  bridge: 'Moved through a bridge, likely to another blockchain',
  high_activity: 'Reached a very busy unlabelled address, which may be an unknown service',
}

function useLiveCase(id) {
  const [record, setRecord] = useState(null)
  const [error, setError] = useState(null)
  const [live, setLive] = useState({ status: null, nodes: [], edges: [], hits: [], risk: null })

  const load = useCallback(() => api.case(id).then(setRecord).catch((e) => setError(e.message)), [id])

  useEffect(() => {
    setRecord(null)
    setError(null)
    setLive({ status: null, nodes: [], edges: [], hits: [], risk: null })
    load()
    const source = new EventSource(`/api/cases/${id}/events`)
    source.onmessage = (message) => {
      const event = JSON.parse(message.data)
      if (event.type === 'status') setLive((s) => ({ ...s, status: event.message }))
      if (event.type === 'risk') setLive((s) => ({ ...s, risk: event }))
      if (event.type === 'edge') setLive((s) => ({ ...s, edges: [...s.edges, event.edge] }))
      if (event.type === 'exchange') setLive((s) => ({ ...s, hits: [...s.hits, event.hit] }))
      if (event.type === 'node') {
        setLive((s) => {
          const nodes = s.nodes.filter((n) => n.id !== event.node.id)
          return { ...s, nodes: [...nodes, event.node] }
        })
      }
      if (event.type === 'complete' || event.type === 'failed') {
        source.close()
        load()
      }
    }
    // The stream ending early is not fatal: the stored case is the source of truth.
    source.onerror = () => { source.close(); load() }
    return () => source.close()
  }, [id, load])

  return { record, error, live, reload: load }
}

export default function CaseDetail() {
  const { id } = useParams()
  const { record, error, live, reload } = useLiveCase(id)

  if (error && !record) return <div className="callout callout-critical">{error} <Link to="/">Back to cases</Link></div>
  if (!record) return <p className="muted">Loading case…</p>

  const report = record.report
  const running = record.status === 'queued' || record.status === 'running'
  const risk = report?.risk || live.risk?.risk
  const flags = report?.list_flags || live.risk?.flags || []
  const signals = report?.signals || live.risk?.signals
  const trace = report?.trace
  const nodes = trace?.nodes || live.nodes
  const edges = trace?.edges || live.edges

  return (
    <div className="stack">
      <div className="page-head" style={{ marginBottom: 4 }}>
        <div style={{ minWidth: 0 }}>
          <div className="row small no-print"><Link to="/">Cases</Link><span className="muted">/</span><span className="muted">{record.id}</span></div>
          <h1 style={{ marginTop: 6 }}>{record.id}</h1>
          <div style={{ marginTop: 6 }}><Address value={record.address} /></div>
          <div className="row" style={{ marginTop: 8 }}>
            <LevelBadge level={record.priority} suffix={record.priority ? ' priority' : ''} />
            <StatusBadge status={record.status} />
            {report?.suspect_entity && <span className="badge badge-info">Known as {report.suspect_entity.name}</span>}
            <span className="small muted">Reported {formatDate(record.created_at)}</span>
          </div>
        </div>
        {report && (
          <div className="row no-print">
            <button className="btn" onClick={() => window.print()}>Print report</button>
            <a className="btn" href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(report, null, 2))}`} download={`${record.id}.json`}>Download JSON</a>
          </div>
        )}
      </div>

      {running && (
        <div className="card progress no-print" role="status" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <span>{live.status || 'Starting analysis'}. The chain data source is rate limited, so a wide trace can take a minute or two.</span>
        </div>
      )}
      {record.status === 'failed' && (
        <div className="callout callout-critical" role="alert">
          The analysis did not finish: {record.error}. No result was stored. Please <Link to="/new">submit the report again</Link>.
        </div>
      )}
      {report?.notes?.map((note) => <div className="callout callout-warning" key={note}>{note}</div>)}
      {report?.suspect_entity?.category === 'exchange' && (
        <div className="callout callout-warning">
          This address is labelled as an {report.suspect_entity.entity} exchange wallet, not an individual's wallet. Reports against it usually mean the funds went to a customer account at that exchange.
        </div>
      )}

      <ExchangeSection trace={trace} hits={live.hits} running={running} />

      {nodes.length > 0 && (
        <section className="card">
          <div className="card-head">
            <h2>Money flow</h2>
            <p>Left to right, starting at the suspect wallet. Only the largest outgoing branches are followed at each step. Hover over a line to see its amount.</p>
          </div>
          <FlowGraph nodes={nodes} edges={edges} />
          {edges.length > 0 && <TransferTable edges={edges} />}
          {trace?.limits?.length > 0 && (
            <div className="small muted" style={{ marginTop: 10 }}>
              <strong>Coverage limits:</strong> {trace.limits.slice(0, 4).join('. ')}{trace.limits.length > 4 ? `, and ${trace.limits.length - 4} more.` : '.'}
            </div>
          )}
        </section>
      )}

      <div className="grid-side">
        <section className="card">
          <div className="card-head"><h2>Why this wallet was rated this way</h2></div>
          {risk ? <RiskSummary risk={risk} /> : <p className="muted">Waiting for wallet data…</p>}
          {risk?.reasons && (
            <>
              <h3 style={{ marginTop: 14 }}>Main factors</h3>
              <Reasons reasons={risk.reasons} />
              <p className="small muted" style={{ marginTop: 10 }}>These explain what drove the model's score. They do not show intent, and each one can have a legitimate cause.</p>
            </>
          )}
        </section>
        <div className="stack">
          <section className="card">
            <div className="card-head"><h2>Public list checks</h2><p>Kept separate from the model score.</p></div>
            {flags.length > 0 ? (
              <div className="callout callout-critical">
                <strong>On {flags.length} public list entr{flags.length === 1 ? 'y' : 'ies'}</strong>
                <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{flags.slice(0, 5).map((f) => <li key={f}>{f}</li>)}</ul>
              </div>
            ) : <p className="ink-2">Not on the fraud lists checked. Lists are incomplete, so this does not clear the wallet.</p>}
            {signals && (
              <dl className="kv" style={{ marginTop: 10 }}>
                <dt>Counterparties checked</dt><dd className="num">{signals.counterparties_checked}</dd>
                <dt>On a fraud list</dt><dd className="num">{signals.flagged_count}</dd>
                <dt>Mixer contacts</dt><dd>{signals.mixer_contacts.length ? signals.mixer_contacts.join(', ') : 'None'}</dd>
              </dl>
            )}
          </section>
          {report?.priority_reasons?.length > 0 && (
            <section className="card">
              <div className="card-head"><h2>Why this priority</h2></div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>{report.priority_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            </section>
          )}
          <ReviewForm record={record} onSaved={reload} />
        </div>
      </div>

      {(record.victim_tx || record.amount_lost || record.description || record.incident_date) && (
        <section className="card">
          <div className="card-head"><h2>Victim's report</h2></div>
          <dl className="kv">
            {record.amount_lost && <><dt>Amount lost</dt><dd>{record.amount_lost}</dd></>}
            {record.incident_date && <><dt>Date</dt><dd>{record.incident_date}</dd></>}
            {record.victim_tx && <><dt>Transaction</dt><dd className="addr"><a href={etherscanTx(record.victim_tx)} target="_blank" rel="noreferrer">{record.victim_tx}</a></dd></>}
            {record.description && <><dt>Details</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{record.description}</dd></>}
          </dl>
        </section>
      )}

      {report && (
        <section className="card">
          <div className="card-head">
            <h2>Sealed report</h2>
            <p>The hash below is recorded in the audit log, so any later change to this report can be detected. It does not show the findings are correct.</p>
          </div>
          <dl className="kv">
            <dt>SHA-256</dt><dd className="addr">{record.report_hash}</dd>
            <dt>Generated</dt><dd>{formatDate(report.generated_at)}</dd>
            <dt>Model version</dt><dd>{report.risk?.model_version || 'Not scored'}</dd>
            <dt>Audit entries</dt><dd className="num">{record.audit.length} · <Link to="/audit" className="no-print">view log</Link></dd>
          </dl>
          <div className="callout" style={{ marginTop: 12 }}>{report.disclaimer}</div>
        </section>
      )}
    </div>
  )
}

function ExchangeSection({ trace, hits, running }) {
  if (trace) {
    return (
      <section className="card">
        <div className="card-head">
          <h2>{trace.exchanges.length ? `Funds reached ${trace.exchanges.length} exchange${trace.exchanges.length > 1 ? 's' : ''}` : 'No exchange reached'}</h2>
          <p>{trace.exchanges.length
            ? 'An exchange can identify its account holders, so this is the point where an official request can lead somewhere.'
            : 'Within the hop and branch limits of this trace, funds did not reach a labelled exchange wallet. Exchange labels are incomplete, so this does not rule it out.'}</p>
        </div>
        {trace.exchanges.length > 0 && (
          <div className="grid-2">
            {trace.exchanges.map((e) => <ExchangeCard key={e.exchange} exchange={e} routes={trace.routes.filter((r) => r.exchange === e.exchange)} />)}
          </div>
        )}
        {trace.terminals.length > 0 && <Terminals terminals={trace.terminals} />}
        {trace.exchanges.length > 0 && (
          <div className="callout" style={{ marginTop: 12 }}>
            <strong>What to do next:</strong> file a complaint with the police. In India, use cybercrime.gov.in or call 1930. Attach this report and ask them to request account details and a freeze from the exchange, quoting the addresses and transaction hashes shown here.
          </div>
        )}
      </section>
    )
  }
  if (!running) return null
  return (
    <section className="card" aria-live="polite">
      <div className="card-head"><h2>Looking for exchanges</h2></div>
      {hits.length === 0
        ? <p className="muted">No exchange reached so far.</p>
        : <ul style={{ margin: 0, paddingLeft: 18 }}>{[...new Set(hits.map((h) => h.exchange))].map((name) => <li key={name}><strong>{name}</strong> reached</li>)}</ul>}
    </section>
  )
}

function ExchangeCard({ exchange, routes }) {
  const shortest = [...routes].sort((a, b) => a.hops - b.hops)[0]
  return (
    <article className="exchange-card">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="exchange-name">{exchange.exchange}</span>
        <span className="badge badge-info" title="How direct the on-chain link is. This is a transparent rule, not a probability.">
          <span style={{ textTransform: 'capitalize' }}>{exchange.confidence}</span>&nbsp;confidence link
        </span>
      </div>
      <dl className="kv">
        <dt>Up to</dt><dd className="num">{Object.entries(exchange.assets).map(([asset, amount]) => `${formatAmount(amount)} ${asset}`).join(' · ')}</dd>
        <dt>Closest route</dt><dd>{exchange.min_hops} hop{exchange.min_hops > 1 ? 's' : ''}</dd>
        <dt>Traced outflow</dt><dd>{pct(exchange.share_of_traced_outflow)} of the largest asset's outflow</dd>
        <dt>Exchange wallet</dt><dd>{shortest.wallet_name} · <a className="addr" href={`https://etherscan.io/address/${shortest.wallet}`} target="_blank" rel="noreferrer">{shortAddr(shortest.wallet)}</a></dd>
        {exchange.deposit_addresses.length > 0 && (
          <><dt>Likely deposit</dt><dd>{exchange.deposit_addresses.map((d) => <div key={d}><Address value={d} short /></div>)}</dd></>
        )}
      </dl>
      {shortest.route.length > 0 && (
        <p className="small muted" style={{ margin: 0 }}>
          Route evidence: {shortest.route.map((step, i) => (
            <span key={step.tx + i}>{i > 0 && ' → '}<a className="addr" href={etherscanTx(step.tx)} target="_blank" rel="noreferrer">{shortAddr(step.tx)}</a></span>
          ))}
        </p>
      )}
    </article>
  )
}

function Terminals({ terminals }) {
  const grouped = new Map()
  terminals.forEach((t) => {
    const key = `${t.kind}|${t.name || t.address}`
    if (!grouped.has(key)) grouped.set(key, t)
  })
  return (
    <div style={{ marginTop: 12 }}>
      <h3>Other places funds went</h3>
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {[...grouped.values()].slice(0, 8).map((t) => (
          <li key={`${t.kind}${t.address}`} className="small ink-2">
            <strong>{t.name || shortAddr(t.address)}</strong>: {TERMINAL_TEXT[t.kind] || t.kind}
          </li>
        ))}
      </ul>
    </div>
  )
}

function TransferTable({ edges }) {
  return (
    <details style={{ marginTop: 12 }} open={false}>
      <summary>Show {edges.length === 1 ? 'this transfer' : `all ${edges.length} transfers`} as a table</summary>
      <div className="table-wrap" style={{ marginTop: 8 }}>
        <table>
          <thead><tr><th>From</th><th>To</th><th className="r">Up to</th><th>Asset</th><th>First seen</th><th>Transaction</th></tr></thead>
          <tbody>
            {edges.map((e, i) => (
              <tr key={`${e.tx}${i}`}>
                <td className="addr">{shortAddr(e.source)}</td>
                <td className="addr">{shortAddr(e.target)}</td>
                <td className="r">{formatAmount(e.amount)}</td>
                <td>{e.asset}</td>
                <td className="small" style={{ whiteSpace: 'nowrap' }}>{formatDate(e.ts)}</td>
                <td className="addr"><a href={etherscanTx(e.tx)} target="_blank" rel="noreferrer">{shortAddr(e.tx)}</a></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  )
}

function ReviewForm({ record, onSaved }) {
  const [status, setStatus] = useState(record.review_status)
  const [note, setNote] = useState(record.review_note || '')
  const [state, setState] = useState(null)

  const save = async (event) => {
    event.preventDefault()
    setState('saving')
    try {
      await api.review(record.id, { review_status: status, review_note: note.trim() || null })
      setState('saved')
      onSaved()
    } catch (e) {
      setState(e.message)
    }
  }

  return (
    <section className="card no-print">
      <div className="card-head"><h2>Analyst review</h2><p>A person makes the decision. Each change is written to the audit log.</p></div>
      <form onSubmit={save} className="stack" style={{ gap: 10 }}>
        <div className="field">
          <label htmlFor="review-status">Decision</label>
          <select id="review-status" style={{ width: '100%' }} value={status} onChange={(e) => { setStatus(e.target.value); setState(null) }}>
            <option value="open">Open</option>
            <option value="escalated">Escalated to law enforcement</option>
            <option value="dismissed">Dismissed as a false alert</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="review-note">Note</label>
          <textarea id="review-note" value={note} onChange={(e) => { setNote(e.target.value); setState(null) }} />
        </div>
        <div className="row">
          <button className="btn" disabled={state === 'saving'}>{state === 'saving' ? 'Saving…' : 'Save decision'}</button>
          {state === 'saved' && <span className="small" role="status">Saved</span>}
          {state && state !== 'saved' && state !== 'saving' && <span className="small" style={{ color: 'var(--critical)' }} role="alert">{state}</span>}
        </div>
      </form>
    </section>
  )
}
