import { useEffect, useState } from 'react'
import { api } from '../api'
import { Tile, pct } from '../components/bits'

const f3 = (x) => (x == null ? '—' : x.toFixed(3))

export default function Model() {
  const [m, setM] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => { api.metrics().then(setM).catch((e) => setError(e.message)) }, [])

  const head = (
    <div className="page-head">
      <div>
        <h1>Model evaluation</h1>
        <p>Measured on a chronological holdout: trained on older wallets and tested on the newest ones, which the model never saw while being built.</p>
      </div>
    </div>
  )
  if (error) return <>{head}<div className="callout">{error}</div></>
  if (!m) return <>{head}<p className="muted">Loading results…</p></>

  const t = m.final_test
  const bySelected = [...m.comparison].sort((a, b) => b.validation.pr_auc - a.validation.pr_auc)
  const at1pct = m.real_world_precision.find((r) => r.prevalence === 0.01)
  const selected = m.comparison.find((row) => row.model === m.selected_model)
  const check = m.selection_check

  return (
    <>
      {head}
      <div className="stack">
        <div className="tiles">
          <Tile label="Selected model" value={<span style={{ fontSize: 19 }}>{m.selected_model}</span>} note={`Version ${m.model_version}`} />
          <Tile label="PR-AUC" value={f3(t.pr_auc)} note="Test set, calibrated scores" />
          <Tile label="Precision" value={pct(t.precision)} note={`${t.fp} false alerts`} />
          <Tile label="Recall" value={pct(t.recall)} note={`${t.fn} flagged wallets missed`} />
          <Tile label="F1" value={f3(t.f1)} note={`Accuracy ${pct(t.accuracy)}`} />
        </div>

        <div className="callout callout-warning">
          <strong>Read this before quoting these numbers.</strong> The test set is {pct(m.splits.test.flagged / m.splits.test.wallets)} flagged wallets, far more than real traffic. If only 1% of wallets were fraudulent, the same model's precision would fall to about <strong>{pct(at1pct?.at_decision)}</strong>, so most alerts would be false. That is why this system ranks wallets for human review and never declares fraud.
        </div>

        <div className="callout callout-warning">
          <strong>How comparison wallets were chosen.</strong> Random blocks favour busy wallets, so each flagged wallet is paired with up to two random wallets from the same period and the same activity band. Some bands could not be filled completely, so quiet bands have fewer comparison wallets per flagged wallet than busy ones. Results per band below come from small groups, so read them as rough.
        </div>

        {check.test_by_band && (
          <section className="card">
            <div className="card-head"><h2>Results by activity level</h2><p>Activity is the number of transactions, contract payments and token transfers read for a wallet. Test set, at the alert cut-off.</p></div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Activity</th><th className="r">Flagged in dataset</th><th className="r">Comparison in dataset</th><th className="r">Test false alerts</th><th className="r">Test flagged caught</th></tr></thead>
                <tbody>
                  {check.test_by_band.map((b) => (
                    <tr key={b.band}>
                      <td>{b.band}</td>
                      <td className="r">{b.dataset_flagged}</td>
                      <td className="r">{b.dataset_controls}</td>
                      <td className="r">{b.fp} of {b.fp + b.tn}{b.fp + b.tn ? ` (${pct(b.fpr)})` : ''}</td>
                      <td className="r">{b.tp} of {b.tp + b.fn}{b.tp + b.fn ? ` (${pct(b.recall)})` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        <div className="grid-2">
          <section className="card">
            <div className="card-head"><h2>Precision and recall</h2><p>Every point is a possible alert cut-off. Moving right catches more flagged wallets at the cost of more false alerts.</p></div>
            <PRChart points={m.pr_curve} operating={m.threshold_table} thresholds={m.thresholds} />
          </section>
          <section className="card">
            <div className="card-head"><h2>Confusion matrix</h2><p>Test set, at the cut-off chosen on validation data ({f3(m.thresholds.decision)}).</p></div>
            <div className="cm" role="table" aria-label="Confusion matrix">
              <div className="h" />
              <div className="h">Model: not alerted</div>
              <div className="h">Model: alerted</div>
              <div className="h">Control wallet</div>
              <div><span className="v">{t.tn}</span>Correctly passed</div>
              <div className="bad"><span className="v">{t.fp}</span>False alerts</div>
              <div className="h">Flagged wallet</div>
              <div className="bad"><span className="v">{t.fn}</span>Missed</div>
              <div><span className="v">{t.tp}</span>Correctly alerted</div>
            </div>
            <h3 style={{ marginTop: 16 }}>Triage levels on the test set</h3>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Level</th><th className="r">Wallets</th><th className="r">Actually flagged</th><th className="r">Share</th></tr></thead>
                <tbody>
                  {['high', 'medium', 'low'].map((level) => {
                    const row = m.triage_on_test[level]
                    return <tr key={level}><td style={{ textTransform: 'capitalize' }}>{level}</td><td className="r">{row.wallets}</td><td className="r">{row.flagged}</td><td className="r">{row.wallets ? pct(row.flagged / row.wallets) : '—'}</td></tr>
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        <section className="card">
          <div className="card-head"><h2>Model comparison</h2><p>The four baselines from the literature review, each with and without SMOTE. Selection used validation PR-AUC only. Test columns are for reporting.</p></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Model</th><th className="r">Val PR-AUC</th><th className="r">Test PR-AUC</th><th className="r">Test precision</th><th className="r">Test recall</th><th className="r">Test F1</th><th className="r">Test accuracy</th><th className="r">False alerts</th></tr></thead>
              <tbody>
                {bySelected.map((row) => (
                  <tr key={row.model} className={row.model === m.selected_model ? 'selected' : ''}>
                    <td>{row.model}{row.model === m.selected_model && <span className="badge badge-info" style={{ marginLeft: 8 }}>Selected</span>}</td>
                    <td className="r">{f3(row.validation.pr_auc)}</td>
                    <td className="r">{f3(row.test.pr_auc)}</td>
                    <td className="r">{pct(row.test.precision)}</td>
                    <td className="r">{pct(row.test.recall)}</td>
                    <td className="r">{f3(row.test.f1)}</td>
                    <td className="r">{pct(row.test.accuracy)}</td>
                    <td className="r">{row.test.fp}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 10, marginBottom: 0 }}>
            This table shows scores before calibration. Calibration groups scores into steps, which is why the selected model's PR-AUC at the top of this page is {f3(t.pr_auc)} rather than {f3(selected.test.pr_auc)}. Before calibration, a random split of the same data gives PR-AUC {f3(m.random_split_contrast.pr_auc)}, against {f3(selected.test.pr_auc)} on the chronological split, which shows how much a random split can flatter a model. Cross-validated ROC-AUC on the training period: {f3(m.cv_train_roc_auc.mean)} ± {f3(m.cv_train_roc_auc.std)}.
          </p>
        </section>

        <div className="grid-2">
          <section className="card">
            <div className="card-head"><h2>Most influential features</h2><p>Global importance in the selected model. Importance is not cause.</p></div>
            <Importance items={m.feature_importance.slice(0, 10)} />
          </section>
          <section className="card">
            <div className="card-head"><h2>Precision if fraud is rare</h2><p>Recall and false-alert rate carry over from the test set. Precision depends on how common fraud is.</p></div>
            <div className="table-wrap">
              <table>
                <thead><tr><th>If this share of wallets were fraudulent</th><th className="r">Expected precision</th></tr></thead>
                <tbody>
                  {m.real_world_precision.map((r) => <tr key={r.prevalence}><td>{pct(r.prevalence)}</td><td className="r">{pct(r.at_decision, 1)}</td></tr>)}
                  <tr><td>Test set ({pct(m.splits.test.flagged / m.splits.test.wallets)})</td><td className="r">{pct(t.precision, 1)}</td></tr>
                </tbody>
              </table>
            </div>
            <h3 style={{ marginTop: 16 }}>Alert cut-offs on the test set</h3>
            <div className="table-wrap">
              <table>
                <thead><tr><th className="r">Cut-off</th><th className="r">Precision</th><th className="r">Recall</th><th className="r">False alerts</th><th className="r">Missed</th></tr></thead>
                <tbody>{m.threshold_table.map((r) => <tr key={r.threshold}><td className="r">{f3(r.threshold)}</td><td className="r">{pct(r.precision)}</td><td className="r">{pct(r.recall)}</td><td className="r">{r.fp}</td><td className="r">{r.fn}</td></tr>)}</tbody>
              </table>
            </div>
          </section>
        </div>

        <section className="card">
          <div className="card-head"><h2>Error review</h2><p>What the model's mistakes have in common, measured in training-set standard deviations against the wallets it got right. Use this to refine features and cut-offs.</p></div>
          <div className="grid-2">
            {Object.entries(m.error_review).map(([key, group]) => (
              <div key={key}>
                <h3>{key === 'false_positive' ? 'False alerts' : 'Missed wallets'}: {group.count}</h3>
                <p className="small ink-2">{group.meaning}</p>
                {group.patterns.length === 0 ? <p className="small muted">Too few cases to compare.</p> : (
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {group.patterns.map((p) => <li key={p.feature} className="small">{p.description}: {p.direction} ({p.effect.toFixed(2)} SD)</li>)}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2>Dataset record</h2><p>Collected from live chain data, so training and scoring use identical feature code.</p></div>
          <dl className="kv">
            <dt>Wallets</dt><dd className="num">{m.dataset.wallets} ({m.dataset.flagged} flagged, {m.dataset.controls} controls)</dd>
            <dt>Sources</dt><dd>{Object.entries(m.dataset.sources).map(([k, v]) => `${k}: ${v}`).join(' · ')}</dd>
            <dt>Date span</dt><dd>{m.dataset.date_range.join(' to ')}</dd>
            <dt>Labels</dt><dd>{m.dataset.label_definition}</dd>
            <dt>Features</dt><dd>{m.feature_count} behaviour features. No timestamps or list membership.</dd>
          </dl>
          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead><tr><th>Split</th><th className="r">Wallets</th><th className="r">Flagged</th><th>From</th><th>To</th></tr></thead>
              <tbody>{Object.entries(m.splits).map(([name, s]) => <tr key={name}><td style={{ textTransform: 'capitalize' }}>{name}</td><td className="r">{s.wallets}</td><td className="r">{s.flagged}</td><td>{s.from}</td><td>{s.to}</td></tr>)}</tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  )
}

function Importance({ items }) {
  const max = Math.max(...items.map((i) => i.importance))
  return (
    <div>
      {items.map((item) => (
        <div className="hbar" key={item.feature}>
          <span>{item.description}</span>
          <div className="hbar-track" aria-hidden="true"><div className="hbar-fill" style={{ width: `${(item.importance / max) * 100}%` }} /></div>
          <span className="num small muted" style={{ textAlign: 'right' }}>{pct(item.importance)}</span>
        </div>
      ))}
    </div>
  )
}

function PRChart({ points, thresholds }) {
  const [hover, setHover] = useState(null)
  const W = 460, H = 300, L = 44, R = 12, T = 12, B = 40
  const x = (r) => L + r * (W - L - R)
  const y = (p) => T + (1 - p) * (H - T - B)
  const sorted = [...points].sort((a, b) => a.recall - b.recall)
  const path = sorted.map((p, i) => `${i ? 'L' : 'M'}${x(p.recall).toFixed(1)},${y(p.precision).toFixed(1)}`).join(' ')
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  const nearest = (cut) => points.reduce((best, p) => (Math.abs(p.threshold - cut) < Math.abs(best.threshold - cut) ? p : best), points[0])
  const marks = [
    { label: 'Medium', ...nearest(thresholds.medium) },
    { label: 'High', ...nearest(thresholds.high) },
  ]

  const onMove = (event) => {
    const box = event.currentTarget.getBoundingClientRect()
    const recall = (((event.clientX - box.left) / box.width) * W - L) / (W - L - R)
    const point = sorted.reduce((best, p) => (Math.abs(p.recall - recall) < Math.abs(best.recall - recall) ? p : best), sorted[0])
    setHover(point)
  }

  return (
    <div className="chart-box">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Precision against recall on the test set. Values are also in the table below."
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="var(--grid)" />
            <text x={L - 8} y={y(v) + 4} textAnchor="end">{v * 100}%</text>
            <text x={x(v)} y={H - B + 18} textAnchor="middle">{v * 100}%</text>
          </g>
        ))}
        <line x1={L} x2={W - R} y1={y(0)} y2={y(0)} stroke="var(--axis)" />
        <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle">Recall</text>
        <text transform={`translate(11,${(T + H - B) / 2}) rotate(-90)`} textAnchor="middle">Precision</text>
        <path d={path} fill="none" stroke="var(--s-exchange)" strokeWidth="2" strokeLinejoin="round" />
        {marks.map((mark) => (
          <g key={mark.label}>
            <circle cx={x(mark.recall)} cy={y(mark.precision)} r="5" fill="var(--s-exchange)" stroke="var(--surface)" strokeWidth="2" />
            <text className="strong" x={x(mark.recall)} y={y(mark.precision) + 20} textAnchor="middle">{mark.label}</text>
          </g>
        ))}
        {hover && (
          <g pointerEvents="none">
            <line x1={x(hover.recall)} x2={x(hover.recall)} y1={T} y2={H - B} stroke="var(--axis)" />
            <circle cx={x(hover.recall)} cy={y(hover.precision)} r="5" fill="var(--s-exchange)" stroke="var(--surface)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover && (
        <div className="chart-tip" style={{ left: `${(x(hover.recall) / W) * 100}%`, top: `${(y(hover.precision) / H) * 100}%` }}>
          Recall {pct(hover.recall)} · Precision {pct(hover.precision)} · Cut-off {hover.threshold.toFixed(3)}
        </div>
      )}
    </div>
  )
}
