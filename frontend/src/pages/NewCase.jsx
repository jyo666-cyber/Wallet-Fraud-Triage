import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'

const EMPTY = { address: '', victim_tx: '', amount_lost: '', incident_date: '', description: '', reporter_ref: '' }

export default function NewCase() {
  const [form, setForm] = useState(EMPTY)
  const [fields, setFields] = useState({})
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const navigate = useNavigate()
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  const submit = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setFields({})
    try {
      const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null]))
      const { id } = await api.createCase(body)
      navigate(`/cases/${id}`)
    } catch (e) {
      setError(e.message)
      setFields(e.fields || {})
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Report a suspect wallet</h1>
          <p>We read the wallet's history from Ethereum, assess its behaviour, and follow the money forward to see whether it reached an exchange.</p>
        </div>
      </div>
      <div className="card">
        <form className="form" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="address">Suspect wallet address</label>
            <input id="address" className={fields.address ? 'invalid mono' : 'mono'} value={form.address} onChange={set('address')} placeholder="0x…" autoComplete="off" spellCheck="false" aria-describedby="address-msg" required />
            {fields.address
              ? <span id="address-msg" className="error">{fields.address}</span>
              : <span id="address-msg" className="hint">The Ethereum wallet you sent funds to.</span>}
          </div>
          <div className="field">
            <label htmlFor="victim_tx">Your transaction hash (optional)</label>
            <input id="victim_tx" className={fields.victim_tx ? 'invalid mono' : 'mono'} value={form.victim_tx} onChange={set('victim_tx')} placeholder="0x…" autoComplete="off" spellCheck="false" aria-describedby="tx-msg" />
            {fields.victim_tx
              ? <span id="tx-msg" className="error">{fields.victim_tx}</span>
              : <span id="tx-msg" className="hint">With this, the trace only follows money that moved after your payment, which gives a tighter result.</span>}
          </div>
          <div className="form-pair">
            <div className="field">
              <label htmlFor="amount_lost">Amount lost (optional)</label>
              <input id="amount_lost" value={form.amount_lost} onChange={set('amount_lost')} placeholder="1.5 ETH" />
            </div>
            <div className="field">
              <label htmlFor="incident_date">Date of incident (optional)</label>
              <input id="incident_date" type="date" value={form.incident_date} onChange={set('incident_date')} />
            </div>
          </div>
          <div className="field">
            <label htmlFor="description">What happened (optional)</label>
            <textarea id="description" value={form.description} onChange={set('description')} placeholder="How you were contacted, and what you were promised." />
            <span className="hint">This appears in the sealed report. Leave out passwords and seed phrases, which you should never share with anyone.</span>
          </div>
          <div className="field">
            <label htmlFor="reporter_ref">Your reference (optional)</label>
            <input id="reporter_ref" value={form.reporter_ref} onChange={set('reporter_ref')} placeholder="A police complaint number, for example" />
            <span className="hint">Stored only in this local system and left out of the sealed report.</span>
          </div>
          {error && <div className="callout callout-critical" role="alert">{error}</div>}
          <div className="row">
            <button className="btn btn-primary" type="submit" disabled={busy}>{busy ? 'Submitting…' : 'Submit and start trace'}</button>
          </div>
        </form>
      </div>
    </>
  )
}
