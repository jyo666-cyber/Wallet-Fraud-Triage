async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`/api${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch {
    throw new Error('Could not reach the backend. Check that it is running.')
  }
  if (response.ok) return response.json()

  const body = await response.json().catch(() => ({}))
  const error = new Error('The request failed. Please try again.')
  if (typeof body.detail === 'string') error.message = body.detail
  if (Array.isArray(body.detail)) {
    // Field-level validation errors from the API, keyed by field name.
    error.fields = Object.fromEntries(
      body.detail.map((d) => [d.loc?.[d.loc.length - 1], d.msg.replace(/^Value error, /, '')]),
    )
    error.message = 'Please fix the highlighted fields.'
  }
  throw error
}

export const api = {
  health: () => request('/health'),
  cases: () => request('/cases'),
  case: (id) => request(`/cases/${id}`),
  createCase: (body) => request('/cases', { method: 'POST', body: JSON.stringify(body) }),
  review: (id, body) => request(`/cases/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  walletRisk: (address) => request(`/wallets/${encodeURIComponent(address)}/risk`),
  metrics: () => request('/model/metrics'),
  audit: () => request('/audit'),
  verifyAudit: () => request('/audit/verify'),
}
