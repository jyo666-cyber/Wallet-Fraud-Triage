import { useMemo, useState } from 'react'
import { formatAmount, shortAddr } from './bits'

const KIND = {
  suspect: { label: 'Suspect wallet', color: 'var(--s-suspect)' },
  wallet: { label: 'Unlabelled wallet', color: 'var(--s-wallet)' },
  exchange: { label: 'Exchange', color: 'var(--s-exchange)' },
  deposit_candidate: { label: 'Likely deposit address', color: 'var(--s-deposit)' },
  mixer: { label: 'Mixer', color: 'var(--s-mixer)' },
  dex: { label: 'DEX', color: 'var(--s-dex)' },
  bridge: { label: 'Bridge', color: 'var(--s-bridge)' },
  high_activity: { label: 'Busy unlabelled address (not followed)', color: 'transparent' },
}

const COL_W = 210
const ROW_H = 62
const PAD = 26

export default function FlowGraph({ nodes, edges }) {
  const [tip, setTip] = useState(null)

  const layout = useMemo(() => {
    const columns = new Map()
    nodes.forEach((n) => {
      if (!columns.has(n.hop)) columns.set(n.hop, [])
      columns.get(n.hop).push(n)
    })
    const tallest = Math.max(1, ...[...columns.values()].map((c) => c.length))
    const height = tallest * ROW_H + PAD
    const positions = new Map()
    columns.forEach((column, hop) => {
      const offset = (height - column.length * ROW_H) / 2
      column.forEach((n, i) => {
        positions.set(n.id, { x: PAD + hop * COL_W, y: offset + i * ROW_H + ROW_H / 2 })
      })
    })
    const width = PAD * 2 + Math.max(0, ...columns.keys()) * COL_W + 150
    return { positions, width, height }
  }, [nodes])

  // Several transfers can link one pair of addresses; each pair is drawn once.
  const links = useMemo(() => {
    const grouped = new Map()
    edges.forEach((e) => {
      const key = `${e.source}|${e.target}`
      if (!grouped.has(key)) grouped.set(key, { source: e.source, target: e.target, parts: [] })
      grouped.get(key).parts.push(`${formatAmount(e.amount)} ${e.asset}`)
    })
    return [...grouped.values()]
  }, [edges])

  const kinds = [...new Set(nodes.map((n) => n.kind))]

  return (
    <div className="chart-box">
      <div className="flow-scroll">
        <svg width={layout.width} height={layout.height} role="img" aria-label={`Fund flow with ${nodes.length} addresses and ${links.length} links. The same transfers are listed in the table below.`}>
          {links.map((link) => {
            const a = layout.positions.get(link.source)
            const b = layout.positions.get(link.target)
            if (!a || !b) return null
            const mid = (a.x + b.x) / 2
            const label = link.parts.join(' + ')
            return (
              <g key={`${link.source}${link.target}`}>
                <path d={`M${a.x},${a.y} C${mid},${a.y} ${mid},${b.y} ${b.x},${b.y}`} className="flow-edge">
                  <title>{label}</title>
                </path>
                {/* Wider invisible stroke: a 1.5px line is too thin a hover target. */}
                <path
                  d={`M${a.x},${a.y} C${mid},${a.y} ${mid},${b.y} ${b.x},${b.y}`}
                  fill="none" stroke="transparent" strokeWidth="16"
                  onMouseEnter={() => setTip({ x: mid, y: (a.y + b.y) / 2, label })}
                  onMouseLeave={() => setTip(null)}
                />
              </g>
            )
          })}
          {nodes.map((n) => {
            const p = layout.positions.get(n.id)
            const kind = KIND[n.kind] || KIND.wallet
            const flagged = n.flags?.length > 0
            const twoLines = Boolean(n.name) || n.kind === 'suspect'
            return (
              <g key={n.id} className="flow-node" transform={`translate(${p.x},${p.y})`}>
                <title>{n.id}</title>
                <circle
                  r={n.kind === 'suspect' || n.kind === 'exchange' ? 9 : 7}
                  fill={kind.color === 'transparent' ? 'var(--surface)' : kind.color}
                  stroke={kind.color === 'transparent' ? 'var(--muted)' : 'var(--surface)'}
                  strokeWidth="2"
                />
                <a href={`https://etherscan.io/address/${n.id}`} target="_blank" rel="noreferrer">
                  <text x="14" y={twoLines ? -2 : 4} className={twoLines ? 'name' : ''}>
                    {n.name ? truncate(n.name, 24) : n.kind === 'suspect' ? 'Suspect wallet' : shortAddr(n.id)}
                  </text>
                  {twoLines && <text x="14" y="13">{shortAddr(n.id)}</text>}
                </a>
                {flagged && <text x="14" y={twoLines ? 27 : 19} style={{ fill: 'var(--critical)' }}>On a fraud list</text>}
              </g>
            )
          })}
        </svg>
      </div>
      {tip && <div className="chart-tip" style={{ left: tip.x, top: tip.y }}>{tip.label}</div>}
      <div className="legend">
        {kinds.map((k) => (
          <span key={k}>
            <i style={{ background: KIND[k]?.color === 'transparent' ? 'var(--surface)' : KIND[k]?.color, border: KIND[k]?.color === 'transparent' ? '1.5px solid var(--muted)' : 0 }} />
            {KIND[k]?.label || k}
          </span>
        ))}
      </div>
    </div>
  )
}

function truncate(text, n) {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text
}
