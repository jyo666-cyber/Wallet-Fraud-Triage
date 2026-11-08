import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Address, Reasons, RiskSummary } from '../components/bits'

export default function WalletCheck() {
  const [address, setAddress] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const check = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(await api.walletRisk(address.trim()))
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
          <h1>Wallet check</h1>
          <p>A quick behaviour score for one address, with no case created and no trace. To follow the money, <Link to="/new">file a report</Link> instead.</p>
        </div>
      </div>
      <div className="stack">
        <form className="card row" onSubmit={check} style={{ flexWrap: 'nowrap' }}>
          <label htmlFor="check-address" style={{ whiteSpace: 'nowrap', fontWeight: 600 }}>Address</label>
          <input id="check-address" className="mono" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="0x…" autoComplete="off" spellCheck="false" />
          <button className="btn btn-primary" disabled={busy || !address.trim()}>{busy ? 'Checking…' : 'Check'}</button>
        </form>
        {error && <div className="callout callout-critical" role="alert">{error}</div>}
        {result && (
          <section className="card">
            <div style={{ marginBottom: 12 }}><Address value={result.address} /></div>
            {result.entity && (
              <div className="callout" style={{ marginBottom: 12 }}>Labelled as <strong>{result.entity.name}</strong> ({result.entity.category}). A service wallet does not behave like the wallets this model was trained on, so read the score with care.</div>
            )}
            {result.list_flags.length > 0 && (
              <div className="callout callout-critical" style={{ marginBottom: 12 }}>
                <strong>On {result.list_flags.length} public fraud list entr{result.list_flags.length === 1 ? 'y' : 'ies'}:</strong> {result.list_flags.slice(0, 3).join('; ')}
              </div>
            )}
            <RiskSummary risk={result.risk} />
            {result.risk.reasons && <><h3 style={{ marginTop: 14 }}>Main factors</h3><Reasons reasons={result.risk.reasons} /></>}
          </section>
        )}
      </div>
    </>
  )
}
